"""The async connection pool and the only two raw statements Python is allowed to run.

``open_pool`` builds an :class:`AsyncConnectionPool`; the configure hook pins the session
time zone to UTC; a one-time role check at open warns when least privilege is being
bypassed. ``check_connection`` runs ``SELECT 1`` for readiness. The per-call statement
counter used by tests lives here too (``docs/01-architecture.md`` section 3).
"""

from __future__ import annotations

import contextvars
from typing import Any

import psycopg
import structlog
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from ..settings import Settings

Pool = AsyncConnectionPool[psycopg.AsyncConnection[dict[str, Any]]]

logger = structlog.get_logger("xcode_api.db")

APPLICATION_NAME = "xcode-api"
EXPECTED_ROLE = "xcode_app"

# One counter per task/context: the gateway increments it per routine call so tests can
# assert the statement budget of an endpoint (docs/09-testing.md section 2).
statement_counter: contextvars.ContextVar[int] = contextvars.ContextVar(
    "xcode_statement_counter", default=0
)


def reset_statement_counter() -> None:
    statement_counter.set(0)


def increment_statement_counter(by: int = 1) -> None:
    statement_counter.set(statement_counter.get() + by)


def current_statement_count() -> int:
    return statement_counter.get()


class StatementCounter:
    """The counter as the composition root hands it to the request middleware: reset at
    the start of a request, read for the request log line."""

    def reset(self) -> None:
        reset_statement_counter()

    def current(self) -> int:
        return current_statement_count()


async def _configure(conn: psycopg.AsyncConnection[Any]) -> None:
    # Connections are autocommit; the gateway wraps every routine call in an explicit
    # transaction (one call = one transaction). The configure hook must leave the connection
    # idle (no open transaction), which autocommit guarantees.
    await conn.set_autocommit(True)
    conn.row_factory = dict_row
    await conn.execute("SET TIME ZONE 'UTC'")


def open_pool(settings: Settings) -> Pool:
    """Build (but do not open) the pool. ``await pool.open()`` connects; the role check
    runs once right after, logging a warning when the connected role is not ``xcode_app``."""
    return AsyncConnectionPool(
        settings.database_url,
        min_size=settings.database_pool_min,
        max_size=settings.database_pool_max,
        kwargs={
            "application_name": APPLICATION_NAME,
            "row_factory": dict_row,
            "autocommit": True,
        },
        configure=_configure,
        open=False,
    )


def open_operator_pool(url: str) -> Pool:
    """Build (but do not open) the one-connection pool of a CLI user command, connected as
    ``xcode_operator`` through ``XCODE_DATABASE_OPERATOR_URL``."""
    return AsyncConnectionPool(
        url,
        min_size=1,
        max_size=1,
        kwargs={
            "application_name": f"{APPLICATION_NAME}-cli",
            "row_factory": dict_row,
            "autocommit": True,
        },
        configure=_configure,
        open=False,
    )


async def check_role(pool: Pool) -> str:
    """Return the connected role; warn if it is not ``xcode_app`` (least privilege bypassed)."""
    async with pool.connection() as conn:
        cur = await conn.execute("SELECT current_user AS role")
        row = await cur.fetchone()
    role = str(row["role"]) if row else ""
    if role != EXPECTED_ROLE:
        logger.warning("db.role_unexpected", role=role, expected=EXPECTED_ROLE)
    return role


async def check_connection(pool: Pool, timeout_seconds: float) -> None:
    """Run ``SELECT 1`` within ``timeout_seconds``; raise on failure or timeout."""
    async with pool.connection(timeout=timeout_seconds) as conn:
        await conn.execute("SELECT 1")
