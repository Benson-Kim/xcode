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
"""

from __future__ import annotations

import json
import shutil
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import psycopg

from . import __version__
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
from .records import Ledger, Record, ToolError, decimal_of, plain
from .tablemap import EXTRACTED_AT, NOT_MIGRATED, TABLES, Column, Table
from .timezones import WINDOWS_TO_IANA

BLOCKING = frozenset({"identity.users", "tenancy.organizations"})
"""A refused row here cascades through every table; the load refuses until it is fixed."""

MANIFEST = "manifest.json"
TRANSFORM = "transform.json"
OLD_SETS = "permission_old_sets.csv"


@dataclass(frozen=True, slots=True)
class Manifest:
    path: Path
    data: dict[str, Any]
    extracted_at: datetime

    @classmethod
    def read(cls, directory: Path) -> Manifest:
        path = directory / MANIFEST
        if not path.is_file():
            raise ToolError(f"{path} is missing: run extract first")
        data = json.loads(path.read_text(encoding="utf-8"))
        moment = datetime.fromisoformat(str(data["extracted_at"]))
        if moment.tzinfo is None:
            raise ToolError("manifest.json extracted_at has no time zone")
        return cls(path, data, moment.astimezone(UTC))

    def table(self, name: str) -> dict[str, Any] | None:
        entry = self.data["tables"].get(name)
        return dict(entry) if entry is not None else None


def load_extract(directory: Path, manifest: Manifest) -> dict[str, list[tuple[Cell, ...]]]:
    """Every extract file whose bytes, rows and header match the manifest."""
    found: dict[str, list[tuple[Cell, ...]]] = {}
    for table in TABLES:
        if table.source is None:
            continue
        entry = manifest.table(table.source)
        if entry is None:
            raise ToolError(f"manifest.json does not list {table.source}")
        if entry.get("absent"):
            found[table.source] = []
            continue
        data = (directory / entry["file"]).read_bytes()
        if sha256(data) != entry["sha256"]:
            raise ToolError(f"{entry['file']} does not match its SHA-256 in manifest.json")
        header, rows = parse_csv(data)
        expected = [c.source for c in table.source_columns]
        if header != expected:
            raise ToolError(f"{entry['file']} has columns {header}, the map expects {expected}")
        if len(rows) != entry["rows"]:
            raise ToolError(f"{entry['file']} has {len(rows)} rows, manifest.json {entry['rows']}")
        found[table.source] = rows
    return found


def source_key(table: Table, raw: Mapping[str, Cell]) -> str:
    return "|".join(f"{name}={raw[name]}" for name in table.key)


def parse_row(
    table: Table, cells: Sequence[Cell], ledger: Ledger
) -> tuple[str, Record | InvalidValueError]:
    columns = table.source_columns
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


@dataclass
class TableResult:
    table: Table
    source_rows: int
    rows: list[Record]
    cells: list[tuple[Cell, ...]]

    def target_key(self, cells: Sequence[Cell]) -> tuple[Cell, ...]:
        names = [c.target for c in self.table.target_columns]
        return tuple(cells[names.index(k)] for k in self.table.target_key)


def run(
    input_dir: Path,
    output_dir: Path,
    conn: Connection,
    fleet_numbers: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    manifest = Manifest.read(input_dir)
    extract = load_extract(input_dir, manifest)
    state = inspect_target(conn, TABLES)
    refuse_unless_empty(conn, state)
    ledger = Ledger()
    ctx = Context(
        extracted_at=manifest.extracted_at,
        parsed={},
        catalogue=read_catalogue(conn),
        ledger=ledger,
        fleet_numbers=fleet_numbers,
    )

    for table in TABLES:
        if table.source is None:
            continue
        parsed: list[Record] = []
        for line in extract[table.source]:
            key, outcome = parse_row(table, line, ledger)
            if isinstance(outcome, InvalidValueError):
                ledger.reject(table.target, table.source, key, str(outcome), "parse")
            else:
                parsed.append(outcome)
        ctx.parsed[table.source] = parsed
    zones = {
        str(row.values["time_zone"])
        for source in ("Localizations", "UserPreferences")
        for row in ctx.parsed.get(source, [])
        if row.values.get("time_zone") is not None
    }
    zones |= {WINDOWS_TO_IANA[z] for z in zones if z in WINDOWS_TO_IANA}
    ctx.catalogue = replace(ctx.catalogue, time_zones=known_time_zones(conn, zones))

    results: list[TableResult] = []
    for table in TABLES:
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
                if DROPS[name](row, ctx):
                    ledger.drop(table.target, table.source, row.key, name)
                else:
                    kept.append(row)
            rows = kept
        for name in table.convert:
            rows = CONVERSIONS[name](table, rows, ctx)
        cells: list[tuple[Cell, ...]] = []
        kept = []
        for row in rows:
            try:
                cells.append(format_row(table, row, manifest.extracted_at))
                kept.append(row)
            except InvalidValueError as problem:
                ledger.reject(table.target, table.source, row.key, str(problem), "format")
        results.append(TableResult(table, source_rows, kept, cells))

    exports = _validate(conn, results, ledger)
    return _write(input_dir, output_dir, manifest, state, results, exports, ctx)


def _validate(conn: Connection, results: list[TableResult], ledger: Ledger) -> dict[str, bytes]:
    """Copy every table into the target inside a transaction that is rolled back; keep the
    rows the database accepts and PostgreSQL's export of them."""
    exports: dict[str, bytes] = {}
    try:
        with conn.transaction(force_rollback=True):
            for result in results:
                table = result.table
                columns = [str(c.target) for c in table.target_columns]
                refused: dict[int, Refusal] = {}
                insert_rows(conn, table.target, columns, result.cells, refused.__setitem__)
                for index, why in sorted(refused.items()):
                    ledger.reject(
                        table.target,
                        table.source,
                        result.rows[index].key,
                        why.problem,
                        why.constraint,
                        blocking=table.target in BLOCKING,
                    )
                result.rows = [r for i, r in enumerate(result.rows) if i not in refused]
                result.cells = [c for i, c in enumerate(result.cells) if i not in refused]
                exports[table.target] = copy_out(conn, table.target, columns, table.target_key)
                _compare(result, columns, exports[table.target])
            deferred = check_deferred(conn)
            if deferred is not None:
                raise ToolError(f"a deferred check failed: {deferred.problem}")
    except psycopg.Error as exc:
        raise ToolError(f"the target refused the validation pass: {exc}") from exc
    return exports


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
    ctx: Context,
) -> dict[str, Any]:
    ledger = ctx.ledger
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
                if table.source is None or "permission_translation" in table.convert
                else 0,
                "loaded": len(result.cells),
                "file": file,
                "sha256": digest,
                "columns": [c.target for c in table.target_columns],
                "key": list(table.target_key),
            }
        )
    old_sets = [
        (str(s["organization_id"]), str(s["user_id"]), key)
        for s in ctx.permission_sets or []
        for key in s["old"]  # type: ignore[attr-defined]
    ]
    old_sets_sha = write_file(
        output_dir / OLD_SETS, csv_bytes(("organization_id", "user_id", "permission"), old_sets)
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
            for name, why in NOT_MIGRATED
        ],
        "rejected": ledger.rejected,
        "blocking": sum(1 for r in ledger.rejected if r["blocking"]),
        "dropped": ledger.dropped,
        "changed": ledger.changed,
        "precision": [
            {"table": t, "column": c, "rounded": n}
            for (t, c), n in sorted(ledger.precision.items())
        ],
        "derived": ledger.derived,
        "permissions": ctx.permission_sets or [],
        "permission_old_sets": {"file": OLD_SETS, "sha256": old_sets_sha},
        "revenue": _revenue_sums(ctx, results),
    }
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
