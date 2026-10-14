"""The expected schema of ``docs/04-schema.md`` sections 1, 2 and 9 as data.

``db/verify.py`` compares the live database against these declarations; nothing here holds
SQL. A new table, index or code table is one entry here plus its migration.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, StrEnum

from ..domain.identity import (
    CodePurpose,
    SignInOperation,
    SignInOutcome,
    SignInRefusal,
    UserStatus,
)
from ..domain.pettycash import PettyCashKind, PettyCashStatus
from ..domain.revenue import NoEarningsReason
from ..domain.setup import (
    ConditionDays,
    ExpenseBucket,
    RecurrenceFrequency,
    RecurringKind,
    SavingRunState,
)
from ..domain.tenancy import (
    BackLimitMode,
    ChangeLogSection,
    DatePattern,
    LogoContentType,
    PermissionSection,
    RoleName,
    ThemeMode,
    WeekNumbering,
)
from ..domain.values import CodedEnum


class TableKind(StrEnum):
    DATA = "data"
    AUDIT = "audit"
    CODE = "code"
    CATALOGUE = "catalogue"


_WRITE_PRIVILEGES = {"I": "INSERT", "U": "UPDATE", "D": "DELETE"}


@dataclass(frozen=True, slots=True)
class TableSpec:
    schema: str
    name: str
    primary_key: tuple[str, ...]
    writes: str = ""
    kind: TableKind = TableKind.DATA
    tenant: bool = True

    @property
    def qualified(self) -> str:
        return f"{self.schema}.{self.name}"

    @property
    def tenant_column(self) -> str:
        return "id" if self.qualified == "tenancy.organizations" else "organization_id"

    def executor_privileges(self) -> frozenset[str]:
        return frozenset({"SELECT", *(_WRITE_PRIVILEGES[c] for c in self.writes)})

    def readonly_privileges(self) -> frozenset[str]:
        if self.kind in (TableKind.CODE, TableKind.CATALOGUE):
            return frozenset({"SELECT"})
        return frozenset()


def _identity(name: str, writes: str, kind: TableKind = TableKind.DATA) -> TableSpec:
    return TableSpec("identity", name, ("id",), writes, kind, tenant=False)


def _code(schema: str, name: str) -> TableSpec:
    return TableSpec(schema, name, ("code",), "", TableKind.CODE, tenant=False)


def _org(schema: str, name: str, writes: str, *key: str) -> TableSpec:
    kind = TableKind.AUDIT if name in ("change_log", "audit_events") else TableKind.DATA
    return TableSpec(schema, name, ("organization_id", *key), writes, kind)


TABLES: tuple[TableSpec, ...] = (
    _identity("users", "IU"),
    _identity("verification_codes", "IU"),
    _identity("trusted_devices", "IU"),
    _identity("refresh_tokens", "IU"),
    _identity("sign_in_attempts", "I", TableKind.AUDIT),
    TableSpec("tenancy", "organizations", ("id",), "IU"),
    _org("tenancy", "memberships", "IU", "user_id"),
    _org("tenancy", "organization_localizations", "IU"),
    _org("tenancy", "organization_brandings", "IU"),
    _org("tenancy", "organization_logos", "IUD"),
    _org("tenancy", "organization_security_policies", "IU"),
    _org("tenancy", "organization_revenue_settings", "IU"),
    _org("tenancy", "user_preferences", "IU", "user_id"),
    _org("tenancy", "roles", "I", "id"),
    _org("tenancy", "person_roles", "IU", "user_id"),
    _org("tenancy", "permission_overrides", "IUD", "user_id", "permission"),
    TableSpec("tenancy", "permissions", ("key",), "", TableKind.CATALOGUE, tenant=False),
    TableSpec(
        "tenancy",
        "permission_dependencies",
        ("permission", "needs"),
        "",
        TableKind.CATALOGUE,
        tenant=False,
    ),
    TableSpec(
        "tenancy",
        "role_defaults",
        ("role_name", "permission"),
        "",
        TableKind.CATALOGUE,
        tenant=False,
    ),
    TableSpec(
        "tenancy",
        "permission_sources",
        ("permission", "source"),
        "",
        TableKind.CATALOGUE,
        tenant=False,
    ),
    TableSpec(
        "tenancy",
        "permission_translations",
        ("old_key", "new_key"),
        "",
        TableKind.CATALOGUE,
        tenant=False,
    ),
    _org("tenancy", "data_scopes", "IUD", "user_id"),
    _org("tenancy", "data_scope_companies", "ID", "user_id", "company_id"),
    _org("tenancy", "data_scope_vehicles", "ID", "user_id", "vehicle_id"),
    _org("tenancy", "change_log", "I", "version"),
    _org("tenancy", "audit_events", "I", "id"),
    _org("setup", "psv_companies", "IU", "id"),
    _org("setup", "fleet_vehicles", "IU", "id"),
    _org("setup", "vehicle_target_sets", "IUD", "id"),
    _org("setup", "vehicle_away_periods", "I", "id"),
    _org("setup", "vehicle_investments", "IUD", "id"),
    _org("setup", "recurring_items", "IU", "id"),
    _org("setup", "recurring_versions", "I", "id"),
    _org("setup", "recurring_allocations", "I", "id"),
    _org("setup", "expense_main_categories", "IU", "id"),
    _org("setup", "expense_categories", "IU", "id"),
    _org("setup", "expense_items", "IU", "id"),
    _code("setup", "recurring_kinds"),
    _code("setup", "recurrence_frequencies"),
    _code("setup", "expense_buckets"),
    _org("revenue", "records", "IU", "id"),
    _code("revenue", "no_earnings_reasons"),
    _org("pettycash", "entries", "IU", "id"),
    _code("pettycash", "kinds"),
    _code("pettycash", "statuses"),
    _org("expenses", "entries", "IU", "id"),
    _org("setup", "recurring_pauses", "IU", "id"),
    _org("setup", "saving_openings", "IUD", "item_id"),
    _org("setup", "saving_opening_amounts", "IUD", "item_id", "vehicle_id"),
    _org("setup", "saving_runs", "I", "item_id", "run_on", "vehicle_id"),
    _code("setup", "saving_run_states"),
)

# Schemas whose every table must be declared in TABLES (ops belongs to the runner).
SPECIFIED_SCHEMAS = ("identity", "tenancy", "setup", "revenue", "pettycash", "expenses")


@dataclass(frozen=True, slots=True)
class IndexSpec:
    """An index as ``pg_get_indexdef`` renders its key list (``DESC`` and expressions
    included), plus uniqueness, partial predicate and access method."""

    table: str
    keys: str
    unique: bool = False
    where: str | None = None
    method: str = "btree"


INDEXES: tuple[IndexSpec, ...] = (
    IndexSpec("identity.users", "email", unique=True),
    IndexSpec("identity.users", "phone_number", unique=True),
    IndexSpec("identity.verification_codes", "user_id, purpose, created_at DESC"),
    IndexSpec("identity.trusted_devices", "user_id, device_id", unique=True),
    IndexSpec("identity.refresh_tokens", "token_hash", unique=True),
    IndexSpec("identity.refresh_tokens", "user_id, device_id"),
    IndexSpec("identity.sign_in_attempts", "user_id, occurred_at DESC"),
    IndexSpec("identity.sign_in_attempts", "phone_digest, occurred_at DESC"),
    IndexSpec("tenancy.organizations", "slug", unique=True),
    IndexSpec("tenancy.memberships", "user_id", unique=True, where="active"),
    IndexSpec("tenancy.memberships", "organization_id, last_name, first_name, user_id"),
    IndexSpec("tenancy.roles", "organization_id, lower(name)", unique=True),
    IndexSpec("tenancy.permissions", "group_order, item_order", unique=True),
    IndexSpec("tenancy.data_scope_companies", "organization_id, company_id"),
    IndexSpec("tenancy.data_scope_vehicles", "organization_id, vehicle_id"),
    IndexSpec("tenancy.change_log", "organization_id, id", unique=True),
    IndexSpec("tenancy.change_log", "organization_id, occurred_at"),
    IndexSpec("tenancy.change_log", "organization_id, section, vehicle_id"),
    IndexSpec("tenancy.change_log", "organization_id, actor_id"),
    IndexSpec("tenancy.audit_events", "organization_id, occurred_at"),
    IndexSpec("setup.recurring_kinds", "name", unique=True),
    IndexSpec("setup.recurrence_frequencies", "name", unique=True),
    IndexSpec("setup.expense_buckets", "name", unique=True),
    IndexSpec("setup.psv_companies", "organization_id, normalized_name", unique=True),
    IndexSpec("setup.fleet_vehicles", "organization_id, registration", unique=True),
    IndexSpec("setup.fleet_vehicles", "organization_id, company_id"),
    IndexSpec(
        "setup.fleet_vehicles",
        "organization_id, company_id, normalized_fleet_number",
        unique=True,
    ),
    IndexSpec("setup.vehicle_target_sets", "organization_id, vehicle_id, starts_on", unique=True),
    IndexSpec("setup.vehicle_away_periods", "organization_id, vehicle_id, left_on", unique=True),
    IndexSpec(
        "setup.vehicle_away_periods",
        "organization_id, vehicle_id, daterange(left_on, returned_on)",
        method="gist",
    ),
    IndexSpec("setup.vehicle_investments", "organization_id, vehicle_id, invested_on"),
    IndexSpec("setup.recurring_versions", "organization_id, item_id, revision", unique=True),
    IndexSpec("setup.recurring_versions", "organization_id, expense_item_id"),
    IndexSpec(
        "setup.recurring_allocations", "organization_id, version_id, vehicle_id", unique=True
    ),
    IndexSpec("setup.recurring_allocations", "organization_id, vehicle_id"),
    IndexSpec("setup.expense_main_categories", "organization_id, normalized_name", unique=True),
    IndexSpec("setup.expense_categories", "organization_id, normalized_name", unique=True),
    IndexSpec("setup.expense_categories", "organization_id, main_category_id"),
    IndexSpec("setup.expense_items", "organization_id, category_id, normalized_name", unique=True),
    IndexSpec("revenue.no_earnings_reasons", "name", unique=True),
    IndexSpec("revenue.records", "organization_id, vehicle_id, business_date", unique=True),
    IndexSpec("revenue.records", "organization_id, business_date"),
    IndexSpec("pettycash.kinds", "name", unique=True),
    IndexSpec("pettycash.statuses", "name", unique=True),
    IndexSpec("pettycash.entries", "organization_id, holder_id, entry_date"),
    IndexSpec(
        "pettycash.entries",
        "organization_id, status, entry_date",
        where="removed_at IS NULL",
    ),
    IndexSpec(
        "pettycash.entries",
        "organization_id, vehicle_id, entry_date",
        where="removed_at IS NULL",
    ),
    IndexSpec("pettycash.entries", "organization_id, expense_item_id"),
    IndexSpec("pettycash.entries", "organization_id, group_id, vehicle_id", unique=True),
    IndexSpec("expenses.entries", "organization_id, entry_date", where="removed_at IS NULL"),
    IndexSpec(
        "expenses.entries",
        "organization_id, vehicle_id, entry_date",
        where="removed_at IS NULL",
    ),
    IndexSpec("expenses.entries", "organization_id, expense_item_id"),
    IndexSpec("expenses.entries", "organization_id, group_id, vehicle_id", unique=True),
    IndexSpec(
        "setup.recurring_pauses",
        "organization_id, item_id",
        unique=True,
        where="paused_through IS NULL",
    ),
    IndexSpec(
        "setup.recurring_pauses",
        "organization_id, item_id, daterange(paused_from, (paused_through + 1), '[)'::text)",
        method="gist",
    ),
    IndexSpec("setup.saving_run_states", "name", unique=True),
    IndexSpec("setup.saving_runs", "organization_id, vehicle_id, run_on"),
)

# Code tables and the domain enum whose members (value, lower-case name, label) they hold.
CODE_TABLE_ENUMS: dict[str, type[CodedEnum]] = {
    "setup.recurring_kinds": RecurringKind,
    "setup.recurrence_frequencies": RecurrenceFrequency,
    "setup.expense_buckets": ExpenseBucket,
    "revenue.no_earnings_reasons": NoEarningsReason,
    "pettycash.kinds": PettyCashKind,
    "pettycash.statuses": PettyCashStatus,
    "setup.saving_run_states": SavingRunState,
}

# CHECK (column IN (...)) constraints and the domain enum whose values they list.
CHECK_LIST_ENUMS: dict[str, type[Enum]] = {
    "identity.users.ck_users_status": UserStatus,
    "identity.verification_codes.ck_verification_codes_purpose": CodePurpose,
    "identity.sign_in_attempts.ck_sign_in_attempts_operation": SignInOperation,
    "identity.sign_in_attempts.ck_sign_in_attempts_outcome": SignInOutcome,
    "identity.sign_in_attempts.ck_sign_in_attempts_refusal": SignInRefusal,
    "tenancy.organization_localizations.ck_localizations_date_pattern": DatePattern,
    "tenancy.organization_localizations.ck_localizations_week_numbering": WeekNumbering,
    "tenancy.organization_logos.ck_logos_content_type": LogoContentType,
    "tenancy.user_preferences.ck_user_preferences_theme_mode": ThemeMode,
    "tenancy.role_defaults.ck_role_defaults_role_name": RoleName,
    "tenancy.memberships.ck_memberships_back_limit_mode": BackLimitMode,
    "tenancy.permissions.ck_permissions_section": PermissionSection,
    "tenancy.change_log.ck_change_log_section": ChangeLogSection,
    "setup.recurring_versions.ck_recurring_versions_condition_days": ConditionDays,
}
