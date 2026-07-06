#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import dataclasses
import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import NoReturn

# Ensure the repo root is on sys.path so that ``app`` is importable
# when the script is run directly (e.g. ``python scripts/run_outbox_dispatcher_once.py``).
_repo_root = str(Path(__file__).resolve().parent.parent)
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

import asyncpg

from app.infrastructure.outbox.logging_consumer import LoggingOutboxConsumer
from app.infrastructure.outbox.outbox_dispatcher import (
    OutboxDispatcher,
    OutboxDispatchResult,
    PostgresOutboxStore,
)

# ---------------------------------------------------------------------------
# Exit codes
# ---------------------------------------------------------------------------

EXIT_OK = 0
EXIT_ARGS = 1
EXIT_GATE = 2
EXIT_CONFIG = 3
EXIT_RESULT_FAIL = 4
EXIT_STORE = 5

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DSN_REGEX = re.compile(
    r"^postgresql://[^@]+@(127\.0\.0\.1|localhost):[0-9]+/[^?]+$"
)
BATCH_SIZE_DEFAULT = 10
CONSUMER_NAME_DEFAULT = "outbox-logging-default"
COMMAND_TIMEOUT = 30
POOL_MIN_SIZE = 1
POOL_MAX_SIZE = 1

# ---------------------------------------------------------------------------
# Logger
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("run_outbox_dispatcher_once")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _redact_dsn(dsn: str) -> str:
    return re.sub(r"(://)[^@]+(@)", r"\1[REDACTED]\2", dsn)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Processar um único batch de outbox_events via OutboxDispatcher.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=BATCH_SIZE_DEFAULT,
        help=f"Número máximo de eventos por batch (default: {BATCH_SIZE_DEFAULT})",
    )
    parser.add_argument(
        "--consumer-name",
        type=str,
        default=CONSUMER_NAME_DEFAULT,
        help=f"Identificador do consumer (default: {CONSUMER_NAME_DEFAULT})",
    )
    parser.add_argument(
        "--worker-id",
        type=str,
        default=None,
        help="Identificador do worker (default: auto-gerado pelo dispatcher)",
    )
    return parser.parse_args(argv)


def _check_gate() -> int:
    enabled = os.environ.get("OUTBOX_DISPATCHER_ENABLED")
    if enabled != "true":
        redacted = _redact_dsn(os.environ.get("EVENT_STORE_POSTGRES_DSN", ""))
        logger.error(
            "Gate bloqueado: OUTBOX_DISPATCHER_ENABLED must be 'true', got %r. "
            "DSN (redigido): %s",
            enabled,
            redacted,
        )
        return EXIT_GATE
    return EXIT_OK


def _check_dsn() -> tuple[int, str | None]:
    dsn = os.environ.get("EVENT_STORE_POSTGRES_DSN")
    if not dsn:
        logger.error("EVENT_STORE_POSTGRES_DSN is not set")
        return EXIT_GATE, None
    if not DSN_REGEX.match(dsn):
        redacted = _redact_dsn(dsn)
        logger.error(
            "DSN inválido ou não-local (apenas 127.0.0.1 ou localhost): %s",
            redacted,
        )
        return EXIT_GATE, None
    return EXIT_OK, dsn


async def _verify_schema(pool: asyncpg.Pool) -> int:
    async with pool.acquire() as conn:
        try:
            await conn.execute("SELECT 1 FROM outbox_events LIMIT 0")
        except asyncpg.UndefinedTableError:
            logger.error(
                "Schema ausente: tabela outbox_events não encontrada. "
                "Execute scripts/apply_edd_schema.sh --apply."
            )
            return EXIT_CONFIG
        except asyncpg.PostgresError as exc:
            logger.error("Erro de configuração do banco: %s", exc)
            return EXIT_CONFIG
        except Exception as exc:
            logger.error("Erro inesperado ao verificar schema: %s", exc)
            return EXIT_CONFIG
    return EXIT_OK


async def _run_once(dsn: str, args: argparse.Namespace) -> int:
    try:
        pool = await asyncpg.create_pool(
            dsn,
            min_size=POOL_MIN_SIZE,
            max_size=POOL_MAX_SIZE,
            command_timeout=COMMAND_TIMEOUT,
        )
    except Exception as exc:
        logger.error("Falha ao criar pool asyncpg: %s", exc)
        return EXIT_STORE

    async with pool:
        schema_code = await _verify_schema(pool)
        if schema_code != EXIT_OK:
            return schema_code

        store = PostgresOutboxStore(pool=pool)
        consumer = LoggingOutboxConsumer(args.consumer_name)

        dispatcher_kwargs: dict = {}
        if args.worker_id is not None:
            dispatcher_kwargs["worker_id"] = args.worker_id

        dispatcher = OutboxDispatcher(
            store=store,
            consumer=consumer,
            consumer_name=args.consumer_name,
            batch_size=args.batch_size,
            **dispatcher_kwargs,
        )

        try:
            result: OutboxDispatchResult = await dispatcher.dispatch_once()
        except Exception as exc:
            logger.error("dispatch_once falhou: %s", exc)
            return EXIT_STORE

        try:
            json_str = json.dumps(
                dataclasses.asdict(result),
                default=str,
                ensure_ascii=False,
            )
        except Exception as exc:
            logger.error("Falha ao serializar resultado como JSON: %s", exc)
            return EXIT_ARGS

        print(json_str, flush=True)

        if result.retry_count > 0 or result.dlq_count > 0:
            return EXIT_RESULT_FAIL

    return EXIT_OK


async def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    gate_code = _check_gate()
    if gate_code != EXIT_OK:
        return gate_code
    dsn_code, dsn = _check_dsn()
    if dsn_code != EXIT_OK:
        return dsn_code
    return await _run_once(dsn, args)  # type: ignore[arg-type]


def _sync_main(argv: list[str] | None = None) -> int:
    return asyncio.run(main(argv))


def entry_point() -> NoReturn:
    sys.exit(_sync_main())


if __name__ == "__main__":
    entry_point()
