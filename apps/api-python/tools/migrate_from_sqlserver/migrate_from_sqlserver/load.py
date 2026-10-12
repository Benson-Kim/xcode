"""``load --dry-run | --apply``: the load files into the target in one transaction, then the
verification queries of ``docs/10-data-migration.md`` section 4.

Both modes do the same work in the same transaction, as ``xcode_owner`` and under the
migration runner's advisory lock: ``COPY`` every table in foreign-key order, check the
deferred constraints, run every verification. ``--dry-run`` always rolls back. ``--apply``
commits only when every verification passes, and then records an ``ops.operator_actions``
row (``data_migration_load``) named after ``XCODE_OPERATOR``. Nothing reaches the target
otherwise: identity ids are given explicitly, and the one sequence moved (the audit trail's)
is moved only on the committing path.
"""

from __future__ import annotations

import json
import os
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb

from . import __version__
from .database import (
    Connection,
    check_deferred,
    copy_in,
    copy_out,
    inspect_target,
    one,
    qualified,
    refuse_unless_empty,
    run_db_verify,
)
from .formats import sha256
from .records import ToolError
from .tablemap import TABLES
from .transform import MANIFEST, OLD_SETS, TRANSFORM, Manifest

LOAD = "load.json"
OPERATOR_ENV = "XCODE_OPERATOR"
LOCK = "SELECT pg_advisory_xact_lock(hashtext('xcode.migrate'))"
SESSION_SAMPLE = 200
TENANT_SCHEMAS = ("tenancy", "setup", "revenue", "pettycash", "expenses")


@dataclass
class Check:
    name: str
    ok: bool
    detail: str
    lines: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "ok": self.ok, "detail": self.detail, "lines": self.lines}


def operator() -> str:
    name = os.environ.get(OPERATOR_ENV, "").strip()
    if not name:
        raise ToolError(f"--apply needs {OPERATOR_ENV}: the name of the DBA running the load")
    if len(name) > 128 or not all(0x20 <= ord(ch) <= 0x7E for ch in name):
        raise ToolError(f"{OPERATOR_ENV} must be 1 to 128 printable ASCII characters")
    return name


def read_work(work_dir: Path) -> tuple[dict[str, Any], dict[str, bytes], bytes]:
    path = work_dir / TRANSFORM
    if not path.is_file():
        raise ToolError(f"{path} is missing: run transform first")
    summary: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    if sha256((work_dir / MANIFEST).read_bytes()) != summary["manifest_sha256"]:
        raise ToolError("manifest.json changed since the transform")
    by_target = {t.target: t for t in TABLES}
    files: dict[str, bytes] = {}
    for table in summary["tables"]:
        known = by_target.get(table["target"])
        if (
            known is None
            or table["file"] != f"load/{known.order:02d}_{known.target}.csv"
            or table["columns"] != [c.target for c in known.target_columns]
            or table["key"] != list(known.target_key)
        ):
            raise ToolError(
                f"transform.json describes {table['target']!r} unlike the table map: "
                "transform again with this version of the tool"
            )
        data = (work_dir / table["file"]).read_bytes()
        if sha256(data) != table["sha256"]:
            raise ToolError(f"{table['file']} does not match its SHA-256 in transform.json")
        files[table["target"]] = data
    old_sets = (work_dir / OLD_SETS).read_bytes()
    if sha256(old_sets) != summary["permission_old_sets"]["sha256"]:
        raise ToolError(f"{OLD_SETS} does not match its SHA-256 in transform.json")
    return summary, files, old_sets


def run(
    work_dir: Path,
    conn: Connection,
    apply: bool,
    accept_rejected: int | None,
) -> dict[str, Any]:
    name = operator() if apply else None
    summary, files, old_sets = read_work(work_dir)
    manifest = Manifest.read(work_dir)
    checks: list[Check] = []
    checks.append(_rejections(summary, accept_rejected))
    checks.append(_ledger(summary, manifest))
    verified, output = run_db_verify()
    checks.append(Check("xcode-api db verify (before the load)", verified, "", output.splitlines()))

    state = inspect_target(conn, TABLES)
    if state.migration != summary["target"]["migration"]:
        raise ToolError(
            f"the target is at migration {state.migration:04d}, the transform ran against "
            f"{summary['target']['migration']:04d}: transform again"
        )
    refuse_unless_empty(conn, state)

    committed = False
    started = datetime.now(UTC)
    try:
        with conn.transaction() as transaction:
            conn.execute(LOCK)
            for table in summary["tables"]:
                copy_in(conn, table["target"], table["columns"], files[table["target"]])
            deferred = check_deferred(conn)
            checks.append(
                Check(
                    "deferred constraints hold",
                    deferred is None,
                    "" if deferred is None else deferred.problem,
                    [],
                )
            )
            checks.extend(_verify(conn, summary, files, old_sets, manifest))
            passed = all(c.ok for c in checks)
            if apply and passed:
                _record(conn, summary, name, checks)
                committed = True
            else:
                raise psycopg.Rollback(transaction)
    except psycopg.Error as exc:
        raise ToolError(f"the load stopped and nothing was written: {exc}") from exc

    if committed:
        verified, output = run_db_verify()
        checks.append(
            Check("xcode-api db verify (after the commit)", verified, "", output.splitlines())
        )
    result = {
        "tool": __version__,
        "mode": "apply" if apply else "dry-run",
        "operator": name,
        "started_at": started.isoformat(),
        "finished_at": datetime.now(UTC).isoformat(),
        "target": {"database": state.database, "migration": state.migration},
        "committed": committed,
        "accepted_rejections": accept_rejected,
        "checks": [c.as_dict() for c in checks],
    }
    (work_dir / LOAD).write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    return result


def _rejections(summary: dict[str, Any], accepted: int | None) -> Check:
    rejected = len(summary["rejected"])
    blocking = int(summary["blocking"])
    lines = [f"{r['table']} {r['key']}: {r['problem']}" for r in summary["rejected"]]
    if blocking:
        return Check(
            "no refused person or organization",
            False,
            f"{blocking} refused rows of identity.users or tenancy.organizations: fix them in "
            "SQL Server and extract again (question 16)",
            lines,
        )
    if rejected and accepted != rejected:
        return Check(
            "refused rows acknowledged",
            False,
            f"{rejected} rows are refused and would not move: review them, fix them in SQL "
            f"Server, or pass --accept-rejected {rejected}",
            lines,
        )
    return Check("refused rows acknowledged", True, f"{rejected} refused", lines)


def _ledger(summary: dict[str, Any], manifest: Manifest) -> Check:
    """Every source row and every row the transform made is loaded, dropped by a documented
    rule, or refused: source + made = loaded + dropped + refused, table by table."""
    lines: list[str] = []
    for table in summary["tables"]:
        source = table["source"]
        if source is not None:
            listed = (manifest.table(source) or {}).get("rows", 0)
            if listed != table["source_rows"]:
                lines.append(f"{source}: manifest {listed}, transform {table['source_rows']}")
        incoming = table["source_rows"] + table["made"]
        outgoing = table["loaded"] + table["dropped"] + table["rejected"]
        if incoming != outgoing:
            lines.append(
                f"{table['target']}: {table['source_rows']} source and {table['made']} made, "
                f"but {table['loaded']} loaded, {table['dropped']} dropped, "
                f"{table['rejected']} refused"
            )
    return Check(
        "every source row is loaded, dropped by a documented rule, or refused",
        not lines,
        "",
        lines,
    )


def _verify(
    conn: Connection,
    summary: dict[str, Any],
    files: dict[str, bytes],
    old_sets: bytes,
    manifest: Manifest,
) -> list[Check]:
    return [
        _counts(conn, summary),
        _checksums(conn, summary, files),
        _organizations(conn),
        _versions(conn),
        _sessions(conn, manifest.extracted_at),
        _revenue(conn, summary),
        _translation(conn, old_sets),
        _figures(conn, manifest.extracted_at),
    ]


def _counts(conn: Connection, summary: dict[str, Any]) -> Check:
    lines: list[str] = []
    for table in summary["tables"]:
        count = one(
            conn, sql.SQL("SELECT count(*) AS n FROM {}").format(qualified(table["target"]))
        )
        if count["n"] != table["loaded"]:
            lines.append(f"{table['target']}: {count['n']} rows, expected {table['loaded']}")
    return Check("rows per table as transformed", not lines, "", lines)


def _checksums(conn: Connection, summary: dict[str, Any], files: dict[str, bytes]) -> Check:
    lines: list[str] = []
    for table in summary["tables"]:
        exported = copy_out(conn, table["target"], table["columns"], table["key"])
        if exported != files[table["target"]]:
            lines.append(f"{table['target']}: SHA-256 {sha256(exported)}, file {table['sha256']}")
    return Check(
        "each table's ordered rows equal its load file byte for byte (SHA-256)",
        not lines,
        "",
        lines,
    )


def _organizations(conn: Connection) -> Check:
    tables = conn.execute(
        "SELECT table_schema || '.' || table_name AS name FROM information_schema.columns "
        "WHERE column_name = 'organization_id' AND table_schema = ANY(%s) "
        "AND table_name IN (SELECT table_name FROM information_schema.tables "
        "  WHERE table_type = 'BASE TABLE' AND table_schema = columns.table_schema) "
        "ORDER BY 1",
        (list(TENANT_SCHEMAS),),
    ).fetchall()
    lines: list[str] = []
    for row in tables:
        orphan = one(
            conn,
            sql.SQL(
                "SELECT count(*) AS n FROM {} AS t WHERE NOT EXISTS "
                "(SELECT 1 FROM tenancy.organizations AS o WHERE o.id = t.organization_id)"
            ).format(qualified(row["name"])),
        )
        if orphan["n"]:
            lines.append(f"{row['name']}: {orphan['n']} rows")
    return Check(
        f"every tenant row's organization exists ({len(tables)} tables)", not lines, "", lines
    )


def _versions(conn: Connection) -> Check:
    """The next logged change of an organization takes ``settings_version + 1`` as its
    change-log version, so no copied change-log row may already hold a higher one."""
    lines = [
        f"{r['id']}: settings version {r['settings_version']}, change log up to {r['top']}"
        for r in conn.execute(
            "SELECT o.id, o.settings_version, max(c.version) AS top "
            "FROM tenancy.organizations AS o JOIN tenancy.change_log AS c "
            "ON c.organization_id = o.id GROUP BY o.id, o.settings_version "
            "HAVING max(c.version) > o.settings_version ORDER BY o.id"
        )
    ]
    return Check(
        "each organization's settings version is past its change log", not lines, "", lines
    )


def _sessions(conn: Connection, at: datetime) -> Check:
    """``api.auth_resolve_session`` resolves people with an active membership on a device that
    is live at the extraction instant, with their copied security version."""
    candidates = conn.execute(
        "SELECT u.id, d.device_id, u.security_version FROM identity.users AS u "
        "JOIN tenancy.memberships AS m ON m.user_id = u.id AND m.active "
        "JOIN identity.trusted_devices AS d ON d.user_id = u.id "
        "WHERE u.status = 'active' AND identity.device_live(d, %s) "
        "ORDER BY u.id, d.device_id LIMIT %s",
        (at, SESSION_SAMPLE),
    ).fetchall()
    lines: list[str] = []
    for row in candidates:
        try:
            with conn.transaction():
                conn.execute(
                    "SELECT api.auth_resolve_session(%s, %s, %s, %s)",
                    (row["id"], row["device_id"], row["security_version"], at),
                )
        except psycopg.Error as exc:
            lines.append(f"user {row['id']} device {row['device_id']}: {exc.diag.message_primary}")
    return Check(
        "sessions resolve for people on live devices",
        not lines,
        f"{len(candidates) - len(lines)} of {len(candidates)} sampled resolve",
        lines,
    )


def _revenue(conn: Connection, summary: dict[str, Any]) -> Check:
    target: dict[tuple[str, str], Decimal] = {}
    for row in conn.execute(
        "SELECT organization_id::text AS org, to_char(business_date, 'YYYY-MM') AS month, "
        "sum(amount) AS total FROM revenue.records WHERE amount IS NOT NULL GROUP BY 1, 2"
    ):
        target[(row["org"], row["month"])] = Decimal(row["total"])
    expected: dict[tuple[str, str], tuple[Decimal, Decimal]] = {}
    for org, months in summary["revenue"].items():
        for month, cell in months.items():
            expected[(org, month)] = (Decimal(cell["source"]), Decimal(cell["excluded"]))
    lines: list[str] = []
    for key in sorted(set(target) | set(expected)):
        source, excluded = expected.get(key, (Decimal(0), Decimal(0)))
        loaded = target.get(key, Decimal(0))
        if loaded != source - excluded:
            lines.append(
                f"{key[0]} {key[1]}: source {source}, not moved {excluded}, target {loaded}"
            )
    detail = ", ".join(f"{k[1]} {v}" for k, v in sorted(target.items()))
    return Check("revenue per organization and month equals the source", not lines, detail, lines)


_NEW_SETS = """
CREATE TEMPORARY TABLE migration_members ON COMMIT DROP AS
SELECT m.organization_id, m.user_id, r.name AS role_name
FROM tenancy.memberships AS m
LEFT JOIN tenancy.person_roles AS pr
  ON pr.organization_id = m.organization_id AND pr.user_id = m.user_id
LEFT JOIN tenancy.roles AS r ON r.organization_id = pr.organization_id AND r.id = pr.role_id;

CREATE TEMPORARY TABLE migration_new_sets ON COMMIT DROP AS
WITH RECURSIVE
chosen AS (
  SELECT o.organization_id, o.user_id, t.new_key AS permission
  FROM migration_old_sets AS o
  JOIN tenancy.permission_translations AS t ON t.old_key = o.permission
  UNION
  SELECT members.organization_id, members.user_id, d.permission
  FROM migration_members AS members
  JOIN tenancy.role_defaults AS d ON lower(d.role_name) = lower(members.role_name)
  JOIN tenancy.permissions AS p ON p.key = d.permission AND p.catalogue
  WHERE NOT EXISTS (
      SELECT 1 FROM tenancy.permission_translations AS t WHERE t.new_key = d.permission)
    AND NOT EXISTS (
      SELECT 1 FROM tenancy.permission_dependencies AS dep WHERE dep.needs = d.permission)
),
expanded (organization_id, user_id, permission) AS (
  SELECT chosen.organization_id, chosen.user_id, chosen.permission FROM chosen
  UNION
  SELECT expanded.organization_id, expanded.user_id, dep.needs
  FROM expanded
  JOIN tenancy.permission_dependencies AS dep ON dep.permission = expanded.permission
)
SELECT expanded.organization_id, expanded.user_id, expanded.permission
FROM expanded
JOIN tenancy.permissions AS p ON p.key = expanded.permission AND p.catalogue;

CREATE TEMPORARY TABLE migration_role_sets ON COMMIT DROP AS
SELECT m.organization_id, m.user_id, d.permission
FROM migration_members AS m
JOIN tenancy.role_defaults AS d ON lower(d.role_name) = lower(m.role_name)
JOIN tenancy.permissions AS p ON p.key = d.permission AND p.catalogue;
"""

_STORED_DIFFERS = """
WITH stored AS (
  SELECT d.organization_id, d.user_id, d.permission
  FROM migration_role_sets AS d
  WHERE NOT EXISTS (
    SELECT 1 FROM tenancy.permission_overrides AS o
    WHERE o.organization_id = d.organization_id AND o.user_id = d.user_id
      AND o.permission = d.permission AND NOT o.granted
  )
  UNION
  SELECT o.organization_id, o.user_id, o.permission
  FROM tenancy.permission_overrides AS o
  WHERE o.granted
)
SELECT organization_id, user_id, permission, 'stored, not translated' AS why
FROM (SELECT * FROM stored EXCEPT SELECT * FROM migration_new_sets) AS extra
UNION ALL
SELECT organization_id, user_id, permission, 'translated, not stored'
FROM (SELECT * FROM migration_new_sets EXCEPT SELECT * FROM stored) AS missing
ORDER BY 1, 2, 3
"""

_LOST = """
SELECT o.organization_id, o.user_id, o.permission
FROM migration_old_sets AS o
WHERE o.permission NOT IN ('revenue.no_earnings', 'bills.view', 'bills.capture', 'bills.approve',
                           'organization.manage')
  AND (
    NOT EXISTS (SELECT 1 FROM tenancy.permission_translations AS t WHERE t.old_key = o.permission)
    OR EXISTS (
      SELECT 1 FROM tenancy.permission_translations AS t
      WHERE t.old_key = o.permission
        AND NOT EXISTS (
          SELECT 1 FROM migration_new_sets AS n
          WHERE n.organization_id = o.organization_id AND n.user_id = o.user_id
            AND n.permission = t.new_key
        )
    )
  )
ORDER BY 1, 2, 3
"""


def _translation(conn: Connection, old_sets: bytes) -> Check:
    """The stored overrides give every person exactly the translated set (the checks of
    ``0009_access``, computed here in SQL from the old sets the transform worked out), and
    nobody loses a right the translation keeps."""
    conn.execute(
        "CREATE TEMPORARY TABLE migration_old_sets "
        "(organization_id uuid, user_id uuid, permission text) ON COMMIT DROP"
    )
    copy_in(
        conn, "pg_temp.migration_old_sets", ("organization_id", "user_id", "permission"), old_sets
    )
    conn.execute(_NEW_SETS)
    lines = [
        f"{r['organization_id']} {r['user_id']} {r['permission']}: {r['why']}"
        for r in conn.execute(_STORED_DIFFERS)
    ]
    lines += [
        f"{r['organization_id']} {r['user_id']} {r['permission']}: lost by the translation"
        for r in conn.execute(_LOST)
    ]
    people = one(conn, "SELECT count(*) AS n FROM migration_members")
    return Check(
        "translated rights reproduce every person's old rights",
        not lines,
        f"{people['n']} people",
        lines,
    )


def _figures(conn: Connection, at: datetime) -> Check:
    """The counts of ``docs/10`` 3.1 for the owner: always passes, the report prints them."""
    lines: list[str] = []
    for row in conn.execute(
        "SELECT u.status, u.pin_hash IS NOT NULL AS has_pin, u.failed_attempts >= 5 AS locked, "
        "count(*) AS n FROM identity.users AS u GROUP BY 1, 2, 3 ORDER BY 1, 2, 3"
    ):
        state = "PIN set" if row["has_pin"] else "not signed in yet (no PIN)"
        lock = ", locked" if row["locked"] else ""
        lines.append(f"people {row['status']}, {state}{lock}: {row['n']}")
    devices = one(
        conn,
        "SELECT count(*) FILTER (WHERE identity.device_live(d, %s)) AS live, "
        "count(*) FILTER (WHERE NOT identity.device_live(d, %s)) AS not_live "
        "FROM identity.trusted_devices AS d",
        (at, at),
    )
    lines.append(
        f"devices live at the extraction instant: {devices['live']}; "
        f"not live: {devices['not_live']}"
    )
    for row in conn.execute(
        "SELECT coalesce(m.name, 'no main category') AS main, count(*) AS n "
        "FROM setup.expense_categories AS c LEFT JOIN setup.expense_main_categories AS m "
        "ON m.organization_id = c.organization_id AND m.id = c.main_category_id "
        "GROUP BY 1 ORDER BY 1"
    ):
        lines.append(f"categories under {row['main']}: {row['n']}")
    sets = one(
        conn,
        "SELECT count(*) AS sets, count(DISTINCT vehicle_id) AS vehicles "
        "FROM setup.vehicle_target_sets",
    )
    lines.append(f"target sets: {sets['sets']} for {sets['vehicles']} vehicles")
    return Check("figures for the owner", True, "", lines)


def _record(
    conn: Connection, summary: dict[str, Any], name: str | None, checks: list[Check]
) -> None:
    audit = conn.execute("SELECT max(id) AS top FROM tenancy.audit_events").fetchone()
    if audit is not None and audit["top"] is not None:
        conn.execute(
            "SELECT setval(pg_get_serial_sequence('tenancy.audit_events', 'id'), %s)",
            (audit["top"],),
        )
    counts: dict[str, int] = defaultdict(int)
    for table in summary["tables"]:
        counts[table["target"]] = table["loaded"]
    detail = {
        "tool": __version__,
        "manifest_sha256": summary["manifest_sha256"],
        "extracted_at": summary["extracted_at"],
        "source": summary["source"],
        "loaded": counts,
        "dropped": len(summary["dropped"]),
        "refused": len(summary["rejected"]),
        "changed": len(summary["changed"]),
        "checks": len(checks),
    }
    conn.execute(
        "INSERT INTO ops.operator_actions (operator, action, target, detail, recorded_at) "
        "VALUES (%s, 'data_migration_load', current_database(), %s, now())",
        (name, Jsonb(detail)),
    )
