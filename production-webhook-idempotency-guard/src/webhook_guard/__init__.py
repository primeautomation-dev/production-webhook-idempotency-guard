"""
Production-safe webhook idempotency guard.

Public API surface for the webhook_guard package.
Internal modules should not be imported directly by consumers.
"""

from .guard import WebhookGuard
from .store import WebhookStore, WebhookStatus, WebhookState
from .lock import DistributedLock
from .models import ProcessingResult

__all__ = [
    "WebhookGuard",
    "WebhookStore",
    "WebhookStatus",
    "WebhookState",
    "DistributedLock",
    "ProcessingResult",
]

__version__ = "0.1.0"
