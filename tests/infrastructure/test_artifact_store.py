"""Tests for InMemoryArtifactStore."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.infrastructure.artifacts import Artifact, InMemoryArtifactStore


def _make_artifact(artifact_id: str = "a1", size: int = 100,
                   ttl: int = 3600) -> Artifact:
    now = datetime.now(tz=timezone.utc)
    return Artifact(
        artifact_id=artifact_id,
        filename="test.txt",
        mime_type="text/plain",
        size_bytes=size,
        created_at=now,
        expires_at=now + timedelta(seconds=ttl),
    )


@pytest.mark.asyncio
async def test_register_and_lookup():
    store = InMemoryArtifactStore()
    art = _make_artifact()
    await store.register(art)
    result = await store.lookup(art.artifact_id)
    assert result.is_found is True
    assert result.artifact is not None
    assert result.artifact.artifact_id == "a1"


@pytest.mark.asyncio
async def test_register_exceeds_max_items():
    store = InMemoryArtifactStore()
    one = Artifact(artifact_id="x", filename="x.txt", mime_type="text/plain",
                   size_bytes=1, created_at=datetime.now(tz=timezone.utc),
                   expires_at=datetime.now(tz=timezone.utc) + timedelta(hours=1))
    await store.register(one)
    store._MAX_ITEMS = 1
    with pytest.raises(ValueError, match="limite de 1 itens"):
        await store.register(one)


@pytest.mark.asyncio
async def test_register_exceeds_max_total_bytes():
    store = InMemoryArtifactStore()
    store._MAX_TOTAL_BYTES = 50
    large = _make_artifact(artifact_id="big", size=100)
    with pytest.raises(ValueError, match="limite de 50 bytes"):
        await store.register(large)


@pytest.mark.asyncio
async def test_lookup_nonexistent_returns_not_found():
    store = InMemoryArtifactStore()
    result = await store.lookup("no-such-id")
    assert result.is_found is False
    assert result.artifact is None
    assert result.is_expired is False


@pytest.mark.asyncio
async def test_lookup_expired_removes_and_returns_expired():
    store = InMemoryArtifactStore()
    art = _make_artifact(ttl=-1)
    await store.register(art)
    now_future = datetime.now(tz=timezone.utc) + timedelta(hours=2)
    result = await store.lookup(art.artifact_id, now=now_future)
    assert result.is_found is False
    assert result.is_expired is True


@pytest.mark.asyncio
async def test_delete_returns_true_when_present():
    store = InMemoryArtifactStore()
    art = _make_artifact()
    await store.register(art)
    deleted = await store.delete(art.artifact_id)
    assert deleted is True
    result = await store.lookup(art.artifact_id)
    assert result.is_found is False


@pytest.mark.asyncio
async def test_delete_returns_false_when_absent():
    store = InMemoryArtifactStore()
    deleted = await store.delete("no-such-id")
    assert deleted is False


@pytest.mark.asyncio
async def test_total_bytes_decrements_on_delete():
    store = InMemoryArtifactStore()
    art = _make_artifact(size=200)
    await store.register(art)
    assert store._total_bytes == 200
    await store.delete(art.artifact_id)
    assert store._total_bytes == 0


@pytest.mark.asyncio
async def test_total_bytes_decrements_on_expired_cleanup():
    store = InMemoryArtifactStore()
    art = _make_artifact(ttl=-1)
    await store.register(art)
    now_future = datetime.now(tz=timezone.utc) + timedelta(hours=2)
    await store.lookup(art.artifact_id, now=now_future)
    assert store._total_bytes == 0


@pytest.mark.asyncio
async def test_lookup_fresh_item_not_expired():
    store = InMemoryArtifactStore()
    art = _make_artifact(ttl=3600)
    await store.register(art)
    now = datetime.now(tz=timezone.utc)
    result = await store.lookup(art.artifact_id, now=now)
    assert result.is_found is True
    assert result.is_expired is False
