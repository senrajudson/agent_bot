"""Tests for ConversationMemorySaveRequested event."""
from __future__ import annotations

from app.domain.events import (
    DOMAIN_EVENTS_REGISTRY,
    ConversationMemorySaveRequested,
)


class TestConversationMemorySaveRequested:
    def test_event_type_in_registry(self) -> None:
        assert "ConversationMemorySaveRequested" in DOMAIN_EVENTS_REGISTRY

    def test_event_type_name(self) -> None:
        event = ConversationMemorySaveRequested()
        assert event.event_type == "ConversationMemorySaveRequested"

    def test_serialization_full_payload(self) -> None:
        event = ConversationMemorySaveRequested(
            conversation_id="user-123",
            aggregate_id="user-123",
            aggregate_type="conversation",
            user_id="user-123",
            user_message="Hello",
            assistant_message="Hi!",
            metadata={"categoria": "pims"},
        )
        record = event.to_event_record()
        assert record["event_type"] == "ConversationMemorySaveRequested"
        assert record["payload"]["user_id"] == "user-123"
        assert record["payload"]["user_message"] == "Hello"
        assert record["payload"]["assistant_message"] == "Hi!"
        assert record["conversation_id"] == "user-123"
        assert record["metadata"] == {"categoria": "pims"}

    def test_serialization_minimal_payload(self) -> None:
        event = ConversationMemorySaveRequested(
            conversation_id="user-123",
            user_message="Hello",
            assistant_message="Hi!",
        )
        record = event.to_event_record()
        assert record["payload"]["user_id"] is None
        assert record["payload"]["user_message"] == "Hello"

    def test_envelope_fields(self) -> None:
        event = ConversationMemorySaveRequested(
            conversation_id="user-123",
            aggregate_id="user-123",
            aggregate_type="conversation",
        )
        assert event.event_id and len(event.event_id) > 0
        assert event.event_version == 1
        assert event.aggregate_id == "user-123"
        assert event.aggregate_type == "conversation"
        assert event.conversation_id == "user-123"
