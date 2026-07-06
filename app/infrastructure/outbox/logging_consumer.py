from __future__ import annotations

import logging

from app.infrastructure.outbox.outbox_dispatcher import OutboxEvent

logger = logging.getLogger("app.infrastructure.outbox.logging_consumer")


class LoggingOutboxConsumer:
    def __init__(self, consumer_name: str) -> None:
        if not consumer_name or not consumer_name.strip():
            raise ValueError("consumer_name must not be empty")
        self._consumer_name = consumer_name

    async def handle(self, event: OutboxEvent) -> None:
        payload = {
            "consumer_name": self._consumer_name,
            "outbox_id": event.outbox_id,
            "event_id": event.event_id,
            "event_type": event.event_type,
            "stream_id": event.stream_id,
            "stream_version": event.stream_version,
            "aggregate_id": event.aggregate_id,
        }
        logger.info("outbox_event_handled", extra=payload)
