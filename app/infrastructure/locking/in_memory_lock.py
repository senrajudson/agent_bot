"""In-memory distributed lock for tests."""
from __future__ import annotations

import asyncio
import time

from app.infrastructure.locking.base import DistributedLock, LockStatus


class InMemoryDistributedLock:
    """In-memory lock for tests (single-process only).

    Supports both sync and async interfaces.
    """

    def __init__(self) -> None:
        self._locks: dict[str, float] = {}
        self._mutex = asyncio.Lock()

    async def try_acquire(self, key: str, ttl_seconds: int) -> LockStatus:
        async with self._mutex:
            now = time.time()
            self._locks = {k: v for k, v in self._locks.items() if v > now}
            if key in self._locks:
                return LockStatus.ALREADY_HELD
            self._locks[key] = now + ttl_seconds
            return LockStatus.ACQUIRED

    async def release(self, key: str) -> bool:
        async with self._mutex:
            return self._locks.pop(key, None) is not None

    async def is_held(self, key: str) -> bool:
        async with self._mutex:
            now = time.time()
            return self._locks.get(key, 0) > now

    # Sync convenience methods for DedupeStore
    def try_acquire_sync(self, key: str, ttl_seconds: int) -> LockStatus:
        """Synchronous try_acquire (runs async in new loop)."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop is not None:
            # Already in async context — use thread-safe approach
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(asyncio.run, self.try_acquire(key, ttl_seconds)).result()
        return asyncio.run(self.try_acquire(key, ttl_seconds))

    def release_sync(self, key: str) -> bool:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop is not None:
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(asyncio.run, self.release(key)).result()
        return asyncio.run(self.release(key))

    def is_held_sync(self, key: str) -> bool:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop is not None:
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(asyncio.run, self.is_held(key)).result()
        return asyncio.run(self.is_held(key))
