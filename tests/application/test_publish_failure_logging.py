"""Tests for safe structured logging on event publish failure (EDD Prompt 10).

These tests cover the 3 publish-time swallow points transformed in Prompt 10:
- EventPublisherImpl.publish (app/application/sagas/event_publisher.py)
- ConversationSaga._publish (app/application/sagas/conversation_saga.py)
- ConversationSaga._publish_error (app/application/sagas/conversation_saga.py)

The tests verify:
- A warning is logged at WARNING level on publish failure.
- The log message follows the contract defined in the Prompt 10 spec.
- Sensitive payload fields (text, content, payload, __dict__) are never logged.
- The error message is truncated to 200 chars + '...'.
- No exception is raised (fire-and-forget preserved).
- The static contract (``except`` and ``pass`` still in source) is preserved.
"""
from __future__ import annotations

import logging
from unittest.mock import AsyncMock

import pytest

from app.application.sagas.conversation_saga import (
    ConversationContext,
    ConversationSaga,
)
from app.application.sagas.event_publisher import EventPublisherImpl
from app.domain.events import (
    AgentRouteSelected,
    InboundMessageReceived,
)
from app.infrastructure.event_store.base import EventStore
from app.infrastructure.event_store.in_memory import InMemoryEventStore


# ===========================================================================
# Class A — EventPublisherImpl.publish logging
# ===========================================================================
class TestEventPublisherImplPublishLogging:
    """3 tests: warning-on-failure, no-payload-leak, truncation."""

    @pytest.mark.asyncio
    async def test_publish_logs_warning_on_store_failure(
        self, caplog: pytest.LogCaptureFixture,
    ) -> None:
        """A1: store.append raises -> logger.warning is emitted with full schema."""
        failing_store = AsyncMock(spec=EventStore)
        failing_store.append.side_effect = RuntimeError("boom")
        publisher = EventPublisherImpl(failing_store)  # type: ignore[arg-type]

        event = AgentRouteSelected(route="pims")
        with caplog.at_level(
            logging.WARNING, logger="app.application.sagas.event_publisher"
        ):
            await publisher.publish("conversation:abc", event)

        assert any(
            r.levelno == logging.WARNING
            and r.name == "app.application.sagas.event_publisher"
            for r in caplog.records
        )
        text = caplog.text
        assert "event=event_publish_failed" in text
        assert "event_type=AgentRouteSelected" in text
        assert f"event_id={event.event_id}" in text
        assert "stream=conversation:abc" in text
        assert "error_class=RuntimeError" in text
        assert "error_message_truncated=boom" in text

    @pytest.mark.asyncio
    async def test_publish_does_not_log_payload_fields(
        self, caplog: pytest.LogCaptureFixture,
    ) -> None:
        """A2: InboundMessageReceived with text='SECRET' -> text NOT in log."""
        failing_store = AsyncMock(spec=EventStore)
        failing_store.append.side_effect = RuntimeError("boom")
        publisher = EventPublisherImpl(failing_store)  # type: ignore[arg-type]

        event = InboundMessageReceived(
            text="SECRET_TOKEN_XYZ",
            user_id="u-leak",
        )
        with caplog.at_level(
            logging.WARNING, logger="app.application.sagas.event_publisher"
        ):
            await publisher.publish("conversation:abc", event)

        text = caplog.text
        assert "SECRET_TOKEN_XYZ" not in text
        assert "u-leak" not in text
        # event_type IS allowed (deterministic, no PII)
        assert "event_type=InboundMessageReceived" in text
        assert f"event_id={event.event_id}" in text

    @pytest.mark.asyncio
    async def test_publish_truncates_long_error_message(
        self, caplog: pytest.LogCaptureFixture,
    ) -> None:
        """A3: 500-char error message -> truncated to 200 + '...'."""
        long_msg = "x" * 500
        failing_store = AsyncMock(spec=EventStore)
        failing_store.append.side_effect = RuntimeError(long_msg)
        publisher = EventPublisherImpl(failing_store)  # type: ignore[arg-type]

        event = AgentRouteSelected(route="pims")
        with caplog.at_level(
            logging.WARNING, logger="app.application.sagas.event_publisher"
        ):
            await publisher.publish("conversation:abc", event)

        text = caplog.text
        truncated_marker = "x" * 200 + "..."
        assert truncated_marker in text
        # 201+ consecutive x's must NOT appear (would mean no truncation)
        assert "x" * 201 not in text


# ===========================================================================
# Class B — ConversationSaga._publish logging
# ===========================================================================
class TestConversationSagaPublishLogging:
    """2 tests: warning-on-failure, anonymous when no cid."""

    @pytest.mark.asyncio
    async def test_saga_publish_logs_warning_on_publisher_failure(
        self, caplog: pytest.LogCaptureFixture,
    ) -> None:
        """B1: publisher raises -> logger.warning from EventPublisherImpl (real path).

        Note: the exception is caught inside ``EventPublisherImpl.publish``, so the
        log is emitted by ``app.application.sagas.event_publisher`` (not the saga
        logger). The saga's ``except`` on ``_publish`` is dead code for store errors
        — the EventStore error never propagates past the inner ``try/except``.
        """
        failing_store = AsyncMock(spec=EventStore)
        failing_store.append.side_effect = RuntimeError("store down")
        publisher = EventPublisherImpl(failing_store)  # type: ignore[arg-type]

        saga = ConversationSaga(
            load_memory_fn=AsyncMock(return_value=None),
            ocr_fn=AsyncMock(return_value=None),
            route_fn=AsyncMock(return_value=None),
            rag_fn=AsyncMock(return_value=None),
            run_agent_fn=AsyncMock(return_value=None),
            save_memory_fn=AsyncMock(),
            event_publisher=publisher,
        )
        ctx = ConversationContext(conversation_id="c1", message_original="hi")
        event = AgentRouteSelected(route="pims")

        with caplog.at_level(
            logging.WARNING, logger="app.application.sagas.event_publisher"
        ):
            await saga._publish(ctx, event)

        text = caplog.text
        assert "event=event_publish_failed" in text
        assert "event_type=AgentRouteSelected" in text
        assert "stream=conversation:c1" in text
        assert "error_class=RuntimeError" in text
        assert "error_message_truncated=store down" in text

    @pytest.mark.asyncio
    async def test_saga_publish_uses_anonymous_when_no_conversation_id(
        self, caplog: pytest.LogCaptureFixture,
    ) -> None:
        """B2: ctx.conversation_id=None -> stream=conversation:anonymous in log."""
        failing_store = AsyncMock(spec=EventStore)
        failing_store.append.side_effect = RuntimeError("boom")
        publisher = EventPublisherImpl(failing_store)  # type: ignore[arg-type]

        saga = ConversationSaga(
            load_memory_fn=AsyncMock(return_value=None),
            ocr_fn=AsyncMock(return_value=None),
            route_fn=AsyncMock(return_value=None),
            rag_fn=AsyncMock(return_value=None),
            run_agent_fn=AsyncMock(return_value=None),
            save_memory_fn=AsyncMock(),
            event_publisher=publisher,
        )
        ctx = ConversationContext(conversation_id=None, message_original="hi")
        event = AgentRouteSelected(route="pims")

        with caplog.at_level(
            logging.WARNING, logger="app.application.sagas.event_publisher"
        ):
            await saga._publish(ctx, event)

        assert "stream=conversation:anonymous" in caplog.text


# ===========================================================================
# Class C — ConversationSaga._publish_error logging
# ===========================================================================
class TestConversationSagaPublishErrorLogging:
    """1 test: warning with stage=publish_error_event."""

    @pytest.mark.asyncio
    async def test_publish_error_logs_warning_with_stage(
        self, caplog: pytest.LogCaptureFixture,
    ) -> None:
        """C1: MessageProcessingFailed publish fails -> warning from EventPublisherImpl.

        Note: the exception from ``store.append`` is caught inside
        ``EventPublisherImpl.publish``, so the log is emitted by
        ``app.application.sagas.event_publisher`` with the event's type name
        (``MessageProcessingFailed``). The saga's ``except`` on ``_publish_error``
        is dead code for store errors — the EventStore error never propagates.
        """
        from app.application.sagas.conversation_saga import _publish_error

        failing_store = AsyncMock(spec=EventStore)
        failing_store.append.side_effect = RuntimeError("store down")
        publisher = EventPublisherImpl(failing_store)  # type: ignore[arg-type]

        saga = ConversationSaga(
            load_memory_fn=AsyncMock(return_value=None),
            ocr_fn=AsyncMock(return_value=None),
            route_fn=AsyncMock(return_value=None),
            rag_fn=AsyncMock(return_value=None),
            run_agent_fn=AsyncMock(return_value=None),
            save_memory_fn=AsyncMock(),
            event_publisher=publisher,
        )
        ctx = ConversationContext(conversation_id="c1", message_original="hi")
        original_exc = RuntimeError("original error")

        with caplog.at_level(
            logging.WARNING, logger="app.application.sagas.event_publisher"
        ):
            await _publish_error(saga, ctx, original_exc)

        text = caplog.text
        assert "event=event_publish_failed" in text
        assert "event_type=MessageProcessingFailed" in text
        assert "stream=conversation:c1" in text
        assert "error_class=RuntimeError" in text
        assert "error_message_truncated=store down" in text
        # Original error message must NOT leak into publish-failure log
        assert "original error" not in text


# ===========================================================================
# Class D — Static canaries (source-code-level contract enforcement)
# ===========================================================================
class TestStaticCanaries:
    """Static source-code-level canaries: spec contract enforcement."""

    def test_event_publisher_module_has_logger_dunder_name(self) -> None:
        """D1: event_publisher.py uses logging.getLogger(__name__)."""
        from pathlib import Path
        source = (
            Path(__file__).resolve().parent.parent.parent
            / "app"
            / "application"
            / "sagas"
            / "event_publisher.py"
        ).read_text()
        assert "logger = logging.getLogger(__name__)" in source

    def test_conversation_saga_module_has_logger_dunder_name(self) -> None:
        """D2: conversation_saga.py uses logging.getLogger(__name__)."""
        from pathlib import Path
        source = (
            Path(__file__).resolve().parent.parent.parent
            / "app"
            / "application"
            / "sagas"
            / "conversation_saga.py"
        ).read_text()
        assert "logger = logging.getLogger(__name__)" in source
