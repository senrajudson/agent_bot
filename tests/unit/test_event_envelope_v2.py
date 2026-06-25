"""Tests for Domain Event envelope v2 (Prompt 1.6)."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from app.domain.enums import AggregateType
from app.domain.events import (
    AgentRunStarted,
    ConversationMemoryLoaded,
    ConversationMemorySaved,
    DOMAIN_EVENTS_REGISTRY,
    DomainEvent,
    InboundMessageReceived,
    MessageProcessingFailed,
    OcrExtractionCompleted,
    new_event_id,
    now_utc,
    event_type_from_class,
)


# =========================================================================
# Helpers
# =========================================================================
class TestHelpers:
    def test_new_event_id_returns_uuid_string(self) -> None:
        eid = new_event_id()
        assert isinstance(eid, str)
        assert len(eid) == 36

    def test_new_event_id_is_unique(self) -> None:
        ids = {new_event_id() for _ in range(100)}
        assert len(ids) == 100

    def test_now_utc_is_timezone_aware(self) -> None:
        t = now_utc()
        assert t.tzinfo is not None
        assert t.tzinfo == timezone.utc

    def test_event_type_from_class(self) -> None:
        assert event_type_from_class(AgentRunStarted) == "AgentRunStarted"
        assert event_type_from_class(DomainEvent) == "DomainEvent"


# =========================================================================
# Base DomainEvent envelope
# =========================================================================
class TestDomainEventEnvelope:
    def test_has_all_envelope_fields(self) -> None:
        e = DomainEvent()
        assert isinstance(e.event_id, str)
        assert e.event_type == "DomainEvent"
        assert e.event_version == 1
        assert isinstance(e.occurred_at, datetime)
        assert e.occurred_at.tzinfo is not None
        assert e.aggregate_id is None
        assert e.aggregate_type is None
        assert e.correlation_id is None
        assert e.causation_id is None
        assert e.conversation_id is None
        assert e.payload == {}
        assert e.metadata == {}

    def test_event_type_set_in_post_init(self) -> None:
        e = DomainEvent()
        assert e.event_type == "DomainEvent"

    def test_to_event_record_has_all_fields(self) -> None:
        e = AgentRunStarted(
            run_id="r1",
            agent_type="pi",
            route="pims",
            correlation_id="corr-1",
            aggregate_id="agg-1",
            aggregate_type=AggregateType.AGENT_RUN.value,
            causation_id="cause-1",
            conversation_id="conv-1",
            metadata={"step": 1},
        )
        r = e.to_event_record()
        assert r["event_id"] == e.event_id
        assert r["event_type"] == "AgentRunStarted"
        assert r["event_version"] == 1
        assert "occurred_at" in r
        assert r["correlation_id"] == "corr-1"
        assert r["aggregate_id"] == "agg-1"
        assert r["aggregate_type"] == "AgentRun"
        assert r["causation_id"] == "cause-1"
        assert r["conversation_id"] == "conv-1"
        assert r["payload"]["run_id"] == "r1"
        assert r["metadata"] == {"step": 1}

    def test_to_dict_legacy_format(self) -> None:
        e = AgentRunStarted(run_id="r1", route="pims")
        d = e.to_dict()
        assert d["event_type"] == "AgentRunStarted"
        assert d["run_id"] == "r1"
        assert "aggregate_id" not in d
        assert "event_version" not in d

    def test_is_frozen(self) -> None:
        e = DomainEvent()
        with pytest.raises(AttributeError):
            e.event_id = "changed"  # type: ignore[misc]


# =========================================================================
# Specific events — envelope fields
# =========================================================================
class TestSpecificEventEnvelope:
    def test_inbound_message_received(self) -> None:
        e = InboundMessageReceived(
            message_id="m1",
            user_id="u1",
            text="hello",
            has_images=True,
            image_count=2,
            correlation_id="corr-1",
            aggregate_id="agg-1",
        )
        r = e.to_event_record()
        assert r["correlation_id"] == "corr-1"
        assert r["aggregate_id"] == "agg-1"
        assert r["payload"]["message_id"] == "m1"
        assert r["payload"]["has_images"] is True

    def test_conversation_memory_saved(self) -> None:
        e = ConversationMemorySaved(
            user_turn_saved=True,
            assistant_turn_saved=True,
            total_turns=4,
        )
        r = e.to_event_record()
        assert r["event_type"] == "ConversationMemorySaved"
        assert r["payload"]["user_turn_saved"] is True
        assert r["payload"]["total_turns"] == 4

    def test_message_processing_failed(self) -> None:
        e = MessageProcessingFailed(
            error_class="RuntimeError",
            error_message="boom",
            stage="saga",
            correlation_id="corr-1",
        )
        r = e.to_event_record()
        assert r["correlation_id"] == "corr-1"
        assert r["payload"]["error_class"] == "RuntimeError"

    def test_ocr_extraction_completed(self) -> None:
        e = OcrExtractionCompleted(
            tags_found=["TAG_A", "TAG_B"],
            total_text_length=150,
            image_count=2,
        )
        r = e.to_event_record()
        assert r["payload"]["tags_found"] == ["TAG_A", "TAG_B"]
        assert r["payload"]["image_count"] == 2


# =========================================================================
# AggregateType enum
# =========================================================================
class TestAggregateType:
    def test_values(self) -> None:
        assert AggregateType.CONVERSATION.value == "Conversation"
        assert AggregateType.AGENT_RUN.value == "AgentRun"
        assert AggregateType.GOOGLE_CHAT_MESSAGE.value == "GoogleChatMessage"
        assert AggregateType.PI_TAG_QUERY.value == "PiTagQuery"


# =========================================================================
# Event type per event
# =========================================================================
class TestEventTypePerEvent:
    @pytest.mark.parametrize("event_cls", list(DOMAIN_EVENTS_REGISTRY.values()))
    def test_event_type_matches_class_name(self, event_cls) -> None:
        e = event_cls()
        assert e.event_type == event_cls.__name__

    def test_all_events_have_version_1(self) -> None:
        for cls in DOMAIN_EVENTS_REGISTRY.values():
            e = cls()
            assert e.event_version == 1, f"{cls.__name__}.event_version != 1"


# =========================================================================
# Event serialization
# =========================================================================
class TestEventSerialization:
    def test_all_events_produce_serializable_records(self) -> None:
        for name, cls in DOMAIN_EVENTS_REGISTRY.items():
            event = cls()
            record = event.to_event_record()
            json_str = json.dumps(record)
            assert len(json_str) > 0
            assert record["event_type"] == name

    def test_record_has_11_keys(self) -> None:
        e = DomainEvent()
        record = e.to_event_record()
        assert len(record) == 11
