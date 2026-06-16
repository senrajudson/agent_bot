"""
Async wrapper around google.cloud.pubsub_v1.SubscriberClient.

Uses streaming pull with FlowControl for concurrency limiting.
The synchronous callback is bridged to the asyncio event loop via
asyncio.run_coroutine_threadsafe so the handler can be a coroutine.
"""

import asyncio
import logging
from typing import Awaitable, Callable

from google.cloud.pubsub_v1.subscriber.client import Client as SubscriberClient
from google.cloud.pubsub_v1.subscriber.message import Message
from google.cloud.pubsub_v1.types import FlowControl


logger = logging.getLogger(__name__)


AsyncHandler = Callable[[Message], Awaitable[None]]


class AgentSubscriber:
    def __init__(
        self,
        subscription_name: str,
        max_in_flight: int = 4,
    ):
        self._subscription_name = subscription_name
        self._max_in_flight = max_in_flight
        self._client: SubscriberClient | None = None
        self._streaming_future = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._inflight: set[asyncio.Task] = set()
        self._inflight_lock = asyncio.Lock()

    async def start(self, handler: AsyncHandler) -> None:
        if self._client is not None:
            return

        self._loop = asyncio.get_running_loop()
        self._client = SubscriberClient()

        flow_control = FlowControl(
            max_messages=self._max_in_flight,
            max_acks_per_request=self._max_in_flight,
        )

        def _on_message(message: Message) -> None:
            if self._loop is None:
                message.nack()
                return

            task = self._loop.create_task(self._dispatch(handler, message))
            self._inflight.add(task)
            task.add_done_callback(self._on_task_done)

        def _on_callback_error(exc: Exception) -> None:
            logger.error("Subscriber callback error: %s", exc, exc_info=True)

        self._streaming_future = self._client.subscribe(
            self._subscription_name,
            callback=_on_message,
            flow_control=flow_control,
        )
        self._streaming_future.add_done_callback(_on_callback_error)

        logger.info(
            "Subscriber started for subscription=%s max_in_flight=%d",
            self._subscription_name,
            self._max_in_flight,
        )

    async def _dispatch(self, handler: AsyncHandler, message: Message) -> None:
        try:
            await handler(message)
        except Exception as e:
            logger.exception("Handler raised exception, nacking message: %s", e)
            try:
                message.nack()
            except Exception:
                logger.exception("Failed to nack message")

    def _on_task_done(self, task: asyncio.Task) -> None:
        self._inflight.discard(task)
        if not task.cancelled() and task.exception() is not None:
            logger.error("Task ended with error: %s", task.exception())

    async def stop(self, timeout: float = 30.0) -> None:
        if self._client is None:
            return

        if self._streaming_future is not None:
            try:
                self._streaming_future.cancel()
            except Exception:
                logger.exception("Error cancelling streaming pull")

        if self._inflight:
            logger.info("Waiting for %d in-flight handlers (timeout=%.1fs)", len(self._inflight), timeout)
            try:
                await asyncio.wait_for(
                    asyncio.gather(*self._inflight, return_exceptions=True),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                logger.warning("In-flight handlers did not finish within timeout; cancelling")
                for task in self._inflight:
                    task.cancel()

        try:
            self._client.close()
        except Exception:
            logger.exception("Error closing subscriber client")

        self._client = None
        self._streaming_future = None
        self._loop = None
        logger.info("Subscriber closed")

    @property
    def inflight_count(self) -> int:
        return len(self._inflight)


def build_subscriber_from_config() -> AgentSubscriber:
    from app.core.config import settings

    return AgentSubscriber(
        subscription_name=settings.PUBSUB_INCOMING_SUBSCRIPTION,
        max_in_flight=settings.PUBSUB_WORKER_CONCURRENCY,
    )
