"""Redis-based distributed lock using SET NX EX."""
from __future__ import annotations

import uuid

from redis.asyncio import Redis

from app.infrastructure.locking.base import DistributedLock, LockStatus


class RedisDistributedLock:
    """Distributed lock using Redis SET NX EX.

    Uses SET key token NX EX ttl to atomically acquire a lock.
    Releases via Lua script that checks ownership.
    """

    RELEASE_SCRIPT = """
    if redis.call("get", KEYS[1]) == ARGV[1] then
        return redis.call("del", KEYS[1])
    else
        return 0
    end
    """

    def __init__(self, redis: Redis, prefix: str = "lock") -> None:
        self._redis = redis
        self._prefix = prefix
        self._tokens: dict[str, str] = {}

    def _key(self, name: str) -> str:
        return f"{self._prefix}:{name}"

    async def try_acquire(self, key: str, ttl_seconds: int) -> LockStatus:
        token = str(uuid.uuid4())
        full_key = self._key(key)
        result = await self._redis.set(
            name=full_key, value=token, ex=ttl_seconds, nx=True
        )
        if result:
            self._tokens[full_key] = token
            return LockStatus.ACQUIRED
        return LockStatus.ALREADY_HELD

    async def release(self, key: str) -> bool:
        full_key = self._key(key)
        token = self._tokens.pop(full_key, None)
        if token is None:
            return False
        result = await self._redis.eval(
            self.RELEASE_SCRIPT, 1, full_key, token
        )
        return result > 0

    async def is_held(self, key: str) -> bool:
        full_key = self._key(key)
        return bool(await self._redis.exists(full_key))
