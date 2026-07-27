from redis.asyncio import Redis

from domain.core.config import get_domain_settings


_redis_client: Redis | None = None


def get_redis_client() -> Redis:
    global _redis_client

    if _redis_client is None:
        _redis_client = Redis.from_url(
            get_domain_settings().REDIS_URL,
            decode_responses=True,
        )

    return _redis_client