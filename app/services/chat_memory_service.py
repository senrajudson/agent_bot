import json
import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Any

from pydantic import BaseModel, Field

from app.clients.redis_client import get_redis_client
from app.core.config import settings
from app.domain.value_objects import ConversationId

logger = logging.getLogger(__name__)

DEFAULT_TIMEZONE = "America/Sao_Paulo"
MEMORY_KEY_PREFIX = "pi_chat:memory"

# Lua script for atomic check-and-append with dedupe.
# KEYS[1] = dedupe_key
# KEYS[2] = memory_list_key
# ARGV[1] = dedupe_ttl_seconds
# ARGV[2] = memory_ttl_seconds
# ARGV[3] = max_memory_items
# ARGV[4] = user_turn_json
# ARGV[5] = assistant_turn_json
_LUA_CHECK_AND_APPEND = """
if redis.call('EXISTS', KEYS[1]) == 1 then
    return 'duplicate'
end
redis.call('RPUSH', KEYS[2], ARGV[4], ARGV[5])
redis.call('LTRIM', KEYS[2], -tonumber(ARGV[3]), -1)
redis.call('EXPIRE', KEYS[2], tonumber(ARGV[2]))
redis.call('SET', KEYS[1], '1', 'EX', tonumber(ARGV[1]))
return 'appended'
"""


class ChatMemoryTurn(BaseModel):
    role: str = Field(description="user ou assistant")
    content: str = Field(description="Conteúdo textual da mensagem")
    created_at: str = Field(description="Data/hora ISO do registro")
    metadata: dict[str, Any] = Field(default_factory=dict)


def _memory_key(conversation_id: ConversationId) -> str:
    return f"{settings.REDIS_KEY_PREFIX}:{conversation_id}:turns"


def _dedupe_key(conversation_id: ConversationId, event_id: str) -> str:
    return f"{settings.REDIS_KEY_PREFIX}:{conversation_id}:dedupe:{event_id}"


def _now_iso() -> str:
    return datetime.now(ZoneInfo(DEFAULT_TIMEZONE)).isoformat(timespec="seconds")


async def load_memory_turns(
    conversation_id: str | None,
    max_turns: int | None = None,
) -> list[ChatMemoryTurn]:
    if not conversation_id:
        return []

    redis = get_redis_client()
    cid = ConversationId.from_user_id(conversation_id)
    key = _memory_key(cid)
    limit = max_turns or settings.CHAT_MEMORY_MAX_TURNS

    raw_items = await redis.lrange(key, -limit, -1)

    turns: list[ChatMemoryTurn] = []

    for item in raw_items:
        try:
            turns.append(ChatMemoryTurn.model_validate_json(item))
        except Exception:
            continue

    return turns


async def append_memory_turns(
    conversation_id: str | None,
    user_message: str,
    assistant_message: str,
    metadata: dict[str, Any] | None = None,
    *,
    idempotency_key: str | None = None,
) -> None:
    if not conversation_id:
        return

    redis = get_redis_client()
    cid = ConversationId.from_user_id(conversation_id)

    metadata = metadata or {}

    user_turn = ChatMemoryTurn(
        role="user",
        content=user_message,
        created_at=_now_iso(),
        metadata=metadata,
    )

    assistant_turn = ChatMemoryTurn(
        role="assistant",
        content=assistant_message,
        created_at=_now_iso(),
        metadata=metadata,
    )

    user_turn_json = user_turn.model_dump_json()
    assistant_turn_json = assistant_turn.model_dump_json()
    ttl = settings.CHAT_MEMORY_TTL_SECONDS
    max_items = settings.CHAT_MEMORY_MAX_TURNS * 2

    memory_key = _memory_key(cid)

    if idempotency_key is not None:
        if not idempotency_key:
            raise ValueError("idempotency_key must not be empty when provided")
        dedupe_key = _dedupe_key(cid, idempotency_key)

        result = await redis.eval(
            _LUA_CHECK_AND_APPEND, 2,
            dedupe_key, memory_key,
            ttl, ttl, max_items,
            user_turn_json, assistant_turn_json,
        )

        if result == b'duplicate' or result == 'duplicate':
            logger.debug(
                "memoria_appender_skip idempotency_key=%s conversation_id=%s",
                idempotency_key[:16] if len(idempotency_key) > 16 else idempotency_key,
                cid,
            )
            return
        if result != b'appended' and result != 'appended':
            raise RuntimeError(
                f"Unexpected Lua script result: {result!r}"
            )
        return

    pipe = redis.pipeline()

    pipe.rpush(
        memory_key,
        user_turn_json,
        assistant_turn_json,
    )

    pipe.ltrim(memory_key, -max_items, -1)
    pipe.expire(memory_key, ttl)

    await pipe.execute()


def format_memory_for_prompt(turns: list[ChatMemoryTurn]) -> str:
    if not turns:
        return ""

    lines = ["Contexto recente da conversa:"]

    lines.append(f"""\n[Leia as conversas abaixo e lembre-se dos dados
                 \ne tags citados para conseguir responder a 
                 \na pergunta do usuário]\n""")

    for turn in turns:
        role_label = "> Usuário" if turn.role == "user" else "> Assistente"
        content = turn.content.strip()

        if not content:
            continue

        lines.append(f"{role_label}: {content}")

    lines.append(f"\n[Última mensagem do usuário baixo]")

    return "\n".join(lines).strip()