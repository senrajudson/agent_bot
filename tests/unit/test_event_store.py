"""Tests for EventStore and EventPublisher."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.domain.events import (
    DomainEvent,
    AgentRouteSelected,
    ConversationMemoryLoaded,
    MessageProcessingFailed,
)
from app.infrastructure.event_store.in_memory import InMemoryEventStore
from app.infrastructure.event_store.base import EventStore, EventPublisher
from app.application.sagas.event_publisher import EventPublisherImpl, NullEventPublisher


# =========================================================================
# InMemoryEventStore
# =========================================================================
class TestInMemoryEventStore:
    @pytest.mark.asyncio
    async def test_append_returns_event_id(self) -> None:
        store = InMemoryEventStore()
        e = DomainEvent()
        result = await store.append("stream1", e)
        assert result == e.event_id

    @pytest.mark.asyncio
    async def test_read_returns_appended_events(self) -> None:
        store = InMemoryEventStore()
        e1 = DomainEvent()
        e2 = DomainEvent()
        await store.append("s", e1)
        await store.append("s", e2)
        events = await store.read("s")
        assert len(events) == 2
        assert events[0].event_id == e1.event_id
        assert events[1].event_id == e2.event_id

    @pytest.mark.asyncio
    async def test_read_empty_stream(self) -> None:
        store = InMemoryEventStore()
        events = await store.read("nonexistent")
        assert events == []

    @pytest.mark.asyncio
    async def test_append_batch(self) -> None:
        store = InMemoryEventStore()
        events = [DomainEvent() for _ in range(5)]
        ids = await store.append_batch("s", events)
        assert len(ids) == 5
        stored = await store.read("s")
        assert len(stored) == 5

    @pytest.mark.asyncio
    async def test_separate_streams(self) -> None:
        store = InMemoryEventStore()
        await store.append("a", DomainEvent())
        await store.append("b", DomainEvent())
        await store.append("b", DomainEvent())
        assert len(await store.read("a")) == 1
        assert len(await store.read("b")) == 2


# =========================================================================
# Protocol conformance
# =========================================================================
class TestProtocolConformance:
    def test_in_memory_is_event_store(self) -> None:
        assert isinstance(InMemoryEventStore(), EventStore)

    def test_in_memory_is_event_publisher(self) -> None:
        # InMemoryEventStore doesn't have publish methods
        assert not isinstance(InMemoryEventStore(), EventPublisher)


# =========================================================================
# EventPublisherImpl
# =========================================================================
class TestEventPublisherImpl:
    @pytest.mark.asyncio
    async def test_publish_delegates_to_store(self) -> None:
        store = InMemoryEventStore()
        publisher = EventPublisherImpl(store)
        e = AgentRouteSelected(route="pims")
        await publisher.publish("stream1", e)
        events = await store.read("stream1")
        assert len(events) == 1

    @pytest.mark.asyncio
    async def test_publish_to_conversation(self) -> None:
        store = InMemoryEventStore()
        publisher = EventPublisherImpl(store)
        e = ConversationMemoryLoaded(turns_count=3)
        await publisher.publish_to_conversation("conv-1", e)
        events = await store.read("conversation:conv-1")
        assert len(events) == 1
        assert events[0].conversation_id == "conv-1"

    @pytest.mark.asyncio
    async def test_publish_to_anonymous(self) -> None:
        store = InMemoryEventStore()
        publisher = EventPublisherImpl(store)
        e = DomainEvent()
        await publisher.publish_to_conversation("", e)
        events = await store.read("conversation:anonymous")
        assert len(events) == 1

    @pytest.mark.asyncio
    async def test_publish_failure_is_silent(self) -> None:
        """Event publish failure should not raise."""
        failing_store = AsyncMock(spec=EventStore)
        failing_store.append.side_effect = Exception("Redis down")
        publisher = EventPublisherImpl(failing_store)
        # Should not raise
        await publisher.publish("s", DomainEvent())


# =========================================================================
# NullEventPublisher
# =========================================================================
class TestNullEventPublisher:
    @pytest.mark.asyncio
    async def test_publish_is_noop(self) -> None:
        publisher = NullEventPublisher()
        # Should not raise, should not store anything
        await publisher.publish("s", DomainEvent())

    @pytest.mark.asyncio
    async def test_publish_to_conversation_is_noop(self) -> None:
        publisher = NullEventPublisher()
        await publisher.publish_to_conversation("c", DomainEvent())
