"""``xcode-api db migrate|routines|status|verify|down``.

All connect as ``xcode_owner`` through ``XCODE_MIGRATION_DATABASE_URL`` and hold the
migration advisory lock for the whole run (``docs/03-database.md`` section 7). Only
``CliSettings`` is validated: a migration job needs the owner URL, the environment and the
operator name, never the API's own secrets.
"""

from __future__ import annotations

import argparse
import getpass

from ...db import migrate as runner
from ...db.verify import run_checks
from ...settings import CliSettings, SettingsError, load_cli_settings

NAME = "db"
HELP = "migration runner: migrate, routines, status, verify, down"


def configure(parser: argparse.ArgumentParser) -> None:
    sub = parser.add_subparsers(dest="db_command", required=True)

    p_migrate = sub.add_parser("migrate", help="apply pending migrations, then routines")
    p_migrate.add_argument("--to", type=int, default=None, help="apply up to this version")
    p_migrate.add_argument("--dry-run", action="store_true")

    p_routines = sub.add_parser("routines", help="apply routine files and fix ownership/grants")
    p_routines.add_argument("--dry-run", action="store_true")

    sub.add_parser("status", help="show applied, pending and drift")
    sub.add_parser("verify", help="run the structural assertions; exit 1 on any failure")

    p_down = sub.add_parser("down", help="reverse the latest applied migration")
    p_down.add_argument("version", type=int)
    p_down.add_argument("--i-know-this-destroys-data", action="store_true", dest="confirmed")


def resolve_operator(settings: CliSettings) -> str:
    if settings.operator:
        return settings.operator
    try:
        return getpass.getuser()
    except Exception:  # pragma: no cover - getuser may fail in a bare container
        return "unknown"


def run(args: argparse.Namespace) -> int:
    try:
        settings = load_cli_settings()
    except SettingsError as exc:
        for message in exc.messages:
            print(message)
        return 2

    if not settings.migration_database_url:
        print("XCODE_MIGRATION_DATABASE_URL is required for db commands")
        return 2

    operator = resolve_operator(settings)
    try:
        db_dir = runner.find_db_dir()
        conn = runner.open_owner_connection(settings.migration_database_url)
    except runner.MigrationError as exc:
        print(str(exc))
        return 1
    try:
        with runner.advisory_lock(conn):
            r = runner.Runner(conn, operator=operator, db_dir=db_dir)
            return _dispatch(args, r, settings)
    except runner.MigrationError as exc:
        print(str(exc))
        return 1
    finally:
        conn.close()


def _dispatch(args: argparse.Namespace, r: runner.Runner, settings: CliSettings) -> int:
    command = args.db_command
    if command == "migrate":
        applied = r.migrate(to=args.to, dry_run=args.dry_run)
        if args.dry_run:
            print(f"pending: {_fmt_versions(applied)}")
        else:
            print(f"applied: {_fmt_versions(applied)}")
        return 0
    if command == "routines":
        routine_paths = r.routines(dry_run=args.dry_run)
        verb = "would apply" if args.dry_run else "applied"
        print(f"{verb} {len(routine_paths)} routine files")
        return 0
    if command == "status":
        return _print_status(r)
    if command == "verify":
        return _run_verify(r)
    if command == "down":
        r.down(args.version, confirmed=args.confirmed, env=settings.env.value)
        print(f"reversed {args.version:04d}")
        return 0
    print(f"unknown db command: {command}")  # pragma: no cover
    return 2


def _print_status(r: runner.Runner) -> int:
    status = r.status()
    print(f"applied: {_fmt_versions(status['applied'])}")  # type: ignore[arg-type]
    print(f"pending: {_fmt_versions(status['pending'])}")  # type: ignore[arg-type]
    routine_drift = status["routine_drift"]
    migration_drift = status["migration_checksum_drift"]
    print(f"routine drift: {routine_drift or 'none'}")
    print(f"migration checksum drift: {migration_drift or 'none'}")
    clean = not status["pending"] and not routine_drift and not migration_drift
    return 0 if clean else 1


def _run_verify(r: runner.Runner) -> int:
    results = run_checks(r.connection)
    failed = False
    for result in results:
        if result.ok:
            print(f"ok    {result.name}")
        else:
            failed = True
            print(f"FAIL  {result.name}")
            for message in result.failures:
                print(f"        - {message}")
    return 1 if failed else 0


def _fmt_versions(versions: list[int]) -> str:
    if not versions:
        return "none"
    return ", ".join(f"{v:04d}" for v in versions)
