from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from .artifact import Artifact, now_utc


@dataclass(frozen=True)
class ArtifactLookupResult:
    artifact: Artifact | None = None
    is_expired: bool = False

    @property
    def is_found(self) -> bool:
        return self.artifact is not None and not self.is_expired


class ArtifactStore(Protocol):
    """Port/interface for artifact storage.

    Single-worker only. Does not survive process restart.
    """

    async def register(self, artifact: Artifact) -> None:
        ...

    async def lookup(
        self,
        artifact_id: str,
        *,
        now: datetime | None = None,
    ) -> ArtifactLookupResult:
        ...

    async def delete(self, artifact_id: str) -> bool:
        ...


class InMemoryArtifactStore:
    """In-memory artifact store.

    NOT thread-safe across multiple workers.
    NOT persistent across process restarts.
    Use only for local/single-worker development.
    """

    _MAX_ITEMS = 100
    _MAX_TOTAL_BYTES = 500 * 1024 * 1024

    def __init__(self) -> None:
        self._items: dict[str, Artifact] = {}
        self._lock = asyncio.Lock()
        self._total_bytes = 0

    async def register(self, artifact: Artifact) -> None:
        async with self._lock:
            if len(self._items) >= self._MAX_ITEMS:
                raise ValueError(
                    f"Store atingiu o limite de {self._MAX_ITEMS} itens."
                )
            if self._total_bytes + artifact.size_bytes > self._MAX_TOTAL_BYTES:
                raise ValueError(
                    f"Store atingiu o limite de {self._MAX_TOTAL_BYTES} bytes."
                )
            self._items[artifact.artifact_id] = artifact
            self._total_bytes += artifact.size_bytes

    async def lookup(
        self,
        artifact_id: str,
        *,
        now: datetime | None = None,
    ) -> ArtifactLookupResult:
        async with self._lock:
            item = self._items.get(artifact_id)
        if item is None:
            return ArtifactLookupResult(artifact=None, is_expired=False)
        if item.is_expired(now):
            async with self._lock:
                self._items.pop(artifact_id, None)
                self._total_bytes = max(
                    0, self._total_bytes - item.size_bytes
                )
            return ArtifactLookupResult(artifact=None, is_expired=True)
        return ArtifactLookupResult(artifact=item, is_expired=False)

    async def delete(self, artifact_id: str) -> bool:
        async with self._lock:
            item = self._items.pop(artifact_id, None)
            if item is None:
                return False
            self._total_bytes = max(0, self._total_bytes - item.size_bytes)
            return True


_artifact_store_singleton: ArtifactStore | None = None


def get_artifact_store() -> ArtifactStore:
    global _artifact_store_singleton
    if _artifact_store_singleton is None:
        _artifact_store_singleton = InMemoryArtifactStore()
    return _artifact_store_singleton
