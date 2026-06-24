"""Regression tests for DedupeStore with RedisDistributedLock.

Verifies that the bridge correctly handles Redis-backed deduplication
through the async path (the sync fallback was removed to fix
TypeError: object int can't be used in 'await' expression).
"""
from __future__ import annotations

import pytest
from fakeredis.aioredis import FakeRedis

from app.bridge.google_chat.dedupe_store import DedupeStore
from app.bridge.google_chat.models import GoogleChatIncomingMessage
from app.infrastructure.locking.redis_lock import RedisDistributedLock


def _fake_event(message_name: str = "msg-456") -> GoogleChatIncomingMessage:
    return GoogleChatIncomingMessage(
        message_name=message_name,
        pubsub_message_id="ps-456",
        space_name="spaces/xyz",
        message_text="oi",
        argument_text="oi",
        formatted_text="oi",
        event_type="MESSAGE",
    )


@pytest.mark.asyncio
async def test_try_start_returns_started_for_new_message() -> None:
    r = FakeRedis(decode_responses=True)
    lock = RedisDistributedLock(r, prefix="test")
    store = DedupeStore(lock=lock)
    event = _fake_event("msg-async-1")
    result = await store.try_start(event)
    assert result == "started"


@pytest.mark.asyncio
async def test_try_start_returns_duplicate_processing_for_same_message() -> None:
    r = FakeRedis(decode_responses=True)
    lock = RedisDistributedLock(r, prefix="test")
    store = DedupeStore(lock=lock)
    event = _fake_event("msg-async-2")
    assert await store.try_start(event) == "started"
    assert await store.try_start(event) == "duplicate_processing"


@pytest.mark.asyncio
async def test_mark_done_allows_reacquire() -> None:
    r = FakeRedis(decode_responses=True)
    lock = RedisDistributedLock(r, prefix="test")
    store = DedupeStore(lock=lock)
    event = _fake_event("msg-async-3")
    assert await store.try_start(event) == "started"
    await store.mark_done(event)
    assert await store.try_start(event) == "duplicate_done"


@pytest.mark.asyncio
async def test_release_processing_allows_reacquire() -> None:
    r = FakeRedis(decode_responses=True)
    lock = RedisDistributedLock(r, prefix="test")
    store = DedupeStore(lock=lock)
    event = _fake_event("msg-async-4")
    assert await store.try_start(event) == "started"
    await store.release_processing(event)
    assert await store.try_start(event) == "started"


@pytest.mark.asyncio
async def test_different_messages_not_deduped() -> None:
    r = FakeRedis(decode_responses=True)
    lock = RedisDistributedLock(r, prefix="test")
    store = DedupeStore(lock=lock)
    assert await store.try_start(_fake_event("msg-a")) == "started"
    assert await store.try_start(_fake_event("msg-b")) == "started"


@pytest.mark.asyncio
async def test_full_cycle_start_mark_done_duplicate_done() -> None:
    """Full bridge cycle: start → process → mark_done → duplicate_done."""
    r = FakeRedis(decode_responses=True)
    lock = RedisDistributedLock(r, prefix="test")
    store = DedupeStore(lock=lock)
    event = _fake_event("msg-full-1")

    # Worker receives message
    assert await store.try_start(event) == "started"

    # Worker processes and marks done
    await store.mark_done(event)

    # Same message arrives again → duplicate_done
    assert await store.try_start(event) == "duplicate_done"


@pytest.mark.asyncio
async def test_two_stores_with_same_lock_dedup() -> None:
    """Simulates two workers sharing the same Redis."""
    r = FakeRedis(decode_responses=True)
    lock = RedisDistributedLock(r, prefix="test")
    store1 = DedupeStore(lock=lock)
    store2 = DedupeStore(lock=lock)
    event = _fake_event("msg-concurrent-1")
    assert await store1.try_start(event) == "started"
    assert await store2.try_start(event) == "duplicate_processing"


@pytest.mark.asyncio
async def test_concurrent_workers_different_messages() -> None:
    """Two workers processing different messages should not interfere."""
    r = FakeRedis(decode_responses=True)
    lock = RedisDistributedLock(r, prefix="test")
    store1 = DedupeStore(lock=lock)
    store2 = DedupeStore(lock=lock)
    assert await store1.try_start(_fake_event("msg-x")) == "started"
    assert await store2.try_start(_fake_event("msg-y")) == "started"
    await store1.mark_done(_fake_event("msg-x"))
    # msg-y processing lock is still held (store2 hasn't released it)
    assert await store2.try_start(_fake_event("msg-y")) == "duplicate_processing"
    # Release and reacquire msg-y
    await store2.release_processing(_fake_event("msg-y"))
    assert await store2.try_start(_fake_event("msg-y")) == "started"
