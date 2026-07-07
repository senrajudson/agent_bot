"""Tests for ChatMemoryService idempotency (T2)."""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from fakeredis.aioredis import FakeRedis
from redis.exceptions import RedisError

from app.domain.value_objects import ConversationId
from app.services.chat_memory_service import (
    MEMORY_KEY_PREFIX,
    append_memory_turns,
    settings,
)


def _memory_key(cid: str) -> str:
    conv = ConversationId.from_user_id(cid)
    return f"{MEMORY_KEY_PREFIX}:{conv}:turns"


def _dedupe_key(cid: str, event_id: str) -> str:
    conv = ConversationId.from_user_id(cid)
    return f"{MEMORY_KEY_PREFIX}:{conv}:dedupe:{event_id}"


CONV_ID = "user-1"
EVT_1 = "evt-001"
EVT_2 = "evt-002"


@pytest.fixture
def fake_redis() -> FakeRedis:
    return FakeRedis(decode_responses=True)


@pytest.fixture
def mock_redis(fake_redis: FakeRedis) -> FakeRedis:
    with patch(
        "app.services.chat_memory_service.get_redis_client",
        return_value=fake_redis,
    ):
        yield fake_redis


# ---------------------------------------------------------------------------
# CA1: mesma idempotency_key não duplica turn
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_duplicate_same_key_does_not_rpush(mock_redis: FakeRedis) -> None:
    await append_memory_turns(CONV_ID, "msg1", "r1", idempotency_key=EVT_1)
    await append_memory_turns(CONV_ID, "msg2", "r2", idempotency_key=EVT_1)
    key = _memory_key(CONV_ID)
    count = await mock_redis.llen(key)
    assert count == 2


# ---------------------------------------------------------------------------
# CA2: event_id diferente salva novo turn
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_different_key_appends_new_turns(mock_redis: FakeRedis) -> None:
    await append_memory_turns(CONV_ID, "msg1", "r1", idempotency_key=EVT_1)
    await append_memory_turns(CONV_ID, "msg2", "r2", idempotency_key=EVT_2)
    key = _memory_key(CONV_ID)
    count = await mock_redis.llen(key)
    assert count == 4


# ---------------------------------------------------------------------------
# CA3: sem idempotency_key mantém comportamento legado
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_key_legacy_behavior(mock_redis: FakeRedis) -> None:
    await append_memory_turns(CONV_ID, "msg1", "r1")
    await append_memory_turns(CONV_ID, "msg2", "r2")
    key = _memory_key(CONV_ID)
    count = await mock_redis.llen(key)
    assert count == 4


# ---------------------------------------------------------------------------
# CA4: dedupe key recebe TTL
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dedupe_key_ttl(mock_redis: FakeRedis) -> None:
    await append_memory_turns(CONV_ID, "msg", "r", idempotency_key=EVT_1)
    dk = _dedupe_key(CONV_ID, EVT_1)
    ttl = await mock_redis.ttl(dk)
    assert ttl > 0
    assert ttl <= settings.CHAT_MEMORY_TTL_SECONDS


# ---------------------------------------------------------------------------
# CA5: memory key continua recebendo TTL
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_memory_key_ttl(mock_redis: FakeRedis) -> None:
    await append_memory_turns(CONV_ID, "msg", "r", idempotency_key=EVT_1)
    mk = _memory_key(CONV_ID)
    ttl = await mock_redis.ttl(mk)
    assert ttl > 0
    assert ttl <= settings.CHAT_MEMORY_TTL_SECONDS


# ---------------------------------------------------------------------------
# CA6: formato do item salvo não muda (sem event_id, sem idempotency_key)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_item_format_unchanged(mock_redis: FakeRedis) -> None:
    await append_memory_turns(CONV_ID, "hello", "world", idempotency_key=EVT_1)
    key = _memory_key(CONV_ID)
    raw = await mock_redis.lrange(key, 0, 0)
    assert len(raw) == 1
    item = json.loads(raw[0])
    assert item["role"] == "user"
    assert item["content"] == "hello"
    assert "event_id" not in item
    assert "idempotency_key" not in item


# ---------------------------------------------------------------------------
# CA7: erro Redis/Lua propaga
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_redis_error_propagates(fake_redis: FakeRedis) -> None:
    with patch(
        "app.services.chat_memory_service.get_redis_client",
        return_value=fake_redis,
    ):
        with patch.object(
            fake_redis, "eval", side_effect=RedisError("simulated redis failure")
        ):
            with pytest.raises(RedisError, match="simulated redis failure"):
                await append_memory_turns(
                    CONV_ID, "msg", "r", idempotency_key=EVT_1
                )


# ---------------------------------------------------------------------------
# CA8: duplicate retorna sucesso/no-op
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_duplicate_returns_noop(mock_redis: FakeRedis) -> None:
    await append_memory_turns(CONV_ID, "msg1", "r1", idempotency_key=EVT_1)
    # Segunda chamada com mesmo event_id não deve lançar exceção
    await append_memory_turns(CONV_ID, "msg2", "r2", idempotency_key=EVT_1)
    key = _memory_key(CONV_ID)
    items = await mock_redis.lrange(key, 0, -1)
    assert len(items) == 2


# ---------------------------------------------------------------------------
# Extra: idempotency_key vazio deve levantar ValueError
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_idempotency_key_raises(mock_redis: FakeRedis) -> None:
    with pytest.raises(ValueError, match="idempotency_key must not be empty"):
        await append_memory_turns(CONV_ID, "msg", "r", idempotency_key="")


# ---------------------------------------------------------------------------
# Extra: idempotency_key com metadata preserva campos
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_idempotency_preserves_metadata(mock_redis: FakeRedis) -> None:
    meta = {"source": "test", "user_id": CONV_ID}
    await append_memory_turns(
        CONV_ID, "msg", "r", metadata=meta, idempotency_key=EVT_1
    )
    key = _memory_key(CONV_ID)
    raw = await mock_redis.lrange(key, 0, -1)
    assert len(raw) == 2
    for item_raw in raw:
        item = json.loads(item_raw)
        assert item["metadata"]["source"] == "test"
        assert item["metadata"]["user_id"] == CONV_ID
