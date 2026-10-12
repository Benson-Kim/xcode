"""The per-call transaction helper: one routine call is one transaction.

``call`` is the only place a routine is invoked. It opens one transaction, binds arguments
server-side, adapts the result rows, counts the call for the statement budget, retries
idempotent calls on transient SQLSTATEs with jittered backoff, and translates every other
SQLSTATE through ``db/errors.py``. It logs ``db.routine`` at DEBUG with the routine name and
duration, never the arguments (``docs/08-operability.md`` section 2).
"""

from __future__ import annotations

import asyncio
import re
import secrets
import time
from collections.abc import Sequence
from typing import Any, overload

import psycopg
import structlog
from psycopg_pool import AsyncConnectionPool

from ..application.observability import report_routine
from .errors import is_transient_error, translate
from .pool import increment_statement_counter
from .types import adapt_row

logger = structlog.get_logger("xcode_api.db")

MAX_ATTEMPTS = 3
BACKOFF_BASE_SECONDS = 0.05

_ROUTINE_NAME = re.compile(r"^[a-z_][a-z0-9_]*$")


@overload
async def call[T](
    pool: AsyncConnectionPool[Any],
    routine: str,
    *args: Any,
    row: type[T],
    idempotent: bool = ...,
    timeout_seconds: int | None = ...,
) -> list[T]: ...


@overload
async def call(
    pool: AsyncConnectionPool[Any],
    routine: str,
    *args: Any,
    row: None = ...,
    idempotent: bool = ...,
    timeout_seconds: int | None = ...,
) -> list[dict[str, Any]]: ...


async def call[T](
    pool: AsyncConnectionPool[Any],
    routine: str,
    *args: Any,
    row: type[T] | None = None,
    idempotent: bool = False,
    timeout_seconds: int | None = None,
) -> list[T] | list[dict[str, Any]]:
    """Call ``api.<routine>(...)`` in one transaction and return its adapted rows.

    ``timeout_seconds`` replaces the role's ``statement_timeout`` for this transaction only;
    the development demo seed is the one caller that needs longer than its role allows.
    """
    if not _ROUTINE_NAME.match(routine):
        raise ValueError(f"illegal routine name: {routine!r}")
    placeholders = ", ".join(["%s"] * len(args))
    # Safe: the routine name is regex-validated above and every argument is bound with %s.
    statement = f"SELECT * FROM api.{routine}({placeholders})"  # noqa: S608

    attempt = 0
    while True:
        attempt += 1
        started = time.perf_counter()
        try:
            rows = await _execute(pool, statement, args, timeout_seconds)
        except psycopg.Error as exc:
            report_routine(routine, time.perf_counter() - started)
            if idempotent and is_transient_error(exc) and attempt < MAX_ATTEMPTS:
                await asyncio.sleep(_backoff(attempt))
                continue
            raise translate(exc) from exc
        duration_ms = (time.perf_counter() - started) * 1000
        report_routine(routine, duration_ms / 1000)
        increment_statement_counter()
        logger.debug("db.routine", routine=routine, duration_ms=round(duration_ms, 3))
        if row is None:
            return rows
        return [adapt_row(r, row) for r in rows]


async def _execute(
    pool: AsyncConnectionPool[Any],
    statement: str,
    args: Sequence[Any],
    timeout_seconds: int | None = None,
) -> list[dict[str, Any]]:
    async with pool.connection() as conn, conn.transaction():
        if timeout_seconds is not None:
            await conn.execute(
                "SELECT set_config('statement_timeout', %s, true)", [f"{timeout_seconds}s"]
            )
        cur = await conn.execute(statement, list(args))
        if cur.description is None:
            return []
        fetched = await cur.fetchall()
        return [dict(r) for r in fetched]


def _backoff(attempt: int) -> float:
    ceiling: float = BACKOFF_BASE_SECONDS * float(2 ** (attempt - 1))
    jitter: float = secrets.randbelow(1000) / 1000.0
    return jitter * ceiling
