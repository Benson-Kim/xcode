"""Rows in flight and the ledger of everything the transform did to them."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

from .formats import Instant


class ToolError(RuntimeError):
    """A condition that stops the command before any write (exit status 1)."""


@dataclass
class Check:
    """One verification of the load: its name, whether it passed, and what it found."""

    name: str
    ok: bool
    detail: str
    lines: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "ok": self.ok, "detail": self.detail, "lines": self.lines}


def decimal_of(value: object, what: str) -> Decimal:
    if not isinstance(value, Decimal):
        raise ToolError(f"{what} is not a number: {value!r}")
    return value


def instant_of(value: object, what: str) -> datetime:
    moment = value.value if isinstance(value, Instant) else value
    if not isinstance(moment, datetime):
        raise ToolError(f"{what} is not an instant: {value!r}")
    return moment


@dataclass(slots=True)
class Record:
    key: str
    src: dict[str, object]
    values: dict[str, object]


@dataclass(frozen=True, slots=True)
class TargetCatalogue:
    catalogue: frozenset[str]
    keys: frozenset[str]
    dependencies: dict[str, frozenset[str]]
    role_defaults: dict[str, frozenset[str]]
    translations: dict[str, frozenset[str]]
    time_zones: frozenset[str]


def plain(value: object) -> object:
    """A JSON-safe form of a value for the ledger."""
    if isinstance(value, Instant):
        return value.value.isoformat()
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, bytes):
        return f"<{len(value)} bytes>"
    if value is None or isinstance(value, bool | int | float | str):
        return value
    return str(value)


@dataclass
class Ledger:
    changed: list[dict[str, Any]] = field(default_factory=list)
    dropped: list[dict[str, Any]] = field(default_factory=list)
    rejected: list[dict[str, Any]] = field(default_factory=list)
    derived: list[dict[str, Any]] = field(default_factory=list)
    precision: dict[tuple[str, str], int] = field(default_factory=dict)

    def change(
        self, table: str, key: str, column: str, old: object, new: object, reason: str
    ) -> None:
        self.changed.append(
            {
                "table": table,
                "key": key,
                "column": column,
                "from": plain(old),
                "to": plain(new),
                "reason": reason,
            }
        )

    def drop(self, table: str, source: str | None, key: str, reason: str) -> None:
        self.dropped.append({"table": table, "source": source, "key": key, "reason": reason})

    def reject(
        self,
        table: str,
        source: str | None,
        key: str,
        problem: str,
        constraint: str | None = None,
        blocking: bool = False,
    ) -> None:
        self.rejected.append(
            {
                "table": table,
                "source": source,
                "key": key,
                "constraint": constraint,
                "problem": problem,
                "blocking": blocking,
            }
        )

    def derive(self, table: str, key: str, note: str) -> None:
        self.derived.append({"table": table, "key": key, "note": note})

    def rounded(self, table: str, column: str) -> None:
        self.precision[(table, column)] = self.precision.get((table, column), 0) + 1
