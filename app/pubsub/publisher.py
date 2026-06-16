"""
Async wrapper around google.cloud.pubsub_v1.PublisherClient.

Publishes agent responses to the outgoing topic. The synchronous
PublisherClient.publish() is dispatched to a thread via asyncio.to_thread
so the event loop is not blocked by gRPC.
"""

import asyncio
import json
import logging
from typing import Any

from google.cloud.pubsub_v1.publisher.client import Client as PublisherClient

from app.pubsub.schemas import OutgoingMessage


logger = logging.getLogger(__name__)


class AgentPublisher:
    def __init__(self, topic_name: str):
        self._topic_name = topic_name
        self._client: PublisherClient | None = None

    async def start(self) -> None:
        if self._client is not None:
            return

        self._client = PublisherClient()
        logger.info("Publisher started for topic=%s", self._topic_name)

    async def publish(self, message: OutgoingMessage) -> str:
        if self._client is None:
            raise RuntimeError("Publisher not started. Call start() first.")

        data = message.model_dump_json().encode("utf-8")
        attrs: dict[str, str] = {
            "request_id": message.request_id,
            "type": message.type,
        }

        future = self._client.publish(self._topic_name, data, **attrs)

        loop = asyncio.get_running_loop()
        message_id = await loop.run_in_executor(None, future.result, 30.0)

        logger.info(
            "Published outgoing message request_id=%s type=%s message_id=%s",
            message.request_id,
            message.type,
            message_id,
        )
        return message_id

    async def close(self) -> None:
        if self._client is None:
            return

        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self._client.stop)
        except Exception as e:
            logger.warning("Error closing publisher: %s", e)
        finally:
            self._client = None
            logger.info("Publisher closed")

    @staticmethod
    def serialize(message: OutgoingMessage) -> bytes:
        return json.dumps(message.model_dump(), default=str).encode("utf-8")


def build_publisher_from_config() -> AgentPublisher:
    from app.core.config import settings

    return AgentPublisher(topic_name=settings.PUBSUB_OUTGOING_TOPIC)
