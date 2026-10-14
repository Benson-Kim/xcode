"""The migration runner (``docs/03-database.md`` section 7).

A single ``xcode_owner`` connection holds a session advisory lock for the whole run.
Migrations are versioned and applied once each in their own transaction; routine files are
repeatable and applied together in one transaction, after which every ``api.*`` routine is
re-owned, stripped of ``PUBLIC`` execute and granted to its caller by name; an ``api.*``
function no file re-created in that transaction (a removed routine, or the old overload of a
changed signature) keeps no caller grant and is reported. Routines are
written against the complete schema: they are applied only when no migration is pending, and
``down`` drops them before reversing a migration (the next ``migrate`` applies them again).
The only DDL in Python is the ``CREATE TABLE IF NOT EXISTS`` for the two bookkeeping tables
and the ``DROP`` of routine functions before a ``down``; everything else is a file on disk.
"""

from __future__ import annotations

import hashlib
import os
import re
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psycopg
import structlog
from psycopg.rows import dict_row

logger = structlog.get_logger("xcode_api.db.migrate")

ADVISORY_LOCK_SQL = "SELECT pg_advisory_lock(hashtext('xcode.migrate'))"
ADVISORY_UNLOCK_SQL = "SELECT pg_advisory_unlock(hashtext('xcode.migrate'))"

_SCHEMA_MIGRATIONS_DDL = """
CREATE TABLE IF NOT EXISTS ops.schema_migrations (
  version integer PRIMARY KEY,
  name text NOT NULL,
  checksum text NOT NULL,
  applied_at timestamptz NOT NULL DEFAULT now(),
  applied_by text NOT NULL,
  duration_ms integer NOT NULL
)
"""

_ROUTINE_VERSIONS_DDL = """
CREATE TABLE IF NOT EXISTS ops.routine_versions (
  path text PRIMARY KEY,
  checksum text NOT NULL,
  applied_at timestamptz NOT NULL DEFAULT now()
)
"""


class MigrationError(RuntimeError):
    """A refusal by the runner (checksum drift, missing file, bad down target, a database
    whose roles and schemas were never set up)."""


REQUIRED_SCHEMAS = (
    "identity",
    "tenancy",
    "setup",
    "revenue",
    "pettycash",
    "expenses",
    "reports",
    "ops",
    "api",
)

_ROUTINE_NAME = re.compile(
    r"CREATE\s+OR\s+REPLACE\s+(?:FUNCTION|PROCEDURE)\s+([a-z_]+)\.([a-z_][a-z0-9_]*)\s*\(",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class MigrationFile:
    version: int
    name: str
    path: Path
    checksum: str


@dataclass(frozen=True, slots=True)
class RoutineFile:
    rel_path: str
    path: Path
    checksum: str


def checksum_bytes(data: bytes) -> str:
    """SHA-256 over file bytes with CRLF normalised to LF (Windows/Linux agree)."""
    normalised = data.replace(b"\r\n", b"\n")
    return hashlib.sha256(normalised).hexdigest()


def _checksum_file(path: Path) -> str:
    return checksum_bytes(path.read_bytes())


def find_db_dir() -> Path:
    """Locate the ``db/`` directory (migrations, routines, roles).

    ``XCODE_DB_DIR`` overrides; otherwise the first ``db`` directory found walking up from
    the current working directory, then alongside the installed package's project root.
    """
    override = os.environ.get("XCODE_DB_DIR")
    if override:
        return Path(override)
    cwd = Path.cwd()
    for base in (cwd, *cwd.parents):
        candidate = base / "db"
        if (candidate / "migrations").is_dir() and (candidate / "routines").is_dir():
            return candidate
    # Installed layout: the package lives under <root>/src/xcode_api; db/ is at <root>/db.
    root = Path(__file__).resolve().parents[3]
    candidate = root / "db"
    if candidate.is_dir():
        return candidate
    raise MigrationError("could not locate the db/ directory (set XCODE_DB_DIR)")


def discover_migrations(db_dir: Path) -> list[MigrationFile]:
    files: list[MigrationFile] = []
    for path in sorted((db_dir / "migrations").glob("*.sql")):
        if path.name.endswith(".down.sql"):
            continue
        stem = path.name[: -len(".sql")]
        version_text, _, name = stem.partition("_")
        try:
            version = int(version_text)
        except ValueError as exc:
            raise MigrationError(f"migration file name is not NNNN_name.sql: {path.name}") from exc
        files.append(
            MigrationFile(version=version, name=name, path=path, checksum=_checksum_file(path))
        )
    files.sort(key=lambda m: m.version)
    _check_strictly_increasing(files)
    return files


def _check_strictly_increasing(files: list[MigrationFile]) -> None:
    seen: set[int] = set()
    for f in files:
        if f.version in seen:
            raise MigrationError(f"duplicate migration version {f.version:04d}")
        seen.add(f.version)


def discover_routines(db_dir: Path) -> list[RoutineFile]:
    routines_dir = db_dir / "routines"
    files: list[RoutineFile] = []
    for path in routines_dir.rglob("*.sql"):
        rel = path.relative_to(routines_dir).as_posix()
        files.append(RoutineFile(rel_path=rel, path=path, checksum=_checksum_file(path)))
    files.sort(key=lambda r: r.rel_path)
    return files


class Runner:
    """Drives the runner commands over one owner connection holding the advisory lock."""

    def __init__(self, conn: psycopg.Connection[dict[str, Any]], *, operator: str, db_dir: Path):
        self._conn = conn
        self._operator = operator
        self._db_dir = db_dir

    @property
    def connection(self) -> psycopg.Connection[dict[str, Any]]:
        return self._conn

    # --- entry points ----------------------------------------------------------------

    def migrate(self, *, to: int | None = None, dry_run: bool = False) -> list[int]:
        self._ensure_bookkeeping()
        migrations = discover_migrations(self._db_dir)
        self._verify_no_drift(migrations)
        applied = self._applied_versions()
        pending = [m for m in migrations if m.version not in applied]
        if to is not None:
            pending = [m for m in pending if m.version <= to]
        if dry_run:
            for m in pending:
                logger.info("db.migrate.pending", version=m.version, name=m.name)
            return [m.version for m in pending]
        done: list[int] = []
        for m in pending:
            self._apply_migration(m)
            done.append(m.version)
        self._record_action("migrate", target=_versions_target(done))
        still_pending = self._pending_versions(migrations)
        if still_pending:
            logger.info("db.routines.deferred", pending=_versions_target(still_pending))
        else:
            self.routines(dry_run=False, record=False)
        return done

    def routines(self, *, dry_run: bool = False, record: bool = True) -> list[str]:
        self._ensure_bookkeeping()
        routines = discover_routines(self._db_dir)
        if dry_run:
            for r in routines:
                logger.info("db.routines.pending", path=r.rel_path)
            return [r.rel_path for r in routines]
        pending = self._pending_versions(discover_migrations(self._db_dir))
        if pending:
            raise MigrationError(
                f"migrations {_versions_target(pending)} are pending; routines need the complete "
                "schema, run db migrate"
            )
        with self._conn.transaction():
            for r in routines:
                started = time.perf_counter()
                self._conn.execute(r.path.read_text(encoding="utf-8"))
                duration_ms = (time.perf_counter() - started) * 1000
                logger.info(
                    "db.routines.applied", path=r.rel_path, duration_ms=round(duration_ms, 3)
                )
            orphans = self._fix_api_routine_grants()
            self._upsert_routine_versions(routines)
            self._delete_missing_routine_rows(routines)
        for routine in orphans:
            logger.warning("db.routines.orphan", routine=routine)
        if record:
            self._record_action("routines", target=f"{len(routines)} files")
        return [r.rel_path for r in routines]

    def down(self, version: int, *, confirmed: bool, env: str) -> None:
        self._ensure_bookkeeping()
        applied = self._applied_versions()
        if not applied:
            raise MigrationError("no migrations are applied")
        latest = max(applied)
        if version != latest:
            raise MigrationError(
                f"db down reverses only the latest applied version "
                f"({latest:04d}), not {version:04d}"
            )
        destructive_env = env not in ("development", "testing")
        if destructive_env and not confirmed:
            raise MigrationError(
                "db down is refused outside development/testing without --i-know-this-destroys-data"
            )
        migrations = {m.version: m for m in discover_migrations(self._db_dir)}
        migration = migrations.get(version)
        if migration is None:
            raise MigrationError(f"no migration file for version {version:04d}")
        down_path = migration.path.with_name(f"{migration.path.name[:-4]}.down.sql")
        if not down_path.is_file():
            raise MigrationError(f"no down file: {down_path.name}")
        if confirmed and destructive_env:
            logger.warning("db.down.destructive", version=version, operator=self._operator, env=env)
        with self._conn.transaction():
            # Routines depend on the tables a down file drops (row types in signatures); they
            # are removed with it and come back with the next migrate.
            dropped = self._drop_routines(discover_routines(self._db_dir))
            self._conn.execute(down_path.read_text(encoding="utf-8"))
            self._conn.execute("DELETE FROM ops.schema_migrations WHERE version = %s", (version,))
        logger.info("db.routines.dropped", count=dropped)
        self._record_action("down", target=f"{version:04d}")

    def status(self) -> dict[str, object]:
        self._ensure_bookkeeping()
        migrations = discover_migrations(self._db_dir)
        applied = self._applied_versions()
        pending = [m.version for m in migrations if m.version not in applied]
        drift = self._routine_drift(discover_routines(self._db_dir))
        checksum_drift = self._migration_checksum_drift(migrations)
        return {
            "applied": sorted(applied),
            "pending": pending,
            "routine_drift": drift,
            "migration_checksum_drift": checksum_drift,
        }

    # --- helpers ----------------------------------------------------------------------

    def _ensure_bookkeeping(self) -> None:
        self._require_schemas()
        with self._conn.transaction():
            self._conn.execute(_SCHEMA_MIGRATIONS_DDL)
            self._conn.execute(_ROUTINE_VERSIONS_DDL)

    def _require_schemas(self) -> None:
        """The roles files (schemas, grants) are a DBA step the runner never performs; a
        database without them gets one clear refusal instead of a failing DDL."""
        cur = self._conn.execute(
            "SELECT nspname FROM pg_catalog.pg_namespace WHERE nspname = ANY(%s)",
            (list(REQUIRED_SCHEMAS),),
        )
        present = {str(r["nspname"]) for r in cur.fetchall()}
        missing = [name for name in REQUIRED_SCHEMAS if name not in present]
        if missing:
            raise MigrationError(
                "schema(s) missing: " + ", ".join(missing) + "; apply db/roles/020_schemas.sql "
                "and db/roles/030_grants.sql to this database first (docs/03-database.md "
                "section 7)"
            )

    def _pending_versions(self, migrations: list[MigrationFile]) -> list[int]:
        applied = self._applied_versions()
        return [m.version for m in migrations if m.version not in applied]

    def _drop_routines(self, routines: list[RoutineFile]) -> int:
        names = sorted(
            {
                (schema.lower(), name.lower())
                for r in routines
                for schema, name in _ROUTINE_NAME.findall(r.path.read_text(encoding="utf-8"))
            }
        )
        dropped = 0
        for schema, name in names:
            cur = self._conn.execute(
                """
                SELECT pg_catalog.pg_get_function_identity_arguments(p.oid) AS args,
                       p.prokind AS kind
                FROM pg_catalog.pg_proc p
                JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
                WHERE n.nspname = %s AND p.proname = %s
                """,
                (schema, name),
            )
            for r in cur.fetchall():
                keyword = "PROCEDURE" if str(r["kind"]) == "p" else "FUNCTION"
                qualified = f"{_quote_ident(schema)}.{_quote_ident(name)}({r['args']})"
                self._conn.execute(f"DROP {keyword} {qualified}")
                dropped += 1
        self._conn.execute("DELETE FROM ops.routine_versions")
        return dropped

    def _applied_versions(self) -> set[int]:
        cur = self._conn.execute("SELECT version FROM ops.schema_migrations")
        return {int(r["version"]) for r in cur.fetchall()}

    def _verify_no_drift(self, migrations: list[MigrationFile]) -> None:
        by_version = {m.version: m for m in migrations}
        cur = self._conn.execute("SELECT version, name, checksum FROM ops.schema_migrations")
        for r in cur.fetchall():
            version = int(r["version"])
            recorded = str(r["checksum"])
            if version not in by_version:
                raise MigrationError(
                    f"migration {version:04d} ({r['name']}) is recorded but its file is gone"
                )
            if by_version[version].checksum != recorded:
                raise MigrationError(
                    f"migration {version:04d} ({by_version[version].name}) changed after it was "
                    "applied; add a new migration instead of editing it"
                )

    def _migration_checksum_drift(self, migrations: list[MigrationFile]) -> list[int]:
        by_version = {m.version: m for m in migrations}
        drift: list[int] = []
        cur = self._conn.execute("SELECT version, checksum FROM ops.schema_migrations")
        for r in cur.fetchall():
            version = int(r["version"])
            if version in by_version and by_version[version].checksum != str(r["checksum"]):
                drift.append(version)
        return sorted(drift)

    def _apply_migration(self, migration: MigrationFile) -> None:
        started = time.perf_counter()
        with self._conn.transaction():
            self._conn.execute(migration.path.read_text(encoding="utf-8"))
            duration_ms = int((time.perf_counter() - started) * 1000)
            self._conn.execute(
                "INSERT INTO ops.schema_migrations "
                "(version, name, checksum, applied_at, applied_by, duration_ms) "
                "VALUES (%s, %s, %s, now(), %s, %s)",
                (
                    migration.version,
                    migration.name,
                    migration.checksum,
                    self._operator,
                    duration_ms,
                ),
            )
        logger.info(
            "db.migrate.applied",
            version=migration.version,
            name=migration.name,
            duration_ms=duration_ms,
        )

    def _fix_api_routine_grants(self) -> list[str]:
        """Re-own every ``api`` routine and grant it to its caller by name, except the ones
        no file re-created in this transaction: CREATE OR REPLACE rewrites the catalogue row,
        so an untouched row is a routine without a file. Those lose every caller grant and are
        returned for the orphan warning."""
        cur = self._conn.execute(
            """
            SELECT p.oid,
                   p.proname AS name,
                   pg_catalog.pg_get_function_identity_arguments(p.oid) AS args,
                   p.prokind AS kind,
                   p.xmin = pg_catalog.pg_current_xact_id()::xid AS from_file
            FROM pg_catalog.pg_proc p
            JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
            WHERE n.nspname = 'api'
            ORDER BY p.proname, args
            """
        )
        orphans: list[str] = []
        for r in cur.fetchall():
            name = str(r["name"])
            args = str(r["args"])
            kind = str(r["kind"])
            keyword = "PROCEDURE" if kind == "p" else "FUNCTION"
            qualified = f"api.{_quote_ident(name)}({args})"
            self._conn.execute(f"ALTER {keyword} {qualified} OWNER TO xcode_api_executor")
            self._conn.execute(f"REVOKE ALL ON {keyword} {qualified} FROM PUBLIC")
            if not r["from_file"]:
                self._conn.execute(
                    f"REVOKE EXECUTE ON {keyword} {qualified} FROM xcode_app, xcode_operator"
                )
                orphans.append(f"api.{name}({args})")
                continue
            for grantee in _callers_for(name):
                self._conn.execute(f"GRANT EXECUTE ON {keyword} {qualified} TO {grantee}")
        return orphans

    def _upsert_routine_versions(self, routines: list[RoutineFile]) -> None:
        for r in routines:
            self._conn.execute(
                "INSERT INTO ops.routine_versions (path, checksum, applied_at) "
                "VALUES (%s, %s, now()) "
                "ON CONFLICT (path) DO UPDATE SET checksum = EXCLUDED.checksum, applied_at = now()",
                (r.rel_path, r.checksum),
            )

    def _delete_missing_routine_rows(self, routines: list[RoutineFile]) -> None:
        present = [r.rel_path for r in routines]
        self._conn.execute("DELETE FROM ops.routine_versions WHERE path <> ALL(%s)", (present,))

    def _routine_drift(self, routines: list[RoutineFile]) -> list[str]:
        by_path = {r.rel_path: r.checksum for r in routines}
        drift: list[str] = []
        cur = self._conn.execute("SELECT path, checksum FROM ops.routine_versions")
        for r in cur.fetchall():
            path = str(r["path"])
            if path not in by_path or by_path[path] != str(r["checksum"]):
                drift.append(path)
        return sorted(drift)

    def _record_action(self, action: str, *, target: str) -> None:
        # down of 0001 removes ops.operator_actions itself; there is then nowhere to record
        # the action, so a missing table is logged rather than raised.
        row = self._conn.execute("SELECT to_regclass('ops.operator_actions') AS t").fetchone()
        if row is None or row["t"] is None:
            logger.warning("db.action_not_recorded", action=action, target=target)
            return
        with self._conn.transaction():
            self._conn.execute(
                "INSERT INTO ops.operator_actions (operator, action, target, detail, recorded_at) "
                "VALUES (%s, %s, %s, '{}'::jsonb, now())",
                (self._operator, action, target),
            )


def _callers_for(name: str) -> list[str]:
    if name.startswith("ops_"):
        return ["xcode_operator"]
    if name.startswith("meta_"):
        return ["xcode_operator", "xcode_app"]
    return ["xcode_app"]


def _quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _versions_target(versions: list[int]) -> str:
    if not versions:
        return "nothing pending"
    return ", ".join(f"{v:04d}" for v in versions)


def open_owner_connection(url: str) -> psycopg.Connection[dict[str, Any]]:
    """Connect as the migration role; a connection failure is a :class:`MigrationError`
    so callers outside ``db/`` never handle psycopg errors themselves."""
    try:
        return psycopg.connect(url, autocommit=True, row_factory=dict_row)
    except psycopg.OperationalError as exc:
        raise MigrationError(
            f"cannot connect with XCODE_MIGRATION_DATABASE_URL: {str(exc).strip()}"
        ) from exc


@contextmanager
def advisory_lock(conn: psycopg.Connection[dict[str, Any]]) -> Iterator[None]:
    """Hold the session-level migration advisory lock for the whole run, released at the end."""
    conn.execute(ADVISORY_LOCK_SQL)
    try:
        yield
    finally:
        try:
            conn.execute(ADVISORY_UNLOCK_SQL)
        except psycopg.Error:  # pragma: no cover - the server releases it on disconnect anyway
            pass
