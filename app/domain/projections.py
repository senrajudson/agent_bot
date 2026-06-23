"""Projections — read models built from event streams.

ConversationMemoryProjection reconstructs ConversationTurn list from events.
This is the core of Etapa 6: ChatMemoryTurn → Event Sourcing.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


# ---------------------------------------------------------------------------
# ConversationTurn (read model — replaces ChatMemoryTurn)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ConversationTurn:
    """Read model — reconstructed from events.

    Same contract as ChatMemoryTurn but built from EventStore.
    """
    role: str  # "user" | "assistant"
    content: str
    created_at: str  # ISO format
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "content": self.content,
            "created_at": self.created_at,
            "metadata": self.metadata,
        }


# ---------------------------------------------------------------------------
# Projection
# ---------------------------------------------------------------------------

@dataclass
class ConversationMemoryProjection:
    """Projection that reconstructs ConversationTurn list from events.

    Reads from stream "conversation:{conversation_id}".
    Builds turns in order based on UserMessageRecorded and AssistantMessageRecorded events.
    """
    conversation_id: str
    turns: list[ConversationTurn] = field(default_factory=list)
    _pending_user: dict | None = field(default=None, repr=False)

    def apply(self, event: Any) -> None:
        """Apply an event to the projection state.

        Handles: UserMessageRecorded, AssistantMessageRecorded.
        Ignores other event types (idempotent).
        """
        event_type = type(event).__name__

        if event_type == "UserMessageRecorded":
            self._pending_user = {
                "content": getattr(event, "content", ""),
                "created_at": getattr(event, "created_at", ""),
                "metadata": dict(getattr(event, "metadata", {})),
            }

        elif event_type == "AssistantMessageRecorded":
            user_info = self._pending_user or {
                "content": "",
                "created_at": getattr(event, "created_at", ""),
                "metadata": {},
            }
            self.turns.append(ConversationTurn(
                role="user",
                content=user_info["content"],
                created_at=user_info["created_at"],
                metadata=user_info["metadata"],
            ))
            self.turns.append(ConversationTurn(
                role="assistant",
                content=getattr(event, "content", ""),
                created_at=getattr(event, "created_at", ""),
                metadata=dict(getattr(event, "metadata", {})),
            ))
            self._pending_user = None

    def project(self) -> list[ConversationTurn]:
        """Return the projected turns as a list."""
        return list(self.turns)


# ---------------------------------------------------------------------------
# Memory events (new in Etapa 6)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class UserMessageRecorded:
    """Event: a user message was recorded in the conversation."""
    event_id: str = ""
    occurred_at: datetime = field(default_factory=lambda: datetime.utcnow())
    conversation_id: str | None = None
    content: str = ""
    created_at: str = ""
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class AssistantMessageRecorded:
    """Event: an assistant response was recorded in the conversation."""
    event_id: str = ""
    occurred_at: datetime = field(default_factory=lambda: datetime.utcnow())
    conversation_id: str | None = None
    content: str = ""
    created_at: str = ""
    metadata: dict = field(default_factory=dict)


def format_turns_for_prompt(turns: list[ConversationTurn]) -> str:
    """Format turns into prompt context string.

    Output is identical to the legacy format_memory_for_prompt().
    """
    if not turns:
        return ""

    lines = ["Contexto recente da conversa:"]

    lines.append(
        "\n[Leia as conversas abaixo e lembre-se dos dados\n"
        "                 \ne tags citados para conseguir responder a \n"
        "                 \na pergunta do usuário]\n"
    )

    for turn in turns:
        role_label = "> Usuário" if turn.role == "user" else "> Assistente"
        content = turn.content.strip()
        if not content:
            continue
        lines.append(f"{role_label}: {content}")

    lines.append("\n[Última mensagem do usuário baixo]")
    return "\n".join(lines).strip()
