"""Canonical CSV files, and value conversion from SQL Server text to PostgreSQL text.

Every file the tool writes or reads is UTF-8 CSV with LF line ends and one header row; every
non-null field is quoted and NULL is an empty unquoted field (``csv.QUOTE_NOTNULL``). That is
also what PostgreSQL's ``COPY ... (FORMAT csv)`` reads, and writes with ``FORCE_QUOTE *``.

The extract holds SQL Server values as text in one fixed form per type (``extract.py`` casts
them in T-SQL): GUIDs upper case, instants in UTC as ``YYYY-MM-DD HH:MM:SS.fffffff``, bits
``0``/``1``, binaries as upper-case hex, floats in round-trip scientific form. The load files
hold PostgreSQL's own text output (session ``TimeZone`` UTC, ``DateStyle`` ISO).
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation
from pathlib import Path

type Cell = str | None
type Value = object

_INSTANT = re.compile(r"(\d{4}-\d{2}-\d{2}) (\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,7}))?")
_INTEGER = re.compile(r"-?[0-9]+")
_DECIMAL = re.compile(r"-?[0-9]+(?:\.[0-9]+)?")


class InvalidValueError(ValueError):
    """A source value that cannot become the target value: the row is rejected with this text."""


def csv_bytes(header: Sequence[str], rows: Iterable[Sequence[Cell]]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, quoting=csv.QUOTE_NOTNULL, lineterminator="\n")
    writer.writerow(header)
    for row in rows:
        writer.writerow(row)
    return buffer.getvalue().encode("utf-8")


def header_bytes(header: Sequence[str]) -> bytes:
    return csv_bytes(header, ())


def parse_csv(data: bytes) -> tuple[list[str], list[tuple[Cell, ...]]]:
    reader = csv.reader(
        io.StringIO(data.decode("utf-8"), newline=""), quoting=csv.QUOTE_NOTNULL, strict=True
    )
    rows = list(reader)
    if not rows:
        raise ValueError("empty file: the header row is missing")
    header = [str(name) for name in rows[0]]
    width = len(header)
    body: list[tuple[Cell, ...]] = []
    for number, row in enumerate(rows[1:], start=2):
        if len(row) != width:
            raise ValueError(f"line {number} has {len(row)} fields, the header {width}")
        body.append(tuple(row))
    return header, body


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_file(path: Path, data: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return sha256(data)


@dataclass(frozen=True, slots=True)
class Instant:
    """An instant from SQL Server, rounded to PostgreSQL's microsecond (half to even)."""

    value: datetime
    rounded: bool


def parse_source(kind: str, text: str) -> Value:
    """Read one extract field of SQL Server type ``kind``."""
    try:
        match kind:
            case "uuid":
                if len(text) != 36:
                    raise InvalidValueError(f"not a GUID: {text!r}")
                return str(uuid.UUID(text))
            case "text" | "json":
                return text
            case "bit":
                if text not in {"0", "1"}:
                    raise InvalidValueError(f"not a bit: {text!r}")
                return text == "1"
            case "int" | "bigint":
                if not _INTEGER.fullmatch(text):
                    raise InvalidValueError(f"not an integer: {text!r}")
                return int(text)
            case "decimal":
                if not _DECIMAL.fullmatch(text):
                    raise InvalidValueError(f"not a decimal: {text!r}")
                return Decimal(text)
            case "date":
                return date.fromisoformat(text)
            case "datetime2" | "datetimeoffset":
                return parse_instant(text)
            case "binary":
                return bytes.fromhex(text)
            case "float":
                return float(text)
    except (ValueError, InvalidOperation) as exc:
        if isinstance(exc, InvalidValueError):
            raise
        raise InvalidValueError(f"not a {kind}: {text!r}") from exc
    raise ValueError(f"unknown source type {kind}")


def parse_instant(text: str) -> Instant:
    found = _INSTANT.fullmatch(text)
    if not found:
        raise InvalidValueError(f"not a UTC instant: {text!r}")
    day, hour, minute, second, fraction = found.groups()
    base = datetime.fromisoformat(f"{day}T{hour}:{minute}:{second}").replace(tzinfo=UTC)
    ticks = int((fraction or "").ljust(7, "0"))
    micro = int((Decimal(ticks) / 10).quantize(Decimal(1), rounding=ROUND_HALF_EVEN))
    return Instant(base + timedelta(microseconds=micro), ticks % 10 != 0)


def format_target(kind: str, value: Value, scale: int | None = None) -> Cell:
    """PostgreSQL's text output for ``value`` in a column of ``kind`` (session TimeZone UTC)."""
    if value is None:
        return None
    match kind:
        case "uuid" | "text" | "jsonb":
            return str(value)
        case "bool":
            return "t" if value else "f"
        case "int":
            if not isinstance(value, int) or isinstance(value, bool):
                raise InvalidValueError(f"not an integer: {value!r}")
            return str(value)
        case "numeric":
            return format_decimal(_as_decimal(value), scale)
        case "date":
            if not isinstance(value, date):
                raise InvalidValueError(f"not a date: {value!r}")
            return value.isoformat()
        case "timestamptz":
            moment = value.value if isinstance(value, Instant) else value
            if not isinstance(moment, datetime) or moment.tzinfo is None:
                raise InvalidValueError(f"not an instant: {value!r}")
            return format_instant(moment)
        case "bytea":
            if not isinstance(value, bytes):
                raise InvalidValueError(f"not bytes: {value!r}")
            return "\\x" + value.hex()
        case "float8":
            if not isinstance(value, float):
                raise InvalidValueError(f"not a float: {value!r}")
            text = repr(value)
            return text[:-2] if text.endswith(".0") else text
    raise ValueError(f"unknown target kind {kind}")


def _as_decimal(value: Value) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return Decimal(value)
    raise InvalidValueError(f"not a number: {value!r}")


def format_decimal(value: Decimal, scale: int | None) -> str:
    if scale is None:
        return format(value, "f")
    quantum = Decimal(1).scaleb(-scale)
    exact = value.quantize(quantum)
    if exact != value:
        raise InvalidValueError(f"{value} has more than {scale} decimal places")
    return format(exact, "f")


def format_instant(moment: datetime) -> str:
    utc = moment.astimezone(UTC)
    text = utc.strftime("%Y-%m-%d %H:%M:%S")
    if utc.microsecond:
        text += f".{utc.microsecond:06d}".rstrip("0")
    return text + "+00"


def same_json(left: str, right: str) -> bool:
    return bool(json.loads(left) == json.loads(right))


def duplicate_json_keys(text: str) -> list[str]:
    """Keys an object in ``text`` repeats: ``jsonb`` keeps only the last of each."""
    repeated: list[str] = []

    def pairs(items: list[tuple[str, object]]) -> dict[str, object]:
        seen: set[str] = set()
        for name, _ in items:
            if name in seen:
                repeated.append(name)
            seen.add(name)
        return dict(items)

    json.loads(text, object_pairs_hook=pairs)
    return repeated


def upper_c(text: str) -> str:
    """``upper(text COLLATE "C")``: only the ASCII letters change."""
    return "".join(chr(ord(ch) - 32) if "a" <= ch <= "z" else ch for ch in text)
