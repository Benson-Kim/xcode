"""The PostgreSQL side: the owner connection, the target checks, ``COPY`` in and out."""

from __future__ import annotations

import os
import shutil
import subprocess
from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from typing import Any

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row

from .formats import Cell, csv_bytes, header_bytes
from .records import TargetCatalogue, ToolError
from .tablemap import Table

TARGET_ENV = "XCODE_MIGRATION_DATABASE_URL"
OWNER = "xcode_owner"
SESSION = (
    "SET TimeZone = 'UTC'",
    "SET DateStyle = 'ISO, YMD'",
    "SET bytea_output = 'hex'",
    "SET extra_float_digits = 1",
    "SET lock_timeout = '30s'",
    "SET statement_timeout = 0",
)

type Connection = psycopg.Connection[dict[str, Any]]


def target_url() -> str:
    url = os.environ.get(TARGET_ENV, "").strip()
    if not url:
        raise ToolError(f"{TARGET_ENV} is not set (the target database as {OWNER})")
    return url


def production() -> bool:
    return os.environ.get("XCODE_ENV", "").strip().lower() == "production"


_LOOPBACK = {"localhost", "127.0.0.1", "::1"}


def require_tls(url: str, env: str = TARGET_ENV) -> None:
    """In production a database that is not on this machine needs ``sslmode=verify-full`` in
    its URL, read by libpq's own parser (a repeated key counts as libpq counts it)."""
    if not production():
        return
    try:
        params = conninfo_to_dict(url)
    except psycopg.ProgrammingError as exc:
        raise ToolError(f"{env} is not a valid connection string") from exc
    hosts = [h for h in str(params.get("host") or "").split(",") if h]
    addresses = [a for a in str(params.get("hostaddr") or "").split(",") if a]
    local = all(h.startswith("/") or h in _LOOPBACK for h in hosts) and all(
        a in _LOOPBACK for a in addresses
    )
    if not local and params.get("sslmode") != "verify-full":
        raise ToolError(f"in production {env} must set sslmode=verify-full for a remote target")


def connect_target(url: str | None = None) -> Connection:
    """An autocommit owner connection with the session settings every text form relies on;
    the commands open their transactions explicitly."""
    url = url or target_url()
    require_tls(url)
    try:
        conn = psycopg.connect(url, autocommit=True, row_factory=dict_row)
    except psycopg.Error as exc:
        raise ToolError(f"cannot connect to the target: {exc}") from exc
    for statement in SESSION:
        conn.execute(statement)
    row = conn.execute("SELECT current_user AS role").fetchone()
    if row is None or row["role"] != OWNER:
        conn.close()
        raise ToolError(f"the target connection must be {OWNER}, not {row and row['role']}")
    return conn


@dataclass(frozen=True, slots=True)
class TargetState:
    database: str
    server_version: str
    migration: int
    present: frozenset[str]


def one(
    conn: Connection, query: str | sql.Composed, params: Sequence[object] = ()
) -> dict[str, Any]:
    """The single row of an aggregate query."""
    row = conn.execute(query, params).fetchone()
    if row is None:
        raise ToolError(f"no row from {query}")
    return row


def inspect_target(conn: Connection, tables: Sequence[Table]) -> TargetState:
    info = one(
        conn,
        "SELECT current_database() AS db, current_setting('server_version') AS version, "
        "(SELECT coalesce(max(version), 0) FROM ops.schema_migrations) AS migration",
    )
    present = {
        table.target
        for table in tables
        if conn.execute("SELECT to_regclass(%s) IS NOT NULL AS ok", (table.target,)).fetchone()[
            "ok"
        ]  # type: ignore[index]
    }
    return TargetState(info["db"], info["version"], int(info["migration"]), frozenset(present))


def refuse_unless_empty(conn: Connection, state: TargetState) -> None:
    occupied = [
        name
        for name in sorted(state.present)
        if conn.execute(
            sql.SQL("SELECT EXISTS (SELECT 1 FROM {}) AS any").format(qualified(name))
        ).fetchone()["any"]  # type: ignore[index]
    ]
    if occupied:
        raise ToolError(
            "the target already holds rows in "
            + ", ".join(occupied)
            + ": load into a freshly migrated database (the load never merges)"
        )


def read_catalogue(conn: Connection) -> TargetCatalogue:
    permissions = conn.execute("SELECT key, catalogue FROM tenancy.permissions").fetchall()
    needs: dict[str, set[str]] = defaultdict(set)
    for row in conn.execute("SELECT permission, needs FROM tenancy.permission_dependencies"):
        needs[row["permission"]].add(row["needs"])
    roles: dict[str, set[str]] = defaultdict(set)
    for row in conn.execute("SELECT role_name, permission FROM tenancy.role_defaults"):
        roles[row["role_name"].lower()].add(row["permission"])
    translations: dict[str, set[str]] = defaultdict(set)
    for row in conn.execute("SELECT old_key, new_key FROM tenancy.permission_translations"):
        translations[row["old_key"]].add(row["new_key"])
    return TargetCatalogue(
        catalogue=frozenset(r["key"] for r in permissions if r["catalogue"]),
        keys=frozenset(r["key"] for r in permissions),
        dependencies={k: frozenset(v) for k, v in needs.items()},
        role_defaults={k: frozenset(v) for k, v in roles.items()},
        translations={k: frozenset(v) for k, v in translations.items()},
        time_zones=frozenset(),
    )


def known_time_zones(conn: Connection, names: Iterable[str]) -> frozenset[str]:
    """The names ``tenancy.check_time_zone`` accepts, the API's own test of a zone."""
    known: set[str] = set()
    for name in sorted(set(names)):
        try:
            with conn.transaction(force_rollback=True):
                conn.execute("SELECT tenancy.check_time_zone(%s)", (name,))
        except psycopg.Error:
            continue
        known.add(name)
    return frozenset(known)


def qualified(name: str) -> sql.Composed:
    schema, table = name.split(".", 1)
    return sql.SQL("{}.{}").format(sql.Identifier(schema), sql.Identifier(table))


def _columns(names: Sequence[str]) -> sql.Composed:
    return sql.SQL(", ").join(sql.Identifier(n) for n in names)


def copy_in(conn: Connection, target: str, columns: Sequence[str], data: bytes) -> None:
    statement = sql.SQL("COPY {} ({}) FROM STDIN WITH (FORMAT csv, HEADER MATCH)").format(
        qualified(target), _columns(columns)
    )
    with conn.cursor() as cur, cur.copy(statement) as copy:
        copy.write(data)


def copy_out(conn: Connection, target: str, columns: Sequence[str], order: Sequence[str]) -> bytes:
    statement = sql.SQL(
        "COPY (SELECT {} FROM {} ORDER BY {}) TO STDOUT WITH (FORMAT csv, FORCE_QUOTE *)"
    ).format(_columns(columns), qualified(target), _columns(order))
    chunks = [header_bytes(columns)]
    with conn.cursor() as cur, cur.copy(statement) as copy:
        chunks.extend(bytes(chunk) for chunk in copy)
    return b"".join(chunks)


@dataclass(frozen=True, slots=True)
class Refusal:
    constraint: str | None
    problem: str


def refusal(exc: psycopg.Error, details: bool = True) -> Refusal:
    """The refusal as the database words it; without ``details`` the detail line (which can
    quote the refused row's values) is left out."""
    diag = exc.diag
    text = diag.message_primary or str(exc).splitlines()[0]
    if details and diag.message_detail:
        text += f" ({diag.message_detail})"
    return Refusal(diag.constraint_name, f"{exc.sqlstate}: {text}")


def insert_rows(
    conn: Connection,
    target: str,
    columns: Sequence[str],
    rows: Sequence[Sequence[Cell]],
    on_refused: Callable[[int, Refusal], None],
    details: bool = True,
) -> None:
    """``COPY`` the rows under a savepoint; when the database refuses the batch, halve it until
    each refused row is alone, so every refusal names one source row and the others load."""

    def attempt(low: int, high: int) -> None:
        if low >= high:
            return
        try:
            with conn.transaction():
                copy_in(conn, target, columns, csv_bytes(columns, rows[low:high]))
        except psycopg.Error as exc:
            if high - low == 1:
                on_refused(low, refusal(exc, details))
                return
            middle = (low + high) // 2
            attempt(low, middle)
            attempt(middle, high)

    attempt(0, len(rows))


def check_deferred(conn: Connection, details: bool = True) -> Refusal | None:
    try:
        with conn.transaction():
            conn.execute("SET CONSTRAINTS ALL IMMEDIATE")
            conn.execute("SET CONSTRAINTS ALL DEFERRED")
    except psycopg.Error as exc:
        return refusal(exc, details)
    return None


def xcode_api_cli() -> str | None:
    configured = os.environ.get("XCODE_API_CLI", "").strip()
    if configured:
        return configured
    return shutil.which("xcode-api")


def run_db_verify() -> tuple[bool, str]:
    """``xcode-api db verify`` against the target (it reads the same environment variable)."""
    cli = xcode_api_cli()
    if cli is None:
        return False, "xcode-api is not on PATH and XCODE_API_CLI is not set"
    try:
        done = subprocess.run(  # noqa: S603 - the operator's own CLI, no shell
            [cli, "db", "verify"],
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"xcode-api db verify did not run: {exc}"
    output = (done.stdout + done.stderr).strip()
    return done.returncode == 0, output
