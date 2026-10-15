"""PostgreSQL targets for the tool's tests, built the way the API's harness builds its own.

A template database gets the role files of ``db/roles`` and ``xcode-api db migrate`` (run as a
subprocess: the tool never imports the API package); each test clones it. The template carries
a fingerprint of the ``db/`` files in its comment and is rebuilt when they change. The server
comes from ``XCODE_TEST_DATABASE_URL`` (a role with CREATEDB and CREATEROLE), the CLI from
``XCODE_API_CLI`` or ``PATH``; without either, every database test is skipped with the reason.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import psycopg
import pytest
from psycopg import sql

DB_DIR = Path(os.environ.get("XCODE_DB_DIR") or Path(__file__).resolve().parents[3] / "db")
TEMPLATE = os.environ.get("XCODE_MIGRATION_TEST_TEMPLATE") or "xcode_migration_template"
if not re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", TEMPLATE):
    raise RuntimeError(f"XCODE_MIGRATION_TEST_TEMPLATE must be a lower-case identifier: {TEMPLATE}")
BUILD_LOCK = f"xcode.migration.test.template:{TEMPLATE}"
SERVER_ROLE_FILES = ("010_roles.sql", "900_local_dev.sql")
DATABASE_ROLE_FILES = ("020_schemas.sql", "030_grants.sql")


def role_url(admin: str, role: str, database: str) -> str:
    parts = urlsplit(admin)
    host = parts.hostname or "localhost"
    port = f":{parts.port}" if parts.port else ""
    return urlunsplit(
        (parts.scheme, f"{role}:{role}@{host}{port}", f"/{database}", parts.query, "")
    )


def admin_on(admin: str, database: str) -> str:
    parts = urlsplit(admin)
    return urlunsplit((parts.scheme, parts.netloc, f"/{database}", parts.query, ""))


def fingerprint() -> str:
    digest = hashlib.sha256()
    for path in sorted(
        p for part in ("roles", "migrations", "routines") for p in (DB_DIR / part).rglob("*.sql")
    ):
        digest.update(path.relative_to(DB_DIR).as_posix().encode() + b"\0")
        digest.update(path.read_bytes().replace(b"\r\n", b"\n") + b"\0")
    return digest.hexdigest()


def cli_env(owner_url: str, **extra: str) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("XCODE_")}
    env.update(
        XCODE_ENV="testing",
        XCODE_MIGRATION_DATABASE_URL=owner_url,
        XCODE_OPERATOR="migration-tests",
        XCODE_DB_DIR=str(DB_DIR),
        **extra,
    )
    cli = os.environ.get("XCODE_API_CLI")
    if cli:
        env["XCODE_API_CLI"] = cli
    return env


def find_cli() -> str | None:
    return os.environ.get("XCODE_API_CLI") or shutil.which("xcode-api")


def run_cli(cli: str, args: list[str], owner_url: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [cli, *args],
        env=cli_env(owner_url),
        capture_output=True,
        text=True,
        timeout=900,
        check=False,
        cwd=DB_DIR.parent,
    )


@dataclass(frozen=True, slots=True)
class Server:
    admin: str
    cli: str

    def apply(self, url: str, names: tuple[str, ...]) -> None:
        with psycopg.connect(url, autocommit=True) as conn:
            for name in names:
                conn.execute((DB_DIR / "roles" / name).read_text(encoding="utf-8"))  # type: ignore[arg-type]

    def ready(self, note: str) -> bool:
        with psycopg.connect(self.admin, autocommit=True) as conn:
            row = conn.execute(
                "SELECT datallowconn, shobj_description(oid, 'pg_database') FROM pg_database "
                "WHERE datname = %s",
                (TEMPLATE,),
            ).fetchone()
        return row is not None and row[0] is False and row[1] == note

    def build_template(self) -> None:
        note = f"xcode migration-tool template {fingerprint()}"
        with psycopg.connect(self.admin, autocommit=True) as lock:
            lock.execute("SELECT pg_advisory_lock(hashtext(%s))", (BUILD_LOCK,))
            try:
                if self.ready(note):
                    return
                self.apply(self.admin, SERVER_ROLE_FILES)
                name = sql.Identifier(TEMPLATE)
                lock.execute(
                    "UPDATE pg_database SET datallowconn = true WHERE datname = %s", (TEMPLATE,)
                )
                lock.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(name))
                lock.execute(sql.SQL("CREATE DATABASE {} OWNER xcode_owner").format(name))
                owner = role_url(self.admin, "xcode_owner", TEMPLATE)
                self.apply(owner, DATABASE_ROLE_FILES)
                done = run_cli(self.cli, ["db", "migrate"], owner)
                if done.returncode != 0:
                    raise RuntimeError(
                        f"xcode-api db migrate failed:\n{done.stdout}\n{done.stderr}"
                    )
                lock.execute(
                    sql.SQL("COMMENT ON DATABASE {} IS {}").format(name, sql.Literal(note))
                )
                lock.execute(
                    "UPDATE pg_database SET datallowconn = false WHERE datname = %s", (TEMPLATE,)
                )
            finally:
                lock.execute("SELECT pg_advisory_unlock(hashtext(%s))", (BUILD_LOCK,))


@dataclass(frozen=True, slots=True)
class Target:
    server: Server
    name: str

    @property
    def owner_url(self) -> str:
        return role_url(self.server.admin, "xcode_owner", self.name)

    @property
    def app_url(self) -> str:
        return role_url(self.server.admin, "xcode_app", self.name)

    def owner(self) -> psycopg.Connection[tuple[object, ...]]:
        conn = psycopg.connect(self.owner_url, autocommit=True)
        conn.execute("SET TimeZone = 'UTC'")
        return conn

    def scalar(self, query: str, params: tuple[object, ...] = ()) -> object:
        with self.owner() as conn:
            row = conn.execute(query, params).fetchone()  # type: ignore[arg-type]
        return None if row is None else row[0]


@pytest.fixture(scope="session")
def server() -> Server:
    admin = os.environ.get("XCODE_TEST_DATABASE_URL")
    if not admin:
        pytest.skip("XCODE_TEST_DATABASE_URL is not set: no PostgreSQL server for the target")
    cli = find_cli()
    if cli is None:
        pytest.skip(
            "xcode-api is not installed (pip install -e apps/api-python) "
            "and XCODE_API_CLI is not set"
        )
    result = Server(admin, cli)
    result.build_template()
    return result


@pytest.fixture
def target(server: Server, monkeypatch: pytest.MonkeyPatch) -> Iterator[Target]:
    name = f"mig10_{uuid.uuid4().hex[:12]}"
    with psycopg.connect(server.admin, autocommit=True) as conn:
        conn.execute(
            sql.SQL("CREATE DATABASE {} TEMPLATE {} OWNER xcode_owner").format(
                sql.Identifier(name), sql.Identifier(TEMPLATE)
            )
        )
    made = Target(server, name)
    for key, value in cli_env(made.owner_url).items():
        if key.startswith("XCODE_"):
            monkeypatch.setenv(key, value)
    monkeypatch.setenv("XCODE_API_CLI", server.cli)
    try:
        yield made
    finally:
        with psycopg.connect(server.admin, autocommit=True) as conn:
            conn.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name))
            )
