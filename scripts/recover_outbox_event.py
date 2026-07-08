#!/usr/bin/env python3
"""Dry‑run recovery eligibility checker and controlled execute for dead_letter outbox events.

Usage:
    # Dry-run (read-only)
    python scripts/recover_outbox_event.py --outbox-id 42 --ticket TICKET-123
    python scripts/recover_outbox_event.py --outbox-id 42 --reason "recovery" --json

    # Execute (requeues dead_letter → pending)
    python scripts/recover_outbox_event.py --execute --yes-i-confirm-recovery \\
        --outbox-id 42 --ticket TICKET-123
    python scripts/recover_outbox_event.py --execute --yes-i-confirm-recovery \\
        --outbox-id 42 --reason "recovery" --requested-by alice --json

Exit codes:
    0  Dry-run or execute completed successfully
    1  Invalid arguments
    2  DSN missing, invalid or non‑local
    3  Schema / table missing
    4  Execute not eligible, or connection / query error
    5  Unexpected transactional error
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, NoReturn

_repo_root = str(Path(__file__).resolve().parent.parent)
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)


# ---------------------------------------------------------------------------
# Exit codes
# ---------------------------------------------------------------------------

EXIT_OK = 0
EXIT_ARGS = 1
EXIT_DSN = 2
EXIT_SCHEMA = 3
EXIT_QUERY = 4
EXIT_UNEXPECTED = 5


ALLOWED_EVENT_TYPES: frozenset[str] = frozenset({
    "ConversationMemorySaveRequested",
})

TABLES_TO_CHECK = ["outbox_events", "outbox_dlq", "processed_events", "outbox_recovery_audit"]

AUDIT_TABLE = "outbox_recovery_audit"

ALLOWED_METADATA_KEYS: frozenset[str] = frozenset({
    "script_name",
    "hostname",
    "consumer_name",
    "confirmation_flag",
    "execution_mode",
})

FORBIDDEN_OUTPUT_KEYS: frozenset[str] = frozenset({
    "event_payload", "payload",
    "user_message", "assistant_message",
    "aggregate_id", "conversation_id",
    "user_id",
    "dsn", "token", "secret", "password",
})

MAX_REQUESTED_BY_LENGTH = 256

DSN_REGEX = re.compile(
    r"^postgresql://[^@]+@(127\.0\.0\.1|localhost):[0-9]+/[^?]+$"
)
COMMAND_TIMEOUT = 30
POOL_MIN_SIZE = 1
POOL_MAX_SIZE = 1

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("recover_outbox_event")


def _redact_dsn(dsn: str) -> str:
    return re.sub(r"(://)[^@]+(@)", r"\1[REDACTED]\2", dsn)


def _outbox_id_type(val: str) -> int:
    n = int(val)
    if n <= 0:
        raise argparse.ArgumentTypeError(
            f"--outbox-id must be a positive integer, got {n}"
        )
    return n


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


class _ArgParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        self.exit(EXIT_ARGS, f"{self.prog}: error: {message}\n")


def _build_parser() -> argparse.ArgumentParser:
    parser = _ArgParser(
        description=(
            "Analisar elegibilidade ou executar recovery controlado "
            "para dead_letter outbox events."
        ),
    )
    parser.add_argument(
        "--outbox-id",
        type=_outbox_id_type,
        required=True,
        help="ID do evento outbox a analisar ou recuperar",
    )
    ticket_group = parser.add_mutually_exclusive_group(required=True)
    ticket_group.add_argument(
        "--ticket",
        type=str,
        help="Identificador do ticket de autorização",
    )
    ticket_group.add_argument(
        "--reason",
        type=str,
        help="Justificativa textual para a operação",
    )
    parser.add_argument(
        "--consumer-name",
        type=str,
        default="outbox-conversation-memory-save-v1",
        help="Nome do consumer (default: outbox-conversation-memory-save-v1)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Saída em JSON único (em vez de tabela texto)",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Executar recovery (requeue dead_letter → pending)",
    )
    parser.add_argument(
        "--yes-i-confirm-recovery",
        action="store_true",
        help="Confirmação textual obrigatória para --execute",
    )
    parser.add_argument(
        "--requested-by",
        type=str,
        default=None,
        help="Operador declarado (opcional; default: NULL)",
    )
    return parser


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.execute and not args.yes_i_confirm_recovery:
        parser.error(
            "--execute requires --yes-i-confirm-recovery"
        )

    if args.requested_by is not None and len(args.requested_by) > MAX_REQUESTED_BY_LENGTH:
        parser.error(
            f"--requested-by must be at most {MAX_REQUESTED_BY_LENGTH} characters"
        )

    if args.execute:
        args.yes_i_confirm_recovery = True

    return args


# ---------------------------------------------------------------------------
# DSN gate
# ---------------------------------------------------------------------------


def _check_dsn() -> tuple[int, str | None]:
    dsn = os.environ.get("EVENT_STORE_POSTGRES_DSN")
    if not dsn:
        logger.error("EVENT_STORE_POSTGRES_DSN is not set")
        return EXIT_DSN, None
    if not DSN_REGEX.match(dsn):
        redacted = _redact_dsn(dsn)
        logger.error(
            "DSN inválido ou não‑local (apenas 127.0.0.1 ou localhost): %s",
            redacted,
        )
        return EXIT_DSN, None
    return EXIT_OK, dsn


# ---------------------------------------------------------------------------
# Schema verification
# ---------------------------------------------------------------------------


async def _verify_schema(pool: Any, required: list[str]) -> int:
    async with pool.acquire() as conn:
        for table in required:
            try:
                await conn.execute(f"SELECT 1 FROM {table} LIMIT 0")
            except Exception:
                logger.error(
                    "Schema ausente: tabela %s não encontrada. "
                    "Execute scripts/apply_edd_schema.sh --apply.",
                    table,
                )
                return EXIT_SCHEMA
    return EXIT_OK


# ---------------------------------------------------------------------------
# Action functions
# ---------------------------------------------------------------------------


async def _check_eligibility(
    pool: Any,
    outbox_id: int,
    consumer_name: str,
    ticket_or_reason: str,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "outbox_id": outbox_id,
        "consumer_name": consumer_name,
        "ticket": ticket_or_reason,
        "eligible": False,
        "reason_code": None,
        "event_id": None,
        "event_type": None,
        "status": None,
        "attempts": None,
        "max_attempts": None,
    }

    # V3 — outbox_id exists
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT event_id, event_type, status, attempts, max_attempts "
            "FROM outbox_events WHERE outbox_id = $1",
            outbox_id,
        )

    if row is None:
        result["reason_code"] = "outbox_not_found"
        return result

    result["event_id"] = row["event_id"]
    result["event_type"] = row["event_type"]
    result["status"] = row["status"]
    result["attempts"] = row["attempts"]
    result["max_attempts"] = row["max_attempts"]

    # V4 — status must be dead_letter
    if row["status"] != "dead_letter":
        result["reason_code"] = "status_not_dead_letter"
        return result

    # V5 — event_type in allowlist
    if row["event_type"] not in ALLOWED_EVENT_TYPES:
        result["reason_code"] = "event_type_not_allowed"
        return result

    # V6 — attempts >= max_attempts
    if row["attempts"] < row["max_attempts"]:
        result["reason_code"] = "attempts_below_max"
        return result

    # V7 — outbox_dlq snapshot exists
    async with pool.acquire() as conn:
        dlq_row = await conn.fetchrow(
            "SELECT 1 FROM outbox_dlq WHERE outbox_id = $1 LIMIT 1",
            outbox_id,
        )

    if dlq_row is None:
        result["reason_code"] = "dlq_snapshot_missing"
        return result

    # V8 — processed_events must NOT have (consumer_name, event_id)
    async with pool.acquire() as conn:
        processed_row = await conn.fetchrow(
            "SELECT 1 FROM processed_events "
            "WHERE consumer_name = $1 AND event_id = $2 LIMIT 1",
            consumer_name,
            row["event_id"],
        )

    if processed_row is not None:
        result["reason_code"] = "processed_events_already_marked"
        return result

    result["eligible"] = True
    result["reason_code"] = None
    return result


# ---------------------------------------------------------------------------
# Execute helpers
# ---------------------------------------------------------------------------


class _NotEligible(Exception):
    """Raised inside the execute transaction to force rollback without audit."""

    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code)


async def _check_eligibility_locked(
    conn: Any,
    outbox_id: int,
    consumer_name: str,
) -> dict[str, Any]:
    """Revalidate V3–V8 inside the open transaction (FOR UPDATE already held)."""
    result: dict[str, Any] = {
        "outbox_id": outbox_id,
        "consumer_name": consumer_name,
        "eligible": False,
        "reason_code": None,
        "event_id": None,
        "event_type": None,
        "status": None,
        "attempts": None,
        "max_attempts": None,
    }

    # V3 — outbox_id exists (already locked by FOR UPDATE)
    row = await conn.fetchrow(
        "SELECT event_id, event_type, status, attempts, max_attempts "
        "FROM outbox_events WHERE outbox_id = $1",
        outbox_id,
    )

    if row is None:
        result["reason_code"] = "outbox_not_found"
        return result

    result["event_id"] = row["event_id"]
    result["event_type"] = row["event_type"]
    result["status"] = row["status"]
    result["attempts"] = row["attempts"]
    result["max_attempts"] = row["max_attempts"]

    # V4 — status must be dead_letter
    if row["status"] != "dead_letter":
        result["reason_code"] = "status_not_dead_letter"
        return result

    # V5 — event_type in allowlist
    if row["event_type"] not in ALLOWED_EVENT_TYPES:
        result["reason_code"] = "event_type_not_allowed"
        return result

    # V6 — attempts >= max_attempts
    if row["attempts"] < row["max_attempts"]:
        result["reason_code"] = "attempts_below_max"
        return result

    # V7 — outbox_dlq snapshot exists
    dlq_row = await conn.fetchrow(
        "SELECT 1 FROM outbox_dlq WHERE outbox_id = $1 LIMIT 1",
        outbox_id,
    )
    if dlq_row is None:
        result["reason_code"] = "dlq_snapshot_missing"
        return result

    # V8 — processed_events must NOT have (consumer_name, event_id)
    processed_row = await conn.fetchrow(
        "SELECT 1 FROM processed_events "
        "WHERE consumer_name = $1 AND event_id = $2 LIMIT 1",
        consumer_name,
        row["event_id"],
    )
    if processed_row is not None:
        result["reason_code"] = "processed_events_already_marked"
        return result

    result["eligible"] = True
    result["reason_code"] = None
    return result


def _build_audit_metadata(args: argparse.Namespace) -> dict[str, Any]:
    import socket
    try:
        hostname = socket.gethostname()
    except Exception:
        hostname = "unknown"
    return {
        "script_name": "recover_outbox_event.py",
        "hostname": hostname,
        "consumer_name": args.consumer_name,
        "confirmation_flag": True,
        "execution_mode": "execute",
    }


def _sanitize_execute_record(rd: dict[str, Any]) -> dict[str, Any]:
    """Remove keys that must never appear in execute output."""
    return {k: v for k, v in rd.items() if k not in FORBIDDEN_OUTPUT_KEYS}


# ---------------------------------------------------------------------------
# Execute formatters
# ---------------------------------------------------------------------------


def _print_execute_text(rd: dict[str, Any]) -> None:
    now_utc = datetime.now(timezone.utc).isoformat(timespec="seconds")
    print(f"[{now_utc}]")
    print(f"executed:          {'sim' if rd.get('executed') else 'não'}")
    print(f"eligible:          {'sim' if rd.get('eligible') else 'não'}")
    print(f"outbox_id:         {rd.get('outbox_id')}")
    if rd.get('event_id'):
        print(f"event_id:          {rd['event_id']}")
    if rd.get('event_type'):
        print(f"event_type:        {rd['event_type']}")
    if rd.get('previous_status'):
        print(f"previous_status:   {rd['previous_status']}")
    if rd.get('new_status'):
        print(f"new_status:        {rd['new_status']}")
    if rd.get('previous_attempts') is not None:
        print(f"previous_attempts: {rd['previous_attempts']}")
    if rd.get('new_attempts') is not None:
        print(f"new_attempts:      {rd['new_attempts']}")
    if rd.get('operation_id'):
        print(f"operation_id:      {rd['operation_id']}")
    print(f"consumer_name:     {rd.get('consumer_name')}")
    if rd.get('reason_code'):
        print(f"reason_code:       {rd['reason_code']}")
    if rd.get('next_step'):
        print(f"next_step:         {rd['next_step']}")
    print()


def _print_execute_json(rd: dict[str, Any]) -> None:
    safe = _sanitize_execute_record(rd)
    json.dump(safe, sys.stdout, default=str, ensure_ascii=False)
    sys.stdout.write("\n")


# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------


def _print_text(rd: dict[str, Any]) -> None:
    now_utc = datetime.now(timezone.utc).isoformat(timespec="seconds")
    print(f"[{now_utc}]")
    print(f"outbox_id:     {rd['outbox_id']}")
    print(f"consumer_name: {rd['consumer_name']}")
    print(f"ticket:        {rd['ticket']}")
    print(f"eligible:      {'sim' if rd['eligible'] else 'não'}")
    if not rd["eligible"]:
        print(f"reason_code:   {rd['reason_code']}")
    else:
        print(f"event_id:      {rd['event_id']}")
        print(f"event_type:    {rd['event_type']}")
        print(f"status:        {rd['status']}")
        print(f"attempts:      {rd['attempts']} / {rd['max_attempts']}")
    print()


def _print_json(rd: dict[str, Any]) -> None:
    json.dump(rd, sys.stdout, default=str, ensure_ascii=False)
    sys.stdout.write("\n")


# ---------------------------------------------------------------------------
# Execute logic
# ---------------------------------------------------------------------------


async def _execute_recovery(dsn: str, args: argparse.Namespace) -> int:
    import asyncpg
    from uuid import uuid4

    operation_id = str(uuid4())
    metadata = _build_audit_metadata(args)

    try:
        pool = await asyncpg.create_pool(
            dsn,
            min_size=POOL_MIN_SIZE,
            max_size=POOL_MAX_SIZE,
            command_timeout=COMMAND_TIMEOUT,
        )
    except Exception as exc:
        logger.error("Falha ao criar pool asyncpg: %s", exc)
        return EXIT_QUERY

    async with pool:
        schema_code = await _verify_schema(pool, TABLES_TO_CHECK)
        if schema_code != EXIT_OK:
            return schema_code

        try:
            async with pool.acquire() as conn:
                async with conn.transaction():
                    # 1. SELECT FOR UPDATE on the target row
                    row = await conn.fetchrow(
                        "SELECT event_id, event_type, status, attempts, max_attempts "
                        "FROM outbox_events WHERE outbox_id = $1 FOR UPDATE",
                        args.outbox_id,
                    )
                    if row is None:
                        raise _NotEligible("outbox_not_found")

                    # 2. Revalidate V4–V8 inside the transaction
                    rd = await _check_eligibility_locked(
                        conn,
                        outbox_id=args.outbox_id,
                        consumer_name=args.consumer_name,
                    )
                    if not rd["eligible"]:
                        raise _NotEligible(rd["reason_code"])

                    previous_attempts = row["attempts"]
                    event_id = row["event_id"]
                    event_type = row["event_type"]

                    # 3. Insert audit record (BEFORE the UPDATE)
                    await conn.execute(
                        f"""
                        INSERT INTO {AUDIT_TABLE} (
                            operation_id, outbox_id, event_id, event_type,
                            operation, command_source,
                            previous_status, new_status,
                            previous_attempts, new_attempts,
                            ticket, reason, requested_by,
                            sanitized_error, metadata
                        ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15)
                        """,
                        operation_id,
                        args.outbox_id,
                        event_id,
                        event_type,
                        "recovery_execute",
                        "cli",
                        "dead_letter",
                        "pending",
                        previous_attempts,
                        0,
                        args.ticket,
                        args.reason,
                        args.requested_by,
                        None,
                        json.dumps(metadata),
                    )

                    # 4. UPDATE outbox_events to pending
                    #    Only columns that exist in the schema:
                    #    locked_by, locked_until (NOT locked_at / lock_owner)
                    result = await conn.execute(
                        """
                        UPDATE outbox_events
                        SET status = 'pending',
                            attempts = 0,
                            available_at = NOW(),
                            locked_by = NULL,
                            locked_until = NULL,
                            last_error = NULL,
                            last_error_class = NULL,
                            dead_lettered_at = NULL,
                            updated_at = NOW()
                        WHERE outbox_id = $1
                        """,
                        args.outbox_id,
                    )
                    if result != "UPDATE 1":
                        logger.error(
                            "UPDATE affected %s rows, expected 1 for outbox_id=%s",
                            result,
                            args.outbox_id,
                        )
                        return EXIT_UNEXPECTED

                    # 5. Transaction commits here

            # 6. Build safe output record
            out_rd: dict[str, Any] = {
                "executed": True,
                "eligible": True,
                "outbox_id": args.outbox_id,
                "event_id": event_id,
                "event_type": event_type,
                "previous_status": "dead_letter",
                "new_status": "pending",
                "previous_attempts": previous_attempts,
                "new_attempts": 0,
                "operation_id": operation_id,
                "consumer_name": args.consumer_name,
                "reason_code": None,
                "next_step": "run worker or one-shot separately",
            }

            if args.json:
                _print_execute_json(out_rd)
            else:
                _print_execute_text(out_rd)

            return EXIT_OK

        except _NotEligible as exc:
            # Rollback already happened, output not-eligible result
            ne_rd: dict[str, Any] = {
                "executed": False,
                "eligible": False,
                "outbox_id": args.outbox_id,
                "consumer_name": args.consumer_name,
                "reason_code": exc.reason_code,
                "next_step": "check reason_code and inspect the event in outbox_dlq",
            }
            if args.json:
                _print_execute_json(ne_rd)
            else:
                _print_execute_text(ne_rd)
            return EXIT_QUERY

        except asyncpg.PostgresError as exc:
            logger.error(
                "Erro transacional: %s",
                _sanitize_execute_record({"error": str(exc)})["error"],
            )
            return EXIT_QUERY

        except Exception as exc:
            logger.error("Erro inesperado: %s", exc)
            return EXIT_UNEXPECTED


# ---------------------------------------------------------------------------
# Main logic
# ---------------------------------------------------------------------------


async def _run_once(dsn: str, args: argparse.Namespace) -> int:
    import asyncpg

    try:
        pool = await asyncpg.create_pool(
            dsn,
            min_size=POOL_MIN_SIZE,
            max_size=POOL_MAX_SIZE,
            command_timeout=COMMAND_TIMEOUT,
        )
    except Exception as exc:
        logger.error("Falha ao criar pool asyncpg: %s", exc)
        return EXIT_QUERY

    async with pool:
        schema_code = await _verify_schema(pool, TABLES_TO_CHECK)
        if schema_code != EXIT_OK:
            return schema_code

        try:
            rd = await _check_eligibility(
                pool,
                outbox_id=args.outbox_id,
                consumer_name=args.consumer_name,
                ticket_or_reason=args.ticket or args.reason,
            )
        except Exception as exc:
            logger.error("Falha na consulta: %s", exc)
            return EXIT_QUERY

    if args.json:
        _print_json(rd)
    else:
        _print_text(rd)

    return EXIT_OK


async def _run_execute(dsn: str, args: argparse.Namespace) -> int:
    return await _execute_recovery(dsn, args)


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parse_args(argv)
    except SystemExit as exc:
        return exc.code

    dsn_code, dsn = _check_dsn()
    if dsn_code != EXIT_OK:
        return dsn_code

    if args.execute:
        return asyncio.run(_run_execute(dsn, args))
    return asyncio.run(_run_once(dsn, args))


def entry_point() -> NoReturn:
    sys.exit(main())


if __name__ == "__main__":
    entry_point()
