"""Tests for ConversationMemorySaveOutboxHandler."""
from __future__ import annotations

from typing import Any, Mapping
from unittest.mock import AsyncMock, patch

import pytest

from app.infrastructure.outbox.handlers.conversation_memory_save_handler import (
    _CONSUMER_NAME,
    ConversationMemorySaveOutboxHandler,
)
from app.infrastructure.outbox.outbox_dispatcher import OutboxEvent


class FakeSaver:
    """Fake ConversationMemorySaver for handler tests."""

    def __init__(self) -> None:
        self.saved_payloads: list[Mapping[str, Any]] = []
        self.should_raise: type[Exception] | None = None

    async def save(self, payload: Mapping[str, Any]) -> None:
        if self.should_raise is not None:
            raise self.should_raise("simulated saver failure")
        self.saved_payloads.append(payload)


@pytest.fixture
def saver() -> FakeSaver:
    return FakeSaver()


@pytest.fixture
def handler(saver: FakeSaver) -> ConversationMemorySaveOutboxHandler:
    return ConversationMemorySaveOutboxHandler(saver=saver)


_ADD_EVENT_PAYLOAD = {
    "user_id": None,
    "user_message": "Hello",
    "assistant_message": "Hi!",
}


def _make_event(
    *,
    event_type: str = "ConversationMemorySaveRequested",
    event_payload: dict | None = None,
) -> OutboxEvent:
    payload = _ADD_EVENT_PAYLOAD if event_payload is None else event_payload
    return OutboxEvent(
        outbox_id=1,
        event_id="evt-001",
        stream_id="conversation:user-123",
        stream_version=1,
        aggregate_id="user-123",
        event_type=event_type,
        event_payload=payload,
        status="locked",
        attempts=0,
        max_attempts=3,
        available_at="2026-01-01T00:00:00+00:00",
        locked_by="w-1",
        locked_until="2026-01-01T00:00:00+00:00",
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",
        correlation_id=None,
        causation_id=None,
        metadata=None,
    )


class TestConversationMemorySaveOutboxHandler:
    async def test_handle_calls_saver_with_payload_copy(
        self, handler: ConversationMemorySaveOutboxHandler, saver: FakeSaver
    ) -> None:
        payload = {"user_id": None, "user_message": "m", "assistant_message": "a"}
        event = _make_event(event_payload=payload)
        await handler.handle(event)
        assert len(saver.saved_payloads) == 1
        saved = saver.saved_payloads[0]
        assert saved["user_message"] == "m"
        assert saved["assistant_message"] == "a"
        assert saved["conversation_id"] == "user-123"

    async def test_handle_does_not_mutate_event_payload(
        self, handler: ConversationMemorySaveOutboxHandler, saver: FakeSaver
    ) -> None:
        payload = {"conversation_id": "c1", "user_message": "m", "assistant_message": "a"}
        event = _make_event(event_payload=payload)
        original_id = event.event_id
        await handler.handle(event)
        assert event.event_id == original_id
        assert event.event_payload == payload

    async def test_handle_raises_on_wrong_event_type(
        self, handler: ConversationMemorySaveOutboxHandler
    ) -> None:
        event = _make_event(event_type="WrongType")
        with pytest.raises(ValueError, match="Unexpected event_type"):
            await handler.handle(event)

    async def test_handle_raises_on_empty_event_payload(
        self, handler: ConversationMemorySaveOutboxHandler
    ) -> None:
        event = _make_event(event_payload={})
        with pytest.raises(ValueError, match="event_payload is empty"):
            await handler.handle(event)

    async def test_handle_propagates_saver_exception(
        self, saver: FakeSaver
    ) -> None:
        saver.should_raise = RuntimeError
        handler = ConversationMemorySaveOutboxHandler(saver=saver)
        event = _make_event()
        with pytest.raises(RuntimeError, match="simulated saver failure"):
            await handler.handle(event)

    async def test_handle_does_not_log_payload_contents(
        self, saver: FakeSaver, caplog
    ) -> None:
        import logging
        caplog.set_level(logging.DEBUG)
        handler = ConversationMemorySaveOutboxHandler(saver=saver)
        event = _make_event()
        await handler.handle(event)
        log_text = caplog.text
        assert "user_message" not in log_text
        assert "assistant_message" not in log_text

    async def test_consumer_name_validation_passes(self) -> None:
        handler = ConversationMemorySaveOutboxHandler(saver=FakeSaver())
        assert handler is not None

    @patch(
        "app.infrastructure.outbox.handlers.conversation_memory_save_handler._CONSUMER_NAME",
        "invalid!name",
    )
    async def test_init_with_invalid_consumer_name_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid consumer_name"):
            ConversationMemorySaveOutboxHandler(saver=FakeSaver())
