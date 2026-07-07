"""Command: Save a conversation turn to memory."""
from __future__ import annotations

from dataclasses import dataclass

from app.application.commands.base import Command
from app.domain.protocols import ConversationMemory


@dataclass(frozen=True)
class SaveConversationTurn(Command):
    """Request saving a user + assistant turn to conversation memory."""

    conversation_id: str
    user_message: str
    assistant_message: str
    metadata: dict | None = None
    idempotency_key: str | None = None


class SaveConversationTurnHandler:
    """Saves conversation turns to Redis-backed memory.

    Delegates to a ConversationMemory (injected via constructor).
    No direct dependency on Redis, json, or any infrastructure.
    """

    def __init__(self, memory: ConversationMemory) -> None:
        self._memory = memory

    async def handle(self, command: SaveConversationTurn) -> None:
        if not command.conversation_id:
            return
        if not command.user_message and not command.assistant_message:
            return
        kwargs = {}
        if command.idempotency_key is not None:
            kwargs["idempotency_key"] = command.idempotency_key
        await self._memory.append_turns(
            conversation_id=command.conversation_id,
            user_message=command.user_message,
            assistant_message=command.assistant_message,
            metadata=command.metadata or {},
            **kwargs,
        )
