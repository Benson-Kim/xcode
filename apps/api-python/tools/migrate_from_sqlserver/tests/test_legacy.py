"""The legacy PostgreSQL source (``docs/10-data-migration.md`` section 7), end to end.

A legacy database is built from the dump's schema (``fixtures/legacy/legacy_schema.sql``) and
synthetic rows that go in through the old application's own triggers
(``fixtures/legacy/legacy_rows.sql``), then marked read-only; ``extract --source legacy``
reads it, and ``transform``/``load`` run against targets built by ``xcode-api db migrate``.
Every figure of 7.5 is worked out here again from the fixture database with the test's own
SQL and its own list of the rows that do not move.
"""

from __future__ import annotations

import calendar
import copy
import csv
import io
import json
import os
import re
import uuid
from collections.abc import Iterator
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import psycopg
import pytest
from psycopg import sql
from psycopg.rows import dict_row

from migrate_from_sqlserver import legacy_checks
from migrate_from_sqlserver.cli import main
from migrate_from_sqlserver.legacy_tablemap import RIGHTS, TABLES
from migrate_from_sqlserver.profile import Manifest

from .conftest import TEMPLATE, Server, Target, admin_on, cli_env

FIXTURES = Path(__file__).parent / "fixtures" / "legacy"
LEGACY_ENV = "XCODE_MIGRATION_LEGACY_URL"


def _id(prefix: str, n: int) -> str:
    return f"{prefix}0000000-0000-4000-8000-{n:012d}"


ADA, HYPATIA, GRACE, MARY, ALAN, NIKOLA = (_id("a", n) for n in range(1, 7))
V1, V2, V3 = (_id("b", n) for n in range(1, 4))
EARNINGS, OFFLOAD, DIESEL, OIL, BRANDING, BRANDING_TWIN, SAVINGS, SACCO = (
    _id("d", n) for n in range(1, 9)
)


def rec(n: int) -> str:
    return _id("e", n)


def cash(n: int) -> str:
    return _id("f", n)


PEOPLE = (
    ("ada@legacy.example", "ada@legacy.example", "0711000001", ""),
    ("hypatia@legacy.example", "hypatia@fleet.example", "0711000002", ""),
    ("grace@legacy.example", "grace.hopper@fleet.example", "0711 000 003", "Owner"),
    ("mary@legacy.example", "mary@legacy.example", "0711000004", ""),
    ("alan@legacy.example", "alan@legacy.example", "0711000005", ""),
    ("nikola@legacy.example", "nikola@legacy.example", "0711000006", ""),
)
MIGRATED_BY = "ada@legacy.example"
HELD_BACK = {
    rec(5),
    rec(6),
    rec(12),
    rec(13),
    rec(14),
    rec(16),
    cash(4),
    cash(8),
    cash(15),
    cash(16),
}
ACCEPT = str(len(HELD_BACK))
PERSONAL = (
    "Ada Lovelace",
    "Lovelace",
    "Hypatia",
    "Brewster",
    "Hopper",
    "Seacole",
    "Turing",
    "Tesla",
    "legacy.example",
    "fleet.example",
    "Payee Fixture Hardware",
)
PHONE = re.compile(r"(?:\+?254|0)?\s*7\s*1\s*1\s*0\s*0\s*0\s*0\s*0\s*[1-6]")
FLEET_MANAGER_29 = {
    "dash.gaps",
    "dash.net",
    "dash.pettycash",
    "expenses.view",
    "pettycash.edit_own",
    "pettycash.spend",
    "pettycash.view",
    "reports.view",
    "revenue.capture",
    "revenue.correct",
    "revenue.view",
    "catalog.view",
    "catalog.add",
    "catalog.edit",
    "pettycash.view_all",
    "pettycash.reports",
    "expenses.capture",
    "expenses.correct",
    "reports.export",
    "revenue.export",
    "expenses.export",
    "pettycash.export",
    "vehicles.view",
    "vehicles.add",
    "vehicles.edit",
    "vehicles.target",
    "companies.view",
    "companies.add",
    "companies.edit",
}


def build_legacy(server: Server, name: str, rows: bool = True, read_only: bool = True) -> str:
    with psycopg.connect(server.admin, autocommit=True) as conn:
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    url = admin_on(server.admin, name)
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute((FIXTURES / "legacy_schema.sql").read_text(encoding="utf-8"))  # type: ignore[arg-type]
    if rows:
        with psycopg.connect(url, autocommit=True) as conn:
            conn.execute((FIXTURES / "legacy_rows.sql").read_text(encoding="utf-8"))  # type: ignore[arg-type]
    if read_only:
        read_only_now(server, name)
    return url


def read_only_now(server: Server, name: str) -> None:
    with psycopg.connect(server.admin, autocommit=True) as conn:
        conn.execute(
            sql.SQL("ALTER DATABASE {} SET default_transaction_read_only = on").format(
                sql.Identifier(name)
            )
        )


def drop(server: Server, name: str) -> None:
    with psycopg.connect(server.admin, autocommit=True) as conn:
        conn.execute(
            sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name))
        )


@pytest.fixture(scope="module")
def legacy(server: Server) -> Iterator[str]:
    name = f"mig10l_{uuid.uuid4().hex[:12]}"
    try:
        yield build_legacy(server, name)
    finally:
        drop(server, name)


def run(*args: str, env: dict[str, str] | None = None) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    saved = {k: os.environ.get(k) for k in (env or {})}
    os.environ.update(env or {})
    try:
        with redirect_stdout(out), redirect_stderr(err):
            code = main(list(args))
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    return code, out.getvalue(), err.getvalue()


@pytest.fixture(scope="module")
def extracted(legacy: str, tmp_path_factory: pytest.TempPathFactory) -> Path:
    directory = tmp_path_factory.mktemp("legacy") / "extract"
    code, out, err = run(
        "extract", "--source", "legacy", "--output", str(directory), env={LEGACY_ENV: legacy}
    )
    assert code == 0, err
    assert "extracted" in out
    return directory


def people_file(directory: Path, rows: tuple[tuple[str, str, str, str], ...] = PEOPLE) -> Path:
    path = directory / "people.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["legacy_email", "email", "phone", "role"])
        writer.writerows(rows)
    return path


def legacy_args(directory: Path, people: Path | None = None) -> list[str]:
    return [
        "--migrated-by",
        MIGRATED_BY,
        "--people",
        str(people or people_file(directory)),
        "--organization-name",
        "Fixture Fleet",
        "--organization-slug",
        "fixture-fleet",
    ]


def load(
    directory: Path, extract: Path, *args: str, people: Path | None = None
) -> tuple[int, str, str, dict, dict | None]:
    work = directory / "work"
    code, out, err = run(
        "load",
        *args,
        "--input",
        str(extract),
        "--output",
        str(work),
        *legacy_args(directory, people),
    )
    summary = json.loads((work / "transform.json").read_text(encoding="utf-8"))
    path = work / "load.json"
    result = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None
    return code, out, err, summary, result


def counts(target: Target) -> int:
    """Rows in every table of the legacy map, and the load's own operator actions."""
    with target.owner() as conn:
        mapped = sum(
            conn.execute(f"SELECT count(*) FROM {t.target}").fetchone()[0]  # type: ignore[index]
            for t in TABLES
        )
        actions = conn.execute(
            "SELECT count(*) FROM ops.operator_actions WHERE action = 'data_migration_load'"
        ).fetchone()[0]  # type: ignore[index]
    return int(mapped) + int(actions)


@dataclass
class Applied:
    target: Target
    work: Path
    summary: dict
    load: dict
    out: str
    err: str


@pytest.fixture(scope="module")
def applied(
    server: Server, extracted: Path, tmp_path_factory: pytest.TempPathFactory
) -> Iterator[Applied]:
    name = f"mig10_{uuid.uuid4().hex[:12]}"
    with psycopg.connect(server.admin, autocommit=True) as conn:
        conn.execute(
            sql.SQL("CREATE DATABASE {} TEMPLATE {} OWNER xcode_owner").format(
                sql.Identifier(name), sql.Identifier(TEMPLATE)
            )
        )
    target = Target(server, name)
    directory = tmp_path_factory.mktemp("applied")
    env = {k: v for k, v in cli_env(target.owner_url).items() if k.startswith("XCODE_")}
    env["XCODE_API_CLI"] = server.cli
    try:
        with pytest.MonkeyPatch.context() as patch:
            for key, value in env.items():
                patch.setenv(key, value)
            code, out, err, summary, result = load(
                directory, extracted, "--apply", "--accept-rejected", ACCEPT
            )
        assert code == 0, (err, [c for c in (result or {}).get("checks", []) if not c["ok"]])
        assert result is not None
        yield Applied(target, directory / "work", summary, result, out, err)
    finally:
        drop(server, name)


def rows(target: Target, query: str, params: tuple[object, ...] = ()) -> list[tuple[object, ...]]:
    with target.owner() as conn:
        return [tuple(r) for r in conn.execute(query, params)]  # type: ignore[arg-type]


def legacy_rows(url: str, query: str) -> list[tuple[object, ...]]:
    with psycopg.connect(url) as conn:
        conn.execute("SET TimeZone = 'UTC'")
        return [tuple(r) for r in conn.execute(query)]  # type: ignore[arg-type]


def month_day(n: int) -> date:
    """``pg_temp.d(n)`` of the fixture: the first day of the last full month, plus n days."""
    this_month = datetime.now(ZoneInfo("Africa/Nairobi")).date().replace(day=1)
    return (this_month - timedelta(days=1)).replace(day=1) + timedelta(days=n)


# The extract


def test_the_extract_writes_every_file_and_the_source_figures(extracted: Path, legacy: str) -> None:
    manifest = json.loads((extracted / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["source"]["kind"] == "legacy"
    assert manifest["source"]["alembic_version"] == "d8e1a4f9c220"
    assert manifest["source"]["snapshot"] == "REPEATABLE READ READ ONLY"
    tables = dict(
        legacy_rows(
            legacy,
            "SELECT relname, n FROM (VALUES "
            + ", ".join(
                f"('{t}', (SELECT count(*) FROM public.{t}))" for t in manifest["legacy_tables"]
            )
            + ") AS c (relname, n)",
        )
    )
    assert manifest["legacy_tables"] == tables
    records = sum(
        manifest["tables"][f]["rows"]
        for f in ("records_revenue", "records_expenses", "records_copies")
    )
    assert records == tables["records"] == 17
    assert manifest["tables"]["records_copies"]["rows"] == 4
    users = (extracted / "users.csv").read_text(encoding="utf-8")
    assert "password" not in users and "fixture.not.a.hash" not in users
    amounts = legacy_rows(legacy, "SELECT plus, minus FROM public.petty_cash")
    balance = sum(
        (Decimal(repr(p)) if p is not None else Decimal(0))
        - (Decimal(repr(m)) if m is not None else Decimal(0))
        for p, m in amounts
    )
    assert Decimal(manifest["figures"]["float"][0]["amount"]) == balance


def test_the_extract_refuses_a_database_that_answers_a_write(
    server: Server, tmp_path: Path
) -> None:
    name = f"mig10l_{uuid.uuid4().hex[:12]}"
    try:
        url = build_legacy(server, name, rows=False, read_only=False)
        code, _, err = run(
            "extract", "--source", "legacy", "--output", str(tmp_path / "x"), env={LEGACY_ENV: url}
        )
    finally:
        drop(server, name)
    assert code == 1
    assert "answers a write" in err
    assert not (tmp_path / "x" / "manifest.json").exists()


def test_a_url_that_only_asks_for_read_only_sessions_does_not_pass_a_writable_database(
    server: Server, tmp_path: Path
) -> None:
    name = f"mig10l_{uuid.uuid4().hex[:12]}"
    try:
        url = build_legacy(server, name, read_only=False)
        joiner = "&" if "?" in url else "?"
        code, _, err = run(
            "extract",
            "--source",
            "legacy",
            "--output",
            str(tmp_path / "x"),
            env={LEGACY_ENV: f"{url}{joiner}options=-c%20default_transaction_read_only%3Don"},
        )
        with psycopg.connect(url, autocommit=True) as conn:
            conn.execute("CREATE TABLE public.written (x int)")
    finally:
        drop(server, name)
    assert code == 1
    assert "answers a write" in err
    assert not (tmp_path / "x" / "manifest.json").exists()


def test_the_extract_refuses_another_alembic_version_and_soft_deleted_rows(
    server: Server, tmp_path: Path
) -> None:
    name = f"mig10l_{uuid.uuid4().hex[:12]}"
    try:
        url = build_legacy(server, name, read_only=False)
        with psycopg.connect(url, autocommit=True) as conn:
            conn.execute("UPDATE public.alembic_version SET version_num = 'ffffffffffff'")
        read_only_now(server, name)
        code, _, err = run(
            "extract", "--source", "legacy", "--output", str(tmp_path / "a"), env={LEGACY_ENV: url}
        )
        assert code == 1 and "d8e1a4f9c220" in err
        with psycopg.connect(url, autocommit=True) as conn:
            conn.execute("SET default_transaction_read_only = off")
            conn.execute("UPDATE public.alembic_version SET version_num = 'd8e1a4f9c220'")
            conn.execute(f"UPDATE public.vehicles SET deleted_at = now() WHERE id = '{V3}'")
        code, _, err = run(
            "extract", "--source", "legacy", "--output", str(tmp_path / "b"), env={LEGACY_ENV: url}
        )
        assert code == 1 and "soft-deleted rows {'vehicles': 1}" in err
    finally:
        drop(server, name)


# Refusals that stop the load or the transform


def test_a_dry_run_with_the_held_back_rows_accepted_passes_every_check_and_writes_nothing(
    target: Target, extracted: Path, tmp_path: Path
) -> None:
    code, _, _, summary, result = load(
        tmp_path, extracted, "--dry-run", "--accept-rejected", ACCEPT
    )
    assert code == 0
    assert result is not None and result["committed"] is False
    assert [c["name"] for c in result["checks"] if not c["ok"]] == []
    assert {r["key"].removeprefix("id=") for r in summary["rejected"]} == HELD_BACK
    assert counts(target) == 0


def test_apply_without_the_acknowledgement_writes_nothing(
    target: Target, extracted: Path, tmp_path: Path
) -> None:
    code, _, _, _, result = load(tmp_path, extracted, "--apply")
    assert code == 1
    assert result is not None and result["committed"] is False
    failed = [c["name"] for c in result["checks"] if not c["ok"]]
    assert failed == ["refused rows acknowledged"]
    assert counts(target) == 0


def test_a_legacy_user_missing_from_the_people_file_stops_the_load(
    target: Target, extracted: Path, tmp_path: Path
) -> None:
    people = people_file(tmp_path, PEOPLE[:-1])
    code, _, _, summary, result = load(
        tmp_path, extracted, "--apply", "--accept-rejected", str(len(HELD_BACK) + 1), people=people
    )
    assert code == 1
    refused = [r for r in summary["rejected"] if r["blocking"]]
    assert [(r["table"], r["key"]) for r in refused] == [("identity.users", f"id={NIKOLA}")]
    assert "no row in --people" in refused[0]["problem"]
    assert result is not None and result["committed"] is False
    assert "no refused person or organization" in [
        c["name"] for c in result["checks"] if not c["ok"]
    ]
    assert counts(target) == 0


def test_a_person_left_without_a_number_is_refused(
    target: Target, extracted: Path, tmp_path: Path
) -> None:
    people = people_file(tmp_path, (*PEOPLE[:1], (*PEOPLE[1][:2], "", ""), *PEOPLE[2:]))
    code, _, _, summary, _ = load(tmp_path, extracted, "--dry-run", people=people)
    assert code == 1
    assert [
        (r["key"], r["blocking"]) for r in summary["rejected"] if r["table"] == "identity.users"
    ] == [(f"id={HYPATIA}", True)]


def test_a_copy_that_disagrees_with_its_original_stops_the_transform(
    server: Server, target: Target, tmp_path: Path
) -> None:
    name = f"mig10l_{uuid.uuid4().hex[:12]}"
    try:
        url = build_legacy(server, name, read_only=False)
        with psycopg.connect(url, autocommit=True) as conn:
            conn.execute(
                f"UPDATE public.records SET amount = 2999 WHERE petty_cash_id = '{cash(5)}'"
            )
        read_only_now(server, name)
        extract = tmp_path / "extract"
        assert (
            run("extract", "--source", "legacy", "--output", str(extract), env={LEGACY_ENV: url})[0]
            == 0
        )
    finally:
        drop(server, name)
    code, _, err = run(
        "transform",
        "--input",
        str(extract),
        "--output",
        str(tmp_path / "w"),
        *legacy_args(tmp_path),
    )
    assert code == 1
    assert f"copies petty_cash id={cash(5)} but differs in amount" in err
    assert not (tmp_path / "w" / "transform.json").exists()


def test_the_people_file_and_migrated_by_are_checked_without_echoing_a_value(
    target: Target, extracted: Path, tmp_path: Path
) -> None:
    bad = tmp_path / "bad.csv"
    bad.write_text("email,phone\nx@y.example,0711000009\n", encoding="utf-8")
    code, _, err = run(
        "transform",
        "--input",
        str(extracted),
        "--output",
        str(tmp_path / "w1"),
        "--migrated-by",
        MIGRATED_BY,
        "--people",
        str(bad),
    )
    assert code == 1 and "the header must be legacy_email,email,phone,role" in err
    twice = people_file(
        tmp_path, (*PEOPLE, ("someone@legacy.example", PEOPLE[0][1], "0711000009", ""))
    )
    code, _, err = run(
        "transform",
        "--input",
        str(extracted),
        "--output",
        str(tmp_path / "w2"),
        *legacy_args(tmp_path, twice),
    )
    assert code == 1 and "line 8: email repeats line 2" in err
    code, _, err = run(
        "transform",
        "--input",
        str(extracted),
        "--output",
        str(tmp_path / "w3"),
        "--migrated-by",
        "mary@legacy.example",
        "--people",
        str(people_file(tmp_path)),
    )
    assert code == 1 and "moves as an Owner" in err
    for message in (err,):
        assert not any(value in message for value in PERSONAL)
    code, _, err = run("transform", "--input", str(extracted), "--output", str(tmp_path / "w4"))
    assert code == 1 and "needs --people" in err
    stranger = people_file(
        tmp_path, (*PEOPLE, ("stranger@legacy.example", "x@new.example", "0711000009", ""))
    )
    code, _, err = run(
        "transform",
        "--input",
        str(extracted),
        "--output",
        str(tmp_path / "w5"),
        *legacy_args(tmp_path, stranger),
    )
    assert code == 1 and "line 8: its legacy_email is not a user of the source" in err
    assert "stranger" not in err


def test_a_second_default_petty_cash_manager_stops_the_transform(
    server: Server, target: Target, tmp_path: Path
) -> None:
    name = f"mig10l_{uuid.uuid4().hex[:12]}"
    try:
        url = build_legacy(server, name, read_only=False)
        with psycopg.connect(url, autocommit=True) as conn:
            conn.execute(
                f"UPDATE public.users SET is_default_petty_cash_manager = true WHERE id = '{ALAN}'"
            )
        read_only_now(server, name)
        extract = tmp_path / "extract"
        assert (
            run("extract", "--source", "legacy", "--output", str(extract), env={LEGACY_ENV: url})[0]
            == 0
        )
    finally:
        drop(server, name)
    code, _, err = run(
        "transform",
        "--input",
        str(extract),
        "--output",
        str(tmp_path / "w"),
        *legacy_args(tmp_path),
    )
    assert code == 1
    assert "marks 2 default petty-cash managers" in err


# The applied load


def test_every_legacy_row_is_loaded_dropped_by_a_named_rule_refused_or_replaced(
    applied: Applied,
) -> None:
    sources = {s["file"]: s for s in applied.summary["sources"]}
    for s in sources.values():
        assert s["rows"] == s["loaded"] + s["dropped"] + s["refused"] + s["replaced"], s
    assert (
        sources["records_revenue"]["loaded"],
        sources["records_revenue"]["dropped"],
        sources["records_revenue"]["refused"],
    ) == (4, 1, 2)
    assert (sources["records_expenses"]["loaded"], sources["records_expenses"]["refused"]) == (2, 4)
    assert sources["records_copies"]["dropped"] == 4
    assert (
        sources["petty_cash"]["loaded"],
        sources["petty_cash"]["dropped"],
        sources["petty_cash"]["refused"],
    ) == (10, 2, 4)
    assert sources["entries"]["dropped"] == 5
    assert sources["roles"]["replaced"] == 3 and sources["permissions"]["replaced"] == 43
    check = {c["name"]: c for c in applied.load["checks"]}
    assert check["every legacy row is loaded, dropped by a named rule, refused, or replaced"]["ok"]
    assert (
        "COMMITTED" in applied.out and "RESULT: committed; every verification passed" in applied.out
    )


def test_people_move_with_their_number_role_names_and_no_pin(applied: Applied) -> None:
    found = {
        str(r[0]): r[1:]
        for r in rows(
            applied.target,
            "SELECT u.id, u.email, u.phone_number, u.pin_hash IS NULL, u.status, m.first_name, "
            "m.last_name, m.active, m.back_limit_mode, r.name, s.all_companies "
            "FROM identity.users AS u JOIN tenancy.memberships AS m ON m.user_id = u.id "
            "JOIN tenancy.person_roles AS pr ON pr.user_id = u.id "
            "JOIN tenancy.roles AS r ON r.id = pr.role_id "
            "JOIN tenancy.data_scopes AS s ON s.user_id = u.id",
        )
    }
    assert found == {
        ADA: (
            "ada@legacy.example",
            "+254711000001",
            True,
            "active",
            "Ada",
            "Lovelace",
            True,
            "none",
            "Owner",
            True,
        ),
        HYPATIA: (
            "hypatia@fleet.example",
            "+254711000002",
            True,
            "active",
            "Hypatia",
            "Hypatia",
            True,
            "none",
            "Owner",
            True,
        ),
        GRACE: (
            "grace.hopper@fleet.example",
            "+254711000003",
            True,
            "active",
            "Grace Brewster",
            "Hopper",
            True,
            "none",
            "Owner",
            True,
        ),
        MARY: (
            "mary@legacy.example",
            "+254711000004",
            True,
            "active",
            "Mary",
            "Seacole",
            True,
            "none",
            "Fleet manager",
            True,
        ),
        ALAN: (
            "alan@legacy.example",
            "+254711000005",
            True,
            "active",
            "Alan",
            "Turing",
            True,
            "none",
            "Fleet manager",
            True,
        ),
        NIKOLA: (
            "nikola@legacy.example",
            "+254711000006",
            True,
            "active",
            "Nikola",
            "Tesla",
            True,
            "none",
            "Fleet manager",
            True,
        ),
    }
    organization = rows(applied.target, "SELECT name, slug FROM tenancy.organizations")
    assert organization == [("Fixture Fleet", "fixture-fleet")]
    assert rows(applied.target, "SELECT name FROM tenancy.roles ORDER BY name") == [
        ("Fleet manager",),
        ("Office admin",),
        ("Owner",),
        ("Revenue clerk",),
    ]
    changes = {
        (c["key"], c["column"])
        for c in applied.summary["changed"]
        if c["table"] in {"identity.users", "tenancy.memberships"}
    }
    assert changes == {
        (f"id={HYPATIA}", "email"),
        (f"id={HYPATIA}", "phone_number"),
        (f"id={GRACE}", "email"),
        (f"id={HYPATIA}", "last_name"),
    }


def test_the_rights_of_each_person(applied: Applied) -> None:
    organization = rows(applied.target, "SELECT id FROM tenancy.organizations")[0][0]
    with applied.target.owner() as conn:
        catalogue = {
            r[0] for r in conn.execute("SELECT key FROM tenancy.permissions WHERE catalogue")
        }
        conn.execute("SELECT tenancy.enter_organization_as_operator(%s)", (organization,))
        held = {
            person: set(
                conn.execute(
                    "SELECT tenancy.assigned_permissions(%s, %s)", (organization, person)
                ).fetchone()[0]
            )
            & catalogue  # type: ignore[index]
            for person in (ADA, HYPATIA, GRACE, MARY, ALAN, NIKOLA)
        }
        overrides = conn.execute(
            "SELECT count(*) FROM tenancy.permission_overrides WHERE user_id IN (%s, %s, %s)",
            (ADA, HYPATIA, GRACE),
        ).fetchone()[0]  # type: ignore[index]
    assert len(catalogue) == 59
    assert held[ADA] == held[HYPATIA] == held[GRACE] == catalogue
    assert overrides == 0
    assert held[MARY] == held[ALAN] == FLEET_MANAGER_29
    assert held[NIKOLA] == set()
    assert {r for rights in RIGHTS.values() for r in rights} <= catalogue


def test_revenue_keeps_the_first_of_a_double_day_and_turns_0_into_a_reason(
    applied: Applied,
) -> None:
    found = {
        str(r[0]): r[1:]
        for r in rows(
            applied.target,
            "SELECT id, vehicle_id, business_date, amount, reason, note, captured_by, "
            "updated_by, version FROM revenue.records",
        )
    }
    assert set(found) == {rec(1), rec(3), rec(4), rec(7)}
    assert found[rec(1)][2] == Decimal("10000.00")
    assert found[rec(3)][2:5] == (None, 4, "0 in the old system")
    assert found[rec(4)][2] == Decimal("7500.50")
    assert {r[5] for r in found.values()} == {uuid.UUID(ADA)}
    dropped = [d for d in applied.summary["dropped"] if d["reason"] == "double_entry"]
    assert [d["key"] for d in dropped] == [f"id={rec(2)}"]


def test_central_expenses_map_merged_items_and_hold_back_the_rest(applied: Applied) -> None:
    found = {
        str(r[0]): r[1:]
        for r in rows(
            applied.target,
            "SELECT id, expense_item_id, units, unit_amount, total, group_id = id, group_size, "
            "group_total, recorded_by FROM expenses.entries",
        )
    }
    assert set(found) == {rec(11), rec(15)}
    assert found[rec(15)][:4] == (
        uuid.UUID(BRANDING),
        Decimal("2.000"),
        Decimal("500.00"),
        Decimal("1000.00"),
    )
    assert found[rec(11)][4:7] == (True, 1, Decimal("1200.00"))
    reasons = {r["key"].removeprefix("id="): r["problem"] for r in applied.summary["rejected"]}
    assert {k for k, v in reasons.items() if "no category" in v} == {rec(12), rec(13), rec(14)}
    assert "divide by the quantity" in reasons[rec(16)]


def test_petty_cash_kinds_statuses_authors_and_the_one_holder(applied: Applied) -> None:
    found = {
        str(r[0]): r[1:]
        for r in rows(
            applied.target,
            "SELECT id, holder_id, kind, status, expense_item_id, units, unit_amount, total, "
            "payee, note, "
            "reviewed_by, reviewed_at = updated_at, recorded_by, updated_by FROM pettycash.entries",
        )
    }
    ada, mary = uuid.UUID(ADA), uuid.UUID(MARY)
    assert {r[0] for r in found.values()} == {mary}
    assert found[cash(1)][1:] == (
        1,
        None,
        None,
        Decimal("1.000"),
        Decimal("50000.00"),
        Decimal("50000.00"),
        None,
        "Float top-up",
        None,
        None,
        ada,
        ada,
    )
    assert found[cash(13)][8] == "Cash Received"
    assert found[cash(5)][1:3] == (2, 2) and found[cash(5)][9:] == (ada, True, mary, ada)
    assert found[cash(7)][1:3] == (2, 1) and found[cash(7)][9:] == (None, None, mary, mary)
    assert found[cash(9)][3] == uuid.UUID(BRANDING)
    assert found[cash(11)][4:7] == (Decimal("0.500"), Decimal("1000.00"), Decimal("500.00"))
    assert found[cash(12)][1:3] == (3, None) and found[cash(12)][7:9] == (
        "Payee Fixture Hardware",
        "Returned part",
    )
    assert found[cash(14)][7:9] == (None, "Insurance 111")
    assert cash(3) not in found and cash(10) not in found and cash(8) not in found
    refused = {r["key"].removeprefix("id="): r for r in applied.summary["rejected"]}
    assert (
        refused[cash(4)]["constraint"] == "format"
        and "more than 2 decimal places" in refused[cash(4)]["problem"]
    )
    assert "needs a vehicle" in refused[cash(8)]["problem"]
    assert "whole cents" in refused[cash(15)]["problem"]
    assert "whole cents" in refused[cash(16)]["problem"]
    holders = {
        c["key"].removeprefix("id=")
        for c in applied.summary["changed"]
        if c["column"] == "holder_id"
    }
    assert holders == {cash(1), cash(2), cash(13), cash(5), cash(6), cash(7), cash(4)}


def test_vehicles_companies_categories_and_items(applied: Applied) -> None:
    vehicles = {
        str(r[0]): r[1:]
        for r in rows(
            applied.target,
            "SELECT v.id, v.registration, v.joined_on, c.name FROM setup.fleet_vehicles AS v "
            "JOIN setup.psv_companies AS c ON c.id = v.company_id",
        )
    }
    assert vehicles == {
        V1: ("KAA 111A", month_day(-5), "Alpha Sacco"),
        V2: ("KBB 222B", month_day(-10), "Alpha Sacco"),
        V3: ("KCC 333C", month_day(1), "Beta Sacco"),
    }
    changed = applied.summary["changed"]
    assert [(c["key"], c["from"], c["to"]) for c in changed if c["column"] == "company_id"] == [
        (f"id={V1}", "alpha sacco ", "Alpha Sacco")
    ]
    assert {(c["key"], c["to"]) for c in changed if c["column"] == "registration"} == {
        (f"id={V2}", "KBB 222B"),
        (f"id={V3}", "KCC 333C"),
    }
    assert {c["key"] for c in changed if c["column"] == "joined_on"} == {f"id={V1}"}
    assert sorted(rows(applied.target, "SELECT name FROM setup.expense_categories")) == [
        ("Body Works",),
        ("Fuel",),
        ("Repairs",),
    ]
    assert sorted(
        str(r[0]) for r in rows(applied.target, "SELECT id FROM setup.expense_items")
    ) == sorted([DIESEL, OIL, BRANDING])
    rules = {
        d["key"].removeprefix("id="): d["reason"]
        for d in applied.summary["dropped"]
        if d["source"] == "entries"
    }
    assert rules == {
        EARNINGS: "revenue_item",
        OFFLOAD: "revenue_item",
        SAVINGS: "uncategorised_item",
        SACCO: "uncategorised_item",
        BRANDING_TWIN: "merged_item",
    }


def _independent_figures(url: str) -> dict[str, object]:
    """The figures of 7.5 from the fixture, with the test's own list of what does not move."""
    held, doubles, zero = HELD_BACK, {rec(2)}, {cash(3), cash(10)}
    out = set(held) | doubles | zero
    revenue = legacy_rows(
        url,
        "SELECT r.id::text, r.date, r.plus FROM public.records AS r "
        "JOIN public.entries AS e ON e.id = r.entry_id WHERE e.factor = 'plus'",
    )
    moved = [(d, Decimal(str(p))) for i, d, p in revenue if i not in out]
    costs = legacy_rows(
        url,
        "SELECT r.id::text, r.petty_cash_id::text, r.vehicle_id::text, r.date, r.minus "
        "FROM public.records AS r JOIN public.entries AS e ON e.id = r.entry_id "
        "WHERE e.factor = 'minus'",
    )
    vehicle_costs: dict[tuple[str, str], Decimal] = {}
    for i, pc, vehicle, day, minus in costs:
        if i in out or (pc is not None and pc in out):
            continue
        key = (vehicle, day.strftime("%Y-%m"))
        vehicle_costs[key] = vehicle_costs.get(key, Decimal(0)) + Decimal(str(minus))
    cash_rows = legacy_rows(
        url, "SELECT id::text, credit_note, plus, minus, committed FROM public.petty_cash"
    )
    buckets: dict[str, tuple[int, Decimal]] = {}
    balance = Decimal(0)
    for i, credit, plus, minus, committed in cash_rows:
        if i in out:
            continue
        name = (
            "credit note"
            if credit
            else "cash"
            if plus is not None
            else "expense approved"
            if committed
            else "expense waiting"
        )
        amount = Decimal(str(plus if plus is not None else minus))
        n, total = buckets.get(name, (0, Decimal(0)))
        buckets[name] = (n + 1, total + amount)
        balance += amount if plus is not None else -amount
    return {
        "days": len(moved),
        "revenue": sum((a for _, a in moved), Decimal(0)),
        "costs": vehicle_costs,
        "buckets": buckets,
        "float": balance,
    }


def test_each_figure_of_7_5_matches_the_fixture(applied: Applied, legacy: str) -> None:
    want = _independent_figures(legacy)
    revenue = rows(
        applied.target, "SELECT count(*), sum(coalesce(amount, 0)) FROM revenue.records"
    )[0]
    assert revenue == (want["days"], want["revenue"]) == (4, Decimal("25500.50"))
    costs = {
        (str(r[0]), str(r[1])): r[2]
        for r in rows(
            applied.target,
            "SELECT vehicle_id, to_char(entry_date, 'YYYY-MM'), sum(total) FROM ("
            "SELECT vehicle_id, entry_date, total FROM expenses.entries UNION ALL "
            "SELECT vehicle_id, entry_date, total FROM pettycash.entries "
            "WHERE kind = 2 AND status = 2"
            ") AS c GROUP BY 1, 2",
        )
    }
    assert costs == want["costs"]
    buckets = {
        r[0]: (r[1], r[2])
        for r in rows(
            applied.target,
            "SELECT CASE kind WHEN 1 THEN 'cash' WHEN 3 THEN 'credit note' WHEN 2 THEN "
            "CASE status WHEN 2 THEN 'expense approved' ELSE 'expense waiting' END END, "
            "count(*), sum(total) "
            "FROM pettycash.entries GROUP BY 1",
        )
    }
    assert buckets == want["buckets"]
    balance = rows(
        applied.target,
        "SELECT sum(CASE WHEN kind = 1 THEN total ELSE -total END) FROM pettycash.entries",
    )[0][0]
    assert balance == want["float"] == Decimal("134300.00")
    check = {c["name"]: c for c in applied.load["checks"]}
    for name in (
        "revenue per vehicle and month: days and Earnings equal the source less what did not move",
        "vehicle costs per vehicle and month: central expenses and approved petty cash equal "
        "the source records less what did not move",
        "petty cash per kind and status, and the float, equal the source less what did not move",
        "every petty-cash entry is held by the one float holder",
    ):
        assert check[name]["ok"], check[name]


def test_through_the_routines_the_vehicle_report_and_sign_in_see_the_migrated_rows(
    applied: Applied, legacy: str
) -> None:
    want = _independent_figures(legacy)["costs"]
    first = month_day(0)
    month = first.strftime("%Y-%m")
    last = first.replace(day=calendar.monthrange(first.year, first.month)[1])
    organization = rows(applied.target, "SELECT id FROM tenancy.organizations")[0][0]
    with applied.target.owner() as conn:
        conn.execute("BEGIN")
        conn.execute("SELECT tenancy.enter_organization_as_operator(%s)", (organization,))
        posted = {
            vehicle: conn.execute(
                "SELECT coalesce(sum(amount), 0) FROM "
                "setup.fleet_postings(ARRAY[%s]::uuid[], %s, %s, %s) WHERE kind = 1",
                (vehicle, first, last, datetime.now(ZoneInfo("Africa/Nairobi")).date()),
            ).fetchone()[0]  # type: ignore[index]
            for vehicle in (V1, V2, V3)
        }
        conn.execute("ROLLBACK")
        conn.execute("BEGIN")
        start = conn.execute(
            "SELECT api.auth_start('test', '0711 000 003', 'test-device', NULL, %s, true, now())",
            ("A" * 64,),
        ).fetchone()[0]  # type: ignore[index]
        status = conn.execute(
            "SELECT identity.sign_in_status(u, true) FROM identity.users AS u WHERE u.id = %s",
            (GRACE,),
        ).fetchone()[0]  # type: ignore[index]
        conn.execute("ROLLBACK")
    assert posted == {v: want.get((v, month), Decimal(0)) for v in (V1, V2, V3)}
    assert posted[V1] == Decimal("8200.00")
    assert (start["outcome"], start["purpose"]) == ("verification_required", "first_setup")  # type: ignore[index]
    assert status == "not_signed_in"
    check = {c["name"]: c for c in applied.load["checks"]}
    signed = check["people with a number reach 'Not signed in yet' through the sign-in routines"]
    assert signed["ok"] and signed["detail"] == "6 of 6 asked for a first-setup code"
    assert check[
        f"the vehicle report's postings for {month} (setup.fleet_postings) equal the vehicle costs"
    ]["ok"]


def test_the_exceptions_list_against_the_fixture(applied: Applied) -> None:
    with (applied.work / "exceptions.csv").open(encoding="utf-8", newline="") as handle:
        listed = list(csv.DictReader(handle))
    assert list(listed[0]) == [
        "kind",
        "day",
        "vehicle",
        "item",
        "amount",
        "entered",
        "reason",
        "legacy_table",
        "legacy_id",
        "decision",
        "note",
    ]
    assert {
        (r["kind"], r["legacy_id"]) for r in listed if r["kind"] != "petty-cash balance day"
    } == {
        *(("held back", i) for i in HELD_BACK),
        ("left out", cash(3)),
        ("left out", cash(10)),
        ("double entry dropped", rec(2)),
        ("possible double, moved", cash(2)),
        ("possible double, moved", cash(6)),
    }
    days = [(r["day"], r["amount"]) for r in listed if r["kind"] == "petty-cash balance day"]
    assert days == [(month_day(12).isoformat(), "500.00"), (month_day(19).isoformat(), "-1500.00")]
    by_id = {r["legacy_id"]: r for r in listed}
    assert (by_id[rec(13)]["vehicle"], by_id[rec(13)]["item"], by_id[rec(13)]["amount"]) == (
        "KCC 333C",
        "Sacco",
        "300.00",
    )
    assert (by_id[cash(8)]["vehicle"], by_id[cash(8)]["item"], by_id[cash(8)]["amount"]) == (
        "",
        "Body Branding",
        "30000.00",
    )
    assert by_id[cash(4)]["amount"] == "12345.675"
    assert by_id[cash(2)]["item"] == "Cash received: Float top-up"
    assert by_id[cash(4)]["day"] == month_day(19).isoformat()
    assert all(r["decision"] == "" and r["note"] == "" and r["reason"] for r in listed)
    assert by_id[rec(2)]["entered"].endswith("18:05")


def test_no_name_e_mail_number_or_payee_reaches_any_output(applied: Applied) -> None:
    outputs = {
        "transform.json": (applied.work / "transform.json").read_text(encoding="utf-8"),
        "load.json": (applied.work / "load.json").read_text(encoding="utf-8"),
        "exceptions.csv": (applied.work / "exceptions.csv").read_text(encoding="utf-8"),
        "report": applied.out,
        "errors": applied.err,
    }
    for name, text in outputs.items():
        assert not [v for v in PERSONAL if v.lower() in text.lower()], name
        assert not PHONE.search(text), name


_BREAKS = (
    (
        "revenue per vehicle and month",
        "UPDATE revenue.records SET amount = amount + 1 WHERE id = ("
        "SELECT id FROM revenue.records WHERE amount IS NOT NULL ORDER BY id LIMIT 1)",
    ),
    (
        "vehicle costs per vehicle and month",
        "UPDATE expenses.entries SET removed_at = now(), removed_by = recorded_by, "
        "removal_reason = 'check' WHERE id = (SELECT id FROM expenses.entries "
        "WHERE to_char(entry_date, 'YYYY-MM') = %(month)s ORDER BY id LIMIT 1)",
    ),
    (
        "the vehicle report's postings",
        "UPDATE expenses.entries SET removed_at = now(), removed_by = recorded_by, "
        "removal_reason = 'check' WHERE id = (SELECT id FROM expenses.entries "
        "WHERE to_char(entry_date, 'YYYY-MM') = %(month)s ORDER BY id LIMIT 1)",
    ),
    (
        "petty cash per kind and status",
        "UPDATE pettycash.entries SET unit_amount = unit_amount + 1 WHERE id = ("
        "SELECT id FROM pettycash.entries WHERE kind = 1 ORDER BY id LIMIT 1)",
    ),
    (
        "every petty-cash entry is held by the one float holder",
        "UPDATE pettycash.entries SET holder_id = %(other)s WHERE id = ("
        "SELECT id FROM pettycash.entries WHERE kind = 1 ORDER BY id LIMIT 1)",
    ),
    (
        "every legacy user is a person",
        "UPDATE tenancy.data_scopes SET all_companies = false WHERE user_id = %(other)s",
    ),
    (
        "each person's rights hold",
        "INSERT INTO tenancy.permission_overrides (organization_id, user_id, permission, granted) "
        "VALUES (%(organization)s, %(other)s, 'revenue.view', false)",
    ),
    (
        "people with a number reach",
        "UPDATE identity.users SET pin_hash = 'c2FsdA==.aGFzaA==' WHERE id = %(other)s",
    ),
)


def test_each_check_of_7_5_fails_on_a_target_that_breaks_it(applied: Applied) -> None:
    manifest = Manifest.read(applied.work)
    summary = applied.summary
    params = {
        "month": summary["legacy"]["last_full_month"],
        "organization": summary["legacy"]["organization_id"],
        "other": next(p for p in (MARY, ALAN) if p != summary["legacy"]["holder"]),
    }

    def failing(statement: str | None) -> list[str]:
        with (
            psycopg.connect(applied.target.owner_url, row_factory=dict_row) as conn,
            conn.transaction(force_rollback=True),
        ):
            conn.execute("SET TimeZone = 'UTC'")
            if statement is not None:
                assert conn.execute(statement, params).rowcount == 1, statement  # type: ignore[arg-type]
            return [c.name for c in legacy_checks.verify(conn, summary, manifest) if not c.ok]

    assert failing(None) == []
    for name, statement in _BREAKS:
        assert any(f.startswith(name) for f in failing(statement)), name
    assert legacy_checks.source_ledger(summary, manifest).ok
    short = copy.deepcopy(summary)
    short["dropped"] = short["dropped"][1:]
    assert not legacy_checks.source_ledger(short, manifest).ok
