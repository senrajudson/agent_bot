"""Tests for Domain Events."""
from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timezone

import pytest

from app.domain.events import (
    AgentRunCompleted,
    AgentRunStarted,
    AgentRouteSelected,
    ConversationMemoryLoaded,
    ConversationMemorySaved,
    DOMAIN_EVENTS_REGISTRY,
    DomainEvent,
    InboundMessageReceived,
    MessageProcessingFailed,
    OcrExtractionCompleted,
    OutboundReplyGenerated,
    RagContextRetrieved,
)


# =========================================================================
# Base DomainEvent
# =========================================================================
class TestDomainEvent:
    def test_has_event_id(self) -> None:
        e = DomainEvent()
        assert isinstance(e.event_id, str)
        assert len(e.event_id) == 36  # UUID

    def test_has_occurred_at(self) -> None:
        e = DomainEvent()
        assert isinstance(e.occurred_at, datetime)

    def test_occurred_at_is_recent(self) -> None:
        e = DomainEvent()
        now = datetime.now(timezone.utc)
        delta = (now - e.occurred_at).total_seconds()
        assert delta < 5  # within 5 seconds

    def test_to_dict_contains_event_type(self) -> None:
        e = DomainEvent()
        d = e.to_dict()
        assert d["event_type"] == "DomainEvent"

    def test_to_dict_contains_event_id(self) -> None:
        e = DomainEvent()
        d = e.to_dict()
        assert "event_id" in d
        assert d["event_id"] == e.event_id

    def test_to_dict_contains_occurred_at(self) -> None:
        e = DomainEvent()
        d = e.to_dict()
        assert "occurred_at" in d

    def test_to_dict_contains_conversation_id(self) -> None:
        e = DomainEvent(conversation_id="conv-1")
        d = e.to_dict()
        assert d["conversation_id"] == "conv-1"

    def test_is_frozen(self) -> None:
        e = DomainEvent()
        with pytest.raises(FrozenInstanceError):
            e.event_id = "other"  # type: ignore[misc]


# =========================================================================
# Specific events
# =========================================================================
class TestInboundMessageReceived:
    def test_to_dict(self) -> None:
        e = InboundMessageReceived(
            message_id="msg-1",
            user_id="u1",
            text="hello",
            has_images=True,
            image_count=2,
        )
        d = e.to_dict()
        assert d["event_type"] == "InboundMessageReceived"
        assert d["message_id"] == "msg-1"
        assert d["user_id"] == "u1"
        assert d["text"] == "hello"
        assert d["has_images"] is True
        assert d["image_count"] == 2


class TestOcrExtractionCompleted:
    def test_to_dict(self) -> None:
        e = OcrExtractionCompleted(
            tags_found=["TAG_A", "TAG_B"],
            total_text_length=150,
        )
        d = e.to_dict()
        assert d["tags_found"] == ["TAG_A", "TAG_B"]
        assert d["total_text_length"] == 150


class TestConversationMemoryLoaded:
    def test_to_dict(self) -> None:
        e = ConversationMemoryLoaded(turns_count=5, max_turns=8)
        d = e.to_dict()
        assert d["turns_count"] == 5
        assert d["max_turns"] == 8


class TestAgentRouteSelected:
    def test_to_dict(self) -> None:
        e = AgentRouteSelected(route="pims", latency_ms=120)
        d = e.to_dict()
        assert d["route"] == "pims"
        assert d["latency_ms"] == 120


class TestRagContextRetrieved:
    def test_to_dict(self) -> None:
        e = RagContextRetrieved(
            query_length=50, chunks_retrieved=3, fixed_chunk_included=True
        )
        d = e.to_dict()
        assert d["chunks_retrieved"] == 3
        assert d["fixed_chunk_included"] is True


class TestAgentRunStarted:
    def test_to_dict(self) -> None:
        e = AgentRunStarted(run_id="r1", agent_type="pi", route="pims")
        d = e.to_dict()
        assert d["run_id"] == "r1"
        assert d["agent_type"] == "pi"


class TestAgentRunCompleted:
    def test_to_dict(self) -> None:
        e = AgentRunCompleted(run_id="r1", output_length=100)
        d = e.to_dict()
        assert d["output_length"] == 100


class TestMessageProcessingFailed:
    def test_to_dict(self) -> None:
        e = MessageProcessingFailed(
            error_class="RuntimeError",
            error_message="boom",
            stage="saga",
        )
        d = e.to_dict()
        assert d["error_class"] == "RuntimeError"
        assert d["error_message"] == "boom"
        assert d["stage"] == "saga"


class TestOutboundReplyGenerated:
    def test_to_dict(self) -> None:
        e = OutboundReplyGenerated(output_length=200, route="pims")
        d = e.to_dict()
        assert d["output_length"] == 200
        assert d["route"] == "pims"


class TestConversationMemorySaved:
    def test_to_dict(self) -> None:
        e = ConversationMemorySaved(user_turn_saved=True, assistant_turn_saved=True)
        d = e.to_dict()
        assert d["user_turn_saved"] is True
        assert d["assistant_turn_saved"] is True


# =========================================================================
# Event registry
# =========================================================================
class TestEventRegistry:
    def test_registry_has_24_events(self) -> None:
        assert len(DOMAIN_EVENTS_REGISTRY) == 24

    def test_registry_values_are_event_classes(self) -> None:
        for name, cls in DOMAIN_EVENTS_REGISTRY.items():
            assert issubclass(cls, DomainEvent)

    def test_registry_key_matches_class_name(self) -> None:
        for name, cls in DOMAIN_EVENTS_REGISTRY.items():
            assert name == cls.__name__

    def test_all_events_to_dict_produce_event_type(self) -> None:
        for cls in DOMAIN_EVENTS_REGISTRY.values():
            event = cls()
            d = event.to_dict()
            assert "event_type" in d
            assert d["event_type"] == cls.__name__


# =========================================================================
# Immutability
# =========================================================================
class TestImmutability:
    @pytest.mark.parametrize("event_cls", list(DOMAIN_EVENTS_REGISTRY.values()))
    def test_event_is_frozen(self, event_cls) -> None:
        event = event_cls()
        with pytest.raises(FrozenInstanceError):
            event.event_id = "changed"  # type: ignore[misc]
