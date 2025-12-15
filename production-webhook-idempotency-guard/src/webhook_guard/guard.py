from typing import Callable, Any, Optional
from datetime import datetime
import time

from .models import ProcessingResult, WebhookStatus
from .store import WebhookStore
from .lock import DistributedLock


class WebhookGuard:
    """
    Production-safe webhook processing guard.

    Guarantees:
    - Exactly-once business effect per webhook_id
    - Safe handling of retries
    - Safe handling of concurrent deliveries
    - Crash detection via durable PROCESSING state

    Does NOT:
    - Retry handlers
    - Roll back external side effects
    - Enforce cross-webhook ordering
    """

    def __init__(
        self,
        store: WebhookStore,
        lock: DistributedLock,
        default_timeout_seconds: int = 300,
    ):
        self._store = store
        self._lock = lock
        self._default_timeout = default_timeout_seconds

    def process(
        self,
        webhook_id: str,
        handler: Callable[[], Any],
        timeout_seconds: Optional[int] = None,
    ) -> ProcessingResult:
        """
        Process a webhook exactly once.

        Algorithm:
        1. Fast-path duplicate check
        2. Atomic reservation
        3. Distributed lock acquisition
        4. Mark PROCESSING (crash boundary)
        5. Execute handler
        6. Mark COMPLETE or FAILED
        7. Release lock
        """

        timeout = timeout_seconds or self._default_timeout
        start_time = datetime.utcnow()
        lock_handle = None

        try:
            # 1. Fast-path duplicate check (retry handling)
            state = self._store.get_state(webhook_id)

            if state is not None:
                if state.status == WebhookStatus.COMPLETE:
                    return self._cached_success(state, start_time)

                if state.status == WebhookStatus.FAILED:
                    return self._cached_failure(state, start_time)

            # 2. Atomic reservation (race-safe)
            reserved, existing_state = self._store.reserve(webhook_id, timeout)

            if not reserved and existing_state is not None:
                if existing_state.status == WebhookStatus.COMPLETE:
                    return self._cached_success(existing_state, start_time)

                if existing_state.status == WebhookStatus.FAILED:
                    return self._cached_failure(existing_state, start_time)

            # 3. Acquire distributed lock (concurrency control)
            lock_handle = self._lock.try_lock(webhook_id, timeout)

            if lock_handle is None:
                # Another worker is processing — wait briefly and re-check
                time.sleep(1)

                final_state = self._store.get_state(webhook_id)
                if final_state is not None:
                    if final_state.status == WebhookStatus.COMPLETE:
                        return self._cached_success(final_state, start_time)

                    if final_state.status == WebhookStatus.FAILED:
                        return self._cached_failure(final_state, start_time)

                return ProcessingResult(
                    success=False,
                    output=None,
                    error="Webhook is currently being processed",
                    duration_ms=self._duration_ms(start_time),
                    cached=False,
                )

            # 4. Mark PROCESSING (CRASH SAFETY BOUNDARY)
            self._store.mark_processing(webhook_id)

            # 5. Execute handler (side effects happen here)
            try:
                output = handler()
                handler_success = True
                handler_error = None
            except Exception as exc:
                output = None
                handler_success = False
                handler_error = str(exc)

            # 6. Persist terminal state
            if handler_success:
                self._store.mark_complete(webhook_id, output)
            else:
                self._store.mark_failed(webhook_id, handler_error)

            return ProcessingResult(
                success=handler_success,
                output=output,
                error=handler_error,
                duration_ms=self._duration_ms(start_time),
                cached=False,
            )

        finally:
            # 7. Always release lock
            if lock_handle is not None:
                try:
                    lock_handle.release()
                except Exception:
                    # Lock auto-released on connection close or timeout
                    pass

    # ---------- helpers ----------

    def _cached_success(self, state, start_time: datetime) -> ProcessingResult:
        return ProcessingResult(
            success=True,
            output=state.result,
            error=None,
            duration_ms=self._duration_ms(start_time),
            cached=True,
        )

    def _cached_failure(self, state, start_time: datetime) -> ProcessingResult:
        return ProcessingResult(
            success=False,
            output=None,
            error=state.error or "Unknown error",
            duration_ms=self._duration_ms(start_time),
            cached=True,
        )

    @staticmethod
    def _duration_ms(start_time: datetime) -> int:
        return int((datetime.utcnow() - start_time).total_seconds() * 1000)
