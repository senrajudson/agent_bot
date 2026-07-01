"""Tests for event_driven_lifespan — groups A, B, C (gate paths)."""
from __future__ import annotations

import asyncio
import inspect
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI

from app.core.lifespan import (
    EVENT_DRIVEN_BACKEND,
    build_event_store_pool_kwargs,
    event_driven_lifespan,
)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeSettings:
    """Minimal Settings-shaped fake for monkeypatching app.core.lifespan.settings."""

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


class _FakePool:
    """Minimal asyncpg.Pool fake with async close()."""

    def __init__(self) -> None:
        self.closed = False
        self.close_calls = 0

    async def close(self) -> None:
        self.close_calls += 1
        self.closed = True


@asynccontextmanager
async def _drive_lifespan(
    settings: _FakeSettings,
    create_pool_mock: Any,
):
    """Run the lifespan once; yield nothing to the caller.

    Yields (app, pool_mock_calls, create_pool_mock) after the lifespan enters
    but before the teardown runs.  Caller finishes the block to trigger
    teardown.
    """
    app = FastAPI()
    with patch("app.core.lifespan.settings", settings):
        with patch("app.core.lifespan.asyncpg.create_pool", create_pool_mock):
            async with event_driven_lifespan(app):
                yield app


# ---------------------------------------------------------------------------
# Group A — EVENT_DRIVEN_ENABLED = False (no-op)
# ---------------------------------------------------------------------------


class TestGroupAFlagFalseNoOp:
    """G0: flag false → no-op, no pool, no DSN required."""

    async def test_a1_does_not_call_create_pool(self) -> None:
        settings = _FakeSettings(enabled=False)
        create_pool = MagicMock(side_effect=AssertionError("create_pool called"))
        async with _drive_lifespan(settings, create_pool) as app:
            assert not hasattr(app.state, "postgres_pool")
        create_pool.assert_not_called()

    async def test_a2_flag_false_skips_dsn_missing(self) -> None:
        settings = _FakeSettings(enabled=False, backend="memory", dsn=None)
        create_pool = MagicMock(side_effect=AssertionError("create_pool called"))
        async with _drive_lifespan(settings, create_pool) as _:
            pass  # no exception

    async def test_a3_flag_false_accepts_any_backend(self) -> None:
        for backend in ("memory", "postgres", "redis_streams", "unknown_xyz"):
            settings = _FakeSettings(enabled=False, backend=backend)
            create_pool = MagicMock(side_effect=AssertionError("create_pool called"))
            async with _drive_lifespan(settings, create_pool) as _:
                pass


# ---------------------------------------------------------------------------
# Group B — flag true + wrong backend (fail-fast)
# ---------------------------------------------------------------------------


class TestGroupBFlagTrueWrongBackend:
    """G1: flag true + backend != transactional_postgres → ValueError."""

    @pytest.mark.parametrize("backend", ["memory", "postgres", "redis_streams"])
    async def test_b_flag_true_wrong_backend_raises_value_error(self, backend: str) -> None:
        settings = _FakeSettings(
            enabled=True,
            backend=backend,
            dsn="postgresql://u:p@h:5432/d",
        )
        create_pool = MagicMock(side_effect=AssertionError("create_pool called"))
        app = FastAPI()
        with patch("app.core.lifespan.settings", settings):
            with patch("app.core.lifespan.asyncpg.create_pool", create_pool):
                with pytest.raises(ValueError) as exc_info:
                    async with event_driven_lifespan(app):
                        pass
        assert EVENT_DRIVEN_BACKEND in str(exc_info.value)
        assert backend in str(exc_info.value)
        create_pool.assert_not_called()


# ---------------------------------------------------------------------------
# Group C — flag true + correct backend + DSN missing (fail-fast)
# ---------------------------------------------------------------------------


class TestGroupCFlagTrueDsnMissing:
    """G2: flag true + correct backend + DSN None/empty → ValueError."""

    @pytest.mark.parametrize("dsn", [None, ""])
    async def test_c_flag_true_dsn_missing_raises_value_error(self, dsn: str | None) -> None:
        settings = _FakeSettings(
            enabled=True,
            backend=EVENT_DRIVEN_BACKEND,
            dsn=dsn,
        )
        create_pool = MagicMock(side_effect=AssertionError("create_pool called"))
        app = FastAPI()
        with patch("app.core.lifespan.settings", settings):
            with patch("app.core.lifespan.asyncpg.create_pool", create_pool):
                with pytest.raises(ValueError) as exc_info:
                    async with event_driven_lifespan(app):
                        pass
        assert "DSN" in str(exc_info.value) or "POSTGRES" in str(exc_info.value)
        create_pool.assert_not_called()


# ---------------------------------------------------------------------------
# Sanity: ensure no test file imports app.main or conversation_saga
# (canary mirrors T10 in test_factory_event_store.py)
# ---------------------------------------------------------------------------


def test_test_file_does_not_import_app_main() -> None:
    """This test file must not import app.main."""
    import ast
    path = inspect.getfile(_drive_lifespan)
    # Walk the current test file
    test_path = __file__
    with open(test_path, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name != "app.main", f"prohibited import: {alias.name}"
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.module.startswith("app.main"):
                assert False, f"prohibited import from: {node.module}"


# ---------------------------------------------------------------------------
# Group D — Success (G3)
# ---------------------------------------------------------------------------


class TestGroupDSuccessG3:
    """G3: flag true + correct backend + DSN present → pool created, closed."""

    async def test_d1_create_pool_called_with_dsn_and_kwargs(self) -> None:
        settings = _FakeSettings(
            enabled=True,
            backend=EVENT_DRIVEN_BACKEND,
            dsn="postgresql://u:p@h.example.com:5432/d",
        )
        pool = _FakePool()
        captured: dict[str, Any] = {}

        async def fake_create_pool(dsn, **kwargs):
            captured["dsn"] = dsn
            captured["kwargs"] = kwargs
            return pool

        app = FastAPI()
        with patch("app.core.lifespan.settings", settings):
            with patch("app.core.lifespan.asyncpg.create_pool", fake_create_pool):
                async with event_driven_lifespan(app):
                    pass

        assert captured["dsn"] == "postgresql://u:p@h.example.com:5432/d"
        assert captured["kwargs"] == {
            "min_size": 1,
            "max_size": 4,
            "command_timeout": 30,
        }
        assert pool.close_calls == 1

    async def test_d2_pool_stored_in_app_state(self) -> None:
        settings = _FakeSettings(
            enabled=True,
            backend=EVENT_DRIVEN_BACKEND,
            dsn="postgresql://u:p@h:5432/d",
        )
        pool = _FakePool()

        async def fake_create_pool(dsn, **kwargs):
            return pool

        app = FastAPI()
        with patch("app.core.lifespan.settings", settings):
            with patch("app.core.lifespan.asyncpg.create_pool", fake_create_pool):
                async with event_driven_lifespan(app):
                    assert app.state.postgres_pool is pool

    async def test_d3_kwargs_contain_expected_values(self) -> None:
        settings = _FakeSettings(
            enabled=True,
            backend=EVENT_DRIVEN_BACKEND,
            dsn="postgresql://u:p@h:5432/d",
        )
        pool = _FakePool()
        captured: dict[str, Any] = {}

        async def fake_create_pool(dsn, **kwargs):
            captured.update(kwargs)
            return pool

        app = FastAPI()
        with patch("app.core.lifespan.settings", settings):
            with patch("app.core.lifespan.asyncpg.create_pool", fake_create_pool):
                async with event_driven_lifespan(app):
                    pass

        assert captured["min_size"] == 1
        assert captured["max_size"] == 4
        assert captured["command_timeout"] == 30

    async def test_d4_pool_closed_on_teardown(self) -> None:
        settings = _FakeSettings(
            enabled=True,
            backend=EVENT_DRIVEN_BACKEND,
            dsn="postgresql://u:p@h:5432/d",
        )
        pool = _FakePool()

        async def fake_create_pool(dsn, **kwargs):
            return pool

        app = FastAPI()
        with patch("app.core.lifespan.settings", settings):
            with patch("app.core.lifespan.asyncpg.create_pool", fake_create_pool):
                async with event_driven_lifespan(app):
                    assert pool.close_calls == 0
                # After teardown
                assert pool.close_calls == 1

    async def test_d5_create_pool_called_exactly_once(self) -> None:
        settings = _FakeSettings(
            enabled=True,
            backend=EVENT_DRIVEN_BACKEND,
            dsn="postgresql://u:p@h:5432/d",
        )
        pool = _FakePool()
        create_pool = AsyncMock(return_value=pool)

        app = FastAPI()
        with patch("app.core.lifespan.settings", settings):
            with patch("app.core.lifespan.asyncpg.create_pool", create_pool):
                async with event_driven_lifespan(app):
                    pass

        assert create_pool.call_count == 1


# ---------------------------------------------------------------------------
# Group E — create_pool failure
# ---------------------------------------------------------------------------


class TestGroupEStartupFailure:
    """create_pool raises → original exception propagates, log is safe."""

    async def test_e1_generic_exception_propagates(self) -> None:
        settings = _FakeSettings(
            enabled=True,
            backend=EVENT_DRIVEN_BACKEND,
            dsn="postgresql://u:p@h:5432/d",
        )

        async def fake_create_pool(dsn, **kwargs):
            raise RuntimeError("boom")

        app = FastAPI()
        with patch("app.core.lifespan.settings", settings):
            with patch("app.core.lifespan.asyncpg.create_pool", fake_create_pool):
                with pytest.raises(RuntimeError, match="boom"):
                    async with event_driven_lifespan(app):
                        pass

    async def test_e2_oserror_propagates(self) -> None:
        settings = _FakeSettings(
            enabled=True,
            backend=EVENT_DRIVEN_BACKEND,
            dsn="postgresql://u:p@h:5432/d",
        )

        async def fake_create_pool(dsn, **kwargs):
            raise OSError("Connection refused")

        app = FastAPI()
        with patch("app.core.lifespan.settings", settings):
            with patch("app.core.lifespan.asyncpg.create_pool", fake_create_pool):
                with pytest.raises(OSError, match="Connection refused"):
                    async with event_driven_lifespan(app):
                        pass

    async def test_e3_dsn_not_in_logs_on_failure(self, caplog) -> None:
        import logging
        settings = _FakeSettings(
            enabled=True,
            backend=EVENT_DRIVEN_BACKEND,
            dsn="postgresql://super_secret_user:super_secret_pwd@h:5432/d",
        )

        async def fake_create_pool(dsn, **kwargs):
            raise RuntimeError("boom")

        app = FastAPI()
        with patch("app.core.lifespan.settings", settings):
            with patch("app.core.lifespan.asyncpg.create_pool", fake_create_pool):
                with caplog.at_level(logging.DEBUG, logger="app.core.lifespan"):
                    with pytest.raises(RuntimeError):
                        async with event_driven_lifespan(app):
                            pass

        log_text = caplog.text
        assert "postgresql://" not in log_text
        assert "super_secret_user" not in log_text
        assert "super_secret_pwd" not in log_text

    async def test_e4_pool_not_stored_on_failure(self) -> None:
        settings = _FakeSettings(
            enabled=True,
            backend=EVENT_DRIVEN_BACKEND,
            dsn="postgresql://u:p@h:5432/d",
        )

        async def fake_create_pool(dsn, **kwargs):
            raise RuntimeError("boom")

        app = FastAPI()
        with patch("app.core.lifespan.settings", settings):
            with patch("app.core.lifespan.asyncpg.create_pool", fake_create_pool):
                with pytest.raises(RuntimeError):
                    async with event_driven_lifespan(app):
                        pass

        assert not hasattr(app.state, "postgres_pool")


# ---------------------------------------------------------------------------
# Group F — pool.close() failure (log-only, no re-raise)
# ---------------------------------------------------------------------------


class TestGroupFCloseFailure:
    """pool.close() raises → logged, NOT propagated."""

    async def test_f1_close_failure_logged_not_propagated(self, caplog) -> None:
        import logging
        settings = _FakeSettings(
            enabled=True,
            backend=EVENT_DRIVEN_BACKEND,
            dsn="postgresql://u:p@h:5432/d",
        )

        class _ExplodingPool:
            async def close(self):
                raise RuntimeError("close boom")

        async def fake_create_pool(dsn, **kwargs):
            return _ExplodingPool()

        app = FastAPI()
        with patch("app.core.lifespan.settings", settings):
            with patch("app.core.lifespan.asyncpg.create_pool", fake_create_pool):
                with caplog.at_level(logging.DEBUG, logger="app.core.lifespan"):
                    # The body runs, then close fails — should NOT propagate
                    async with event_driven_lifespan(app):
                        pass

        log_text = caplog.text
        assert "pool close failed" in log_text
        assert "close boom" in log_text

    async def test_f2_dsn_not_in_close_failure_logs(self, caplog) -> None:
        import logging
        settings = _FakeSettings(
            enabled=True,
            backend=EVENT_DRIVEN_BACKEND,
            dsn="postgresql://super_secret_user:super_secret_pwd@h:5432/d",
        )

        class _ExplodingPool:
            async def close(self):
                raise RuntimeError("close boom with secret super_secret_pwd marker")

        async def fake_create_pool(dsn, **kwargs):
            return _ExplodingPool()

        app = FastAPI()
        with patch("app.core.lifespan.settings", settings):
            with patch("app.core.lifespan.asyncpg.create_pool", fake_create_pool):
                with caplog.at_level(logging.DEBUG, logger="app.core.lifespan"):
                    async with event_driven_lifespan(app):
                        pass

        log_text = caplog.text
        assert "postgresql://" not in log_text
        assert "super_secret_user" not in log_text


# ---------------------------------------------------------------------------
# Group G — build_event_store_pool_kwargs helper
# ---------------------------------------------------------------------------


class TestGroupGHelperKwargs:
    """G: build_event_store_pool_kwargs is pure and returns fixed defaults."""

    def test_g1_returns_expected_defaults(self) -> None:
        result = build_event_store_pool_kwargs(_FakeSettings())
        assert result == {"min_size": 1, "max_size": 4, "command_timeout": 30}

    def test_g2_does_not_contain_server_settings(self) -> None:
        result = build_event_store_pool_kwargs(_FakeSettings())
        assert "server_settings" not in result

    def test_g3_does_not_contain_search_path(self) -> None:
        result = build_event_store_pool_kwargs(_FakeSettings())
        assert "search_path" not in result

    def test_g4_does_not_contain_dsn(self) -> None:
        result = build_event_store_pool_kwargs(_FakeSettings())
        assert "dsn" not in result

    def test_g5_two_calls_return_independent_dicts(self) -> None:
        a = build_event_store_pool_kwargs(_FakeSettings())
        b = build_event_store_pool_kwargs(_FakeSettings())
        assert a is not b
        assert a == b

    def test_g6_helper_does_not_call_create_pool(self) -> None:
        """Calling the helper must not trigger any pool I/O."""
        create_pool = MagicMock(side_effect=AssertionError("create_pool called"))
        with patch("app.core.lifespan.asyncpg.create_pool", create_pool):
            build_event_store_pool_kwargs(_FakeSettings())
        create_pool.assert_not_called()
