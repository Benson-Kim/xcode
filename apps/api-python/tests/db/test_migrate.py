"""The migration runner as xcode_owner (``docs/03-database.md`` section 7)."""

from __future__ import annotations

import json
import secrets
import threading
import time
from pathlib import Path

import psycopg
import pytest
from psycopg.rows import dict_row

from xcode_api.db.migrate import (
    MigrationError,
    Runner,
    advisory_lock,
    checksum_bytes,
    find_db_dir,
    open_owner_connection,
)
from xcode_api.db.verify import run_checks

from ..support.database import Harness, _with_role

pytestmark = pytest.mark.structure


def _runner(url: str) -> tuple[Runner, psycopg.Connection[dict[str, object]]]:
    conn = open_owner_connection(url)
    return Runner(conn, operator="tester", db_dir=find_db_dir()), conn


def test_fresh_apply_then_status_is_clean(fresh_owner_url: str) -> None:
    runner, conn = _runner(fresh_owner_url)
    try:
        with advisory_lock(conn):
            applied = runner.migrate()
            assert 1 in applied
            status = runner.status()
        assert status["pending"] == []
        assert status["routine_drift"] == []
        assert status["migration_checksum_drift"] == []
        rows = conn.execute("SELECT version FROM ops.schema_migrations").fetchall()
        assert {int(r["version"]) for r in rows} == set(applied)
    finally:
        conn.close()


def test_second_migrate_applies_nothing(fresh_owner_url: str) -> None:
    runner, conn = _runner(fresh_owner_url)
    try:
        with advisory_lock(conn):
            runner.migrate()
            again = runner.migrate()
        assert again == []
    finally:
        conn.close()


def test_edited_applied_file_is_refused(fresh_owner_url: str) -> None:
    runner, conn = _runner(fresh_owner_url)
    try:
        with advisory_lock(conn):
            runner.migrate()
            # Corrupt the recorded checksum to simulate an edited applied file.
            conn.execute("UPDATE ops.schema_migrations SET checksum = 'tampered' WHERE version = 1")
            with pytest.raises(MigrationError) as exc:
                runner.migrate()
        assert "0001" in str(exc.value) or "ops" in str(exc.value)
    finally:
        conn.close()


def test_recorded_version_without_a_file_is_refused(fresh_owner_url: str) -> None:
    runner, conn = _runner(fresh_owner_url)
    try:
        with advisory_lock(conn):
            runner.migrate()
            conn.execute(
                "INSERT INTO ops.schema_migrations "
                "(version, name, checksum, applied_at, applied_by, duration_ms) "
                "VALUES (9999, 'ghost', 'x', now(), 'tester', 0)"
            )
            with pytest.raises(MigrationError) as exc:
                runner.migrate()
        assert "9999" in str(exc.value)
    finally:
        conn.close()


def test_down_then_up(fresh_owner_url: str) -> None:
    runner, conn = _runner(fresh_owner_url)
    try:
        with advisory_lock(conn):
            # db down reverses only the latest applied version; 0001 is the one with a down file.
            runner.migrate(to=1)
            runner.down(1, confirmed=True, env="testing")
            after_down = conn.execute("SELECT count(*) AS n FROM ops.schema_migrations").fetchall()
            assert after_down[0]["n"] == 0
            table_gone = conn.execute("SELECT to_regclass('ops.operator_actions') AS t").fetchall()
            assert table_gone[0]["t"] is None
            again = runner.migrate()
        assert 1 in again
    finally:
        conn.close()


def _api_routines(conn: psycopg.Connection[dict[str, object]]) -> int:
    row = conn.execute(
        "SELECT count(*) AS n FROM pg_proc WHERE pronamespace = 'api'::regnamespace"
    ).fetchone()
    assert row is not None
    return int(str(row["n"]))


def test_routines_wait_until_no_migration_is_pending(fresh_owner_url: str) -> None:
    runner, conn = _runner(fresh_owner_url)
    try:
        with advisory_lock(conn):
            runner.migrate(to=1)
            assert _api_routines(conn) == 0
            with pytest.raises(MigrationError) as exc:
                runner.routines()
            assert "0002" in str(exc.value)
            runner.migrate()
            assert _api_routines(conn) > 0
    finally:
        conn.close()


def test_down_drops_the_routines_and_migrate_restores_them(fresh_owner_url: str) -> None:
    runner, conn = _runner(fresh_owner_url)
    try:
        with advisory_lock(conn):
            applied = runner.migrate()
            runner.down(max(applied), confirmed=True, env="testing")
            assert _api_routines(conn) == 0
            helper = conn.execute("SELECT to_regprocedure('identity.lock_user(uuid)') AS f")
            assert helper.fetchone() == {"f": None}
            runner.migrate()
            assert _api_routines(conn) > 0
            failed = [r for r in run_checks(conn) if not r.ok]
            assert not failed, [(r.name, r.failures) for r in failed]
    finally:
        conn.close()


def test_every_migration_reverses_and_reapplies(fresh_owner_url: str) -> None:
    runner, conn = _runner(fresh_owner_url)
    try:
        with advisory_lock(conn):
            applied = runner.migrate()
            for version in sorted(applied, reverse=True):
                runner.down(version, confirmed=True, env="testing")
            left = conn.execute(
                "SELECT count(*) AS n FROM pg_tables "
                "WHERE schemaname IN ('identity', 'tenancy', 'setup', 'revenue')"
            ).fetchone()
            again = runner.migrate()
        assert left == {"n": 0}
        assert again == applied
        failed = [r for r in run_checks(conn) if not r.ok]
        assert not failed, [(r.name, r.failures) for r in failed]
    finally:
        conn.close()


def test_routine_ownership_and_grants_are_fixed_up(fresh_owner_url: str) -> None:
    runner, conn = _runner(fresh_owner_url)
    try:
        with advisory_lock(conn):
            runner.migrate()
        rows = conn.execute(
            """
            SELECT p.proname AS name, pg_get_userbyid(p.proowner) AS owner,
                   has_function_privilege('xcode_app', p.oid, 'EXECUTE') AS app_exec,
                   has_function_privilege('xcode_operator', p.oid, 'EXECUTE') AS op_exec
            FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
            WHERE n.nspname = 'api'
            """
        ).fetchall()
        by_name = {str(r["name"]): r for r in rows}
        assert by_name["rate_limit_hit"]["owner"] == "xcode_api_executor"
        assert by_name["rate_limit_hit"]["app_exec"] is True
        # meta_* is granted to both; ops_* to the operator only.
        assert by_name["meta_contract_version"]["app_exec"] is True
        assert by_name["meta_contract_version"]["op_exec"] is True
        assert by_name["ops_record_operator_action"]["app_exec"] is False
        assert by_name["ops_record_operator_action"]["op_exec"] is True
    finally:
        conn.close()


def test_routines_rerun_fixes_grants_when_a_file_omits_them(fresh_owner_url: str) -> None:
    runner, conn = _runner(fresh_owner_url)
    try:
        with advisory_lock(conn):
            runner.migrate()
            # Simulate a routine whose file granted nothing / wrong owner; the runner re-fixes.
            sig = "api.rate_limit_hit(text, integer, integer, timestamptz)"
            conn.execute(f"ALTER FUNCTION {sig} OWNER TO xcode_owner")
            conn.execute(f"GRANT EXECUTE ON FUNCTION {sig} TO PUBLIC")
            runner.routines()
        rows = conn.execute(
            """
            SELECT pg_get_userbyid(p.proowner) AS owner,
                   EXISTS (
                     SELECT 1 FROM aclexplode(p.proacl) a
                     WHERE a.grantee = 0 AND a.privilege_type = 'EXECUTE'
                   ) AS public_exec
            FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
            WHERE n.nspname = 'api' AND p.proname = 'rate_limit_hit'
            """
        ).fetchall()
        assert rows[0]["owner"] == "xcode_api_executor"
        assert rows[0]["public_exec"] is False
    finally:
        conn.close()


def test_routines_leave_a_stale_overload_without_a_caller(fresh_owner_url: str) -> None:
    runner, conn = _runner(fresh_owner_url)
    stale = "api.meta_contract_version(integer)"
    current = "api.meta_contract_version()"
    try:
        with advisory_lock(conn):
            runner.migrate()
            conn.execute(
                "CREATE FUNCTION api.meta_contract_version(p_old integer) RETURNS integer "
                "LANGUAGE sql SECURITY DEFINER SET search_path = pg_catalog, pg_temp "
                "AS 'SELECT 0'"
            )
            runner.routines()
            conn.execute(f"GRANT EXECUTE ON FUNCTION {stale} TO xcode_app, xcode_operator")
            runner.routines()

        def can_execute(role: str, signature: str) -> bool:
            row = conn.execute(
                "SELECT has_function_privilege(%s, %s, 'EXECUTE') AS ok", (role, signature)
            ).fetchone()
            return bool(row and row["ok"])

        assert not can_execute("xcode_app", stale)
        assert not can_execute("xcode_operator", stale)
        assert can_execute("xcode_app", current)
        assert can_execute("xcode_operator", current)
        assert not [r for r in run_checks(conn) if not r.ok]
    finally:
        conn.close()


def test_crlf_and_lf_produce_the_same_checksum() -> None:
    lf = b"CREATE OR REPLACE FUNCTION api.x()\nRETURNS int AS 'SELECT 1';\n"
    crlf = lf.replace(b"\n", b"\r\n")
    assert checksum_bytes(lf) == checksum_bytes(crlf)


def test_dry_run_changes_nothing(fresh_owner_url: str) -> None:
    runner, conn = _runner(fresh_owner_url)
    try:
        with advisory_lock(conn):
            pending = runner.migrate(dry_run=True)
            assert 1 in pending
            rows = conn.execute("SELECT count(*) AS n FROM ops.schema_migrations").fetchall()
        assert rows[0]["n"] == 0
    finally:
        conn.close()


def _waits_on_an_advisory_lock(observer: psycopg.Connection[dict[str, object]], pid: int) -> bool:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        row = observer.execute(
            "SELECT count(*) AS n FROM pg_locks "
            "WHERE pid = %s AND locktype = 'advisory' AND NOT granted",
            (pid,),
        ).fetchone()
        if row is not None and row["n"]:
            return True
        threading.Event().wait(0.05)
    return False


def test_concurrent_runners_serialize(fresh_owner_url: str) -> None:
    first_runner, first_conn = _runner(fresh_owner_url)
    second_runner, second_conn = _runner(fresh_owner_url)
    observer = open_owner_connection(fresh_owner_url)
    second_applied: list[list[int]] = []
    errors: list[BaseException] = []

    def second() -> None:
        try:
            with advisory_lock(second_conn):
                second_applied.append(second_runner.migrate())
        except BaseException as exc:  # surfaced by the assertions below
            errors.append(exc)

    worker = threading.Thread(target=second)
    try:
        with advisory_lock(first_conn):
            worker.start()
            second_waited = _waits_on_an_advisory_lock(observer, second_conn.info.backend_pid)
            first_applied = first_runner.migrate()
        worker.join(timeout=60)
    finally:
        worker.join(timeout=60)
        for conn in (first_conn, second_conn, observer):
            conn.close()

    assert second_waited, "the second runner did not wait for the first one's lock"
    assert not errors, errors
    assert 1 in first_applied
    assert second_applied == [[]]


def test_database_without_schemas_is_refused_with_guidance(
    harness: Harness, worker_id: str
) -> None:
    name = f"bare_{worker_id}_{secrets.token_hex(6)}"
    with psycopg.connect(harness.admin_url, autocommit=True, row_factory=dict_row) as admin:
        admin.execute(f"CREATE DATABASE {name} OWNER xcode_owner")
    try:
        runner, conn = _runner(_with_role(harness.admin_url, "xcode_owner", "xcode_owner", name))
        try:
            with advisory_lock(conn), pytest.raises(MigrationError) as exc:
                runner.migrate()
            assert "schema(s) missing" in str(exc.value)
            assert "020_schemas.sql" in str(exc.value)
        finally:
            conn.close()
    finally:
        harness.drop_test_database(name)


def test_down_file_exists_for_every_migration() -> None:
    migrations = find_db_dir() / "migrations"
    for up in migrations.glob("*.sql"):
        if up.name.endswith(".down.sql"):
            continue
        down = Path(str(up)[:-4] + ".down.sql")
        assert down.is_file(), f"missing down file for {up.name}"


_PEOPLE = [
    ("Owner", [("bills.view", False)]),
    ("Office admin", [("access.manage", True), ("reports.export", False)]),
    ("Fleet manager", [("pettycash.spend", False), ("invest.view", True)]),
    ("Revenue clerk", [("reports.export", True), ("revenue.no_earnings", False)]),
    ("Revenue clerk", []),
]


def _seed_people_before_the_catalogue(
    conn: psycopg.Connection[dict[str, object]],
) -> list[tuple[str, object, object]]:
    org = conn.execute(
        "INSERT INTO tenancy.organizations (slug, name) VALUES ('grants', 'Grants') RETURNING id"
    ).fetchone()
    assert org is not None
    roles = {}
    for name in ("Owner", "Office admin", "Fleet manager", "Revenue clerk"):
        row = conn.execute(
            "INSERT INTO tenancy.roles (organization_id, name) VALUES (%s, %s) RETURNING id",
            (org["id"], name),
        ).fetchone()
        assert row is not None
        roles[name] = row["id"]
    people = []
    for slot, (role, overrides) in enumerate(_PEOPLE):
        user = conn.execute(
            "INSERT INTO identity.users (email, phone_number) VALUES (%s, %s) RETURNING id",
            (f"person{slot}@example.com", f"+25472200{slot:04d}"),
        ).fetchone()
        assert user is not None
        conn.execute(
            "INSERT INTO tenancy.memberships (organization_id, user_id, first_name, last_name) "
            "VALUES (%s, %s, 'Person', %s)",
            (org["id"], user["id"], f"Number {slot}"),
        )
        conn.execute(
            "INSERT INTO tenancy.person_roles (organization_id, user_id, role_id) "
            "VALUES (%s, %s, %s)",
            (org["id"], user["id"], roles[role]),
        )
        for permission, granted in overrides:
            conn.execute(
                "INSERT INTO tenancy.permission_overrides "
                "(organization_id, user_id, permission, granted) VALUES (%s, %s, %s, %s)",
                (org["id"], user["id"], permission, granted),
            )
        people.append((role, org["id"], user["id"]))
    return people


def _permissions(
    conn: psycopg.Connection[dict[str, object]], function: str, org: object, user: object
) -> set[str]:
    with conn.transaction():
        conn.execute("SELECT set_config('xcode.organization_id', %s, true)", (str(org),))
        row = conn.execute(f"SELECT tenancy.{function}(%s, %s) AS p", (org, user)).fetchone()
    assert row is not None
    return set(row["p"])  # type: ignore[call-overload]


def test_the_grant_translation_keeps_what_each_person_could_do(fresh_owner_url: str) -> None:
    catalogue = json.loads(
        (
            Path(__file__).resolve().parent.parent / "support" / "permission_catalogue.json"
        ).read_text(encoding="utf-8")
    )
    translations: dict[str, list[str]] = catalogue["translations"]
    sources = {item["key"]: set(item["sources"]) for item in catalogue["retired"]}
    rights = [item["key"] for group in catalogue["groups"] for item in group["items"]]
    runner, conn = _runner(fresh_owner_url)
    try:
        with advisory_lock(conn):
            runner.migrate(to=8)
            people = _seed_people_before_the_catalogue(conn)
            resolver = find_db_dir() / "routines" / "30_tenancy" / "assigned_permissions.sql"
            conn.execute(resolver.read_text(encoding="utf-8"))  # type: ignore[arg-type]
            before = [
                _permissions(conn, "assigned_permissions", org, user) for _, org, user in people
            ]
            runner.migrate()
            after = [
                _permissions(conn, "effective_permissions", org, user) for _, org, user in people
            ]
            granted_legacy = conn.execute(
                "SELECT count(*) AS n FROM tenancy.permission_overrides o "
                "JOIN tenancy.permissions p ON p.key = o.permission WHERE NOT p.catalogue"
            ).fetchone()
    finally:
        conn.close()
    assert granted_legacy == {"n": 0}
    for (role, _, _), old, new in zip(people, before, after, strict=True):
        for key in old:
            assert set(translations[key]) <= new, (role, key)
            if sources.get(key):
                assert key in new, (role, key)
        if role == "Owner":
            assert set(rights) | {"organization.manage"} <= new
    clerk_old, clerk_new = before[3], after[3]
    assert "reports.export" in clerk_old and "revenue.no_earnings" not in clerk_old
    assert {"reports.view", "reports.export", "revenue.export", "pettycash.export"} <= clerk_new
    fleet_old, fleet_new = before[2], after[2]
    assert "pettycash.spend" not in fleet_old
    assert not {"pettycash.spend", "pettycash.edit_own"} & fleet_new
    assert {"reports.investment", "vehicles.view", "invest.view"} <= fleet_new
    assert {"scheduled.view", "savings.view", "commitments.view"} <= fleet_new
    office_new = after[1]
    assert {
        f"{kind}.{right}"
        for kind in ("scheduled", "savings")
        for right in ("view", "add", "edit", "pause")
    } <= office_new
    assert {"people.edit", "access.manage"} <= office_new


def _seed_setup_before_target_sets(
    conn: psycopg.Connection[dict[str, object]],
) -> dict[str, object]:
    def one(statement: str, *params: object) -> object:
        row = conn.execute(statement, params).fetchone()  # type: ignore[arg-type]
        assert row is not None
        return row["id"]

    ids: dict[str, object] = {}
    for slug in ("split-a", "split-b"):
        ids[slug] = one(
            "INSERT INTO tenancy.organizations (slug, name) VALUES (%s, %s) RETURNING id",
            slug,
            slug.title(),
        )
    org, other = ids["split-a"], ids["split-b"]
    company = one(
        "INSERT INTO setup.psv_companies (organization_id, name) VALUES (%s, 'North') RETURNING id",
        org,
    )
    for registration in ("KDA 482M", "KDB 111A"):
        ids[registration] = one(
            "INSERT INTO setup.fleet_vehicles (organization_id, company_id, registration, "
            "joined_on) VALUES (%s, %s, %s, DATE '2026-01-05') RETURNING id",
            org,
            company,
            registration,
        )
    for registration, revision, starts, weekly in [
        ("KDA 482M", 1, "2026-01-05", "7000"),
        ("KDA 482M", 2, "2026-02-02", "9000"),
        ("KDA 482M", 3, "2026-02-02", "14000.50"),
        ("KDA 482M", 4, "2026-03-02", "10"),
        ("KDB 111A", 1, "2026-01-05", "0.05"),
        ("KDB 111A", 2, "2026-02-02", "0.07"),
    ]:
        conn.execute(
            "INSERT INTO setup.vehicle_targets (organization_id, vehicle_id, revision, "
            "effective_from, weekly_amount) VALUES (%s, %s, %s, %s, %s)",
            (org, ids[registration], revision, starts, weekly),
        )
    for owner, name, bucket in [
        (org, "Insurance", 2),
        (org, "Parking", 2),
        (org, "Bank loan", 3),
        (other, "Tyres", 1),
    ]:
        conn.execute(
            "INSERT INTO setup.expense_categories (organization_id, name, bucket) "
            "VALUES (%s, %s, %s)",
            (owner, name, bucket),
        )
    return ids


def test_the_setup_migration_splits_weekly_targets_and_groups_categories_by_bucket(
    fresh_owner_url: str,
) -> None:
    runner, conn = _runner(fresh_owner_url)
    notices: list[str] = []
    conn.add_notice_handler(lambda notice: notices.append(notice.message_primary or ""))
    try:
        with advisory_lock(conn):
            runner.migrate(to=9)
            ids = _seed_setup_before_target_sets(conn)
            runner.migrate(to=10)
            sets = conn.execute(
                "SELECT vehicle_id, starts_on::text AS starts, ARRAY[monday, tuesday, wednesday, "
                "thursday, friday, saturday, sunday]::text[] AS days, created_by "
                "FROM setup.vehicle_target_sets ORDER BY vehicle_id = %s DESC, starts_on",
                (ids["KDA 482M"],),
            ).fetchall()
            groups = conn.execute(
                "SELECT c.organization_id, c.name, m.name AS main, m.id AS main_id "
                "FROM setup.expense_categories AS c "
                "LEFT JOIN setup.expense_main_categories AS m "
                "ON m.organization_id = c.organization_id AND m.id = c.main_category_id "
                "ORDER BY c.name"
            ).fetchall()
            mains = conn.execute(
                "SELECT count(*) AS n FROM setup.expense_main_categories"
            ).fetchone()
    finally:
        conn.close()
    kda, kdb = ids["KDA 482M"], ids["KDB 111A"]
    assert [(s["vehicle_id"], s["starts"], s["days"], s["created_by"]) for s in sets] == [
        (kda, "2026-01-05", ["1000.00"] * 7, None),
        (kda, "2026-02-02", ["2000.07"] * 6 + ["2000.08"], None),
        (kda, "2026-03-02", ["1.43"] * 6 + ["1.42"], None),
        (kdb, "2026-02-02", ["0.01"] * 7, None),
    ]
    org, other = ids["split-a"], ids["split-b"]
    assert [(g["organization_id"], g["name"], g["main"]) for g in groups] == [
        (org, "Bank loan", "Loan repayments"),
        (org, "Insurance", "Recurring charges"),
        (org, "Parking", "Recurring charges"),
        (other, "Tyres", "Repairs and maintenance"),
    ]
    assert groups[1]["main_id"] == groups[2]["main_id"]
    assert mains == {"n": 3}
    assert (
        "setup.vehicle_target_sets: 4 sets from 5 dated weekly targets; 1 too small to split, "
        "left for the owner; setup.expense_main_categories: 3 made for 4 categories"
    ) in notices
