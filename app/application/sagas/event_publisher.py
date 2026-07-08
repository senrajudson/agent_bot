"""EventPublisher — wraps EventStore for Saga injection."""
from __future__ import annotations

import logging

from app.domain.events import DomainEvent
from app.infrastructure.event_store.base import EventStore

logger = logging.getLogger(__name__)

ERROR_MESSAGE_LIMIT: int = 200


def _truncate_error_message(message: str, limit: int = ERROR_MESSAGE_LIMIT) -> str:
    if len(message) <= limit:
        return message
    return message[:limit] + "..."


class EventPublisherImpl:
    """Publishes events to an EventStore."""

    def __init__(self, event_store: EventStore) -> None:
        self._store = event_store

    async def publish(self, stream: str, event: DomainEvent) -> None:
        try:
            await self._store.append(stream, event)
        except Exception as exc:
            logger.warning(
                "event=event_publish_failed event_type=%s event_id=%s stream=%s "
                "error_class=%s error_message_truncated=%s",
                type(event).__name__,
                event.event_id,
                stream,
                type(exc).__name__,
                _truncate_error_message(str(exc)),
            )

    async def publish_to_conversation(
        self, conversation_id: str, event: DomainEvent
    ) -> None:
        stream = f"conversation:{conversation_id}" if conversation_id else "conversation:anonymous"
        # Set conversation_id on the event before publishing
        fields = {k: v for k, v in event.__dict__.items() if k != "conversation_id"}
        event_with_cid = type(event)(**fields, conversation_id=conversation_id or None)
        await self.publish(stream, event_with_cid)


class NullEventPublisher:
    """No-op publisher for when events are disabled."""

    async def publish(self, stream: str, event: DomainEvent) -> None:
        pass

    async def publish_to_conversation(
        self, conversation_id: str, event: DomainEvent
    ) -> None:
        pass
