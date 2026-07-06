"""Outbox handler for persisting conversation memory turns asynchronously."""
from __future__ import annotations

import logging
import re
from typing import Any, Mapping

from app.application.commands.save_conversation_turn import (
    SaveConversationTurn,
    SaveConversationTurnHandler,
)
from app.domain.protocols import ConversationMemorySaver
from app.infrastructure.outbox.outbox_dispatcher import OutboxEvent

logger = logging.getLogger(
    "app.infrastructure.outbox.handlers.conversation_memory_save_handler"
)

_CONSUMER_NAME_REGEX = re.compile(
    r"^outbox-[a-z][a-z0-9-]{0,30}-v[0-9]+$"
)
_EXPECTED_EVENT_TYPE = "ConversationMemorySaveRequested"
_CONSUMER_NAME = "outbox-conversation-memory-save-v1"


class SaveConversationTurnMemorySaver:
    """Adapter: implements ConversationMemorySaver via SaveConversationTurnHandler.

    Converts event_payload (dict) to SaveConversationTurn Command
    and delegates to the existing handler.
    """

    def __init__(self, save_handler: SaveConversationTurnHandler) -> None:
        self._handler = save_handler

    async def save(self, payload: Mapping[str, Any]) -> None:
        if not payload:
            raise ValueError("payload is empty")
        conversation_id = payload.get("conversation_id")
        if not conversation_id:
            raise ValueError("payload.conversation_id is required")

        command = SaveConversationTurn(
            conversation_id=conversation_id,
            user_message=payload.get("user_message", ""),
            assistant_message=payload.get("assistant_message", ""),
            metadata=payload.get("metadata") or {},
        )
        await self._handler.handle(command)


class ConversationMemorySaveOutboxHandler:
    """Outbox handler that persists conversation memory turns.

    Receives OutboxEvent, validates event_type and payload,
    delegates to a ConversationMemorySaver.
    """

    def __init__(self, saver: ConversationMemorySaver) -> None:
        if not _CONSUMER_NAME_REGEX.match(_CONSUMER_NAME):
            raise ValueError(f"Invalid consumer_name: {_CONSUMER_NAME!r}")
        self._saver = saver

    async def handle(self, event: OutboxEvent) -> None:
        if event.event_type != _EXPECTED_EVENT_TYPE:
            raise ValueError(
                f"Unexpected event_type: {event.event_type!r} "
                f"(expected {_EXPECTED_EVENT_TYPE!r})"
            )
        if not event.event_payload:
            raise ValueError("event_payload is empty")

        # Copy payload to avoid mutation of the original OutboxEvent
        payload_copy = dict(event.event_payload)
        # Enrich with envelope fields needed by the adapter
        payload_copy["conversation_id"] = event.aggregate_id or ""
        if event.metadata:
            payload_copy["turn_metadata"] = dict(event.metadata)
        await self._saver.save(payload_copy)

        logger.debug(
            "conversation_memory_save_processed",
            extra={
                "event_id": event.event_id,
                "event_type": event.event_type,
                "consumer_name": _CONSUMER_NAME,
                "stream_id": event.stream_id,
                "outbox_id": event.outbox_id,
            },
        )
