"""Tests for ``app.core.runtime_publisher`` (EDD Prompt 9).

Groups:
    A — EVENT_DRIVEN_ENABLED=false (R1)
    B — backend mismatch (R2)
    C — pool is None (R3)
    D — success (R4)
    E — unexpected error (R5)
    F — static canaries (isolation)
    G — global settings fallback (S3)
"""
from __future__ import annotations

import ast
import logging
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from app.application.sagas.event_publisher import EventPublisherImpl
from app.application.sagas.event_publisher import NullEventPublisher
from app.core.runtime_publisher import (
    EVENT_CREATED_TX,
    EVENT_CREATION_FAILED,
    EVENT_DISABLED,
    EVENT_FALLBACK_NULL,
    LOG_TRUNCATE_LIMIT,
    NULL_PUBLISHER_TYPE,
    REASON_BACKEND_MISMATCH,
    REASON_POOL_MISSING,
    TRANSACTIONAL_BACKEND,
    TRANSACTIONAL_PUBLISHER_TYPE,
    TRANSACTIONAL_STORE_TYPE,
    _truncate,
    build_runtime_event_publisher,
)


# ---------------------------------------------------------------------------
# Fake Settings (mimics app.core.config.Settings shape)
# ---------------------------------------------------------------------------


class _FakeSettings:
    """Minimal Settings-shaped fake for monkeypatching app.core.runtime_publisher._global_settings."""

    def __init__(
        self,
        *,
        enabled: bool = False,
        backend: str = "memory",
        dsn: str | None = None,
    ) -> None:
        self.EVENT_DRIVEN_ENABLED = enabled
        self.EVENT_STORE_BACKEND = backend
        self.EVENT_STORE_POSTGRES_DSN = dsn


def _settings_disabled() -> _FakeSettings:
    return _FakeSettings(enabled=False)


def _settings_backend_memory() -> _FakeSettings:
    return _FakeSettings(enabled=True, backend="memory")


def _settings_backend_legacy_postgres() -> _FakeSettings:
    return _FakeSettings(enabled=True, backend="postgres")


def _settings_backend_redis_streams() -> _FakeSettings:
    return _FakeSettings(enabled=True, backend="redis_streams")


def _settings_backend_tx_with_dsn() -> _FakeSettings:
    return _FakeSettings(
        enabled=True,
        backend=TRANSACTIONAL_BACKEND,
        dsn="postgresql://user:pwd@host.example.com:5432/agent_bot_events",
    )


# ---------------------------------------------------------------------------
# Helpers for static canaries (Grupo F)
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _read_helper_source() -> str:
    source_path = _REPO_ROOT / "app" / "core" / "runtime_publisher.py"
    return source_path.read_text(encoding="utf-8")


def _parse_ast(source: str) -> ast.Module:
    return ast.parse(source)


# ---------------------------------------------------------------------------
# A — EVENT_DRIVEN_ENABLED=false (R1)
# ---------------------------------------------------------------------------


class TestGroupAFlagFalse:
    """R1: flag false → NullEventPublisher, no pool, no store."""

    def test_a1_returns_null_publisher_when_flag_false(self) -> None:
        result = build_runtime_event_publisher(
            pool=MagicMock(), settings=_settings_disabled()
        )
        assert isinstance(result, NullEventPublisher)

    def test_a2_does_not_use_pool_when_flag_false(self) -> None:
        pool = MagicMock(name="unused_pool")
        build_runtime_event_publisher(pool=pool, settings=_settings_disabled())
        # pool should not be accessed in any way
        pool.assert_not_called()

    def test_a3_does_not_create_transactional_store_when_flag_false(
        self,
    ) -> None:
        with patch(
            "app.core.runtime_publisher.TransactionalPostgresEventStore"
        ) as mock_cls:
            build_runtime_event_publisher(
                pool=MagicMock(), settings=_settings_disabled()
            )
            mock_cls.assert_not_called()

    def test_a4_does_not_create_event_publisher_impl_when_flag_false(
        self,
    ) -> None:
        with patch(
            "app.core.runtime_publisher.EventPublisherImpl"
        ) as mock_cls:
            build_runtime_event_publisher(
                pool=MagicMock(), settings=_settings_disabled()
            )
            mock_cls.assert_not_called()

    @pytest.mark.parametrize("level", [logging.INFO, logging.DEBUG])
    def test_a5_logs_disabled_when_flag_false(
        self, caplog: pytest.LogCaptureFixture, level: int
    ) -> None:
        with caplog.at_level(level, logger="app.core.runtime_publisher"):
            build_runtime_event_publisher(
                pool=MagicMock(), settings=_settings_disabled()
            )
        assert EVENT_DISABLED in caplog.text


# ---------------------------------------------------------------------------
# B — backend mismatch (R2)
# ---------------------------------------------------------------------------


class TestGroupBBackendMismatch:
    """R2: backend != transactional_postgres → NullEventPublisher."""

    @pytest.mark.parametrize(
        "settings",
        [
            _settings_backend_memory(),
            _settings_backend_legacy_postgres(),
            _settings_backend_redis_streams(),
        ],
    )
    def test_b_backend_returns_null(self, settings: _FakeSettings) -> None:
        result = build_runtime_event_publisher(
            pool=MagicMock(), settings=settings
        )
        assert isinstance(result, NullEventPublisher)

    @pytest.mark.parametrize(
        "settings_fixture,expected_backend",
        [
            (_settings_backend_memory, "memory"),
            (_settings_backend_legacy_postgres, "postgres"),
            (_settings_backend_redis_streams, "redis_streams"),
        ],
    )
    def test_b_logs_backend_mismatch(
        self,
        caplog: pytest.LogCaptureFixture,
        settings_fixture: Any,
        expected_backend: str,
    ) -> None:
        settings = settings_fixture()
        with caplog.at_level(logging.INFO, logger="app.core.runtime_publisher"):
            build_runtime_event_publisher(
                pool=MagicMock(), settings=settings
            )
        assert EVENT_FALLBACK_NULL in caplog.text
        assert REASON_BACKEND_MISMATCH in caplog.text
        assert expected_backend in caplog.text

    def test_b_does_not_create_store(self) -> None:
        with patch(
            "app.core.runtime_publisher.TransactionalPostgresEventStore"
        ) as mock_cls:
            build_runtime_event_publisher(
                pool=MagicMock(), settings=_settings_backend_memory()
            )
            mock_cls.assert_not_called()


# ---------------------------------------------------------------------------
# C — pool is None (R3)
# ---------------------------------------------------------------------------


class TestGroupCPoolMissing:
    """R3: flag true + backend ok + pool None → NullEventPublisher."""

    def test_c_pool_none_returns_null(self) -> None:
        result = build_runtime_event_publisher(
            pool=None, settings=_settings_backend_tx_with_dsn()
        )
        assert isinstance(result, NullEventPublisher)

    def test_c_logs_pool_missing(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.INFO, logger="app.core.runtime_publisher"):
            build_runtime_event_publisher(
                pool=None, settings=_settings_backend_tx_with_dsn()
            )
        assert EVENT_FALLBACK_NULL in caplog.text
        assert REASON_POOL_MISSING in caplog.text

    def test_c_does_not_create_store(self) -> None:
        with patch(
            "app.core.runtime_publisher.TransactionalPostgresEventStore"
        ) as mock_cls:
            build_runtime_event_publisher(
                pool=None, settings=_settings_backend_tx_with_dsn()
            )
            mock_cls.assert_not_called()


# ---------------------------------------------------------------------------
# D — success (R4)
# ---------------------------------------------------------------------------


class TestGroupDSuccess:
    """R4: all pre-requisites satisfied → EventPublisherImpl."""

    def test_d_returns_event_publisher_impl(self) -> None:
        pool = MagicMock(name="fake_pool")
        result = build_runtime_event_publisher(
            pool=pool, settings=_settings_backend_tx_with_dsn()
        )
        assert isinstance(result, EventPublisherImpl)

    def test_d_uses_transactional_postgres_event_store(self) -> None:
        pool = MagicMock(name="fake_pool")
        result = build_runtime_event_publisher(
            pool=pool, settings=_settings_backend_tx_with_dsn()
        )
        # EventPublisherImpl._store is the internal EventStore reference
        assert "TransactionalPostgresEventStore" in type(
            result._store
        ).__name__

    def test_d_does_not_call_pool_acquire(self) -> None:
        pool = MagicMock(name="fake_pool")
        build_runtime_event_publisher(
            pool=pool, settings=_settings_backend_tx_with_dsn()
        )
        pool.acquire.assert_not_called()

    def test_d_logs_created_transactional(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        pool = MagicMock(name="fake_pool")
        with caplog.at_level(logging.INFO, logger="app.core.runtime_publisher"):
            build_runtime_event_publisher(
                pool=pool, settings=_settings_backend_tx_with_dsn()
            )
        assert EVENT_CREATED_TX in caplog.text
        assert TRANSACTIONAL_PUBLISHER_TYPE in caplog.text
        assert TRANSACTIONAL_STORE_TYPE in caplog.text


# ---------------------------------------------------------------------------
# E — unexpected error (R5)
# ---------------------------------------------------------------------------


class TestGroupEError:
    """R5: TransactionalPostgresEventStore raises → NullEventPublisher."""

    def test_e_returns_null_on_unexpected_exception(self) -> None:
        pool = MagicMock(name="fake_pool")
        with patch(
            "app.core.runtime_publisher.TransactionalPostgresEventStore",
            side_effect=RuntimeError("boom"),
        ):
            result = build_runtime_event_publisher(
                pool=pool, settings=_settings_backend_tx_with_dsn()
            )
        assert isinstance(result, NullEventPublisher)

    def test_e_logs_creation_failed(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        pool = MagicMock(name="fake_pool")
        with patch(
            "app.core.runtime_publisher.TransactionalPostgresEventStore",
            side_effect=RuntimeError("boom"),
        ):
            with caplog.at_level(
                logging.WARNING, logger="app.core.runtime_publisher"
            ):
                build_runtime_event_publisher(
                    pool=pool, settings=_settings_backend_tx_with_dsn()
                )
        assert EVENT_CREATION_FAILED in caplog.text

    def test_e_log_does_not_contain_dsn(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        pool = MagicMock(name="fake_pool")
        with patch(
            "app.core.runtime_publisher.TransactionalPostgresEventStore",
            side_effect=RuntimeError(
                "postgresql://user:secret@pwd@host:5432/db"
            ),
        ):
            with caplog.at_level(
                logging.WARNING, logger="app.core.runtime_publisher"
            ):
                build_runtime_event_publisher(
                    pool=pool, settings=_settings_backend_tx_with_dsn()
                )
        # DSN full string should NOT appear in logs
        assert "postgresql://" not in caplog.text

    def test_e_message_truncated_to_limit_plus_ellipsis(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        pool = MagicMock(name="fake_pool")
        long_msg = "x" * (LOG_TRUNCATE_LIMIT * 2)  # 1000 chars
        with patch(
            "app.core.runtime_publisher.TransactionalPostgresEventStore",
            side_effect=RuntimeError(long_msg),
        ):
            with caplog.at_level(
                logging.WARNING, logger="app.core.runtime_publisher"
            ):
                build_runtime_event_publisher(
                    pool=pool, settings=_settings_backend_tx_with_dsn()
                )
        # Find the truncated message in the log record
        for record in caplog.records:
            msg = record.getMessage()
            if EVENT_CREATION_FAILED in msg:
                assert len(msg) <= LOG_TRUNCATE_LIMIT + len("...") + 200  # fields overhead
                break

    def test_e_exception_does_not_propagate(self) -> None:
        pool = MagicMock(name="fake_pool")
        with patch(
            "app.core.runtime_publisher.TransactionalPostgresEventStore",
            side_effect=RuntimeError("boom"),
        ):
            # Should NOT raise
            build_runtime_event_publisher(
                pool=pool, settings=_settings_backend_tx_with_dsn()
            )


# ---------------------------------------------------------------------------
# F — static canaries (isolation)
# ---------------------------------------------------------------------------


class TestGroupFStaticCanaries:
    """Source-code-level canaries: ensure helper is clean of forbidden imports."""

    SOURCE = _read_helper_source()
    TREE = _parse_ast(SOURCE)

    def _has_import(self, name: str) -> bool:
        for node in ast.walk(self.TREE):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if name in alias.name:
                        return True
            elif isinstance(node, ast.ImportFrom):
                if node.module and name in node.module:
                    return True
                for alias in node.names:
                    if name == alias.name:
                        return True
        return False

    def test_f1_does_not_import_fastapi(self) -> None:
        assert not self._has_import("fastapi"), "import fastapi found"

    def test_f2_does_not_import_app_main(self) -> None:
        assert not self._has_import("app.main"), "import app.main found"

    def test_f3_does_not_import_asyncpg(self) -> None:
        assert not self._has_import("asyncpg"), "import asyncpg found"

    def test_f4_does_not_import_inmemory_event_store(self) -> None:
        assert not self._has_import("InMemoryEventStore"), (
            "InMemoryEventStore found"
        )

    def test_f5_does_not_reference_app_state(self) -> None:
        assert "app.state" not in self.SOURCE

    def test_f6_does_not_call_pool_acquire(self) -> None:
        assert "pool.acquire" not in self.SOURCE


# ---------------------------------------------------------------------------
# G — global settings fallback (S3)
# ---------------------------------------------------------------------------


class TestGroupGGlobalSettings:
    """settings=None uses global app.core.config.settings."""

    def test_g_settings_none_uses_global(self) -> None:
        """patch _global_settings and call with settings=None."""
        import app.core.runtime_publisher as rp

        fake = _FakeSettings()
        # Will fall to R1 because enabled=False by default
        with patch.object(rp, "_global_settings", fake):
            with patch(
                "app.core.runtime_publisher.TransactionalPostgresEventStore"
            ) as mock_store:
                result = rp.build_runtime_event_publisher(
                    pool=MagicMock(), settings=None
                )
        assert isinstance(result, NullEventPublisher)
        mock_store.assert_not_called()

    def test_g_does_not_depend_on_real_env(self) -> None:
        """Test works without real env vars (does not read os.environ)."""
        import app.core.runtime_publisher as rp

        fake = _FakeSettings(enabled=False)
        with patch.object(rp, "_global_settings", fake):
            result = rp.build_runtime_event_publisher(
                pool=MagicMock(), settings=None
            )
        assert isinstance(result, NullEventPublisher)


# ---------------------------------------------------------------------------
# _truncate unit test (sanity)
# ---------------------------------------------------------------------------


class TestTruncate:
    """Direct test for _truncate helper."""

    def test_short_value_not_truncated(self) -> None:
        assert _truncate("short") == "short"

    def test_long_value_truncated_with_ellipsis(self) -> None:
        long_val = "a" * 1000
        result = _truncate(long_val, limit=500)
        assert len(result) == 500 + 3  # 500 chars + "..."
        assert result.endswith("...")

    def test_value_at_limit_not_truncated(self) -> None:
        val = "x" * 500
        assert _truncate(val, limit=500) == val
