"""``python -m migrate_from_sqlserver extract | transform | load | report``.

Connection strings come only from the environment: ``XCODE_MIGRATION_SOURCE_URL`` (SQL
Server, for ``extract``), ``XCODE_MIGRATION_LEGACY_URL`` (the legacy PostgreSQL database, for
``extract --source legacy``) and ``XCODE_MIGRATION_DATABASE_URL`` (PostgreSQL as
``xcode_owner``, for ``transform`` and ``load``). Exit status 0 when the command did what it
says and every verification passed, 1 when it stopped or a verification failed, 2 for a usage
error.
"""

from __future__ import annotations

import argparse
import csv
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path

from . import __version__, legacy_extract
from . import extract as extract_command
from . import load as load_command
from . import report as report_command
from . import transform as transform_command
from .database import connect_target
from .legacy_tablemap import FLEET_MANAGER, OWNER
from .profile import LEGACY, SQLSERVER, Options, Person
from .records import ToolError

PEOPLE_HEADER = ["legacy_email", "email", "phone", "role"]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m migrate_from_sqlserver",
        description="Copy the .NET API's SQL Server data into the xcode PostgreSQL schema.",
    )
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_extract = sub.add_parser("extract", help="source tables to CSV files and manifest.json")
    p_extract.add_argument("--output", type=Path, required=True, help="a new, empty directory")
    p_extract.add_argument(
        "--source",
        choices=(SQLSERVER, LEGACY),
        default=SQLSERVER,
        help="the .NET API's SQL Server (default) or the legacy PostgreSQL database",
    )
    p_extract.add_argument(
        "--frozen",
        action="store_true",
        help="the .NET API is in maintenance (needed when the database has no SNAPSHOT isolation)",
    )

    p_transform = sub.add_parser("transform", help="validate the extract and write load files")
    p_transform.add_argument("--input", type=Path, required=True, help="the extract directory")
    p_transform.add_argument("--output", type=Path, required=True, help="the work directory")
    p_transform.add_argument("--fleet-numbers", type=Path, help="CSV: registration,fleet_number")
    _legacy_arguments(p_transform)

    p_load = sub.add_parser("load", help="load the files in one transaction and verify")
    mode = p_load.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="always roll back")
    mode.add_argument("--apply", action="store_true", help="commit when every check passes")
    p_load.add_argument(
        "--input",
        type=Path,
        required=True,
        help="a work directory, or an extract directory (transformed first)",
    )
    p_load.add_argument("--output", type=Path, help="work directory when --input is an extract")
    p_load.add_argument("--fleet-numbers", type=Path, help="CSV: registration,fleet_number")
    _legacy_arguments(p_load)
    p_load.add_argument(
        "--accept-rejected",
        type=int,
        default=None,
        metavar="N",
        help="load without the N refused rows the report lists (must equal their count)",
    )
    p_load.add_argument("--all", action="store_true", help="print every listed row")

    p_report = sub.add_parser("report", help="print the report of a work directory")
    p_report.add_argument("--input", type=Path, required=True, help="the work directory")
    p_report.add_argument("--all", action="store_true", help="print every listed row")
    return parser


def _legacy_arguments(parser: argparse.ArgumentParser) -> None:
    legacy = parser.add_argument_group("an extract of the legacy database (docs/10 7.2)")
    legacy.add_argument("--organization-name", help="the organization's name (My fleet)")
    legacy.add_argument("--organization-slug", help="the organization's slug (my-fleet)")
    legacy.add_argument(
        "--migrated-by",
        metavar="EMAIL",
        help="the Administrator who authors every value the source never stored",
    )
    legacy.add_argument(
        "--people",
        type=Path,
        help="CSV legacy_email,email,phone,role: one row per legacy user (never in the repository)",
    )


def _people(path: Path | None) -> dict[str, Person] | None:
    """The people file, keyed by the legacy e-mail folded to lower case. A problem names the
    line, never a value: the file holds personal details."""
    if path is None:
        return None
    people: dict[str, Person] = {}
    seen: dict[tuple[str, str], int] = {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != PEOPLE_HEADER:
            raise ToolError(f"{path}: the header must be {','.join(PEOPLE_HEADER)}")
        for line, row in enumerate(reader, start=2):
            legacy_email = (row.get("legacy_email") or "").strip().lower()
            email = (row.get("email") or "").strip()
            phone = (row.get("phone") or "").strip()
            role_text = (row.get("role") or "").strip()
            if not legacy_email or not email:
                raise ToolError(f"{path} line {line}: legacy_email and email are required")
            role = next((r for r in (OWNER, FLEET_MANAGER) if r.lower() == role_text.lower()), None)
            if role_text and role is None:
                raise ToolError(f"{path} line {line}: role must be Owner, Fleet manager or empty")
            for column, value in (
                ("legacy_email", legacy_email),
                ("email", email.lower()),
                ("phone", "".join(ch for ch in phone if ch.isdigit())[-9:]),
            ):
                if not value:
                    continue
                first = seen.setdefault((column, value), line)
                if first != line:
                    raise ToolError(f"{path} line {line}: {column} repeats line {first}")
            people[legacy_email] = Person(line, legacy_email, email, phone, role)
    return people


def _fleet_numbers(path: Path | None) -> dict[str, str] | None:
    if path is None:
        return None
    numbers: dict[str, str] = {}
    with path.open(encoding="utf-8", newline="") as handle:
        for line, row in enumerate(csv.DictReader(handle), start=2):
            registration = (row.get("registration") or "").strip()
            number = (row.get("fleet_number") or "").strip()
            if not registration or not number:
                raise ToolError(f"{path} line {line}: registration and fleet_number are required")
            if registration in numbers:
                raise ToolError(f"{path} line {line}: {registration} is listed twice")
            numbers[registration] = number
    return numbers


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return _run(args)
    except ToolError as exc:
        print(f"stopped: {exc}", file=sys.stderr)  # noqa: T201
        return 1


def _where(summary: dict[str, object]) -> str:
    source = summary.get("source")
    kind = source.get("kind") if isinstance(source, dict) else None
    return "the old application" if kind == LEGACY else "SQL Server"


def _options(args: argparse.Namespace) -> Options:
    return Options(
        fleet_numbers=_fleet_numbers(args.fleet_numbers),
        organization_name=args.organization_name,
        organization_slug=args.organization_slug,
        migrated_by=args.migrated_by,
        people=_people(args.people),
    )


def _run(args: argparse.Namespace) -> int:
    if args.command == "extract":
        if args.source == LEGACY:
            if args.frozen:
                raise ToolError("--frozen is for SQL Server; the legacy extract reads a copy")
            manifest = legacy_extract.run(args.output)
        else:
            manifest = extract_command.run(args.output, args.frozen)
        rows = sum(int(t.get("rows", 0)) for t in manifest["tables"].values())
        print(f"extracted {rows} rows into {args.output} at {manifest['extracted_at']}")  # noqa: T201
        return 0
    if args.command == "report":
        return report_command.run(args.input, everything=args.all)

    conn = connect_target()
    try:
        if args.command == "transform":
            summary = transform_command.run(args.input, args.output, conn, options=_options(args))
            print(  # noqa: T201
                f"transformed into {args.output}: {len(summary['rejected'])} refused, "
                f"{len(summary['dropped'])} dropped, {len(summary['changed'])} changed; "
                "run report, then load --dry-run"
            )
            if summary["deferred"] is not None:
                print(  # noqa: T201
                    f"stopped: the accepted rows break a deferred rule: "
                    f"{summary['deferred']['problem']}; run report for the refused rows "
                    f"behind it, fix them in {_where(summary)} and extract again",
                    file=sys.stderr,
                )
                return 1
            return 0
        work = args.input
        if not (work / transform_command.TRANSFORM).is_file():
            work = args.output or Path(tempfile.mkdtemp(prefix="xcode-migration-"))
            transform_command.run(args.input, work, conn, options=_options(args))
            print(f"transformed {args.input} into {work}")  # noqa: T201
        result = load_command.run(work, conn, args.apply, args.accept_rejected)
    finally:
        conn.close()
    report_command.run(work, everything=args.all)
    passed = all(c["ok"] for c in result["checks"])
    return 0 if passed and (result["committed"] or not args.apply) else 1
