"""Transform and load against a PostgreSQL target built by ``xcode-api db migrate``."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import shutil
import subprocess
import sys
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import psycopg
import pytest

from migrate_from_sqlserver.cli import main
from migrate_from_sqlserver.formats import parse_csv
from migrate_from_sqlserver.tablemap import TABLES

from . import fixture_data as fx
from .conftest import Target, run_cli

LOADED_TABLES = [t.target for t in TABLES if t.since <= 12]


def _load(tmp: Path, *args: str) -> tuple[int, dict, dict | None]:
    work = tmp / "work"
    code = main(["load", *args, "--input", str(fx.EXTRACT_DIR), "--output", str(work)])
    summary = json.loads((work / "transform.json").read_text(encoding="utf-8"))
    load_path = work / "load.json"
    load = json.loads(load_path.read_text(encoding="utf-8")) if load_path.is_file() else None
    return code, summary, load


def _counts(target: Target) -> dict[str, int]:
    """Rows in every loaded table, and the load's own operator actions (the template already
    holds the migration runner's)."""
    with target.owner() as conn:
        counts = {
            name: conn.execute(f"SELECT count(*) FROM {name}").fetchone()[0]  # type: ignore[index]
            for name in LOADED_TABLES
        }
        counts["data_migration_load"] = conn.execute(
            "SELECT count(*) FROM ops.operator_actions WHERE action = 'data_migration_load'"
        ).fetchone()[0]  # type: ignore[index]
    return counts


def _checks(load: dict) -> dict[str, dict]:
    return {c["name"]: c for c in load["checks"]}


def test_the_invalid_row_is_reported_by_its_key_and_a_dry_run_writes_nothing(
    target: Target, tmp_path: Path
) -> None:
    sequence_before = target.scalar(
        "SELECT last_value FROM pg_sequences "
        "WHERE schemaname = 'tenancy' AND sequencename = 'audit_events_id_seq'"
    )
    code, summary, load = _load(tmp_path, "--dry-run")

    assert code == 1
    assert [(r["table"], r["key"], r["constraint"]) for r in summary["rejected"]] == [
        (
            "setup.vehicle_away_periods",
            f"OrganizationId={fx.ORG}|Id={fx.INVALID_AWAY}",
            "ck_vehicle_away_periods_returned_on",
        )
    ]
    assert load is not None and load["committed"] is False
    assert _checks(load)["refused rows acknowledged"]["ok"] is False
    assert all(n == 0 for n in _counts(target).values())
    assert (
        target.scalar(
            "SELECT last_value FROM pg_sequences "
            "WHERE schemaname = 'tenancy' AND sequencename = 'audit_events_id_seq'"
        )
        == sequence_before
    )


def test_a_dry_run_that_accepts_the_refusal_passes_every_check_and_still_writes_nothing(
    target: Target, tmp_path: Path
) -> None:
    code, _, load = _load(tmp_path, "--dry-run", "--accept-rejected", "1")

    assert code == 0
    assert load is not None
    assert [c["name"] for c in load["checks"] if not c["ok"]] == []
    assert load["committed"] is False
    assert all(n == 0 for n in _counts(target).values())


def test_apply_loads_everything_else_and_records_the_operator(
    target: Target, tmp_path: Path
) -> None:
    code, summary, load = _load(tmp_path, "--apply", "--accept-rejected", "1")

    assert code == 0, [c for c in load["checks"] if not c["ok"]] if load else summary
    assert load is not None and load["committed"] is True
    counts = _counts(target)
    for table in summary["tables"]:
        assert counts[table["target"]] == table["loaded"], table["target"]
    assert counts["setup.vehicle_away_periods"] == 1
    assert (
        target.scalar(
            "SELECT count(*) FROM setup.vehicle_away_periods WHERE id = %s",
            (fx.INVALID_AWAY.lower(),),
        )
        == 0
    )
    with target.owner() as conn:
        actions = conn.execute(
            "SELECT operator, action, target, detail FROM ops.operator_actions "
            "WHERE action = 'data_migration_load'"
        ).fetchall()
    assert [(a[0], a[1], a[2]) for a in actions] == [
        ("migration-tests", "data_migration_load", target.name)
    ]
    assert actions[0][3]["refused"] == 1
    verify = run_cli(target.server.cli, ["db", "verify"], target.owner_url)
    assert verify.returncode == 0, verify.stdout + verify.stderr


def test_counts_and_checksums_match_the_manifest_and_the_load_files(
    target: Target, tmp_path: Path
) -> None:
    code, summary, _ = _load(tmp_path, "--apply", "--accept-rejected", "1")
    assert code == 0
    manifest = json.loads((fx.EXTRACT_DIR / "manifest.json").read_text(encoding="utf-8"))
    for name, entry in manifest["tables"].items():
        if "file" in entry:
            data = (fx.EXTRACT_DIR / entry["file"]).read_bytes()
            assert hashlib.sha256(data).hexdigest() == entry["sha256"], name
            assert len(parse_csv(data)[1]) == entry["rows"], name
    work = tmp_path / "work"
    with target.owner() as conn:
        for table in summary["tables"]:
            columns = ", ".join(table["columns"])
            order = ", ".join(table["key"])
            buffer = bytearray()
            with conn.cursor().copy(
                f"COPY (SELECT {columns} FROM {table['target']} ORDER BY {order}) "
                "TO STDOUT WITH (FORMAT csv, FORCE_QUOTE *)"
            ) as copy:
                for chunk in copy:
                    buffer += chunk
            file = (work / table["file"]).read_bytes()
            assert file.split(b"\n", 1)[1] == bytes(buffer), table["target"]
            assert hashlib.sha256(file).hexdigest() == table["sha256"]


def test_revenue_per_organization_and_month_matches_the_source(
    target: Target, tmp_path: Path
) -> None:
    assert _load(tmp_path, "--apply", "--accept-rejected", "1")[0] == 0
    source: dict[tuple[str, str], Decimal] = defaultdict(Decimal)
    for row in fx.rows()["RevenueRecords"]:
        if row["Amount"] is not None:
            source[(str(row["OrganizationId"]).lower(), str(row["BusinessDate"])[:7])] += Decimal(
                str(row["Amount"])
            )
    with target.owner() as conn:
        loaded = {
            (str(r[0]), r[1]): r[2]
            for r in conn.execute(
                "SELECT organization_id, to_char(business_date, 'YYYY-MM'), sum(amount) "
                "FROM revenue.records GROUP BY 1, 2"
            )
        }
    assert loaded == dict(source)
    assert set(m for _, m in loaded) == {"2026-09", "2026-10"}


def test_every_tenant_row_names_an_existing_organization(target: Target, tmp_path: Path) -> None:
    assert _load(tmp_path, "--apply", "--accept-rejected", "1")[0] == 0
    with target.owner() as conn:
        tables = [
            r[0]
            for r in conn.execute(
                "SELECT c.table_schema || '.' || c.table_name FROM information_schema.columns AS c "
                "JOIN information_schema.tables AS t USING (table_schema, table_name) "
                "WHERE c.column_name = 'organization_id' AND t.table_type = 'BASE TABLE' "
                "AND c.table_schema IN ('tenancy', 'setup', 'revenue', 'pettycash')"
            )
        ]
        assert len(tables) >= 20
        loaded_rows = 0
        for name in tables:
            loaded_rows += conn.execute(f"SELECT count(*) FROM {name}").fetchone()[0]  # type: ignore[index]
            orphans = conn.execute(
                f"SELECT count(*) FROM {name} AS t WHERE NOT EXISTS "
                "(SELECT 1 FROM tenancy.organizations AS o WHERE o.id = t.organization_id)"
            ).fetchone()[0]  # type: ignore[index]
            assert orphans == 0, name
        assert loaded_rows > 50


def _pin_matches(stored: str, pin: str) -> bool:
    salt, key = (base64.b64decode(part) for part in stored.split("."))
    return hmac.compare_digest(hashlib.pbkdf2_hmac("sha256", pin.encode(), salt, 210_000, 32), key)


def test_a_copied_pin_hash_and_token_digest_sign_in_through_the_routines(
    target: Target, tmp_path: Path
) -> None:
    """The hash and the digest moved byte for byte: the owner's PIN verifies against the
    copied hash, the decision routine signs the owner in on the trusted phone, the session
    resolves with the copied security version, and the copied refresh digest rotates."""
    assert _load(tmp_path, "--apply", "--accept-rejected", "1")[0] == 0
    now = fx.EXTRACTED_AT + timedelta(hours=1)
    owner = fx.OWNER.lower()
    stored_hash = next(u["PinHash"] for u in fx.rows()["Users"] if u["Id"] == fx.OWNER)
    with psycopg.connect(target.app_url, autocommit=True) as conn:
        lookup = conn.execute(
            "SELECT user_id, pin_hash, security_version, device_trusted "
            "FROM api.auth_account_lookup('req-1', %s, %s, NULL, true, %s)",
            (fx.OWNER_PHONE, fx.OWNER_DEVICE, now),
        ).fetchone()
        assert lookup is not None
        assert (str(lookup[0]), lookup[1], lookup[2], lookup[3]) == (owner, stored_hash, 3, True)
        assert _pin_matches(lookup[1], fx.PIN)
        assert not _pin_matches(lookup[1], "2581")

        new_refresh = (
            hmac.new(fx.SIGNING_KEY.encode(), b"after-sign-in", hashlib.sha256).hexdigest().upper()
        )
        signed_in = conn.execute(
            "SELECT api.auth_sign_in('req-2', %s, %s, true, %s, NULL, %s, false, %s)",
            (owner, fx.OWNER_DEVICE, lookup[1], new_refresh, now),
        ).fetchone()[0]  # type: ignore[index]
        assert signed_in["outcome"] == "authenticated", signed_in

        session = conn.execute(
            "SELECT api.auth_resolve_session(%s, %s, %s, %s)", (owner, fx.OWNER_DEVICE, 3, now)
        ).fetchone()[0]  # type: ignore[index]
        assert session["organization_id"] == fx.ORG.lower()
        assert session["role"] == "Owner"

        copied = fx.digest(fx.OWNER_TOKEN)
        rotated = conn.execute(
            "SELECT api.auth_refresh('req-3', %s, %s, %s, %s)",
            (copied, fx.OWNER_DEVICE, fx.digest("rotated"), now),
        ).fetchone()[0]  # type: ignore[index]
        assert rotated["outcome"] == "authenticated", rotated

        with pytest.raises(psycopg.Error, match="session_invalid"):
            conn.execute(
                "SELECT api.auth_resolve_session(%s, %s, %s, %s)", (owner, fx.OWNER_DEVICE, 2, now)
            )


def test_the_design_conversions_arrive_as_documented(target: Target, tmp_path: Path) -> None:
    code, summary, _ = _load(tmp_path, "--apply", "--accept-rejected", "1")
    assert code == 0
    with target.owner() as conn:
        users = {
            str(r[0]).upper(): r[1:]
            for r in conn.execute(
                "SELECT id, email, phone_number, status, failed_attempts, "
                "untrusted_failed_attempts, pin_hash IS NULL FROM identity.users"
            )
        }
        assert users[fx.OWNER][:2] == ("owner@example.com", "+254711000001")
        assert users[fx.CLERK][1] == "+254711000002"
        assert users[fx.CLERK][3] == 5
        assert users[fx.MANAGER][3:5] == (0, 5)
        assert users[fx.ADMIN][5] is True
        assert users[fx.LEAVER][2] == "removed"

        sets = conn.execute(
            "SELECT vehicle_id, starts_on::text, monday, sunday, monday * 6 + sunday "
            "FROM setup.vehicle_target_sets ORDER BY 1, 2"
        ).fetchall()
        by_vehicle = {(str(s[0]).upper(), s[1]): s[2:] for s in sets}
        assert by_vehicle[(fx.V1, "2026-01-05")] == (
            Decimal("1100.00"),
            Decimal("1100.00"),
            Decimal("7700.00"),
        )
        assert by_vehicle[(fx.V1, "2026-06-01")] == (
            Decimal("1428.57"),
            Decimal("1428.58"),
            Decimal("10000.00"),
        )
        assert (fx.V2, "2026-01-05") not in by_vehicle
        reasons = {(d["table"], d["reason"]) for d in summary["dropped"]}
        assert ("setup.vehicle_target_sets", "superseded_target") in reasons
        assert ("setup.vehicle_target_sets", "target_too_small") in reasons

        mains = dict(
            conn.execute(
                "SELECT c.name, m.name FROM setup.expense_categories AS c "
                "JOIN setup.expense_main_categories AS m ON m.id = c.main_category_id"
            ).fetchall()
        )
        assert mains == {
            "Repairs": "Repairs and maintenance",
            "Insurance": "Recurring charges",
            "Loans": "Loan repayments",
        }

        assert (
            conn.execute("SELECT time_zone FROM tenancy.organization_localizations").fetchone()[0]
            == "Africa/Nairobi"
        )  # type: ignore[index]
        assert conn.execute(
            "SELECT access_token_minutes, logo_light_url "
            "FROM tenancy.organization_security_policies "
            "CROSS JOIN tenancy.organization_brandings"
        ).fetchone() == (15, None)
        assert (
            conn.execute(
                "SELECT count(*) FROM tenancy.memberships WHERE back_limit_mode <> 'none'"
            ).fetchone()[0]
            == 0
        )  # type: ignore[index]

        petty = {
            str(r[0]).upper(): r[1:]
            for r in conn.execute(
                "SELECT id, kind, status, sent_back_note, reviewed_by IS NOT NULL, total "
                "FROM pettycash.entries"
            )
        }
        assert petty[fx.guid("pc:sent-back")][:3] == (2, 1, "Attach the receipt")
        assert petty[fx.guid("pc:credit")][1:4] == (None, None, False)
        assert petty[fx.guid("pc:approved")][4] == Decimal("99.99")

        devices = {
            r[0]: r[1]
            for r in conn.execute(
                "SELECT device_id, identity.device_live(d, %s) FROM identity.trusted_devices AS d",
                (fx.EXTRACTED_AT,),
            )
        }
        assert devices == {
            "phone-owner": True,
            "phone-clerk": True,
            "phone-old": False,
            "tablet-owner": False,
        }
        tokens = {r[0] for r in conn.execute("SELECT token_hash FROM identity.refresh_tokens")}
        assert tokens == {fx.digest(fx.OWNER_TOKEN), fx.digest("clerk-live")}

        assert (
            conn.execute(
                "SELECT count(*) FROM tenancy.permission_overrides AS o "
                "JOIN tenancy.permissions AS p ON p.key = o.permission WHERE NOT p.catalogue"
            ).fetchone()[0]
            == 0
        )  # type: ignore[index]
    clerk = next(p for p in summary["permissions"] if p["user_id"] == fx.CLERK.lower())
    assert "revenue.no_earnings" not in clerk["old"]
    manager = next(p for p in summary["permissions"] if p["user_id"] == fx.MANAGER.lower())
    assert "pettycash.approve_item" in manager["old"]
    admin = next(p for p in summary["permissions"] if p["user_id"] == fx.ADMIN.lower())
    assert "bills.approve" in admin["not_carried"]


def test_every_enumeration_value_arrives(target: Target, tmp_path: Path) -> None:
    assert _load(tmp_path, "--apply", "--accept-rejected", "1")[0] == 0
    with target.owner() as conn:

        def values(query: str) -> set[object]:
            return {r[0] for r in conn.execute(query)}  # type: ignore[arg-type]

        assert values("SELECT status FROM identity.users") == {"active", "removed"}
        assert values("SELECT reason FROM revenue.records") == {None, 1, 2, 3, 4}
        assert values("SELECT kind FROM setup.recurring_versions") == {1, 2}
        assert values("SELECT frequency FROM setup.recurring_versions") == {1, 2, 3, 4}
        assert values("SELECT bucket FROM setup.expense_categories") == {1, 2, 3}
        assert values("SELECT kind FROM pettycash.entries") == {1, 2, 3}
        assert values("SELECT status FROM pettycash.entries") == {None, 1, 2}


def test_apply_refuses_without_the_acknowledgement_and_writes_nothing(
    target: Target, tmp_path: Path
) -> None:
    code, _, load = _load(tmp_path, "--apply")
    assert code == 1
    assert load is not None and load["committed"] is False
    assert all(n == 0 for n in _counts(target).values())


def test_apply_refuses_a_refused_person_even_when_acknowledged(
    target: Target, tmp_path: Path
) -> None:
    data = fx.rows()
    data["Users"][0]["PhoneNumber"] = ""
    extract = tmp_path / "extract"
    fx.build(extract, data)
    work = tmp_path / "work"
    code = main(
        [
            "load",
            "--apply",
            "--input",
            str(extract),
            "--output",
            str(work),
            "--accept-rejected",
            "99",
        ]
    )
    assert code == 1
    summary = json.loads((work / "transform.json").read_text(encoding="utf-8"))
    assert summary["blocking"] >= 1
    assert all(n == 0 for n in _counts(target).values())


def test_apply_needs_the_operator_name(
    target: Target, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("XCODE_OPERATOR")
    work = tmp_path / "work"
    assert main(["transform", "--input", str(fx.EXTRACT_DIR), "--output", str(work)]) == 0
    assert main(["load", "--apply", "--input", str(work), "--accept-rejected", "1"]) == 1
    assert all(n == 0 for n in _counts(target).values())


def test_a_second_load_refuses_a_target_that_holds_rows(target: Target, tmp_path: Path) -> None:
    assert _load(tmp_path, "--apply", "--accept-rejected", "1")[0] == 0
    before = _counts(target)
    second = tmp_path / "second"
    code = main(
        [
            "load",
            "--apply",
            "--input",
            str(fx.EXTRACT_DIR),
            "--output",
            str(second),
            "--accept-rejected",
            "1",
        ]
    )
    assert code == 1
    assert _counts(target) == before


def test_a_tampered_load_file_stops_the_load(target: Target, tmp_path: Path) -> None:
    work = tmp_path / "work"
    assert main(["transform", "--input", str(fx.EXTRACT_DIR), "--output", str(work)]) == 0
    path = next((work / "load").glob("*identity.users.csv"))
    path.write_bytes(path.read_bytes().replace(b"+254711000001", b"+254711000009"))
    assert main(["load", "--apply", "--input", str(work), "--accept-rejected", "1"]) == 1
    assert all(n == 0 for n in _counts(target).values())


def test_a_tampered_extract_file_stops_the_transform(target: Target, tmp_path: Path) -> None:
    extract = tmp_path / "extract"
    shutil.copytree(fx.EXTRACT_DIR, extract)
    path = extract / "RevenueRecords.csv"
    path.write_bytes(path.read_bytes().replace(b'"4500.00"', b'"4600.00"'))
    assert main(["transform", "--input", str(extract), "--output", str(tmp_path / "w")]) == 1


def test_source_rows_for_a_table_the_target_lacks_stop_the_transform(
    target: Target, tmp_path: Path
) -> None:
    """Central expenses need migration 0013; the tool refuses to drop them silently."""
    if target.scalar("SELECT to_regclass('expenses.entries') IS NOT NULL"):
        pytest.skip("the target has expenses.entries (migration 0013): the guard does not apply")
    data = fx.rows()
    data["CentralExpenses"] = [
        {
            "OrganizationId": fx.ORG,
            "Id": fx.guid("ce:1"),
            "Date": "2026-10-01",
            "VehicleId": fx.V1,
            "ExpenseItemId": fx.TYRES,
            "Units": "1.000",
            "UnitAmount": "10.00",
            "Total": "10.00",
            "Note": None,
            "GroupId": fx.guid("ce:g1"),
            "GroupSize": "1",
            "GroupTotal": "10.00",
            "GroupUnits": "1.000",
            "GroupUnitAmount": "10.00",
            "RecordedBy": fx.OWNER,
            "RecordedAt": fx.at(fx.EXTRACTED_AT),
            "UpdatedBy": fx.OWNER,
            "UpdatedAt": fx.at(fx.EXTRACTED_AT),
            "RemovedBy": None,
            "RemovedAt": None,
            "RemovalReason": None,
            "Version": "1",
        }
    ]
    extract = tmp_path / "extract"
    fx.build(extract, data)
    assert main(["transform", "--input", str(extract), "--output", str(tmp_path / "w")]) == 1


def test_the_map_covers_every_column_the_target_requires(target: Target) -> None:
    """A target column that is NOT NULL without a default must be mapped; a mapped column must
    exist. This fails when a migration adds or renames a column the map does not know."""
    with target.owner() as conn:
        for table in TABLES:
            rows = conn.execute(
                "SELECT column_name, is_nullable = 'NO' AND column_default IS NULL "
                "AND is_generated = 'NEVER' AND is_identity = 'NO' "
                "FROM information_schema.columns WHERE table_schema || '.' || table_name = %s",
                (table.target,),
            ).fetchall()
            if not rows:
                assert table.since > 12, f"{table.target} is missing from the target"
                continue
            present = {r[0] for r in rows}
            required = {r[0] for r in rows if r[1]}
            mapped = {c.target for c in table.target_columns}
            assert mapped <= present, (table.target, mapped - present)
            assert required <= mapped, (table.target, required - mapped)


def test_the_cli_runs_as_the_prompt_shows(target: Target, tmp_path: Path) -> None:
    """``python -m migrate_from_sqlserver load --dry-run --input tests/fixtures/extract``."""
    done = subprocess.run(
        [
            sys.executable,
            "-m",
            "migrate_from_sqlserver",
            "load",
            "--dry-run",
            "--input",
            "tests/fixtures/extract",
            "--output",
            str(tmp_path / "w"),
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    assert done.returncode == 1, done.stderr
    assert "REFUSED ROWS (1; 0 blocking)" in done.stdout
    assert f"OrganizationId={fx.ORG}|Id={fx.INVALID_AWAY}" in done.stdout
    assert "RESULT: verification failed; nothing was written" in done.stdout


def test_a_row_lost_without_a_documented_rule_stops_the_load(
    target: Target, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A conversion that loses a row without a ledger entry is caught by the ledger check."""
    from migrate_from_sqlserver import conversions

    original = conversions.CONVERSIONS["normalized_name"]

    def losing(table, rows, ctx):  # type: ignore[no-untyped-def]
        kept = original(table, rows, ctx)
        return kept[1:] if table.source == "PsvCompany" else kept

    monkeypatch.setitem(conversions.CONVERSIONS, "normalized_name", losing)
    code, _, load = _load(tmp_path, "--apply", "--accept-rejected", "1")
    assert code == 1
    assert load is not None and load["committed"] is False
    ledger = _checks(load)["every source row is loaded, dropped by a documented rule, or refused"]
    assert ledger["ok"] is False
    assert any("setup.psv_companies" in line for line in ledger["lines"])
    assert all(n == 0 for n in _counts(target).values())


def test_a_value_the_database_changes_on_the_way_in_stops_the_transform_and_the_load(
    target: Target, tmp_path: Path
) -> None:
    work = tmp_path / "work"
    assert main(["transform", "--input", str(fx.EXTRACT_DIR), "--output", str(work)]) == 0
    with target.owner() as conn:
        conn.execute(
            "CREATE FUNCTION setup.test_alter_name() RETURNS trigger LANGUAGE plpgsql AS "
            "$$ BEGIN NEW.name := NEW.name || ' Ltd'; RETURN NEW; END $$"
        )
        conn.execute(
            "CREATE TRIGGER test_alter_name BEFORE INSERT ON setup.psv_companies "
            "FOR EACH ROW EXECUTE FUNCTION setup.test_alter_name()"
        )
    assert main(["load", "--dry-run", "--input", str(work), "--accept-rejected", "1"]) == 1
    load = json.loads((work / "load.json").read_text(encoding="utf-8"))
    sums = _checks(load)["each table's ordered rows equal its load file byte for byte (SHA-256)"]
    assert sums["ok"] is False and any("setup.psv_companies" in x for x in sums["lines"])
    again = tmp_path / "again"
    assert main(["transform", "--input", str(fx.EXTRACT_DIR), "--output", str(again)]) == 1
    assert not (again / "transform.json").exists()


def test_a_transform_json_unlike_the_table_map_stops_the_load(
    target: Target, tmp_path: Path
) -> None:
    """No SQL is built from the work directory: a table it names is the map's or nothing."""
    work = tmp_path / "work"
    assert main(["transform", "--input", str(fx.EXTRACT_DIR), "--output", str(work)]) == 0
    path = work / "transform.json"
    summary = json.loads(path.read_text(encoding="utf-8"))
    summary["tables"][0]["target"] = "identity.users; DROP TABLE tenancy.roles"
    path.write_text(json.dumps(summary), encoding="utf-8")
    assert main(["load", "--dry-run", "--input", str(work), "--accept-rejected", "1"]) == 1
    assert target.scalar("SELECT to_regclass('tenancy.roles') IS NOT NULL") is True
    assert not (work / "load.json").exists()


def test_a_settings_version_behind_the_change_log_stops_the_load(
    target: Target, tmp_path: Path
) -> None:
    """After the cutover the next logged change takes settings_version + 1; a copied change
    log that already holds that version would refuse every write of the organization."""
    data = fx.rows()
    data["Organizations"][0]["SettingsVersion"] = "3"
    extract = tmp_path / "extract"
    fx.build(extract, data)
    work = tmp_path / "work"
    code = main(
        [
            "load",
            "--apply",
            "--input",
            str(extract),
            "--output",
            str(work),
            "--accept-rejected",
            "1",
        ]
    )
    assert code == 1
    load = json.loads((work / "load.json").read_text(encoding="utf-8"))
    check = _checks(load)["each organization's settings version is past its change log"]
    assert check["ok"] is False
    assert all(n == 0 for n in _counts(target).values())
