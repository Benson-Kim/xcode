"""The table map of ``docs/10-data-migration.md`` section 3, as data.

One :class:`Table` per target table, in foreign-key load order: a table may reference an
earlier one, never a later one. A column names its SQL Server column and type, its PostgreSQL
column and kind, and either a fixed value or nothing (a conversion fills it). ``drops`` are
the documented predicates for rows that are not moved; ``convert`` names the conversions of
``conversions.py`` that run over the table's rows after the column mapping. The code iterates
over :data:`TABLES`: adding a table is adding a record here (and a conversion if it needs one).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

EXTRACTED_AT = "<extracted-at>"
"""A column the source does not have that takes the extraction instant."""

DERIVED = "<derived>"
"""A column a conversion fills."""

_TARGET_KIND = {
    "uuid": "uuid",
    "text": "text",
    "json": "jsonb",
    "bit": "bool",
    "int": "int",
    "bigint": "int",
    "decimal": "numeric",
    "date": "date",
    "datetime2": "timestamptz",
    "datetimeoffset": "timestamptz",
    "binary": "bytea",
    "float": "float8",
}


@dataclass(frozen=True, slots=True)
class Column:
    target: str | None
    source: str | None = None
    src: str = ""
    kind: str = ""
    scale: int | None = None
    precision: int | None = None
    values: Mapping[str, object] | None = None
    const: object = DERIVED

    @property
    def fixed(self) -> bool:
        return self.source is None and self.const is not DERIVED


@dataclass(frozen=True, slots=True)
class Table:
    order: int
    source: str | None
    target: str
    key: tuple[str, ...]
    target_key: tuple[str, ...]
    columns: tuple[Column, ...]
    drops: tuple[str, ...] = ()
    convert: tuple[str, ...] = ()
    since: int = 1
    reads: tuple[str, ...] = field(default=())

    @property
    def target_columns(self) -> tuple[Column, ...]:
        return tuple(c for c in self.columns if c.target is not None)

    @property
    def source_columns(self) -> tuple[Column, ...]:
        return tuple(c for c in self.columns if c.source is not None)

    @property
    def schema(self) -> str:
        return self.target.split(".", 1)[0]

    @property
    def name(self) -> str:
        return self.target.split(".", 1)[1]


def _col(source: str, target: str | None, src: str, **extra: object) -> Column:
    kind = str(extra.pop("kind", _TARGET_KIND[src]))
    return Column(target=target, source=source, src=src, kind=kind, **extra)  # type: ignore[arg-type]


def uid(source: str, target: str | None) -> Column:
    return _col(source, target, "uuid")


def text(source: str, target: str | None) -> Column:
    return _col(source, target, "text")


def bit(source: str, target: str | None) -> Column:
    return _col(source, target, "bit")


def integer(source: str, target: str | None, values: Mapping[str, object] | None = None) -> Column:
    if values is not None:
        return _col(source, target, "int", kind="text", values=values)
    return _col(source, target, "int")


def code(source: str, target: str | None, values: Mapping[str, object]) -> Column:
    """An enumeration stored as an ``int`` whose target is a ``smallint`` code."""
    return _col(source, target, "int", values=values)


def big(source: str, target: str | None) -> Column:
    return _col(source, target, "bigint")


def money(source: str, target: str | None, precision: int = 14, scale: int = 2) -> Column:
    return _col(source, target, "decimal", precision=precision, scale=scale)


def day(source: str, target: str | None) -> Column:
    return _col(source, target, "date")


def utc(source: str, target: str | None) -> Column:
    return _col(source, target, "datetime2")


def instant(source: str, target: str | None) -> Column:
    return _col(source, target, "datetimeoffset")


def blob(source: str, target: str | None) -> Column:
    return _col(source, target, "binary")


def number(source: str, target: str | None) -> Column:
    return _col(source, target, "float")


def jsonb(source: str, target: str | None) -> Column:
    return _col(source, target, "json")


def fixed(target: str, kind: str, value: object) -> Column:
    return Column(target=target, kind=kind, const=value)


def derived(
    target: str, kind: str, scale: int | None = None, precision: int | None = None
) -> Column:
    return Column(target=target, kind=kind, scale=scale, precision=precision)


def created() -> tuple[Column, Column]:
    return fixed("created_at", "timestamptz", EXTRACTED_AT), fixed(
        "updated_at", "timestamptz", EXTRACTED_AT
    )


def _same(*values: int) -> dict[str, object]:
    return {str(v): v for v in values}


USER_STATUS = {"0": "active", "1": "removed"}
NO_EARNINGS_REASON = _same(1, 2, 3, 4)
RECURRING_KIND = _same(1, 2)
FREQUENCY = _same(1, 2, 3, 4)
BUCKET = _same(1, 2, 3)
PETTY_CASH_KIND = _same(1, 2, 3)
PETTY_CASH_STATUS = {"1": 1, "2": 2, "3": 1}
"""``SentBack`` (3) becomes a waiting expense with its note (``docs/04-schema.md`` 6.2, DEC-21)."""

ORG_KEY = ("OrganizationId", "Id")
ORG_TARGET_KEY = ("organization_id", "id")


TABLES: tuple[Table, ...] = (
    Table(
        1,
        "Users",
        "identity.users",
        ("Id",),
        ("id",),
        (
            uid("Id", "id"),
            text("Email", "email"),
            text("PhoneNumber", "phone_number"),
            text("PinHash", "pin_hash"),
            integer("Status", "status", USER_STATUS),
            integer("SecurityVersion", "security_version"),
            integer("FailedAttempts", "failed_attempts"),
            instant("PausedUntil", None),
            integer("UntrustedFailedAttempts", "untrusted_failed_attempts"),
            big("Version", "version"),
            *created(),
            fixed("pin_reset_required", "bool", False),
            fixed("last_signed_in_at", "timestamptz", None),
        ),
        convert=("user_email", "user_phone", "user_lock"),
    ),
    Table(
        2,
        "Organizations",
        "tenancy.organizations",
        ("Id",),
        ("id",),
        (
            uid("Id", "id"),
            text("Slug", "slug"),
            text("Name", "name"),
            day("BusinessDate", "business_date"),
            big("SettingsVersion", "settings_version"),
            *created(),
        ),
    ),
    Table(
        3,
        "Memberships",
        "tenancy.memberships",
        ("OrganizationId", "UserId"),
        ("organization_id", "user_id"),
        (
            uid("OrganizationId", "organization_id"),
            uid("UserId", "user_id"),
            text("FirstName", "first_name"),
            text("LastName", "last_name"),
            bit("Active", "active"),
            money("ApprovalLimit", "approval_limit"),
            big("Version", "version"),
            *created(),
            fixed("back_limit_mode", "text", "none"),
            fixed("back_limit_count", "int", None),
            fixed("back_limit_from", "date", None),
        ),
    ),
    Table(
        4,
        "Localizations",
        "tenancy.organization_localizations",
        ("OrganizationId",),
        ("organization_id",),
        (
            uid("OrganizationId", "organization_id"),
            text("Locale", "locale"),
            text("TimeZone", "time_zone"),
            text("DatePattern", "date_pattern"),
            bit("Hour12", "hour12"),
            integer("FirstDayOfWeek", "first_day_of_week"),
            text("WeekNumbering", "week_numbering"),
            text("Currency", "currency"),
            bit("UseGrouping", "use_grouping"),
            integer("NumberDecimals", "number_decimals"),
            bit("AllowLocaleOverride", "allow_locale_override"),
            bit("AllowTimeZoneOverride", "allow_time_zone_override"),
            bit("AllowHour12Override", "allow_hour12_override"),
            bit("AllowThemeOverride", "allow_theme_override"),
            *created(),
        ),
        convert=("time_zone",),
    ),
    Table(
        5,
        "Brandings",
        "tenancy.organization_brandings",
        ("OrganizationId",),
        ("organization_id",),
        (
            uid("OrganizationId", "organization_id"),
            text("DisplayName", "display_name"),
            text("LegalName", "legal_name"),
            text("LogoAlt", "logo_alt"),
            text("Primary", "primary_color"),
            text("Secondary", "secondary_color"),
            text("Accent", "accent_color"),
            text("LogoLight", "logo_light_url"),
            text("LogoDark", "logo_dark_url"),
            text("Favicon", "favicon_url"),
            text("TermsUrl", "terms_url"),
            text("PrivacyUrl", "privacy_url"),
            text("Domain", "domain"),
            text("SupportEmail", "support_email"),
            *created(),
        ),
        convert=("blank_optional_text",),
    ),
    Table(
        6,
        "Logos",
        "tenancy.organization_logos",
        ("OrganizationId",),
        ("organization_id",),
        (
            uid("OrganizationId", "organization_id"),
            text("ContentType", "content_type"),
            blob("Data", "data"),
            instant("UpdatedAt", "updated_at"),
        ),
    ),
    Table(
        7,
        "SecurityPolicies",
        "tenancy.organization_security_policies",
        ("OrganizationId",),
        ("organization_id",),
        (
            uid("OrganizationId", "organization_id"),
            integer("PasswordMinLength", "password_min_length"),
            bit("PasswordComplexity", "password_complexity"),
            integer("PasswordHistory", "password_history"),
            integer("PinLength", "pin_length"),
            integer("LockoutThreshold", "lockout_threshold"),
            integer("LockoutMinutes", "lockout_minutes"),
            integer("AccessTokenMinutes", "access_token_minutes"),
            integer("RefreshTokenDays", "refresh_token_days"),
            integer("IdleUnlockSeconds", "idle_unlock_seconds"),
            bit("AllowPinSignIn", "allow_pin_sign_in"),
            *created(),
        ),
        convert=("policy_bounds",),
    ),
    Table(
        8,
        "Roles",
        "tenancy.roles",
        ORG_KEY,
        ORG_TARGET_KEY,
        (
            uid("OrganizationId", "organization_id"),
            uid("Id", "id"),
            text("Name", "name"),
            fixed("created_at", "timestamptz", EXTRACTED_AT),
        ),
    ),
    Table(
        9,
        "PersonRoles",
        "tenancy.person_roles",
        ("OrganizationId", "UserId", "RoleId"),
        ("organization_id", "user_id"),
        (
            uid("OrganizationId", "organization_id"),
            uid("UserId", "user_id"),
            uid("RoleId", "role_id"),
            fixed("updated_at", "timestamptz", EXTRACTED_AT),
        ),
        drops=("no_membership",),
    ),
    Table(
        10,
        "PermissionOverrides",
        "tenancy.permission_overrides",
        ("OrganizationId", "UserId", "Permission"),
        ("organization_id", "user_id", "permission"),
        (
            uid("OrganizationId", "organization_id"),
            uid("UserId", "user_id"),
            text("Permission", "permission"),
            bit("Granted", "granted"),
        ),
        drops=("no_membership",),
        convert=("permission_translation",),
        reads=("Memberships", "PersonRoles", "Roles"),
    ),
    Table(
        11,
        "UserPreferences",
        "tenancy.user_preferences",
        ("OrganizationId", "UserId"),
        ("organization_id", "user_id"),
        (
            uid("OrganizationId", "organization_id"),
            uid("UserId", "user_id"),
            text("Locale", "locale"),
            text("TimeZone", "time_zone"),
            bit("Hour12", "hour12"),
            text("ThemeMode", "theme_mode"),
            bit("ReducedMotion", "reduced_motion"),
            number("FontScale", "font_scale"),
            *created(),
        ),
        drops=("no_membership",),
        convert=("time_zone",),
    ),
    Table(
        12,
        "PsvCompany",
        "setup.psv_companies",
        ORG_KEY,
        ORG_TARGET_KEY,
        (
            uid("OrganizationId", "organization_id"),
            uid("Id", "id"),
            text("Name", "name"),
            text("NormalizedName", None),
            day("ArchivedOn", "archived_on"),
            *created(),
        ),
        convert=("normalized_name",),
    ),
    Table(
        13,
        "FleetVehicle",
        "setup.fleet_vehicles",
        ORG_KEY,
        ORG_TARGET_KEY,
        (
            uid("OrganizationId", "organization_id"),
            uid("Id", "id"),
            uid("CompanyId", "company_id"),
            text("Registration", "registration"),
            day("JoinedOn", "joined_on"),
            day("LeftOn", "left_on"),
            *created(),
            derived("fleet_number", "text"),
            fixed("initial_investment", "numeric", None),
        ),
        convert=("fleet_number",),
    ),
    Table(
        14,
        None,
        "setup.expense_main_categories",
        ("OrganizationId", "Bucket"),
        ORG_TARGET_KEY,
        (
            derived("organization_id", "uuid"),
            derived("id", "uuid"),
            derived("name", "text"),
            *created(),
        ),
        convert=("main_categories",),
        since=10,
        reads=("ExpenseCategory",),
    ),
    Table(
        15,
        "ExpenseCategory",
        "setup.expense_categories",
        ORG_KEY,
        ORG_TARGET_KEY,
        (
            uid("OrganizationId", "organization_id"),
            uid("Id", "id"),
            text("Name", "name"),
            text("NormalizedName", None),
            code("Bucket", "bucket", BUCKET),
            day("StoppedOn", "stopped_on"),
            *created(),
            derived("main_category_id", "uuid"),
        ),
        convert=("normalized_name", "main_category"),
    ),
    Table(
        16,
        "ExpenseItem",
        "setup.expense_items",
        ORG_KEY,
        ORG_TARGET_KEY,
        (
            uid("OrganizationId", "organization_id"),
            uid("Id", "id"),
            uid("CategoryId", "category_id"),
            text("Name", "name"),
            text("NormalizedName", None),
            day("StoppedOn", "stopped_on"),
            *created(),
        ),
        convert=("normalized_name",),
    ),
    Table(
        17,
        "VehicleTarget",
        "setup.vehicle_target_sets",
        ORG_KEY,
        ORG_TARGET_KEY,
        (
            uid("OrganizationId", "organization_id"),
            uid("Id", "id"),
            uid("VehicleId", "vehicle_id"),
            day("EffectiveFrom", "starts_on"),
            integer("Revision", None),
            money("WeeklyAmount", None),
            *(
                derived(d, "numeric", scale=2, precision=14)
                for d in (
                    "monday",
                    "tuesday",
                    "wednesday",
                    "thursday",
                    "friday",
                    "saturday",
                    "sunday",
                )
            ),
            fixed("created_at", "timestamptz", EXTRACTED_AT),
            fixed("created_by", "uuid", None),
        ),
        convert=("target_sets",),
        since=10,
    ),
    Table(
        18,
        "VehicleAwayPeriod",
        "setup.vehicle_away_periods",
        ORG_KEY,
        ORG_TARGET_KEY,
        (
            uid("OrganizationId", "organization_id"),
            uid("Id", "id"),
            uid("VehicleId", "vehicle_id"),
            day("LeftOn", "left_on"),
            day("ReturnedOn", "returned_on"),
            fixed("created_at", "timestamptz", EXTRACTED_AT),
        ),
    ),
    Table(
        19,
        "VehicleInvestment",
        "setup.vehicle_investments",
        ORG_KEY,
        ORG_TARGET_KEY,
        (
            uid("OrganizationId", "organization_id"),
            uid("Id", "id"),
            uid("VehicleId", "vehicle_id"),
            day("Date", "invested_on"),
            text("Description", "description"),
            money("Amount", "amount"),
            uid("RecordedBy", "recorded_by"),
            instant("RecordedAt", "recorded_at"),
            fixed("updated_at", "timestamptz", EXTRACTED_AT),
        ),
    ),
    Table(
        20,
        "SetupDataScopes",
        "tenancy.data_scopes",
        ("OrganizationId", "UserId"),
        ("organization_id", "user_id"),
        (
            uid("OrganizationId", "organization_id"),
            uid("UserId", "user_id"),
            bit("AllCompanies", "all_companies"),
            fixed("updated_at", "timestamptz", EXTRACTED_AT),
        ),
        drops=("no_membership",),
    ),
    Table(
        21,
        "SetupCompanyScopes",
        "tenancy.data_scope_companies",
        ("OrganizationId", "UserId", "CompanyId"),
        ("organization_id", "user_id", "company_id"),
        (
            uid("OrganizationId", "organization_id"),
            uid("UserId", "user_id"),
            uid("CompanyId", "company_id"),
        ),
        drops=("no_membership",),
    ),
    Table(
        22,
        "SetupVehicleScopes",
        "tenancy.data_scope_vehicles",
        ("OrganizationId", "UserId", "VehicleId"),
        ("organization_id", "user_id", "vehicle_id"),
        (
            uid("OrganizationId", "organization_id"),
            uid("UserId", "user_id"),
            uid("VehicleId", "vehicle_id"),
        ),
        drops=("no_membership",),
    ),
    Table(
        23,
        "RecurringItem",
        "setup.recurring_items",
        ORG_KEY,
        ORG_TARGET_KEY,
        (
            uid("OrganizationId", "organization_id"),
            uid("Id", "id"),
            day("StoppedFrom", "stopped_from"),
            *created(),
        ),
    ),
    Table(
        24,
        "RecurringVersion",
        "setup.recurring_versions",
        ORG_KEY,
        ORG_TARGET_KEY,
        (
            uid("OrganizationId", "organization_id"),
            uid("Id", "id"),
            uid("ItemId", "item_id"),
            integer("Revision", "revision"),
            day("EffectiveFrom", "effective_from"),
            text("Name", "name"),
            code("Kind", "kind", RECURRING_KIND),
            money("Amount", "amount"),
            code("Frequency", "frequency", FREQUENCY),
            integer("Day", "day"),
            bit("LastDay", "last_day"),
            integer("Month", "month"),
            day("Start", "start_on"),
            day("End", "end_on"),
            uid("ExpenseItemId", "expense_item_id"),
            code("Bucket", "bucket", BUCKET),
            text("Note", "note"),
            fixed("created_at", "timestamptz", EXTRACTED_AT),
        ),
        convert=("allocation_sums",),
        reads=("RecurringAllocation",),
    ),
    Table(
        25,
        "RecurringAllocation",
        "setup.recurring_allocations",
        ORG_KEY,
        ORG_TARGET_KEY,
        (
            uid("OrganizationId", "organization_id"),
            uid("Id", "id"),
            uid("VersionId", "version_id"),
            uid("VehicleId", "vehicle_id"),
            money("Amount", "amount"),
        ),
    ),
    Table(
        26,
        "RevenueRecords",
        "revenue.records",
        ORG_KEY,
        ORG_TARGET_KEY,
        (
            uid("OrganizationId", "organization_id"),
            uid("Id", "id"),
            uid("VehicleId", "vehicle_id"),
            day("BusinessDate", "business_date"),
            money("Amount", "amount"),
            code("Reason", "reason", NO_EARNINGS_REASON),
            text("Note", "note"),
            instant("CapturedAt", "captured_at"),
            uid("CapturedBy", "captured_by"),
            instant("UpdatedAt", "updated_at"),
            uid("UpdatedBy", "updated_by"),
            bit("CorrectedAfterDate", "corrected_after_date"),
            big("Version", "version"),
        ),
    ),
    Table(
        27,
        "PettyCashEntries",
        "pettycash.entries",
        ORG_KEY,
        ORG_TARGET_KEY,
        (
            uid("OrganizationId", "organization_id"),
            uid("Id", "id"),
            uid("HolderId", "holder_id"),
            code("Kind", "kind", PETTY_CASH_KIND),
            day("Date", "entry_date"),
            uid("VehicleId", "vehicle_id"),
            uid("ExpenseItemId", "expense_item_id"),
            money("Units", "units", precision=12, scale=3),
            money("UnitAmount", "unit_amount"),
            money("Total", None),
            text("Payee", "payee"),
            text("Note", "note"),
            bit("Reimbursable", "reimbursable"),
            code("Status", "status", PETTY_CASH_STATUS),
            text("SentBackNote", "sent_back_note"),
            fixed("reject_reason", "text", None),
            fixed("reopen_reason", "text", None),
            uid("ReviewedBy", "reviewed_by"),
            instant("ReviewedAt", "reviewed_at"),
            uid("RecordedBy", "recorded_by"),
            instant("RecordedAt", "recorded_at"),
            uid("UpdatedBy", "updated_by"),
            instant("UpdatedAt", "updated_at"),
            uid("RemovedBy", "removed_by"),
            instant("RemovedAt", "removed_at"),
            text("RemovalReason", "removal_reason"),
            big("Version", "version"),
        ),
        convert=("petty_cash_review", "computed_total"),
        since=12,
    ),
    Table(
        28,
        "CentralExpenses",
        "expenses.entries",
        ORG_KEY,
        ORG_TARGET_KEY,
        (
            uid("OrganizationId", "organization_id"),
            uid("Id", "id"),
            day("Date", "entry_date"),
            uid("VehicleId", "vehicle_id"),
            uid("ExpenseItemId", "expense_item_id"),
            money("Units", "units", precision=12, scale=3),
            money("UnitAmount", "unit_amount"),
            money("Total", None),
            text("Note", "note"),
            uid("GroupId", "group_id"),
            integer("GroupSize", "group_size"),
            money("GroupTotal", "group_total"),
            money("GroupUnits", "group_units", precision=12, scale=3),
            money("GroupUnitAmount", "group_unit_amount"),
            uid("RecordedBy", "recorded_by"),
            instant("RecordedAt", "recorded_at"),
            uid("UpdatedBy", "updated_by"),
            instant("UpdatedAt", "updated_at"),
            uid("RemovedBy", "removed_by"),
            instant("RemovedAt", "removed_at"),
            text("RemovalReason", "removal_reason"),
            big("Version", "version"),
        ),
        convert=("trimmed_note", "computed_total"),
        since=13,
    ),
    Table(
        29,
        "RecurringPause",
        "setup.recurring_pauses",
        ORG_KEY,
        ORG_TARGET_KEY,
        (
            uid("OrganizationId", "organization_id"),
            uid("Id", "id"),
            uid("ItemId", "item_id"),
            day("From", "paused_from"),
            day("Through", "paused_through"),
            *created(),
        ),
        since=13,
    ),
    Table(
        30,
        "OrganizationSettingsVersion",
        "tenancy.change_log",
        ORG_KEY,
        ("organization_id", "version"),
        (
            uid("OrganizationId", "organization_id"),
            big("Version", "version"),
            uid("Id", "id"),
            text("Section", "section"),
            uid("EntityId", "entity_id"),
            uid("VehicleId", "vehicle_id"),
            uid("ActorId", "actor_id"),
            text("Reason", "reason"),
            utc("OccurredAt", "occurred_at"),
            utc("EffectiveFrom", "effective_from"),
            text("Before", "before"),
            text("After", "after"),
            text("CorrelationId", "request_id"),
        ),
    ),
    Table(
        31,
        "AuditEvents",
        "tenancy.audit_events",
        ORG_KEY,
        ORG_TARGET_KEY,
        (
            uid("OrganizationId", "organization_id"),
            uid("Id", None),
            derived("id", "int"),
            uid("ActorId", "actor_id"),
            text("Action", "action"),
            text("Entity", "entity"),
            jsonb("Before", "before"),
            jsonb("After", "after"),
            instant("OccuredAt", "occurred_at"),
            text("CorrelationId", "request_id"),
        ),
        convert=("audit_ids", "json_keys"),
    ),
    Table(
        32,
        "TrustedDevices",
        "identity.trusted_devices",
        ("Id",),
        ("id",),
        (
            uid("Id", "id"),
            uid("UserId", "user_id"),
            text("DeviceId", "device_id"),
            bit("Revoked", "revoked"),
            instant("TrustExpiresAt", "trust_expires_at"),
            *created(),
            fixed("token_hash", "text", None),
            fixed("name", "text", None),
            derived("trusted_at", "timestamptz"),
            derived("last_used_at", "timestamptz"),
            fixed("remembered", "bool", True),
        ),
        convert=("device_dates",),
        reads=("RefreshTokens", "Memberships", "SecurityPolicies"),
    ),
    Table(
        33,
        "RefreshTokens",
        "identity.refresh_tokens",
        ("Id",),
        ("id",),
        (
            uid("Id", "id"),
            uid("UserId", "user_id"),
            text("DeviceId", "device_id"),
            text("TokenHash", "token_hash"),
            instant("ExpiresAt", "expires_at"),
            bit("Revoked", "revoked"),
            big("Version", "version"),
            *created(),
        ),
        drops=("revoked_token", "expired_token"),
    ),
)

NOT_MIGRATED: tuple[tuple[str, str], ...] = (
    (
        "VerificationCodes",
        "codes live 10 minutes; nobody needs one across the cutover (question 12)",
    ),
    ("RolePermissions", "legacy table, dropped in docs/04-schema.md section 1"),
    ("RecurringKindLookup", "code table seeded by migration 0005 with the same integers"),
    ("RecurrenceFrequencyLookup", "code table seeded by migration 0005 with the same integers"),
    ("ExpenseBucketLookup", "code table seeded by migration 0005 with the same integers"),
    ("__EFMigrationsHistory", "ops.schema_migrations starts at the PostgreSQL baseline"),
)
"""Source tables the extract counts but does not copy: their rows are dropped by design."""

DROP_REASONS: Mapping[str, str] = {
    "no_membership": "the person has no membership in the organization (docs/10 3)",
    "revoked_token": "a revoked refresh token is never usable (question 12)",
    "expired_token": "a refresh token past its expiry at the extraction instant (question 12)",
    "unknown_permission": "a key that is not in the .NET catalogue (docs/10 section 3 row 10)",
    "superseded_target": "a lower revision of a weekly target dated the same day (docs/10 3.1)",
    "target_too_small": (
        "a weekly target too small to split into seven positive cents; the owner enters it "
        "(docs/10 3.1)"
    ),
    "translated_override": (
        "an old override; the person's rights are rewritten through the grant translation "
        "(docs/10 3.1)"
    ),
}


def by_source() -> dict[str, Table]:
    return {t.source: t for t in TABLES if t.source is not None}


def source_tables() -> tuple[str, ...]:
    """Every SQL Server table the extract reads, in load order, then the read-only ones."""
    names: list[str] = [t.source for t in TABLES if t.source is not None]
    return tuple(names)
