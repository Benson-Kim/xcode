"""The PostgreSQL rate limiter against the real routine: the shared contract cases
(``tests/unit/test_rate_limiter_contract.py``) run against ``PostgresRateLimiter`` backed by
``api.rate_limit_hit`` (``docs/02-stack.md`` ADR-10, ``docs/09-testing.md`` section 1)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import pytest
from psycopg_pool import AsyncConnectionPool

from xcode_api.application.ports import RateLimiter
from xcode_api.db.routines.ops import OpsRoutines
from xcode_api.infra.rate_limit import PostgresRateLimiter

from ..unit.test_rate_limiter_contract import CONTRACT_CASES


@pytest.mark.parametrize("case", CONTRACT_CASES, ids=lambda c: c.__name__)
async def test_postgres_adapter_honours_each_case(
    case: Callable[[RateLimiter], Awaitable[None]],
    pool: AsyncConnectionPool[object],
) -> None:
    limiter = PostgresRateLimiter(OpsRoutines(pool))
    await case(limiter)
