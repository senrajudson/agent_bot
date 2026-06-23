"""Tests for DedupeStore with DistributedLock."""
from __future__ import annotations

import pytest

from app.bridge.google_chat.dedupe_store import DedupeStore
from app.bridge.google_chat.models import GoogleChatIncomingMessage
from app.infrastructure.locking.in_memory_lock import InMemoryDistributedLock


# ---------------------------------------------------------------------------
# Fake event
# ---------------------------------------------------------------------------
def _fake_event(message_name: str = "msg-123") -> GoogleChatIncomingMessage:
    return GoogleChatIncomingMessage(
        message_name=message_name,
        pubsub_message_id="ps-1",
        space_name="spaces/abc",
        message_text="hello",
        argument_text="hello",
        formatted_text="hello",
        event_type="MESSAGE",
    )


# =========================================================================
# DedupeStore initialization
# =========================================================================
class TestDedupeStoreInit:
    def test_requires_lock(self) -> None:
        with pytest.raises(ValueError, match="DistributedLock"):
            DedupeStore(lock=None)

    def test_accepts_lock(self) -> None:
        lock = InMemoryDistributedLock()
        store = DedupeStore(lock=lock)
        assert store._lock is lock


# =========================================================================
# try_start
# =========================================================================
class TestTryStart:
    def test_returns_started_for_new_message(self) -> None:
        lock = InMemoryDistributedLock()
        store = DedupeStore(lock=lock)
        event = _fake_event("msg-1")
        assert store.try_start(event) == "started"

    def test_returns_duplicate_processing_if_same_key(self) -> None:
        lock = InMemoryDistributedLock()
        store = DedupeStore(lock=lock)
        event = _fake_event("msg-1")
        store.try_start(event)
        assert store.try_start(event) == "duplicate_processing"

    def test_different_messages_are_independent(self) -> None:
        lock = InMemoryDistributedLock()
        store = DedupeStore(lock=lock)
        assert store.try_start(_fake_event("msg-1")) == "started"
        assert store.try_start(_fake_event("msg-2")) == "started"


# =========================================================================
# mark_done
# =========================================================================
class TestMarkDone:
    def test_returns_duplicate_done_after_mark_done(self) -> None:
        lock = InMemoryDistributedLock()
        store = DedupeStore(lock=lock)
        event = _fake_event("msg-1")
        store.try_start(event)
        store.mark_done(event)
        assert store.try_start(event) == "duplicate_done"

    def test_mark_done_releases_processing(self) -> None:
        lock = InMemoryDistributedLock()
        store = DedupeStore(lock=lock)
        event = _fake_event("msg-1")
        store.try_start(event)
        store.mark_done(event)
        # Processing should be released
        processing_key = "google_chat:dedupe_lock:google_chat:dedupe:processing:msg-1"
        assert not lock.is_held_sync(processing_key)


# =========================================================================
# release_processing
# =========================================================================
class TestReleaseProcessing:
    def test_allows_reacquire_after_release(self) -> None:
        lock = InMemoryDistributedLock()
        store = DedupeStore(lock=lock)
        event = _fake_event("msg-1")
        store.try_start(event)
        store.release_processing(event)
        assert store.try_start(event) == "started"


# =========================================================================
# Multi-worker simulation
# =========================================================================
class TestMultiWorker:
    def test_two_stores_with_same_lock_dedup(self) -> None:
        shared_lock = InMemoryDistributedLock()
        store1 = DedupeStore(lock=shared_lock)
        store2 = DedupeStore(lock=shared_lock)
        event = _fake_event("msg-1")
        assert store1.try_start(event) == "started"
        assert store2.try_start(event) == "duplicate_processing"

    def test_different_messages_not_deduped(self) -> None:
        shared_lock = InMemoryDistributedLock()
        store1 = DedupeStore(lock=shared_lock)
        store2 = DedupeStore(lock=shared_lock)
        assert store1.try_start(_fake_event("msg-1")) == "started"
        assert store2.try_start(_fake_event("msg-2")) == "started"
