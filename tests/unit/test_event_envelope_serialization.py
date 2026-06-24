"""Tests for event envelope serialization roundtrip."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from app.domain.events import (
    AgentRunStarted,
    ConversationMemorySaved,
    DomainEvent,
    DOMAIN_EVENTS_REGISTRY,
)
from app.domain.enums import AggregateType


# =========================================================================
# to_event_record roundtrip
# =========================================================================
class TestEventRecordRoundtrip:
    def test_base_event_roundtrip(self) -> None:
        e = DomainEvent(
            correlation_id="corr-1",
            aggregate_id="agg-1",
            aggregate_type=AggregateType.CONVERSATION.value,
        )
        record = e.to_event_record()
        # Verify all envelope fields present
        assert "event_id" in record
        assert "event_type" in record
        assert "event_version" in record
        assert "occurred_at" in record
        assert "aggregate_id" in record
        assert "aggregate_type" in record
        assert "correlation_id" in record
        assert "causation_id" in record
        assert "conversation_id" in record
        assert "payload" in record
        assert "metadata" in record

    def test_specific_event_payload_in_record(self) -> None:
        e = AgentRunStarted(
            run_id="r1",
            agent_type="pi",
            route="pims",
            message_id="msg-1",
            correlation_id="corr-1",
            metadata={"step": 2},
        )
        record = e.to_event_record()
        assert record["payload"]["run_id"] == "r1"
        assert record["payload"]["agent_type"] == "pi"
        assert record["payload"]["route"] == "pims"
        assert record["metadata"] == {"step": 2}

    def test_record_json_serializable(self) -> None:
        e = ConversationMemorySaved(
            user_turn_saved=True,
            assistant_turn_saved=False,
            total_turns=3,
            correlation_id="corr-1",
            metadata={"key": "value"},
        )
        record = e.to_event_record()
        # Should not raise
        json_str = json.dumps(record)
        parsed = json.loads(json_str)
        assert parsed["event_type"] == "ConversationMemorySaved"
        assert parsed["payload"]["user_turn_saved"] is True
        assert parsed["metadata"] == {"key": "value"}

    def test_all_events_produce_serializable_records(self) -> None:
        for name, cls in DOMAIN_EVENTS_REGISTRY.items():
            event = cls()
            record = event.to_event_record()
            # Must be JSON-serializable
            json_str = json.dumps(record)
            assert len(json_str) > 0
            # Must have event_type
            assert record["event_type"] == name

    def test_occurred_at_is_iso_format(self) -> None:
        e = DomainEvent()
        record = e.to_event_record()
        # Parse ISO format
        dt = datetime.fromisoformat(record["occurred_at"])
        assert dt.tzinfo is not None
