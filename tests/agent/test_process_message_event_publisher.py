"""Tests for process_message event_publisher injection (EDD Prompt 11).

Scenarios:
    A. process_message(payload) without event_publisher → NullEventPublisher default
    B. process_message(payload, event_publisher=fake)  → publisher injected into saga
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.application.sagas.event_publisher import NullEventPublisher
from app.infrastructure.event_store import EventPublisher
from app.schemas.chat import ChatRequest


class TestProcessMessageDefault:
    """Scenario A: default is NullEventPublisher."""

    @pytest.mark.asyncio
    async def test_default_uses_null_publisher(
        self,
        simple_text_request,
        mock_redis,
        mock_route_general,
        mock_general_agent,
        mock_ocr_no_images,
    ):
        from app.agent.orchestrator import _build_saga, process_message

        captured: dict = {}

        original = _build_saga

        def spy(event_publisher=None, event_store=None):
            captured["event_publisher"] = event_publisher
            return original(event_publisher=event_publisher, event_store=event_store)

        with patch("app.agent.orchestrator._build_saga", spy):
            response = await process_message(simple_text_request)

        assert response.ok is True
        publisher = captured.get("event_publisher")
        assert publisher is None or isinstance(publisher, NullEventPublisher), (
            f"expected NullEventPublisher, got {type(publisher).__name__}"
        )


class TestProcessMessageInjected:
    """Scenario B: injected publisher reaches saga."""

    @pytest.mark.asyncio
    async def test_injected_publisher_reaches_saga(
        self,
        simple_text_request,
        mock_redis,
        mock_route_general,
        mock_general_agent,
        mock_ocr_no_images,
    ):
        from app.agent.orchestrator import _build_saga, process_message

        fake_publisher = MagicMock(spec=EventPublisher)
        captured: dict = {}

        original = _build_saga

        def spy(event_publisher=None, event_store=None):
            captured["event_publisher"] = event_publisher
            return original(event_publisher=event_publisher, event_store=event_store)

        with patch("app.agent.orchestrator._build_saga", spy):
            response = await process_message(
                simple_text_request,
                event_publisher=fake_publisher,
            )

        assert response.ok is True
        assert captured.get("event_publisher") is fake_publisher
