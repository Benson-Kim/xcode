"""The template the database tests clone: rebuilt when the files change, never under a run."""

from __future__ import annotations

import secrets
from pathlib import Path

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from ..support.database import (
    TEMPLATE_USE_LOCK,
    Harness,
    _template_note,
    template_fingerprint,
)


def _db_tree(root: Path, routine: bytes) -> Path:
    db_dir = root / "db"
    for part in ("roles", "migrations", "routines/10_common"):
        (db_dir / part).mkdir(parents=True)
    (db_dir / "roles" / "010_roles.sql").write_bytes(b"SELECT 1;\n")
    (db_dir / "migrations" / "0001_ops.sql").write_bytes(b"SELECT 2;\n")
    (db_dir / "routines" / "10_common" / "x.sql").write_bytes(routine)
    return db_dir


def test_the_fingerprint_follows_every_db_file(tmp_path: Path) -> None:
    lf = template_fingerprint(_db_tree(tmp_path / "lf", b"SELECT 3;\nSELECT 4;\n"))
    crlf = template_fingerprint(_db_tree(tmp_path / "crlf", b"SELECT 3;\r\nSELECT 4;\r\n"))
    edited = template_fingerprint(_db_tree(tmp_path / "edited", b"SELECT 3;\nSELECT 5;\n"))
    assert lf == crlf
    assert edited != lf


def test_a_frozen_template_from_other_files_is_not_reused(harness: Harness) -> None:
    name = f"probe_template_{secrets.token_hex(4)}"
    with psycopg.connect(harness.admin_url, autocommit=True, row_factory=dict_row) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        try:

            def stamp(note: str | None, frozen: bool) -> bool:
                admin.execute(
                    sql.SQL("COMMENT ON DATABASE {} IS {}").format(
                        sql.Identifier(name), sql.Literal(note)
                    )
                )
                admin.execute(
                    "UPDATE pg_database SET datallowconn = %s WHERE datname = %s",
                    (not frozen, name),
                )
                return harness.template_is_ready(name)

            assert stamp(_template_note(harness.fingerprint), frozen=True)
            assert not stamp(_template_note("0" * 64), frozen=True)
            assert not stamp(None, frozen=True)
            assert not stamp(_template_note(harness.fingerprint), frozen=False)
        finally:
            admin.execute("UPDATE pg_database SET datallowconn = true WHERE datname = %s", (name,))
            admin.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(name)))


def test_a_running_session_blocks_a_rebuild(harness: Harness) -> None:
    with psycopg.connect(harness.admin_url, autocommit=True, row_factory=dict_row) as other:
        exclusive = other.execute(
            "SELECT pg_try_advisory_lock(hashtext(%s)) AS ok", (TEMPLATE_USE_LOCK,)
        ).fetchone()
        shared = other.execute(
            "SELECT pg_try_advisory_lock_shared(hashtext(%s)) AS ok", (TEMPLATE_USE_LOCK,)
        ).fetchone()
    assert exclusive is not None and exclusive["ok"] is False
    assert shared is not None and shared["ok"] is True
