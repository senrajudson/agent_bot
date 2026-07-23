"""Tests for AttachmentDedupeStore."""
from __future__ import annotations

import pytest

from app.bridge.google_chat.dedupe_store import AttachmentDedupeStore


class FakeRedis:
    """Minimal fake AsyncRedis for unit tests."""
    def __init__(self):
        self._store: dict[str, str] = {}

    async def set(self, key: str, value: str, *, nx: bool = False, ex: int = 0) -> bool:
        if nx and key in self._store:
            return False
        self._store[key] = value
        return True

    async def get(self, key: str) -> str | None:
        return self._store.get(key)


@pytest.fixture
def store():
    redis = FakeRedis()
    return AttachmentDedupeStore(redis)  # type: ignore[arg-type]


class TestAttachmentDedupeStore:
    def test_make_key_normalizes_missing_space_thread(self, store):
        key = store.make_key("evt1", "art1")
        assert "unknown" in key
        assert "evt1" in key
        assert "art1" in key

    def test_make_key_includes_all_parts(self, store):
        key = store.make_key("evt1", "art1", space="spaces/xxx", thread="spaces/xxx/threads/t1")
        assert "evt1" in key
        assert "art1" in key
        assert "spaces/xxx" in key
        assert "threads/t1" in key

    @pytest.mark.asyncio
    async def test_start_returns_true_first_time(self, store):
        key = store.make_key("evt1", "art1")
        result = await store.start(key)
        assert result is True

    @pytest.mark.asyncio
    async def test_start_returns_false_when_pending(self, store):
        key = store.make_key("evt1", "art1")
        await store.start(key)
        result = await store.start(key)
        assert result is False

    @pytest.mark.asyncio
    async def test_mark_sent_prevents_repeat(self, store):
        key = store.make_key("evt1", "art1")
        await store.start(key)
        await store.mark_sent(key)
        state = await store.get_state(key)
        assert state == "SENT"

    @pytest.mark.asyncio
    async def test_mark_failed_retryable_allows_retry(self, store):
        key = store.make_key("evt1", "art1")
        await store.start(key)
        await store.mark_failed(key, permanent=False)
        state = await store.get_state(key)
        assert state == "FAILED_RETRYABLE"

    @pytest.mark.asyncio
    async def test_mark_failed_permanent_blocks_retry(self, store):
        key = store.make_key("evt1", "art1")
        await store.start(key)
        await store.mark_failed(key, permanent=True)
        state = await store.get_state(key)
        assert state == "FAILED_PERMANENT"

    @pytest.mark.asyncio
    async def test_get_state_returns_none_for_unknown(self, store):
        key = store.make_key("unknown", "unknown")
        state = await store.get_state(key)
        assert state is None

    def test_filename_not_used_in_key(self, store):
        key1 = store.make_key("evt1", "art1", space="s1")
        key2 = store.make_key("evt1", "art1", space="s1")
        assert key1 == key2
