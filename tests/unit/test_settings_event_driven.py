"""Tests for EVENT_DRIVEN_ENABLED and related Settings fields."""
from __future__ import annotations

import pytest

from app.core.config import Settings


class TestEventDrivenEnabledDefault:
    """T6: default values for new and existing fields."""

    def test_event_driven_enabled_default_is_false(self) -> None:
        s = Settings()
        assert s.EVENT_DRIVEN_ENABLED is False

    def test_event_store_postgres_dsn_still_in_settings(self) -> None:
        s = Settings()
        assert hasattr(s, "EVENT_STORE_POSTGRES_DSN")
        assert s.EVENT_STORE_POSTGRES_DSN is None

    def test_event_store_backend_legacy_default_is_memory(self) -> None:
        s = Settings()
        assert s.EVENT_STORE_BACKEND == "memory"


class TestEventDrivenEnabledParsing:
    """T6: parsing of EVENT_DRIVEN_ENABLED from env strings."""

    def test_parses_true(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("EVENT_DRIVEN_ENABLED", "true")
        s = Settings()
        assert s.EVENT_DRIVEN_ENABLED is True

    def test_parses_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("EVENT_DRIVEN_ENABLED", "false")
        s = Settings()
        assert s.EVENT_DRIVEN_ENABLED is False
