"""Tenancy vocabulary: organizations, memberships, settings, access and the change log.

Enumeration values are the wire strings and the values the ``tenancy`` tables constrain;
``Permission`` lists the 59 catalogue keys in catalogue order, ``RetiredPermission`` the keys
outside it that are derived for v2.11 phones. ``tests/db/test_enum_parity.py``
proves each enum against the database. The records below the enumerations are what the
tenancy routines return and take; their field names are the document keys of
``docs/05-routines.md`` section 1.3 (the wire names in snake case).
"""

from __future__ import annotations

import base64
import binascii
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID

from .errors import RuleViolation
from .identity import SignInStatus


class Permission(StrEnum):
    DASH_NET = "dash.net"
    DASH_GAPS = "dash.gaps"
    DASH_PETTY_CASH = "dash.pettycash"

    REVENUE_VIEW = "revenue.view"
    REVENUE_CAPTURE = "revenue.capture"
    REVENUE_CORRECT = "revenue.correct"
    REVENUE_EXPORT = "revenue.export"

    EXPENSES_VIEW = "expenses.view"
    EXPENSES_CAPTURE = "expenses.capture"
    EXPENSES_CORRECT = "expenses.correct"
    EXPENSES_EXPORT = "expenses.export"

    PETTY_CASH_VIEW = "pettycash.view"
    PETTY_CASH_VIEW_ALL = "pettycash.view_all"
    PETTY_CASH_REPORTS = "pettycash.reports"
    PETTY_CASH_EXPORT = "pettycash.export"
    PETTY_CASH_SPEND = "pettycash.spend"
    PETTY_CASH_SPEND_OTHER = "pettycash.spend_other"
    PETTY_CASH_EDIT_OWN = "pettycash.edit_own"
    PETTY_CASH_EDIT = "pettycash.edit"
    PETTY_CASH_DELETE_OWN = "pettycash.delete_own"
    PETTY_CASH_DELETE = "pettycash.delete"
    PETTY_CASH_DELETE_APPROVED = "pettycash.delete_approved"
    PETTY_CASH_SEND_BACK = "pettycash.send_back"
    PETTY_CASH_APPROVE_ITEM = "pettycash.approve_item"
    PETTY_CASH_APPROVE_DAY = "pettycash.approve_day"
    PETTY_CASH_REJECT = "pettycash.reject"
    PETTY_CASH_REOPEN = "pettycash.reopen"
    PETTY_CASH_ISSUE = "pettycash.issue"
    PETTY_CASH_ISSUE_NEGATIVE = "pettycash.issue_negative"
    PETTY_CASH_CREDIT = "pettycash.credit"
    PETTY_CASH_DELETE_CASH = "pettycash.delete_cash"

    SCHEDULED_VIEW = "scheduled.view"
    SCHEDULED_ADD = "scheduled.add"
    SCHEDULED_EDIT = "scheduled.edit"
    SCHEDULED_PAUSE = "scheduled.pause"

    SAVINGS_VIEW = "savings.view"
    SAVINGS_ADD = "savings.add"
    SAVINGS_EDIT = "savings.edit"
    SAVINGS_PAUSE = "savings.pause"

    REPORTS_VIEW = "reports.view"
    REPORTS_INVESTMENT = "reports.investment"
    REPORTS_EXPORT = "reports.export"

    COMPANIES_VIEW = "companies.view"
    COMPANIES_ADD = "companies.add"
    COMPANIES_EDIT = "companies.edit"

    VEHICLES_VIEW = "vehicles.view"
    VEHICLES_ADD = "vehicles.add"
    VEHICLES_EDIT = "vehicles.edit"
    VEHICLES_TARGET = "vehicles.target"

    CATALOG_VIEW = "catalog.view"
    CATALOG_ADD = "catalog.add"
    CATALOG_EDIT = "catalog.edit"
    CATALOG_STOP = "catalog.stop"

    PEOPLE_VIEW = "people.view"
    PEOPLE_ADD = "people.add"
    PEOPLE_EDIT = "people.edit"
    PEOPLE_BLOCK = "people.block"
    PEOPLE_SIGN_IN = "people.sign_in"

    AUDIT_VIEW = "audit.view"


class RetiredPermission(StrEnum):
    """Keys outside the catalogue that v2.11 phones still read: a member holds one while
    holding any of its sources (``tenancy.permission_sources``); nobody is granted one."""

    DASH_CAPTURE = "dash.capture"
    DASH_FLOAT = "dash.float"
    DASH_REVENUE = "dash.revenue"
    DASH_COSTS = "dash.costs"
    DASH_COMMITMENTS = "dash.commitments"
    DASH_INVESTMENT = "dash.investment"
    DASH_EDITS = "dash.edits"
    REVENUE_NO_EARNINGS = "revenue.no_earnings"
    EXPENSES_SETUP = "expenses.setup"
    BILLS_VIEW = "bills.view"
    BILLS_CAPTURE = "bills.capture"
    BILLS_APPROVE = "bills.approve"
    COMMITMENTS_VIEW = "commitments.view"
    COMMITMENTS_MANAGE = "commitments.manage"
    COMPANIES_MANAGE = "companies.manage"
    VEHICLES_MANAGE = "vehicles.manage"
    INVEST_VIEW = "invest.view"
    INVEST_MANAGE = "invest.manage"
    PEOPLE_MANAGE = "people.manage"
    ACCESS_MANAGE = "access.manage"


ORGANIZATION_MANAGE = "organization.manage"
"""The hidden key of the organization settings: an Owner role default, never in the
catalogue and never granted."""


class PermissionSection(StrEnum):
    """The sections of the petty-cash card in the person form (``tenancy.permissions.section``)."""

    VIEW = "View"
    EXPENSES = "Expenses"
    APPROVAL = "Approval"
    CASH = "Cash"


class BackLimitMode(StrEnum):
    """How far back a person may change records: any date, N days or N months back."""

    NONE = "none"
    DAYS = "days"
    MONTHS = "months"


class RoleName(StrEnum):
    """The four catalogue roles; names are matched case-insensitively."""

    OWNER = "Owner"
    OFFICE_ADMIN = "Office admin"
    FLEET_MANAGER = "Fleet manager"
    REVENUE_CLERK = "Revenue clerk"


class ChangeLogSection(StrEnum):
    COMPANIES = "companies"
    VEHICLES = "vehicles"
    INVESTMENT = "investment"
    EXPENSES = "expenses"
    RECURRING = "recurring"
    PEOPLE = "people"
    REVENUE = "revenue"
    ORGANIZATION = "organization"
    BUSINESS_DATE = "businessDate"
    LOCALIZATION = "localization"
    BRANDING = "branding"
    SECURITY_POLICY = "securityPolicy"
    LOGO = "logo"
    SIGN_IN = "signIn"
    PETTYCASH = "pettycash"


class ScopeMode(StrEnum):
    ALL = "all"
    COMPANIES = "companies"
    VEHICLES = "vehicles"


class ThemeMode(StrEnum):
    LIGHT = "light"
    DARK = "dark"
    SYSTEM = "system"


class DatePattern(StrEnum):
    SHORT = "short"
    MEDIUM = "medium"
    LONG = "long"


class WeekNumbering(StrEnum):
    ISO8601 = "iso8601"
    LOCAL = "local"


class LogoContentType(StrEnum):
    PNG = "image/png"
    JPEG = "image/jpeg"
    WEBP = "image/webp"


@dataclass(frozen=True, slots=True)
class Organization:
    id: UUID
    slug: str
    name: str
    business_date: date | None
    settings_version: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class Membership:
    organization_id: UUID
    user_id: UUID
    first_name: str
    last_name: str
    active: bool
    approval_limit: Decimal | None
    version: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class Localization:
    organization_id: UUID
    locale: str
    time_zone: str
    date_pattern: DatePattern
    hour12: bool
    first_day_of_week: int
    week_numbering: WeekNumbering
    currency: str
    use_grouping: bool
    number_decimals: int
    allow_locale_override: bool
    allow_time_zone_override: bool
    allow_hour12_override: bool
    allow_theme_override: bool


@dataclass(frozen=True, slots=True)
class Branding:
    """The branding section under its wire names; the table renames ``primary`` and the URL
    columns (``primary_color``, ``logo_light_url``) and the routines map between them."""

    organization_id: UUID
    display_name: str
    legal_name: str
    logo_light: str | None
    logo_dark: str | None
    logo_alt: str
    favicon: str | None
    primary: str
    secondary: str
    accent: str
    domain: str | None
    support_email: str | None
    terms_url: str | None
    privacy_url: str | None


@dataclass(frozen=True, slots=True)
class Logo:
    organization_id: UUID
    content_type: LogoContentType
    data: bytes
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class SecurityPolicy:
    organization_id: UUID
    password_min_length: int
    password_complexity: bool
    password_history: int
    pin_length: int
    lockout_threshold: int
    lockout_minutes: int
    access_token_minutes: int
    refresh_token_days: int
    idle_unlock_seconds: int
    allow_pin_sign_in: bool


@dataclass(frozen=True, slots=True)
class RevenueSettings:
    """The low-day threshold (a day below it needs a reason) and the amber band of the gap to
    target, in per cent of the target."""

    organization_id: UUID
    low_day_threshold: Decimal
    gap_amber_percent: Decimal


@dataclass(frozen=True, slots=True)
class UserPreferences:
    organization_id: UUID
    user_id: UUID
    locale: str | None
    time_zone: str | None
    hour12: bool | None
    theme_mode: ThemeMode | None
    reduced_motion: bool
    font_scale: float


@dataclass(frozen=True, slots=True)
class Role:
    organization_id: UUID
    id: UUID
    name: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class PermissionOverride:
    organization_id: UUID
    user_id: UUID
    permission: Permission
    granted: bool


@dataclass(frozen=True, slots=True)
class CatalogueItem:
    """One row of ``tenancy.permissions`` with its direct dependencies."""

    key: Permission
    group_name: str
    label: str
    group_order: int
    item_order: int
    needs: tuple[Permission, ...]


@dataclass(frozen=True, slots=True)
class DataScope:
    """A person's data scope; ``all_companies`` wins over the two id lists."""

    organization_id: UUID
    user_id: UUID
    all_companies: bool
    company_ids: tuple[UUID, ...]
    vehicle_ids: tuple[UUID, ...]


@dataclass(frozen=True, slots=True)
class ChangeLogEntry:
    """``tenancy.change_log``; ``before`` and ``after`` are the JSON text exactly as stored."""

    organization_id: UUID
    version: int
    id: UUID
    section: ChangeLogSection
    entity_id: UUID
    vehicle_id: UUID | None
    actor_id: UUID
    reason: str
    occurred_at: datetime
    effective_from: datetime | None
    before: str | None
    after: str | None
    request_id: str


class SettingsSection(StrEnum):
    """The organization settings sections a save names, as the route and the change log do."""

    ORGANIZATION = "organization"
    LOCALIZATION = "localization"
    BRANDING = "branding"
    SECURITY_POLICY = "securityPolicy"
    BUSINESS_DATE = "businessDate"
    REVENUE = "revenue"


@dataclass(frozen=True, slots=True)
class TenantContext:
    """Who acts, in which organization, for which request and when: what every tenant
    routine takes first (actor, organization, request id) and last (now)."""

    actor_id: UUID
    organization_id: UUID | None
    request_id: str
    now: datetime


# --- access and people ---------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PermissionItem:
    key: str
    label: str
    needs: tuple[str, ...]
    section: PermissionSection | None


@dataclass(frozen=True, slots=True)
class PermissionGroup:
    name: str
    items: tuple[PermissionItem, ...]


@dataclass(frozen=True, slots=True)
class AccessRole:
    id: UUID
    name: str
    permissions: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CompanyOption:
    id: UUID
    name: str


@dataclass(frozen=True, slots=True)
class VehicleOption:
    id: UUID
    registration: str
    fleet_number: str | None
    company_id: UUID


@dataclass(frozen=True, slots=True)
class ScopeOptions:
    companies: tuple[CompanyOption, ...]
    vehicles: tuple[VehicleOption, ...]


@dataclass(frozen=True, slots=True)
class MyScope:
    """The actor's own reach and how far back they may change records: ``earliest`` is the
    first date their writes may carry today (``None`` for any date)."""

    all_companies: bool
    companies: tuple[CompanyOption, ...]
    vehicles: tuple[VehicleOption, ...]
    can_change: str
    earliest: date | None


@dataclass(frozen=True, slots=True)
class BackLimit:
    """How far back a person may change records: ``count`` days or months back (``None`` with
    ``none``), and a fixed date they may never go before."""

    mode: BackLimitMode
    count: int | None
    from_date: date | None


@dataclass(frozen=True, slots=True)
class ModuleAccess:
    """One access chip of the people list: a catalogue module and how many of its rights the
    person holds."""

    name: str
    held: int
    total: int


@dataclass(frozen=True, slots=True)
class PersonDevice:
    id: UUID
    name: str | None
    trusted_at: datetime
    last_used_at: datetime


@dataclass(frozen=True, slots=True)
class PersonSignIn:
    """The "Sign in" pane: status, which lock holds (``every_device``, ``new_devices``),
    the last sign-in, where codes go and the live trusted devices."""

    status: SignInStatus
    lock: str | None
    last_signed_in_at: datetime | None
    email: str
    devices: tuple[PersonDevice, ...]


@dataclass(frozen=True, slots=True)
class Person:
    """A person as a viewer may see them: scope ids inside the viewer's reach, the rest
    counted; ``permissions`` is the catalogue rights their role and overrides give them, kept
    when inactive; ``sign_in`` only on a single person."""

    id: UUID
    first_name: str
    last_name: str
    email: str
    phone_number: str
    role: str | None
    active: bool
    scope_mode: ScopeMode
    company_ids: tuple[UUID, ...]
    vehicle_ids: tuple[UUID, ...]
    permissions: tuple[str, ...]
    approval_limit: Decimal | None
    has_pin: bool
    version: int
    other_companies: int
    other_vehicles: int
    status: SignInStatus
    last_signed_in_at: datetime | None
    back_limit: BackLimit
    can_change: str
    modules: tuple[ModuleAccess, ...]
    everything: bool
    sign_in: PersonSignIn | None


@dataclass(frozen=True, slots=True)
class PeoplePage:
    items: tuple[Person, ...]
    total: int


@dataclass(frozen=True, slots=True)
class BackLimitInput:
    """The back-dating limit as a save sends it; no mode keeps the stored one (7 days back for
    a new person)."""

    mode: str | None
    count: int | None
    from_date: date | None


@dataclass(frozen=True, slots=True)
class PersonDetails:
    """What a person save sends, as received: the routine trims, normalises and decides."""

    first_name: str | None
    last_name: str | None
    email: str | None
    phone_number: str | None
    role: str | None
    scope_mode: str | None
    company_ids: tuple[UUID, ...]
    vehicle_ids: tuple[UUID, ...]
    permissions: tuple[str, ...]
    approval_limit: Decimal | None
    back_limit: BackLimitInput | None = None


@dataclass(frozen=True, slots=True)
class PeopleQuery:
    context: TenantContext
    page: int
    page_size: int
    role: str | None = None
    status: str | None = None


@dataclass(frozen=True, slots=True)
class PersonQuery:
    context: TenantContext
    user_id: UUID


@dataclass(frozen=True, slots=True)
class PersonSave:
    """Create when ``user_id`` is ``None``, else update at ``expected_version``."""

    context: TenantContext
    user_id: UUID | None
    details: PersonDetails
    expected_version: int | None


@dataclass(frozen=True, slots=True)
class PersonLifecycle:
    context: TenantContext
    user_id: UUID
    active: bool
    expected_version: int | None
    reason: str | None


@dataclass(frozen=True, slots=True)
class PersonSignOut:
    context: TenantContext
    user_id: UUID


@dataclass(frozen=True, slots=True)
class PersonPinReset:
    context: TenantContext
    user_id: UUID


@dataclass(frozen=True, slots=True)
class PersonDeviceRemoval:
    context: TenantContext
    user_id: UUID
    device_id: UUID


# --- change log ----------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class HistoryFilter:
    page: int
    page_size: int
    section: str | None
    from_date: date | None
    to_date: date | None
    text: str | None
    before: int | None
    include_total: bool


@dataclass(frozen=True, slots=True)
class HistoryQuery:
    context: TenantContext
    filter: HistoryFilter


@dataclass(frozen=True, slots=True)
class HistoryEntry:
    """One change-log row as the viewer may read it; ``before`` and ``after`` are JSON text."""

    version: int
    section: str
    entity_id: UUID
    reason: str
    occurred_at: datetime
    actor_id: UUID
    actor_name: str
    before: str | None
    after: str | None


@dataclass(frozen=True, slots=True)
class HistoryPage:
    items: tuple[HistoryEntry, ...]
    total: int | None
    has_more: bool
    next_before: int | None


# --- organization settings, appearance, preferences ----------------------------------------


@dataclass(frozen=True, slots=True)
class OrganizationDetails:
    id: UUID
    slug: str
    name: str
    business_date: date | None
    settings_version: int


@dataclass(frozen=True, slots=True)
class EffectiveFormats:
    locale: str
    time_zone: str
    date_pattern: DatePattern
    hour12: bool
    first_day_of_week: int
    week_numbering: WeekNumbering
    currency: str
    use_grouping: bool
    number_decimals: int
    direction: str


@dataclass(frozen=True, slots=True)
class EffectiveSettings:
    formats: EffectiveFormats
    branding: Branding
    security_policy: SecurityPolicy
    theme_mode: ThemeMode
    reduced_motion: bool
    font_scale: float


@dataclass(frozen=True, slots=True)
class OrganizationSettings:
    organization: OrganizationDetails
    localization: Localization
    branding: Branding
    security_policy: SecurityPolicy
    effective_business_date: date
    calendar_date: date
    effective: EffectiveSettings
    revenue: RevenueSettings


@dataclass(frozen=True, slots=True)
class AppearanceBranding:
    display_name: str
    logo_alt: str
    primary: str
    secondary: str
    accent: str
    logo: str | None


@dataclass(frozen=True, slots=True)
class Appearance:
    organization_name: str
    settings_version: int
    business_date: date
    branding: AppearanceBranding
    formats: EffectiveFormats
    theme_mode: ThemeMode
    reduced_motion: bool
    font_scale: float
    lockout_threshold: int
    lockout_minutes: int
    idle_unlock_seconds: int


@dataclass(frozen=True, slots=True)
class PreferenceDefaults:
    locale: str
    time_zone: str
    hour12: bool


@dataclass(frozen=True, slots=True)
class Preferences:
    """The person's own preferences; a value the organization no longer allows is ``None``."""

    organization_id: UUID
    user_id: UUID
    locale: str | None
    time_zone: str | None
    hour12: bool | None
    theme_mode: ThemeMode | None
    reduced_motion: bool
    font_scale: float
    allow_locale_override: bool
    allow_time_zone_override: bool
    allow_hour12_override: bool
    allow_theme_override: bool
    organization: PreferenceDefaults


@dataclass(frozen=True, slots=True)
class PreferenceChoices:
    """A preferences save as received; ``None`` clears an override."""

    locale: str | None
    time_zone: str | None
    hour12: bool | None
    theme_mode: str | None
    reduced_motion: bool
    font_scale: float


@dataclass(frozen=True, slots=True)
class PreferencesSave:
    context: TenantContext
    choices: PreferenceChoices


@dataclass(frozen=True, slots=True)
class SettingsSave:
    """One section save: ``value`` is the posted JSON value under the document keys; the
    routine merges, validates and decides."""

    context: TenantContext
    section: str
    value: Any
    reason: str | None
    expected_version: int | None


LOGO_MAX_BYTES = 256 * 1024
LOGO_MAX_DATA_URL = (LOGO_MAX_BYTES + 2) // 3 * 4 + 64
_LOGO_DATA_URL = re.compile(r"data:(image/(?:png|jpeg|webp));base64,([A-Za-z0-9+/=]+)")


@dataclass(frozen=True, slots=True)
class LogoUpload:
    """A logo as the wire carries it, a ``data:image/...;base64,`` URL, decoded. Only the
    transport encoding is checked here (length before decoding, the URL shape, base64); the
    routine decides the type, the size and the signature."""

    content_type: str
    data: bytes

    @classmethod
    def parse(cls, data_url: str) -> LogoUpload:
        if len(data_url) > LOGO_MAX_DATA_URL:
            raise RuleViolation(code="logo_too_large")
        match = _LOGO_DATA_URL.fullmatch(data_url)
        if match is None:
            raise RuleViolation(code="logo_type")
        try:
            data = base64.b64decode(match.group(2), validate=True)
        except (binascii.Error, ValueError):
            raise RuleViolation(code="logo_unreadable") from None
        return cls(content_type=match.group(1), data=data)

    @property
    def data_url(self) -> str:
        return f"data:{self.content_type};base64,{base64.b64encode(self.data).decode('ascii')}"


@dataclass(frozen=True, slots=True)
class LogoSave:
    context: TenantContext
    logo: LogoUpload
    reason: str | None


@dataclass(frozen=True, slots=True)
class LogoRemoval:
    context: TenantContext
    reason: str | None
