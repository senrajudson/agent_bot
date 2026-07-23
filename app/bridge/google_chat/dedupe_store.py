"""Dedupe store for Google Chat messages — uses DistributedLock."""
from __future__ import annotations

import logging
from typing import Literal

from redis.asyncio import Redis as AsyncRedis

from app.bridge.google_chat.config import (
    GoogleChatBridgeSettings,
    get_google_chat_bridge_settings,
)
from app.bridge.google_chat.models import GoogleChatIncomingMessage
from app.infrastructure.locking.base import DistributedLock, LockStatus

logger = logging.getLogger(__name__)

DedupeStatus = Literal["started", "duplicate_done", "duplicate_processing"]
AttachmentState = Literal["PENDING", "SENT", "FAILED_RETRYABLE", "FAILED_PERMANENT"]


class AttachmentDedupeStore:
    """Per-attachment idempotency store.

    Key format: ``attachment:{event_id}:{artifact_id}:{space}:{thread}``
    States: PENDING, SENT, FAILED_RETRYABLE, FAILED_PERMANENT
    TTL: 24 hours.
    """

    _STATE_TTL_SECONDS = 86400

    def __init__(self, redis: AsyncRedis, prefix: str = "google_chat:att_dedupe") -> None:
        self._redis = redis
        self._prefix = prefix

    def make_key(
        self,
        event_id: str,
        artifact_id: str,
        space: str | None = None,
        thread: str | None = None,
    ) -> str:
        space = space or "unknown"
        thread = thread or "unknown"
        return f"attachment:{event_id}:{artifact_id}:{space}:{thread}"

    async def start(self, key: str) -> bool:
        return await self._redis.set(key, "PENDING", nx=True, ex=self._STATE_TTL_SECONDS)

    async def mark_sent(self, key: str) -> None:
        await self._redis.set(key, "SENT", ex=self._STATE_TTL_SECONDS)

    async def mark_failed(self, key: str, permanent: bool = False) -> None:
        state = "FAILED_PERMANENT" if permanent else "FAILED_RETRYABLE"
        await self._redis.set(key, state, ex=self._STATE_TTL_SECONDS)

    async def get_state(self, key: str) -> AttachmentState | None:
        val = await self._redis.get(key)
        return val if val else None


class DedupeStore:
    """Dedupe store using DistributedLock (Redis-based).

    All lock operations are async — the caller (worker) must be
    inside an ``asyncio.run`` context.
    """

    def __init__(
        self,
        settings: GoogleChatBridgeSettings | None = None,
        lock: DistributedLock | None = None,
        processing_ttl_seconds: int = 900,
    ):
        self.settings = settings or get_google_chat_bridge_settings()
        self.processing_ttl_seconds = processing_ttl_seconds

        if lock is None:
            raise ValueError(
                "DedupeStore requires a DistributedLock. "
                "Pass a RedisDistributedLock or InMemoryDistributedLock."
            )
        self._lock = lock

    async def try_start(self, event: GoogleChatIncomingMessage) -> DedupeStatus:
        message_key = self._message_key(event)
        done_key = self._done_key(message_key)
        processing_key = self._processing_key(message_key)

        # Check if already done
        if await self._lock.is_held(done_key):
            return "duplicate_done"

        # Try acquire processing lock
        status = await self._lock.try_acquire(processing_key, self.processing_ttl_seconds)
        if status == LockStatus.ALREADY_HELD:
            return "duplicate_processing"

        return "started"

    async def mark_done(self, event: GoogleChatIncomingMessage) -> None:
        message_key = self._message_key(event)
        done_key = self._done_key(message_key)
        processing_key = self._processing_key(message_key)

        # Set done marker (long TTL)
        await self._lock.try_acquire(done_key, self.settings.google_chat_dedupe_ttl_seconds)
        # Release processing
        await self._lock.release(processing_key)

    async def release_processing(self, event: GoogleChatIncomingMessage) -> None:
        message_key = self._message_key(event)
        processing_key = self._processing_key(message_key)
        await self._lock.release(processing_key)

    def _message_key(self, event: GoogleChatIncomingMessage) -> str:
        return event.message_name or event.pubsub_message_id

    @staticmethod
    def _done_key(message_key: str) -> str:
        return f"google_chat:dedupe:done:{message_key}"

    @staticmethod
    def _processing_key(message_key: str) -> str:
        return f"google_chat:dedupe:processing:{message_key}"
