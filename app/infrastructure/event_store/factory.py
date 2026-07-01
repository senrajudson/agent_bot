"""Event Store factory — selects backend based on EVENT_STORE_BACKEND env var.

Supported backends:
    - "memory"                  (default) — InMemoryEventStore
    - "redis_streams"           — RedisStreamsEventStore
    - "postgres"                — PostgresEventStore (legacy)
    - "transactional_postgres"  — TransactionalPostgresEventStore (EDD, requires EVENT_DRIVEN_ENABLED=true)

The default preserves the existing runtime behavior of the /chat endpoint.
The ``get_transactional_event_store()`` function is an isolated EDD path
that does NOT modify ``get_event_store()`` or the ``/chat`` runtime.
"""
from __future__ import annotations

import os
import logging
from typing import Any

from app.core.config import Settings, settings as _global_settings
from app.infrastructure.event_store.transactional_postgres_event_store import TransactionalPostgresEventStore

logger = logging.getLogger(__name__)


def _mask_dsn_host(dsn: str) -> str:
    """Extract host from DSN without exposing user/password. Returns 'unknown' on failure."""
    if not dsn or "@" not in dsn:
        return "unknown"
    try:
        return dsn.split("@", 1)[-1].split("/", 1)[0]
    except Exception:
        return "unknown"


def get_transactional_event_store(
    pool: Any,
    settings: Settings | None = None,
) -> TransactionalPostgresEventStore:
    """Build a TransactionalPostgresEventStore with EDD validation.

    This function is isolated from ``get_event_store()`` and does NOT create
    a pool, does NOT connect to Postgres, and does NOT modify ``/chat`` runtime.

    Args:
        pool: An asyncpg pool (must be pre-created by the caller).
        settings: Optional Settings override. When None, uses the global settings.

    Raises:
        ValueError: If any validation fails (flag off, wrong backend, missing DSN, no pool).
    """
    if pool is None:
        raise ValueError("pool is required to build TransactionalPostgresEventStore")

    s = settings if settings is not None else _global_settings

    if not s.EVENT_DRIVEN_ENABLED:
        raise ValueError("EVENT_DRIVEN_ENABLED must be true to build TransactionalPostgresEventStore")

    if s.EVENT_STORE_BACKEND != "transactional_postgres":
        raise ValueError(
            f"EVENT_STORE_BACKEND must be 'transactional_postgres' when EVENT_DRIVEN_ENABLED is true; got '{s.EVENT_STORE_BACKEND}'"
        )

    if not s.EVENT_STORE_POSTGRES_DSN:
        raise ValueError("EVENT_STORE_POSTGRES_DSN is required when EVENT_DRIVEN_ENABLED is true")

    logger.info(
        "EventStore EDD: building TransactionalPostgresEventStore (backend=%s, dsn_host=%s)",
        s.EVENT_STORE_BACKEND,
        _mask_dsn_host(s.EVENT_STORE_POSTGRES_DSN),
    )

    return TransactionalPostgresEventStore(pool=pool)


def get_event_store():
    """Create and return the appropriate EventStore based on configuration.

    Returns:
        InMemoryEventStore | RedisStreamsEventStore | PostgresEventStore
    """
    backend = os.environ.get("EVENT_STORE_BACKEND", "memory").lower()

    if backend == "postgres":
        dsn = os.environ.get("EVENT_STORE_POSTGRES_DSN")
        if not dsn:
            raise ValueError(
                "EVENT_STORE_POSTGRES_DSN must be set when EVENT_STORE_BACKEND=postgres"
            )
        from app.infrastructure.event_store.postgres_event_store import PostgresEventStore
        logger.info("EventStore: using PostgreSQL backend (%s)", dsn.split("@")[-1])
        return PostgresEventStore(dsn=dsn)

    if backend == "redis_streams":
        try:
            from app.infrastructure.event_store.redis_streams import RedisStreamsEventStore
            from app.clients.redis_client import get_redis_client
            redis = get_redis_client()
            logger.info("EventStore: using Redis Streams backend")
            return RedisStreamsEventStore(redis=redis)
        except Exception as exc:
            logger.warning(
                "Failed to create RedisStreamsEventStore, falling back to InMemory: %s", exc
            )

    # Default: InMemory (preserves current behavior)
    from app.infrastructure.event_store.in_memory import InMemoryEventStore
    logger.debug("EventStore: using InMemory backend")
    return InMemoryEventStore()
