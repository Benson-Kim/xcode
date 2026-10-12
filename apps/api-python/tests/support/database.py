"""PostgreSQL test harness: a template database built once, cloned per test.

The session fixtures live here and are re-exported by ``tests/conftest.py``. A database is
reached through ``XCODE_TEST_DATABASE_URL`` (a superuser or a role with CREATEDB and
CREATEROLE) when set, otherwise a throwaway ``testcontainers`` ``postgres:18``. When neither
is available the session fixture skips every database test (``docs/09-testing.md`` section 2).

The template carries a fingerprint of the ``db/`` files and the runner in its comment and is
rebuilt when they change. Every session holds a shared advisory lock while it clones; a
rebuild needs that lock exclusively, so a stale template is never dropped under another
session's run: the new session fails with a message instead of testing old routines.
"""

from __future__ import annotations

import hashlib
import os
import re
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import psycopg
import pytest
from psycopg import sql
from psycopg.rows import dict_row

from xcode_api.db import migrate
from xcode_api.db.migrate import Runner, advisory_lock, checksum_bytes, find_db_dir

# XCODE_TEST_TEMPLATE gives a session its own template, for example to test changed routines
# while another session's run still clones the shared one.
TEMPLATE_DB = os.environ.get("XCODE_TEST_TEMPLATE") or "xcode_template"
if not re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", TEMPLATE_DB):
    raise RuntimeError(f"XCODE_TEST_TEMPLATE must be a lower-case identifier: {TEMPLATE_DB!r}")
TEMPLATE_BUILD_LOCK = f"xcode.test.template:{TEMPLATE_DB}"
TEMPLATE_USE_LOCK = f"xcode.test.template.use:{TEMPLATE_DB}"

ROLE_FILES = ("010_roles.sql", "020_schemas.sql", "030_grants.sql", "900_local_dev.sql")
# Files that must be applied inside the target database (schemas, grants, dev passwords are
# database-local or role-local); 010 creates global roles and may run anywhere.
SERVER_ROLE_FILES = ("010_roles.sql", "900_local_dev.sql")
DATABASE_ROLE_FILES = ("020_schemas.sql", "030_grants.sql")


@dataclass(frozen=True, slots=True)
class AdminConnection:
    """How the harness reaches the server with CREATE DATABASE / CREATE ROLE rights."""

    url: str


def _admin_url() -> str | None:
    return os.environ.get("XCODE_TEST_DATABASE_URL")


def _with_dbname(url: str, dbname: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, f"/{dbname}", parts.query, parts.fragment))


def _with_role(url: str, user: str, password: str, dbname: str) -> str:
    parts = urlsplit(url)
    host = parts.hostname or "localhost"
    port = f":{parts.port}" if parts.port else ""
    query = f"?{parts.query}" if parts.query else ""
    return f"{parts.scheme}://{user}:{password}@{host}{port}/{dbname}{query}"


def _read_role_files(db_dir: Path, names: tuple[str, ...]) -> list[str]:
    roles_dir = db_dir / "roles"
    return [(roles_dir / name).read_text(encoding="utf-8") for name in names]


def template_fingerprint(db_dir: Path) -> str:
    """SHA-256 over every SQL file the template is built from and the runner that builds it."""
    digest = hashlib.sha256()
    sources = sorted(
        path
        for part in ("roles", "migrations", "routines")
        for path in (db_dir / part).rglob("*.sql")
    )
    for path in [*sources, Path(migrate.__file__)]:
        name = path.relative_to(db_dir).as_posix() if path.is_relative_to(db_dir) else path.name
        digest.update(f"{name}\0{checksum_bytes(path.read_bytes())}\0".encode())
    return digest.hexdigest()


def _template_note(fingerprint: str) -> str:
    return f"xcode test template {fingerprint}"


def try_exclusive_lock(conn: psycopg.Connection[dict[str, Any]], key: str) -> bool:
    row = conn.execute("SELECT pg_try_advisory_lock(hashtext(%s)) AS ok", (key,)).fetchone()
    return bool(row and row["ok"])


def _apply(url: str, statements: list[str]) -> None:
    with psycopg.connect(url, autocommit=True, row_factory=dict_row) as conn:
        for sql in statements:
            conn.execute(sql)  # type: ignore[arg-type]


@dataclass(frozen=True, slots=True)
class Harness:
    admin_url: str
    db_dir: Path
    fingerprint: str = ""

    def admin_db_url(self) -> str:
        return self.admin_url

    def template_owner_url(self) -> str:
        return _with_role(self.admin_url, "xcode_owner", "xcode_owner", TEMPLATE_DB)

    def build_template(self) -> None:
        # Serialise template creation across pytest-xdist workers: each is its own process
        # with its own session fixture, so without this lock they race on DROP/CREATE.
        with psycopg.connect(self.admin_url, autocommit=True, row_factory=dict_row) as lock_conn:
            lock_conn.execute("SELECT pg_advisory_lock(hashtext(%s))", (TEMPLATE_BUILD_LOCK,))
            try:
                if self.template_is_ready():
                    return
                if not try_exclusive_lock(lock_conn, TEMPLATE_USE_LOCK):
                    raise RuntimeError(
                        f"{TEMPLATE_DB} was built from other db/ files and another test session "
                        "is cloning it; rerun when that session ends"
                    )
                try:
                    self._build_template_locked()
                finally:
                    lock_conn.execute(
                        "SELECT pg_advisory_unlock(hashtext(%s))", (TEMPLATE_USE_LOCK,)
                    )
            finally:
                lock_conn.execute("SELECT pg_advisory_unlock(hashtext(%s))", (TEMPLATE_BUILD_LOCK,))

    def template_is_ready(self, name: str = TEMPLATE_DB) -> bool:
        """Frozen (``datallowconn = false``, so a worker finished building it) and built from
        the current files."""
        with psycopg.connect(self.admin_url, autocommit=True, row_factory=dict_row) as conn:
            row = conn.execute(
                "SELECT datallowconn, pg_catalog.shobj_description(oid, 'pg_database') AS note "
                "FROM pg_database WHERE datname = %s",
                (name,),
            ).fetchone()
        return (
            row is not None
            and row["datallowconn"] is False
            and row["note"] == _template_note(self.fingerprint)
        )

    def _build_template_locked(self) -> None:
        # 010 (roles) and 900 (dev passwords) are global; apply them on the admin database.
        _apply(self.admin_url, _read_role_files(self.db_dir, SERVER_ROLE_FILES))
        # Recreate the template database as a clean slate.
        with psycopg.connect(self.admin_url, autocommit=True, row_factory=dict_row) as conn:
            _set_allowconn(conn, TEMPLATE_DB, True)
            _terminate(conn, TEMPLATE_DB)
            conn.execute(f"DROP DATABASE IF EXISTS {TEMPLATE_DB}")
            conn.execute(f"CREATE DATABASE {TEMPLATE_DB} OWNER xcode_owner")
        # Schemas and grants are database-local: apply them inside the template.
        owner_url = self.template_owner_url()
        _apply(owner_url, _read_role_files(self.db_dir, DATABASE_ROLE_FILES))
        # Migrate and load routines into the template as the owner.
        conn = psycopg.connect(owner_url, autocommit=True, row_factory=dict_row)
        try:
            with advisory_lock(conn):
                Runner(conn, operator="test-harness", db_dir=self.db_dir).migrate()
        finally:
            conn.close()
        # Freeze the template so nothing connects to it (TEMPLATE clones need zero sessions).
        with psycopg.connect(self.admin_url, autocommit=True, row_factory=dict_row) as conn:
            conn.execute(
                sql.SQL("COMMENT ON DATABASE {} IS {}").format(
                    sql.Identifier(TEMPLATE_DB), sql.Literal(_template_note(self.fingerprint))
                )
            )
            _set_allowconn(conn, TEMPLATE_DB, False)

    def create_test_database(self, name: str) -> tuple[str, str]:
        # The template stays frozen (datallowconn = false): that is exactly what guarantees
        # no session is connected to it, which CREATE DATABASE ... TEMPLATE requires.
        with psycopg.connect(self.admin_url, autocommit=True, row_factory=dict_row) as conn:
            conn.execute(f"CREATE DATABASE {name} TEMPLATE {TEMPLATE_DB} OWNER xcode_owner")
        app_url = _with_role(self.admin_url, "xcode_app", "xcode_app", name)
        owner_url = _with_role(self.admin_url, "xcode_owner", "xcode_owner", name)
        return app_url, owner_url

    def create_schema_only_database(self, name: str) -> str:
        """A database with roles, schemas and grants but no migrations applied, for runner
        tests that need a fresh slate. Returns the owner URL."""
        with psycopg.connect(self.admin_url, autocommit=True, row_factory=dict_row) as conn:
            conn.execute(f"CREATE DATABASE {name} OWNER xcode_owner")
        owner_url = _with_role(self.admin_url, "xcode_owner", "xcode_owner", name)
        _apply(owner_url, _read_role_files(self.db_dir, DATABASE_ROLE_FILES))
        return owner_url

    def drop_test_database(self, name: str) -> None:
        with psycopg.connect(self.admin_url, autocommit=True, row_factory=dict_row) as conn:
            _terminate(conn, name)
            conn.execute(f"DROP DATABASE IF EXISTS {name}")


@contextmanager
def executor_connection(owner_url: str) -> Iterator[psycopg.Connection[dict[str, Any]]]:
    """An owner connection switched to ``xcode_api_executor`` (the owner is a member), so
    statements run with the executor's privileges and under its row-level security, exactly
    as a routine body does. Callers set ``xcode.organization_id`` themselves."""
    conn = psycopg.connect(owner_url, autocommit=True, row_factory=dict_row)
    try:
        conn.execute("SET ROLE xcode_api_executor")
        yield conn
    finally:
        conn.close()


def _set_allowconn(conn: psycopg.Connection[dict[str, object]], dbname: str, allow: bool) -> None:
    conn.execute("UPDATE pg_database SET datallowconn = %s WHERE datname = %s", (allow, dbname))


def _terminate(conn: psycopg.Connection[dict[str, object]], dbname: str) -> None:
    conn.execute(
        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
        "WHERE datname = %s AND pid <> pg_backend_pid()",
        (dbname,),
    )


def start_harness() -> Iterator[Harness]:
    """Yield a ready :class:`Harness`, or skip the session when no database is reachable."""
    db_dir = find_db_dir()
    admin_url = _admin_url()
    container = None
    if admin_url is None:
        admin_url, container = _start_testcontainer()
    if admin_url is None:
        pytest.skip(
            "no PostgreSQL available: set XCODE_TEST_DATABASE_URL or run a Docker daemon "
            "for testcontainers",
            allow_module_level=True,
        )
    harness = Harness(admin_url=admin_url, db_dir=db_dir, fingerprint=template_fingerprint(db_dir))
    harness.build_template()
    use_conn = psycopg.connect(admin_url, autocommit=True, row_factory=dict_row)
    try:
        use_conn.execute("SELECT pg_advisory_lock_shared(hashtext(%s))", (TEMPLATE_USE_LOCK,))
        yield harness
    finally:
        use_conn.close()
        if container is not None:
            container.stop()


def _start_testcontainer() -> tuple[str | None, object | None]:
    try:
        from testcontainers.community.postgres import PostgresContainer
    except ImportError:  # pragma: no cover - older testcontainers layout
        try:
            from testcontainers.postgres import PostgresContainer
        except ImportError:
            return None, None
    try:
        container = PostgresContainer("postgres:18", driver=None)
        container.start()
    except Exception:  # pragma: no cover - no Docker daemon
        return None, None
    url = container.get_connection_url()
    # testcontainers returns a SQLAlchemy-style URL; normalise to libpq.
    url = url.replace("postgresql+psycopg2://", "postgresql://").replace(
        "postgresql+psycopg://", "postgresql://"
    )
    return url, container
