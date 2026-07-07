"""Test that LoggingOutboxConsumer does not log event_payload contents."""
from __future__ import annotations

import logging

import pytest

from app.infrastructure.outbox.logging_consumer import LoggingOutboxConsumer
from app.infrastructure.outbox.outbox_dispatcher import OutboxEvent

USER_SECRET_SENTINEL = "USER_SECRET_SENTINEL_DO_NOT_LEAK"
ASSISTANT_SECRET_SENTINEL = "ASSISTANT_SECRET_SENTINEL_DO_NOT_LEAK"


def _make_event_with_sensitive_payload() -> OutboxEvent:
    return OutboxEvent(
        outbox_id=1,
        event_id="evt-cms-leak-1",
        stream_id="conversation:user-leak-1",
        stream_version=1,
        aggregate_id="user-leak-1",
        event_type="ConversationMemorySaveRequested",
        event_payload={
            "user_message": USER_SECRET_SENTINEL,
            "assistant_message": ASSISTANT_SECRET_SENTINEL,
            "conversation_id": "user-leak-1",
        },
        status="locked",
        attempts=0,
        max_attempts=3,
        available_at="2026-01-01T00:00:00+00:00",
        locked_by="w-leak-1",
        locked_until="2026-01-01T00:00:30+00:00",
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",
        correlation_id=None,
        causation_id=None,
        metadata=None,
    )


class TestLoggingConsumerDoesNotLogPayload:
    async def test_consumer_does_not_log_event_payload(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(
            logging.INFO,
            logger="app.infrastructure.outbox.logging_consumer",
        )
        consumer = LoggingOutboxConsumer(consumer_name="test-cms-no-leak")
        event = _make_event_with_sensitive_payload()
        await consumer.handle(event)
        log_text = caplog.text
        assert USER_SECRET_SENTINEL not in log_text
        assert ASSISTANT_SECRET_SENTINEL not in log_text
        assert "user_message" not in log_text
        assert "assistant_message" not in log_text
        assert "event_payload" not in log_text
        assert "outbox_event_handled" in log_text
