"""Dedupe store for Google Chat messages — uses DistributedLock."""
from __future__ import annotations

import logging
from typing import Literal

from app.bridge.google_chat.config import (
    GoogleChatBridgeSettings,
    get_google_chat_bridge_settings,
)
from app.bridge.google_chat.models import GoogleChatIncomingMessage
from app.infrastructure.locking.base import DistributedLock, LockStatus

logger = logging.getLogger(__name__)

DedupeStatus = Literal["started", "duplicate_done", "duplicate_processing"]


class DedupeStore:
    """Dedupe store using DistributedLock (Redis-based).

    Eliminates the in-memory fallback that breaks in multi-worker (P1 #11).
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

    def try_start(self, event: GoogleChatIncomingMessage) -> DedupeStatus:
        message_key = self._message_key(event)
        done_key = self._done_key(message_key)
        processing_key = self._processing_key(message_key)

        # Check if already done
        is_done = self._is_held(done_key)
        if is_done:
            return "duplicate_done"

        # Try acquire processing lock
        status = self._acquire(processing_key, self.processing_ttl_seconds)
        if status == LockStatus.ALREADY_HELD:
            return "duplicate_processing"

        return "started"

    def mark_done(self, event: GoogleChatIncomingMessage) -> None:
        message_key = self._message_key(event)
        done_key = self._done_key(message_key)
        processing_key = self._processing_key(message_key)

        # Set done marker (long TTL)
        self._acquire(done_key, self.settings.google_chat_dedupe_ttl_seconds)
        # Release processing
        self._release(processing_key)

    def release_processing(self, event: GoogleChatIncomingMessage) -> None:
        message_key = self._message_key(event)
        processing_key = self._processing_key(message_key)
        self._release(processing_key)

    def _message_key(self, event: GoogleChatIncomingMessage) -> str:
        return event.message_name or event.pubsub_message_id

    @staticmethod
    def _done_key(message_key: str) -> str:
        return f"google_chat:dedupe:done:{message_key}"

    @staticmethod
    def _processing_key(message_key: str) -> str:
        return f"google_chat:dedupe:processing:{message_key}"

    def _acquire(self, key: str, ttl: int) -> LockStatus:
        if hasattr(self._lock, 'try_acquire_sync'):
            return self._lock.try_acquire_sync(key, ttl)
        import asyncio
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(self._lock.try_acquire(key, ttl))
        finally:
            loop.close()

    def _release(self, key: str) -> bool:
        if hasattr(self._lock, 'release_sync'):
            return self._lock.release_sync(key)
        import asyncio
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(self._lock.release(key))
        finally:
            loop.close()

    def _is_held(self, key: str) -> bool:
        if hasattr(self._lock, 'is_held_sync'):
            return self._lock.is_held_sync(key)
        import asyncio
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(self._lock.is_held(key))
        finally:
            loop.close()
