"""Readiness use case: does the database answer within the budget, with the routine
contract this package expects?"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from ..ports import Clock, RateLimiter
from ..repositories import OpsRepository

READINESS_BUDGET_SECONDS = 10.0
# A window of its own: the probe proves the shared limiter answers, never charges a client.
READINESS_LIMIT_KEY = "health:ready"
READINESS_LIMIT_WINDOW_SECONDS = 60
READINESS_LIMIT = 2_147_483_647


@dataclass(frozen=True, slots=True)
class ReadinessReport:
    """Outcome of a readiness probe. ``reason`` is for the log only, never the client."""

    ready: bool
    reason: str | None = None


class CheckReadiness:
    """Probes the database through ``OpsRepository`` within a bounded budget.

    Ready means ``ping`` succeeded, ``contract_version`` equals the version the package
    expects (a routine deployment that moved the contract takes the process out of
    rotation instead of letting it call routines it does not know) and, when a shared
    limiter is given (``XCODE_RATE_LIMIT_BACKEND=postgres``), it answers. ``execute`` never
    raises: a failure, a timeout or a mismatch becomes ``ReadinessReport(ready=False)``
    with the reason recorded for logging. The HTTP layer maps it to 200/503.
    """

    def __init__(
        self,
        ops: OpsRepository,
        *,
        expected_contract_version: int,
        budget_seconds: float = READINESS_BUDGET_SECONDS,
        shared_limiter: tuple[RateLimiter, Clock] | None = None,
    ):
        self._ops = ops
        self._expected_contract_version = expected_contract_version
        self._budget_seconds = budget_seconds
        self._shared_limiter = shared_limiter

    async def execute(self) -> ReadinessReport:
        try:
            version = await asyncio.wait_for(self._probe(), timeout=self._budget_seconds)
        except TimeoutError:
            return ReadinessReport(ready=False, reason="database probe timed out")
        except Exception as exc:
            return ReadinessReport(ready=False, reason=f"{type(exc).__name__}: {exc}")
        if version != self._expected_contract_version:
            return ReadinessReport(
                ready=False,
                reason=(
                    f"routine contract version {version} != "
                    f"expected {self._expected_contract_version}"
                ),
            )
        return ReadinessReport(ready=True)

    async def _probe(self) -> int:
        await self._ops.ping()
        version = await self._ops.contract_version()
        if self._shared_limiter is not None:
            limiter, clock = self._shared_limiter
            await limiter.hit(
                READINESS_LIMIT_KEY, READINESS_LIMIT, READINESS_LIMIT_WINDOW_SECONDS, clock.now()
            )
        return version
