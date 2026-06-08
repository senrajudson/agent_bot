import json
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Any

from pydantic import BaseModel, Field

from app.clients.redis_client import get_redis_client
from app.core.config import settings


DEFAULT_TIMEZONE = "America/Sao_Paulo"
MEMORY_KEY_PREFIX = "pi_chat:memory"


class ChatMemoryTurn(BaseModel):
    role: str = Field(description="user ou assistant")
    content: str = Field(description="Conteúdo textual da mensagem")
    created_at: str = Field(description="Data/hora ISO do registro")
    metadata: dict[str, Any] = Field(default_factory=dict)


def _memory_key(conversation_id: str) -> str:
    return f"{MEMORY_KEY_PREFIX}:{conversation_id}:turns"


def _now_iso() -> str:
    return datetime.now(ZoneInfo(DEFAULT_TIMEZONE)).isoformat(timespec="seconds")


async def load_memory_turns(
    conversation_id: str | None,
    max_turns: int | None = None,
) -> list[ChatMemoryTurn]:
    if not conversation_id:
        return []

    redis = get_redis_client()
    key = _memory_key(conversation_id)
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
) -> None:
    if not conversation_id:
        return

    redis = get_redis_client()
    key = _memory_key(conversation_id)

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

    max_items = settings.CHAT_MEMORY_MAX_TURNS * 2

    pipe = redis.pipeline()

    pipe.rpush(
        key,
        user_turn.model_dump_json(),
        assistant_turn.model_dump_json(),
    )

    pipe.ltrim(key, -max_items, -1)
    pipe.expire(key, settings.CHAT_MEMORY_TTL_SECONDS)

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