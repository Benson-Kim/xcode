"""Checks that need no database."""

from __future__ import annotations

import ast
import re
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from migrate_from_sqlserver import legacy_catalogue
from migrate_from_sqlserver.conversions import new_set, normalize_phone, old_set, split_week
from migrate_from_sqlserver.database import require_tls
from migrate_from_sqlserver.extract import odbc_connection_string
from migrate_from_sqlserver.formats import (
    InvalidValueError,
    csv_bytes,
    duplicate_json_keys,
    format_target,
    parse_csv,
    parse_instant,
    parse_source,
    upper_c,
)
from migrate_from_sqlserver.records import TargetCatalogue, ToolError
from migrate_from_sqlserver.tablemap import TABLES

from . import fixture_data as fx
from .conftest import DB_DIR


def test_the_committed_fixture_equals_a_fresh_build(tmp_path: Path) -> None:
    fx.build(tmp_path)
    committed = sorted(p.name for p in fx.EXTRACT_DIR.iterdir())
    assert committed == sorted(p.name for p in tmp_path.iterdir())
    for name in committed:
        assert (fx.EXTRACT_DIR / name).read_bytes() == (tmp_path / name).read_bytes(), name


def test_the_legacy_catalogue_is_the_one_migration_0004_seeded() -> None:
    text = (DB_DIR / "migrations" / "0004_access_catalog.sql").read_text(encoding="utf-8")
    row = r"^  \('([a-z]+\.[a-z_]+)',\s*'[^']*',\s*'(?:[^']|'')*',\s*\d+,\s*\d+\)"
    keys = re.findall(row, text, re.M)
    assert tuple(keys) == legacy_catalogue.KEYS
    dependencies = re.findall(r"^  \('([a-z]+\.[a-z_]+)', '([a-z]+\.[a-z_]+)'\)[,;]", text, re.M)
    assert tuple(dependencies) == legacy_catalogue.DEPENDENCIES
    defaults = re.findall(
        r"^  \('(Office admin|Fleet manager|Revenue clerk)', '([a-z._]+)'\)", text, re.M
    )
    listed = [
        (role, key)
        for role, keys in legacy_catalogue.ROLE_DEFAULTS.items()
        if role != "Owner"
        for key in keys
    ]
    assert defaults == listed
    assert "SELECT 'Owner', key FROM tenancy.permissions WHERE key <> 'dash.capture'" in text
    assert sum(len(v) for v in legacy_catalogue.ROLE_DEFAULTS.values()) == 79


def test_the_map_is_in_foreign_key_order_and_names_each_target_once() -> None:
    orders = [t.order for t in TABLES]
    assert orders == sorted(orders) == list(range(1, len(TABLES) + 1))
    targets = [t.target for t in TABLES]
    assert len(targets) == len(set(targets))
    position = {t.target: i for i, t in enumerate(TABLES)}
    text = "\n".join(
        p.read_text(encoding="utf-8")
        for p in sorted((DB_DIR / "migrations").glob("*.sql"))
        if not p.name.endswith(".down.sql")
    )
    for table in TABLES:
        for referenced in re.findall(
            rf"CREATE TABLE {re.escape(table.target)} \((.*?)\n\);", text, re.S
        ):
            for parent in re.findall(r"REFERENCES ([a-z]+\.[a-z_]+)", referenced):
                if parent in position:
                    assert position[parent] < position[table.target], (table.target, parent)


def test_csv_round_trips_null_empty_quotes_and_newlines() -> None:
    rows = [("a", None, ""), ('say "hi"', "line\nbreak", "x,y")]
    header, body = parse_csv(csv_bytes(("one", "two", "three"), rows))
    assert header == ["one", "two", "three"]
    assert body == rows


def test_instants_round_the_100ns_digit_half_to_even_and_print_as_postgresql_does() -> None:
    assert parse_instant("2026-10-12 18:00:00.1234565").value.microsecond == 123456
    assert parse_instant("2026-10-12 18:00:00.1234575").value.microsecond == 123458
    carried = parse_instant("2026-10-12 23:59:59.9999995")
    assert carried.value == datetime(2026, 10, 13, tzinfo=UTC) and carried.rounded
    assert format_target("timestamptz", parse_instant("2026-10-12 18:00:00.5000000")) == (
        "2026-10-12 18:00:00.5+00"
    )
    assert format_target("timestamptz", parse_instant("2026-10-12 18:00:00.0000000")) == (
        "2026-10-12 18:00:00+00"
    )
    with pytest.raises(InvalidValueError):
        parse_instant("2026-10-12T18:00:00Z")


def test_values_print_as_postgresql_prints_them() -> None:
    assert parse_source("uuid", "6F1D2C3B-0A9E-4D8C-B7A6-5E4F3D2C1B0A") == (
        "6f1d2c3b-0a9e-4d8c-b7a6-5e4f3d2c1b0a"
    )
    assert format_target("numeric", Decimal("1500"), 2) == "1500.00"
    assert format_target("numeric", Decimal("-0.50"), 2) == "-0.50"
    with pytest.raises(InvalidValueError):
        format_target("numeric", Decimal("1.005"), 2)
    assert format_target("float8", parse_source("float", "1.0000000000000000E+000")) == "1"
    assert format_target("float8", parse_source("float", "1.2500000000000000E+000")) == "1.25"
    assert format_target("bytea", parse_source("binary", "89504E47")) == "\\x89504e47"
    assert format_target("bool", parse_source("bit", "1")) == "t"
    for kind, text in (("bit", "2"), ("int", "1.5"), ("decimal", "1e5"), ("uuid", "nope")):
        with pytest.raises(InvalidValueError):
            parse_source(kind, text)


def test_repeated_json_keys_are_found() -> None:
    assert duplicate_json_keys('{"a":1,"b":{"c":1,"c":2},"a":3}') == ["c", "a"]
    assert duplicate_json_keys('{"a":1}') == []


def test_upper_under_the_c_collation_folds_ascii_only() -> None:
    assert upper_c("\u00e9cole Bus") == "\u00e9COLE BUS"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("+254711000001", "+254711000001"),
        ("0711 000 002", "+254711000002"),
        ("254111000003", "+254111000003"),
        ("711000004", "+254711000004"),
        ("", None),
        ("+254811000001", None),
        ("07\u0661\u0661000002", None),
    ],
)
def test_phone_numbers_normalise_as_the_api_does(raw: str, expected: str | None) -> None:
    assert normalize_phone(raw) == expected


def test_a_week_splits_into_days_that_add_up_exactly() -> None:
    assert split_week(Decimal("7700.00")) == (Decimal("1100.00"), Decimal("1100.00"))
    day, sunday = split_week(Decimal("10000.00"))  # type: ignore[misc]
    assert day * 6 + sunday == Decimal("10000.00") and sunday > 0
    assert split_week(Decimal("0.05")) is None
    assert split_week(Decimal("0.07")) == (Decimal("0.01"), Decimal("0.01"))
    for cents in range(1, 3000):
        weekly = Decimal(cents) / 100
        split = split_week(weekly)
        if split is not None:
            assert split[0] * 6 + split[1] == weekly


def test_the_old_resolver_drops_denials_and_keys_missing_their_needs() -> None:
    clerk = old_set("revenue CLERK", set(), {"revenue.no_earnings"})
    assert clerk == {"dash.capture", "dash.gaps", "revenue.view", "revenue.capture"}
    held = old_set("Revenue clerk", set(), {"revenue.view"})
    assert held == set()
    granted = old_set(None, {"pettycash.approve_day"}, set())
    assert granted == {"pettycash.approve_day", "pettycash.approve_item", "pettycash.view_all"}


def test_the_new_set_follows_translations_role_rights_and_needs() -> None:
    catalogue = TargetCatalogue(
        catalogue=frozenset({"rev.view", "rev.capture", "pc.new"}),
        keys=frozenset({"rev.view", "rev.capture", "pc.new", "organization.manage"}),
        dependencies={"rev.capture": frozenset({"rev.view"})},
        role_defaults={
            "owner": frozenset({"rev.view", "rev.capture", "pc.new", "organization.manage"})
        },
        translations={
            "revenue.capture": frozenset({"rev.capture"}),
            "revenue.view": frozenset({"rev.view"}),
        },
        time_zones=frozenset(),
    )
    assert new_set("Owner", set(), catalogue) == {"pc.new"}
    assert new_set("Owner", {"revenue.capture"}, catalogue) == {"pc.new", "rev.capture", "rev.view"}
    assert new_set(None, {"revenue.capture"}, catalogue) == {"rev.capture", "rev.view"}


def test_ado_net_connection_strings_become_odbc_with_encryption_on() -> None:
    drivers = ["SQL Server", "ODBC Driver 17 for SQL Server", "ODBC Driver 18 for SQL Server"]
    ado = (
        "Server=localhost,1433;Database=XCodeTest;Integrated Security=True;Encrypt=True;"
        "TrustServerCertificate=True;Connect Timeout=60"
    )
    assert odbc_connection_string(ado, drivers) == (
        "Server=localhost,1433;Database=XCodeTest;Trusted_Connection=yes;Encrypt=yes;"
        "TrustServerCertificate=yes;Connection Timeout=60;Driver={ODBC Driver 18 for SQL Server}"
    )
    plain = odbc_connection_string("Server=db;Database=x;User Id=u;Password={p;w}", drivers)
    assert plain.endswith(";Encrypt=yes")
    assert "PWD={p;w}" in plain


@pytest.mark.parametrize(
    ("url", "refused"),
    [
        ("postgresql://xcode_owner:x@db.example.com/xcode", True),
        ("postgresql://xcode_owner:x@db.example.com/xcode?sslmode=require", True),
        ("postgresql://xcode_owner:x@db.example.com/xcode?sslmode=verify-full", False),
        (
            "postgresql://xcode_owner:x@db.example.com/xcode?sslmode=verify-full&sslmode=disable",
            True,
        ),
        ("postgresql://xcode_owner:x@127.0.0.1:5432/xcode", False),
        ("host=/var/run/postgresql dbname=xcode user=xcode_owner", False),
        ("host=localhost hostaddr=10.0.0.5 dbname=xcode", True),
    ],
)
def test_production_needs_verify_full_for_a_remote_target(
    url: str, refused: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XCODE_ENV", "production")
    if refused:
        with pytest.raises(ToolError, match="verify-full"):
            require_tls(url)
    else:
        require_tls(url)
    monkeypatch.setenv("XCODE_ENV", "development")
    require_tls(url)


def test_production_needs_an_encrypted_sql_server_connection_that_checks_its_certificate() -> None:
    drivers = ["ODBC Driver 18 for SQL Server"]
    for unsafe in ("Server=db;Encrypt=no", "Server=db;TrustServerCertificate=True"):
        with pytest.raises(ToolError, match="production"):
            odbc_connection_string(unsafe, drivers, production=True)
        odbc_connection_string(unsafe, drivers, production=False)
    assert "Encrypt=yes" in odbc_connection_string("Server=db", drivers, production=True)


def test_the_tool_imports_nothing_from_the_api_package() -> None:
    package = Path(__file__).resolve().parents[1] / "migrate_from_sqlserver"
    imported: set[str] = set()
    for path in package.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                imported.add(node.module.split(".")[0])
            elif isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
    assert "xcode_api" not in imported
    assert imported - set(sys.stdlib_module_names) <= {"psycopg", "pyodbc"}
