"""Fixed-window rate limiting backed by Redis."""

from __future__ import annotations

import time

from app.core.config import get_settings
from app.core.exceptions import RateLimitedError
from app.core.logging import get_logger
from app.core.redis import get_async_redis

logger = get_logger(__name__)


async def enforce_rate_limit(bucket: str, identity: str, limit_per_minute: int) -> None:
    settings = get_settings()
    if not settings.rate_limit_enabled or limit_per_minute <= 0:
        return
    window = int(time.time() // 60)
    key = f"rl:{bucket}:{identity}:{window}"
    try:
        client = get_async_redis()
        pipe = client.pipeline()
        pipe.incr(key)
        pipe.expire(key, 70)
        count, _ = await pipe.execute()
    except Exception:  # noqa: BLE001 - Redis outage policy is configurable
        if settings.rate_limit_fail_open:
            logger.warning("rate_limit_unavailable", extra={"bucket": bucket})
            return
        raise RateLimitedError("Rate limiting unavailable", code="RATE_LIMIT_UNAVAILABLE") from None
    if int(count) > limit_per_minute:
        retry_after = 60 - int(time.time()) % 60
        raise RateLimitedError(
            "Too many requests",
            headers={"Retry-After": str(retry_after)},
        )
