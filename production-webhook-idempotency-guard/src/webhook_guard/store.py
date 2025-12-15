from typing import Optional, Tuple, Any, Protocol
from datetime import datetime, timedelta

from .models import WebhookState, WebhookStatus


class WebhookStore(Protocol):
    """
    Persistence boundary for webhook processing state.

    Guarantees:
    - Atomic reservation
    - Valid state transitions only
    - Terminal states are immutable
    """

    def get_state(self, webhook_id: str) -> Optional[WebhookState]:
        ...

    def reserve(self, webhook_id: str, timeout_seconds: int) -> Tuple[bool, Optional[WebhookState]]:
        ...

    def mark_processing(self, webhook_id: str) -> None:
        ...

    def mark_complete(self, webhook_id: str, result: Any) -> None:
        ...

    def mark_failed(self, webhook_id: str, error: str) -> None:
        ...


class InMemoryStore:
    """
    In-memory reference implementation.

    Used for:
    - Tests
    - Local experiments
    - Demonstrating state transition rules

    NOT for production.
    """

    def __init__(self):
        self._data: dict[str, WebhookState] = {}

    def get_state(self, webhook_id: str) -> Optional[WebhookState]:
        return self._data.get(webhook_id)

    def reserve(self, webhook_id: str, timeout_seconds: int) -> Tuple[bool, Optional[WebhookState]]:
        """
        Atomic reservation semantics.

        Returns:
            (True, None) if newly reserved
            (False, existing_state) if already exists
        """
        existing = self._data.get(webhook_id)
        if existing is not None:
            return False, existing

        now = datetime.utcnow()
        state = WebhookState(
            webhook_id=webhook_id,
            status=WebhookStatus.PENDING,
            reserved_until=now + timedelta(seconds=timeout_seconds),
            result=None,
            error=None,
            created_at=now,
            updated_at=now,
        )
        self._data[webhook_id] = state
        return True, None

    def mark_processing(self, webhook_id: str) -> None:
        state = self._data.get(webhook_id)
        if state is None:
            raise ValueError(f"Webhook {webhook_id} does not exist")

        if state.status != WebhookStatus.PENDING:
            raise ValueError(
                f"Webhook {webhook_id} is in {state.status} state, cannot mark PROCESSING"
            )

        self._data[webhook_id] = WebhookState(
            webhook_id=state.webhook_id,
            status=WebhookStatus.PROCESSING,
            reserved_until=state.reserved_until,
            result=state.result,
            error=state.error,
            created_at=state.created_at,
            updated_at=datetime.utcnow(),
        )

    def mark_complete(self, webhook_id: str, result: Any) -> None:
        state = self._data.get(webhook_id)
        if state is None:
            raise ValueError(f"Webhook {webhook_id} does not exist")

        if state.status != WebhookStatus.PROCESSING:
            raise ValueError(
                f"Webhook {webhook_id} is in {state.status} state, cannot mark COMPLETE"
            )

        self._data[webhook_id] = WebhookState(
            webhook_id=state.webhook_id,
            status=WebhookStatus.COMPLETE,
            reserved_until=state.reserved_until,
            result=result,
            error=None,
            created_at=state.created_at,
            updated_at=datetime.utcnow(),
        )

    def mark_failed(self, webhook_id: str, error: str) -> None:
        state = self._data.get(webhook_id)
        if state is None:
            raise ValueError(f"Webhook {webhook_id} does not exist")

        if state.status != WebhookStatus.PROCESSING:
            raise ValueError(
                f"Webhook {webhook_id} is in {state.status} state, cannot mark FAILED"
            )

        self._data[webhook_id] = WebhookState(
            webhook_id=state.webhook_id,
            status=WebhookStatus.FAILED,
            reserved_until=state.reserved_until,
            result=None,
            error=error,
            created_at=state.created_at,
            updated_at=datetime.utcnow(),
        )
