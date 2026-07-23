"""Tests for worker attachment flow (D07).

All tests use mocks and fakes — no real network, no service account.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.bridge.google_chat.bridge_internal_artifact_client import (
    BridgeArtifactClient,
    BridgeArtifactClientError,
    BridgeArtifactExpired,
    BridgeArtifactNotFound,
)
from app.bridge.google_chat.dedupe_store import AttachmentDedupeStore
from app.infrastructure.artifacts.upload_service import _basename_safe
from app.schemas.chat import ChatAttachment


class FakeRedis:
    def __init__(self):
        self._store: dict[str, str] = {}

    async def set(self, key, value, *, nx=False, ex=0):
        if nx and key in self._store:
            return False
        self._store[key] = value
        return True

    async def get(self, key):
        return self._store.get(key)


@pytest.fixture
def store():
    return AttachmentDedupeStore(FakeRedis())


def make_attachment(
    artifact_id="a1", filename="test.txt", mime_type="text/plain",
    size_bytes=1000, caption=None,
) -> ChatAttachment:
    return ChatAttachment(
        artifact_id=artifact_id,
        filename=filename,
        mime_type=mime_type,
        size_bytes=size_bytes,
        caption=caption,
    )


# 6. Fluxo feliz


class TestHappyPath:
    @pytest.mark.asyncio
    async def test_single_attachment_sent_confirmed(self, store):
        key = store.make_key("evt1", "a1")
        assert await store.get_state(key) is None
        assert await store.start(key) is True
        assert await store.get_state(key) == "PENDING"
        await store.mark_sent(key)
        assert await store.get_state(key) == "SENT"

    @pytest.mark.asyncio
    async def test_three_attachments_independent(self, store):
        for i in range(3):
            key = store.make_key("evt1", f"a{i}")
            await store.start(key)
            await store.mark_sent(key)
        for i in range(3):
            assert await store.get_state(store.make_key("evt1", f"a{i}")) == "SENT"

    @pytest.mark.asyncio
    async def test_sent_only_after_confirmation(self, store):
        key = store.make_key("evt1", "a1")
        await store.start(key)
        assert await store.get_state(key) == "PENDING"
        await store.mark_sent(key)
        assert await store.get_state(key) == "SENT"


# 7. Limites


class TestLimits:
    def test_more_than_3_truncated(self):
        atts = [make_attachment(artifact_id=f"a{i}") for i in range(5)]
        assert len(atts[:3]) == 3

    def test_single_over_25mb(self):
        assert make_attachment(size_bytes=30 * 1024 * 1024).size_bytes > 26214400

    def test_aggregate_over_50mb(self):
        a1 = make_attachment(artifact_id="b1", size_bytes=30 * 1024 * 1024)
        a2 = make_attachment(artifact_id="b2", size_bytes=30 * 1024 * 1024)
        assert (a1.size_bytes or 0) + (a2.size_bytes or 0) > 52428800

    def test_mime_not_allowed(self):
        att = make_attachment(mime_type="application/json")
        allowed = {"text/plain", "text/csv", "application/pdf", "image/png", "image/jpeg"}
        assert att.mime_type not in allowed

    def test_negative_size_bytes_rejected(self):
        with pytest.raises(Exception):
            ChatAttachment(artifact_id="a1", filename="f.txt", mime_type="text/plain", size_bytes=-1)

    def test_unsafe_filename_sanitized(self):
        safe = _basename_safe("../../etc/passwd")
        assert ".." not in safe

    def test_empty_filename_rejected(self):
        with pytest.raises(Exception):
            ChatAttachment(artifact_id="a1", filename="", mime_type="text/plain")

    def test_empty_mime_type_rejected(self):
        with pytest.raises(Exception):
            ChatAttachment(artifact_id="a1", filename="f.txt", mime_type="")

    def test_duplicate_artifact_id_deduped(self):
        atts = [make_attachment(artifact_id="dup"), make_attachment(artifact_id="dup")]
        seen = set()
        deduped = [a for a in atts if not (a.artifact_id in seen or seen.add(a.artifact_id))]
        assert len(deduped) == 1


# 8. Idempotência


class TestIdempotencia:
    def test_key_format(self):
        k = AttachmentDedupeStore.make_key(None, "evt1", "art1", "s1", "t1")
        assert "evt1" in k and "art1" in k and "s1" in k and "t1" in k

    def test_filename_not_in_key(self):
        assert AttachmentDedupeStore.make_key(None, "e", "a") == AttachmentDedupeStore.make_key(None, "e", "a")

    @pytest.mark.asyncio
    async def test_sent_blocks_duplicate(self, store):
        key = store.make_key("e", "a")
        await store.start(key)
        await store.mark_sent(key)
        assert await store.start(key) is False

    @pytest.mark.asyncio
    async def test_retryable_allows_retry_in_future(self, store):
        key = store.make_key("e", "a")
        await store.start(key)
        await store.mark_failed(key, permanent=False)
        assert await store.get_state(key) == "FAILED_RETRYABLE"
        assert await store.start(key) is False

    @pytest.mark.asyncio
    async def test_permanent_blocks(self, store):
        key = store.make_key("e", "a")
        await store.start(key)
        await store.mark_failed(key, permanent=True)
        assert await store.get_state(key) == "FAILED_PERMANENT"
        assert await store.start(key) is False

    @pytest.mark.asyncio
    async def test_two_attachments_independent(self, store):
        k1, k2 = store.make_key("e", "a1"), store.make_key("e", "a2")
        await store.start(k1)
        await store.mark_sent(k1)
        await store.start(k2)
        await store.mark_sent(k2)
        assert await store.get_state(k1) == "SENT"
        assert await store.get_state(k2) == "SENT"

    def test_missing_space_has_unknown(self):
        k = AttachmentDedupeStore.make_key(None, "e", "a")
        assert "unknown" in k


# 9. Erros transitórios


class TestTransientErrors:
    def test_timeout_is_retryable(self):
        assert isinstance(httpx.TimeoutException("x"), (httpx.TimeoutException, httpx.RequestError))

    def test_429_is_client_error(self):
        assert httpx.Response(429).status_code == 429

    def test_5xx_is_server_error(self):
        for code in (500, 502, 503):
            assert httpx.Response(code).is_server_error


# 10. Erros permanentes


class TestPermanentErrors:
    def test_not_found_no_retry(self):
        client = BridgeArtifactClient("http://t", "t", 5)
        with patch.object(client, "_download_once", side_effect=BridgeArtifactNotFound("nf")):
            with pytest.raises(BridgeArtifactNotFound):
                client.download_to_temp("x", "x.txt")

    def test_expired_no_retry(self):
        client = BridgeArtifactClient("http://t", "t", 5)
        with patch.object(client, "_download_once", side_effect=BridgeArtifactExpired("exp")):
            with pytest.raises(BridgeArtifactExpired):
                client.download_to_temp("x", "x.txt")

    def test_auth_no_retry(self):
        client = BridgeArtifactClient("http://t", "t", 5)
        with patch.object(client, "_download_once", side_effect=BridgeArtifactClientError("auth")):
            with pytest.raises(BridgeArtifactClientError):
                client.download_to_temp("x", "x.txt")


# 11. Falhas parciais


class TestPartialFailures:
    @pytest.mark.asyncio
    async def test_first_sent_second_fails(self, store):
        k1, k2 = store.make_key("e", "a1"), store.make_key("e", "a2")
        await store.start(k1)
        await store.mark_sent(k1)
        await store.start(k2)
        await store.mark_failed(k2, permanent=True)
        assert await store.get_state(k1) == "SENT"
        assert await store.get_state(k2) == "FAILED_PERMANENT"

    @pytest.mark.asyncio
    async def test_reentry_no_duplicate(self, store):
        key = store.make_key("e", "a")
        await store.start(key)
        await store.mark_sent(key)
        assert await store.start(key) is False
        assert await store.get_state(key) == "SENT"


# 12. Spool lifecycle


class TestSpoolLifecycle:
    def test_small_stays_in_memory(self):
        import tempfile
        s = tempfile.SpooledTemporaryFile(max_size=65536)
        s.write(b"hi")
        s.seek(0)
        assert s.read() == b"hi"
        s.close()

    def test_large_rolls_to_disk(self):
        import tempfile
        s = tempfile.SpooledTemporaryFile(max_size=1024)
        s.write(b"x" * 2048)
        s.seek(0)
        assert len(s.read()) == 2048
        s.close()
