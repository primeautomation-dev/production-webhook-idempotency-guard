from typing import Optional, Protocol


class LockHandle(Protocol):
    """Handle representing an acquired distributed lock."""

    def release(self) -> None:
        """Release the lock."""
        ...


class DistributedLock(Protocol):
    """
    Distributed lock interface.

    Implementations must guarantee:
    - Non-blocking acquisition (no waiting forever)
    - Lock scope is per-key (webhook_id)
    - Auto-release on process crash or connection loss
    """

    def try_lock(self, key: str, timeout_seconds: int) -> Optional[LockHandle]:
        """
        Attempt to acquire a lock for the given key.

        Returns:
            LockHandle if acquired successfully
            None if lock is already held by another process

        Must NOT block indefinitely.
        """
        ...
