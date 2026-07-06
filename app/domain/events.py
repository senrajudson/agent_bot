"""Domain Events — immutable records of things that happened.

Each event represents a fact about the system that already occurred.
Events are frozen dataclasses with event_id (UUID), occurred_at (UTC),
and conversation_id (for stream partitioning).

24 events covering the full /chat lifecycle + EDD outbox.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
import uuid


def _new_id() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


# Public aliases (used by tests and external code)
new_event_id = _new_id
now_utc = _now


def event_type_from_class(cls: type) -> str:
    """Return the stable event_type name for a class."""
    return cls.__name__


# ---------------------------------------------------------------------------
# Base Event
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DomainEvent:
    """Base class for all domain events — 11-field envelope."""

    event_id: str = field(default_factory=_new_id)
    event_type: str = ""
    event_version: int = 1
    occurred_at: datetime = field(default_factory=_now)
    aggregate_id: str | None = None
    aggregate_type: str | None = None
    correlation_id: str | None = None
    causation_id: str | None = None
    conversation_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.event_type:
            object.__setattr__(self, "event_type", event_type_from_class(type(self)))

    # -- Compatibility properties ---------------------------------------------

    @property
    def payload(self) -> dict[str, Any]:
        """Specific event payload (excludes envelope fields)."""
        envelope_fields = {
            "event_id", "event_type", "event_version", "occurred_at",
            "aggregate_id", "aggregate_type", "correlation_id",
            "causation_id", "conversation_id", "metadata",
        }
        return {k: v for k, v in self.__dict__.items() if k not in envelope_fields}

    # -- Serialization --------------------------------------------------------

    def to_event_record(self) -> dict[str, Any]:
        """Full envelope record (Prompt 1.6)."""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "event_version": self.event_version,
            "occurred_at": self.occurred_at.isoformat(),
            "aggregate_id": self.aggregate_id,
            "aggregate_type": self.aggregate_type,
            "correlation_id": self.correlation_id,
            "causation_id": self.causation_id,
            "conversation_id": self.conversation_id,
            "payload": self.payload,
            "metadata": self.metadata,
        }

    def to_dict(self) -> dict[str, Any]:
        """Legacy flat format used by RedisStreamsEventStore and existing tests."""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "occurred_at": self.occurred_at.isoformat(),
            "conversation_id": self.conversation_id,
            "correlation_id": self.correlation_id,
            **self._payload(),
        }

    def _payload(self) -> dict[str, Any]:
        """Legacy: override in subclasses to add specific fields."""
        return {}


# ---------------------------------------------------------------------------
# 23 Domain Events
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class InboundMessageReceived(DomainEvent):
    message_id: str = ""
    user_id: str | None = None
    text: str = ""
    has_images: bool = False
    image_count: int = 0

    def _payload(self) -> dict[str, Any]:
        return {"message_id": self.message_id, "user_id": self.user_id, "text": self.text, "has_images": self.has_images, "image_count": self.image_count}


@dataclass(frozen=True)
class OcrExtractionCompleted(DomainEvent):
    message_id: str = ""
    image_count: int = 0
    tags_found: list[str] = field(default_factory=list)
    total_text_length: int = 0

    def _payload(self) -> dict[str, Any]:
        return {"message_id": self.message_id, "image_count": self.image_count, "tags_found": self.tags_found, "total_text_length": self.total_text_length}


@dataclass(frozen=True)
class ConversationMemoryLoaded(DomainEvent):
    turns_count: int = 0
    max_turns: int = 0

    def _payload(self) -> dict[str, Any]:
        return {"turns_count": self.turns_count, "max_turns": self.max_turns}


@dataclass(frozen=True)
class AgentRouteSelected(DomainEvent):
    message_id: str = ""
    route: str = ""
    latency_ms: int = 0

    def _payload(self) -> dict[str, Any]:
        return {"message_id": self.message_id, "route": self.route, "latency_ms": self.latency_ms}


@dataclass(frozen=True)
class RagContextRetrieved(DomainEvent):
    message_id: str = ""
    query_length: int = 0
    chunks_retrieved: int = 0
    fixed_chunk_included: bool = False

    def _payload(self) -> dict[str, Any]:
        return {"message_id": self.message_id, "query_length": self.query_length, "chunks_retrieved": self.chunks_retrieved, "fixed_chunk_included": self.fixed_chunk_included}


@dataclass(frozen=True)
class AgentRunStarted(DomainEvent):
    run_id: str = ""
    agent_type: str = ""
    route: str = ""
    message_id: str = ""

    def _payload(self) -> dict[str, Any]:
        return {"run_id": self.run_id, "agent_type": self.agent_type, "route": self.route, "message_id": self.message_id}


@dataclass(frozen=True)
class AgentToolInvocationRequested(DomainEvent):
    run_id: str = ""
    tool_name: str = ""
    args_keys: list[str] = field(default_factory=list)

    def _payload(self) -> dict[str, Any]:
        return {"run_id": self.run_id, "tool_name": self.tool_name, "args_keys": self.args_keys}


@dataclass(frozen=True)
class AgentToolInvocationCompleted(DomainEvent):
    run_id: str = ""
    tool_name: str = ""
    success: bool = True
    latency_ms: int = 0
    response_size: int = 0

    def _payload(self) -> dict[str, Any]:
        return {"run_id": self.run_id, "tool_name": self.tool_name, "success": self.success, "latency_ms": self.latency_ms, "response_size": self.response_size}


@dataclass(frozen=True)
class AgentRunCompleted(DomainEvent):
    run_id: str = ""
    output_length: int = 0
    total_tool_calls: int = 0
    total_steps: int = 0

    def _payload(self) -> dict[str, Any]:
        return {"run_id": self.run_id, "output_length": self.output_length, "total_tool_calls": self.total_tool_calls, "total_steps": self.total_steps}


@dataclass(frozen=True)
class AgentRunAborted(DomainEvent):
    run_id: str = ""
    reason: str = ""
    step_count: int = 0

    def _payload(self) -> dict[str, Any]:
        return {"run_id": self.run_id, "reason": self.reason, "step_count": self.step_count}


@dataclass(frozen=True)
class PiTagQueried(DomainEvent):
    tag: str = ""
    web_id: str = ""
    point_type: str = ""
    eng_unit: str = ""
    has_value: bool = False

    def _payload(self) -> dict[str, Any]:
        return {"tag": self.tag, "web_id": self.web_id, "point_type": self.point_type, "eng_unit": self.eng_unit, "has_value": self.has_value}


@dataclass(frozen=True)
class PiHistoricalSeriesRetrieved(DomainEvent):
    tag: str = ""
    method: str = ""
    points_count: int = 0
    time_window_start: str = ""
    time_window_end: str = ""

    def _payload(self) -> dict[str, Any]:
        return {"tag": self.tag, "method": self.method, "points_count": self.points_count, "time_window_start": self.time_window_start, "time_window_end": self.time_window_end}


@dataclass(frozen=True)
class StatisticsComputed(DomainEvent):
    tag: str = ""
    operation: str = ""
    result_value: float | None = None
    latency_ms: int = 0

    def _payload(self) -> dict[str, Any]:
        return {"tag": self.tag, "operation": self.operation, "result_value": self.result_value, "latency_ms": self.latency_ms}


@dataclass(frozen=True)
class CalculusComputed(DomainEvent):
    tag: str = ""
    operation: str = ""
    time_unit: str = ""
    result_value: float | None = None
    latency_ms: int = 0

    def _payload(self) -> dict[str, Any]:
        return {"tag": self.tag, "operation": self.operation, "time_unit": self.time_unit, "result_value": self.result_value, "latency_ms": self.latency_ms}


@dataclass(frozen=True)
class PimsStatusChecked(DomainEvent):
    total_logs: int = 0
    errors_count: int = 0
    warnings_count: int = 0
    lookback_minutes: int = 0

    def _payload(self) -> dict[str, Any]:
        return {"total_logs": self.total_logs, "errors_count": self.errors_count, "warnings_count": self.warnings_count, "lookback_minutes": self.lookback_minutes}


@dataclass(frozen=True)
class OutboundReplyGenerated(DomainEvent):
    message_id: str = ""
    output_length: int = 0
    route: str = ""

    def _payload(self) -> dict[str, Any]:
        return {"message_id": self.message_id, "output_length": self.output_length, "route": self.route}


@dataclass(frozen=True)
class ConversationMemorySaved(DomainEvent):
    user_turn_saved: bool = False
    assistant_turn_saved: bool = False
    total_turns: int = 0

    def _payload(self) -> dict[str, Any]:
        return {"user_turn_saved": self.user_turn_saved, "assistant_turn_saved": self.assistant_turn_saved, "total_turns": self.total_turns}


@dataclass(frozen=True)
class GoogleChatEventReceived(DomainEvent):
    external_event_id: str = ""
    space: str = ""
    has_attachments: bool = False

    def _payload(self) -> dict[str, Any]:
        return {"external_event_id": self.external_event_id, "space": self.space, "has_attachments": self.has_attachments}


@dataclass(frozen=True)
class GoogleChatDedupeStarted(DomainEvent):
    external_event_id: str = ""
    ttl_seconds: int = 0

    def _payload(self) -> dict[str, Any]:
        return {"external_event_id": self.external_event_id, "ttl_seconds": self.ttl_seconds}


@dataclass(frozen=True)
class GoogleChatReplySent(DomainEvent):
    external_event_id: str = ""
    space: str = ""
    latency_ms: int = 0

    def _payload(self) -> dict[str, Any]:
        return {"external_event_id": self.external_event_id, "space": self.space, "latency_ms": self.latency_ms}


@dataclass(frozen=True)
class GoogleChatDedupeCompleted(DomainEvent):
    external_event_id: str = ""
    duration_ms: int = 0

    def _payload(self) -> dict[str, Any]:
        return {"external_event_id": self.external_event_id, "duration_ms": self.duration_ms}


@dataclass(frozen=True)
class MessageProcessingFailed(DomainEvent):
    message_id: str = ""
    error_class: str = ""
    error_message: str = ""
    stage: str = ""

    def _payload(self) -> dict[str, Any]:
        return {"message_id": self.message_id, "error_class": self.error_class, "error_message": self.error_message, "stage": self.stage}


@dataclass(frozen=True)
class GoogleChatAttachmentDownloaded(DomainEvent):
    external_event_id: str = ""
    attachment_name: str = ""
    mime_type: str = ""
    size_bytes: int = 0

    def _payload(self) -> dict[str, Any]:
        return {"external_event_id": self.external_event_id, "attachment_name": self.attachment_name, "mime_type": self.mime_type, "size_bytes": self.size_bytes}


@dataclass(frozen=True)
class ConversationMemorySaveRequested(DomainEvent):
    """Event: a request to persist a conversation turn via the outbox.

    'conversation_id' and 'metadata' are inherited from DomainEvent envelope.
    """

    user_id: str | None = None
    user_message: str = ""
    assistant_message: str = ""

    def _payload(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "user_message": self.user_message,
            "assistant_message": self.assistant_message,
        }


# ---------------------------------------------------------------------------
# Event registry for deserialization
# ---------------------------------------------------------------------------

DOMAIN_EVENTS_REGISTRY: dict[str, type[DomainEvent]] = {
    cls.__name__: cls for cls in [
        InboundMessageReceived,
        OcrExtractionCompleted,
        ConversationMemoryLoaded,
        AgentRouteSelected,
        RagContextRetrieved,
        AgentRunStarted,
        AgentToolInvocationRequested,
        AgentToolInvocationCompleted,
        AgentRunCompleted,
        AgentRunAborted,
        PiTagQueried,
        PiHistoricalSeriesRetrieved,
        StatisticsComputed,
        CalculusComputed,
        PimsStatusChecked,
        OutboundReplyGenerated,
        ConversationMemorySaved,
        GoogleChatEventReceived,
        GoogleChatDedupeStarted,
        GoogleChatReplySent,
        GoogleChatDedupeCompleted,
        MessageProcessingFailed,
        GoogleChatAttachmentDownloaded,
        ConversationMemorySaveRequested,
    ]
}
