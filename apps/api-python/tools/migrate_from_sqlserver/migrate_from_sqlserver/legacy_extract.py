"""``extract --source legacy``: the legacy PostgreSQL database to CSV files and
``manifest.json`` (``docs/10-data-migration.md`` 7.2).

It reads a restored copy through ``XCODE_MIGRATION_LEGACY_URL`` and refuses a database that
answers a write (mark the copy read-only: ``ALTER DATABASE <copy> SET
default_transaction_read_only = on``), any alembic version but the one the map was checked
against, and any soft-deleted row (the map does not cover one). One ``REPEATABLE READ READ
ONLY`` transaction runs one query per file of ``legacy_tablemap.EXTRACTS``, counts every
legacy table, and works out in SQL the source figures ``load`` checks the target against.
PostgreSQL casts every value to the text form ``formats.parse_source`` reads: ids as text,
instants in UTC to the microsecond, booleans ``0``/``1``, and each ``double precision``
amount as the shortest decimal that reads back as the same number, so an amount that would
round is refused by the transform rather than rounded.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from . import __version__
from . import legacy_tablemap as m
from .database import require_tls
from .formats import Cell, csv_bytes, write_file
from .records import ToolError

LEGACY_ENV = "XCODE_MIGRATION_LEGACY_URL"
SNAPSHOT = "REPEATABLE READ READ ONLY"
_CAST = {
    "uuid": "s.{c}::text",
    "text": "s.{c}::text",
    "json": "to_jsonb(s.{c})::text",
    "bit": "CASE WHEN s.{c} THEN '1' WHEN NOT s.{c} THEN '0' END",
    "int": "s.{c}::text",
    "decimal": "((s.{c})::text)::numeric::text",
    "date": "to_char(s.{c}, 'YYYY-MM-DD')",
    "datetime2": "to_char(s.{c} AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS.US')",
}
_SESSION = (
    "SET TimeZone = 'UTC'",
    "SET extra_float_digits = 1",
    "SET statement_timeout = 0",
)
_READ_ONLY = """
    SELECT current_setting('transaction_read_only') = 'on' AS session,
           pg_is_in_recovery() OR EXISTS (
             SELECT 1
             FROM pg_db_role_setting AS s, unnest(s.setconfig) AS c (setting)
             WHERE s.setrole = 0
               AND s.setdatabase = (SELECT oid FROM pg_database WHERE datname = current_database())
               AND lower(c.setting) IN ('default_transaction_read_only=on',
                                        'default_transaction_read_only=true',
                                        'default_transaction_read_only=yes',
                                        'default_transaction_read_only=1')) AS copy"""
"""This session cannot write, and the database itself is marked read-only (or is a standby):
a read-only session alone (``options=-c default_transaction_read_only=on`` in the URL, or
``PGOPTIONS``) says nothing about what the database answers other sessions."""

FIGURES: dict[str, str] = {
    "revenue": """
        SELECT r.vehicle_id::text AS vehicle, to_char(r.date, 'YYYY-MM') AS month,
               count(DISTINCT r.date) AS days, sum(((r.plus)::text)::numeric)::text AS amount
        FROM public.records AS r JOIN public.entries AS e ON e.id = r.entry_id
        WHERE r.petty_cash_id IS NULL AND e.factor = 'plus'
        GROUP BY 1, 2 ORDER BY 1, 2""",
    "vehicle_costs": """
        SELECT r.vehicle_id::text AS vehicle, to_char(r.date, 'YYYY-MM') AS month,
               coalesce(sum(((r.minus)::text)::numeric), 0)::text AS amount
        FROM public.records AS r LEFT JOIN public.entries AS e ON e.id = r.entry_id
        WHERE r.petty_cash_id IS NOT NULL OR e.factor IS DISTINCT FROM 'plus'
        GROUP BY 1, 2 ORDER BY 1, 2""",
    "petty_cash": """
        SELECT CASE WHEN credit_note THEN 'credit note' WHEN plus IS NOT NULL THEN 'cash'
                    WHEN committed THEN 'expense approved' ELSE 'expense waiting' END AS bucket,
               count(*) AS count,
               coalesce(sum(((coalesce(plus, minus))::text)::numeric), 0)::text AS amount
        FROM public.petty_cash GROUP BY 1 ORDER BY 1""",
    "float": """
        SELECT (coalesce(sum(((plus)::text)::numeric), 0)
                - coalesce(sum(((minus)::text)::numeric), 0))::text AS amount
        FROM public.petty_cash""",
    "people": """
        SELECT count(*) AS users,
               count(*) FILTER (WHERE is_default_petty_cash_manager) AS float_holders,
               count(*) FILTER (WHERE phone IS NULL OR btrim(phone) = '') AS without_number
        FROM public.users""",
    "roles": """
        SELECT coalesce(role, '(none)') AS role, count(*) AS users
        FROM public.users GROUP BY 1 ORDER BY 1""",
    "daily_balance": """
        WITH stored AS (
          SELECT b.date, ((b.closing_balance)::text)::numeric AS closing,
                 (SELECT coalesce(sum(((p.plus)::text)::numeric), 0)
                         - coalesce(sum(((p.minus)::text)::numeric), 0)
                  FROM public.petty_cash AS p WHERE p.date <= b.date) AS entries
          FROM public.petty_cash_daily_balances AS b)
        SELECT (SELECT max(date) FROM stored
                WHERE date <= (now() AT TIME ZONE 'Africa/Nairobi')::date)::text AS day,
               (SELECT closing::text FROM stored
                WHERE date <= (now() AT TIME ZONE 'Africa/Nairobi')::date
                ORDER BY date DESC LIMIT 1) AS closing,
               (SELECT min(date) FROM stored
                WHERE round(closing, 2) <> round(entries, 2))::text AS first_differs,
               (SELECT count(*) FROM stored
                WHERE round(closing, 2) <> round(entries, 2)) AS days_differ""",
}


def _select(extract: m.Extract) -> sql.Composed:
    casts = sql.SQL(", ").join(
        sql.SQL(_CAST[c.src] + " AS {c}").format(c=sql.Identifier(str(c.source)))
        for c in extract.columns
    )
    order = sql.SQL(", ").join(sql.SQL("s.{}").format(sql.Identifier(k)) for k in extract.key)
    return sql.SQL("SELECT {} FROM ({}) AS s ORDER BY {}").format(
        casts,
        sql.SQL(extract.rows),
        order,
    )


def _columns(conn: psycopg.Connection[dict[str, Any]]) -> dict[str, set[str]]:
    present: dict[str, set[str]] = {}
    for row in conn.execute(
        "SELECT table_name, column_name FROM information_schema.columns "
        "WHERE table_schema = 'public'"
    ):
        present.setdefault(row["table_name"], set()).add(row["column_name"])
    return present


def run(output_dir: Path) -> dict[str, Any]:
    url = os.environ.get(LEGACY_ENV, "").strip()
    if not url:
        raise ToolError(f"{LEGACY_ENV} is not set (a restored, read-only copy of the database)")
    if (output_dir / "manifest.json").exists():
        raise ToolError(f"{output_dir} already holds an extract: use a new directory")
    require_tls(url, LEGACY_ENV)
    try:
        conn = psycopg.connect(url, autocommit=True, row_factory=dict_row)
    except psycopg.Error as exc:
        raise ToolError(f"cannot connect to the legacy database: {exc}") from exc
    try:
        for statement in _SESSION:
            conn.execute(statement)
        answers = conn.execute(_READ_ONLY).fetchone()
        if answers is None or not answers["session"] or not answers["copy"]:
            raise ToolError(
                "the legacy database answers a write: extract from a restored copy marked "
                "read-only (ALTER DATABASE <copy> SET default_transaction_read_only = on), "
                "never from the running application's database"
            )
        manifest = _read(conn, output_dir)
    finally:
        conn.close()
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    return manifest


def _read(conn: psycopg.Connection[dict[str, Any]], output_dir: Path) -> dict[str, Any]:
    with conn.transaction(force_rollback=True):
        conn.execute(f"SET TRANSACTION ISOLATION LEVEL {SNAPSHOT}")
        info = conn.execute(
            "SELECT now() AS at, current_database() AS db, "
            "current_setting('server_version') AS version"
        ).fetchone()
        assert info is not None  # noqa: S101 - one row
        present = _columns(conn)
        missing_tables = [t for t in m.LEGACY_TABLES if t not in present]
        if missing_tables:
            raise ToolError(f"the legacy database has no {missing_tables}: is this the right one?")
        version = conn.execute("SELECT version_num FROM public.alembic_version").fetchall()
        versions = sorted(str(v["version_num"]) for v in version)
        if versions != [m.VERSION]:
            raise ToolError(
                f"the legacy database is at alembic {versions}, the map of docs/10 section 7 "
                f"was checked against {m.VERSION}: check the map against it first"
            )
        for extract in m.EXTRACTS:
            lacking = sorted({str(c.source) for c in extract.columns} - present[extract.table])
            if lacking:
                raise ToolError(f"{extract.table} lacks {lacking}: the map expects them")
        deleted = {
            table: n
            for table in m.LEGACY_TABLES
            if "deleted_at" in present[table]
            for n in [
                conn.execute(
                    sql.SQL(
                        "SELECT count(*) AS n FROM public.{} WHERE deleted_at IS NOT NULL"
                    ).format(sql.Identifier(table))
                ).fetchone()["n"]  # type: ignore[index]
            ]
            if n
        }
        if deleted:
            raise ToolError(
                f"soft-deleted rows {deleted}: the map of docs/10 section 7 does not cover them; "
                "check it first"
            )
        counts = {
            table: int(
                conn.execute(
                    sql.SQL("SELECT count(*) AS n FROM public.{}").format(sql.Identifier(table))
                ).fetchone()["n"]  # type: ignore[index]
            )
            for table in m.LEGACY_TABLES
        }
        tables: dict[str, Any] = {}
        for extract in m.EXTRACTS:
            names = [str(c.source) for c in extract.columns]
            rows: list[tuple[Cell, ...]] = [
                tuple(row[n] for n in names) for row in conn.execute(_select(extract))
            ]
            file = f"{extract.name}.csv"
            digest = write_file(output_dir / file, csv_bytes(names, rows))
            tables[extract.name] = {
                "file": file,
                "rows": len(rows),
                "sha256": digest,
                "legacy_table": extract.table,
            }
        for table, _ in m.COUNTED:
            tables[table] = {"rows": counts[table], "copied": False, "legacy_table": table}
        figures = {name: conn.execute(query).fetchall() for name, query in FIGURES.items()}
    return {
        "format": 1,
        "tool": __version__,
        "extracted_at": info["at"].isoformat(),
        "source": {
            "kind": "legacy",
            "database": info["db"],
            "server_version": info["version"],
            "alembic_version": m.VERSION,
            "snapshot": SNAPSHOT,
        },
        "legacy_tables": counts,
        "tables": tables,
        "figures": _plain(figures),
    }


def _plain(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_plain(v) for v in value]
    if value is None or isinstance(value, bool | int | str):
        return value
    return str(value)
