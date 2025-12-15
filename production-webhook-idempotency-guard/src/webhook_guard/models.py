from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional


class WebhookStatus(str, Enum):
    """
    Webhook processing states.

    State transitions:
        PENDING -> PROCESSING -> COMPLETE | FAILED
    """

    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"


@dataclass(frozen=True)
class WebhookState:
    """
    Immutable snapshot of webhook state.

    Used for:
    - Retry fast-path
    - Concurrency checks
    - Crash recovery decisions
    """

    webhook_id: str
    status: WebhookStatus
    reserved_until: Optional[Any]
    result: Optional[Any]
    error: Optional[str]
    created_at: Any
    updated_at: Any


@dataclass(frozen=True)
class ProcessingResult:
    """
    Result returned from WebhookGuard.process().

    cached=True indicates the result was returned from a previous execution
    (retry or concurrent request).
    """

    success: bool
    output: Optional[Any]
    error: Optional[str]
    duration_ms: int
    cached: bool
