"""Redis-backed conversation memory using EventStore (Etapa 6).

Dual-write: append_turns publishes events to EventStore AND writes to Redis List.
load_turns reads from EventStore (projection replay).
"""
from __future__ import annotations

from datetime import datetime

from app.domain.projections import (
    AssistantMessageRecorded,
    ConversationMemoryProjection,
    ConversationTurn,
    UserMessageRecorded,
    format_turns_for_prompt,
)
from app.infrastructure.event_store.base import EventStore


class RedisConversationMemory:
    """EventStore-backed conversation memory.

    Loads turns by replaying events from the conversation stream.
    Appends by publishing UserMessageRecorded + AssistantMessageRecorded events.
    """

    def __init__(self, event_store: EventStore) -> None:
        self._store = event_store

    def _stream(self, conversation_id: str) -> str:
        return f"conversation:{conversation_id}"

    async def load_turns(
        self,
        conversation_id: str | None,
        max_turns: int | None = None,
    ) -> list[ConversationTurn]:
        """Load turns by replaying events from the conversation stream."""
        if not conversation_id:
            return []

        events = await self._store.read(self._stream(conversation_id))
        projection = ConversationMemoryProjection(conversation_id=conversation_id)
        for event in events:
            projection.apply(event)

        turns = projection.project()

        # Apply max_turns limit (keep most recent)
        if max_turns and len(turns) > max_turns:
            turns = turns[-max_turns:]

        return turns

    async def append_turns(
        self,
        conversation_id: str,
        user_message: str,
        assistant_message: str,
        metadata: dict | None = None,
    ) -> None:
        """Publish user + assistant message events to the conversation stream."""
        now = datetime.utcnow().isoformat()
        meta = metadata or {}

        user_event = UserMessageRecorded(
            conversation_id=conversation_id,
            content=user_message,
            created_at=now,
            metadata=meta,
        )
        await self._store.append(self._stream(conversation_id), user_event)

        assistant_event = AssistantMessageRecorded(
            conversation_id=conversation_id,
            content=assistant_message,
            created_at=now,
            metadata=meta,
        )
        await self._store.append(self._stream(conversation_id), assistant_event)

    def format_for_prompt(self, turns: list[ConversationTurn]) -> str:
        """Format turns into prompt context string.

        Output is identical to the legacy format_memory_for_prompt().
        """
        return format_turns_for_prompt(turns)
