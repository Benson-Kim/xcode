"""The table-by-table checks of ``docs/04-schema.md`` through ``db/verify.py`` (the module
``xcode-api db verify`` runs), as xcode_owner on a database cloned from the template.

Each check passes on the migrated schema, and each negative test breaks one object and
proves the matching check names it.
"""

from __future__ import annotations

from typing import Any

import psycopg
import pytest

from xcode_api.db.schema_spec import TABLES, TableKind
from xcode_api.db.verify import CheckResult, run_checks

pytestmark = pytest.mark.structure

Conn = psycopg.Connection[dict[str, Any]]

SCHEMA_CHECKS = (
    "declared tables exist with their primary keys",
    "tenant tables have RLS and the tenant_isolation policy",
    "declared indexes exist",
    "table privileges match the declared writes",
    "updated_at columns are touched by trigger",
    "tenant foreign keys start with organization_id",
    "code tables match the domain enums",
    "no secret-named columns without _hash/_digest",
    "audit tables are append-only for the executor",
    "xcode_readonly is locked out of identity and secret columns",
    "extensions within the allow-list",
    "public schema is empty",
    "xcode_app/xcode_operator have no table or sequence privileges",
)


def _check(conn: Conn, name: str) -> CheckResult:
    return {r.name: r for r in run_checks(conn)}[name]


@pytest.mark.parametrize("name", SCHEMA_CHECKS)
def test_schema_check_passes_on_the_migrated_schema(owner_conn: Conn, name: str) -> None:
    result = _check(owner_conn, name)
    assert result.ok, result.failures


def test_every_declared_table_exists(owner_conn: Conn) -> None:
    rows = owner_conn.execute(
        "SELECT schemaname || '.' || tablename AS qualified FROM pg_tables "
        "WHERE schemaname IN ('identity', 'tenancy', 'setup', 'revenue', 'pettycash')"
    ).fetchall()
    assert {r["qualified"] for r in rows} == {t.qualified for t in TABLES}
    assert len(TABLES) == 45


def test_tenant_tables_are_exactly_those_with_an_organization(owner_conn: Conn) -> None:
    rows = owner_conn.execute(
        "SELECT table_schema || '.' || table_name AS qualified FROM information_schema.columns "
        "WHERE column_name = 'organization_id' "
        "AND table_schema IN ('identity', 'tenancy', 'setup', 'revenue', 'pettycash')"
    ).fetchall()
    with_column = {r["qualified"] for r in rows}
    declared = {t.qualified for t in TABLES if t.tenant}
    assert declared == with_column | {"tenancy.organizations"}


def test_readonly_reads_only_code_tables_and_the_catalogue(owner_conn: Conn) -> None:
    rows = owner_conn.execute(
        "SELECT table_schema || '.' || table_name AS qualified, privilege_type "
        "FROM information_schema.role_table_grants WHERE grantee = 'xcode_readonly'"
    ).fetchall()
    readable = {t.qualified for t in TABLES if t.kind in (TableKind.CODE, TableKind.CATALOGUE)}
    assert {r["qualified"] for r in rows} == readable
    assert {r["privilege_type"] for r in rows} == {"SELECT"}


def test_verify_reports_readonly_usage_on_identity(owner_conn: Conn) -> None:
    owner_conn.execute("GRANT USAGE ON SCHEMA identity TO xcode_readonly")
    result = _check(owner_conn, "xcode_readonly is locked out of identity and secret columns")
    assert result.failures == ["xcode_readonly has USAGE on schema identity (expected none)"]


def test_btree_gist_lives_outside_public(owner_conn: Conn) -> None:
    row = owner_conn.execute(
        "SELECT extnamespace::regnamespace::text AS schema_name FROM pg_extension "
        "WHERE extname = 'btree_gist'"
    ).fetchone()
    assert row is not None
    assert row["schema_name"] == "ops"


def test_verify_reports_a_dropped_index(owner_conn: Conn) -> None:
    owner_conn.execute("DROP INDEX revenue.ix_records_business_date")
    result = _check(owner_conn, "declared indexes exist")
    assert not result.ok
    assert result.failures == [
        "index missing: revenue.records USING btree (organization_id, business_date)"
    ]


def test_verify_reports_a_dropped_partial_unique_index(owner_conn: Conn) -> None:
    owner_conn.execute("DROP INDEX tenancy.uq_memberships_active_user")
    owner_conn.execute(
        "CREATE UNIQUE INDEX uq_memberships_any_user ON tenancy.memberships (user_id)"
    )
    result = _check(owner_conn, "declared indexes exist")
    assert result.failures == [
        "index missing: UNIQUE tenancy.memberships USING btree (user_id) WHERE active"
    ]


def test_verify_reports_disabled_rls(owner_conn: Conn) -> None:
    owner_conn.execute("ALTER TABLE setup.fleet_vehicles DISABLE ROW LEVEL SECURITY")
    result = _check(owner_conn, "tenant tables have RLS and the tenant_isolation policy")
    assert result.failures == ["setup.fleet_vehicles is a tenant table but RLS is not enabled"]


def test_verify_reports_rls_disabled_on_organizations(owner_conn: Conn) -> None:
    owner_conn.execute("ALTER TABLE tenancy.organizations DISABLE ROW LEVEL SECURITY")
    result = _check(owner_conn, "tenant tables have RLS and the tenant_isolation policy")
    assert result.failures == ["tenancy.organizations is a tenant table but RLS is not enabled"]


def test_verify_reports_a_second_policy(owner_conn: Conn) -> None:
    owner_conn.execute("CREATE POLICY open_read ON revenue.records FOR SELECT USING (true)")
    result = _check(owner_conn, "tenant tables have RLS and the tenant_isolation policy")
    assert result.failures == [
        "revenue.records must carry exactly the tenant_isolation policy, "
        "has ['open_read', 'tenant_isolation']"
    ]


def test_verify_reports_a_policy_with_the_wrong_expression(owner_conn: Conn) -> None:
    owner_conn.execute(
        "ALTER POLICY tenant_isolation ON setup.psv_companies USING (true) "
        "WITH CHECK (organization_id = tenancy.current_organization())"
    )
    result = _check(owner_conn, "tenant tables have RLS and the tenant_isolation policy")
    assert result.failures == ["setup.psv_companies.tenant_isolation qual is 'true'"]


def test_verify_reports_a_policy_for_another_role(owner_conn: Conn) -> None:
    owner_conn.execute("ALTER POLICY tenant_isolation ON tenancy.memberships TO PUBLIC")
    result = _check(owner_conn, "tenant tables have RLS and the tenant_isolation policy")
    assert result.failures == ["tenancy.memberships.tenant_isolation applies to ['public']"]


def test_verify_reports_rls_on_a_code_table(owner_conn: Conn) -> None:
    owner_conn.execute("ALTER TABLE setup.expense_buckets ENABLE ROW LEVEL SECURITY")
    result = _check(owner_conn, "tenant tables have RLS and the tenant_isolation policy")
    assert result.failures == ["setup.expense_buckets is not a tenant table but has RLS enabled"]


def test_verify_reports_an_extra_write_privilege(owner_conn: Conn) -> None:
    owner_conn.execute("GRANT DELETE ON setup.fleet_vehicles TO xcode_api_executor")
    result = _check(owner_conn, "table privileges match the declared writes")
    assert result.failures == [
        "xcode_api_executor holds ['DELETE', 'INSERT', 'SELECT', 'UPDATE'] on "
        "setup.fleet_vehicles, expected ['INSERT', 'SELECT', 'UPDATE']"
    ]


def test_verify_reports_a_missing_write_privilege(owner_conn: Conn) -> None:
    owner_conn.execute("REVOKE INSERT ON revenue.records FROM xcode_api_executor")
    result = _check(owner_conn, "table privileges match the declared writes")
    assert result.failures == [
        "xcode_api_executor holds ['SELECT', 'UPDATE'] on revenue.records, "
        "expected ['INSERT', 'SELECT', 'UPDATE']"
    ]


def test_verify_reports_a_readonly_grant_on_a_data_table(owner_conn: Conn) -> None:
    owner_conn.execute("GRANT SELECT ON revenue.records TO xcode_readonly")
    result = _check(owner_conn, "table privileges match the declared writes")
    assert result.failures == ["xcode_readonly holds ['SELECT'] on revenue.records, expected []"]


def test_verify_reports_a_public_grant(owner_conn: Conn) -> None:
    owner_conn.execute("GRANT SELECT ON setup.recurring_kinds TO PUBLIC")
    result = _check(owner_conn, "table privileges match the declared writes")
    assert result.failures == ["PUBLIC holds ['SELECT'] on setup.recurring_kinds (expected none)"]


def test_verify_reports_an_update_grant_on_an_audit_table(owner_conn: Conn) -> None:
    owner_conn.execute("GRANT UPDATE ON tenancy.audit_events TO xcode_api_executor")
    result = _check(owner_conn, "audit tables are append-only for the executor")
    assert result.failures == [
        "audit table tenancy.audit_events grants UPDATE to xcode_api_executor"
    ]


def test_verify_reports_an_undeclared_table(owner_conn: Conn) -> None:
    owner_conn.execute("CREATE TABLE setup.stray (id int PRIMARY KEY)")
    result = _check(owner_conn, "declared tables exist with their primary keys")
    assert result.failures == ["table setup.stray is not declared in db/schema_spec.py"]


def test_verify_reports_a_changed_primary_key(owner_conn: Conn) -> None:
    owner_conn.execute("ALTER TABLE identity.trusted_devices DROP CONSTRAINT pk_trusted_devices")
    owner_conn.execute("ALTER TABLE identity.trusted_devices ADD PRIMARY KEY (user_id, device_id)")
    result = _check(owner_conn, "declared tables exist with their primary keys")
    assert result.failures == [
        "identity.trusted_devices primary key is ('user_id', 'device_id'), expected ('id',)"
    ]


def test_verify_reports_a_missing_touch_trigger(owner_conn: Conn) -> None:
    owner_conn.execute("DROP TRIGGER touch_updated_at ON setup.recurring_items")
    result = _check(owner_conn, "updated_at columns are touched by trigger")
    assert result.failures == [
        "setup.recurring_items has updated_at but no BEFORE UPDATE ops.touch_updated_at() trigger"
    ]


def test_verify_reports_a_foreign_key_that_skips_the_organization(owner_conn: Conn) -> None:
    owner_conn.execute("ALTER TABLE setup.psv_companies ADD CONSTRAINT uq_psv_id UNIQUE (id)")
    owner_conn.execute(
        "ALTER TABLE setup.fleet_vehicles ADD CONSTRAINT fk_loose_company "
        "FOREIGN KEY (company_id) REFERENCES setup.psv_companies (id)"
    )
    result = _check(owner_conn, "tenant foreign keys start with organization_id")
    assert result.failures == [
        "setup.fleet_vehicles.fk_loose_company does not start with organization_id on both sides"
    ]


def test_verify_reports_a_tenant_table_without_an_organization_key(owner_conn: Conn) -> None:
    owner_conn.execute(
        "ALTER TABLE setup.recurring_items DROP CONSTRAINT fk_recurring_items_organization"
    )
    result = _check(owner_conn, "tenant foreign keys start with organization_id")
    assert result.failures == [
        "setup.recurring_items has no foreign key (organization_id) -> tenancy.organizations"
    ]


def test_verify_reports_a_code_table_that_drifted_from_its_enum(owner_conn: Conn) -> None:
    owner_conn.execute("INSERT INTO revenue.no_earnings_reasons VALUES (5, 'strike', 'Strike')")
    result = _check(owner_conn, "code tables match the domain enums")
    assert not result.ok
    assert result.failures[0].startswith("revenue.no_earnings_reasons holds")


def test_verify_exempts_only_the_code_key_of_code_tables(owner_conn: Conn) -> None:
    owner_conn.execute("ALTER TABLE setup.fleet_vehicles ADD COLUMN code text")
    result = _check(owner_conn, "no secret-named columns without _hash/_digest")
    assert result.failures == [
        "setup.fleet_vehicles.code is a secret-ish name and does not end in _hash or _digest"
    ]


def test_verify_reports_an_extension_outside_the_allow_list(owner_conn: Conn) -> None:
    owner_conn.execute("CREATE EXTENSION IF NOT EXISTS citext WITH SCHEMA ops")
    result = _check(owner_conn, "extensions within the allow-list")
    assert result.failures == ["extension citext is installed but not on the allow-list"]
