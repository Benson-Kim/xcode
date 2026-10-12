"""``report``: what moved, what did not, what changed, and every verification, for the DBA."""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .load import LOAD
from .records import ToolError
from .transform import MANIFEST, TRANSFORM

type Out = Callable[[str], None]


def _read(path: Path) -> dict[str, Any] | None:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def run(work_dir: Path, out: Out = print, everything: bool = False, limit: int = 50) -> int:
    manifest = _read(work_dir / MANIFEST)
    summary = _read(work_dir / TRANSFORM)
    if manifest is None or summary is None:
        raise ToolError(f"{work_dir} holds no transform: run transform (or load) first")
    load = _read(work_dir / LOAD)
    source = manifest["source"]
    out("DATA MIGRATION REPORT")
    out(
        f"  extracted   {manifest['extracted_at']} from {source.get('database')} "
        f"(SQL Server {source.get('server_version')}; {source.get('snapshot')}; "
        f"latest EF migration {source.get('latest_migration')})"
    )
    target = summary["target"]
    out(
        f"  transformed {summary['written_at']} against {target['database']} at migration "
        f"{target['migration']:04d} (PostgreSQL {target['server_version']})"
    )
    if load is not None:
        out(
            f"  load        {load['mode']} by {load['operator'] or '-'} at {load['finished_at']}: "
            f"{'COMMITTED' if load['committed'] else 'rolled back, nothing written'}"
        )
    else:
        out("  load        not run")

    checks = {c["name"]: c for c in (load or {}).get("checks", [])}
    checksum_lines = " ".join(
        checks.get("each table's ordered rows equal its load file byte for byte (SHA-256)", {}).get(
            "lines", []
        )
    )
    out("")
    out("TABLES (source rows = loaded + dropped + refused - made)")
    out(
        f"  {'source':<28} {'target':<38} {'source':>7} {'made':>6} {'dropped':>7} "
        f"{'refused':>7} {'loaded':>7}  checksum"
    )
    for t in summary["tables"]:
        if load is None:
            checksum = "not loaded"
        elif t["target"] in checksum_lines:
            checksum = "DIFFERS"
        else:
            checksum = "match"
        out(
            f"  {t['source'] or '(made)':<28} {t['target']:<38} {t['source_rows']:>7} "
            f"{t['made']:>6} {t['dropped']:>7} {t['rejected']:>7} {t['loaded']:>7}  {checksum}"
        )
    for entry in summary["not_migrated"]:
        out(
            f"  {entry['source']:<28} {'not copied':<38} {entry['rows'] or 0:>7}  "
            f"({entry['reason']})"
        )

    out("")
    out(f"REFUSED ROWS ({len(summary['rejected'])}; {summary['blocking']} blocking)")
    for r in summary["rejected"]:
        flag = " BLOCKING" if r["blocking"] else ""
        out(f"  {r['table']} {r['key']}: {r['problem']} [{r['constraint'] or '-'}]{flag}")

    out("")
    out(f"DROPPED BY A DOCUMENTED RULE ({len(summary['dropped'])})")
    by_reason: dict[tuple[str, str], list[str]] = defaultdict(list)
    for d in summary["dropped"]:
        by_reason[(d["table"], d["reason"])].append(d["key"])
    for (table, reason), keys in sorted(by_reason.items()):
        out(f"  {table} {reason}: {len(keys)}")
        for key in keys if everything else keys[:limit]:
            out(f"    {key}")
        if not everything and len(keys) > limit:
            out(f"    ... {len(keys) - limit} more (report --all)")

    out("")
    out(f"CHANGED VALUES ({len(summary['changed'])})")
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for c in summary["changed"]:
        groups[(c["table"], c["column"], c["reason"])].append(c)
    for (table, column, reason), items in sorted(groups.items()):
        out(f"  {table}.{column}: {reason} ({len(items)})")
        for c in items if everything else items[:limit]:
            out(f"    {c['key']}: {c['from']!r} -> {c['to']!r}")
        if not everything and len(items) > limit:
            out(f"    ... {len(items) - limit} more (report --all)")
    for p in summary["precision"]:
        out(
            f"  {p['table']}.{p['column']}: the 100 ns digit rounded half to even to the "
            f"microsecond ({p['rounded']})"
        )

    out("")
    out(f"MADE BY THE TRANSFORM ({len(summary['derived'])})")
    made: dict[str, int] = defaultdict(int)
    for d in summary["derived"]:
        made[d["table"]] += 1
    for table, count in sorted(made.items()):
        out(f"  {table}: {count}")
        if table != "tenancy.permission_overrides":
            for d in [d for d in summary["derived"] if d["table"] == table][:limit]:
                out(f"    {d['key']}: {d['note']}")

    out("")
    out(f"RIGHTS PER PERSON, OLD -> NEW ({len(summary['permissions'])})")
    for p in summary["permissions"]:
        out(
            f"  {p['organization_id']} {p['user_id']} ({p['role'] or 'no role'}): "
            f"{len(p['old'])} -> {len(p['new'])} rights"
        )
        if p["not_carried"]:
            out(f"    not carried: {', '.join(p['not_carried'])}")
        if p["gained"]:
            out(f"    gained: {', '.join(p['gained'])}")

    out("")
    out("REVENUE PER ORGANIZATION AND MONTH (source - not moved = expected)")
    for org, months in sorted(summary["revenue"].items()):
        for month, cell in sorted(months.items()):
            out(f"  {org} {month}: {cell['source']} - {cell['excluded']}")

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
