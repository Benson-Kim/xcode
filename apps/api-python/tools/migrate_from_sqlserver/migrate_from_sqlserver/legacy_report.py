"""The report of a legacy migration, and the owner's exceptions list (``exceptions.csv``).

People are named by role and legacy creation date, never by name, e-mail or number; payees do
not appear. The exceptions list has one row per held-back, left-out or dropped row, possible
double moved and petty-cash balance day (``docs/10-data-migration.md`` 7.2), with empty
Decision and Note columns for the owner.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Callable
from pathlib import Path
from typing import Any

from . import legacy_tablemap as m
from .formats import csv_bytes, write_file

type Out = Callable[[str], None]

EXCEPTIONS = "exceptions.csv"
COLUMNS = (
    "kind",
    "day",
    "vehicle",
    "item",
    "amount",
    "entered",
    "reason",
    "legacy_table",
    "legacy_id",
    "decision",
    "note",
)
PERSONAL = frozenset({("identity.users", "email"), ("identity.users", "phone_number")})
TYPED = frozenset({"kind", "vehicle", "item", "reason"})
"""Columns that carry text typed in the old application (item names, cash labels)."""
FORMULA = ("=", "+", "-", "@", chr(9), chr(13))


def _cell(column: str, value: object) -> str:
    """The cell as a spreadsheet shows it: typed text that a spreadsheet would run as a formula
    gets a leading apostrophe; days and amounts stay as they are."""
    text = "" if value is None else str(value)
    return "'" + text if column in TYPED and text.startswith(FORMULA) else text


def write_exceptions(work_dir: Path, summary: dict[str, Any]) -> int:
    rows = [(*(_cell(c, e[c]) for c in COLUMNS[:-2]), "", "") for e in summary["exceptions"]]
    write_file(work_dir / EXCEPTIONS, csv_bytes(COLUMNS, rows))
    return len(rows)


def run(
    work_dir: Path,
    manifest: dict[str, Any],
    summary: dict[str, Any],
    load: dict[str, Any] | None,
    out: Out = print,
    everything: bool = False,
    limit: int = 50,
) -> int:
    def capped(items: list[Any]) -> list[Any]:
        return items if everything else items[:limit]

    source = manifest["source"]
    legacy = summary["legacy"]
    people = {f"id={p['user_id']}": p["label"] for p in summary["people"]}
    out("DATA MIGRATION REPORT (the legacy database, docs/10 section 7)")
    out(
        f"  extracted   {manifest['extracted_at']} from {source.get('database')} "
        f"(PostgreSQL {source.get('server_version')}; alembic {source.get('alembic_version')}; "
        f"{source.get('snapshot')})"
    )
    target = summary["target"]
    out(
        f"  transformed {summary['written_at']} against {target['database']} at migration "
        f"{target['migration']:04d} (PostgreSQL {target['server_version']}), organization "
        f"{legacy['organization']!r}"
    )
    if load is not None:
        out(
            f"  load        {load['mode']} by {load['operator'] or '-'} at {load['finished_at']}: "
            f"{'COMMITTED' if load['committed'] else 'rolled back, nothing written'}"
        )
    else:
        out("  load        not run")

    out("")
    out("LEGACY TABLES (rows = loaded + dropped by a rule + refused + replaced)")
    out(f"  {'file':<28} {'rows':>7} {'loaded':>7} {'dropped':>7} {'refused':>7} {'replaced':>8}")
    for s in summary["sources"]:
        out(
            f"  {s['file']:<28} {s['rows']:>7} {s['loaded']:>7} {s['dropped']:>7} "
            f"{s['refused']:>7} {s['replaced']:>8}"
        )
    for entry in summary["not_migrated"]:
        out(f"  {entry['source']:<28} {entry['rows'] or 0:>7} not read ({entry['reason']})")

    out("")
    out("TARGET TABLES (source rows + made = loaded + dropped + refused)")
    out(
        f"  {'target':<38} {'file':<18} {'source':>6} {'made':>5} {'dropped':>7} "
        f"{'refused':>7} {'loaded':>6}"
    )
    for t in summary["tables"]:
        out(
            f"  {t['target']:<38} {t['source'] or '(made)':<18} {t['source_rows']:>6} "
            f"{t['made']:>5} {t['dropped']:>7} {t['rejected']:>7} {t['loaded']:>6}"
        )

    out("")
    out(f"REFUSED AND HELD BACK ({len(summary['rejected'])}; {summary['blocking']} blocking)")
    groups: dict[tuple[str, str], list[str]] = defaultdict(list)
    for r in summary["rejected"]:
        flag = " BLOCKING" if r["blocking"] else ""
        groups[(r["table"], f"{r['problem']} [{r['constraint'] or '-'}]{flag}")].append(
            people.get(r["key"], r["key"])
        )
    for (table, problem), keys in sorted(groups.items()):
        out(f"  {table} {problem}: {len(keys)}")
        for key in capped(keys):
            out(f"    {key}")
    if summary["deferred"] is not None:
        out(f"  DEFERRED RULE BROKEN: {summary['deferred']['problem']} BLOCKING")

    out("")
    out(f"DROPPED BY A RULE OF docs/10 7.3 ({len(summary['dropped'])})")
    rules: dict[str, list[str]] = defaultdict(list)
    for d in summary["dropped"]:
        rules[d["reason"]].append(f"{d['source']} {d['key']}")
    for rule, keys in sorted(rules.items()):
        out(f"  {rule} ({len(keys)}): {m.RULES.get(rule, rule)}")
        for key in (
            capped(keys) if rule not in {"petty_cash_copy", "daily_balance", "budget"} else []
        ):
            out(f"    {key}")

    out("")
    out(f"CHANGED VALUES ({len(summary['changed'])})")
    changes: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for c in summary["changed"]:
        changes[(c["table"], c["column"], c["reason"])].append(c)
    for (table, column, reason), items in sorted(changes.items()):
        out(f"  {table}.{column}: {reason} ({len(items)})")
        for c in capped(items):
            if c["key"] in people:
                out(f"    {people[c['key']]}")
            elif (table, column) not in PERSONAL:
                out(f"    {c['key']}: {c['from']!r} -> {c['to']!r}")

    out("")
    made = Counter(d["table"] for d in summary["derived"])
    out(f"MADE BY THE TOOL ({len(summary['derived'])})")
    for table, count in sorted(made.items()):
        out(f"  {table}: {count}")

    out("")
    out(f"PEOPLE ({len(summary['people'])}; rights before and after in VERIFICATIONS)")
    for p in summary["people"]:
        marks = [
            *(["moves"] if p["moved"] else ["DOES NOT MOVE"]),
            *(["author of the old entries"] if p["migrated_by"] else []),
            *(["holds the float"] if p["holder"] else []),
        ]
        out(f"  {p['label']}: {', '.join(marks)}")
        out(
            f"    {len(p['legacy'])} legacy permissions -> {len(p['translated'])} rights translated"
        )
        if p["not_carried"]:
            out(f"    not carried: {', '.join(p['not_carried'])}")

    listed = summary["listed"]
    out("")
    out("LISTED FOR THE OWNER")
    for item in listed["uncategorised_items"]:
        out(f"  item without a category: {item['item']} ({item['records']} records held back)")
    for item in listed["merged_items"]:
        out(
            f"  merged item: {item['item']} into {item['into']} ({item['id']} -> {item['kept_id']})"
        )
    for p in listed["provisions"]:
        out(f"  provision balance (not moved, question 97): {p['vehicle']} {p['balance']}")
    out(f"  budgets (not moved, question 97): {len(listed['budgets'])} with a budget")
    for b in capped(listed["budgets"]):
        out(f"    {b['vehicle']} {b['month']} {b['category']}: {b['budget']}")

    count = write_exceptions(work_dir, summary)
    kinds = Counter(e["kind"] for e in summary["exceptions"])
    out("")
    out(f"EXCEPTIONS LIST ({count} rows in {work_dir / EXCEPTIONS})")
    for kind, n in sorted(kinds.items()):
        out(f"  {kind}: {n}")

    out("")
    if load is None:
        out("VERIFICATIONS: not run (load --dry-run runs them)")
        return 0
    out("VERIFICATIONS")
    for c in load["checks"]:
        mark = "ok  " if c["ok"] else "FAIL"
        out(f"  [{mark}] {c['name']}{': ' + c['detail'] if c['detail'] else ''}")
        for line in c["lines"] if everything or not c["ok"] else c["lines"][:limit]:
            out(f"         {line}")
    passed = all(c["ok"] for c in load["checks"])
    out("")
    if load["committed"]:
        out("RESULT: committed; every verification passed")
    elif passed:
        out("RESULT: every verification passed; nothing was written (dry run)")
    else:
        out("RESULT: verification failed; nothing was written")
    return 0
