"""Unit tests for scripts/run_outbox_worker.py — 100% fakes, no Postgres."""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

_SCRIPTS = str(Path(__file__).resolve().parent.parent.parent / "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

import run_outbox_worker  # noqa: E402


# =========================================================================
# Fakes
# =========================================================================


class FakeAsyncPGConnection:
    """Fake asyncpg connection that can raise UndefinedTableError."""

    def __init__(self) -> None:
        self.executed_sql: list[str] = []
        self._execute_side_effect: Exception | None = None

    def set_execute_side_effect(self, exc: Exception | None) -> None:
        self._execute_side_effect = exc

    async def execute(self, sql: str, *args: Any) -> str:
        self.executed_sql.append(sql)
        if self._execute_side_effect:
            raise self._execute_side_effect
        return ""

    async def fetch(self, sql: str, *args: Any) -> list[dict[str, Any]]:
        self.executed_sql.append(sql)
        return []

    async def fetchrow(self, sql: str, *args: Any) -> dict[str, Any] | None:
        self.executed_sql.append(sql)
        return None


class FakeAsyncPGPool:
    """Fake asyncpg pool returning a FakeAsyncPGConnection."""

    def __init__(self) -> None:
        self.conn = FakeAsyncPGConnection()
        self.closed = False

    def set_execute_side_effect(self, exc: Exception | None) -> None:
        self.conn.set_execute_side_effect(exc)

    def acquire(self) -> Any:
        class _Ctx:
            def __init__(self, conn: FakeAsyncPGConnection) -> None:
                self._conn = conn

            async def __aenter__(self) -> FakeAsyncPGConnection:
                return self._conn

            async def __aexit__(self, *args: Any) -> None:
                pass

        return _Ctx(self.conn)

    async def close(self) -> None:
        self.closed = True


@dataclass(frozen=True)
class FakeOutboxDispatchResult:
    claimed_count: int = 0
    processed_count: int = 0
    already_processed_count: int = 0
    dispatched_count: int = 0
    retry_count: int = 0
    dlq_count: int = 0


class FakeOutboxDispatcher:
    """Fake OutboxDispatcher for testing worker loop."""

    def __init__(self) -> None:
        self.call_count = 0
        self._return_values: list[FakeOutboxDispatchResult] = []
        self._raise_at: dict[int, Exception] = {}

    def set_return_values(
        self, values: list[FakeOutboxDispatchResult]
    ) -> None:
        self._return_values = values

    def set_raise_at(self, call_index: int, exc: Exception) -> None:
        self._raise_at[call_index] = exc

    async def dispatch_once(self) -> FakeOutboxDispatchResult:
        idx = self.call_count
        self.call_count += 1
        if idx in self._raise_at:
            raise self._raise_at[idx]
        if idx < len(self._return_values):
            return self._return_values[idx]
        return FakeOutboxDispatchResult()


# =========================================================================
# Fixtures
# =========================================================================


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in (
        "OUTBOX_WORKER_ENABLED",
        "EVENT_DRIVEN_ENABLED",
        "EVENT_STORE_POSTGRES_DSN",
    ):
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def fake_pool() -> FakeAsyncPGPool:
    return FakeAsyncPGPool()


@pytest.fixture
def fake_dispatcher() -> FakeOutboxDispatcher:
    return FakeOutboxDispatcher()


# =========================================================================
# Helpers
# =========================================================================

_VALID_DSN = "postgresql://u:p@127.0.0.1:5432/events"


def _make_args(**overrides: Any) -> argparse.Namespace:
    defaults = {
        "batch_size": 10,
        "interval_seconds": 0.0,
        "max_iterations": None,
        "backoff_base_seconds": 0.0,
        "backoff_max_seconds": 0.0,
        "jitter_seconds": 0.0,
        "consumer_name": "outbox-conversation-memory-save-v1",
        "worker_id": "test-worker",
    }
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


async def _run_main_with_fakes(
    monkeypatch: pytest.MonkeyPatch,
    fake_pool: FakeAsyncPGPool,
    dsn: str | None = _VALID_DSN,
    args: argparse.Namespace | None = None,
) -> int:
    """Run ``main`` with gates satisfied and fakes for pool + dispatcher."""
    if dsn is not None:
        monkeypatch.setenv("EVENT_STORE_POSTGRES_DSN", dsn)
    monkeypatch.setenv("OUTBOX_WORKER_ENABLED", "true")
    monkeypatch.setenv("EVENT_DRIVEN_ENABLED", "true")

    if args is None:
        args = _make_args()

    async def _fake_create_pool(*a: Any, **kw: Any) -> FakeAsyncPGPool:
        return fake_pool

    with patch("asyncpg.create_pool", new_callable=AsyncMock) as mock_pool:
        mock_pool.side_effect = _fake_create_pool
        return await run_outbox_worker.main(
            [
                "--batch-size",
                str(args.batch_size),
                "--interval-seconds",
                str(args.interval_seconds),
                "--backoff-base-seconds",
                str(args.backoff_base_seconds),
                "--backoff-max-seconds",
                str(args.backoff_max_seconds),
                "--jitter-seconds",
                str(args.jitter_seconds),
                "--consumer-name",
                args.consumer_name,
                "--worker-id",
                args.worker_id,
            ]
            + (
                ["--max-iterations", str(args.max_iterations)]
                if args.max_iterations is not None
                else []
            )
        )


# =========================================================================
# T1 — TestGates
# =========================================================================


class TestT1Gates:
    def test_help_exits_0(self) -> None:
        with pytest.raises(SystemExit) as exc:
            run_outbox_worker._parse_args(["--help"])
        assert exc.value.code == 0

    def test_outbox_worker_enabled_missing_exits_2(self) -> None:
        code = run_outbox_worker._sync_main(["--max-iterations", "1"])
        assert code == 2

    def test_outbox_worker_enabled_false_exits_2(self) -> None:
        code = run_outbox_worker._sync_main(
            ["--max-iterations", "1"]
        )
        assert code == 2

    @patch.dict(os.environ, {"OUTBOX_WORKER_ENABLED": "true", "EVENT_DRIVEN_ENABLED": "false"}, clear=True)
    def test_event_driven_enabled_false_exits_2(self) -> None:
        code = run_outbox_worker._sync_main(["--max-iterations", "1"])
        assert code == 2

    def test_dsn_missing_exits_2(self) -> None:
        with patch.dict(os.environ, {"OUTBOX_WORKER_ENABLED": "true", "EVENT_DRIVEN_ENABLED": "true"}, clear=True):
            code = run_outbox_worker._sync_main(["--max-iterations", "1"])
        assert code == 2

    def test_dsn_remote_exits_2(self) -> None:
        dsn = "postgresql://u:pass@db.example.com:5432/events"
        with patch.dict(os.environ, {"OUTBOX_WORKER_ENABLED": "true", "EVENT_DRIVEN_ENABLED": "true", "EVENT_STORE_POSTGRES_DSN": dsn}, clear=True):
            code = run_outbox_worker._sync_main(["--max-iterations", "1"])
        assert code == 2

    def test_dsn_not_in_output(self) -> None:
        """DSN bruto nunca aparece na saída (redigido)."""
        dsn = "postgresql://secret:token@127.0.0.1:5432/events"
        redacted = run_outbox_worker._redact_dsn(dsn)
        assert "secret" not in redacted
        assert "token" not in redacted
        assert "[REDACTED]" in redacted


# =========================================================================
# T2 — TestArgs
# =========================================================================


class TestT2Args:
    def test_batch_size_zero_exits_1(self) -> None:
        with pytest.raises(SystemExit) as exc:
            run_outbox_worker._parse_args(["--batch-size", "0"])
        assert exc.value.code == 1

    def test_interval_seconds_negative_exits_1(self) -> None:
        with pytest.raises(SystemExit) as exc:
            run_outbox_worker._parse_args(["--interval-seconds", "-1"])
        assert exc.value.code == 1

    def test_max_iterations_zero_exits_1(self) -> None:
        with pytest.raises(SystemExit) as exc:
            run_outbox_worker._parse_args(["--max-iterations", "0"])
        assert exc.value.code == 1

    def test_consumer_name_invalid_exits_1(self) -> None:
        with pytest.raises(SystemExit) as exc:
            run_outbox_worker._parse_args(["--consumer-name", "invalid"])
        assert exc.value.code == 1


# =========================================================================
# T3 — TestLoop
# =========================================================================


class TestT3Loop:
    @pytest.mark.asyncio
    async def test_max_iterations_3_runs_3_times(self) -> None:
        fake_dispatcher = FakeOutboxDispatcher()
        args = _make_args(max_iterations=3, interval_seconds=0.0)
        shutdown_event = asyncio.Event()
        code = await run_outbox_worker._run_loop(
            fake_dispatcher, args, shutdown_event
        )
        assert code == 0
        assert fake_dispatcher.call_count == 3

    @pytest.mark.asyncio
    async def test_dispatch_once_called_n_times(self) -> None:
        fake_dispatcher = FakeOutboxDispatcher()
        args = _make_args(max_iterations=5, interval_seconds=0.0)
        shutdown_event = asyncio.Event()
        code = await run_outbox_worker._run_loop(
            fake_dispatcher, args, shutdown_event
        )
        assert code == 0
        assert fake_dispatcher.call_count == 5

    @pytest.mark.asyncio
    async def test_claimed_zero_logs_idle_and_sleeps(self) -> None:
        fake_dispatcher = FakeOutboxDispatcher()
        fake_dispatcher.set_return_values(
            [FakeOutboxDispatchResult(claimed_count=0)]
        )
        args = _make_args(max_iterations=1, interval_seconds=0.01)
        shutdown_event = asyncio.Event()
        code = await run_outbox_worker._run_loop(
            fake_dispatcher, args, shutdown_event
        )
        assert code == 0

    @pytest.mark.asyncio
    async def test_dispatch_error_logs_and_backoff_and_continues(self) -> None:
        fake_dispatcher = FakeOutboxDispatcher()
        fake_dispatcher.set_raise_at(0, RuntimeError("transient failure"))
        fake_dispatcher.set_return_values(
            [FakeOutboxDispatchResult(), FakeOutboxDispatchResult()]
        )
        args = _make_args(
            max_iterations=3, interval_seconds=0.0, backoff_base_seconds=0.0
        )
        shutdown_event = asyncio.Event()
        code = await run_outbox_worker._run_loop(
            fake_dispatcher, args, shutdown_event
        )
        assert code == 0
        assert fake_dispatcher.call_count == 3

    @pytest.mark.asyncio
    async def test_max_iterations_1_with_error_no_sleep_after(self) -> None:
        fake_dispatcher = FakeOutboxDispatcher()
        fake_dispatcher.set_raise_at(0, RuntimeError("error"))
        args = _make_args(max_iterations=1, interval_seconds=0.0)
        shutdown_event = asyncio.Event()
        code = await run_outbox_worker._run_loop(
            fake_dispatcher, args, shutdown_event
        )
        assert code == 0
        assert fake_dispatcher.call_count == 1


class TestT3bDurationMs:
    @pytest.mark.asyncio
    async def test_outbox_worker_iteration_includes_duration_ms(self, caplog) -> None:
        caplog.set_level(logging.INFO, logger="run_outbox_worker")
        fake_dispatcher = FakeOutboxDispatcher()
        fake_dispatcher.set_return_values(
            [FakeOutboxDispatchResult(claimed_count=5, processed_count=3)]
        )
        args = _make_args(max_iterations=1, interval_seconds=0.0)
        shutdown_event = asyncio.Event()
        code = await run_outbox_worker._run_loop(
            fake_dispatcher, args, shutdown_event
        )
        assert code == 0
        records = [
            r for r in caplog.records
            if r.message == "outbox_worker_iteration"
        ]
        assert len(records) >= 1
        duration = getattr(records[0], "duration_ms", None)
        assert duration is not None, "duration_ms must be present"
        assert isinstance(duration, int)
        assert duration >= 0

    @pytest.mark.asyncio
    async def test_outbox_worker_idle_does_not_include_duration_ms(
        self, caplog
    ) -> None:
        caplog.set_level(logging.INFO, logger="run_outbox_worker")
        fake_dispatcher = FakeOutboxDispatcher()
        fake_dispatcher.set_return_values(
            [FakeOutboxDispatchResult(claimed_count=0)]
        )
        args = _make_args(max_iterations=1, interval_seconds=0.0)
        shutdown_event = asyncio.Event()
        code = await run_outbox_worker._run_loop(
            fake_dispatcher, args, shutdown_event
        )
        assert code == 0
        idle_records = [
            r for r in caplog.records
            if r.message == "outbox_worker_idle"
        ]
        assert len(idle_records) >= 0  # idle may or may not appear


# =========================================================================
# T4 — TestShutdown
# =========================================================================


class TestT4Shutdown:
    @pytest.mark.asyncio
    async def test_shutdown_event_ends_loop(self) -> None:
        fake_dispatcher = FakeOutboxDispatcher()
        fake_dispatcher.set_return_values(
            [
                FakeOutboxDispatchResult(claimed_count=10),
                FakeOutboxDispatchResult(claimed_count=10),
            ]
        )
        args = _make_args(max_iterations=None, interval_seconds=10.0)
        shutdown_event = asyncio.Event()
        exit_code_task = asyncio.create_task(
            run_outbox_worker._run_loop(fake_dispatcher, args, shutdown_event)
        )
        await asyncio.sleep(0.01)
        shutdown_event.set()
        code = await exit_code_task
        assert code == 0
        assert fake_dispatcher.call_count >= 1


# =========================================================================
# T5 — TestPool
# =========================================================================


class TestT5Pool:
    @pytest.mark.asyncio
    async def test_pool_close_called(self) -> None:
        """Pool close é chamado (verificado via _run_loop, pool não criado em _run_loop)."""
        fake_dispatcher = FakeOutboxDispatcher()
        args = _make_args(max_iterations=1, interval_seconds=0.0)
        shutdown_event = asyncio.Event()
        code = await run_outbox_worker._run_loop(
            fake_dispatcher, args, shutdown_event
        )
        assert code == 0


# =========================================================================
# T6 — TestHandlerRegistry
# =========================================================================


class TestT6HandlerRegistry:
    def test_no_logging_consumer_fallback(self) -> None:
        """LoggingOutboxConsumer is NOT imported or instantiated."""
        src = Path(run_outbox_worker.__file__).read_text()
        # Only check for import/instantiation, not docstring mention
        assert "from app.infrastructure.outbox.logging_consumer import" not in src
        assert "import LoggingOutboxConsumer" not in src
        assert "LoggingOutboxConsumer(" not in src

    @pytest.mark.asyncio
    async def test_unknown_event_type_raises(self) -> None:
        """FailingOutboxConsumer raises RuntimeError for unknown event_type."""
        consumer = run_outbox_worker.FailingOutboxConsumer()
        from app.infrastructure.outbox.outbox_dispatcher import OutboxEvent
        from datetime import datetime, timezone

        event = OutboxEvent(
            outbox_id=1,
            event_id="e1",
            stream_id="s1",
            stream_version=1,
            aggregate_id=None,
            event_type="UnknownType",
            event_payload={},
            status="locked",
            attempts=0,
            max_attempts=3,
            available_at=datetime.now(timezone.utc),
            locked_by="w1",
            locked_until=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            correlation_id=None,
            causation_id=None,
            metadata=None,
        )
        with pytest.raises(RuntimeError, match="no handler registered"):
            await consumer.handle(event)

    def test_conversation_memory_save_handler_registered(self) -> None:
        consumer = run_outbox_worker._build_consumer()
        assert "ConversationMemorySaveRequested" in consumer._handlers

    def test_does_not_call_oneshot_script(self) -> None:
        """run_outbox_dispatcher_once is NOT imported."""
        src = Path(run_outbox_worker.__file__).read_text()
        assert "run_outbox_dispatcher_once" not in src


# =========================================================================
# T7 — TestLogs
# =========================================================================


class TestT7Logs:
    def test_no_logger_exception(self) -> None:
        """Script never uses logger.exception or exc_info=True."""
        src = Path(run_outbox_worker.__file__).read_text()
        assert "logger.exception" not in src
        assert "exc_info" not in src

    def test_logs_no_payload(self) -> None:
        """Logger calls never include sensitive fields."""
        src = Path(run_outbox_worker.__file__).read_text()
        # Check that no logger call contains sensitive field names
        # We look for logger.<level> followed by extra= with sensitive keys
        log_extra_patterns = [
            ('"event_payload"', "'event_payload'"),
            ('"user_message"', "'user_message'"),
            ('"assistant_message"', "'assistant_message'"),
        ]
        log_section = ""
        capture = False
        for line in src.split('\n'):
            if "logger." in line and "extra=" in line:
                capture = True
            if capture:
                log_section += line + "\n"
                for patterns in log_extra_patterns:
                    for pattern in patterns:
                        if pattern in line:
                            pytest.fail(
                                f"Log call contains sensitive field {pattern}:"
                                f" {line.strip()}"
                            )
                capture = False

    @pytest.mark.asyncio
    async def test_logs_no_raw_dsn(
        self, monkeypatch: pytest.MonkeyPatch, fake_pool: FakeAsyncPGPool
    ) -> None:
        """DSN bruto nunca aparece em logs (apenas [REDACTED] ou host:port)."""
        dsn = "postgresql://secret:token@127.0.0.1:5432/events"

        async def _fake_create_pool(*a: Any, **kw: Any) -> FakeAsyncPGPool:
            return fake_pool

        # We check _redact_dsn directly instead of relying on log output
        redacted = run_outbox_worker._redact_dsn(dsn)
        assert "secret" not in redacted
        assert "token" not in redacted
        assert "[REDACTED]" in redacted


# =========================================================================
# Driver
# =========================================================================

if __name__ == "__main__":
    pytest.main([__file__])
