"""Privileges by role, exercised (``docs/04-schema.md`` sections 1 and 9).

The executor may write exactly the "Writes" column of each table (append-only tables refuse
``UPDATE`` and ``DELETE``); ``xcode_app`` and ``xcode_operator`` cannot read any table;
``xcode_readonly`` reads the code tables and the catalogue only. The positive tests prove the
constraint functions and triggers work under the executor's privileges, as routines will.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from urllib.parse import urlsplit

import psycopg
import pytest
from psycopg import sql
from psycopg.rows import dict_row

from xcode_api.db.migrate import find_db_dir
from xcode_api.db.schema_spec import TABLES, TableKind, TableSpec

from ..support.database import executor_connection
from ..support.rows import OrganizationRows, seed_organization

Conn = psycopg.Connection[dict[str, Any]]

_STATEMENTS = {
    "INSERT": "INSERT INTO {table} DEFAULT VALUES",
    "UPDATE": "UPDATE {table} SET {column} = {column} WHERE false",
    "DELETE": "DELETE FROM {table} WHERE false",
}
DENIED = [
    (table, privilege)
    for table in TABLES
    for privilege in ("INSERT", "UPDATE", "DELETE")
    if privilege not in table.executor_privileges()
]


def _statement(conn: Conn, table: TableSpec, privilege: str) -> sql.Composed:
    column = conn.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_schema = %s "
        "AND table_name = %s AND is_identity = 'NO' AND is_generated = 'NEVER' "
        "ORDER BY ordinal_position LIMIT 1",
        (table.schema, table.name),
    ).fetchone()
    assert column is not None
    return sql.SQL(_STATEMENTS[privilege]).format(
        table=sql.Identifier(table.schema, table.name),
        column=sql.Identifier(column["column_name"]),
    )


def _login(url: str, role: str) -> str:
    parts = urlsplit(url)
    port = f":{parts.port}" if parts.port else ""
    query = f"?{parts.query}" if parts.query else ""
    return f"{parts.scheme}://{role}:{role}@{parts.hostname}{port}{parts.path}{query}"


def _all_tables(owner: Conn) -> list[str]:
    rows = owner.execute(
        "SELECT schemaname || '.' || tablename AS qualified FROM pg_tables "
        "WHERE schemaname IN ('identity', 'tenancy', 'setup', 'revenue', 'pettycash', 'ops')"
    ).fetchall()
    return sorted(r["qualified"] for r in rows)


def _select(conn: Conn, qualified: str) -> psycopg.Error | None:
    try:
        conn.execute(
            sql.SQL("SELECT 1 FROM {} LIMIT 0").format(sql.Identifier(*qualified.split(".", 1)))
        )
    except psycopg.Error as exc:
        return exc
    return None


@pytest.fixture
def executor(owner_url: str) -> Iterator[Conn]:
    with executor_connection(owner_url) as conn:
        yield conn


@pytest.fixture
def readonly_conn(owner_url: str) -> Iterator[Conn]:
    url = _login(owner_url, "xcode_readonly")
    conn = psycopg.connect(url, autocommit=True, row_factory=dict_row)
    try:
        yield conn
    finally:
        conn.close()


def test_append_only_tables_refuse_update_and_delete(executor: Conn) -> None:
    append_only = [t for t in TABLES if t.writes == "I"]
    assert {t.qualified for t in append_only} == {
        "identity.sign_in_attempts",
        "tenancy.roles",
        "tenancy.change_log",
        "tenancy.audit_events",
        "setup.vehicle_away_periods",
        "setup.recurring_versions",
        "setup.recurring_allocations",
    }
    for table in append_only:
        for privilege in ("UPDATE", "DELETE"):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                executor.execute(_statement(executor, table, privilege))


def test_no_routine_body_rewrites_history_or_deletes_a_setup_record() -> None:
    # Versions, shares, targets and away periods are append-only; companies, vehicles,
    # scheduled items and the catalogue are never deleted. The grants refuse it (above); no
    # routine body even says it.
    append_only = (
        "vehicle_away_periods",
        "recurring_versions",
        "recurring_allocations",
    )
    never_deleted = (
        *append_only,
        "psv_companies",
        "fleet_vehicles",
        "recurring_items",
        "expense_main_categories",
        "expense_categories",
        "expense_items",
    )
    forbidden = [f"update setup.{name} " for name in append_only]
    forbidden += [f"delete from setup.{name} " for name in never_deleted]
    offenders = []
    for path in sorted((find_db_dir() / "routines").rglob("*.sql")):
        code = [line.split("--", 1)[0] for line in path.read_text(encoding="utf-8").splitlines()]
        words = " ".join(" ".join(code).lower().split()) + " "
        offenders += [(path.name, statement) for statement in forbidden if statement in words]
    assert offenders == []


@pytest.mark.parametrize(
    ("table", "privilege"), DENIED, ids=[f"{t.qualified}-{p}" for t, p in DENIED]
)
def test_executor_holds_no_write_beyond_the_declared_ones(
    executor: Conn, table: TableSpec, privilege: str
) -> None:
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        executor.execute(_statement(executor, table, privilege))


@pytest.mark.parametrize("role", ["xcode_app", "xcode_operator"])
def test_app_and_operator_cannot_select_any_table(
    owner_conn: Conn, owner_url: str, role: str
) -> None:
    tables = _all_tables(owner_conn)
    assert len(tables) > 38
    with psycopg.connect(_login(owner_url, role), autocommit=True, row_factory=dict_row) as conn:
        readable = [
            qualified
            for qualified in tables
            if not isinstance(_select(conn, qualified), psycopg.errors.InsufficientPrivilege)
        ]
    assert readable == []


def test_readonly_reads_code_tables_and_the_catalogue_only(
    owner_conn: Conn, readonly_conn: Conn
) -> None:
    allowed = {
        t.qualified
        for t in TABLES
        if t.kind in (TableKind.CODE, TableKind.CATALOGUE) and t.schema != "pettycash"
    }
    readable = {q for q in _all_tables(owner_conn) if _select(readonly_conn, q) is None}
    assert readable == allowed
    row = readonly_conn.execute("SELECT count(*) AS n FROM tenancy.permissions").fetchone()
    assert row == {"n": 80}


@pytest.fixture
def org(owner_conn: Conn) -> OrganizationRows:
    return seed_organization(owner_conn)


def _enter(conn: Conn, rows: OrganizationRows) -> None:
    conn.execute("SELECT set_config('xcode.organization_id', %s, true)", (str(rows.org),))


def test_executor_writes_through_constraint_functions_and_triggers(
    executor: Conn, org: OrganizationRows
) -> None:
    params = org.params()
    with executor.transaction():
        _enter(executor, org)
        executor.execute(
            "UPDATE tenancy.organization_brandings SET primary_color = '#14213D' "
            "WHERE organization_id = %(org)s",
            params,
        )
        executor.execute(
            "UPDATE setup.fleet_vehicles SET left_on = DATE '2026-12-31' WHERE id = %(vehicle)s",
            params,
        )
        executor.execute(
            "INSERT INTO setup.vehicle_away_periods (organization_id, vehicle_id, left_on, "
            "returned_on) VALUES (%(org)s, %(vehicle)s, DATE '2026-04-06', DATE '2026-04-13')",
            params,
        )
        version = executor.execute(
            "INSERT INTO setup.recurring_versions (organization_id, item_id, revision, "
            "effective_from, name, kind, amount, frequency, day, last_day, start_on) VALUES "
            "(%(org)s, %(recurring)s, 2, DATE '2026-02-01', 'Savings', 2, 50, 2, 1, false, "
            "DATE '2026-02-01') RETURNING id",
            params,
        ).fetchone()
        assert version is not None
        executor.execute(
            "INSERT INTO setup.recurring_allocations (organization_id, version_id, vehicle_id, "
            "amount) VALUES (%(org)s, %(version)s, %(vehicle)s, 50)",
            {**params, "version": version["id"]},
        )
    row = executor.execute(
        "SELECT 1 AS ok FROM setup.recurring_versions WHERE id = %s", (version["id"],)
    ).fetchone()
    assert row is None  # invisible again outside the transaction that set the organization


def test_executor_is_refused_by_the_deferred_share_check(
    executor: Conn, org: OrganizationRows
) -> None:
    with pytest.raises(psycopg.Error) as caught:
        with executor.transaction():
            _enter(executor, org)
            executor.execute(
                "INSERT INTO setup.recurring_versions (organization_id, item_id, revision, "
                "effective_from, name, kind, amount, frequency, day, last_day, start_on) VALUES "
                "(%(org)s, %(recurring)s, 2, DATE '2026-02-01', 'Savings', 2, 50, 2, 1, false, "
                "DATE '2026-02-01')",
                org.params(),
            )
    assert (caught.value.sqlstate, caught.value.diag.message_primary) == (
        "XC422",
        "allocation_sum_mismatch",
    )


def test_executor_is_refused_by_the_registration_trigger(
    executor: Conn, org: OrganizationRows
) -> None:
    with pytest.raises(psycopg.Error) as caught:
        with executor.transaction():
            _enter(executor, org)
            executor.execute(
                "UPDATE setup.fleet_vehicles SET registration = 'KDC 001C' WHERE id = %(vehicle)s",
                org.params(),
            )
    assert (caught.value.sqlstate, caught.value.diag.message_primary) == (
        "XC422",
        "registration_immutable",
    )
