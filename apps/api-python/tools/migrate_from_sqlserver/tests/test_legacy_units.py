"""Checks of the legacy profile that need no database."""

from __future__ import annotations

import json
import re
from decimal import Decimal
from pathlib import Path

import pytest

from migrate_from_sqlserver import legacy_tablemap as m
from migrate_from_sqlserver.cli import _people
from migrate_from_sqlserver.legacy_conversions import PROFILE, _exact_total, money_text, translate
from migrate_from_sqlserver.legacy_report import COLUMNS, write_exceptions
from migrate_from_sqlserver.profile import Manifest
from migrate_from_sqlserver.records import TargetCatalogue, ToolError

FIXTURES = Path(__file__).parent / "fixtures" / "legacy"


def test_the_legacy_map_is_in_load_order_and_every_file_has_a_place() -> None:
    targets = [t.target for t in m.TABLES]
    assert len(targets) == len(set(targets))
    assert [t.order for t in m.TABLES] == list(range(1, len(m.TABLES) + 1))
    by_source = {t.source: t for t in m.TABLES if t.source is not None}
    for extract in m.EXTRACTS:
        assert extract.table in m.LEGACY_TABLES
        if extract.fate == m.LOADED:
            assert by_source[extract.name].source_columns == extract.columns
        else:
            assert extract.rule in m.RULES
            assert extract.name not in by_source
    assert {e.table for e in m.EXTRACTS} | {t for t, _ in m.COUNTED} == set(m.LEGACY_TABLES)
    assert {f.name for f in PROFILE.files} == {e.name for e in m.EXTRACTS}
    for table in m.TABLES:
        for name in table.drops:
            assert name in PROFILE.drops and name in m.RULES
        for name in table.convert:
            assert name in PROFILE.conversions


def test_the_records_files_split_the_table_by_their_conditions() -> None:
    queries = {e.name: e.rows for e in m.EXTRACTS if e.table == "records"}
    assert set(queries) == {"records_revenue", "records_expenses", "records_copies"}
    assert "r.petty_cash_id IS NULL AND e.factor = 'plus'" in queries["records_revenue"]
    assert (
        "r.petty_cash_id IS NULL AND e.factor IS DISTINCT FROM 'plus'"
        in queries["records_expenses"]
    )
    assert "LEFT JOIN" in queries["records_expenses"]
    assert "r.petty_cash_id IS NOT NULL" in queries["records_copies"]


def test_the_rights_table_names_every_legacy_permission() -> None:
    rows = (FIXTURES / "legacy_rows.sql").read_text(encoding="utf-8")
    block = rows[rows.index("INSERT INTO permissions") : rows.index("INSERT INTO roles")]
    titles = set(re.findall(r"'([a-z_]+:[a-z_]+)'", block))
    assert len(titles) == 43
    assert set(m.RIGHTS) == titles
    assert {k for k, v in m.RIGHTS.items() if not v} == {
        "budgets:read",
        "budgets:write",
        "reports:budget",
    }


def _catalogue() -> TargetCatalogue:
    return TargetCatalogue(
        catalogue=frozenset({"revenue.view", "revenue.capture", "dash.net", "people.view"}),
        keys=frozenset(),
        dependencies={
            "revenue.capture": frozenset({"revenue.view"}),
            "dash.net": frozenset({"revenue.view"}),
        },
        role_defaults={},
        translations={},
        time_zones=frozenset(),
    )


def test_a_translation_adds_each_right_s_needs_and_lists_names_without_a_right() -> None:
    rights, not_carried = translate(
        ["records:write", "dashboard:read", "budgets:read", "unknown:thing"], _catalogue()
    )
    assert rights == {"revenue.capture", "revenue.view", "dash.net"}
    assert not_carried == ["budgets:read", "unknown:thing"]


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "people.csv"
    path.write_text(text, encoding="utf-8")
    return path


def test_the_people_file_is_read_by_legacy_e_mail_with_a_known_role(tmp_path: Path) -> None:
    people = _people(
        _write(
            tmp_path,
            "legacy_email,email,phone,role\n"
            " Someone@Old.example ,someone@new.example,0711 000 009,owner\n"
            "other@old.example,other@new.example,0711000008,\n",
        )
    )
    assert people is not None
    assert sorted(people) == ["other@old.example", "someone@old.example"]
    assert people["someone@old.example"].role == "Owner"
    assert people["other@old.example"].role is None
    assert people["someone@old.example"].line == 2


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("email,phone\nsecret@x.example,0711000001\n", "the header must be"),
        (
            "legacy_email,email,phone,role\na@x.example,secret@x.example,0711000001,Boss\n",
            "line 2: role must be Owner, Fleet manager or empty",
        ),
        (
            "legacy_email,email,phone,role\na@x.example,secret@x.example,0711000001,\n"
            "b@x.example,SECRET@x.example,0711000002,\n",
            "line 3: email repeats line 2",
        ),
        (
            "legacy_email,email,phone,role\na@x.example,a@y.example,+254 711 000 001,\n"
            "b@x.example,b@y.example,0711000001,\n",
            "line 3: phone repeats line 2",
        ),
        ("legacy_email,email,phone,role\n,secret@x.example,0711000001,\n", "line 2: legacy_email"),
    ],
)
def test_a_people_file_problem_names_the_line_and_never_a_value(
    tmp_path: Path, text: str, message: str
) -> None:
    with pytest.raises(ToolError) as caught:
        _people(_write(tmp_path, text))
    assert message in str(caught.value)
    assert "secret" not in str(caught.value).lower() and "0711" not in str(caught.value)


def test_a_manifest_without_a_kind_is_sql_server_s(tmp_path: Path) -> None:
    (tmp_path / "manifest.json").write_text(
        json.dumps({"extracted_at": "2026-10-14T06:00:00+00:00", "source": {}, "tables": {}}),
        encoding="utf-8",
    )
    assert Manifest.read(tmp_path).kind == "sqlserver"
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {
                "extracted_at": "2026-10-14T06:00:00+00:00",
                "source": {"kind": "oracle"},
                "tables": {},
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ToolError, match="unknown source kind"):
        _ = Manifest.read(tmp_path).kind


def test_typed_text_that_a_spreadsheet_would_run_is_written_as_text(tmp_path: Path) -> None:
    row = dict.fromkeys(COLUMNS[:-2], "")
    row.update(
        kind="held back",
        day="2026-09-20",
        item='=HYPERLINK("http://x.example")',
        vehicle="@KAA 111A",
        amount="-1500.00",
        reason="+1 more",
    )
    assert write_exceptions(tmp_path, {"exceptions": [row]}) == 1
    lines = (tmp_path / "exceptions.csv").read_text(encoding="utf-8").splitlines()
    written = next(iter(__import__("csv").DictReader(lines)))
    assert written["item"].startswith("'=HYPERLINK")
    assert written["vehicle"] == "'@KAA 111A"
    assert written["reason"] == "'+1 more"
    assert written["amount"] == "-1500.00"
    assert written["day"] == "2026-09-20"


def test_amounts_read_to_the_cent_unless_they_have_more() -> None:
    assert money_text(Decimal("-1500.000")) == "-1500.00"
    assert money_text(Decimal("30000")) == "30000.00"
    assert money_text(Decimal("12345.675")) == "12345.675"


def test_a_total_must_be_exact_and_in_whole_cents() -> None:
    """The target stores round(units * unit_amount, 2): an amount it would round, or one that
    is not the product, does not move."""
    assert _exact_total(Decimal("2"), Decimal("1500"), Decimal("3000"))
    assert _exact_total(Decimal("0.5"), Decimal("1000"), Decimal("500"))
    assert not _exact_total(Decimal("1.5"), Decimal("10.25"), Decimal("15.375"))
    assert not _exact_total(Decimal("4.5"), Decimal("33.33"), Decimal("149.98499999999999"))
    assert not _exact_total(Decimal("1"), Decimal("100"), None)
