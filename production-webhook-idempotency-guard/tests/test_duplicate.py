"""
Tests proving webhook idempotency under duplicate (retry) delivery.

Validates that:
- Sequential retries do not re-execute side effects
- Cached results are returned after success
- Cached failures are returned after permanent failure
"""

from typing import Optional, Any
from datetime import datetime, timedelta

from webhook_guard.guard import WebhookGuard
from webhook_guard.models import WebhookStatus, WebhookState, ProcessingResult
from webhook_guard.store import InMemoryStore


# -------- fake distributed lock (always succeeds, no concurrency here) --------

class FakeLockHandle:
    def __init__(self, lock, key: str):
        self._lock = lock
        self._key = key

    def release(self) -> None:
        self._lock._release(self._key)


class FakeDistributedLock:
    def __init__(self):
        self._held = set()

    def try_lock(self, key: str, timeout_seconds: int) -> Optional[FakeLockHandle]:
        if key in self._held:
            return None
        self._held.add(key)
        return FakeLockHandle(self, key)

    def _release(self, key: str) -> None:
        self._held.discard(key)


# -------- tests --------

def test_sequential_retries_execute_once():
    """
    Scenario:
    Same webhook is delivered multiple times sequentially.

    Expectation:
    - Handler executes exactly once
    - Subsequent calls return cached result
    """

    store = InMemoryStore()
    lock = FakeDistributedLock()
    guard = WebhookGuard(store=store, lock=lock)

    execution_count = 0

    def handler():
        nonlocal execution_count
        execution_count += 1
        return {"count": execution_count}

    webhook_id = "duplicate-webhook-1"

    # First delivery
    result1 = guard.process(webhook_id, handler, 60)
    assert result1.success is True
    assert result1.cached is False
    assert result1.output == {"count": 1}
    assert execution_count == 1

    # Second delivery (retry)
    result2 = guard.process(webhook_id, handler, 60)
    assert result2.success is True
    assert result2.cached is True
    assert result2.output == {"count": 1}
    assert execution_count == 1

    # Third delivery (retry)
    result3 = guard.process(webhook_id, handler, 60)
    assert result3.success is True
    assert result3.cached is True
    assert result3.output == {"count": 1}
    assert execution_count == 1


def test_retry_after_success_returns_cached_result():
    """
    Scenario:
    First execution succeeds, client retries due to timeout.

    Expectation:
    - Side effect executed once
    - Retry returns cached success
    """

    store = InMemoryStore()
    lock = FakeDistributedLock()
    guard = WebhookGuard(store=store, lock=lock)

    execution_count = 0

    def handler():
        nonlocal execution_count
        execution_count += 1
        return {"status": "confirmed"}

    webhook_id = "order-webhook-1"

    result1 = guard.process(webhook_id, handler, 60)
    assert result1.success is True
    assert result1.cached is False
    assert execution_count == 1

    result2 = guard.process(webhook_id, handler, 60)
    assert result2.success is True
    assert result2.cached is True
    assert execution_count == 1


def test_retry_after_failure_returns_cached_failure():
    """
    Scenario:
    Handler fails permanently, client retries.

    Expectation:
    - Handler executed once
    - Failure cached
    - Retries do NOT re-execute handler
    """

    store = InMemoryStore()
    lock = FakeDistributedLock()
    guard = WebhookGuard(store=store, lock=lock)

    execution_count = 0

    def failing_handler():
        nonlocal execution_count
        execution_count += 1
        raise ValueError("invalid payload")

    webhook_id = "failure-webhook-1"

    # First attempt fails
    result1 = guard.process(webhook_id, failing_handler, 60)
    assert result1.success is False
    assert result1.cached is False
    assert "invalid payload" in result1.error
    assert execution_count == 1

    # Retry returns cached failure
    result2 = guard.process(webhook_id, failing_handler, 60)
    assert result2.success is False
    assert result2.cached is True
    assert "invalid payload" in result2.error
    assert execution_count == 1

    # Further retries still cached
    result3 = guard.process(webhook_id, failing_handler, 60)
    assert result3.success is False
    assert result3.cached is True
    assert execution_count == 1
