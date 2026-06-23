"""EventPublisher — wraps EventStore for Saga injection."""
from __future__ import annotations

from app.domain.events import DomainEvent
from app.infrastructure.event_store.base import EventStore


class EventPublisherImpl:
    """Publishes events to an EventStore."""

    def __init__(self, event_store: EventStore) -> None:
        self._store = event_store

    async def publish(self, stream: str, event: DomainEvent) -> None:
        try:
            await self._store.append(stream, event)
        except Exception:
            pass  # Fire-and-forget: event publish failure is non-critical

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
