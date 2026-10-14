"""The verifications of ``docs/10-data-migration.md`` 7.5 for the legacy database.

Each compares the target, inside the load's transaction, with the source figures the extract
worked out in SQL (``manifest.json`` ``figures``) less the part the transform says did not
move (``transform.json`` ``excluded``); the people checks read the target through the API's
own routines. ``source_ledger`` runs before the load: every row of every legacy table is
loaded, dropped by a named rule, refused, or replaced.
"""

from __future__ import annotations

import calendar
import secrets
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from datetime import date
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

import psycopg

from . import legacy_tablemap as m
from .database import Connection
from .profile import Manifest
from .records import Check

NAIROBI = ZoneInfo(m.TIME_ZONE)
_ZERO = Decimal(0)


def _n(value: object) -> Decimal:
    return _ZERO if value is None else Decimal(str(value))


def source_ledger(summary: dict[str, Any], manifest: Manifest) -> Check:
    """Each legacy table's rows are exactly its files' rows, and each file's rows are loaded,
    dropped by a named rule, refused, or replaced by rows the tool made."""
    files = manifest.data["tables"]
    counts = manifest.data["legacy_tables"]
    by_target = {t["target"]: t for t in summary["tables"]}
    targets = {t.source: t.target for t in m.TABLES if t.source is not None}
    dropped = Counter(str(d["source"]) for d in summary["dropped"])
    refused = Counter(str(r["source"]) for r in summary["rejected"])
    held: dict[str, int] = defaultdict(int)
    lines: list[str] = []
    for extract in m.EXTRACTS:
        rows = int(files[extract.name]["rows"])
        held[extract.table] += rows
        loaded = 0
        if extract.fate == m.LOADED:
            table = by_target.get(targets[extract.name])
            loaded = int(table["loaded"]) - int(table["made"]) if table else 0
        replaced = rows if extract.fate == m.REPLACED else 0
        moved = loaded + dropped[extract.name] + refused[extract.name] + replaced
        if rows != moved:
            lines.append(
                f"{extract.name}: {rows} rows, but {loaded} loaded, {dropped[extract.name]} "
                f"dropped, {refused[extract.name]} refused, {replaced} replaced"
            )
    for table, _ in m.COUNTED:
        held[table] += int(files[table]["rows"])
    for table in m.LEGACY_TABLES:
        if held[table] != int(counts[table]):
            lines.append(f"{table}: {counts[table]} rows in the source, {held[table]} in its files")
    return Check(
        "every legacy row is loaded, dropped by a named rule, refused, or replaced",
        not lines,
        f"{len(m.LEGACY_TABLES)} legacy tables",
        lines,
    )


def verify(conn: Connection, summary: dict[str, Any], manifest: Manifest) -> list[Check]:
    legacy = summary["legacy"]
    conn.execute("SELECT tenancy.enter_organization_as_operator(%s)", (legacy["organization_id"],))
    figures = manifest.data["figures"]
    excluded = summary["excluded"]
    costs = _expected_costs(figures, excluded)
    return [
        _people(conn, summary, figures),
        _rights(conn, summary),
        _holder(conn, legacy["holder"]),
        _revenue(conn, figures, excluded),
        _costs(conn, costs),
        _petty_cash(conn, figures, excluded),
        _postings(conn, legacy, costs, manifest),
        _not_signed_in(conn, summary, manifest),
    ]


def _people(conn: Connection, summary: dict[str, Any], figures: dict[str, Any]) -> Check:
    rows = {
        r["id"]: r
        for r in conn.execute(
            "SELECT u.id::text AS id, u.status, u.pin_hash IS NULL AS no_pin, m.active, "
            "r.name AS role, s.all_companies "
            "FROM identity.users AS u "
            "LEFT JOIN tenancy.memberships AS m ON m.user_id = u.id "
            "LEFT JOIN tenancy.person_roles AS pr "
            "  ON pr.organization_id = m.organization_id AND pr.user_id = u.id "
            "LEFT JOIN tenancy.roles AS r ON r.organization_id = pr.organization_id "
            "  AND r.id = pr.role_id "
            "LEFT JOIN tenancy.data_scopes AS s "
            "  ON s.organization_id = m.organization_id AND s.user_id = u.id"
        )
    }
    users = int(figures["people"][0]["users"])
    lines: list[str] = []
    if len(rows) != users:
        lines.append(f"the source has {users} users, the target {len(rows)} people")
    for person in summary["people"]:
        row = rows.get(person["user_id"])
        if row is None:
            lines.append(f"{person['label']}: not in the target")
            continue
        wrong = [
            what
            for what, ok in (
                ("not active", row["status"] == "active" and row["active"]),
                (f"role {row['role']}", row["role"] == person["role"]),
                ("no all-companies scope", row["all_companies"] is True),
                ("a PIN", row["no_pin"]),
            )
            if not ok
        ]
        if wrong:
            lines.append(f"{person['label']}: {', '.join(wrong)}")
    return Check(
        "every legacy user is a person: active membership, their role, all companies, no PIN",
        not lines,
        f"{len(rows)} people",
        lines,
    )


def _rights(conn: Connection, summary: dict[str, Any]) -> Check:
    catalogue = {
        r["key"] for r in conn.execute("SELECT key FROM tenancy.permissions WHERE catalogue")
    }
    organization_id = summary["legacy"]["organization_id"]
    lines: list[str] = []
    failed = False
    for person in summary["people"]:
        if not person["moved"]:
            continue
        row = conn.execute(
            "SELECT tenancy.assigned_permissions(%s, %s) AS keys",
            (organization_id, person["user_id"]),
        ).fetchone()
        assigned = set(row["keys"] if row is not None else []) & catalogue
        translated = set(person["translated"])
        owner = person["role"] == m.OWNER
        ok = translated <= assigned if owner else assigned == translated
        failed |= not ok
        lines.append(
            f"{person['label']}: {len(person['legacy'])} legacy permissions -> "
            f"{len(assigned)} rights" + ("" if ok else " MISMATCH")
        )
        lines.append(f"  before: {', '.join(person['legacy']) or '-'}")
        lines.append(f"  after:  {', '.join(sorted(assigned)) or '-'}")
        if person["not_carried"]:
            lines.append(f"  not carried: {', '.join(person['not_carried'])}")
        if not ok:
            missing = sorted(translated - assigned)
            extra = sorted(assigned - translated) if not owner else []
            lines.append(
                f"  missing: {', '.join(missing) or '-'}; extra: {', '.join(extra) or '-'}"
            )
    return Check(
        "each person's rights hold their translated legacy permissions (7.4)",
        not failed,
        "",
        lines,
    )


def _holder(conn: Connection, holder: str) -> Check:
    row = conn.execute(
        "SELECT count(*) AS n, count(*) FILTER (WHERE holder_id <> %s) AS other "
        "FROM pettycash.entries",
        (holder,),
    ).fetchone()
    other = int(row["other"]) if row else -1
    return Check(
        "every petty-cash entry is held by the one float holder",
        other == 0,
        f"{row['n'] if row else 0} entries",
        [] if other == 0 else [f"{other} entries held by someone else"],
    )


def _compare(
    expected: Mapping[tuple[str, str], Decimal],
    actual: Mapping[tuple[str, str], Decimal],
    what: str,
) -> list[str]:
    return [
        f"{key[0]} {key[1]}: expected {expected.get(key, _ZERO)} {what}, "
        f"target {actual.get(key, _ZERO)}"
        for key in sorted(set(expected) | set(actual))
        if expected.get(key, _ZERO) != actual.get(key, _ZERO)
    ]


def _minus(
    rows: Iterable[Mapping[str, Any]], excluded: Mapping[str, Any], field: str
) -> dict[tuple[str, str], Decimal]:
    out: dict[tuple[str, str], Decimal] = {}
    for row in rows:
        key = (str(row["vehicle"]), str(row["month"]))
        out[key] = _n(row[field]) - _n(excluded.get(key[0], {}).get(key[1], {}).get(field))
    return out


def _revenue(conn: Connection, figures: dict[str, Any], excluded: dict[str, Any]) -> Check:
    days = _minus(figures["revenue"], excluded["revenue"], "days")
    amounts = _minus(figures["revenue"], excluded["revenue"], "amount")
    target_days: dict[tuple[str, str], Decimal] = {}
    target_amounts: dict[tuple[str, str], Decimal] = {}
    for row in conn.execute(
        "SELECT vehicle_id::text AS vehicle, to_char(business_date, 'YYYY-MM') AS month, "
        "count(*) AS days, coalesce(sum(amount), 0) AS amount FROM revenue.records GROUP BY 1, 2"
    ):
        target_days[(row["vehicle"], row["month"])] = _n(row["days"])
        target_amounts[(row["vehicle"], row["month"])] = _n(row["amount"])
    lines = _compare(days, target_days, "days") + _compare(amounts, target_amounts, "")
    return Check(
        "revenue per vehicle and month: days and Earnings equal the source less what did not move",
        not lines,
        f"{sum(target_days.values())} days, {sum(target_amounts.values())}",
        lines,
    )


def _expected_costs(
    figures: dict[str, Any], excluded: dict[str, Any]
) -> dict[tuple[str, str], Decimal]:
    out: dict[tuple[str, str], Decimal] = {}
    for row in figures["vehicle_costs"]:
        key = (str(row["vehicle"]), str(row["month"]))
        out[key] = _n(row["amount"]) - _n(excluded["vehicle_costs"].get(key[0], {}).get(key[1]))
    return out


def _costs(conn: Connection, expected: dict[tuple[str, str], Decimal]) -> Check:
    actual: dict[tuple[str, str], Decimal] = {}
    for row in conn.execute(
        "SELECT vehicle_id::text AS vehicle, to_char(entry_date, 'YYYY-MM') AS month, "
        "sum(total) AS amount FROM ("
        "  SELECT vehicle_id, entry_date, total FROM expenses.entries WHERE removed_at IS NULL"
        "  UNION ALL"
        "  SELECT vehicle_id, entry_date, total FROM pettycash.entries"
        "  WHERE kind = 2 AND status = 2 AND removed_at IS NULL"
        ") AS costs GROUP BY 1, 2"
    ):
        actual[(row["vehicle"], row["month"])] = _n(row["amount"])
    lines = _compare(expected, actual, "")
    return Check(
        "vehicle costs per vehicle and month: central expenses and approved petty cash equal "
        "the source records less what did not move",
        not lines,
        f"{sum(actual.values())}",
        lines,
    )


def _petty_cash(conn: Connection, figures: dict[str, Any], excluded: dict[str, Any]) -> Check:
    expected: dict[tuple[str, str], Decimal] = {}
    for row in figures["petty_cash"]:
        out = excluded["petty_cash"].get(row["bucket"], {})
        expected[(row["bucket"], "count")] = _n(row["count"]) - _n(out.get("count"))
        expected[(row["bucket"], "amount")] = _n(row["amount"]) - _n(out.get("amount"))
    actual: dict[tuple[str, str], Decimal] = {}
    for row in conn.execute(
        "SELECT CASE kind WHEN 1 THEN 'cash' WHEN 3 THEN 'credit note' "
        "  ELSE CASE status WHEN 2 THEN 'expense approved' WHEN 1 THEN 'expense waiting' "
        "  ELSE 'expense ' || status END END AS bucket, count(*) AS count, "
        "  sum(total) AS amount FROM pettycash.entries WHERE removed_at IS NULL GROUP BY 1"
    ):
        actual[(row["bucket"], "count")] = _n(row["count"])
        actual[(row["bucket"], "amount")] = _n(row["amount"])
    lines = _compare(expected, actual, "")
    float_row = conn.execute(
        "SELECT coalesce(sum(CASE WHEN kind = 1 THEN total ELSE -total END), 0) AS amount "
        "FROM pettycash.entries WHERE removed_at IS NULL"
    ).fetchone()
    target_float = _n(float_row["amount"] if float_row else None)
    source_float = _n(figures["float"][0]["amount"])
    expected_float = source_float - _n(excluded["float"])
    if target_float != expected_float:
        lines.append(
            f"float: source {source_float} less {_n(excluded['float'])} not moved is "
            f"{expected_float}, target {target_float}"
        )
    balance = figures["daily_balance"][0]
    shown = [
        f"{bucket}: {actual.get((bucket, 'count'), _ZERO)} "
        f"for {actual.get((bucket, 'amount'), _ZERO)}"
        for bucket in sorted({k[0] for k in actual})
    ]
    shown.append(
        f"float {target_float} (source {source_float} over every row, less {_n(excluded['float'])})"
    )
    shown.append(
        f"not checked: the old daily balance read {balance['closing']} on {balance['day']}; it "
        f"first differs from its own entries on {balance['first_differs']} "
        f"({balance['days_differ']} days differ)"
    )
    return Check(
        "petty cash per kind and status, and the float, equal the source less what did not move",
        not lines,
        "",
        lines + shown if lines else shown,
    )


def _month_span(month: str) -> tuple[date, date]:
    year, number = (int(p) for p in month.split("-"))
    return date(year, number, 1), date(year, number, calendar.monthrange(year, number)[1])


def _postings(
    conn: Connection,
    legacy: dict[str, Any],
    costs: dict[tuple[str, str], Decimal],
    manifest: Manifest,
) -> Check:
    month = str(legacy["last_full_month"])
    first, last = _month_span(month)
    today = manifest.extracted_at.astimezone(NAIROBI).date()
    vehicles = [
        r["id"] for r in conn.execute("SELECT id::text AS id FROM setup.fleet_vehicles ORDER BY id")
    ]
    lines: list[str] = []
    total = _ZERO
    for vehicle in vehicles:
        row = conn.execute(
            "SELECT coalesce(sum(amount), 0) AS amount "
            "FROM setup.fleet_postings(ARRAY[%s]::uuid[], %s, %s, %s) WHERE kind = 1",
            (vehicle, first, last, today),
        ).fetchone()
        posted = _n(row["amount"] if row else None)
        total += posted
        expected = costs.get((vehicle, month), _ZERO)
        if posted != expected:
            registration = legacy["vehicles"].get(vehicle, vehicle)
            lines.append(f"{registration}: the vehicle report posts {posted}, expected {expected}")
    return Check(
        f"the vehicle report's postings for {month} (setup.fleet_postings) equal the vehicle costs",
        not lines,
        f"{len(vehicles)} vehicles, {total}",
        lines,
    )


def _not_signed_in(conn: Connection, summary: dict[str, Any], manifest: Manifest) -> Check:
    lines: list[str] = []
    reached = 0
    people = [p for p in summary["people"] if p["moved"]]
    for person in people:
        try:
            with conn.transaction(force_rollback=True):
                row = conn.execute(
                    "SELECT api.auth_start('data-migration-check', u.phone_number, "
                    "'data-migration-check', NULL, %s, true, %s) AS result "
                    "FROM identity.users AS u WHERE u.id = %s",
                    (secrets.token_hex(32).upper(), manifest.extracted_at, person["user_id"]),
                ).fetchone()
        except psycopg.Error as exc:
            lines.append(f"{person['label']}: {exc.diag.message_primary}")
            continue
        result = row["result"] if row else {}
        if (
            result.get("outcome") == "verification_required"
            and result.get("purpose") == "first_setup"
        ):
            reached += 1
        else:
            lines.append(
                f"{person['label']}: {result.get('outcome')} "
                f"({result.get('refusal') or result.get('purpose')})"
            )
    return Check(
        "people with a number reach 'Not signed in yet' through the sign-in routines",
        not lines and reached == len(people),
        f"{reached} of {len(people)} asked for a first-setup code",
        lines,
    )
