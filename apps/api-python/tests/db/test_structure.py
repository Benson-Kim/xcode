"""Structural assertions as xcode_owner (``docs/03-database.md`` sections 2, 3, 7, 9).

The same checks back ``xcode-api db verify``; here each one is a named assertion, plus
negative tests that create a violating object and prove the matching check reports it.
"""

from __future__ import annotations

import secrets

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.rows import dict_row

from xcode_api.db.verify import CheckResult, row_security_failures, run_checks

from ..support.database import Harness

pytestmark = pytest.mark.structure


def _by_name(results: list[CheckResult]) -> dict[str, CheckResult]:
    return {r.name: r for r in results}


def test_every_structure_check_passes_on_a_clean_template(
    owner_conn: psycopg.Connection[dict[str, object]],
) -> None:
    results = run_checks(owner_conn)
    failed = [r for r in results if not r.ok]
    assert not failed, [(r.name, r.failures) for r in failed]


def test_api_routines_are_security_definer_owned_by_executor(
    owner_conn: psycopg.Connection[dict[str, object]],
) -> None:
    rows = owner_conn.execute(
        """
        SELECT p.proname AS name, p.prosecdef AS secdef,
               pg_get_userbyid(p.proowner) AS owner
        FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = 'api'
        """
    ).fetchall()
    assert rows, "no api routines found"
    for r in rows:
        assert r["secdef"], f"api.{r['name']} is not SECURITY DEFINER"
        assert r["owner"] == "xcode_api_executor", f"api.{r['name']} owner is {r['owner']}"


def test_app_has_no_table_privileges_anywhere(
    owner_conn: psycopg.Connection[dict[str, object]],
) -> None:
    rows = owner_conn.execute(
        "SELECT count(*) AS n FROM information_schema.role_table_grants WHERE grantee = 'xcode_app'"
    ).fetchall()
    assert rows[0]["n"] == 0


_NO_DATA_PRIVILEGES = "xcode_app/xcode_operator have no table or sequence privileges"


def test_verify_reports_a_column_grant_to_the_app_role(
    owner_conn: psycopg.Connection[dict[str, object]],
) -> None:
    owner_conn.execute("GRANT USAGE ON SCHEMA identity TO xcode_app")
    owner_conn.execute("GRANT SELECT (pin_hash) ON identity.users TO xcode_app")
    try:
        result = _by_name(run_checks(owner_conn))[_NO_DATA_PRIVILEGES]
        assert not result.ok
        assert any(
            "xcode_app" in f and "identity.users" in f and "pin_hash" in f for f in result.failures
        ), result.failures
        assert any("xcode_app" in f and "schema identity" in f for f in result.failures)
    finally:
        owner_conn.execute("REVOKE SELECT (pin_hash) ON identity.users FROM xcode_app")
        owner_conn.execute("REVOKE USAGE ON SCHEMA identity FROM xcode_app")


def test_verify_reports_data_schema_usage_for_the_operator(
    owner_conn: psycopg.Connection[dict[str, object]],
) -> None:
    owner_conn.execute("GRANT USAGE ON SCHEMA tenancy TO xcode_operator")
    try:
        result = _by_name(run_checks(owner_conn))[_NO_DATA_PRIVILEGES]
        assert not result.ok
        assert any("xcode_operator" in f and "schema tenancy" in f for f in result.failures)
    finally:
        owner_conn.execute("REVOKE USAGE ON SCHEMA tenancy FROM xcode_operator")


def test_app_cannot_execute_ops_routines(
    owner_conn: psycopg.Connection[dict[str, object]],
) -> None:
    result = _by_name(run_checks(owner_conn))["xcode_app cannot execute api.ops_*"]
    assert result.ok, result.failures


def test_verify_reports_a_security_invoker_routine_in_api(
    owner_conn: psycopg.Connection[dict[str, object]],
) -> None:
    owner_conn.execute(
        """
        CREATE FUNCTION api._bad_invoker() RETURNS integer
        LANGUAGE sql SECURITY INVOKER AS 'SELECT 1'
        """
    )
    try:
        result = _by_name(run_checks(owner_conn))["api.* routine properties"]
        assert not result.ok
        assert any("_bad_invoker" in f for f in result.failures)
    finally:
        owner_conn.execute("DROP FUNCTION api._bad_invoker()")


def test_verify_reports_dynamic_sql_in_a_helper_schema(
    owner_conn: psycopg.Connection[dict[str, object]],
) -> None:
    owner_conn.execute(
        """
        CREATE FUNCTION tenancy._bad_dynamic(p_name text) RETURNS void
        LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $$
        BEGIN
          EXECUTE format('SELECT %I', p_name);
        END;
        $$
        """
    )
    try:
        result = _by_name(run_checks(owner_conn))["no dynamic SQL in routines"]
        assert result.failures == [
            "tenancy._bad_dynamic body contains EXECUTE or format( and is not allow-listed"
        ]
    finally:
        owner_conn.execute("DROP FUNCTION tenancy._bad_dynamic(text)")


def test_verify_reports_a_tenant_routine_that_skips_enter_organization(
    owner_conn: psycopg.Connection[dict[str, object]],
) -> None:
    owner_conn.execute(
        """
        CREATE FUNCTION api._bad_tenant_read(
          p_actor_id uuid, p_organization_id uuid, p_request_id text, p_now timestamptz
        ) RETURNS integer
        LANGUAGE sql SECURITY DEFINER SET search_path = pg_catalog, pg_temp
        AS 'SELECT count(*)::integer FROM tenancy.memberships'
        """
    )
    owner_conn.execute(
        """
        CREATE FUNCTION api._good_tenant_read(
          p_actor_id uuid, p_organization_id uuid, p_request_id text, p_now timestamptz
        ) RETURNS integer
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
        BEGIN
          PERFORM tenancy.enter_organization(p_actor_id, p_organization_id, p_request_id);
          RETURN (SELECT count(*)::integer FROM tenancy.memberships);
        END;
        $$
        """
    )
    try:
        result = _by_name(run_checks(owner_conn))["tenant routines enter their organization"]
        assert result.failures == [
            "api._bad_tenant_read takes p_organization_id but never calls "
            "tenancy.enter_organization"
        ]
    finally:
        owner_conn.execute(
            "DROP FUNCTION api._bad_tenant_read(uuid, uuid, text, timestamptz), "
            "api._good_tenant_read(uuid, uuid, text, timestamptz)"
        )


def test_verify_reports_a_secret_named_column(
    owner_conn: psycopg.Connection[dict[str, object]],
) -> None:
    owner_conn.execute("CREATE TABLE ops._bad_secret (id int, token text)")
    try:
        result = _by_name(run_checks(owner_conn))["no secret-named columns without _hash/_digest"]
        assert not result.ok
        assert any("token" in f for f in result.failures)
    finally:
        owner_conn.execute("DROP TABLE ops._bad_secret")


def test_verify_reports_a_missing_schema(
    owner_conn: psycopg.Connection[dict[str, object]],
) -> None:
    owner_conn.execute("ALTER SCHEMA pettycash RENAME TO pettycash_moved")
    try:
        result = _by_name(run_checks(owner_conn))["schemas exist"]
        assert not result.ok
        assert any("pettycash" in f for f in result.failures)
    finally:
        owner_conn.execute("ALTER SCHEMA pettycash_moved RENAME TO pettycash")


def test_verify_reports_a_tenant_table_without_a_policy(
    owner_conn: psycopg.Connection[dict[str, object]],
) -> None:
    owner_conn.execute("CREATE TABLE tenancy._bad_tenant (id int, organization_id uuid NOT NULL)")
    try:
        result = _by_name(run_checks(owner_conn))[
            "tenant tables have RLS and the tenant_isolation policy"
        ]
        assert not result.ok
        assert any("_bad_tenant" in f for f in result.failures)
    finally:
        owner_conn.execute("DROP TABLE tenancy._bad_tenant")


def test_verify_reports_a_service_role_without_its_timeouts(
    harness: Harness, owner_url: str
) -> None:
    """The setting is scoped to this test database, which the fixture drops afterwards."""
    dbname = conninfo_to_dict(owner_url)["dbname"]
    admin_url = make_conninfo(harness.admin_url, dbname=dbname)
    with psycopg.connect(admin_url, autocommit=True, row_factory=dict_row) as admin:
        is_superuser = admin.execute(
            "SELECT rolsuper FROM pg_roles WHERE rolname = current_user"
        ).fetchone()
        if not (is_superuser and is_superuser["rolsuper"]):
            pytest.skip("setting another role's parameters needs a superuser")
        db = sql.Identifier(str(dbname))
        admin.execute(
            sql.SQL("ALTER ROLE xcode_app IN DATABASE {} SET statement_timeout = 0").format(db)
        )
        admin.execute(
            sql.SQL("ALTER ROLE xcode_operator IN DATABASE {} SET lock_timeout = '0s'").format(db)
        )
        try:
            result = _by_name(run_checks(admin))[
                "role attributes (connlimit, timeouts, not bypassrls)"
            ]
        finally:
            admin.execute(sql.SQL("ALTER ROLE xcode_app IN DATABASE {} RESET ALL").format(db))
            admin.execute(sql.SQL("ALTER ROLE xcode_operator IN DATABASE {} RESET ALL").format(db))
    assert not result.ok
    assert any("xcode_app" in f and "statement_timeout" in f for f in result.failures), (
        result.failures
    )
    assert any("xcode_operator" in f and "lock_timeout" in f for f in result.failures)
    assert not any("idle_in_transaction" in f for f in result.failures), result.failures


def test_verify_reports_a_service_role_that_row_security_does_not_bind(
    harness: Harness, owner_url: str
) -> None:
    """Roles are global to the server, so the probes live in a transaction that is rolled
    back: no other database or test ever sees them."""
    admin_url = make_conninfo(harness.admin_url, dbname=conninfo_to_dict(owner_url)["dbname"])
    suffix = secrets.token_hex(4)
    probes = {name: f"probe_{name}_{suffix}" for name in ("superuser", "bypass", "member", "clean")}
    with psycopg.connect(admin_url, row_factory=dict_row) as admin:
        is_superuser = admin.execute(
            "SELECT rolsuper FROM pg_roles WHERE rolname = current_user"
        ).fetchone()
        if not (is_superuser and is_superuser["rolsuper"]):
            pytest.skip("creating a BYPASSRLS or superuser role needs a superuser")
        try:
            for statement, name in (
                ("CREATE ROLE {} NOLOGIN SUPERUSER", "superuser"),
                ("CREATE ROLE {} NOLOGIN BYPASSRLS", "bypass"),
                ("CREATE ROLE {} NOLOGIN IN ROLE xcode_owner", "member"),
                ("CREATE ROLE {} NOLOGIN", "clean"),
            ):
                admin.execute(sql.SQL(statement).format(sql.Identifier(probes[name])))
            failures = row_security_failures(admin, tuple(probes.values()))
        finally:
            admin.rollback()

    assert any(probes["superuser"] in f and "superuser" in f for f in failures), failures
    assert any(probes["bypass"] in f and "BYPASSRLS" in f for f in failures), failures
    assert any(probes["member"] in f and "acts as xcode_owner" in f for f in failures), failures
    assert not any(probes["clean"] in f for f in failures), failures
