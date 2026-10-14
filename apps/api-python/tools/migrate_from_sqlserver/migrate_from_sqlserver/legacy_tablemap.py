"""The legacy PostgreSQL database mapped onto the schema (``docs/10-data-migration.md`` 7.3
and 7.4), as data.

The legacy application keeps one fleet per database in ``public`` (alembic ``d8e1a4f9c220``).
``EXTRACTS`` are the queries ``extract --source legacy`` runs, one file each: the rows of one
target table, or rows only read (a petty-cash copy is checked against its original, the daily
balances are compared, provisions and budgets are listed). Together the files of a legacy
table hold each of its rows exactly once; ``load`` checks that against the table's count.
``TABLES`` are the target tables in foreign-key load order, as in ``tablemap.py``.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass

from .tablemap import (
    EXTRACTED_AT,
    Column,
    Table,
    bit,
    created,
    day,
    derived,
    fixed,
    integer,
    jsonb,
    money,
    text,
    uid,
    utc,
)

VERSION = "d8e1a4f9c220"
"""The alembic version the map was checked against; the extract refuses any other."""

LEGACY_IDS = uuid.UUID("5d0f3a8e-2b1c-4e57-9c46-1a7e3f2b9d84")
"""Namespace of the ids the tool makes: the same organization and natural key give the same id."""

ORGANIZATION_NAME = "My fleet"
ORGANIZATION_SLUG = "my-fleet"
ROLES = ("Owner", "Office admin", "Fleet manager", "Revenue clerk")
OWNER = "Owner"
FLEET_MANAGER = "Fleet manager"
ADMINISTRATOR = "Administrator"
TIME_ZONE = "Africa/Nairobi"
ZERO_NOTE = "0 in the old system"
OTHER_REASON = 4
CREDIT_NOTE_LABEL = "credit note"
"""The label the old application gives every credit note (in ``name`` and ``source``)."""
CASH, EXPENSE, CREDIT = 1, 2, 3
WAITING, APPROVED = 1, 2

LOADED, DROPPED, REPLACED = "loaded", "dropped", "replaced"


@dataclass(frozen=True, slots=True)
class Extract:
    """One query of the legacy extract: ``rows`` selects whole rows of ``table``."""

    name: str
    table: str
    rows: str
    columns: tuple[Column, ...]
    fate: str = LOADED
    rule: str = ""
    key: tuple[str, ...] = ("id",)


def _org() -> Column:
    return derived("organization_id", "uuid")


TABLES: tuple[Table, ...] = (
    Table(
        1,
        "users",
        "identity.users",
        ("id",),
        ("id",),
        (
            uid("id", "id"),
            text("name", None),
            text("email", None),
            text("phone", None),
            text("role", None),
            uid("role_id", None),
            jsonb("permissions", None),
            bit("is_default_petty_cash_manager", None),
            utc("created_at", "created_at"),
            utc("updated_at", "updated_at"),
            derived("email", "text"),
            derived("phone_number", "text"),
            fixed("pin_hash", "text", None),
            fixed("status", "text", "active"),
            fixed("security_version", "int", 0),
            fixed("failed_attempts", "int", 0),
            fixed("untrusted_failed_attempts", "int", 0),
            fixed("version", "int", 0),
            fixed("pin_reset_required", "bool", False),
            fixed("last_signed_in_at", "timestamptz", None),
        ),
        convert=("people",),
    ),
    Table(
        2,
        None,
        "tenancy.organizations",
        ("organization",),
        ("id",),
        (
            derived("id", "uuid"),
            derived("slug", "text"),
            derived("name", "text"),
            fixed("business_date", "date", None),
            fixed("settings_version", "int", 1),
            *created(),
        ),
        convert=("organization",),
    ),
    Table(
        3,
        None,
        "tenancy.organization_localizations",
        ("organization",),
        ("organization_id",),
        (_org(), *created()),
        convert=("organization_settings",),
    ),
    Table(
        4,
        None,
        "tenancy.organization_brandings",
        ("organization",),
        ("organization_id",),
        (_org(), *created()),
        convert=("organization_settings",),
    ),
    Table(
        5,
        None,
        "tenancy.organization_security_policies",
        ("organization",),
        ("organization_id",),
        (_org(), *created()),
        convert=("organization_settings",),
    ),
    Table(
        6,
        None,
        "tenancy.roles",
        ("name",),
        ("organization_id", "id"),
        (
            _org(),
            derived("id", "uuid"),
            derived("name", "text"),
            fixed("created_at", "timestamptz", EXTRACTED_AT),
        ),
        convert=("roles",),
    ),
    Table(
        7,
        None,
        "tenancy.memberships",
        ("user",),
        ("organization_id", "user_id"),
        (
            _org(),
            derived("user_id", "uuid"),
            derived("first_name", "text"),
            derived("last_name", "text"),
            fixed("active", "bool", True),
            fixed("approval_limit", "numeric", None),
            fixed("version", "int", 1),
            derived("created_at", "timestamptz"),
            derived("updated_at", "timestamptz"),
            fixed("back_limit_mode", "text", "none"),
            fixed("back_limit_count", "int", None),
            fixed("back_limit_from", "date", None),
        ),
        convert=("memberships",),
    ),
    Table(
        8,
        None,
        "tenancy.person_roles",
        ("user",),
        ("organization_id", "user_id"),
        (
            _org(),
            derived("user_id", "uuid"),
            derived("role_id", "uuid"),
            fixed("updated_at", "timestamptz", EXTRACTED_AT),
        ),
        convert=("person_roles",),
    ),
    Table(
        9,
        None,
        "tenancy.permission_overrides",
        ("user", "permission"),
        ("organization_id", "user_id", "permission"),
        (
            _org(),
            derived("user_id", "uuid"),
            derived("permission", "text"),
            derived("granted", "bool"),
        ),
        convert=("overrides",),
    ),
    Table(
        10,
        None,
        "tenancy.data_scopes",
        ("user",),
        ("organization_id", "user_id"),
        (
            _org(),
            derived("user_id", "uuid"),
            fixed("all_companies", "bool", True),
            fixed("updated_at", "timestamptz", EXTRACTED_AT),
        ),
        convert=("data_scopes",),
    ),
    Table(
        11,
        None,
        "setup.psv_companies",
        ("sacco",),
        ("organization_id", "id"),
        (
            _org(),
            derived("id", "uuid"),
            derived("name", "text"),
            fixed("archived_on", "date", None),
            *created(),
        ),
        convert=("companies",),
        reads=("vehicles",),
    ),
    Table(
        12,
        "vehicles",
        "setup.fleet_vehicles",
        ("id",),
        ("organization_id", "id"),
        (
            _org(),
            uid("id", "id"),
            text("registration", "registration"),
            text("sacco", None),
            money("provision_bf", None),
            money("provision_cf", None),
            utc("created_at", "created_at"),
            utc("updated_at", "updated_at"),
            derived("company_id", "uuid"),
            derived("joined_on", "date"),
            fixed("left_on", "date", None),
            derived("fleet_number", "text"),
            fixed("initial_investment", "numeric", None),
        ),
        convert=("vehicles",),
    ),
    Table(
        13,
        "categories",
        "setup.expense_categories",
        ("id",),
        ("organization_id", "id"),
        (
            _org(),
            uid("id", "id"),
            text("title", "name"),
            text("factor", None),
            utc("created_at", "created_at"),
            utc("updated_at", "updated_at"),
            fixed("bucket", "int", None),
            fixed("stopped_on", "date", None),
            fixed("main_category_id", "uuid", None),
        ),
        drops=("income_category",),
        convert=("trimmed_name",),
    ),
    Table(
        14,
        "entries",
        "setup.expense_items",
        ("id",),
        ("organization_id", "id"),
        (
            _org(),
            uid("id", "id"),
            uid("category_id", "category_id"),
            text("title", "name"),
            text("factor", None),
            integer("position", None),
            bit("primary", None),
            utc("created_at", "created_at"),
            utc("updated_at", "updated_at"),
            fixed("stopped_on", "date", None),
        ),
        drops=("revenue_item", "uncategorised_item", "merged_item"),
        convert=("trimmed_name",),
    ),
    Table(
        15,
        "records_revenue",
        "revenue.records",
        ("id",),
        ("organization_id", "id"),
        (
            _org(),
            uid("id", "id"),
            uid("vehicle_id", "vehicle_id"),
            uid("entry_id", None),
            day("date", "business_date"),
            money("plus", None),
            utc("created_at", "captured_at"),
            utc("updated_at", "updated_at"),
            derived("amount", "numeric", scale=2, precision=14),
            derived("reason", "int"),
            derived("note", "text"),
            derived("captured_by", "uuid"),
            derived("updated_by", "uuid"),
            fixed("corrected_after_date", "bool", False),
            fixed("version", "int", 1),
        ),
        convert=("revenue_days",),
    ),
    Table(
        16,
        "records_expenses",
        "expenses.entries",
        ("id",),
        ("organization_id", "id"),
        (
            _org(),
            uid("id", "id"),
            uid("vehicle_id", "vehicle_id"),
            uid("entry_id", None),
            day("date", "entry_date"),
            money("minus", None),
            money("quantity", None, precision=12, scale=3),
            utc("created_at", "recorded_at"),
            utc("updated_at", "updated_at"),
            derived("expense_item_id", "uuid"),
            derived("units", "numeric", scale=3, precision=12),
            derived("unit_amount", "numeric", scale=2, precision=14),
            derived("group_id", "uuid"),
            derived("group_size", "int"),
            derived("group_total", "numeric", scale=2, precision=14),
            derived("group_units", "numeric", scale=3, precision=12),
            derived("group_unit_amount", "numeric", scale=2, precision=14),
            fixed("note", "text", None),
            derived("recorded_by", "uuid"),
            derived("updated_by", "uuid"),
            fixed("removed_by", "uuid", None),
            fixed("removed_at", "timestamptz", None),
            fixed("removal_reason", "text", None),
            fixed("version", "int", 1),
        ),
        convert=("central_expenses",),
    ),
    Table(
        17,
        "petty_cash",
        "pettycash.entries",
        ("id",),
        ("organization_id", "id"),
        (
            _org(),
            uid("id", "id"),
            day("date", "entry_date"),
            uid("vehicle_id", "vehicle_id"),
            uid("entry_id", None),
            money("unit_price", None),
            money("quantity", None, precision=12, scale=3),
            money("plus", None),
            money("minus", None),
            bit("committed", None),
            bit("credit_note", None),
            text("name", None),
            text("source", None),
            text("description", None),
            uid("manager_id", None),
            utc("created_at", "recorded_at"),
            utc("updated_at", "updated_at"),
            derived("holder_id", "uuid"),
            derived("kind", "int"),
            derived("expense_item_id", "uuid"),
            derived("units", "numeric", scale=3, precision=12),
            derived("unit_amount", "numeric", scale=2, precision=14),
            derived("payee", "text"),
            derived("note", "text"),
            fixed("reimbursable", "bool", False),
            derived("status", "int"),
            fixed("sent_back_note", "text", None),
            fixed("reject_reason", "text", None),
            fixed("reopen_reason", "text", None),
            derived("reviewed_by", "uuid"),
            derived("reviewed_at", "timestamptz"),
            derived("recorded_by", "uuid"),
            derived("updated_by", "uuid"),
            fixed("removed_by", "uuid", None),
            fixed("removed_at", "timestamptz", None),
            fixed("removal_reason", "text", None),
            fixed("version", "int", 1),
            fixed("group_id", "uuid", None),
            fixed("group_total", "numeric", None),
            fixed("group_units", "numeric", None),
            fixed("group_unit_amount", "numeric", None),
        ),
        drops=("zero_amount",),
        convert=("petty_cash",),
    ),
)

_BY_SOURCE = {t.source: t for t in TABLES if t.source is not None}


def _of(name: str) -> tuple[Column, ...]:
    return _BY_SOURCE[name].source_columns


EXTRACTS: tuple[Extract, ...] = (
    Extract("users", "users", "SELECT * FROM public.users", _of("users")),
    Extract(
        "roles",
        "roles",
        "SELECT * FROM public.roles",
        (
            uid("id", None),
            text("title", None),
            jsonb("permissions", None),
            bit("is_system_role", None),
        ),
        REPLACED,
        "roles",
    ),
    Extract(
        "permissions",
        "permissions",
        "SELECT * FROM public.permissions",
        (uid("id", None), text("title", None)),
        REPLACED,
        "permissions",
    ),
    Extract("vehicles", "vehicles", "SELECT * FROM public.vehicles", _of("vehicles")),
    Extract("categories", "categories", "SELECT * FROM public.categories", _of("categories")),
    Extract("entries", "entries", "SELECT * FROM public.entries", _of("entries")),
    Extract(
        "records_revenue",
        "records",
        "SELECT r.* FROM public.records AS r JOIN public.entries AS e ON e.id = r.entry_id "
        "WHERE r.petty_cash_id IS NULL AND e.factor = 'plus'",
        _of("records_revenue"),
    ),
    Extract(
        "records_expenses",
        "records",
        "SELECT r.* FROM public.records AS r LEFT JOIN public.entries AS e ON e.id = r.entry_id "
        "WHERE r.petty_cash_id IS NULL AND e.factor IS DISTINCT FROM 'plus'",
        _of("records_expenses"),
    ),
    Extract(
        "records_copies",
        "records",
        "SELECT r.* FROM public.records AS r WHERE r.petty_cash_id IS NOT NULL",
        (
            uid("id", None),
            uid("petty_cash_id", None),
            uid("vehicle_id", None),
            uid("entry_id", None),
            day("date", None),
            money("minus", None),
            money("quantity", None, precision=12, scale=3),
        ),
        DROPPED,
        "petty_cash_copy",
    ),
    Extract("petty_cash", "petty_cash", "SELECT * FROM public.petty_cash", _of("petty_cash")),
    Extract(
        "petty_cash_daily_balances",
        "petty_cash_daily_balances",
        "SELECT * FROM public.petty_cash_daily_balances",
        (
            uid("id", None),
            day("date", None),
            money("opening_balance", None),
            money("closing_balance", None),
        ),
        DROPPED,
        "daily_balance",
    ),
    Extract(
        "provisions",
        "provisions",
        "SELECT * FROM public.provisions",
        (
            uid("id", None),
            uid("vehicle_id", None),
            money("amount", None),
            text("entry_type", None),
            day("date", None),
            money("balance_after", None),
        ),
        DROPPED,
        "provision",
    ),
    Extract(
        "budgets",
        "budgets",
        "SELECT * FROM public.budgets",
        (
            uid("id", None),
            uid("vehicle_id", None),
            uid("category_id", None),
            integer("year", None),
            integer("month", None),
            money("budget", None),
            money("actual", None),
        ),
        DROPPED,
        "budget",
    ),
)

COUNTED: tuple[tuple[str, str], ...] = (
    ("password_reset_codes", "reset codes of the old e-mail sign-in; everyone signs in afresh"),
    ("alembic_version", "the old application's schema version, checked by the extract"),
)
"""Legacy tables the extract counts but does not read: none of their rows moves."""

LEGACY_TABLES: tuple[str, ...] = (
    "users",
    "roles",
    "permissions",
    "vehicles",
    "categories",
    "entries",
    "records",
    "petty_cash",
    "petty_cash_daily_balances",
    "provisions",
    "budgets",
    "password_reset_codes",
    "alembic_version",
)

RULES: Mapping[str, str] = {
    "income_category": "a plus category: it holds only Earnings, which becomes revenue (7.3 row 9)",
    "revenue_item": "a plus item: Earnings becomes revenue, the others are unused (7.3 row 11)",
    "uncategorised_item": (
        "an item without a category: held back with its deductions until the owner decides "
        "(7.3 row 10, question 96)"
    ),
    "merged_item": (
        "a second item whose name folds to one already in its category: merged into the first "
        "(7.3 row 11)"
    ),
    "double_entry": (
        "a second revenue row for the same vehicle, day and amount: the one entered first is "
        "kept (7.3 row 12, question 92)"
    ),
    "zero_amount": (
        "a petty-cash row of amount 0: it moves no money and the target refuses a zero total "
        "(7.3 row 14)"
    ),
    "petty_cash_copy": (
        "the copy of a committed petty-cash expense; the original moves and the vehicle report "
        "posts it (7.3)"
    ),
    "daily_balance": "the target computes the float from the entries; compared in 7.5 (7.3)",
    "provision": "the saving model starts empty; balance listed for the owner (question 97)",
    "budget": "the target has no budgets; budgets listed for the owner (question 97)",
    "roles": "replaced by the four roles (7.4)",
    "permissions": "replaced by the 59-right catalogue (7.4)",
}

HELD_BACK = {
    "uncategorised": "held back: its item has no category (question 96)",
    "no_vehicle": "held back: a petty-cash expense needs a vehicle (question 95)",
    "differing_day": "held back: two different revenue amounts on one vehicle and day (7.3 row 12)",
    "no_person": "the person has no row in --people (questions 90 and 98)",
    "no_number": "the person has no number in --people (question 90)",
    "bad_number": "the number in --people is not a Kenyan mobile number",
    "bad_email": "the e-mail in --people is not an e-mail address",
    "inexact_unit": "the amount does not divide by the quantity to the cent",
    "total_differs": (
        "unit price times quantity does not give the amount exactly in whole cents, so the "
        "target's total would differ"
    ),
}

RIGHTS: Mapping[str, tuple[str, ...]] = {
    "dashboard:read": ("dash.net",),
    "dashboard:overview": ("dash.net",),
    "dashboard:financial": ("dash.net",),
    "dashboard:vehicles": ("dash.gaps",),
    "dashboard:petty_cash": ("dash.pettycash",),
    "records:read": ("revenue.view", "expenses.view"),
    "records:write": ("revenue.capture", "expenses.capture"),
    "records:delete": ("revenue.correct", "expenses.correct"),
    "records:lock": ("revenue.correct", "expenses.correct"),
    "categories:read": ("catalog.view",),
    "entries:read": ("catalog.view",),
    "categories:write": ("catalog.add", "catalog.edit"),
    "entries:write": ("catalog.add", "catalog.edit"),
    "categories:delete": ("catalog.stop",),
    "entries:delete": ("catalog.stop",),
    "vehicles:read": ("vehicles.view", "companies.view"),
    "vehicles:write": (
        "vehicles.add",
        "vehicles.edit",
        "vehicles.target",
        "companies.add",
        "companies.edit",
    ),
    "petty_cash:read": ("pettycash.view", "pettycash.view_all"),
    "petty_cash:write_expense": ("pettycash.spend", "pettycash.edit_own"),
    "petty_cash:write_cash": ("pettycash.issue", "pettycash.issue_negative"),
    "petty_cash:write_credit_note": ("pettycash.credit",),
    "petty_cash:commit": (
        "pettycash.approve_item",
        "pettycash.approve_day",
        "pettycash.send_back",
        "pettycash.reject",
        "pettycash.reopen",
    ),
    "petty_cash:delete": ("pettycash.delete", "pettycash.delete_approved", "pettycash.delete_cash"),
    "petty_cash:reconcile": ("pettycash.reports",),
    "reports:petty_cash": ("pettycash.reports",),
    "provisions:read": ("savings.view",),
    "provisions:write": ("savings.add", "savings.edit"),
    "provisions:delete": ("savings.pause",),
    "reports:read": ("reports.view",),
    "reports:income": ("reports.view",),
    "reports:expenses": ("reports.view",),
    "reports:print": ("reports.view",),
    "statements:read": ("reports.view",),
    "reports:export": ("reports.export", "revenue.export", "expenses.export", "pettycash.export"),
    "users:read": ("people.view",),
    "roles:read": ("people.view",),
    "permissions:read": ("people.view",),
    "users:write": ("people.add", "people.edit", "people.block", "people.sign_in"),
    "roles:write": ("people.add", "people.edit", "people.block", "people.sign_in"),
    "roles:delete": ("people.add", "people.edit", "people.block", "people.sign_in"),
    "budgets:read": (),
    "budgets:write": (),
    "reports:budget": (),
}
"""Legacy permission names to rights (``docs/10`` 7.4); an empty tuple is a name with no right
(no budgets in the target), a name missing here is unknown: both are listed as not carried."""
