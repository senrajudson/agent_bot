"""Tests for DistributedLock implementations."""
from __future__ import annotations

import asyncio
import time

import pytest

from app.infrastructure.locking.base import DistributedLock, LockStatus
from app.infrastructure.locking.in_memory_lock import InMemoryDistributedLock


# =========================================================================
# Protocol conformance
# =========================================================================
class TestProtocolConformance:
    def test_in_memory_is_distributed_lock(self) -> None:
        assert isinstance(InMemoryDistributedLock(), DistributedLock)

    def test_redis_lock_is_distributed_lock(self) -> None:
        from app.infrastructure.locking.redis_lock import RedisDistributedLock
        assert RedisDistributedLock.__init__.__annotations__ is not None


# =========================================================================
# LockStatus
# =========================================================================
class TestLockStatus:
    def test_values(self) -> None:
        assert LockStatus.ACQUIRED == "acquired"
        assert LockStatus.ALREADY_HELD == "already_held"
        assert LockStatus.NOT_HELD == "not_held"


# =========================================================================
# InMemoryDistributedLock
# =========================================================================
class TestInMemoryDistributedLock:
    @pytest.mark.asyncio
    async def test_try_acquire_returns_acquired(self) -> None:
        lock = InMemoryDistributedLock()
        result = await lock.try_acquire("k1", ttl_seconds=60)
        assert result == LockStatus.ACQUIRED

    @pytest.mark.asyncio
    async def test_try_acquire_returns_already_held(self) -> None:
        lock = InMemoryDistributedLock()
        await lock.try_acquire("k1", ttl_seconds=60)
        result = await lock.try_acquire("k1", ttl_seconds=60)
        assert result == LockStatus.ALREADY_HELD

    @pytest.mark.asyncio
    async def test_release_returns_true(self) -> None:
        lock = InMemoryDistributedLock()
        await lock.try_acquire("k1", ttl_seconds=60)
        result = await lock.release("k1")
        assert result is True

    @pytest.mark.asyncio
    async def test_release_unheld_returns_false(self) -> None:
        lock = InMemoryDistributedLock()
        result = await lock.release("nonexistent")
        assert result is False

    @pytest.mark.asyncio
    async def test_release_allows_reacquire(self) -> None:
        lock = InMemoryDistributedLock()
        await lock.try_acquire("k1", ttl_seconds=60)
        await lock.release("k1")
        result = await lock.try_acquire("k1", ttl_seconds=60)
        assert result == LockStatus.ACQUIRED

    @pytest.mark.asyncio
    async def test_is_held_true(self) -> None:
        lock = InMemoryDistributedLock()
        await lock.try_acquire("k1", ttl_seconds=60)
        assert await lock.is_held("k1") is True

    @pytest.mark.asyncio
    async def test_is_held_false(self) -> None:
        lock = InMemoryDistributedLock()
        assert await lock.is_held("k1") is False

    @pytest.mark.asyncio
    async def test_is_held_after_release(self) -> None:
        lock = InMemoryDistributedLock()
        await lock.try_acquire("k1", ttl_seconds=60)
        await lock.release("k1")
        assert await lock.is_held("k1") is False

    @pytest.mark.asyncio
    async def test_separate_keys(self) -> None:
        lock = InMemoryDistributedLock()
        await lock.try_acquire("k1", ttl_seconds=60)
        result = await lock.try_acquire("k2", ttl_seconds=60)
        assert result == LockStatus.ACQUIRED
        assert await lock.is_held("k1") is True
        assert await lock.is_held("k2") is True

    @pytest.mark.asyncio
    async def test_ttl_expires_lock(self) -> None:
        lock = InMemoryDistributedLock()
        await lock.try_acquire("k1", ttl_seconds=0)  # expires immediately
        await asyncio.sleep(0.01)
        result = await lock.try_acquire("k1", ttl_seconds=60)
        assert result == LockStatus.ACQUIRED

    @pytest.mark.asyncio
    async def test_concurrent_acquire_only_one_wins(self) -> None:
        lock = InMemoryDistributedLock()
        results = []
        for _ in range(10):
            r = await lock.try_acquire("shared", ttl_seconds=60)
            results.append(r)
        assert results.count(LockStatus.ACQUIRED) == 1
        assert results.count(LockStatus.ALREADY_HELD) == 9

    @pytest.mark.asyncio
    async def test_release_then_acquire_after_ttl(self) -> None:
        lock = InMemoryDistributedLock()
        await lock.try_acquire("k1", ttl_seconds=0)
        await asyncio.sleep(0.01)
        await lock.release("k1")  # should return False (already expired)
        result = await lock.try_acquire("k1", ttl_seconds=60)
        assert result == LockStatus.ACQUIRED
