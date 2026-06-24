"""Tests for InMemoryEventStore EventStoreV2 interface."""
from __future__ import annotations

import pytest

from app.domain.events import (
    AgentRouteSelected,
    ConversationMemoryLoaded,
    DomainEvent,
    new_event_id,
)
from app.infrastructure.event_store.in_memory import InMemoryEventStore
from app.infrastructure.event_store.errors import ConcurrencyConflictError


# =========================================================================
# append_to_stream + load_stream
# =========================================================================
class TestInMemoryEventStoreV2:
    @pytest.mark.asyncio
    async def test_append_to_stream_increments_version(self) -> None:
        store = InMemoryEventStore()
        await store.append_to_stream("s1", [DomainEvent(), DomainEvent()])
        assert store.get_stream_version("s1") == 2

    @pytest.mark.asyncio
    async def test_load_stream_returns_all_events(self) -> None:
        store = InMemoryEventStore()
        e1 = AgentRouteSelected(route="pims")
        e2 = AgentRouteSelected(route="general")
        await store.append_to_stream("s1", [e1, e2])
        events = await store.load_stream("s1")
        assert len(events) == 2
        assert events[0].event_id == e1.event_id
        assert events[1].event_id == e2.event_id

    @pytest.mark.asyncio
    async def test_load_stream_from_version(self) -> None:
        store = InMemoryEventStore()
        events_in = [DomainEvent() for _ in range(5)]
        await store.append_to_stream("s1", events_in)
        # from_version=2 means skip first 2 (0-indexed)
        events = await store.load_stream("s1", from_version=2)
        assert len(events) == 3

    @pytest.mark.asyncio
    async def test_load_stream_empty(self) -> None:
        store = InMemoryEventStore()
        events = await store.load_stream("nonexistent")
        assert events == []

    @pytest.mark.asyncio
    async def test_separate_streams(self) -> None:
        store = InMemoryEventStore()
        await store.append_to_stream("a", [DomainEvent()])
        await store.append_to_stream("b", [DomainEvent(), DomainEvent()])
        assert len(await store.load_stream("a")) == 1
        assert len(await store.load_stream("b")) == 2
        assert store.get_stream_version("a") == 1
        assert store.get_stream_version("b") == 2


# =========================================================================
# Optimistic concurrency
# =========================================================================
class TestConcurrency:
    @pytest.mark.asyncio
    async def test_expected_version_success(self) -> None:
        store = InMemoryEventStore()
        await store.append_to_stream("s1", [DomainEvent()])
        # Expected version 1 should succeed (current is 1)
        await store.append_to_stream("s1", [DomainEvent()], expected_version=1)
        assert store.get_stream_version("s1") == 2

    @pytest.mark.asyncio
    async def test_expected_version_none_always_succeeds(self) -> None:
        store = InMemoryEventStore()
        await store.append_to_stream("s1", [DomainEvent()])
        await store.append_to_stream("s1", [DomainEvent()], expected_version=None)
        assert store.get_stream_version("s1") == 2

    @pytest.mark.asyncio
    async def test_expected_version_wrong_raises(self) -> None:
        store = InMemoryEventStore()
        await store.append_to_stream("s1", [DomainEvent()])
        with pytest.raises(ConcurrencyConflictError) as exc_info:
            await store.append_to_stream("s1", [DomainEvent()], expected_version=99)
        assert exc_info.value.stream_id == "s1"
        assert exc_info.value.expected_version == 99
        assert exc_info.value.actual_version == 1

    @pytest.mark.asyncio
    async def test_expected_version_on_empty_stream(self) -> None:
        store = InMemoryEventStore()
        # Expected version 0 on empty stream should succeed
        await store.append_to_stream("s1", [DomainEvent()], expected_version=0)
        assert store.get_stream_version("s1") == 1


# =========================================================================
# load_by_correlation_id
# =========================================================================
class TestLoadByCorrelationId:
    @pytest.mark.asyncio
    async def test_filters_by_correlation_id(self) -> None:
        store = InMemoryEventStore()
        e1 = DomainEvent(correlation_id="c1")
        e2 = DomainEvent(correlation_id="c2")
        e3 = DomainEvent(correlation_id="c1")
        await store.append_to_stream("s1", [e1, e2, e3])
        results = await store.load_by_correlation_id("c1")
        assert len(results) == 2
        assert all(e.correlation_id == "c1" for e in results)

    @pytest.mark.asyncio
    async def test_no_match(self) -> None:
        store = InMemoryEventStore()
        await store.append_to_stream("s1", [DomainEvent()])
        results = await store.load_by_correlation_id("nonexistent")
        assert results == []


# =========================================================================
# load_by_event_type
# =========================================================================
class TestLoadByEventType:
    @pytest.mark.asyncio
    async def test_filters_by_type(self) -> None:
        store = InMemoryEventStore()
        await store.append_to_stream("s1", [
            AgentRouteSelected(route="pims"),
            ConversationMemoryLoaded(turns_count=3),
            AgentRouteSelected(route="general"),
        ])
        results = await store.load_by_event_type("AgentRouteSelected")
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_limit(self) -> None:
        store = InMemoryEventStore()
        events = [AgentRouteSelected(route=f"r{i}") for i in range(10)]
        await store.append_to_stream("s1", events)
        results = await store.load_by_event_type("AgentRouteSelected", limit=3)
        assert len(results) == 3
