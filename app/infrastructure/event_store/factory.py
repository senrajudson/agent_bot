"""Event Store factory — selects backend based on EVENT_STORE_BACKEND env var.

Supported backends:
    - "memory"        (default) — InMemoryEventStore
    - "redis_streams" — RedisStreamsEventStore
    - "postgres"      — PostgresEventStore

The default preserves the existing runtime behavior of the /chat endpoint.
"""
from __future__ import annotations

import os
import logging

logger = logging.getLogger(__name__)


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
