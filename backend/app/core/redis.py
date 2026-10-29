from __future__ import annotations

from functools import lru_cache

import redis
import redis.asyncio as aioredis

from app.core.config import get_settings


@lru_cache(maxsize=1)
def get_async_redis() -> aioredis.Redis:
    return aioredis.from_url(
        get_settings().redis_url,
        socket_timeout=2,
        socket_connect_timeout=2,
        health_check_interval=30,
        decode_responses=True,
    )


@lru_cache(maxsize=1)
def get_sync_redis() -> redis.Redis:
    return redis.from_url(
        get_settings().redis_url,
        socket_timeout=5,
        socket_connect_timeout=5,
        health_check_interval=30,
        decode_responses=True,
    )
