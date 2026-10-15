"""Shared rate-limiter contract, run against both adapters.

The behavioural cases are exported as ``CONTRACT_CASES`` (each an async function taking a
``RateLimiter``) so ``tests/db/test_rate_limit_postgres.py`` runs the very same cases
against the PostgreSQL routine. ``ADAPTERS`` lists the adapter factories.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

import pytest

from xcode_api.application.ports import RateLimiter
from xcode_api.infra.rate_limit import MemoryRateLimiter, PostgresRateLimiter

from ..support.fakes import FakeOpsRepository

T0 = datetime(2026, 10, 7, 9, 0, 0, tzinfo=UTC)
LATER = datetime(2026, 10, 7, 9, 1, 0, tzinfo=UTC)
PARTWAY = datetime(2026, 10, 7, 9, 0, 45, tzinfo=UTC)


async def case_first_hit_is_allowed(limiter: RateLimiter) -> None:
    decision = await limiter.hit("k", 2, 60, T0)
    assert decision.allowed
    assert decision.remaining == 1


async def case_window_fills_and_refuses(limiter: RateLimiter) -> None:
    for _ in range(2):
        assert (await limiter.hit("k", 2, 60, T0)).allowed
    refused = await limiter.hit("k", 2, 60, T0)
    assert not refused.allowed
    assert refused.remaining == 0
    assert refused.retry_after_seconds > 0


async def case_new_window_resets_the_count(limiter: RateLimiter) -> None:
    await limiter.hit("k", 1, 60, T0)
    assert not (await limiter.hit("k", 1, 60, T0)).allowed
    assert (await limiter.hit("k", 1, 60, LATER)).allowed


async def case_retry_after_is_seconds_to_window_end(limiter: RateLimiter) -> None:
    await limiter.hit("k", 1, 60, PARTWAY)
    refused = await limiter.hit("k", 1, 60, PARTWAY)
    assert refused.retry_after_seconds == 15


async def case_keys_are_independent(limiter: RateLimiter) -> None:
    await limiter.hit("a", 1, 60, T0)
    assert (await limiter.hit("b", 1, 60, T0)).allowed


CONTRACT_CASES: list[Callable[[RateLimiter], Awaitable[None]]] = [
    case_first_hit_is_allowed,
    case_window_fills_and_refuses,
    case_new_window_resets_the_count,
    case_retry_after_is_seconds_to_window_end,
    case_keys_are_independent,
]


def _memory() -> RateLimiter:
    return MemoryRateLimiter()


def _postgres_fake() -> RateLimiter:
    # The fake ops always allows; it exercises the delegation path only. The real window
    # behaviour of PostgresRateLimiter is proven against the routine in tests/db.
    return PostgresRateLimiter(FakeOpsRepository())


ADAPTERS: list[Callable[[], RateLimiter]] = [_memory, _postgres_fake]


@pytest.mark.parametrize("case", CONTRACT_CASES, ids=lambda c: c.__name__)
async def test_memory_adapter_honours_each_case(
    case: Callable[[RateLimiter], Awaitable[None]],
) -> None:
    await case(MemoryRateLimiter())


@pytest.mark.parametrize("make_limiter", ADAPTERS)
async def test_both_adapters_honour_the_port(
    make_limiter: Callable[[], RateLimiter],
) -> None:
    limiter = make_limiter()
    decision = await limiter.hit("k", 5, 60, T0)
    assert decision.allowed
    assert decision.remaining >= 0
    assert decision.retry_after_seconds >= 0


def test_contract_adapters_cover_both_implementations() -> None:
    kinds = {type(make()).__name__ for make in ADAPTERS}
    assert kinds == {"MemoryRateLimiter", "PostgresRateLimiter"}
