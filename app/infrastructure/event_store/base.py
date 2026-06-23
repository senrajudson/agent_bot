"""EventStore and EventPublisher protocols."""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.domain.events import DomainEvent


@runtime_checkable
class EventStore(Protocol):
    """Append-only event log. Each stream is a named sequence of events."""

    async def append(self, stream: str, event: DomainEvent) -> str: ...

    async def read(self, stream: str, from_id: str = "0") -> list[DomainEvent]: ...

    async def append_batch(self, stream: str, events: list[DomainEvent]) -> list[str]: ...


@runtime_checkable
class EventPublisher(Protocol):
    """Publishes events to streams. Used by the Saga."""

    async def publish(self, stream: str, event: DomainEvent) -> None: ...

    async def publish_to_conversation(
        self, conversation_id: str, event: DomainEvent
    ) -> None: ...
