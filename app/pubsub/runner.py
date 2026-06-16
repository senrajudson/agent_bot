"""
Pub/Sub worker lifecycle.

Boots the publisher + subscriber, wires the worker handler, and handles
SIGTERM/SIGINT for graceful shutdown.
"""

import asyncio
import logging
import signal
from typing import Awaitable, Callable

from app.core.config import settings
from app.pubsub.publisher import AgentPublisher, build_publisher_from_config
from app.pubsub.subscriber import AgentSubscriber, build_subscriber_from_config
from app.pubsub.worker import handle_incoming


logger = logging.getLogger(__name__)


async def run_pubsub_worker() -> None:
    if not settings.PUBSUB_ENABLED:
        logger.warning(
            "PUBSUB_ENABLED=false. Worker will not start. "
            "Set PUBSUB_ENABLED=true in .env to enable."
        )
        return

    if not settings.PUBSUB_INCOMING_SUBSCRIPTION or not settings.PUBSUB_OUTGOING_TOPIC:
        raise RuntimeError(
            "PUBSUB_INCOMING_SUBSCRIPTION and PUBSUB_OUTGOING_TOPIC must be set."
        )

    publisher: AgentPublisher = build_publisher_from_config()
    subscriber: AgentSubscriber = build_subscriber_from_config()

    await publisher.start()

    loop = asyncio.get_running_loop()

    stop_event = asyncio.Event()

    def _request_stop() -> None:
        logger.info("Shutdown signal received")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _request_stop)
        except NotImplementedError:
            signal.signal(sig, lambda *_: _request_stop())

    try:
        await subscriber.start(
            handler=lambda msg: handle_incoming(msg, publisher),
        )
        logger.info(
            "Pub/Sub worker running. subscription=%s topic=%s concurrency=%d",
            settings.PUBSUB_INCOMING_SUBSCRIPTION,
            settings.PUBSUB_OUTGOING_TOPIC,
            settings.PUBSUB_WORKER_CONCURRENCY,
        )

        await stop_event.wait()
        logger.info("Stopping Pub/Sub worker...")

    finally:
        await subscriber.stop(timeout=settings.PUBSUB_SHUTDOWN_TIMEOUT_SECONDS)
        await publisher.close()
        logger.info("Pub/Sub worker stopped cleanly")


__all__ = ["run_pubsub_worker"]
