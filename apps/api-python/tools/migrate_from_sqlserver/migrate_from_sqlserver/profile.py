"""What a source kind gives the shared engine: its table map, its extract files, its
conversions and drop rules, and the hooks that build its context and its extra results.

``transform``, ``load`` and ``report`` read the source kind from ``manifest.json``
(``source.kind``; an extract without one is SQL Server's) and run over the profile of that
kind: ``SQLSERVER`` (``tablemap.py``, ``conversions.py``) or ``legacy`` (``legacy_*.py``).
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .database import Connection
from .formats import Cell
from .records import Ledger, Record, ToolError
from .tablemap import Column, Table

MANIFEST = "manifest.json"
SQLSERVER = "sqlserver"
LEGACY = "legacy"
KINDS = (SQLSERVER, LEGACY)


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

    @property
    def kind(self) -> str:
        kind = str(self.data.get("source", {}).get("kind") or SQLSERVER)
        if kind not in KINDS:
            raise ToolError(f"manifest.json names an unknown source kind {kind!r}")
        return kind

    def table(self, name: str) -> dict[str, Any] | None:
        entry = self.data["tables"].get(name)
        return dict(entry) if entry is not None else None


@dataclass(frozen=True, slots=True)
class SourceFile:
    """One extract file: the rows of a target table, or rows only read (``target`` names the
    ledger table its refusals are filed under)."""

    name: str
    target: str
    key: tuple[str, ...]
    columns: tuple[Column, ...]
    read_only: bool = False


def files_of(tables: Sequence[Table]) -> tuple[SourceFile, ...]:
    return tuple(
        SourceFile(t.source, t.target, t.key, t.source_columns)
        for t in tables
        if t.source is not None
    )


@dataclass(frozen=True, slots=True)
class Person:
    """One row of ``--people``: where a legacy user moves (personal details: never printed)."""

    line: int
    legacy_email: str
    email: str
    phone: str
    role: str | None


@dataclass(frozen=True, slots=True)
class Options:
    fleet_numbers: Mapping[str, str] | None = None
    organization_name: str | None = None
    organization_slug: str | None = None
    migrated_by: str | None = None
    people: Mapping[str, Person] | None = None

    @property
    def legacy(self) -> bool:
        return any(
            v is not None
            for v in (
                self.organization_name,
                self.organization_slug,
                self.migrated_by,
                self.people,
            )
        )


@dataclass
class TableResult:
    table: Table
    source_rows: int
    rows: list[Record]
    cells: list[tuple[Cell, ...]]

    def target_key(self, cells: Sequence[Cell]) -> tuple[Cell, ...]:
        names = [c.target for c in self.table.target_columns]
        return tuple(cells[names.index(k)] for k in self.table.target_key)


type Conversion = Callable[[Table, list[Record], Any], list[Record]]
type Drop = Callable[[Record, Any], bool]


@dataclass(frozen=True, slots=True)
class Profile:
    kind: str
    tables: tuple[Table, ...]
    files: tuple[SourceFile, ...]
    not_migrated: tuple[tuple[str, str], ...]
    conversions: Mapping[str, Conversion]
    drops: Mapping[str, Drop]
    blocking: frozenset[str]
    begin: Callable[[Connection, Manifest, Ledger, Options], Any]
    """The context the conversions share, made before any row is parsed."""
    prepare: Callable[[Connection, Any], None]
    """Runs once every file is parsed (``ctx.parsed``), before the first table."""
    finish: Callable[[Any, list[TableResult], Path], dict[str, Any]]
    """Keys added to ``transform.json`` (and any file of its own written into the work
    directory), once the target has accepted or refused every row."""
    details: bool = True
    """Whether a refusal carries the database's detail line (it can quote the row)."""
    made_by: frozenset[str] = field(default_factory=frozenset)
    """Conversions that make the rows of a table that also has a source."""
