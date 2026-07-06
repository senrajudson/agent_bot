from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.run_outbox_dispatcher_once import (
    EXIT_OK,
    EXIT_ARGS,
    EXIT_GATE,
    EXIT_CONFIG,
    EXIT_RESULT_FAIL,
    EXIT_STORE,
    _parse_args,
    _redact_dsn,
    OutboxDispatchResult,
)

_VALID_DSN = "postgresql://user@127.0.0.1:5433/db"


# =========================================================================
# Unit — _redact_dsn
# =========================================================================


class TestRedactDsn:
    def test_redacts_password(self) -> None:
        dsn = "postgresql://user:secret@127.0.0.1:5433/db"
        assert _redact_dsn(dsn) == "postgresql://[REDACTED]@127.0.0.1:5433/db"

    def test_redacts_without_password(self) -> None:
        dsn = "postgresql://user@127.0.0.1:5433/db"
        assert _redact_dsn(dsn) == "postgresql://[REDACTED]@127.0.0.1:5433/db"


# =========================================================================
# Unit — _parse_args
# =========================================================================


class TestParseArgs:
    def test_defaults(self) -> None:
        args = _parse_args([])
        assert args.batch_size == 10
        assert args.consumer_name == "outbox-logging-default"
        assert args.worker_id is None

    def test_custom_values(self) -> None:
        args = _parse_args(["--batch-size", "5", "--consumer-name", "my-consumer", "--worker-id", "w-42"])
        assert args.batch_size == 5
        assert args.consumer_name == "my-consumer"
        assert args.worker_id == "w-42"

    def test_help_exits_zero(self) -> None:
        with pytest.raises(SystemExit) as exc:
            _parse_args(["--help"])
        assert exc.value.code == 0


# =========================================================================
# Unit — Gate (OUTBOX_DISPATCHER_ENABLED)
# =========================================================================


class TestGate:
    def test_gate_absent_returns_exit_gate(self) -> None:
        from scripts.run_outbox_dispatcher_once import _check_gate

        with patch.dict(os.environ, {}, clear=True):
            code = _check_gate()
        assert code == EXIT_GATE

    def test_gate_false_returns_exit_gate(self) -> None:
        from scripts.run_outbox_dispatcher_once import _check_gate

        with patch.dict(os.environ, {"OUTBOX_DISPATCHER_ENABLED": "false"}, clear=True):
            code = _check_gate()
        assert code == EXIT_GATE

    def test_gate_true_returns_ok(self) -> None:
        from scripts.run_outbox_dispatcher_once import _check_gate

        with patch.dict(os.environ, {"OUTBOX_DISPATCHER_ENABLED": "true"}, clear=True):
            code = _check_gate()
        assert code == EXIT_OK


# =========================================================================
# Unit — DSN
# =========================================================================


class TestDsn:
    def test_dsn_absent_returns_exit_gate(self) -> None:
        from scripts.run_outbox_dispatcher_once import _check_dsn

        with patch.dict(os.environ, {}, clear=True):
            code, dsn = _check_dsn()
        assert code == EXIT_GATE
        assert dsn is None

    def test_dsn_non_local_rejected(self) -> None:
        from scripts.run_outbox_dispatcher_once import _check_dsn

        with patch.dict(os.environ, {"EVENT_STORE_POSTGRES_DSN": "postgresql://u@p:10.0.0.1:5432/db"}, clear=True):
            code, dsn = _check_dsn()
        assert code == EXIT_GATE
        assert dsn is None

    def test_dsn_valid_returns_ok(self) -> None:
        from scripts.run_outbox_dispatcher_once import _check_dsn

        with patch.dict(os.environ, {"EVENT_STORE_POSTGRES_DSN": _VALID_DSN}, clear=True):
            code, dsn = _check_dsn()
        assert code == EXIT_OK
        assert dsn == _VALID_DSN


# =========================================================================
# Integration-like — main() with mocks
# =========================================================================


def _make_result(claimed=0, processed=0, already=0, dispatched=0, retry=0, dlq=0) -> OutboxDispatchResult:
    return OutboxDispatchResult(
        claimed_count=claimed,
        processed_count=processed,
        already_processed_count=already,
        dispatched_count=dispatched,
        retry_count=retry,
        dlq_count=dlq,
    )


def _fake_pool():
    fake_conn = AsyncMock(spec_set=["execute"])
    fake_conn.execute = AsyncMock(return_value="SELECT 0")

    class FakeAcquire:
        async def __aenter__(self):
            return fake_conn
        async def __aexit__(self, *args):
            pass

    class FakePool:
        def acquire(self):
            return FakeAcquire()
        async def close(self):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass

    return FakePool()


class TestMainWithMocks:
    """Test main() orchestrator with gate/DSN/pool/dispatch all mocked."""

    @patch.dict(os.environ, {}, clear=True)
    def test_gate_absent_returns_exit_gate(self) -> None:
        from scripts.run_outbox_dispatcher_once import main
        code = asyncio.run(main([]))
        assert code == EXIT_GATE

    @patch.dict(os.environ, {"OUTBOX_DISPATCHER_ENABLED": "true", "EVENT_STORE_POSTGRES_DSN": _VALID_DSN}, clear=True)
    async def test_pool_fail_returns_exit_store(self) -> None:
        from scripts.run_outbox_dispatcher_once import main

        with patch("asyncpg.create_pool", side_effect=RuntimeError("pool fail")):
            code = await main([])
        assert code == EXIT_STORE

    @patch.dict(os.environ, {"OUTBOX_DISPATCHER_ENABLED": "true", "EVENT_STORE_POSTGRES_DSN": _VALID_DSN}, clear=True)
    async def test_schema_missing_returns_exit_config(self) -> None:
        from scripts.run_outbox_dispatcher_once import main

        with patch("asyncpg.create_pool", new_callable=AsyncMock, return_value=_fake_pool()):
            with patch("scripts.run_outbox_dispatcher_once._verify_schema", new_callable=AsyncMock, return_value=EXIT_CONFIG):
                code = await main([])
        assert code == EXIT_CONFIG

    @patch.dict(os.environ, {"OUTBOX_DISPATCHER_ENABLED": "true", "EVENT_STORE_POSTGRES_DSN": _VALID_DSN}, clear=True)
    async def test_dispatch_ok_returns_exit_ok(self) -> None:
        from scripts.run_outbox_dispatcher_once import main

        with patch("asyncpg.create_pool", new_callable=AsyncMock, return_value=_fake_pool()):
            with patch("scripts.run_outbox_dispatcher_once._verify_schema", new_callable=AsyncMock, return_value=EXIT_OK):
                with patch(
                    "scripts.run_outbox_dispatcher_once.OutboxDispatcher.dispatch_once",
                    new_callable=AsyncMock,
                    return_value=_make_result(claimed=1, processed=1, dispatched=1),
                ):
                    code = await main([])
        assert code == EXIT_OK

    @patch.dict(os.environ, {"OUTBOX_DISPATCHER_ENABLED": "true", "EVENT_STORE_POSTGRES_DSN": _VALID_DSN}, clear=True)
    async def test_claimed_zero_is_ok(self) -> None:
        from scripts.run_outbox_dispatcher_once import main

        with patch("asyncpg.create_pool", new_callable=AsyncMock, return_value=_fake_pool()):
            with patch("scripts.run_outbox_dispatcher_once._verify_schema", new_callable=AsyncMock, return_value=EXIT_OK):
                with patch(
                    "scripts.run_outbox_dispatcher_once.OutboxDispatcher.dispatch_once",
                    new_callable=AsyncMock,
                    return_value=_make_result(claimed=0),
                ):
                    code = await main([])
        assert code == EXIT_OK

    @patch.dict(os.environ, {"OUTBOX_DISPATCHER_ENABLED": "true", "EVENT_STORE_POSTGRES_DSN": _VALID_DSN}, clear=True)
    async def test_retry_returns_exit_fail(self) -> None:
        from scripts.run_outbox_dispatcher_once import main

        with patch("asyncpg.create_pool", new_callable=AsyncMock, return_value=_fake_pool()):
            with patch("scripts.run_outbox_dispatcher_once._verify_schema", new_callable=AsyncMock, return_value=EXIT_OK):
                with patch(
                    "scripts.run_outbox_dispatcher_once.OutboxDispatcher.dispatch_once",
                    new_callable=AsyncMock,
                    return_value=_make_result(claimed=1, retry=1),
                ):
                    code = await main([])
        assert code == EXIT_RESULT_FAIL

    @patch.dict(os.environ, {"OUTBOX_DISPATCHER_ENABLED": "true", "EVENT_STORE_POSTGRES_DSN": _VALID_DSN}, clear=True)
    async def test_dlq_returns_exit_fail(self) -> None:
        from scripts.run_outbox_dispatcher_once import main

        with patch("asyncpg.create_pool", new_callable=AsyncMock, return_value=_fake_pool()):
            with patch("scripts.run_outbox_dispatcher_once._verify_schema", new_callable=AsyncMock, return_value=EXIT_OK):
                with patch(
                    "scripts.run_outbox_dispatcher_once.OutboxDispatcher.dispatch_once",
                    new_callable=AsyncMock,
                    return_value=_make_result(claimed=1, dlq=1),
                ):
                    code = await main([])
        assert code == EXIT_RESULT_FAIL

    @patch.dict(os.environ, {"OUTBOX_DISPATCHER_ENABLED": "true", "EVENT_STORE_POSTGRES_DSN": _VALID_DSN}, clear=True)
    async def test_dispatch_raises_returns_exit_store(self) -> None:
        from scripts.run_outbox_dispatcher_once import main

        with patch("asyncpg.create_pool", new_callable=AsyncMock, return_value=_fake_pool()):
            with patch("scripts.run_outbox_dispatcher_once._verify_schema", new_callable=AsyncMock, return_value=EXIT_OK):
                with patch(
                    "scripts.run_outbox_dispatcher_once.OutboxDispatcher.dispatch_once",
                    new_callable=AsyncMock,
                    side_effect=RuntimeError("dispatch boom"),
                ):
                    code = await main([])
        assert code == EXIT_STORE

    @patch.dict(os.environ, {"OUTBOX_DISPATCHER_ENABLED": "true", "EVENT_STORE_POSTGRES_DSN": _VALID_DSN}, clear=True)
    async def test_json_output_shape(self, capsys) -> None:
        from scripts.run_outbox_dispatcher_once import main

        with patch("asyncpg.create_pool", new_callable=AsyncMock, return_value=_fake_pool()):
            with patch("scripts.run_outbox_dispatcher_once._verify_schema", new_callable=AsyncMock, return_value=EXIT_OK):
                with patch(
                    "scripts.run_outbox_dispatcher_once.OutboxDispatcher.dispatch_once",
                    new_callable=AsyncMock,
                    return_value=_make_result(claimed=1, processed=1, dispatched=1),
                ):
                    code = await main([])
        assert code == EXIT_OK
        captured = capsys.readouterr()
        import json
        data = json.loads(captured.out)
        assert "claimed_count" in data
        assert "processed_count" in data
        assert "dispatched_count" in data
        assert "retry_count" in data
        assert "dlq_count" in data
        assert data["claimed_count"] == 1

    @patch.dict(os.environ, {"OUTBOX_DISPATCHER_ENABLED": "true"}, clear=True)
    def test_dsn_absent_returns_exit_gate(self) -> None:
        from scripts.run_outbox_dispatcher_once import main
        code = asyncio.run(main([]))
        assert code == EXIT_GATE
