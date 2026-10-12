"""Rate-limiter adapters: in-process fixed window and a PostgreSQL-backed delegate.

Both honour the :class:`~xcode_api.application.ports.RateLimiter` contract and pass the
shared contract cases in ``tests/unit/test_rate_limiter_contract.py``.
"""

from __future__ import annotations

import math
from datetime import datetime

from ..application.ports import RateLimitDecision
from ..application.repositories import OpsRepository


def _window_start(now: datetime, window_seconds: int) -> int:
    epoch = int(now.timestamp())
    return (epoch // window_seconds) * window_seconds


class MemoryRateLimiter:
    """Fixed-window limiter with per-process counters.

    The window a hit falls in is ``floor(now / window_seconds) * window_seconds``. Counters
    for windows older than two windows are evicted on each hit so the map stays bounded.
    Correct only within one process; use :class:`PostgresRateLimiter` across replicas.
    """

    def __init__(self) -> None:
        self._counts: dict[tuple[str, int], int] = {}

    async def hit(
        self, key: str, limit: int, window_seconds: int, now: datetime
    ) -> RateLimitDecision:
        start = _window_start(now, window_seconds)
        self._evict(start, window_seconds)
        bucket = (key, start)
        used = self._counts.get(bucket, 0) + 1
        self._counts[bucket] = used
        window_end = start + window_seconds
        retry_after = max(0, math.ceil(window_end - now.timestamp()))
        if used > limit:
            return RateLimitDecision(allowed=False, remaining=0, retry_after_seconds=retry_after)
        return RateLimitDecision(
            allowed=True, remaining=limit - used, retry_after_seconds=retry_after
        )

    def _evict(self, current_start: int, window_seconds: int) -> None:
        cutoff = current_start - 2 * window_seconds
        stale = [bucket for bucket in self._counts if bucket[1] < cutoff]
        for bucket in stale:
            del self._counts[bucket]


class PostgresRateLimiter:
    """Delegates to ``OpsRepository.rate_limit_hit`` (routine ``api.rate_limit_hit``).

    Correct across replicas because the counter lives in the database; this adapter only
    forwards the call and the window parameters.
    """

    def __init__(self, ops: OpsRepository) -> None:
        self._ops = ops

    async def hit(
        self, key: str, limit: int, window_seconds: int, now: datetime
    ) -> RateLimitDecision:
        return await self._ops.rate_limit_hit(key, limit, window_seconds, now)
