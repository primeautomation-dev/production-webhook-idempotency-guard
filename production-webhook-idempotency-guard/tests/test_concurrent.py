"""
Tests proving webhook processing safety under concurrent execution.

Validates that:
- Concurrent requests do not cause duplicate execution
- Distributed lock enforces single execution
- Cached results are returned correctly under race conditions
"""

import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, Any, List

from webhook_guard.guard import WebhookGuard
from webhook_guard.models import WebhookStatus, WebhookState, ProcessingResult
from webhook_guard.store import InMemoryStore


# -------- fake distributed lock --------

class FakeLockHandle:
    def __init__(self, lock, key: str):
        self._lock = lock
        self._key = key

    def release(self) -> None:
        self._lock._release(self._key)


class FakeDistributedLock:
    """
    Thread-safe fake distributed lock.

    Guarantees:
    - Only one holder per key
    - Non-blocking acquisition
    """

    def __init__(self):
        self._held = set()
        self._lock = threading.Lock()

    def try_lock(self, key: str, timeout_seconds: int) -> Optional[FakeLockHandle]:
        with self._lock:
            if key in self._held:
                return None
            self._held.add(key)
            return FakeLockHandle(self, key)

    def _release(self, key: str) -> None:
        with self._lock:
            self._held.discard(key)


# -------- tests --------

def test_concurrent_requests_execute_once():
    """
    Scenario:
    10 workers concurrently process the same webhook_id.

    Expectation:
    - Handler executes EXACTLY once
    - One non-cached success
    - Other requests return cached result or in-progress failure
    """

    store = InMemoryStore()
    lock = FakeDistributedLock()
    guard = WebhookGuard(store=store, lock=lock)

    execution_count = 0
    counter_lock = threading.Lock()

    def make_handler():
        def handler():
            nonlocal execution_count
            with counter_lock:
                execution_count += 1
                current = execution_count
            time.sleep(0.01)  # amplify race window
            return {"execution": current}
        return handler

    webhook_id = "concurrent-webhook-1"
    results: List[ProcessingResult] = []

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [
            executor.submit(guard.process, webhook_id, make_handler(), 60)
            for _ in range(10)
        ]
        for future in as_completed(futures):
            results.append(future.result())

    # CRITICAL: handler executed once
    assert execution_count == 1

    # Exactly one fresh success
    fresh = [r for r in results if r.success and not r.cached]
    assert len(fresh) == 1

    # Cached successes must match output
    cached = [r for r in results if r.cached]
    assert len(cached) > 0

    for r in cached:
        assert r.output == {"execution": 1}


def test_concurrent_side_effect_not_duplicated():
    """
    Scenario:
    Payment-style side effect under heavy concurrency.

    Expectation:
    - Side effect occurs once
    - All successful results are consistent
    """

    store = InMemoryStore()
    lock = FakeDistributedLock()
    guard = WebhookGuard(store=store, lock=lock)

    execution_count = 0
    side_effects = []
    counter_lock = threading.Lock()

    def make_handler():
        def handler():
            nonlocal execution_count
            with counter_lock:
                execution_count += 1
                side_effects.append("charged")
                current = execution_count
            time.sleep(0.02)
            return {"payment_id": f"PAY-{current}"}
        return handler

    webhook_id = "payment-webhook-1"
    results: List[ProcessingResult] = []

    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = [
            executor.submit(guard.process, webhook_id, make_handler(), 60)
            for _ in range(20)
        ]
        for future in as_completed(futures):
            results.append(future.result())

    # Side effect once
    assert execution_count == 1
    assert side_effects == ["charged"]

    successes = [r for r in results if r.success]
    assert len(successes) > 0

    for r in successes:
        assert r.output == {"payment_id": "PAY-1"}
