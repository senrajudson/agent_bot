"""Helpers CLI compartilhados para scripts EDD.

Centraliza:
- DSN_REGEX, redact_dsn
- POOL_MIN_SIZE, POOL_MAX_SIZE, COMMAND_TIMEOUT
- setup_edd_cli_logging

Sem dependência de asyncpg, argparse, env vars, rede ou negócio.
"""
from __future__ import annotations

import logging
import re
import sys

DSN_REGEX = re.compile(
    r"^postgresql://[^@]+@(127\.0\.0\.1|localhost):[0-9]+/[^?]+$"
)

POOL_MIN_SIZE: int = 1
POOL_MAX_SIZE: int = 1
COMMAND_TIMEOUT: int = 30


def redact_dsn(dsn: str) -> str:
    """Redact credentials from a PostgreSQL DSN for safe logging."""
    return re.sub(r"(://)[^@]+(@)", r"\1[REDACTED]\2", dsn)


def setup_edd_cli_logging() -> None:
    """Configure logging for EDD CLI scripts (identical to current behavior)."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stderr,
    )
