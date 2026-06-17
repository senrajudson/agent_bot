from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Literal

from app.bridge.google_chat.config import (
    GoogleChatBridgeSettings,
    get_google_chat_bridge_settings,
)
from app.bridge.google_chat.models import GoogleChatIncomingMessage

logger = logging.getLogger(__name__)

DedupeStatus = Literal["started", "duplicate_done", "duplicate_processing"]


@dataclass(slots=True)
class MemoryEntry:
    value: str
    expires_at: float


class DedupeStore:
    def __init__(
        self,
        settings: GoogleChatBridgeSettings | None = None,
        processing_ttl_seconds: int = 900,
    ):
        self.settings = settings or get_google_chat_bridge_settings()
        self.processing_ttl_seconds = processing_ttl_seconds

        self._redis = None
        self._memory: dict[str, MemoryEntry] = {}

        self._init_redis()

    def _init_redis(self) -> None:
        if not self.settings.redis_url:
            logger.warning("REDIS_URL não configurado. Usando dedupe em memória.")
            return

        try:
            import redis

            self._redis = redis.Redis.from_url(
                self.settings.redis_url,
                decode_responses=True,
            )

            self._redis.ping()

            logger.info("Dedupe Redis habilitado. url=%s", self.settings.redis_url)

        except Exception as exc:
            self._redis = None

            logger.warning(
                "Não foi possível conectar no Redis. "
                "Usando dedupe em memória. erro=%s",
                exc,
            )

    def try_start(self, event: GoogleChatIncomingMessage) -> DedupeStatus:
        message_key = self._message_key(event)

        done_key = self._done_key(message_key)
        processing_key = self._processing_key(message_key)

        if self._exists(done_key):
            return "duplicate_done"

        started = self._set_if_absent(
            key=processing_key,
            value="processing",
            ttl_seconds=self.processing_ttl_seconds,
        )

        if not started:
            return "duplicate_processing"

        return "started"

    def mark_done(self, event: GoogleChatIncomingMessage) -> None:
        message_key = self._message_key(event)

        done_key = self._done_key(message_key)
        processing_key = self._processing_key(message_key)

        self._set(
            key=done_key,
            value="done",
            ttl_seconds=self.settings.google_chat_dedupe_ttl_seconds,
        )

        self._delete(processing_key)

    def release_processing(self, event: GoogleChatIncomingMessage) -> None:
        message_key = self._message_key(event)
        processing_key = self._processing_key(message_key)

        self._delete(processing_key)

    def _message_key(self, event: GoogleChatIncomingMessage) -> str:
        return event.message_name or event.pubsub_message_id

    @staticmethod
    def _done_key(message_key: str) -> str:
        return f"google_chat:dedupe:done:{message_key}"

    @staticmethod
    def _processing_key(message_key: str) -> str:
        return f"google_chat:dedupe:processing:{message_key}"

    def _exists(self, key: str) -> bool:
        if self._redis is not None:
            try:
                return bool(self._redis.exists(key))
            except Exception as exc:
                logger.warning("Falha ao consultar Redis. key=%s erro=%s", key, exc)

        self._cleanup_memory()
        entry = self._memory.get(key)

        if entry is None:
            return False

        if entry.expires_at <= time.time():
            self._memory.pop(key, None)
            return False

        return True

    def _set_if_absent(
        self,
        key: str,
        value: str,
        ttl_seconds: int,
    ) -> bool:
        if self._redis is not None:
            try:
                return bool(
                    self._redis.set(
                        name=key,
                        value=value,
                        ex=ttl_seconds,
                        nx=True,
                    )
                )
            except Exception as exc:
                logger.warning("Falha ao gravar Redis NX. key=%s erro=%s", key, exc)

        self._cleanup_memory()

        if self._exists(key):
            return False

        self._memory[key] = MemoryEntry(
            value=value,
            expires_at=time.time() + ttl_seconds,
        )

        return True

    def _set(
        self,
        key: str,
        value: str,
        ttl_seconds: int,
    ) -> None:
        if self._redis is not None:
            try:
                self._redis.set(
                    name=key,
                    value=value,
                    ex=ttl_seconds,
                )
                return
            except Exception as exc:
                logger.warning("Falha ao gravar Redis. key=%s erro=%s", key, exc)

        self._cleanup_memory()

        self._memory[key] = MemoryEntry(
            value=value,
            expires_at=time.time() + ttl_seconds,
        )

    def _delete(self, key: str) -> None:
        if self._redis is not None:
            try:
                self._redis.delete(key)
                return
            except Exception as exc:
                logger.warning("Falha ao remover chave Redis. key=%s erro=%s", key, exc)

        self._memory.pop(key, None)

    def _cleanup_memory(self) -> None:
        now = time.time()

        expired_keys = [
            key
            for key, entry in self._memory.items()
            if entry.expires_at <= now
        ]

        for key in expired_keys:
            self._memory.pop(key, None)