"""Distributed Lock Protocol — cross-process synchronization."""
from __future__ import annotations

from enum import Enum
from typing import Protocol, runtime_checkable


class LockStatus(str, Enum):
    ACQUIRED = "acquired"
    ALREADY_HELD = "already_held"
    NOT_HELD = "not_held"


@runtime_checkable
class DistributedLock(Protocol):
    """Protocol for cross-process locks using Redis SET NX EX."""

    async def try_acquire(self, key: str, ttl_seconds: int) -> LockStatus:
        """Try to acquire a lock with TTL. Returns ACQUIRED or ALREADY_HELD."""
        ...

    async def release(self, key: str) -> bool:
        """Release a lock. Returns True if released, False if not held."""
        ...

    async def is_held(self, key: str) -> bool:
        """Check if a lock is currently held."""
        ...
