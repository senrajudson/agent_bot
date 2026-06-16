"""
Pub/Sub worker entry point.

Usage:
    poetry run python -m app.worker_main
"""

import asyncio
import logging

from app.observability.phoenix import setup_phoenix_tracing
from app.pubsub.runner import run_pubsub_worker


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


setup_phoenix_tracing()


if __name__ == "__main__":
    asyncio.run(run_pubsub_worker())
