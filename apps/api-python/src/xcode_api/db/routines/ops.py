"""``OpsRoutines``: the real ``OpsRepository``, one typed method per routine."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from psycopg.types.json import Jsonb
from psycopg_pool import AsyncConnectionPool

from ...application.errors import IntegrityBug
from ...application.ports import RateLimitDecision
from ...domain.identity import (
    AccountSummary,
    ClearedPause,
    DemoSeeding,
    OperatorRequest,
    ProvisionedUser,
    RemovedUser,
    RevokedSessions,
    SeededDemo,
    UserProvisioning,
)
from ..pool import check_connection
from ..session import call
from ..types import (
    account_summary,
    cleared_pause,
    provisioned_user,
    removed_user,
    revoked_sessions,
)

READINESS_BUDGET_SECONDS = 10.0
# The seed writes six weeks of history in one call; xcode_operator's own limit is 5 s.
SEED_TIMEOUT_SECONDS = 120


@dataclass(frozen=True, slots=True)
class _RateLimitRow:
    allowed: bool
    remaining: int
    retry_after_seconds: int


class OpsRoutines:
    """Operations and metadata routines: ops_*, meta_* and rate_limit_hit."""

    def __init__(self, pool: AsyncConnectionPool[Any]) -> None:
        self._pool = pool

    async def ping(self) -> None:
        await check_connection(self._pool, READINESS_BUDGET_SECONDS)

    async def contract_version(self) -> int:
        rows = await call(self._pool, "meta_contract_version", idempotent=True)
        if not rows:
            raise IntegrityBug("api.meta_contract_version returned no row")
        value = next(iter(rows[0].values()))
        return int(value)

    async def rate_limit_hit(
        self, key: str, limit: int, window_seconds: int, now: datetime
    ) -> RateLimitDecision:
        rows = await call(
            self._pool,
            "rate_limit_hit",
            key,
            limit,
            window_seconds,
            now,
            row=_RateLimitRow,
        )
        if not rows:
            raise IntegrityBug("api.rate_limit_hit returned no row")
        decided = rows[0]
        return RateLimitDecision(
            allowed=decided.allowed,
            remaining=decided.remaining,
            retry_after_seconds=decided.retry_after_seconds,
        )

    async def record_operator_action(
        self,
        operator: str,
        action: str,
        target: str,
        detail: Mapping[str, Any],
    ) -> None:
        await call(
            self._pool,
            "ops_record_operator_action",
            operator,
            action,
            target,
            Jsonb(dict(detail)),
            datetime.now(UTC),
        )

    async def provision_user(self, command: UserProvisioning) -> ProvisionedUser:
        rows = await call(
            self._pool,
            "ops_provision_user",
            command.operator,
            command.request_id,
            command.email,
            command.phone,
            command.role,
            command.first_name,
            command.last_name,
            command.organization_name,
            command.now,
        )
        return provisioned_user(_document(rows, "ops_provision_user"))

    async def remove_user(self, command: OperatorRequest) -> RemovedUser:
        return removed_user(await self._operator_call("ops_remove_user", command))

    async def clear_pause(self, command: OperatorRequest) -> ClearedPause:
        return cleared_pause(await self._operator_call("ops_clear_pause", command))

    async def revoke_sessions(self, command: OperatorRequest) -> RevokedSessions:
        return revoked_sessions(await self._operator_call("ops_revoke_sessions", command))

    async def account_state(self, command: OperatorRequest) -> AccountSummary:
        return account_summary(await self._operator_call("ops_account_state", command))

    async def unassigned_user_count(self) -> int:
        rows = await call(self._pool, "meta_unassigned_user_count")
        if not rows:
            raise IntegrityBug("api.meta_unassigned_user_count returned no row")
        return int(next(iter(rows[0].values())))

    async def seed_demo(self, command: DemoSeeding) -> SeededDemo:
        rows = await call(
            self._pool,
            "ops_seed_demo",
            command.operator,
            command.request_id,
            command.environment,
            Jsonb(dict(command.pin_hashes)),
            command.now,
            timeout_seconds=SEED_TIMEOUT_SECONDS,
        )
        document = _document(rows, "ops_seed_demo")
        return SeededDemo(
            organization_id=UUID(str(document["organization_id"])),
            created=bool(document["created"]),
        )

    async def _operator_call(self, routine: str, command: OperatorRequest) -> dict[str, Any]:
        rows = await call(
            self._pool, routine, command.operator, command.request_id, command.email, command.now
        )
        return _document(rows, routine)


def _document(rows: list[dict[str, Any]], routine: str) -> dict[str, Any]:
    if len(rows) != 1:
        raise IntegrityBug(f"api.{routine} returned {len(rows)} rows, expected one")
    value = rows[0].get(routine)
    if not isinstance(value, dict):
        raise IntegrityBug(f"api.{routine} returned no document")
    return value
