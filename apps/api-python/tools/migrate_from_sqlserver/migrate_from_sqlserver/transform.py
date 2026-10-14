"""``transform``: the extract becomes validated load files.

1. Every extract file is checked against ``manifest.json`` (row count, SHA-256, header).
2. Each row is parsed by its column types and mapped to the target columns; documented drop
   predicates and the table's conversions run; every changed value goes to the ledger.
3. In one transaction on the target that is always rolled back, the rows are copied in
   foreign-key order. A refused batch is halved until each refused row stands alone, so each
   violation is reported with its source key; rows that reference a refused row are refused
   by their foreign key in turn.
4. PostgreSQL's own export of the accepted rows becomes the load file, after a check that it
   holds exactly the values the transform produced.

The table map, conversions and extra results come from the profile of the extract's source
kind (``profile.py``): SQL Server's here, the legacy database's in ``legacy_conversions.py``.
"""

from __future__ import annotations

import json
import shutil
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import psycopg

from . import __version__
from . import legacy_conversions as legacy
from .conversions import CONVERSIONS, DROPS, Context
from .database import (
    Connection,
    Refusal,
    check_deferred,
    copy_out,
    insert_rows,
    inspect_target,
    known_time_zones,
    read_catalogue,
    refuse_unless_empty,
)
from .formats import (
    Cell,
    Instant,
    InvalidValueError,
    csv_bytes,
    format_target,
    parse_csv,
    parse_source,
    same_json,
    sha256,
    write_file,
)
from .profile import (
    LEGACY,
    MANIFEST,
    SQLSERVER,
    Manifest,
    Options,
    Profile,
    SourceFile,
    TableResult,
    files_of,
)
from .records import Ledger, Record, ToolError, decimal_of, plain
from .tablemap import EXTRACTED_AT, NOT_MIGRATED, TABLES, Column, Table
from .timezones import WINDOWS_TO_IANA

__all__ = ["MANIFEST", "OLD_SETS", "TRANSFORM", "Manifest", "TableResult", "profile_for", "run"]

BLOCKING = frozenset({"identity.users", "tenancy.organizations"})
"""A refused row here cascades through every table; the load refuses until it is fixed."""

TRANSFORM = "transform.json"
OLD_SETS = "permission_old_sets.csv"


def load_extract(
    directory: Path, manifest: Manifest, files: Sequence[SourceFile] | None = None
) -> dict[str, list[tuple[Cell, ...]]]:
    """Every extract file whose bytes, rows and header match the manifest."""
    found: dict[str, list[tuple[Cell, ...]]] = {}
    for source in files if files is not None else files_of(TABLES):
        entry = manifest.table(source.name)
        if entry is None:
            raise ToolError(f"manifest.json does not list {source.name}")
        if entry.get("absent"):
            found[source.name] = []
            continue
        data = (directory / entry["file"]).read_bytes()
        if sha256(data) != entry["sha256"]:
            raise ToolError(f"{entry['file']} does not match its SHA-256 in manifest.json")
        header, rows = parse_csv(data)
        expected = [c.source for c in source.columns]
        if header != expected:
            raise ToolError(f"{entry['file']} has columns {header}, the map expects {expected}")
        if len(rows) != entry["rows"]:
            raise ToolError(f"{entry['file']} has {len(rows)} rows, manifest.json {entry['rows']}")
        found[source.name] = rows
    return found


def source_key(table: Table | SourceFile, raw: Mapping[str, Cell]) -> str:
    return "|".join(f"{name}={raw[name]}" for name in table.key)


def parse_row(
    table: Table | SourceFile, cells: Sequence[Cell], ledger: Ledger
) -> tuple[str, Record | InvalidValueError]:
    columns = table.source_columns if isinstance(table, Table) else table.columns
    raw = {c.source: cells[i] for i, c in enumerate(columns) if c.source is not None}
    key = source_key(table, raw)
    record = Record(key, {}, {})
    try:
        for column in columns:
            source = str(column.source)
            text = raw[source]
            value = None if text is None else _parse(column, text)
            if isinstance(value, Instant) and value.rounded:
                ledger.rounded(table.target, column.target or source)
            record.src[source] = (
                parse_source(column.src, text) if column.values and text is not None else value
            )
            if column.target is not None:
                record.values[column.target] = value
    except InvalidValueError as problem:
        return key, problem
    return key, record


def _parse(column: Column, text: str) -> object:
    if column.src in {"text", "json"} and "\x00" in text:
        raise InvalidValueError(f"{column.source} holds U+0000, which PostgreSQL text cannot store")
    if column.values is not None:
        if text not in column.values:
            raise InvalidValueError(f"{column.source} {text!r} is not a known value")
        return column.values[text]
    value = parse_source(column.src, text)
    if column.src == "json":
        try:
            json.loads(text)
        except ValueError as exc:
            raise InvalidValueError(f"{column.source} is not JSON: {exc}") from exc
    return value


def format_row(table: Table, record: Record, extracted_at: datetime) -> tuple[Cell, ...]:
    cells: list[Cell] = []
    for column in table.target_columns:
        if column.fixed:
            value = extracted_at if column.const == EXTRACTED_AT else column.const
        elif column.target not in record.values:
            raise ToolError(f"{table.target}.{column.target} was not filled for {record.key}")
        else:
            value = record.values[column.target]
        cell = format_target(column.kind, value, column.scale)
        if cell is not None and column.precision is not None and column.scale is not None:
            bound = Decimal(10) ** (column.precision - column.scale)
            if abs(Decimal(cell)) >= bound:
                raise InvalidValueError(
                    f"{column.target} {cell} does not fit "
                    f"numeric({column.precision},{column.scale})"
                )
        cells.append(cell)
    return tuple(cells)


def _sqlserver_context(
    conn: Connection, manifest: Manifest, ledger: Ledger, options: Options
) -> Context:
    if options.legacy:
        raise ToolError(
            "--people, --migrated-by, --organization-name and --organization-slug are for an "
            "extract of the legacy database, and this one is SQL Server's"
        )
    return Context(
        extracted_at=manifest.extracted_at,
        parsed={},
        catalogue=read_catalogue(conn),
        ledger=ledger,
        fleet_numbers=options.fleet_numbers,
    )


def _sqlserver_zones(conn: Connection, ctx: Context) -> None:
    zones = {
        str(row.values["time_zone"])
        for source in ("Localizations", "UserPreferences")
        for row in ctx.parsed.get(source, [])
        if row.values.get("time_zone") is not None
    }
    zones |= {WINDOWS_TO_IANA[z] for z in zones if z in WINDOWS_TO_IANA}
    ctx.catalogue = replace(ctx.catalogue, time_zones=known_time_zones(conn, zones))


def _sqlserver_finish(ctx: Context, results: list[TableResult], output_dir: Path) -> dict[str, Any]:
    old_sets = [
        (str(s["organization_id"]), str(s["user_id"]), key)
        for s in ctx.permission_sets or []
        for key in s["old"]  # type: ignore[attr-defined]
    ]
    old_sets_sha = write_file(
        output_dir / OLD_SETS, csv_bytes(("organization_id", "user_id", "permission"), old_sets)
    )
    return {
        "permissions": ctx.permission_sets or [],
        "permission_old_sets": {"file": OLD_SETS, "sha256": old_sets_sha},
        "revenue": _revenue_sums(ctx, results),
    }


SQLSERVER_PROFILE = Profile(
    kind=SQLSERVER,
    tables=TABLES,
    files=files_of(TABLES),
    not_migrated=NOT_MIGRATED,
    conversions=CONVERSIONS,
    drops=DROPS,
    blocking=BLOCKING,
    begin=_sqlserver_context,
    prepare=_sqlserver_zones,
    finish=_sqlserver_finish,
    made_by=frozenset({"permission_translation"}),
)


def profile_for(kind: str) -> Profile:
    return legacy.PROFILE if kind == LEGACY else SQLSERVER_PROFILE


def run(
    input_dir: Path,
    output_dir: Path,
    conn: Connection,
    fleet_numbers: Mapping[str, str] | None = None,
    options: Options | None = None,
) -> dict[str, Any]:
    manifest = Manifest.read(input_dir)
    profile = profile_for(manifest.kind)
    options = options or Options(fleet_numbers=fleet_numbers)
    extract = load_extract(input_dir, manifest, profile.files)
    state = inspect_target(conn, profile.tables)
    refuse_unless_empty(conn, state)
    ledger = Ledger()
    ctx = profile.begin(conn, manifest, ledger, options)

    for source in profile.files:
        parsed: list[Record] = []
        for line in extract[source.name]:
            key, outcome = parse_row(source, line, ledger)
            if isinstance(outcome, InvalidValueError):
                if source.read_only:
                    raise ToolError(f"{source.name} {key}: {outcome}")
                ledger.reject(source.target, source.name, key, str(outcome), "parse")
            else:
                parsed.append(outcome)
        ctx.parsed[source.name] = parsed
    profile.prepare(conn, ctx)

    results: list[TableResult] = []
    for table in profile.tables:
        rows = list(ctx.parsed.get(table.source, [])) if table.source else []
        source_rows = len(extract[table.source]) if table.source else 0
        if table.target not in state.present:
            if rows or source_rows:
                raise ToolError(
                    f"the source has {source_rows} {table.source} rows but the target has no "
                    f"{table.target}: apply migration {table.since:04d} to the target first"
                )
            continue
        for name in table.drops:
            kept = []
            for row in rows:
                if profile.drops[name](row, ctx):
                    ledger.drop(table.target, table.source, row.key, name)
                else:
                    kept.append(row)
            rows = kept
        for name in table.convert:
            rows = profile.conversions[name](table, rows, ctx)
        cells: list[tuple[Cell, ...]] = []
        kept = []
        for row in rows:
            try:
                cells.append(format_row(table, row, manifest.extracted_at))
                kept.append(row)
            except InvalidValueError as problem:
                ledger.reject(table.target, table.source, row.key, str(problem), "format")
        results.append(TableResult(table, source_rows, kept, cells))

    exports, deferred = _validate(conn, results, ledger, profile)
    return _write(input_dir, output_dir, manifest, state, results, exports, ctx, deferred, profile)


def _validate(
    conn: Connection,
    results: list[TableResult],
    ledger: Ledger,
    profile: Profile = SQLSERVER_PROFILE,
) -> tuple[dict[str, bytes], Refusal | None]:
    """Copy every table into the target inside a transaction that is rolled back; keep the
    rows the database accepts and PostgreSQL's export of them. A deferred rule the accepted
    rows break (a refused vehicle takes its allocations with it) is returned rather than
    raised, so the refused rows behind it are still written out."""
    exports: dict[str, bytes] = {}
    try:
        with conn.transaction(force_rollback=True):
            for result in results:
                table = result.table
                columns = [str(c.target) for c in table.target_columns]
                refused: dict[int, Refusal] = {}
                insert_rows(
                    conn, table.target, columns, result.cells, refused.__setitem__, profile.details
                )
                for index, why in sorted(refused.items()):
                    ledger.reject(
                        table.target,
                        table.source,
                        result.rows[index].key,
                        why.problem,
                        why.constraint,
                        blocking=table.target in profile.blocking,
                    )
                result.rows = [r for i, r in enumerate(result.rows) if i not in refused]
                result.cells = [c for i, c in enumerate(result.cells) if i not in refused]
                exports[table.target] = copy_out(conn, table.target, columns, table.target_key)
                _compare(result, columns, exports[table.target])
            deferred = check_deferred(conn, profile.details)
    except psycopg.Error as exc:
        raise ToolError(f"the target refused the validation pass: {exc}") from exc
    return exports, deferred


def _compare(result: TableResult, columns: list[str], exported: bytes) -> None:
    """The database holds exactly the values the transform produced (no value was read in
    another time zone, rounded, or truncated on the way in)."""
    header, rows = parse_csv(exported)
    if header != columns:
        raise ToolError(f"{result.table.target}: exported columns {header}, expected {columns}")
    expected = {result.target_key(cells): cells for cells in result.cells}
    if len(rows) != len(expected):
        raise ToolError(
            f"{result.table.target}: the target holds {len(rows)} rows, "
            f"the transform {len(expected)}"
        )
    kinds = [c.kind for c in result.table.target_columns]
    for row in rows:
        mine = expected.get(result.target_key(row))
        if mine is None:
            raise ToolError(
                f"{result.table.target}: the target holds a row the transform did not make"
            )
        for name, kind, theirs, ours in zip(columns, kinds, row, mine, strict=True):
            equal = theirs == ours or (
                kind == "jsonb"
                and theirs is not None
                and ours is not None
                and same_json(theirs, ours)
            )
            if not equal:
                raise ToolError(
                    f"{result.table.target}.{name}: the target holds {theirs!r} where the "
                    f"transform wrote {ours!r} (key {result.target_key(row)})"
                )


def _write(
    input_dir: Path,
    output_dir: Path,
    manifest: Manifest,
    state: Any,
    results: list[TableResult],
    exports: dict[str, bytes],
    ctx: Any,
    deferred: Refusal | None,
    profile: Profile = SQLSERVER_PROFILE,
) -> dict[str, Any]:
    ledger: Ledger = ctx.ledger
    output_dir.mkdir(parents=True, exist_ok=True)
    if output_dir.resolve() != input_dir.resolve():
        shutil.copyfile(manifest.path, output_dir / MANIFEST)
    counts: dict[tuple[str, str], int] = defaultdict(int)
    for entry in ledger.dropped:
        counts[(entry["table"], "dropped")] += 1
    for entry in ledger.rejected:
        counts[(entry["table"], "rejected")] += 1
    tables: list[dict[str, Any]] = []
    for result in results:
        table = result.table
        file = f"load/{table.order:02d}_{table.target}.csv"
        digest = write_file(output_dir / file, exports[table.target])
        tables.append(
            {
                "order": table.order,
                "source": table.source,
                "target": table.target,
                "source_rows": result.source_rows,
                "dropped": counts[(table.target, "dropped")],
                "rejected": counts[(table.target, "rejected")],
                "made": sum(1 for d in ledger.derived if d["table"] == table.target)
                if table.source is None or profile.made_by & set(table.convert)
                else 0,
                "loaded": len(result.cells),
                "file": file,
                "sha256": digest,
                "columns": [c.target for c in table.target_columns],
                "key": list(table.target_key),
            }
        )
    summary: dict[str, Any] = {
        "tool": __version__,
        "written_at": datetime.now(UTC).isoformat(),
        "manifest_sha256": sha256(manifest.path.read_bytes()),
        "extracted_at": manifest.extracted_at.isoformat(),
        "source": manifest.data.get("source", {}),
        "target": {
            "database": state.database,
            "server_version": state.server_version,
            "migration": state.migration,
        },
        "tables": tables,
        "not_migrated": [
            {"source": name, "rows": (manifest.table(name) or {}).get("rows"), "reason": why}
            for name, why in profile.not_migrated
        ],
        "rejected": ledger.rejected,
        "blocking": sum(1 for r in ledger.rejected if r["blocking"]),
        "deferred": None
        if deferred is None
        else {"constraint": deferred.constraint, "problem": deferred.problem},
        "dropped": ledger.dropped,
        "changed": ledger.changed,
        "precision": [
            {"table": t, "column": c, "rounded": n}
            for (t, c), n in sorted(ledger.precision.items())
        ],
        "derived": ledger.derived,
    }
    summary.update(profile.finish(ctx, results, output_dir))
    (output_dir / TRANSFORM).write_text(
        json.dumps(summary, indent=2, default=plain) + "\n", encoding="utf-8", newline="\n"
    )
    return summary


def _revenue_sums(ctx: Context, results: list[TableResult]) -> dict[str, dict[str, dict[str, str]]]:
    """Per organization and month: the source sum, and the part of it not loaded."""
    loaded = {
        r.key for result in results if result.table.source == "RevenueRecords" for r in result.rows
    }
    sums: dict[str, dict[str, dict[str, Decimal]]] = defaultdict(
        lambda: defaultdict(lambda: {"source": Decimal(0), "excluded": Decimal(0)})
    )
    for row in ctx.parsed.get("RevenueRecords", []):
        if row.values["amount"] is None:
            continue
        amount = decimal_of(row.values["amount"], row.key)
        month = str(row.values["business_date"])[:7]
        cell = sums[str(row.values["organization_id"])][month]
        cell["source"] += amount
        if row.key not in loaded:
            cell["excluded"] += amount
    return {
        org: {m: {k: format(v, "f") for k, v in c.items()} for m, c in months.items()}
        for org, months in sums.items()
    }
