"""The rules of ``docs/04-schema.md`` section 7 that the schema enforces on any path.

As xcode_owner on rows seeded for two organizations (``tests/support/rows.py``). Every CHECK,
unique constraint, exclusion constraint, foreign key and trigger has a statement that must
fail, asserted by SQLSTATE and constraint name (or, for triggers, the code in ``MESSAGE``);
completeness tests fail when a constraint is added without a case. Each case runs in its own
rolled-back transaction, so one seeded database serves all cases of a test.
"""

from __future__ import annotations

import json
import math
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import psycopg
import pytest
from psycopg import sql

from ..support.rows import OrganizationRows, seed_organization

pytestmark = pytest.mark.structure

Conn = psycopg.Connection[dict[str, Any]]

SCHEMAS = ["identity", "tenancy", "setup", "revenue", "pettycash", "expenses"]


@dataclass(frozen=True, slots=True)
class Case:
    constraint: str
    statement: str


@dataclass(frozen=True, slots=True)
class Seeded:
    conn: Conn
    a: OrganizationRows
    b: OrganizationRows

    def params(self) -> dict[str, Any]:
        return {**self.a.params(), **{f"b_{k}": v for k, v in self.b.params().items()}}


@pytest.fixture
def seeded(owner_conn: Conn) -> Seeded:
    return Seeded(owner_conn, seed_organization(owner_conn), seed_organization(owner_conn))


def _failure(conn: Conn, statement: str | sql.Composed, params: dict[str, Any]) -> psycopg.Error:
    try:
        with conn.transaction(force_rollback=True):
            conn.execute(statement, params)  # type: ignore[arg-type]
            conn.execute("SET CONSTRAINTS ALL IMMEDIATE")
    except psycopg.Error as exc:
        return exc
    raise AssertionError(f"statement succeeded: {statement!r}")


def _run(seeded: Seeded, cases: list[Case], sqlstate: str) -> list[str]:
    mismatches: list[str] = []
    for case in cases:
        try:
            exc = _failure(seeded.conn, case.statement, seeded.params())
        except AssertionError as missing:
            mismatches.append(f"{case.constraint}: {missing}")
            continue
        got = (exc.sqlstate, exc.diag.constraint_name)
        if got != (sqlstate, case.constraint):
            mismatches.append(f"{case.constraint}: got {got}, {exc.diag.message_primary}")
    return mismatches


def _passes(seeded: Seeded, statements: list[str]) -> list[str]:
    failures: list[str] = []
    for statement in statements:
        try:
            with seeded.conn.transaction(force_rollback=True):
                seeded.conn.execute(statement, seeded.params())  # type: ignore[arg-type]
                seeded.conn.execute("SET CONSTRAINTS ALL IMMEDIATE")
        except psycopg.Error as exc:
            failures.append(f"{statement}: {exc.sqlstate} {exc.diag.message_primary}")
    return failures


def _constraint_names(conn: Conn, contype: str) -> set[str]:
    rows = conn.execute(
        "SELECT conname FROM pg_constraint WHERE contype = %s "
        "AND connamespace::regnamespace::text = ANY(%s)",
        (contype, SCHEMAS),
    ).fetchall()
    return {r["conname"] for r in rows}


# --- CHECK constraints (23514) --------------------------------------------------------

_USER = "UPDATE identity.users SET {} WHERE id = %(user)s"
_CODE = "UPDATE identity.verification_codes SET {} WHERE id = %(code)s"
_ATTEMPT = "UPDATE identity.sign_in_attempts SET {} WHERE user_id = %(user)s"
_ORG = "UPDATE tenancy.organizations SET {} WHERE id = %(org)s"
_MEMBER = "UPDATE tenancy.memberships SET {} WHERE organization_id = %(org)s AND user_id = %(user)s"
_LOCAL = "UPDATE tenancy.organization_localizations SET {} WHERE organization_id = %(org)s"
_BRAND = "UPDATE tenancy.organization_brandings SET {} WHERE organization_id = %(org)s"
_LOGO = "UPDATE tenancy.organization_logos SET {} WHERE organization_id = %(org)s"
_POLICY = "UPDATE tenancy.organization_security_policies SET {} WHERE organization_id = %(org)s"
_PREFS = "UPDATE tenancy.user_preferences SET {} WHERE organization_id = %(org)s"
_LOG = "UPDATE tenancy.change_log SET {} WHERE organization_id = %(org)s"
_AUDIT = "UPDATE tenancy.audit_events SET {} WHERE organization_id = %(org)s"
_VEHICLE = "UPDATE setup.fleet_vehicles SET {} WHERE id = %(vehicle)s"
_TARGET_SET = "UPDATE setup.vehicle_target_sets SET {} WHERE id = %(target_set)s"
_MAIN = "UPDATE setup.expense_main_categories SET {} WHERE id = %(main_category)s"
_VERSION = "UPDATE setup.recurring_versions SET {} WHERE id = %(version)s"
_RECORD = "UPDATE revenue.records SET {} WHERE id = %(record)s"
_ENTRY = "UPDATE pettycash.entries SET {} WHERE id = %(entry)s"
_CENTRAL = "UPDATE expenses.entries SET {} WHERE id = %(central)s"
_SAVING = "UPDATE setup.recurring_versions SET {} WHERE id = %(saving_version)s"
_PAUSE = "UPDATE setup.recurring_pauses SET {} WHERE id = %(pause)s"
_OPENING = "UPDATE setup.saving_opening_amounts SET {} WHERE item_id = %(saving)s"
_RUN = "UPDATE setup.saving_runs SET {} WHERE item_id = %(saving)s"
_GROUP = "group_id = gen_random_uuid(), group_total = {}, group_units = {}, group_unit_amount = {}"
_NO_EXPENSE = (
    "status = NULL, vehicle_id = NULL, expense_item_id = NULL, reviewed_by = NULL, "
    "reviewed_at = NULL"
)
_CREDIT = "kind = 3, " + _NO_EXPENSE
_CASH = "kind = 1, " + _NO_EXPENSE
_PNG_OF = "data = decode('89504e470d0a1a0a', 'hex') || decode(repeat('00', {}), 'hex')"


def _set(template: str, assignment: str) -> str:
    return template.format(assignment)


CHECK_CASES = [
    Case("ck_users_email", _set(_USER, "email = 'Owner@Example.com'")),
    Case("ck_users_phone_number", _set(_USER, "phone_number = '+254812345678'")),
    Case("ck_users_pin_hash", _set(_USER, "pin_hash = 'not a hash'")),
    Case("ck_users_status", _set(_USER, "status = 'deleted'")),
    Case("ck_users_security_version", _set(_USER, "security_version = -1")),
    Case("ck_users_failed_attempts", _set(_USER, "failed_attempts = 6")),
    Case("ck_users_untrusted_failed_attempts", _set(_USER, "untrusted_failed_attempts = -1")),
    Case("ck_verification_codes_purpose", _set(_CODE, "purpose = 'sign_in'")),
    Case("ck_verification_codes_device_id", _set(_CODE, "device_id = ''")),
    Case("ck_verification_codes_code_hash", _set(_CODE, "code_hash = repeat('a', 64)")),
    Case("ck_verification_codes_failed_attempts", _set(_CODE, "failed_attempts = -1")),
    Case(
        "ck_trusted_devices_device_id",
        "UPDATE identity.trusted_devices SET device_id = repeat('d', 129) WHERE id = %(device)s",
    ),
    Case(
        "ck_trusted_devices_token_hash",
        "UPDATE identity.trusted_devices SET token_hash = repeat('a', 64) WHERE id = %(device)s",
    ),
    Case(
        "ck_trusted_devices_name",
        "UPDATE identity.trusted_devices SET name = 'call http://x' WHERE id = %(device)s",
    ),
    Case(
        "ck_trusted_devices_remembered",
        "UPDATE identity.trusted_devices SET remembered = false, token_hash = repeat('A', 64) "
        "WHERE id = %(device)s",
    ),
    Case(
        "ck_refresh_tokens_device_id",
        "UPDATE identity.refresh_tokens SET device_id = '' WHERE id = %(token)s",
    ),
    Case(
        "ck_refresh_tokens_token_hash",
        "UPDATE identity.refresh_tokens SET token_hash = 'ABC' WHERE id = %(token)s",
    ),
    Case("ck_sign_in_attempts_operation", _set(_ATTEMPT, "operation = 'login'")),
    Case("ck_sign_in_attempts_outcome", _set(_ATTEMPT, "outcome = 'silent'")),
    Case("ck_sign_in_attempts_refusal", _set(_ATTEMPT, "refusal = 'invalid_pin'")),
    Case("ck_sign_in_attempts_device_id", _set(_ATTEMPT, "device_id = repeat('d', 129)")),
    Case("ck_sign_in_attempts_request_id", _set(_ATTEMPT, "request_id = repeat('r', 129)")),
    Case("ck_organizations_slug", _set(_ORG, "slug = 'Not A Slug'")),
    Case("ck_organizations_name", _set(_ORG, "name = ''")),
    Case("ck_memberships_first_name", _set(_MEMBER, "first_name = ''")),
    Case("ck_memberships_last_name", _set(_MEMBER, "last_name = repeat('l', 101)")),
    Case("ck_memberships_approval_limit", _set(_MEMBER, "approval_limit = -0.01")),
    Case(
        "ck_memberships_back_limit_mode",
        _set(_MEMBER, "back_limit_mode = 'weeks', back_limit_count = 1"),
    ),
    Case(
        "ck_memberships_back_limit_count",
        _set(_MEMBER, "back_limit_mode = 'months', back_limit_count = 121"),
    ),
    Case("ck_localizations_locale", _set(_LOCAL, "locale = 'en_GB'")),
    Case("ck_localizations_date_pattern", _set(_LOCAL, "date_pattern = 'full'")),
    Case("ck_localizations_first_day_of_week", _set(_LOCAL, "first_day_of_week = 7")),
    Case("ck_localizations_week_numbering", _set(_LOCAL, "week_numbering = 'us'")),
    Case("ck_localizations_currency", _set(_LOCAL, "currency = 'kes'")),
    Case("ck_localizations_number_decimals", _set(_LOCAL, "number_decimals = 3")),
    Case("ck_brandings_display_name", _set(_BRAND, "display_name = ''")),
    Case("ck_brandings_legal_name", _set(_BRAND, "legal_name = repeat('x', 201)")),
    Case("ck_brandings_logo_alt", _set(_BRAND, "logo_alt = ''")),
    Case("ck_brandings_primary_color", _set(_BRAND, "primary_color = 'blue'")),
    Case("ck_brandings_secondary_color", _set(_BRAND, "secondary_color = '#14213'")),
    Case("ck_brandings_accent_color", _set(_BRAND, "accent_color = '#GG6B3A'")),
    Case("ck_brandings_contrast", _set(_BRAND, "accent_color = '#FFFF00'")),
    Case(
        "ck_brandings_logo_light_url", _set(_BRAND, "logo_light_url = 'http://example.com/l.png'")
    ),
    Case("ck_brandings_logo_dark_url", _set(_BRAND, "logo_dark_url = 'ftp://example.com/d.png'")),
    Case(
        "ck_brandings_favicon_url",
        _set(_BRAND, "favicon_url = 'https://' || repeat('a', 2041)"),
    ),
    Case("ck_brandings_terms_url", _set(_BRAND, "terms_url = 'example.com/terms'")),
    Case("ck_brandings_privacy_url", _set(_BRAND, "privacy_url = 'http://example.com'")),
    Case("ck_brandings_domain", _set(_BRAND, "domain = '-bad.example.com'")),
    Case("ck_brandings_support_email", _set(_BRAND, "support_email = 'support.example.com'")),
    Case("ck_logos_content_type", _set(_LOGO, "content_type = 'image/gif'")),
    Case(
        "ck_logos_size",
        _set(_LOGO, _PNG_OF.format(262137)),
    ),
    Case("ck_logos_signature", _set(_LOGO, "data = decode('ffd8ff00', 'hex')")),
    Case("ck_security_policies_password_min_length", _set(_POLICY, "password_min_length = 11")),
    Case("ck_security_policies_password_history", _set(_POLICY, "password_history = 25")),
    Case("ck_security_policies_pin_length", _set(_POLICY, "pin_length = 3")),
    Case("ck_security_policies_lockout_threshold", _set(_POLICY, "lockout_threshold = 11")),
    Case("ck_security_policies_lockout_minutes", _set(_POLICY, "lockout_minutes = 0")),
    Case("ck_security_policies_access_token_minutes", _set(_POLICY, "access_token_minutes = 16")),
    Case("ck_security_policies_refresh_token_days", _set(_POLICY, "refresh_token_days = 91")),
    Case("ck_security_policies_idle_unlock_seconds", _set(_POLICY, "idle_unlock_seconds = 29")),
    Case("ck_security_policies_allow_pin_sign_in", _set(_POLICY, "allow_pin_sign_in = false")),
    Case("ck_user_preferences_locale", _set(_PREFS, "locale = 'e'")),
    Case("ck_user_preferences_theme_mode", _set(_PREFS, "theme_mode = 'sepia'")),
    Case("ck_user_preferences_font_scale", _set(_PREFS, "font_scale = 3.01")),
    Case("ck_change_log_version", _set(_LOG, "version = 0")),
    Case("ck_change_log_section", _set(_LOG, "section = 'settings'")),
    Case("ck_change_log_vehicle", _set(_LOG, "vehicle_id = NULL")),
    Case("ck_change_log_reason", _set(_LOG, "reason = ''")),
    Case("ck_change_log_request_id", _set(_LOG, "request_id = repeat('r', 129)")),
    Case("ck_audit_events_action", _set(_AUDIT, "action = repeat('a', 101)")),
    Case("ck_audit_events_entity", _set(_AUDIT, "entity = repeat('e', 201)")),
    Case("ck_audit_events_request_id", _set(_AUDIT, "request_id = repeat('r', 129)")),
    Case(
        "ck_permissions_key",
        "UPDATE tenancy.permissions SET key = 'Bills.Approve' WHERE key = 'bills.approve'",
    ),
    Case(
        "ck_permissions_section",
        "UPDATE tenancy.permissions SET section = 'Other' WHERE key = 'pettycash.view'",
    ),
    Case(
        "ck_permission_sources_distinct",
        "UPDATE tenancy.permission_sources SET source = permission "
        "WHERE permission = 'access.manage'",
    ),
    Case(
        "ck_permission_dependencies_distinct",
        "UPDATE tenancy.permission_dependencies SET needs = permission "
        "WHERE permission = 'dash.gaps'",
    ),
    Case(
        "ck_role_defaults_role_name",
        "UPDATE tenancy.role_defaults SET role_name = 'Driver' "
        "WHERE role_name = 'Revenue clerk' AND permission = 'dash.gaps'",
    ),
    Case("ck_roles_name", "UPDATE tenancy.roles SET name = '' WHERE id = %(role)s"),
    Case(
        "ck_psv_companies_name",
        "UPDATE setup.psv_companies SET name = ' Metro Trans' WHERE id = %(company)s",
    ),
    Case(
        "ck_fleet_vehicles_registration",
        "INSERT INTO setup.fleet_vehicles (organization_id, company_id, registration, joined_on) "
        "VALUES (%(org)s, %(company)s, 'KDA482M', DATE '2026-01-05')",
    ),
    Case("ck_fleet_vehicles_left_on", _set(_VEHICLE, "left_on = DATE '2026-01-04'")),
    Case("ck_fleet_vehicles_fleet_number", _set(_VEHICLE, "fleet_number = ' MT-01'")),
    Case("ck_fleet_vehicles_fleet_number", _set(_VEHICLE, "fleet_number = ''")),
    Case("ck_fleet_vehicles_fleet_number", _set(_VEHICLE, "fleet_number = repeat('f', 21)")),
    Case("ck_fleet_vehicles_initial_investment", _set(_VEHICLE, "initial_investment = 0")),
    Case("ck_vehicle_target_sets_days", _set(_TARGET_SET, "sunday = 0")),
    Case("ck_vehicle_target_sets_days", _set(_TARGET_SET, "wednesday = -1")),
    Case(
        "ck_vehicle_away_periods_returned_on",
        "UPDATE setup.vehicle_away_periods SET returned_on = left_on WHERE id = %(away)s",
    ),
    Case(
        "ck_vehicle_investments_description",
        "UPDATE setup.vehicle_investments SET description = '' WHERE id = %(investment)s",
    ),
    Case(
        "ck_vehicle_investments_amount",
        "UPDATE setup.vehicle_investments SET amount = -5 WHERE id = %(investment)s",
    ),
    Case("ck_expense_main_categories_name", _set(_MAIN, "name = repeat('m', 101)")),
    Case("ck_expense_main_categories_name", _set(_MAIN, "name = 'Repairs '")),
    Case(
        "ck_expense_categories_name",
        "UPDATE setup.expense_categories SET name = repeat('n', 101) WHERE id = %(category)s",
    ),
    Case(
        "ck_expense_items_name",
        "UPDATE setup.expense_items SET name = 'Cover ' WHERE id = %(item)s",
    ),
    Case("ck_recurring_versions_revision", _set(_VERSION, "revision = 0")),
    Case("ck_recurring_versions_name", _set(_VERSION, "name = ''")),
    Case("ck_recurring_versions_amount", _set(_VERSION, "amount = 0")),
    Case("ck_recurring_versions_end_on", _set(_VERSION, "end_on = DATE '2025-12-31'")),
    Case("ck_recurring_versions_note", _set(_VERSION, "note = repeat('n', 201)")),
    Case("ck_recurring_versions_schedule", _set(_VERSION, "day = 29")),
    Case("ck_recurring_versions_kind", _set(_VERSION, "kind = 2")),
    Case(
        "ck_recurring_allocations_amount",
        "UPDATE setup.recurring_allocations SET amount = 0 WHERE id = %(allocation)s",
    ),
    Case("ck_records_amount", _set(_RECORD, "amount = 0")),
    Case("ck_records_note", _set(_RECORD, "amount = NULL, reason = 4, note = repeat('n', 81)")),
    Case("ck_records_entry", _set(_RECORD, "amount = NULL")),
    Case("ck_records_entry", _set(_RECORD, "note = 'Late'")),
    Case("ck_records_entry", _set(_RECORD, "reason = 1, note = 'Late'")),
    Case(
        "ck_revenue_settings_low_day_threshold",
        "UPDATE tenancy.organization_revenue_settings SET low_day_threshold = -0.01 "
        "WHERE organization_id = %(org)s",
    ),
    Case(
        "ck_revenue_settings_gap_amber_percent",
        "UPDATE tenancy.organization_revenue_settings SET gap_amber_percent = 100.01 "
        "WHERE organization_id = %(org)s",
    ),
    Case("ck_entries_units", _set(_ENTRY, "units = -1")),
    Case("ck_entries_total", _set(_ENTRY, "units = 0.001, unit_amount = 0.01")),
    Case("ck_entries_payee", _set(_ENTRY, _CREDIT + ", payee = ''")),
    Case("ck_entries_note", _set(_ENTRY, "note = repeat('n', 81)")),
    Case(
        "ck_entries_sent_back_note",
        _set(_ENTRY, "status = 1, sent_back_note = repeat('s', 201)"),
    ),
    Case("ck_entries_reject_reason", _set(_ENTRY, "status = 4, reject_reason = ''")),
    Case("ck_entries_reopen_reason", _set(_ENTRY, "reopen_reason = repeat('o', 201)")),
    Case("ck_entries_removal_reason", _set(_ENTRY, "removal_reason = repeat('r', 501)")),
    Case("ck_entries_version", _set(_ENTRY, "version = 0")),
    Case("ck_entries_kind_shape", _set(_ENTRY, "reimbursable = true")),
    Case("ck_entries_kind_shape", _set(_ENTRY, "expense_item_id = NULL")),
    Case(
        "ck_entries_kind_shape",
        _set(
            _ENTRY,
            "kind = 1, status = NULL, expense_item_id = NULL, reviewed_by = NULL, "
            "reviewed_at = NULL",
        ),
    ),
    Case("ck_entries_review", _set(_ENTRY, "reviewed_at = NULL")),
    Case("ck_entries_removal", _set(_ENTRY, "removed_at = NULL")),
    Case("ck_entries_group", _set(_ENTRY, "group_id = gen_random_uuid()")),
    Case("ck_entries_group", _set(_ENTRY, _CASH + ", " + _GROUP.format(900, 2, 450))),
    Case("ck_entries_group_total", _set(_ENTRY, _GROUP.format(0, 2, 450))),
    Case("ck_entries_group_units", _set(_ENTRY, _GROUP.format(900, 0, 450))),
    Case("ck_entries_group_unit_amount", _set(_ENTRY, _GROUP.format(900, 2, 0))),
    Case("ck_entries_units", _set(_CENTRAL, "group_size = 2, units = -1")),
    Case("ck_entries_total", _set(_CENTRAL, "group_size = 2, units = 0.001, unit_amount = 0.01")),
    Case("ck_entries_note", _set(_CENTRAL, "note = ' Front tyres'")),
    Case("ck_entries_note", _set(_CENTRAL, "note = ''")),
    Case("ck_entries_group_size", _set(_CENTRAL, "group_size = 51")),
    Case("ck_entries_group_size", _set(_CENTRAL, "group_size = 0")),
    Case("ck_entries_group_total", _set(_CENTRAL, "group_size = 2, group_total = 0")),
    Case("ck_entries_group_units", _set(_CENTRAL, "group_size = 2, group_units = 0")),
    Case("ck_entries_group_unit_amount", _set(_CENTRAL, "group_size = 2, group_unit_amount = 0")),
    Case("ck_entries_group", _set(_CENTRAL, "group_total = 501")),
    Case("ck_entries_group", _set(_CENTRAL, "units = 3")),
    Case("ck_entries_removal", _set(_CENTRAL, "removed_at = NULL")),
    Case("ck_entries_removal", _set(_CENTRAL, "removal_reason = NULL")),
    Case("ck_entries_removal_reason", _set(_CENTRAL, "removal_reason = repeat('r', 501)")),
    Case("ck_entries_version", _set(_CENTRAL, "version = 0")),
    Case("ck_recurring_pauses_through", _set(_PAUSE, "paused_through = DATE '2026-02-27'")),
    Case("ck_recurring_versions_condition_min", _set(_SAVING, "condition_min = 0")),
    Case("ck_recurring_versions_condition_days", _set(_SAVING, "condition_days = 2")),
    Case("ck_recurring_versions_condition", _set(_SAVING, "condition_days = NULL")),
    Case(
        "ck_recurring_versions_condition", _set(_VERSION, "condition_min = 1, condition_days = 1")
    ),
    Case("ck_saving_opening_amounts_amount", _set(_OPENING, "amount = 0")),
    Case("ck_saving_runs_amount", _set(_RUN, "amount = 0")),
]


def test_every_check_constraint_refuses_a_violating_row(seeded: Seeded) -> None:
    assert _run(seeded, CHECK_CASES, "23514") == []


def test_every_check_constraint_has_a_case(owner_conn: Conn) -> None:
    assert {c.constraint for c in CHECK_CASES} == _constraint_names(owner_conn, "c")


_WEEKLY = "frequency = 2, day = {day}, last_day = {last}, month = {month}"


@pytest.mark.parametrize(
    ("assignment", "valid"),
    [
        (_WEEKLY.format(day=0, last="false", month="NULL"), True),
        (_WEEKLY.format(day=6, last="false", month="NULL"), True),
        (_WEEKLY.format(day=7, last="false", month="NULL"), False),
        (_WEEKLY.format(day="NULL", last="false", month="NULL"), False),
        (_WEEKLY.format(day=3, last="true", month="NULL"), False),
        (_WEEKLY.format(day=3, last="false", month=1), False),
        ("frequency = 3, day = 1, last_day = false, month = NULL", True),
        ("frequency = 3, day = 28, last_day = false, month = NULL", True),
        ("frequency = 3, day = NULL, last_day = true, month = NULL", True),
        ("frequency = 3, day = 29, last_day = false, month = NULL", False),
        ("frequency = 3, day = 0, last_day = false, month = NULL", False),
        ("frequency = 3, day = 15, last_day = true, month = NULL", False),
        ("frequency = 3, day = NULL, last_day = false, month = NULL", False),
        ("frequency = 3, day = 15, last_day = false, month = 6", False),
        ("frequency = 4, day = 15, last_day = false, month = 6", True),
        ("frequency = 4, day = NULL, last_day = true, month = 12", True),
        ("frequency = 4, day = 15, last_day = false, month = NULL", False),
        ("frequency = 4, day = 15, last_day = false, month = 13", False),
        ("frequency = 1, day = NULL, last_day = false, month = NULL", True),
        ("frequency = 1, day = 1, last_day = false, month = NULL", False),
    ],
)
def test_schedule_shape(seeded: Seeded, assignment: str, valid: bool) -> None:
    statement = _set(_VERSION, assignment)
    if valid:
        assert _passes(seeded, [statement]) == []
    else:
        exc = _failure(seeded.conn, statement, seeded.params())
        expected = ("23514", "ck_recurring_versions_schedule")
        assert (exc.sqlstate, exc.diag.constraint_name) == expected


def test_boundary_values_pass(seeded: Seeded) -> None:
    assert (
        _passes(
            seeded,
            [
                _set(_USER, "pin_hash = NULL"),
                _set(_USER, "email = repeat('a', 308) || '@example.com'"),
                _set(_MEMBER, "approval_limit = 0"),
                _set(_MEMBER, "back_limit_mode = 'days', back_limit_count = 0"),
                _set(_MEMBER, "back_limit_mode = 'days', back_limit_count = 3650"),
                _set(
                    _MEMBER,
                    "back_limit_mode = 'months', back_limit_count = 120, "
                    "back_limit_from = '2026-01-01'",
                ),
                _set(_MEMBER, "back_limit_mode = 'none', back_limit_from = '2026-01-01'"),
                _set(_BRAND, "domain = 'Fleet_1.Example.CO.KE.', privacy_url = 'HTTPS://x.ke'"),
                _set(_LOCAL, "first_day_of_week = 0, number_decimals = 0, locale = 'sw-KE'"),
                _set(_BRAND, "primary_color = '#1d5fd6', domain = 'fleet.example.co.ke'"),
                _set(_BRAND, "logo_light_url = 'https://' || repeat('a', 2040)"),
                _set(_LOGO, _PNG_OF.format(262136)),
                _set(_LOGO, "content_type = 'image/jpeg', data = decode('ffd8ff', 'hex')"),
                _set(
                    _LOGO,
                    "content_type = 'image/webp', "
                    "data = decode('52494646000000005745425056503820', 'hex')",
                ),
                _set(_POLICY, "password_min_length = 128, pin_length = 8"),
                _set(_POLICY, "idle_unlock_seconds = 3600, lockout_threshold = 3"),
                _set(_PREFS, "font_scale = 3, theme_mode = NULL, locale = NULL"),
                _set(_LOG, "section = 'people', vehicle_id = NULL"),
                _set(_VEHICLE, "left_on = joined_on"),
                _set(_VEHICLE, "fleet_number = repeat('f', 20), initial_investment = 0.01"),
                _set(_VEHICLE, "fleet_number = NULL, initial_investment = NULL"),
                _set(_TARGET_SET, "monday = 0.01, sunday = 999999999999.99, created_by = NULL"),
                _set(_MAIN, "name = repeat('m', 100)"),
                "UPDATE setup.expense_categories SET bucket = NULL, main_category_id = NULL "
                "WHERE id = %(category)s",
                _set(_VERSION, "kind = 1, expense_item_id = NULL, bucket = NULL"),
                _set(_VERSION, "end_on = start_on, note = repeat('n', 200)"),
                _set(_RECORD, "amount = NULL, reason = 4, note = repeat('n', 80)"),
                _set(_RECORD, "amount = NULL, reason = 3, note = NULL"),
                _set(_RECORD, "amount = 999999999999.99"),
                _set(_ENTRY, "units = 999999999.999, unit_amount = 0.01"),
                _set(_ENTRY, "units = 0.001, unit_amount = 5"),
                _set(_ENTRY, "unit_amount = -999999999999.99"),
                _set(_ENTRY, "status = 1, sent_back_note = repeat('s', 200)"),
                _set(
                    _ENTRY,
                    "status = 4, reject_reason = repeat('j', 200), "
                    "reopen_reason = repeat('o', 200)",
                ),
                _set(_ENTRY, "removal_reason = repeat('r', 500), note = repeat('n', 80)"),
                _set(_ENTRY, "removed_by = NULL, removed_at = NULL, removal_reason = NULL"),
                _set(
                    _ENTRY,
                    _CREDIT + ", payee = repeat('p', 80), reimbursable = true, unit_amount = -450",
                ),
                _set(_ENTRY, _CASH + ", unit_amount = -450"),
                _set(_LOG, "section = 'pettycash', vehicle_id = NULL"),
                _set(_LOG, "section = 'pettycash'"),
            ],
        )
        == []
    )


def test_money_columns_cap_at_fourteen_digits(seeded: Seeded) -> None:
    exc = _failure(seeded.conn, _set(_RECORD, "amount = 1000000000000"), seeded.params())
    assert exc.sqlstate == "22003"


# --- unique and exclusion constraints (23505, 23P01) ----------------------------------

UNIQUE_CASES = [
    Case(
        "uq_users_email",
        "UPDATE identity.users SET email = (SELECT email FROM identity.users WHERE id = %(user)s) "
        "WHERE id = %(user2)s",
    ),
    Case(
        "uq_users_phone_number",
        "UPDATE identity.users SET phone_number = "
        "(SELECT phone_number FROM identity.users WHERE id = %(user)s) WHERE id = %(user2)s",
    ),
    Case(
        "uq_trusted_devices_token",
        "INSERT INTO identity.trusted_devices (user_id, device_id, trusted_at, last_used_at, "
        "token_hash) VALUES (%(user)s, 'device-2', now(), now(), repeat('B', 64)), "
        "(%(user)s, 'device-3', now(), now(), repeat('B', 64))",
    ),
    Case(
        "uq_trusted_devices_user_device",
        "INSERT INTO identity.trusted_devices (user_id, device_id, trusted_at, last_used_at) "
        "VALUES (%(user)s, 'device-1', now(), now())",
    ),
    Case(
        "uq_refresh_tokens_token_hash",
        "INSERT INTO identity.refresh_tokens (user_id, device_id, token_hash, expires_at) "
        "SELECT user_id, 'device-2', token_hash, expires_at FROM identity.refresh_tokens "
        "WHERE id = %(token)s",
    ),
    Case(
        "uq_organizations_slug",
        "UPDATE tenancy.organizations SET slug = (SELECT slug FROM tenancy.organizations "
        "WHERE id = %(org)s) WHERE id = %(b_org)s",
    ),
    Case(
        "uq_memberships_active_user",
        "INSERT INTO tenancy.memberships (organization_id, user_id, first_name, last_name) "
        "VALUES (%(b_org)s, %(user)s, 'Owen', 'Owner')",
    ),
    Case(
        "pk_person_roles",
        "INSERT INTO tenancy.person_roles (organization_id, user_id, role_id) "
        "VALUES (%(org)s, %(user)s, %(role)s)",
    ),
    Case(
        "uq_roles_name",
        "INSERT INTO tenancy.roles (organization_id, name) VALUES (%(org)s, 'OWNER')",
    ),
    Case(
        "uq_permissions_order",
        "UPDATE tenancy.permissions SET item_order = 2 WHERE key = 'dash.capture'",
    ),
    Case(
        "uq_change_log_id",
        "INSERT INTO tenancy.change_log (organization_id, version, id, section, entity_id, "
        "actor_id, reason, occurred_at, request_id) VALUES (%(org)s, 3, %(change_log_id)s, "
        "'people', %(user)s, %(user)s, 'Changed', now(), 'r')",
    ),
    Case(
        "uq_psv_companies_normalized_name",
        "INSERT INTO setup.psv_companies (organization_id, name) VALUES (%(org)s, 'METRO trans')",
    ),
    Case(
        "uq_fleet_vehicles_registration",
        "INSERT INTO setup.fleet_vehicles (organization_id, company_id, registration, joined_on) "
        "VALUES (%(org)s, %(company)s, 'KDA 482M', DATE '2026-02-01')",
    ),
    Case(
        "uq_fleet_vehicles_fleet_number",
        "INSERT INTO setup.fleet_vehicles (organization_id, company_id, registration, "
        "fleet_number, joined_on) VALUES (%(org)s, %(company)s, 'KDC 300C', 'mt-01', "
        "DATE '2026-02-01')",
    ),
    Case(
        "uq_vehicle_target_sets_start",
        "INSERT INTO setup.vehicle_target_sets (organization_id, vehicle_id, starts_on, monday, "
        "tuesday, wednesday, thursday, friday, saturday, sunday) VALUES (%(org)s, %(vehicle)s, "
        "DATE '2026-01-05', 1, 1, 1, 1, 1, 1, 1)",
    ),
    Case(
        "uq_vehicle_away_periods_left_on",
        "INSERT INTO setup.vehicle_away_periods (organization_id, vehicle_id, left_on, "
        "returned_on) VALUES (%(org)s, %(vehicle)s, DATE '2026-03-02', DATE '2026-03-03')",
    ),
    Case(
        "uq_recurring_versions_revision",
        "INSERT INTO setup.recurring_versions (organization_id, item_id, revision, "
        "effective_from, name, kind, amount, frequency, day, last_day, start_on) VALUES "
        "(%(org)s, %(recurring)s, 1, DATE '2026-02-01', 'Savings', 2, 10, 2, 1, false, "
        "DATE '2026-02-01')",
    ),
    Case(
        "uq_recurring_allocations_vehicle",
        "INSERT INTO setup.recurring_allocations (organization_id, version_id, vehicle_id, "
        "amount) VALUES (%(org)s, %(version)s, %(vehicle)s, 1)",
    ),
    Case(
        "uq_expense_main_categories_normalized_name",
        "INSERT INTO setup.expense_main_categories (organization_id, name) "
        "VALUES (%(org)s, 'RECURRING charges')",
    ),
    Case(
        "uq_expense_categories_normalized_name",
        "INSERT INTO setup.expense_categories (organization_id, name, bucket) "
        "VALUES (%(org)s, 'insurance', 1)",
    ),
    Case(
        "uq_expense_items_normalized_name",
        "INSERT INTO setup.expense_items (organization_id, category_id, name) "
        "VALUES (%(org)s, %(category)s, 'COMPREHENSIVE COVER')",
    ),
    Case(
        "uq_records_vehicle_day",
        "INSERT INTO revenue.records (organization_id, vehicle_id, business_date, amount, "
        "captured_at, captured_by, updated_by) VALUES (%(org)s, %(vehicle)s, DATE '2026-02-02', "
        "1, now(), %(user)s, %(user)s)",
    ),
    Case(
        "uq_recurring_kinds_name",
        "INSERT INTO setup.recurring_kinds VALUES (9, 'cost', 'Cost')",
    ),
    Case(
        "uq_recurrence_frequencies_name",
        "INSERT INTO setup.recurrence_frequencies VALUES (9, 'weekly', 'Weekly')",
    ),
    Case(
        "uq_expense_buckets_name",
        "INSERT INTO setup.expense_buckets VALUES (9, 'loan_repayments', 'loans')",
    ),
    Case(
        "uq_no_earnings_reasons_name",
        "INSERT INTO revenue.no_earnings_reasons VALUES (9, 'other', 'Other')",
    ),
    Case("uq_kinds_name", "INSERT INTO pettycash.kinds VALUES (9, 'cash', 'Cash')"),
    Case(
        "uq_statuses_name",
        "INSERT INTO pettycash.statuses VALUES (9, 'waiting', 'Waiting')",
    ),
    Case(
        "pk_entries",
        "INSERT INTO pettycash.entries (organization_id, id, holder_id, kind, entry_date, "
        "unit_amount, recorded_by, recorded_at, updated_by, updated_at) VALUES (%(org)s, "
        "%(entry)s, %(user)s, 1, DATE '2026-02-02', 100, %(user)s, now(), %(user)s, now())",
    ),
    Case(
        "uq_entries_group_vehicle",
        "INSERT INTO pettycash.entries (organization_id, holder_id, kind, entry_date, vehicle_id, "
        "expense_item_id, unit_amount, status, recorded_by, recorded_at, updated_by, updated_at, "
        "group_id, group_total, group_units, group_unit_amount) SELECT %(org)s, %(user)s, 2, "
        "DATE '2026-02-02', %(vehicle)s, %(item)s, 450, 1, %(user)s, now(), %(user)s, now(), "
        "g.id, 900, 2, 450 FROM (VALUES (1), (2)) v(n), (SELECT gen_random_uuid() AS id) g",
    ),
    Case(
        "uq_entries_group_vehicle",
        "INSERT INTO expenses.entries (organization_id, id, entry_date, vehicle_id, "
        "expense_item_id, units, unit_amount, group_id, group_size, group_total, group_units, "
        "group_unit_amount, recorded_by, recorded_at, updated_by, updated_at) SELECT "
        "organization_id, gen_random_uuid(), entry_date, vehicle_id, expense_item_id, units, "
        "unit_amount, group_id, group_size, group_total, group_units, group_unit_amount, "
        "recorded_by, recorded_at, updated_by, updated_at FROM expenses.entries "
        "WHERE id = %(central)s",
    ),
    Case(
        "pk_entries",
        "INSERT INTO expenses.entries (organization_id, id, entry_date, vehicle_id, "
        "expense_item_id, units, unit_amount, group_id, group_size, group_total, group_units, "
        "group_unit_amount, recorded_by, recorded_at, updated_by, updated_at) SELECT "
        "organization_id, id, entry_date, %(vehicle2)s, expense_item_id, units, unit_amount, "
        "gen_random_uuid(), group_size, group_total, group_units, group_unit_amount, "
        "recorded_by, recorded_at, updated_by, updated_at FROM expenses.entries "
        "WHERE id = %(central)s",
    ),
    Case(
        "uq_recurring_pauses_open",
        "INSERT INTO setup.recurring_pauses (organization_id, item_id, paused_from) VALUES "
        "(%(org)s, %(recurring)s, DATE '2026-04-01'), (%(org)s, %(recurring)s, DATE '2026-05-01')",
    ),
    Case(
        "uq_saving_run_states_name",
        "INSERT INTO setup.saving_run_states VALUES (9, 'saved', 'Saved')",
    ),
    Case(
        "pk_saving_runs",
        "INSERT INTO setup.saving_runs SELECT * FROM setup.saving_runs WHERE item_id = %(saving)s",
    ),
    Case(
        "pk_saving_opening_amounts",
        "INSERT INTO setup.saving_opening_amounts SELECT * FROM setup.saving_opening_amounts "
        "WHERE item_id = %(saving)s",
    ),
]


def test_unique_constraints_refuse_duplicates(seeded: Seeded) -> None:
    assert _run(seeded, UNIQUE_CASES, "23505") == []


def test_every_unique_constraint_and_index_has_a_case(owner_conn: Conn) -> None:
    rows = owner_conn.execute(
        """
        SELECT ic.relname
        FROM pg_index i
        JOIN pg_class ic ON ic.oid = i.indexrelid
        JOIN pg_class tc ON tc.oid = i.indrelid
        WHERE i.indisunique AND NOT i.indisprimary
          AND tc.relnamespace::regnamespace::text = ANY(%s)
        """,
        (SCHEMAS,),
    ).fetchall()
    covered = {c.constraint for c in UNIQUE_CASES if not c.constraint.startswith("pk_")}
    assert covered == {r["relname"] for r in rows}


def test_uniqueness_passes_where_the_rule_allows(seeded: Seeded) -> None:
    assert (
        _passes(
            seeded,
            [
                "INSERT INTO tenancy.memberships (organization_id, user_id, first_name, "
                "last_name, active) VALUES (%(b_org)s, %(user)s, 'Owen', 'Owner', false)",
                "INSERT INTO setup.psv_companies (organization_id, name) "
                "VALUES (%(b_org)s, 'Metro Trans 2')",
                "INSERT INTO setup.fleet_vehicles (organization_id, company_id, registration, "
                "joined_on) VALUES (%(b_org)s, %(b_company)s, 'KDA 483M', DATE '2026-01-05')",
                "INSERT INTO tenancy.roles (organization_id, name) "
                "VALUES (%(org)s, 'Fleet manager')",
                "WITH c AS (INSERT INTO setup.psv_companies (organization_id, name) "
                "VALUES (%(org)s, 'Coast Line') RETURNING id) "
                "INSERT INTO setup.fleet_vehicles (organization_id, company_id, registration, "
                "fleet_number, joined_on) SELECT %(org)s, c.id, 'KDC 300C', 'MT-01', "
                "DATE '2026-01-05' FROM c",
                "INSERT INTO setup.fleet_vehicles (organization_id, company_id, registration, "
                "joined_on) VALUES (%(org)s, %(company)s, 'KDD 400D', DATE '2026-01-05')",
                "INSERT INTO setup.vehicle_target_sets (organization_id, vehicle_id, starts_on, "
                "monday, tuesday, wednesday, thursday, friday, saturday, sunday) VALUES "
                "(%(org)s, %(vehicle)s, DATE '2026-01-06', 1, 1, 1, 1, 1, 1, 1)",
            ],
        )
        == []
    )


def test_names_and_registrations_are_unique_per_organization_only(seeded: Seeded) -> None:
    row = seeded.conn.execute(
        "SELECT (SELECT count(*) FROM setup.fleet_vehicles WHERE registration = 'KDA 482M') AS v, "
        "(SELECT count(*) FROM setup.psv_companies WHERE name = 'Metro Trans') AS c, "
        "(SELECT count(*) FROM tenancy.roles WHERE name = 'Owner') AS r, "
        "(SELECT count(*) FROM setup.fleet_vehicles WHERE fleet_number = 'MT-01') AS f, "
        "(SELECT count(*) FROM setup.expense_main_categories "
        "WHERE name = 'Recurring charges') AS m"
    ).fetchone()
    assert row == {"v": 2, "c": 2, "r": 2, "f": 2, "m": 2}


def test_away_periods_cannot_overlap(seeded: Seeded) -> None:
    exc = _failure(
        seeded.conn,
        "INSERT INTO setup.vehicle_away_periods (organization_id, vehicle_id, left_on, "
        "returned_on) VALUES (%(org)s, %(vehicle)s, DATE '2026-03-05', DATE '2026-03-12')",
        seeded.params(),
    )
    assert (exc.sqlstate, exc.diag.constraint_name) == ("23P01", "ex_vehicle_away_periods_overlap")
    assert _constraint_names(seeded.conn, "x") == {
        "ex_vehicle_away_periods_overlap",
        "ex_recurring_pauses_overlap",
    }


def test_pauses_of_an_item_cannot_overlap(seeded: Seeded) -> None:
    insert = (
        "INSERT INTO setup.recurring_pauses (organization_id, item_id, paused_from, "
        "paused_through) VALUES (%(org)s, %(recurring)s, {}, {})"
    )
    for start, through in (
        ("DATE '2026-03-10'", "DATE '2026-03-20'"),
        ("DATE '2026-02-01'", "NULL"),
        ("DATE '2026-03-05'", "DATE '2026-03-05'"),
    ):
        exc = _failure(seeded.conn, insert.format(start, through), seeded.params())
        assert (exc.sqlstate, exc.diag.constraint_name) == ("23P01", "ex_recurring_pauses_overlap")
    assert (
        _passes(
            seeded,
            [
                insert.format("DATE '2026-03-11'", "NULL"),
                insert.format("DATE '2026-02-27'", "DATE '2026-02-28'"),
                insert.format("DATE '2026-03-05'", "DATE '2026-03-04'"),
                insert.format("DATE '2026-03-01'", "DATE '2026-02-28'"),
                "INSERT INTO setup.recurring_pauses (organization_id, item_id, paused_from) "
                "VALUES (%(org)s, %(saving)s, DATE '2026-03-05')",
            ],
        )
        == []
    )


def test_adjacent_and_other_vehicles_away_periods_pass(seeded: Seeded) -> None:
    assert (
        _passes(
            seeded,
            [
                "INSERT INTO setup.vehicle_away_periods (organization_id, vehicle_id, left_on, "
                "returned_on) VALUES (%(org)s, %(vehicle)s, DATE '2026-03-09', DATE '2026-03-16')",
                "INSERT INTO setup.vehicle_away_periods (organization_id, vehicle_id, left_on, "
                "returned_on) VALUES (%(org)s, %(vehicle)s, DATE '2026-02-23', DATE '2026-03-02')",
                "INSERT INTO setup.vehicle_away_periods (organization_id, vehicle_id, left_on, "
                "returned_on) VALUES (%(org)s, %(vehicle2)s, DATE '2026-03-02', DATE '2026-03-09')",
            ],
        )
        == []
    )


# --- foreign keys (23503) ---------------------------------------------------------------

REFERENCE_CASES = [
    Case(
        "fk_verification_codes_user",
        "UPDATE identity.verification_codes SET user_id = gen_random_uuid() WHERE id = %(code)s",
    ),
    Case(
        "fk_trusted_devices_user",
        "UPDATE identity.trusted_devices SET user_id = gen_random_uuid() WHERE id = %(device)s",
    ),
    Case(
        "fk_refresh_tokens_user",
        "UPDATE identity.refresh_tokens SET user_id = gen_random_uuid() WHERE id = %(token)s",
    ),
    Case("fk_sign_in_attempts_user", _set(_ATTEMPT, "user_id = gen_random_uuid()")),
    Case(
        "fk_memberships_user",
        "INSERT INTO tenancy.memberships (organization_id, user_id, first_name, last_name) "
        "VALUES (%(org)s, gen_random_uuid(), 'No', 'Body')",
    ),
    Case(
        "fk_permission_dependencies_permission",
        "INSERT INTO tenancy.permission_dependencies VALUES ('no.such_key', 'revenue.view')",
    ),
    Case(
        "fk_permission_dependencies_needs",
        "INSERT INTO tenancy.permission_dependencies VALUES ('revenue.view', 'no.such_key')",
    ),
    Case(
        "fk_permission_sources_permission",
        "INSERT INTO tenancy.permission_sources VALUES ('no.such_key', 'revenue.view')",
    ),
    Case(
        "fk_permission_sources_source",
        "INSERT INTO tenancy.permission_sources VALUES ('dash.capture', 'no.such_key')",
    ),
    Case(
        "fk_permission_translations_old_key",
        "INSERT INTO tenancy.permission_translations VALUES ('no.such_key', 'revenue.view')",
    ),
    Case(
        "fk_permission_translations_new_key",
        "INSERT INTO tenancy.permission_translations VALUES ('revenue.view', 'no.such_key')",
    ),
    Case(
        "fk_role_defaults_permission",
        "INSERT INTO tenancy.role_defaults VALUES ('Owner', 'no.such_key')",
    ),
    Case(
        "fk_permission_overrides_permission",
        "INSERT INTO tenancy.permission_overrides (organization_id, user_id, permission, granted) "
        "VALUES (%(org)s, %(user)s, 'no.such_key', true)",
    ),
    Case(
        "fk_expense_categories_bucket",
        "UPDATE setup.expense_categories SET bucket = 9 WHERE id = %(category)s",
    ),
    # The kind and schedule CHECKs refuse unknown codes first, so these keys are proven by
    # removing the code a stored version uses.
    Case("fk_recurring_versions_kind", "DELETE FROM setup.recurring_kinds WHERE code = 1"),
    Case(
        "fk_recurring_versions_frequency",
        "DELETE FROM setup.recurrence_frequencies WHERE code = 3",
    ),
    Case("fk_recurring_versions_bucket", _set(_VERSION, "bucket = 9")),
    Case("fk_records_reason", _set(_RECORD, "amount = NULL, reason = 9")),
    Case("fk_entries_kind", "DELETE FROM pettycash.kinds WHERE code = 2"),
    Case("fk_entries_status", "DELETE FROM pettycash.statuses WHERE code = 2"),
    Case("fk_saving_runs_state", "DELETE FROM setup.saving_run_states WHERE code = 1"),
]


def test_references_to_users_codes_and_the_catalogue_must_exist(seeded: Seeded) -> None:
    assert _run(seeded, REFERENCE_CASES, "23503") == []


def _foreign_keys(conn: Conn) -> list[dict[str, Any]]:
    return conn.execute(
        """
        SELECT k.conname,
               k.conrelid::regclass::text AS source,
               k.confrelid::regclass::text AS target,
               ARRAY(
                 SELECT a.attname::text FROM unnest(k.conkey) WITH ORDINALITY AS u(n, p)
                 JOIN pg_attribute a ON a.attrelid = k.conrelid AND a.attnum = u.n ORDER BY u.p
               ) AS source_columns,
               ARRAY(
                 SELECT a.attname::text FROM unnest(k.confkey) WITH ORDINALITY AS u(n, p)
                 JOIN pg_attribute a ON a.attrelid = k.confrelid AND a.attnum = u.n ORDER BY u.p
               ) AS target_columns
        FROM pg_constraint k
        WHERE k.contype = 'f' AND k.connamespace::regnamespace::text = ANY(%s)
        ORDER BY k.conname
        """,
        (SCHEMAS,),
    ).fetchall()


def _is_composite(fk: dict[str, Any]) -> bool:
    return len(fk["source_columns"]) > 1 and fk["source_columns"][0] == "organization_id"


def _is_organization_key(fk: dict[str, Any]) -> bool:
    return fk["target"] == "tenancy.organizations"


def _ident(qualified: str) -> sql.Identifier:
    return sql.Identifier(*qualified.split(".", 1))


def test_composite_foreign_keys_refuse_another_organizations_rows(seeded: Seeded) -> None:
    """Point each tenant-to-tenant reference of an organization A row at organization B's
    row: the composite key (A, B's id) does not exist, so the row cannot cross tenants."""
    conn, mismatches = seeded.conn, []
    composite = [fk for fk in _foreign_keys(conn) if _is_composite(fk)]
    assert len(composite) == 45
    for fk in composite:
        columns = fk["source_columns"][1:]
        target_columns = fk["target_columns"][1:]
        statement = sql.SQL(
            "UPDATE {source} SET ({columns}) = (SELECT {target_columns} FROM {target} "
            "WHERE organization_id = %(b_org)s LIMIT 1) "
            "WHERE ctid = (SELECT ctid FROM {source} WHERE organization_id = %(org)s LIMIT 1)"
        ).format(
            source=_ident(fk["source"]),
            target=_ident(fk["target"]),
            columns=sql.SQL(", ").join(map(sql.Identifier, columns)),
            target_columns=sql.SQL(", ").join(map(sql.Identifier, target_columns)),
        )
        if len(columns) == 1:
            statement = sql.SQL(
                "UPDATE {source} SET {column} = (SELECT {target_column} FROM {target} "
                "WHERE organization_id = %(b_org)s LIMIT 1) "
                "WHERE ctid = (SELECT ctid FROM {source} WHERE organization_id = %(org)s LIMIT 1)"
            ).format(
                source=_ident(fk["source"]),
                target=_ident(fk["target"]),
                column=sql.Identifier(columns[0]),
                target_column=sql.Identifier(target_columns[0]),
            )
        exc = _failure(conn, statement, seeded.params())
        if (exc.sqlstate, exc.diag.constraint_name) != ("23503", fk["conname"]):
            mismatches.append(f"{fk['conname']}: {exc.sqlstate} {exc.diag.message_primary}")
    assert mismatches == []


def test_organization_foreign_keys_refuse_an_unknown_organization(seeded: Seeded) -> None:
    conn, mismatches = seeded.conn, []
    for fk in _foreign_keys(conn):
        if not _is_organization_key(fk):
            continue
        statement = sql.SQL(
            "UPDATE {source} SET organization_id = gen_random_uuid() "
            "WHERE ctid = (SELECT ctid FROM {source} WHERE organization_id = %(org)s LIMIT 1)"
        ).format(source=_ident(fk["source"]))
        exc = _failure(conn, statement, seeded.params())
        if exc.sqlstate != "23503":
            mismatches.append(f"{fk['conname']}: {exc.sqlstate} {exc.diag.message_primary}")
    assert mismatches == []


def test_every_foreign_key_has_a_case(owner_conn: Conn) -> None:
    fks = _foreign_keys(owner_conn)
    generic = {fk["conname"] for fk in fks if _is_composite(fk) or _is_organization_key(fk)}
    explicit = {c.constraint for c in REFERENCE_CASES}
    assert generic.isdisjoint(explicit)
    assert generic | explicit == {fk["conname"] for fk in fks}


# --- triggers (XC422) -------------------------------------------------------------------


def _detail(exc: psycopg.Error) -> dict[str, Any]:
    detail = exc.diag.message_detail
    assert detail is not None
    parsed: dict[str, Any] = json.loads(detail)
    return parsed


def test_registration_cannot_change(seeded: Seeded) -> None:
    exc = _failure(seeded.conn, _set(_VEHICLE, "registration = 'KDA 999Z'"), seeded.params())
    assert (exc.sqlstate, exc.diag.message_primary) == ("XC422", "registration_immutable")
    assert _detail(exc) == {"registration": "KDA 482M"}


def test_vehicle_updates_that_keep_the_registration_pass(seeded: Seeded) -> None:
    assert (
        _passes(
            seeded,
            [
                _set(_VEHICLE, "registration = 'KDA 482M', left_on = DATE '2026-06-30'"),
                _set(_VEHICLE, "company_id = company_id"),
            ],
        )
        == []
    )


def test_business_date_cannot_change(seeded: Seeded) -> None:
    exc = _failure(seeded.conn, _set(_RECORD, "business_date = DATE '2026-02-03'"), seeded.params())
    assert (exc.sqlstate, exc.diag.message_primary) == ("XC422", "business_date_immutable")
    assert _detail(exc) == {"date": "2026-02-02"}


def test_record_updates_that_keep_the_day_pass(seeded: Seeded) -> None:
    assert _passes(seeded, [_set(_RECORD, "amount = 3500, version = version + 1")]) == []


_NEW_VERSION = (
    "INSERT INTO setup.recurring_versions (organization_id, id, item_id, revision, "
    "effective_from, name, kind, amount, frequency, day, last_day, start_on) VALUES "
    "(%(org)s, %(new_version)s, %(recurring)s, 2, DATE '2026-02-01', 'Savings', 2, {amount}, "
    "2, 1, false, DATE '2026-02-01')"
)
_SHARE = (
    "INSERT INTO setup.recurring_allocations (organization_id, version_id, vehicle_id, amount) "
    "VALUES (%(org)s, %(new_version)s, %({vehicle})s, {amount})"
)


@pytest.fixture
def new_version(seeded: Seeded) -> Iterator[dict[str, Any]]:
    yield {**seeded.params(), "new_version": "6f1c1d2e-0000-4000-8000-000000000001"}


def _commit(conn: Conn, statements: list[str], params: dict[str, Any]) -> psycopg.Error | None:
    try:
        with conn.transaction():
            for statement in statements:
                conn.execute(statement, params)  # type: ignore[arg-type]
    except psycopg.Error as exc:
        return exc
    return None


def test_a_version_without_shares_is_refused_at_commit(
    seeded: Seeded, new_version: dict[str, Any]
) -> None:
    exc = _commit(seeded.conn, [_NEW_VERSION.format(amount=100)], new_version)
    assert exc is not None
    assert (exc.sqlstate, exc.diag.message_primary) == ("XC422", "allocation_sum_mismatch")
    assert _detail(exc) == {
        "version_id": new_version["new_version"],
        "amount": 100.00,
        "allocated": 0,
        "vehicles": 0,
    }


def test_shares_that_do_not_add_up_are_refused_at_commit(
    seeded: Seeded, new_version: dict[str, Any]
) -> None:
    exc = _commit(
        seeded.conn,
        [
            _NEW_VERSION.format(amount=100),
            _SHARE.format(vehicle="vehicle", amount=60),
            _SHARE.format(vehicle="vehicle2", amount="39.99"),
        ],
        new_version,
    )
    assert exc is not None
    assert (exc.sqlstate, exc.diag.message_primary) == ("XC422", "allocation_sum_mismatch")
    assert _detail(exc)["allocated"] == 99.99


def test_shares_that_add_up_exactly_commit(seeded: Seeded, new_version: dict[str, Any]) -> None:
    exc = _commit(
        seeded.conn,
        [
            _NEW_VERSION.format(amount="100.01"),
            _SHARE.format(vehicle="vehicle", amount="60.01"),
            _SHARE.format(vehicle="vehicle2", amount=40),
        ],
        new_version,
    )
    assert exc is None


def test_changing_a_version_amount_rechecks_the_shares(seeded: Seeded) -> None:
    exc = _commit(seeded.conn, [_set(_VERSION, "amount = 1001")], seeded.params())
    assert exc is not None
    assert (exc.sqlstate, exc.diag.message_primary) == ("XC422", "allocation_sum_mismatch")


@pytest.mark.parametrize(("vehicles", "valid"), [(500, True), (501, False)])
def test_a_version_has_at_most_500_shares(seeded: Seeded, vehicles: int, valid: bool) -> None:
    params = {**seeded.params(), "n": vehicles}
    seeded.conn.execute(
        "INSERT INTO setup.fleet_vehicles (organization_id, company_id, registration, joined_on) "
        "SELECT %(org)s, %(company)s, 'KZZ ' || lpad(i::text, 3, '0') || 'A', DATE '2026-01-05' "
        "FROM generate_series(0, 500) AS i",
        params,
    )
    exc = _commit(
        seeded.conn,
        [
            "INSERT INTO setup.recurring_items (organization_id, id) "
            "VALUES (%(org)s, '6f1c1d2e-0000-4000-8000-000000000002')",
            "INSERT INTO setup.recurring_versions (organization_id, id, item_id, revision, "
            "effective_from, name, kind, amount, frequency, day, last_day, start_on) VALUES "
            "(%(org)s, '6f1c1d2e-0000-4000-8000-000000000003', "
            "'6f1c1d2e-0000-4000-8000-000000000002', 1, DATE '2026-02-01', 'Wide', 2, %(n)s, 2, "
            "1, false, DATE '2026-02-01')",
            "INSERT INTO setup.recurring_allocations (organization_id, version_id, vehicle_id, "
            "amount) SELECT %(org)s, '6f1c1d2e-0000-4000-8000-000000000003', id, 1 "
            "FROM setup.fleet_vehicles WHERE organization_id = %(org)s "
            "AND registration LIKE 'KZZ %%' ORDER BY registration LIMIT %(n)s",
        ],
        params,
    )
    if valid:
        assert exc is None
    else:
        assert exc is not None
        assert (exc.sqlstate, exc.diag.message_primary) == ("XC422", "allocation_sum_mismatch")
        assert _detail(exc)["vehicles"] == 501


def test_updated_at_is_touched_unless_the_statement_sets_it(seeded: Seeded) -> None:
    conn, params = seeded.conn, seeded.params()
    conn.execute(
        "UPDATE identity.users SET updated_at = TIMESTAMPTZ '2000-01-01T00:00:00Z' "
        "WHERE id = %(user)s",
        params,
    )
    kept = conn.execute(
        "SELECT updated_at = TIMESTAMPTZ '2000-01-01T00:00:00Z' AS kept FROM identity.users "
        "WHERE id = %(user)s",
        params,
    ).fetchone()
    assert kept is not None
    assert kept["kept"] is True
    conn.execute("UPDATE identity.users SET failed_attempts = 1 WHERE id = %(user)s", params)
    touched = conn.execute(
        "SELECT updated_at > now() - interval '1 minute' AS touched FROM identity.users "
        "WHERE id = %(user)s",
        params,
    ).fetchone()
    assert touched is not None
    assert touched["touched"] is True


# --- brand colour contrast ----------------------------------------------------------------


def _python_ratio(colour: str, against: str) -> float:
    """The WCAG 2 ratio, written independently of the SQL function as its parity fixture."""

    def linear(byte: int) -> float:
        c = byte / 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    def luminance(hex_colour: str) -> float:
        r, g, b = (int(hex_colour[i : i + 2], 16) for i in (1, 3, 5))
        return 0.2126 * linear(r) + 0.7152 * linear(g) + 0.0722 * linear(b)

    la, lb = luminance(colour), luminance(against)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


# Ratios worked out by hand from the formula, truncated to two decimals.
CONTRAST_TABLE = [
    ("#000000", "#FFFFFF", "21.00"),
    ("#FFFFFF", "#FFFFFF", "1.00"),
    ("#1D5FD6", "#FFFFFF", "5.73"),
    ("#1d5fd6", "#F6F3EC", "5.17"),
    ("#14213D", "#F6F3EC", "14.41"),
    ("#1E6B3A", "#F6F3EC", "5.88"),
    ("#767676", "#FFFFFF", "4.54"),
    ("#767676", "#F6F3EC", "4.09"),
    ("#777777", "#FFFFFF", "4.47"),
    ("#078A22", "#FFFFFF", "4.49"),
    ("#FFFF00", "#FFFFFF", "1.07"),
]


@pytest.mark.parametrize(("colour", "against", "expected"), CONTRAST_TABLE)
def test_contrast_ratio(owner_conn: Conn, colour: str, against: str, expected: str) -> None:
    row = owner_conn.execute(
        "SELECT tenancy.check_contrast(%s, %s)::text AS ratio", (colour, against)
    ).fetchone()
    assert row is not None
    assert row["ratio"] == expected
    assert f"{math.floor(_python_ratio(colour, against) * 100) / 100:.2f}" == expected


def test_contrast_is_truncated_so_a_ratio_just_below_the_bar_fails(seeded: Seeded) -> None:
    assert 4.495 < _python_ratio("#078A22", "#FFFFFF") < 4.5
    exc = _failure(seeded.conn, _set(_BRAND, "primary_color = '#078A22'"), seeded.params())
    assert (exc.sqlstate, exc.diag.constraint_name) == ("23514", "ck_brandings_contrast")


def test_contrast_must_hold_against_both_surfaces(seeded: Seeded) -> None:
    exc = _failure(seeded.conn, _set(_BRAND, "secondary_color = '#767676'"), seeded.params())
    assert (exc.sqlstate, exc.diag.constraint_name) == ("23514", "ck_brandings_contrast")


def test_contrast_of_a_malformed_colour_is_null(owner_conn: Conn) -> None:
    row = owner_conn.execute(
        "SELECT tenancy.check_contrast('blue', '#FFFFFF') AS a, "
        "tenancy.check_contrast('#FFFFFF', '#FFF') AS b"
    ).fetchone()
    assert row == {"a": None, "b": None}
