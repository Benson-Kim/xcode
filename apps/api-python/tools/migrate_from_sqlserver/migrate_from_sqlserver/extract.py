"""``extract``: every mapped SQL Server table to one canonical CSV, plus ``manifest.json``.

One snapshot transaction reads everything (``SNAPSHOT`` isolation when the database allows
it; otherwise ``--frozen`` must state that the .NET API is in maintenance, and the read runs
under ``READ COMMITTED``). T-SQL casts each value to one fixed text form per type, so the
files do not depend on the driver: GUIDs ``CONVERT(char(36))`` (upper case), instants
converted to UTC as ``datetime2(7)`` style 121, dates style 23, bits ``0``/``1``, binaries
style 2 (hex), floats style 3 (round trip). Rows are ordered by the table's key, and each
file's SHA-256 goes into the manifest, which ``transform`` checks.
"""

from __future__ import annotations

import json
import os
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from . import __version__
from .database import production
from .formats import Cell, csv_bytes, parse_instant, write_file
from .records import ToolError
from .tablemap import NOT_MIGRATED, TABLES, Column

SOURCE_ENV = "XCODE_MIGRATION_SOURCE_URL"
SCHEMA = "dbo"
_CAST = {
    "uuid": "CONVERT(char(36), {c})",
    "text": "{c}",
    "json": "{c}",
    "bit": "CONVERT(char(1), {c})",
    "int": "CONVERT(varchar(20), {c})",
    "bigint": "CONVERT(varchar(20), {c})",
    "decimal": "CONVERT(varchar(48), {c})",
    "date": "CONVERT(char(10), {c}, 23)",
    "datetime2": "CONVERT(varchar(27), CONVERT(datetime2(7), {c}), 121)",
    "datetimeoffset": (
        "CONVERT(varchar(27), CONVERT(datetime2(7), SWITCHOFFSET({c}, '+00:00')), 121)"
    ),
    "binary": "CONVERT(varchar(max), {c}, 2)",
    "float": "CONVERT(varchar(32), {c}, 3)",
}
_ADO_KEYS = {
    "server": "Server",
    "data source": "Server",
    "address": "Server",
    "database": "Database",
    "initial catalog": "Database",
    "user id": "UID",
    "uid": "UID",
    "user": "UID",
    "password": "PWD",
    "pwd": "PWD",
    "integrated security": "Trusted_Connection",
    "trusted_connection": "Trusted_Connection",
    "encrypt": "Encrypt",
    "trustservercertificate": "TrustServerCertificate",
    "trust server certificate": "TrustServerCertificate",
    "connect timeout": "Connection Timeout",
    "connection timeout": "Connection Timeout",
    "applicationintent": "ApplicationIntent",
    "application intent": "ApplicationIntent",
    "driver": "Driver",
}
_YES = {
    "true": "yes",
    "yes": "yes",
    "sspi": "yes",
    "false": "no",
    "no": "no",
    "mandatory": "yes",
    "optional": "no",
    "strict": "strict",
}


def _pairs(value: str) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    item, depth = "", 0
    for ch in value + ";":
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth = max(0, depth - 1)
        if ch == ";" and depth == 0:
            if item.strip():
                name, _, setting = item.partition("=")
                pairs.append((name.strip(), setting.strip()))
            item = ""
        else:
            item += ch
    return pairs


def odbc_connection_string(value: str, drivers: Sequence[str], production: bool = False) -> str:
    """An ODBC connection string from an ODBC or ADO.NET one (the form ``SQLSERVER_TEST_CONNECTION``
    and the .NET ``ConnectionStrings__Auth`` use). Encryption is on unless the string says no."""
    settings: dict[str, str] = {}
    for name, setting in _pairs(value):
        key = _ADO_KEYS.get(name.lower(), name)
        if key in {"Trusted_Connection", "Encrypt", "TrustServerCertificate"}:
            settings[key] = _YES.get(setting.lower(), setting)
        else:
            settings[key] = setting
    if "Driver" not in settings:
        preferred = [d for d in drivers if d.startswith("ODBC Driver ") and "SQL Server" in d]
        if not preferred:
            raise ToolError("no Microsoft ODBC Driver for SQL Server is installed")
        settings["Driver"] = "{" + sorted(preferred)[-1] + "}"
    settings.setdefault("Encrypt", "yes")
    if production and (
        settings["Encrypt"].lower() not in {"yes", "strict"}
        or settings.get("TrustServerCertificate", "no").lower() == "yes"
    ):
        raise ToolError(
            "in production the SQL Server connection must be encrypted and check the server "
            "certificate (Encrypt=yes, no TrustServerCertificate)"
        )
    return ";".join(f"{k}={v}" for k, v in settings.items())


def _select(table_name: str, columns: Sequence[Column]) -> str:
    casts = ", ".join(_CAST[c.src].format(c=f"[{c.source}]") for c in columns)
    return f"SELECT {casts} FROM [{SCHEMA}].[{table_name}]"  # noqa: S608 - names from the map


def run(output_dir: Path, frozen: bool) -> dict[str, Any]:
    try:
        import pyodbc  # type: ignore[import-not-found]  # noqa: PLC0415 - only extract needs it
    except ImportError as exc:
        raise ToolError("extract needs pyodbc: pip install -r requirements.lock.txt") from exc
    url = os.environ.get(SOURCE_ENV, "").strip()
    if not url:
        raise ToolError(f"{SOURCE_ENV} is not set (the SQL Server connection string)")
    if (output_dir / "manifest.json").exists():
        raise ToolError(f"{output_dir} already holds an extract: use a new directory")
    output_dir.mkdir(parents=True, exist_ok=True)
    connection = odbc_connection_string(url, pyodbc.drivers(), production())
    conn = pyodbc.connect(connection, autocommit=True)
    try:
        cur = conn.cursor()
        cur.execute("SELECT snapshot_isolation_state FROM sys.databases WHERE name = DB_NAME()")
        snapshot = cur.fetchone()[0] == 1
        if not snapshot and not frozen:
            raise ToolError(
                "the source does not allow SNAPSHOT isolation: put the .NET API in maintenance "
                "and pass --frozen"
            )
        conn.autocommit = False
        level = "SNAPSHOT" if snapshot else "READ COMMITTED"
        cur.execute(f"SET TRANSACTION ISOLATION LEVEL {level}")
        cur.execute(
            "SELECT CONVERT(varchar(27), SYSUTCDATETIME(), 121), DB_NAME(), "
            "CONVERT(nvarchar(128), SERVERPROPERTY('ProductVersion')), @@VERSION"
        )
        moment, database, version, banner = cur.fetchone()
        extracted_at = parse_instant(str(moment)).value
        cur.execute(
            "SELECT TABLE_NAME, COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = ?",
            SCHEMA,
        )
        present: dict[str, set[str]] = {}
        for table_name, column_name in cur.fetchall():
            present.setdefault(str(table_name), set()).add(str(column_name))
        tables: dict[str, Any] = {}
        for table in TABLES:
            if table.source is None:
                continue
            if table.source not in present:
                tables[table.source] = {"absent": True, "rows": 0}
                continue
            columns = table.source_columns
            missing = [c.source for c in columns if c.source not in present[table.source]]
            if missing:
                raise ToolError(
                    f"{table.source} lacks {missing}: bring the .NET database to its latest "
                    "migration before the extract"
                )
            cur.execute(_select(table.source, columns))
            rows: list[tuple[Cell, ...]] = [
                tuple(None if v is None else str(v) for v in row) for row in cur.fetchall()
            ]
            names = [c.source for c in columns]
            positions = [names.index(k) for k in table.key]
            rows.sort(key=lambda r: tuple(r[i] or "" for i in positions))
            file = f"{table.source}.csv"
            digest = write_file(output_dir / file, csv_bytes(names, rows))  # type: ignore[arg-type]
            tables[table.source] = {"file": file, "rows": len(rows), "sha256": digest}
        for name, _ in NOT_MIGRATED:
            if name in present:
                cur.execute(f"SELECT COUNT_BIG(*) FROM [{SCHEMA}].[{name}]")  # noqa: S608
                tables[name] = {"rows": int(cur.fetchone()[0]), "copied": False}
            else:
                tables[name] = {"absent": True, "rows": 0, "copied": False}
        latest = None
        if "__EFMigrationsHistory" in present:
            cur.execute("SELECT MAX(MigrationId) FROM [dbo].[__EFMigrationsHistory]")
            latest = cur.fetchone()[0]
        conn.rollback()
    finally:
        conn.close()
    manifest = {
        "format": 1,
        "tool": __version__,
        "extracted_at": extracted_at.isoformat(),
        "source": {
            "database": database,
            "server_version": version,
            "server": str(banner).splitlines()[0],
            "snapshot": "SNAPSHOT isolation"
            if snapshot
            else "READ COMMITTED during a write freeze",
            "latest_migration": latest,
        },
        "tables": tables,
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    return manifest
