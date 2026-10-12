"""Row-level security on every tenant table (``docs/03-database.md`` section 3).

Statements run as ``xcode_api_executor`` (an owner connection after ``SET ROLE``), the role
every routine runs as, with ``xcode.organization_id`` set directly by ``set_config`` the way
``tenancy.enter_organization`` will set it. Organization A's rows are invisible with B's id
and with no id; a row naming another organization cannot be inserted or moved there.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from uuid import UUID

import psycopg
import pytest
from psycopg import sql
from psycopg.types.json import Jsonb

from xcode_api.db.schema_spec import TABLES, TableSpec

from ..support.database import executor_connection
from ..support.rows import OrganizationRows, seed_organization

Conn = psycopg.Connection[dict[str, Any]]

TENANT_TABLES = [t for t in TABLES if t.tenant]


@contextmanager
def _session(conn: Conn, organization: UUID | None) -> Iterator[None]:
    with conn.transaction(force_rollback=True):
        if organization is not None:
            conn.execute(
                "SELECT set_config('xcode.organization_id', %s, true)", (str(organization),)
            )
        yield


def _refusal(conn: Conn, organization: UUID | None, statement: sql.Composed, params: Any) -> str:
    with pytest.raises(psycopg.Error) as caught:
        with _session(conn, organization):
            conn.execute(statement, params)
    assert caught.value.sqlstate == "42501", caught.value
    return caught.value.diag.message_primary or ""


def _count(conn: Conn, table: TableSpec, where: sql.Composable, params: Any = None) -> int:
    query = sql.SQL("SELECT count(*) AS n FROM {} WHERE {}").format(
        sql.Identifier(table.schema, table.name), where
    )
    row = conn.execute(query, params).fetchone()
    assert row is not None
    return int(row["n"])


def _insertable_columns(owner: Conn, table: TableSpec) -> list[str]:
    rows = owner.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = %s AND table_name = %s AND is_generated = 'NEVER' "
        "AND is_identity = 'NO' ORDER BY ordinal_position",
        (table.schema, table.name),
    ).fetchall()
    return [r["column_name"] for r in rows]


@pytest.fixture
def organizations(owner_conn: Conn) -> tuple[OrganizationRows, OrganizationRows]:
    return seed_organization(owner_conn), seed_organization(owner_conn)


@pytest.fixture
def executor(owner_url: str) -> Iterator[Conn]:
    with executor_connection(owner_url) as conn:
        yield conn


def test_every_tenant_table_is_covered() -> None:
    assert len(TENANT_TABLES) == 29


@pytest.mark.parametrize("table", TENANT_TABLES, ids=lambda t: t.qualified)
def test_rows_of_another_organization_are_invisible(
    owner_conn: Conn,
    executor: Conn,
    organizations: tuple[OrganizationRows, OrganizationRows],
    table: TableSpec,
) -> None:
    a, b = organizations
    column = sql.Identifier(table.tenant_column)
    is_a = sql.SQL("{} = %s").format(column)
    assert _count(owner_conn, table, is_a, (a.org,)) > 0
    b_rows = _count(owner_conn, table, is_a, (b.org,))
    assert b_rows > 0

    with _session(executor, b.org):
        assert _count(executor, table, is_a, (a.org,)) == 0
        assert _count(executor, table, sql.SQL("true")) == b_rows
    with _session(executor, None):
        assert _count(executor, table, sql.SQL("true")) == 0


@pytest.mark.parametrize(
    "table", [t for t in TENANT_TABLES if "I" in t.writes], ids=lambda t: t.qualified
)
def test_a_row_naming_another_organization_cannot_be_inserted(
    owner_conn: Conn,
    executor: Conn,
    organizations: tuple[OrganizationRows, OrganizationRows],
    table: TableSpec,
) -> None:
    a, b = organizations
    columns = _insertable_columns(owner_conn, table)
    target = sql.Identifier(table.schema, table.name)
    found = owner_conn.execute(
        sql.SQL("SELECT to_jsonb(t) AS row FROM {} t WHERE {} = %s LIMIT 1").format(
            target, sql.Identifier(table.tenant_column)
        ),
        (a.org,),
    ).fetchone()
    assert found is not None
    insert = sql.SQL(
        "INSERT INTO {target} ({columns}) SELECT {columns} "
        "FROM jsonb_populate_record(NULL::{target}, %s::jsonb)"
    ).format(target=target, columns=sql.SQL(", ").join(map(sql.Identifier, columns)))
    row = Jsonb(found["row"])
    for organization in (b.org, None):
        message = _refusal(executor, organization, insert, (row,))
        assert "row-level security" in message, message


@pytest.mark.parametrize(
    "table", [t for t in TENANT_TABLES if "U" in t.writes], ids=lambda t: t.qualified
)
def test_a_row_cannot_be_moved_to_another_organization(
    owner_conn: Conn,
    executor: Conn,
    organizations: tuple[OrganizationRows, OrganizationRows],
    table: TableSpec,
) -> None:
    a, b = organizations
    column = sql.Identifier(table.tenant_column)
    target = sql.Identifier(table.schema, table.name)
    move = sql.SQL("UPDATE {} SET {} = %s WHERE {} = %s").format(target, column, column)
    message = _refusal(executor, b.org, move, (a.org, b.org))
    assert "row-level security" in message, message

    touch = sql.SQL("UPDATE {} SET {} = {} WHERE {} = %s").format(target, column, column, column)
    with _session(executor, b.org):
        assert executor.execute(touch, (a.org,)).rowcount == 0


@pytest.mark.parametrize(
    "table", [t for t in TENANT_TABLES if "U" not in t.writes], ids=lambda t: t.qualified
)
def test_append_only_rows_cannot_be_moved_at_all(
    executor: Conn,
    organizations: tuple[OrganizationRows, OrganizationRows],
    table: TableSpec,
) -> None:
    a, b = organizations
    column = sql.Identifier(table.tenant_column)
    move = sql.SQL("UPDATE {} SET {} = %s WHERE {} = %s").format(
        sql.Identifier(table.schema, table.name), column, column
    )
    message = _refusal(executor, b.org, move, (a.org, b.org))
    assert message.startswith("permission denied"), message


@pytest.mark.parametrize(
    "table", [t for t in TENANT_TABLES if "D" in t.writes], ids=lambda t: t.qualified
)
def test_rows_of_another_organization_cannot_be_deleted(
    owner_conn: Conn,
    executor: Conn,
    organizations: tuple[OrganizationRows, OrganizationRows],
    table: TableSpec,
) -> None:
    a, b = organizations
    is_a = sql.SQL("{} = %s").format(sql.Identifier(table.tenant_column))
    before = _count(owner_conn, table, is_a, (a.org,))
    delete = sql.SQL("DELETE FROM {} WHERE {}").format(
        sql.Identifier(table.schema, table.name), is_a
    )
    with executor.transaction():
        executor.execute("SELECT set_config('xcode.organization_id', %s, true)", (str(b.org),))
        assert executor.execute(delete, (a.org,)).rowcount == 0
    assert _count(owner_conn, table, is_a, (a.org,)) == before


def test_the_setting_is_transaction_local(
    executor: Conn, organizations: tuple[OrganizationRows, OrganizationRows]
) -> None:
    a, _ = organizations
    with executor.transaction():
        executor.execute("SELECT set_config('xcode.organization_id', %s, true)", (str(a.org),))
        inside = executor.execute("SELECT count(*) AS n FROM tenancy.organizations").fetchone()
    after = executor.execute("SELECT count(*) AS n FROM tenancy.organizations").fetchone()
    assert inside == {"n": 1}
    assert after == {"n": 0}


def test_session_functions_read_the_transaction_settings(executor: Conn) -> None:
    organization = "7a0c4b1e-1111-4111-8111-000000000001"
    actor = "7a0c4b1e-2222-4222-8222-000000000002"
    with executor.transaction():
        empty = executor.execute(
            "SELECT tenancy.current_organization() AS o, tenancy.current_actor() AS a, "
            "tenancy.current_request() AS r"
        ).fetchone()
        executor.execute(
            "SELECT set_config('xcode.organization_id', %s, true), "
            "set_config('xcode.actor_id', %s, true), set_config('xcode.request_id', 'req-1', true)",
            (organization, actor),
        )
        set_ = executor.execute(
            "SELECT tenancy.current_organization()::text AS o, tenancy.current_actor()::text AS a, "
            "tenancy.current_request() AS r"
        ).fetchone()
    assert empty == {"o": None, "a": None, "r": None}
    assert set_ == {"o": organization, "a": actor, "r": "req-1"}
