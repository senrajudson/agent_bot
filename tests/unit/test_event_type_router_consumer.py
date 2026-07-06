from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.infrastructure.outbox.event_type_router_consumer import (
    EventTypeRouterConsumer,
)
from app.infrastructure.outbox.outbox_dispatcher import OutboxEvent

NOW = "2026-01-01T00:00:00+00:00"


def _make_event(
    *,
    outbox_id: int = 1,
    event_id: str = "e1",
    event_type: str = "TestEvent",
    stream_id: str = "s1",
    stream_version: int = 1,
    aggregate_id: str | None = None,
    event_payload: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> OutboxEvent:
    return OutboxEvent(
        outbox_id=outbox_id,
        event_id=event_id,
        stream_id=stream_id,
        stream_version=stream_version,
        aggregate_id=aggregate_id,
        event_type=event_type,
        event_payload=event_payload or {},
        status="locked",
        attempts=0,
        max_attempts=3,
        available_at=NOW,
        locked_by="w-1",
        locked_until=NOW,
        created_at=NOW,
        updated_at=NOW,
        correlation_id=None,
        causation_id=None,
        metadata=metadata,
    )


class FakeHandler:
    """Handler fake que registra eventos recebidos."""

    def __init__(self) -> None:
        self.calls: list[OutboxEvent] = []
        self.should_raise: type[Exception] | None = None

    async def handle(self, event: OutboxEvent) -> None:
        if self.should_raise is not None:
            raise self.should_raise("simulated failure")
        self.calls.append(event)


# =========================================================================
# Init
# =========================================================================


class TestEventTypeRouterConsumerInit:
    def test_rejects_none_fallback(self) -> None:
        with pytest.raises(ValueError, match="fallback is required"):
            EventTypeRouterConsumer(fallback=None)

    def test_accepts_handlers_none(self) -> None:
        router = EventTypeRouterConsumer(handlers=None, fallback=FakeHandler())
        assert router._handlers == {}
        assert router._fallback is not None

    def test_accepts_empty_handlers(self) -> None:
        router = EventTypeRouterConsumer(handlers={}, fallback=FakeHandler())
        assert router._handlers == {}
        assert router._fallback is not None

    def test_copies_handlers_dict(self) -> None:
        original: dict[str, FakeHandler] = {"Foo": FakeHandler()}
        router = EventTypeRouterConsumer(handlers=original, fallback=FakeHandler())
        original["Bar"] = FakeHandler()
        assert "Bar" not in router._handlers

    def test_does_not_import_logging_consumer(self) -> None:
        from app.infrastructure.outbox import event_type_router_consumer as router_mod

        assert "LoggingOutboxConsumer" not in dir(router_mod)


# =========================================================================
# Handle
# =========================================================================


class TestEventTypeRouterConsumerHandle:
    @pytest.mark.asyncio
    async def test_routes_to_specific_handler(self) -> None:
        handler_a = FakeHandler()
        handler_b = FakeHandler()
        router = EventTypeRouterConsumer(
            handlers={"EventA": handler_a, "EventB": handler_b},
            fallback=FakeHandler(),
        )
        event_a = _make_event(event_type="EventA")
        event_b = _make_event(event_type="EventB")

        await router.handle(event_a)
        await router.handle(event_b)

        assert len(handler_a.calls) == 1
        assert handler_a.calls[0].event_type == "EventA"
        assert len(handler_b.calls) == 1
        assert handler_b.calls[0].event_type == "EventB"

    @pytest.mark.asyncio
    async def test_routes_to_fallback_when_event_type_unknown(self) -> None:
        fallback = FakeHandler()
        handler_a = FakeHandler()
        router = EventTypeRouterConsumer(
            handlers={"EventA": handler_a},
            fallback=fallback,
        )
        event = _make_event(event_type="UnknownEvent")

        await router.handle(event)

        assert len(handler_a.calls) == 0
        assert len(fallback.calls) == 1
        assert fallback.calls[0].event_type == "UnknownEvent"

    @pytest.mark.asyncio
    async def test_does_not_mutate_outbox_event(self) -> None:
        handler = FakeHandler()
        router = EventTypeRouterConsumer(
            handlers={"TestEvent": handler},
            fallback=FakeHandler(),
        )
        event = _make_event(event_type="TestEvent")
        original = event.event_id

        await router.handle(event)

        assert event.event_id == original

    @pytest.mark.asyncio
    async def test_handler_raises_exception_propagates(self) -> None:
        handler = FakeHandler()
        handler.should_raise = ValueError
        router = EventTypeRouterConsumer(
            handlers={"FailEvent": handler},
            fallback=FakeHandler(),
        )
        event = _make_event(event_type="FailEvent")

        with pytest.raises(ValueError, match="simulated failure"):
            await router.handle(event)

    @pytest.mark.asyncio
    async def test_fallback_is_async_callable(self) -> None:
        fallback = AsyncMock()
        router = EventTypeRouterConsumer(
            handlers={},
            fallback=fallback,
        )
        event = _make_event(event_type="AnyEvent")

        await router.handle(event)

        fallback.handle.assert_awaited_once_with(event)
