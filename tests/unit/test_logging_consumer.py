from __future__ import annotations

import logging
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from app.infrastructure.outbox.logging_consumer import LoggingOutboxConsumer
from app.infrastructure.outbox.outbox_dispatcher import OutboxEvent

NOW = datetime.now(timezone.utc)


def _make_event(
    *,
    outbox_id: int = 1,
    event_id: str = "e1",
    event_type: str = "TestEvent",
    stream_id: str = "s1",
    stream_version: int = 1,
    aggregate_id: str | None = None,
    event_payload: dict | None = None,
    metadata: dict | None = None,
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


class TestLoggingOutboxConsumerInit:
    def test_rejects_empty_string(self) -> None:
        with pytest.raises(ValueError, match="consumer_name"):
            LoggingOutboxConsumer("")

    def test_rejects_whitespace_only(self) -> None:
        with pytest.raises(ValueError, match="consumer_name"):
            LoggingOutboxConsumer("   ")

    def test_accepts_valid_name(self) -> None:
        c = LoggingOutboxConsumer("test-consumer")
        assert c._consumer_name == "test-consumer"


class TestLoggingOutboxConsumerHandle:
    @pytest.mark.asyncio
    async def test_handle_is_async(self) -> None:
        consumer = LoggingOutboxConsumer("test")
        event = _make_event()
        result = consumer.handle(event)
        assert hasattr(result, "__await__")

    @pytest.mark.asyncio
    async def test_handle_returns_none(self) -> None:
        consumer = LoggingOutboxConsumer("test")
        event = _make_event()
        result = await consumer.handle(event)
        assert result is None

    @pytest.mark.asyncio
    async def test_handle_calls_logger_info(self, caplog) -> None:
        consumer = LoggingOutboxConsumer("test-consumer")
        event = _make_event(
            event_id="e-123",
            event_type="TestEvent",
            stream_id="conv:abc",
            stream_version=2,
            aggregate_id="agg-01",
        )
        with caplog.at_level(logging.INFO):
            await consumer.handle(event)
        assert len(caplog.records) >= 1
        assert caplog.records[0].message == "outbox_event_handled"

    @pytest.mark.asyncio
    async def test_handle_logs_whitelisted_fields(self, caplog) -> None:
        consumer = LoggingOutboxConsumer("whitelist-test")
        event = _make_event(
            outbox_id=42,
            event_id="e-999",
            event_type="CustomEvent",
            stream_id="stream:x",
            stream_version=5,
            aggregate_id="agg-99",
        )
        with caplog.at_level(logging.INFO):
            await consumer.handle(event)
        record = caplog.records[0]
        payload = record.__dict__
        assert payload.get("consumer_name") == "whitelist-test"
        assert payload.get("outbox_id") == 42
        assert payload.get("event_id") == "e-999"
        assert payload.get("event_type") == "CustomEvent"
        assert payload.get("stream_id") == "stream:x"
        assert payload.get("stream_version") == 5
        assert payload.get("aggregate_id") == "agg-99"

    @pytest.mark.asyncio
    async def test_handle_is_idempotent(self) -> None:
        consumer = LoggingOutboxConsumer("test")
        event = _make_event()
        await consumer.handle(event)
        await consumer.handle(event)

    @pytest.mark.asyncio
    async def test_handle_does_not_log_event_payload(self, caplog) -> None:
        consumer = LoggingOutboxConsumer("pii-guard")
        secret = "msg secreta"
        event = _make_event(event_payload={"content": secret})
        with caplog.at_level(logging.INFO):
            await consumer.handle(event)
        text = " ".join(str(r.__dict__) for r in caplog.records)
        assert secret not in text

    @pytest.mark.asyncio
    async def test_handle_does_not_log_metadata(self, caplog) -> None:
        consumer = LoggingOutboxConsumer("meta-guard")
        secret = "meta-value-secreta"
        event = _make_event(metadata={"foo": secret})
        with caplog.at_level(logging.INFO):
            await consumer.handle(event)
        text = " ".join(str(r.__dict__) for r in caplog.records)
        assert secret not in text

    @pytest.mark.asyncio
    async def test_handle_propagates_logger_exception(self) -> None:
        consumer = LoggingOutboxConsumer("c1-guard")
        event = _make_event()
        with patch.object(
            logging.Logger, "info", side_effect=RuntimeError("logger boom")
        ):
            with pytest.raises(RuntimeError, match="logger boom"):
                await consumer.handle(event)
