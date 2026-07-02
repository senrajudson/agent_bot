"""Tests for /chat wiring of build_runtime_event_publisher (EDD Prompt 11).

Scenarios:
    1. EVENT_DRIVEN_ENABLED=false          → NullEventPublisher (R1)
    2. flag=true, pool present              → EventPublisherImpl (R4)
    3. flag=true, pool absent               → NullEventPublisher (R3)
    4. TransactionalPostgresEventStore raises → NullEventPublisher (R5)
    5. backend mismatch                     → NullEventPublisher (R2)
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.application.sagas.event_publisher import (
    EventPublisherImpl,
    NullEventPublisher,
)


class TestChatWiringFlagFalse:
    """Scenario 1: EVENT_DRIVEN_ENABLED=false → NullEventPublisher (R1)."""

    def test_chat_uses_null_publisher_when_flag_false(
        self,
        app_client,
        chat_payload_text,
        mock_route_general,
        mock_general_agent,
        mock_ocr_no_images,
        mock_redis,
    ):
        captured: dict = {}

        from app.main import build_runtime_event_publisher as real_fn

        def spy(pool, settings=None):
            result = real_fn(pool, settings)
            captured["publisher"] = result
            return result

        with patch("app.main.build_runtime_event_publisher", spy):
            response = app_client.post("/chat", json=chat_payload_text.model_dump())

        assert response.status_code == 200
        assert isinstance(captured.get("publisher"), NullEventPublisher)


class TestChatWiringFlagTrueWithPool:
    """Scenario 2: EVENT_DRIVEN_ENABLED=true + pool → EventPublisherImpl (R4)."""

    def test_chat_uses_event_publisher_impl_with_pool(
        self,
        app_client,
        chat_payload_text,
        mock_route_general,
        mock_general_agent,
        mock_ocr_no_images,
        mock_redis,
        monkeypatch,
    ):
        fake_pool = MagicMock(name="fake_pool")
        captured: dict = {}

        monkeypatch.setattr("app.core.config.settings.EVENT_DRIVEN_ENABLED", True)
        monkeypatch.setattr(
            "app.core.config.settings.EVENT_STORE_BACKEND",
            "transactional_postgres",
        )

        from app.main import build_runtime_event_publisher as real_fn

        def spy(pool, settings=None):
            result = real_fn(pool, settings)
            captured["publisher"] = result
            return result

        app_client.app.state.postgres_pool = fake_pool
        try:
            with patch("app.main.build_runtime_event_publisher", spy):
                response = app_client.post(
                    "/chat", json=chat_payload_text.model_dump()
                )
        finally:
            del app_client.app.state.postgres_pool

        assert response.status_code == 200
        publisher = captured.get("publisher")
        assert isinstance(publisher, EventPublisherImpl), (
            f"expected EventPublisherImpl, got {type(publisher).__name__}"
        )


class TestChatWiringFlagTruePoolMissing:
    """Scenario 3: EVENT_DRIVEN_ENABLED=true, pool None → NullEventPublisher (R3)."""

    def test_chat_uses_null_publisher_when_pool_missing(
        self,
        app_client,
        chat_payload_text,
        mock_route_general,
        mock_general_agent,
        mock_ocr_no_images,
        mock_redis,
        monkeypatch,
    ):
        captured: dict = {}

        monkeypatch.setattr("app.core.config.settings.EVENT_DRIVEN_ENABLED", True)
        monkeypatch.setattr(
            "app.core.config.settings.EVENT_STORE_BACKEND",
            "transactional_postgres",
        )

        from app.main import build_runtime_event_publisher as real_fn

        def spy(pool, settings=None):
            result = real_fn(pool, settings)
            captured["publisher"] = result
            return result

        with patch("app.main.build_runtime_event_publisher", spy):
            response = app_client.post(
                "/chat", json=chat_payload_text.model_dump()
            )

        assert response.status_code == 200
        assert isinstance(captured.get("publisher"), NullEventPublisher)


class TestChatWiringConstructionError:
    """Scenario 4: TransactionalPostgresEventStore raises → NullEventPublisher (R5)."""

    def test_chat_uses_null_publisher_on_construction_error(
        self,
        app_client,
        chat_payload_text,
        mock_route_general,
        mock_general_agent,
        mock_ocr_no_images,
        mock_redis,
        monkeypatch,
    ):
        fake_pool = MagicMock(name="fake_pool")
        captured: dict = {}

        monkeypatch.setattr("app.core.config.settings.EVENT_DRIVEN_ENABLED", True)
        monkeypatch.setattr(
            "app.core.config.settings.EVENT_STORE_BACKEND",
            "transactional_postgres",
        )

        from app.main import build_runtime_event_publisher as real_fn

        def spy(pool, settings=None):
            result = real_fn(pool, settings)
            captured["publisher"] = result
            return result

        app_client.app.state.postgres_pool = fake_pool
        try:
            with patch("app.main.build_runtime_event_publisher", spy):
                with patch(
                    "app.core.runtime_publisher.TransactionalPostgresEventStore",
                    side_effect=RuntimeError("boom"),
                ):
                    response = app_client.post(
                        "/chat", json=chat_payload_text.model_dump()
                    )
        finally:
            del app_client.app.state.postgres_pool

        assert response.status_code == 200
        assert isinstance(captured.get("publisher"), NullEventPublisher)


class TestChatWiringBackendMismatch:
    """Scenario 5: backend mismatch → NullEventPublisher (R2)."""

    def test_chat_uses_null_publisher_on_backend_mismatch(
        self,
        app_client,
        chat_payload_text,
        mock_route_general,
        mock_general_agent,
        mock_ocr_no_images,
        mock_redis,
        monkeypatch,
    ):
        captured: dict = {}

        monkeypatch.setattr("app.core.config.settings.EVENT_DRIVEN_ENABLED", True)
        # Keep EVENT_STORE_BACKEND as "memory" (default) → R2

        from app.main import build_runtime_event_publisher as real_fn

        def spy(pool, settings=None):
            result = real_fn(pool, settings)
            captured["publisher"] = result
            return result

        with patch("app.main.build_runtime_event_publisher", spy):
            response = app_client.post(
                "/chat", json=chat_payload_text.model_dump()
            )

        assert response.status_code == 200
        assert isinstance(captured.get("publisher"), NullEventPublisher)
