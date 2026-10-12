"""``extract`` against a real SQL Server: only when ``SQLSERVER_TEST_CONNECTION`` is set, the
convention of the .NET ``SqlServerTests``. The extract only reads."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from migrate_from_sqlserver.cli import main
from migrate_from_sqlserver.formats import parse_csv
from migrate_from_sqlserver.tablemap import NOT_MIGRATED, TABLES

CONNECTION = os.environ.get("SQLSERVER_TEST_CONNECTION")
pytestmark = [
    pytest.mark.sqlserver,
    pytest.mark.skipif(not CONNECTION, reason="SQLSERVER_TEST_CONNECTION is not set"),
]


def test_extract_writes_every_mapped_table_with_its_checksum(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("pyodbc")
    monkeypatch.setenv("XCODE_MIGRATION_SOURCE_URL", str(CONNECTION))
    out = tmp_path / "extract"
    assert main(["extract", "--output", str(out), "--frozen"]) == 0
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    sources = [t.source for t in TABLES if t.source is not None]
    assert set(manifest["tables"]) == set(sources) | {name for name, _ in NOT_MIGRATED}
    assert manifest["source"]["server_version"]
    for table in TABLES:
        if table.source is None or manifest["tables"][table.source].get("absent"):
            continue
        entry = manifest["tables"][table.source]
        data = (out / entry["file"]).read_bytes()
        assert hashlib.sha256(data).hexdigest() == entry["sha256"]
        header, rows = parse_csv(data)
        assert header == [c.source for c in table.source_columns]
        assert len(rows) == entry["rows"]
        keys = [header.index(k) for k in table.key]
        ordered = [tuple(r[i] or "" for i in keys) for r in rows]
        assert ordered == sorted(ordered)
    assert main(["extract", "--output", str(out), "--frozen"]) == 1
