"""Query: Get conversation memory turns."""
from __future__ import annotations

from dataclasses import dataclass, field

from app.application.queries.base import Query
from app.domain.protocols import ConversationMemory, ConversationTurnLike


@dataclass(frozen=True)
class GetConversationMemory(Query):
    """Request conversation memory for a given conversation_id."""

    conversation_id: str
    max_turns: int | None = None


@dataclass(frozen=True)
class GetConversationMemoryResult:
    """Result of memory retrieval."""

    turns: list[ConversationTurnLike] = field(default_factory=list)
    context: str = ""


class GetConversationMemoryHandler:
    """Loads conversation memory from Redis-backed storage.

    Delegates to a ConversationMemory (injected via constructor).
    No direct dependency on Redis or json.
    """

    def __init__(self, memory: ConversationMemory) -> None:
        self._memory = memory

    async def handle(
        self, query: GetConversationMemory
    ) -> GetConversationMemoryResult:
        turns = await self._memory.load_turns(
            query.conversation_id, query.max_turns
        )
        context = self._memory.format_for_prompt(turns)
        return GetConversationMemoryResult(turns=turns, context=context)
