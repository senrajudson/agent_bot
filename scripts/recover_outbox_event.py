#!/usr/bin/env python3
"""Dry‑run recovery eligibility checker for dead_letter outbox events.

Usage:
    python scripts/recover_outbox_event.py --outbox-id 42 --ticket TICKET-123
    python scripts/recover_outbox_event.py --outbox-id 42 --reason "recovery" --json

Exit codes:
    0  Dry‑run executed (eligible=true or eligible=false)
    1  Argumentos inválidos
    2  DSN ausente, inválido ou não‑local
    3  Schema / tabela ausente
    4  Erro de conexão ou query
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


ALLOWED_EVENT_TYPES: frozenset[str] = frozenset({
    "ConversationMemorySaveRequested",
})

TABLES_TO_CHECK = ["outbox_events", "outbox_dlq", "processed_events"]

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
        description="Analisar elegibilidade de dead_letter para recovery (dry-run, read‑only).",
    )
    parser.add_argument(
        "--outbox-id",
        type=_outbox_id_type,
        required=True,
        help="ID do evento outbox a analisar",
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
    return parser


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = _build_parser()
    return parser.parse_args(argv)


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


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parse_args(argv)
    except SystemExit as exc:
        return exc.code

    dsn_code, dsn = _check_dsn()
    if dsn_code != EXIT_OK:
        return dsn_code

    return asyncio.run(_run_once(dsn, args))


def entry_point() -> NoReturn:
    sys.exit(main())


if __name__ == "__main__":
    entry_point()
