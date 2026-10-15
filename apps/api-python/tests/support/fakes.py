"""In-memory fakes for the ports and repositories, for use-case and HTTP-plumbing tests."""

from __future__ import annotations

import asyncio
import copy
import dataclasses
import functools
import json
import re
from collections.abc import Awaitable, Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_EVEN, ROUND_HALF_UP, Context, Decimal
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4, uuid5
from zoneinfo import ZoneInfo

from xcode_api.application.ports import (
    PinHasher,
    RateLimitDecision,
    VerificationMail,
)
from xcode_api.db.contract import EXPECTED_CONTRACT_VERSION
from xcode_api.domain.errors import Conflict, Forbidden, NotFound, RuleViolation, SessionInvalid
from xcode_api.domain.expenses import (
    ExpenseAllocation,
    ExpenseChange,
    ExpenseFigures,
    ExpenseGroup,
    ExpenseItemOption,
    ExpenseLedger,
    ExpenseLedgerQuery,
    ExpenseLedgerRow,
    ExpenseOptions,
    ExpenseOptionsQuery,
    ExpensePermissions,
    ExpensePurchase,
    ExpenseRecorded,
    ExpenseRemoval,
    ExpenseSaved,
    ExpenseSource,
    ExpenseVehicleOption,
)
from xcode_api.domain.identity import (
    AccountLookup,
    AccountPolicy,
    AccountState,
    AccountSummary,
    AuthOutcome,
    AuthOutcomeKind,
    ClearedPause,
    CodeCheck,
    CodeEntry,
    CodePurpose,
    CodeRequest,
    CodeResend,
    CodeWithdrawal,
    DemoSeeding,
    DeviceListing,
    DeviceRemoval,
    DeviceRevocation,
    DeviceVerification,
    NumberCheck,
    OperatorRequest,
    PinChange,
    PinCheck,
    PinCompletion,
    PinProblem,
    PinVerdict,
    ProvisionedUser,
    RemovedUser,
    RevokedSessions,
    SeededDemo,
    SessionCheck,
    SessionContext,
    SignInRefusal,
    SignInStatus,
    TokenRefresh,
    TokenSignOut,
    TrustedDeviceView,
    UserLookup,
    UserProvisioning,
    UserStatus,
)
from xcode_api.domain.pettycash import (
    EntryKind,
    EntryState,
    OverviewPeriod,
    PettyCashApprovalHolder,
    PettyCashApprovalsCard,
    PettyCashApproved,
    PettyCashCreate,
    PettyCashDashboard,
    PettyCashDayApproval,
    PettyCashDecision,
    PettyCashEntriesApproval,
    PettyCashEntry,
    PettyCashEntryPage,
    PettyCashEntryQuery,
    PettyCashFigures,
    PettyCashFloat,
    PettyCashFloatCard,
    PettyCashGroup,
    PettyCashHolder,
    PettyCashItemOption,
    PettyCashLine,
    PettyCashOptions,
    PettyCashOptionsQuery,
    PettyCashOverview,
    PettyCashOverviewQuery,
    PettyCashPermissions,
    PettyCashSaved,
    PettyCashUpdate,
    PettyCashVehicleOption,
    SaveOutcome,
)
from xcode_api.domain.policies import CODE_TRIES, PIN_TRIES, TRUSTED_DEVICE_IDLE_DAYS
from xcode_api.domain.reports import (
    CellKind,
    ExpenseExportQuery,
    PettyCashExportQuery,
    ReportColumn,
    ReportDocument,
    ReportExportQuery,
    ReportFigure,
    ReportHolder,
    ReportQuery,
    ReportsAccess,
    ReportTable,
    RevenueExportQuery,
)
from xcode_api.domain.revenue import (
    CaptureOutcome,
    CaptureResult,
    CellStatus,
    DashboardPeriod,
    GapBand,
    LastWeek,
    NoEarningsReason,
    RevenueCapture,
    RevenueCell,
    RevenueDashboard,
    RevenueDashboardQuery,
    RevenueDay,
    RevenueDayQuery,
    RevenueDayResult,
    RevenueDaySave,
    RevenueDaySaved,
    RevenueDayTotal,
    RevenueDayVehicle,
    RevenueGap,
    RevenueVehicleWeek,
    RevenueWeek,
    RevenueWeekQuery,
)
from xcode_api.domain.setup import (
    AwayEntry,
    CompanyChoice,
    CompanyLifecycle,
    CompanyPage,
    CompanySave,
    CompanySummary,
    ExpenseBucket,
    ExpenseCategoryPage,
    ExpenseCategorySave,
    ExpenseCategorySummary,
    ExpenseItemChoice,
    ExpenseItemCreate,
    ExpenseItemRename,
    ExpenseItemSummary,
    ExpenseLifecycle,
    InvestmentCreate,
    InvestmentDetails,
    InvestmentEntry,
    InvestmentRemoval,
    InvestmentSummary,
    InvestmentUpdate,
    MainCategoryPage,
    MainCategorySave,
    MainCategorySummary,
    NextTarget,
    OpeningSummary,
    RecurrenceFrequency,
    RecurringCancelStop,
    RecurringDefinition,
    RecurringKind,
    RecurringListQuery,
    RecurringMonth,
    RecurringPage,
    RecurringPause,
    RecurringRun,
    RecurringRuns,
    RecurringRunShare,
    RecurringRunsQuery,
    RecurringSave,
    RecurringStop,
    RecurringSummary,
    RevenueRule,
    RunState,
    RunStates,
    SetupPageQuery,
    ShareSummary,
    ShareVehicle,
    TargetEntry,
    TargetSetRemoval,
    TargetSetSave,
    TargetSetSummary,
    VehicleListQuery,
    VehiclePage,
    VehicleQuery,
    VehicleReport,
    VehicleReportQuery,
    VehicleRetirement,
    VehicleReturn,
    VehicleSave,
    VehicleSummary,
)
from xcode_api.domain.tenancy import (
    AccessRole,
    Appearance,
    AppearanceBranding,
    BackLimit,
    BackLimitMode,
    Branding,
    DatePattern,
    EffectiveFormats,
    EffectiveSettings,
    HistoryEntry,
    HistoryPage,
    HistoryQuery,
    Localization,
    LogoRemoval,
    LogoSave,
    LogoUpload,
    ModuleAccess,
    MyScope,
    OrganizationDetails,
    OrganizationSettings,
    PeoplePage,
    PeopleQuery,
    PermissionGroup,
    PermissionItem,
    PermissionSection,
    Person,
    PersonDetails,
    PersonDevice,
    PersonDeviceRemoval,
    PersonLifecycle,
    PersonPinReset,
    PersonQuery,
    PersonSave,
    PersonSignIn,
    PersonSignOut,
    PreferenceDefaults,
    Preferences,
    PreferencesSave,
    RevenueSettings,
    ScopeMode,
    ScopeOptions,
    SecurityPolicy,
    SettingsSave,
    TenantContext,
    ThemeMode,
    UserPreferences,
    WeekNumbering,
)
from xcode_api.domain.values import PhoneNumber, WriteOutcome, WriteResult

from .scenario import T0


@dataclass(slots=True)
class FakeAccount:
    """One provisioned person as the ops fake keeps it: the state the operator routines
    read and change, nothing more."""

    user_id: UUID
    email: str
    phone: str
    status: UserStatus = UserStatus.ACTIVE
    membership_active: bool = True
    security_version: int = 0
    failed_attempts: int = 0
    untrusted_failed_attempts: int = 0
    pin_reset_required: bool = False
    last_signed_in_at: datetime | None = None
    trusted_devices: int = 0
    live_refresh_tokens: int = 0


class FakeOpsRepository:
    """Configurable ops repository for the database-free plumbing tests; the database-backed
    API tests use the real routines."""

    def __init__(
        self,
        *,
        healthy: bool = True,
        ping_delay_seconds: float = 0.0,
        contract_version: int = EXPECTED_CONTRACT_VERSION,
    ) -> None:
        self.healthy = healthy
        self.ping_delay_seconds = ping_delay_seconds
        self._contract_version = contract_version
        self.operator_actions: list[dict[str, Any]] = []
        self.accounts: dict[str, FakeAccount] = {}
        self.organization_id = uuid4()
        self.ping_calls = 0
        self.contract_version_calls = 0
        self.demo_seeded = False
        self.demo_pin_hashes: dict[str, str] = {}

    async def ping(self) -> None:
        self.ping_calls += 1
        if self.ping_delay_seconds:
            await asyncio.sleep(self.ping_delay_seconds)
        if not self.healthy:
            raise RuntimeError("database unavailable")

    async def contract_version(self) -> int:
        self.contract_version_calls += 1
        return self._contract_version

    async def rate_limit_hit(
        self, key: str, limit: int, window_seconds: int, now: datetime
    ) -> RateLimitDecision:
        return RateLimitDecision(allowed=True, remaining=limit, retry_after_seconds=window_seconds)

    async def record_operator_action(
        self, operator: str, action: str, target: str, detail: Mapping[str, Any]
    ) -> None:
        self.operator_actions.append(
            {"operator": operator, "action": action, "target": target, "detail": dict(detail)}
        )

    # --- operator user routines (api.ops_*), in memory ----------------------------------

    def _record(self, command: OperatorRequest | UserProvisioning, action: str) -> str:
        email = command.email.strip().lower()
        self.operator_actions.append(
            {
                "operator": command.operator,
                "action": action,
                "target": email,
                "detail": {"request_id": command.request_id},
            }
        )
        return email

    def _find(self, command: OperatorRequest, action: str) -> FakeAccount:
        email = self._record(command, action)
        account = self.accounts.get(email)
        if account is None:
            raise NotFound("not_found")
        return account

    async def provision_user(self, command: UserProvisioning) -> ProvisionedUser:
        email = self._record(command, "provision-user")
        if "@" not in email:
            raise RuleViolation("people_email_invalid")
        created_organization = not self.accounts
        account = self.accounts.get(email)
        if account is None:
            account = FakeAccount(user_id=uuid4(), email=email, phone=command.phone)
            self.accounts[email] = account
            return ProvisionedUser(
                account.user_id, self.organization_id, True, created_organization, False
            )
        reactivated = account.status is not UserStatus.ACTIVE or not account.membership_active
        changed = reactivated or account.phone != command.phone
        account.phone = command.phone
        account.status = UserStatus.ACTIVE
        account.membership_active = True
        if changed:
            account.security_version += 1
            account.trusted_devices = 0
            account.live_refresh_tokens = 0
        return ProvisionedUser(account.user_id, self.organization_id, False, False, reactivated)

    async def remove_user(self, command: OperatorRequest) -> RemovedUser:
        account = self._find(command, "remove-user")
        removed = account.status is UserStatus.ACTIVE
        if removed:
            account.status = UserStatus.REMOVED
            account.security_version += 1
        tokens, account.live_refresh_tokens = account.live_refresh_tokens, 0
        return RemovedUser(account.user_id, removed, tokens)

    async def clear_pause(self, command: OperatorRequest) -> ClearedPause:
        account = self._find(command, "clear-pause")
        was_locked = (
            account.failed_attempts >= PIN_TRIES or account.untrusted_failed_attempts >= PIN_TRIES
        )
        account.failed_attempts = 0
        account.untrusted_failed_attempts = 0
        return ClearedPause(account.user_id, was_locked)

    async def revoke_sessions(self, command: OperatorRequest) -> RevokedSessions:
        account = self._find(command, "revoke-sessions")
        account.security_version += 1
        devices, account.trusted_devices = account.trusted_devices, 0
        tokens, account.live_refresh_tokens = account.live_refresh_tokens, 0
        return RevokedSessions(account.user_id, devices, tokens)

    async def account_state(self, command: OperatorRequest) -> AccountSummary:
        account = self._find(command, "account-state")
        return AccountSummary(
            user_id=account.user_id,
            status=account.status,
            has_pin=False,
            pin_reset_required=account.pin_reset_required,
            sign_in_status=SignInStatus.BLOCKED
            if account.status is not UserStatus.ACTIVE or not account.membership_active
            else SignInStatus.NOT_SIGNED_IN,
            last_signed_in_at=account.last_signed_in_at,
            failed_attempts=account.failed_attempts,
            untrusted_failed_attempts=account.untrusted_failed_attempts,
            trusted_devices=account.trusted_devices,
            live_refresh_tokens=account.live_refresh_tokens,
            active_membership=account.membership_active,
        )

    async def unassigned_user_count(self) -> int:
        return sum(
            1
            for a in self.accounts.values()
            if a.status is UserStatus.ACTIVE and not a.membership_active
        )

    async def seed_demo(self, command: DemoSeeding) -> SeededDemo:
        self.operator_actions.append(
            {
                "operator": command.operator,
                "action": "seed-demo",
                "target": "demo-fleet",
                "detail": {"request_id": command.request_id},
            }
        )
        if command.environment != "development":
            raise Forbidden(code="seed_development_only")
        created = not self.demo_seeded
        self.demo_seeded = True
        self.demo_pin_hashes = {**dict(command.pin_hashes), **self.demo_pin_hashes}
        return SeededDemo(self.organization_id, created)


# --- identity: the api.auth_* routines, in memory -----------------------------------------

CODE_LIFETIME = timedelta(minutes=10)
COOLDOWN = timedelta(minutes=1)
HOURLY_CODES = 5
DAILY_CODES = 10
_POLICY_DEFAULTS = {
    "pin_length": 4,
    "lockout_threshold": 5,
    "lockout_minutes": 15,
    "access_token_minutes": 10,
    "refresh_token_days": 30,
}
_POLICY_BOUNDS = {
    "pin_length": (4, 8),
    "lockout_threshold": (3, 10),
    "lockout_minutes": (1, 60),
    "access_token_minutes": (1, 15),
    "refresh_token_days": (1, 90),
}
_USER_FIELDS = frozenset(
    {
        "failed_attempts",
        "untrusted_failed_attempts",
        "status",
        "security_version",
        "pin_hash",
        "pin_reset_required",
        "last_signed_in_at",
    }
)
_CATALOGUE_PATH = Path(__file__).with_name("permission_catalogue.json")


@functools.cache
def _catalogue() -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(_CATALOGUE_PATH.read_text(encoding="utf-8"))
    return loaded


def role_names() -> tuple[str, ...]:
    """The role names the catalogue defines, in its order."""
    return tuple(_catalogue()["role_defaults"])


@functools.cache
def _needs() -> dict[str, tuple[str, ...]]:
    return {
        item["key"]: tuple(item["needs"])
        for group in _catalogue()["groups"]
        for item in group["items"]
    }


def _role_default(role: str | None) -> Any:
    defaults = {name.lower(): value for name, value in _catalogue()["role_defaults"].items()}
    return defaults.get((role or "").lower())


def role_rights(role: str) -> tuple[str, ...]:
    """``tenancy.role_permissions``: a role's default catalogue rights with their dependencies,
    in catalogue order; what a person save sends for the role alone."""
    chosen = _role_default(role)
    if isinstance(chosen, dict):
        return expand_permissions(key for key in _needs() if key not in chosen["all_except"])
    return expand_permissions(chosen)


def hidden_rights(role: str | None) -> tuple[str, ...]:
    """The keys outside the catalogue a role's defaults give (the Owner's
    ``organization.manage``)."""
    chosen = _role_default(role)
    return tuple(chosen.get("hidden", ())) if isinstance(chosen, dict) else ()


def held_permissions(rights: Iterable[str], role: str | None) -> tuple[str, ...]:
    """``tenancy.effective_permissions`` of an active member assigned the catalogue ``rights``
    under ``role``: the rights, every retired key one of them is a source of, then the role's
    hidden keys, in catalogue order."""
    assigned = set(rights)
    derived = tuple(
        item["key"] for item in _catalogue()["retired"] if assigned & set(item["sources"])
    )
    return tuple(key for key in _needs() if key in assigned) + derived + hidden_rights(role)


def role_permissions(role: str) -> tuple[str, ...]:
    """What ``tenancy.effective_permissions`` returns for a member holding only ``role``: the
    permission claims of their token."""
    return held_permissions(role_rights(role), role)


def mask_email(email: str) -> str:
    """``identity.mask_email``: the first character, ``***`` and everything from the first ``@``."""
    at = email.find("@")
    if at <= 0:
        return "***"
    return email[0] + "***" + email[at:]


@dataclass(slots=True)
class FakeUser:
    """One person as the identity fake keeps it: ``identity.users`` plus the membership and
    role link ``identity.policy_for`` reads."""

    user_id: UUID
    organization_id: UUID
    email: str
    phone: str
    status: UserStatus = UserStatus.ACTIVE
    pin_hash: str | None = None
    security_version: int = 0
    failed_attempts: int = 0
    untrusted_failed_attempts: int = 0
    pin_reset_required: bool = False
    last_signed_in_at: datetime | None = None
    role: str | None = "Owner"
    first_name: str = "Jane"
    last_name: str = "Doe"
    membership: bool = True


@dataclass(slots=True)
class FakeCode:
    code_id: UUID
    user_id: UUID
    purpose: CodePurpose
    device_id: str
    code_hash: str
    created_at: datetime
    expires_at: datetime
    consumed: bool = False
    failed_attempts: int = 0

    @property
    def withdrawn(self) -> bool:
        return self.consumed and self.expires_at <= self.created_at


@dataclass(slots=True)
class FakeToken:
    user_id: UUID
    device_id: str
    token_hash: str
    expires_at: datetime
    revoked: bool = False


@dataclass(slots=True)
class FakeDevice:
    user_id: UUID
    device_id: str
    revoked: bool = False
    trust_expires_at: datetime | None = None
    token_hash: str | None = None
    name: str | None = None
    remembered: bool = True
    trusted_at: datetime = T0
    last_used_at: datetime = T0
    row_id: UUID = field(default_factory=uuid4)

    def live(self, now: datetime) -> bool:
        return (
            not self.revoked
            and now < self.last_used_at + timedelta(days=TRUSTED_DEVICE_IDLE_DAYS)
            and (self.trust_expires_at is None or now < self.trust_expires_at)
        )


@dataclass(slots=True)
class FakeAttempt:
    """A sign-in history row of a number without an account (the simulated account reads it)."""

    digest: str
    device_id: str
    operation: str
    outcome: str
    refusal: str | None
    occurred_at: datetime


class FakeIdentityRepository:
    """In-memory ``IdentityRepository`` with the outcomes of the ``api.auth_*`` routines.

    ``tests/db/test_fakes_match_routines.py`` runs one scenario table against this fake and
    against the real routines and asserts identical results. Accounts are keyed by the
    normalised phone; digests are opaque strings compared for equality. Of the sign-in history
    only the rows of numbers without an account are kept (the simulated account of the number
    step reads them); change-log rows are not modelled.
    """

    def __init__(self, *, calls: list[str] | None = None) -> None:
        self.calls: list[str] = calls if calls is not None else []
        self.organization_id = uuid4()
        self._users: dict[UUID, FakeUser] = {}
        self._policies: dict[UUID, dict[str, int]] = {}
        self._codes: list[FakeCode] = []
        self._tokens: list[FakeToken] = []
        self._devices: list[FakeDevice] = []
        self._unknown: list[FakeAttempt] = []

    # --- arranging state --------------------------------------------------------------------

    def add_account(
        self,
        *,
        email: str = "jane.doe@example.com",
        phone: str = "0712345678",
        pin_hash: str | None = None,
        status: UserStatus = UserStatus.ACTIVE,
        role: str | None = "Owner",
        first_name: str = "Jane",
        last_name: str = "Doe",
        membership: bool = True,
        organization_id: UUID | None = None,
    ) -> UUID:
        parsed = PhoneNumber.parse(phone)
        if parsed is None:
            raise ValueError(f"{phone!r} does not normalise to a phone number")
        if any(u.phone == parsed.value or u.email == email for u in self._users.values()):
            raise ValueError("the phone number or email is already taken")
        canonical = None
        if role is not None:
            canonical = next((n for n in role_names() if n.lower() == role.lower()), None)
            if canonical is None:
                raise ValueError(f"unknown role {role!r}")
        user = FakeUser(
            user_id=uuid4(),
            organization_id=organization_id or self.organization_id,
            email=email,
            phone=parsed.value,
            status=status,
            pin_hash=pin_hash,
            role=canonical,
            first_name=first_name,
            last_name=last_name,
            membership=membership,
        )
        self._users[user.user_id] = user
        return user.user_id

    def set_policy(self, organization_id: UUID, **fields: int) -> None:
        unknown = set(fields) - set(_POLICY_DEFAULTS)
        if unknown:
            raise ValueError(f"unknown policy field(s) {sorted(unknown)}")
        self._policies.setdefault(organization_id, {}).update(fields)

    def trust(
        self,
        user_id: UUID,
        device_id: str,
        *,
        expires_at: datetime | None = None,
        revoked: bool = False,
        token_hash: str | None = None,
        name: str | None = None,
        remembered: bool = True,
        last_used_at: datetime = T0,
    ) -> None:
        device = self._device(user_id, device_id)
        if device is None:
            self._devices.append(
                FakeDevice(
                    user_id,
                    device_id,
                    revoked,
                    expires_at,
                    token_hash,
                    name,
                    remembered,
                    min(last_used_at, T0),
                    last_used_at,
                )
            )
        else:
            device.revoked = revoked
            device.trust_expires_at = expires_at
            device.token_hash = token_hash
            device.name = name
            device.remembered = remembered
            device.last_used_at = last_used_at

    def store_token(
        self,
        user_id: UUID,
        device_id: str,
        token_hash: str,
        *,
        expires_at: datetime,
        revoked: bool = False,
    ) -> None:
        self._insert_token(FakeToken(user_id, device_id, token_hash, expires_at, revoked))

    def store_code(
        self,
        user_id: UUID,
        purpose: CodePurpose,
        device_id: str,
        code_hash: str,
        *,
        created_at: datetime,
        consumed: bool = False,
        withdrawn: bool = False,
        failed_attempts: int = 0,
    ) -> UUID:
        expires_at = created_at if withdrawn else created_at + CODE_LIFETIME
        code = self._insert_code(
            user_id,
            purpose,
            device_id,
            code_hash,
            created_at,
            expires_at,
            consumed or withdrawn,
            failed_attempts,
        )
        return code.code_id

    def set_user(self, user_id: UUID, **fields: object) -> None:
        unknown = set(fields) - _USER_FIELDS
        if unknown:
            raise ValueError(f"unknown user field(s) {sorted(unknown)}")
        user = self._users[user_id]
        for name, value in fields.items():
            setattr(user, name, value)

    # --- reading state ----------------------------------------------------------------------

    def user(self, user_id: UUID) -> FakeUser:
        return replace(self._users[user_id])

    def codes(self, user_id: UUID) -> list[FakeCode]:
        return [replace(c) for c in self._codes if c.user_id == user_id]

    def tokens(self, user_id: UUID) -> list[FakeToken]:
        return [replace(t) for t in self._tokens if t.user_id == user_id]

    def devices(self, user_id: UUID) -> list[FakeDevice]:
        return [replace(d) for d in self._devices if d.user_id == user_id]

    def live_tokens(self, user_id: UUID, device_id: str | None = None) -> int:
        return sum(
            1
            for t in self._tokens
            if t.user_id == user_id
            and not t.revoked
            and (device_id is None or t.device_id == device_id)
        )

    # --- IdentityRepository -----------------------------------------------------------------

    async def account_lookup(self, query: AccountLookup) -> AccountState | None:
        user = self._by_phone(query.phone)
        self.calls.append("account_lookup")
        if user is None:
            if query.pin_try:
                self._remember(
                    query.phone, query.device_id, "sign_in", "refused", "unknown_number", query.now
                )
            return None
        return self._state(
            user, self._trusted(user.user_id, query.device_id, query.device_token_hash, query.now)
        )

    async def account_lookup_user(self, query: UserLookup) -> AccountState | None:
        user = self._users.get(query.user_id)
        self.calls.append("account_lookup_user")
        if user is None:
            return None
        device = self._device(user.user_id, query.device_id)
        return self._state(user, device is not None and device.live(query.now))

    async def start(self, command: NumberCheck) -> AuthOutcome:
        outcome = self._start(command)
        self.calls.append("start")
        return outcome

    async def sign_in(self, verdict: PinVerdict) -> AuthOutcome:
        outcome = self._sign_in(verdict)
        self.calls.append("sign_in")
        return outcome

    async def pin(self, command: PinCheck) -> AuthOutcome:
        outcome = self._pin(command)
        self.calls.append("pin")
        return outcome

    async def check_code(self, command: CodeEntry) -> AuthOutcome:
        outcome = self._check_code(command)
        self.calls.append("check_code")
        return outcome

    async def resend_code(self, command: CodeResend) -> AuthOutcome:
        outcome = self._resend_code(command)
        self.calls.append("resend_code")
        return outcome

    async def verify_device(self, command: DeviceVerification) -> AuthOutcome:
        outcome = self._verify_device(command)
        self.calls.append("verify_device")
        return outcome

    async def request_code(self, command: CodeRequest) -> AuthOutcome:
        outcome = self._request_code(command)
        self.calls.append("request_code")
        return outcome

    async def verify_code(self, command: CodeCheck) -> AuthOutcome:
        outcome = self._verify_code(command)
        self.calls.append("verify_code")
        return outcome

    async def complete_pin(self, command: PinCompletion) -> AuthOutcome:
        outcome = self._complete_pin(command)
        self.calls.append("complete_pin")
        return outcome

    async def change_pin(self, command: PinChange) -> AuthOutcome:
        outcome = self._change_pin(command)
        self.calls.append("change_pin")
        return outcome

    async def refresh(self, command: TokenRefresh) -> AuthOutcome:
        outcome = self._refresh(command)
        self.calls.append("refresh")
        return outcome

    async def sign_out(self, command: TokenSignOut) -> AuthOutcome:
        token = self._token_of(command.token_hash)
        if token is not None and token.device_id == command.device_id:
            self._revoke_tokens(token.user_id, command.device_id)
            device = self._device(token.user_id, command.device_id)
            if device is not None and not device.remembered:
                device.revoked = True
            outcome = AuthOutcome(AuthOutcomeKind.SIGNED_OUT)
        else:
            outcome = AuthOutcome(AuthOutcomeKind.SIGNED_OUT, refusal=SignInRefusal.TOKEN_UNKNOWN)
        self.calls.append("sign_out")
        return outcome

    async def revoke_device(self, command: DeviceRevocation) -> AuthOutcome:
        user = self._users.get(command.user_id)
        if user is not None:
            device = self._device(user.user_id, command.device_id)
            if device is not None:
                self._remove_devices(user.user_id, command.now, device.row_id)
            self._revoke_tokens(user.user_id, command.device_id)
            for code in self._codes:
                if code.user_id == user.user_id and code.device_id == command.device_id:
                    code.consumed = True
        self.calls.append("revoke_device")
        return AuthOutcome(AuthOutcomeKind.DEVICE_REVOKED)

    async def device_list(self, query: DeviceListing) -> tuple[TrustedDeviceView, ...]:
        self.calls.append("device_list")
        devices = [
            d
            for d in self._devices
            if d.user_id == query.user_id and d.remembered and d.live(query.now)
        ]
        devices.sort(key=lambda d: (-d.last_used_at.timestamp(), str(d.row_id)))
        return tuple(
            TrustedDeviceView(
                d.row_id, d.name, d.trusted_at, d.last_used_at, d.device_id == query.device_id
            )
            for d in devices
        )

    async def device_remove(self, command: DeviceRemoval) -> AuthOutcome:
        self.calls.append("device_remove")
        device = next(
            (
                d
                for d in self._devices
                if d.row_id == command.row_id and d.user_id == command.user_id
            ),
            None,
        )
        if command.user_id not in self._users or device is None or not device.live(command.now):
            raise NotFound()
        self._remove_devices(command.user_id, command.now, device.row_id)
        return AuthOutcome(AuthOutcomeKind.DEVICE_REVOKED)

    async def withdraw_code(self, command: CodeWithdrawal) -> None:
        for code in self._codes:
            if code.code_id == command.code_id and not code.consumed:
                code.consumed = True
                code.expires_at = code.created_at
        self.calls.append("withdraw_code")

    async def resolve_session(self, check: SessionCheck) -> SessionContext:
        user = self._users.get(check.user_id)
        self.calls.append("resolve_session")
        device = None if user is None else self._device(user.user_id, check.device_id)
        if (
            user is None
            or user.status is not UserStatus.ACTIVE
            or user.security_version != check.security_version
            or device is None
            or not device.live(check.now)
        ):
            raise SessionInvalid
        if not user.membership:
            return SessionContext(organization_id=None, role=None)
        return SessionContext(organization_id=user.organization_id, role=user.role)

    # --- lookups ----------------------------------------------------------------------------

    def _by_phone(self, phone: str) -> FakeUser | None:
        parsed = PhoneNumber.parse(phone)
        if parsed is None:
            return None
        return next((u for u in self._users.values() if u.phone == parsed.value), None)

    def _device(self, user_id: UUID, device_id: str) -> FakeDevice | None:
        return next(
            (d for d in self._devices if d.user_id == user_id and d.device_id == device_id), None
        )

    def _trusted(
        self, user_id: UUID, device_id: str, token_hash: str | None, now: datetime
    ) -> bool:
        """``identity.device_trusted``: ``None`` is the released routes' legacy check."""
        device = self._device(user_id, device_id)
        if device is None or not device.remembered or not device.live(now):
            return False
        if token_hash is None:
            return device.token_hash is None
        return device.token_hash == token_hash

    def _state(self, user: FakeUser, device_trusted: bool) -> AccountState:
        return AccountState(
            user_id=user.user_id,
            status=user.status,
            pin_hash=user.pin_hash,
            phone_number=user.phone,
            security_version=user.security_version,
            failed_attempts=user.failed_attempts,
            untrusted_failed_attempts=user.untrusted_failed_attempts,
            pin_reset_required=user.pin_reset_required,
            device_trusted=device_trusted,
            policy=self._policy_for(user),
        )

    def _token_of(self, token_hash: str) -> FakeToken | None:
        return next((t for t in self._tokens if t.token_hash == token_hash), None)

    def _policy_for(self, user: FakeUser) -> AccountPolicy | None:
        if not user.membership or user.role is None:
            return None
        raw = self._policies.get(user.organization_id, {})

        def pick(name: str) -> int:
            low, high = _POLICY_BOUNDS[name]
            return min(max(raw.get(name, _POLICY_DEFAULTS[name]), low), high)

        return AccountPolicy(
            organization_id=user.organization_id,
            pin_length=pick("pin_length"),
            lockout_threshold=pick("lockout_threshold"),
            lockout_minutes=pick("lockout_minutes"),
            access_token_minutes=pick("access_token_minutes"),
            refresh_token_days=pick("refresh_token_days"),
            role_name=user.role,
            first_name=user.first_name,
            last_name=user.last_name,
            permissions=role_permissions(user.role),
        )

    # --- the simulated account of a number without one --------------------------------------

    @staticmethod
    def _digest(phone: str) -> str:
        parsed = PhoneNumber.parse(phone)
        return parsed.value if parsed is not None else phone

    def _remember(
        self,
        phone: str,
        device_id: str,
        operation: str,
        outcome: str,
        refusal: str | None,
        now: datetime,
    ) -> None:
        self._unknown.append(
            FakeAttempt(self._digest(phone), device_id, operation, outcome, refusal, now)
        )

    def _unknown_pin_tries(self, phone: str) -> int:
        digest = self._digest(phone)
        tries = sum(
            1
            for a in self._unknown
            if a.digest == digest and a.operation == "sign_in" and a.refusal == "unknown_number"
        )
        return min(tries, PIN_TRIES + 1)

    def _unknown_code_tries(self, phone: str, device_id: str, now: datetime) -> int | None:
        digest = self._digest(phone)
        issued = None
        for index, a in enumerate(self._unknown):
            if (
                a.digest == digest
                and a.device_id == device_id
                and a.occurred_at >= now - CODE_LIFETIME
                and (
                    a.operation == "forgot_pin"
                    or (a.operation == "code" and a.outcome == "code_resent")
                )
            ):
                issued = index
        if issued is None:
            return None
        return sum(
            1
            for a in self._unknown[issued + 1 :]
            if a.digest == digest
            and a.device_id == device_id
            and a.operation == "code"
            and a.refusal == "wrong_code"
        )

    # --- shared steps (the identity.* helpers) ----------------------------------------------

    def _insert_token(self, token: FakeToken) -> None:
        if self._token_of(token.token_hash) is not None:
            raise ValueError("duplicate refresh token digest")
        self._tokens.append(token)

    def _insert_code(
        self,
        user_id: UUID,
        purpose: CodePurpose,
        device_id: str,
        code_hash: str,
        created_at: datetime,
        expires_at: datetime,
        consumed: bool = False,
        failed_attempts: int = 0,
    ) -> FakeCode:
        code = FakeCode(
            uuid4(),
            user_id,
            purpose,
            device_id,
            code_hash,
            created_at,
            expires_at,
            consumed,
            failed_attempts,
        )
        self._codes.append(code)
        return code

    def _revoke_tokens(self, user_id: UUID, device_id: str | None = None) -> None:
        for token in self._tokens:
            if token.user_id == user_id and (device_id is None or token.device_id == device_id):
                token.revoked = True

    def _remove_devices(self, user_id: UUID, now: datetime, row_id: UUID | None = None) -> int:
        """``identity.remove_devices``: the live remembered rows removed are counted."""
        removed = [
            d
            for d in self._devices
            if d.user_id == user_id and (row_id is None or d.row_id == row_id) and not d.revoked
        ]
        live = sum(1 for d in removed if d.remembered and d.live(now))
        ids = {d.device_id for d in removed}
        for device in removed:
            device.revoked = True
        for token in self._tokens:
            if token.user_id == user_id and (row_id is None or token.device_id in ids):
                token.revoked = True
        for code in self._codes:
            if code.user_id == user_id and (row_id is None or code.device_id in ids):
                code.consumed = True
        return live

    def _code_caps(
        self, user_id: UUID, skip_cooldown: bool, replacement: bool, now: datetime
    ) -> bool:
        counted = [
            c
            for c in self._codes
            if c.user_id == user_id and not c.withdrawn and c.created_at > now - timedelta(days=1)
        ]
        cooling = (
            not skip_cooldown
            and not replacement
            and any(c.created_at + COOLDOWN > now for c in counted)
        )
        hourly = sum(1 for c in counted if c.created_at > now - timedelta(hours=1))
        return not (cooling or hourly >= HOURLY_CODES or len(counted) >= DAILY_CODES)

    def _issue_code(
        self,
        user: FakeUser,
        purpose: CodePurpose,
        device_id: str,
        code_hash: str | None,
        skip_cooldown: bool,
        replacement: bool,
        now: datetime,
    ) -> FakeCode | None:
        if code_hash is None or not self._code_caps(user.user_id, skip_cooldown, replacement, now):
            return None
        for code in self._codes:
            if code.user_id == user.user_id and code.purpose is purpose:
                code.consumed = True
        return self._insert_code(
            user.user_id, purpose, device_id, code_hash, now, now + CODE_LIFETIME, False
        )

    @staticmethod
    def _issued(
        kind: AuthOutcomeKind,
        user: FakeUser,
        code: FakeCode | None,
        purpose: CodePurpose,
        *,
        masked: bool = True,
        refusal: SignInRefusal | None = None,
    ) -> AuthOutcome:
        return AuthOutcome(
            kind,
            refusal=refusal,
            purpose=purpose,
            masked_email=mask_email(user.email) if masked else None,
            code_issued=code is not None,
            code_id=code.code_id if code else None,
            email=user.email if code else None,
        )

    def _matching_code(
        self,
        user: FakeUser,
        purpose: CodePurpose,
        device_id: str,
        code_hash: str | None,
        now: datetime,
    ) -> tuple[FakeCode | None, SignInRefusal | None, bool, int | None]:
        """``identity.matching_code``: the code, or the refusal, whether this try voided the
        code and the tries left."""
        candidates = [
            c
            for c in self._codes
            if c.user_id == user.user_id
            and c.purpose is purpose
            and c.device_id == device_id
            and not c.consumed
        ]
        if not candidates:
            return None, SignInRefusal.CODE_EXPIRED, False, None
        code = sorted(candidates, key=lambda c: c.created_at)[-1]
        if now > code.expires_at or code.failed_attempts >= CODE_TRIES:
            return None, SignInRefusal.CODE_EXPIRED, False, None
        if code_hash is None or code.code_hash != code_hash:
            code.failed_attempts += 1
            code.consumed = code.failed_attempts >= CODE_TRIES
            return (
                None,
                SignInRefusal.WRONG_CODE,
                code.consumed,
                max(CODE_TRIES - code.failed_attempts, 0),
            )
        return code, None, False, None

    def _trust_device(
        self,
        user_id: UUID,
        device_id: str,
        name: str | None,
        token_hash: str | None,
        remembered: bool,
        trust_days: int | None,
        now: datetime,
    ) -> None:
        expires_at = None if trust_days is None else now + timedelta(days=trust_days)
        device = self._device(user_id, device_id)
        if device is None:
            device = FakeDevice(user_id, device_id)
            self._devices.append(device)
        device.revoked = False
        device.trust_expires_at = expires_at
        device.token_hash = token_hash if remembered else None
        device.name = name if name is not None else device.name
        device.remembered = remembered
        device.trusted_at = now
        device.last_used_at = now

    def _issue_session(
        self,
        user: FakeUser,
        device_id: str,
        token_hash: str,
        policy: AccountPolicy,
        now: datetime,
        *,
        signing_in: bool = True,
    ) -> AuthOutcome:
        expires_at = now + timedelta(days=policy.refresh_token_days)
        self._insert_token(FakeToken(user.user_id, device_id, token_hash, expires_at))
        device = self._device(user.user_id, device_id)
        if device is not None:
            device.last_used_at = now
        if signing_in:
            user.last_signed_in_at = now
        return AuthOutcome(
            AuthOutcomeKind.AUTHENTICATED,
            user_id=user.user_id,
            organization_id=policy.organization_id,
            role=policy.role_name,
            first_name=policy.first_name,
            last_name=policy.last_name,
            permissions=policy.permissions,
            security_version=user.security_version,
            access_token_minutes=policy.access_token_minutes,
            refresh_expires_at=expires_at,
        )

    @staticmethod
    def _refused(
        refusal: SignInRefusal | None = None, tries_left: int | None = None
    ) -> AuthOutcome:
        return AuthOutcome(AuthOutcomeKind.REFUSED, refusal=refusal, tries_left=tries_left)

    @staticmethod
    def _locked_for(user: FakeUser, trusted: bool) -> bool:
        return user.failed_attempts >= PIN_TRIES or (
            not trusted and user.untrusted_failed_attempts >= PIN_TRIES
        )

    @staticmethod
    def _count_wrong_pin(user: FakeUser, trusted: bool) -> int:
        if trusted:
            user.failed_attempts = min(user.failed_attempts + 1, PIN_TRIES)
            return user.failed_attempts
        user.untrusted_failed_attempts = min(user.untrusted_failed_attempts + 1, PIN_TRIES)
        return user.untrusted_failed_attempts

    @staticmethod
    def _readiness(user: FakeUser, purpose: CodePurpose) -> tuple[bool, SignInRefusal | None]:
        """Whether a first-setup or reset request is blocked, and the refusal it carries."""
        refusal = None
        if user.status is not UserStatus.ACTIVE:
            refusal = SignInRefusal.INACTIVE
        elif purpose is CodePurpose.PIN_RESET and user.pin_hash is None:
            refusal = SignInRefusal.NO_PIN
        blocked = (
            refusal is not None
            or purpose not in (CodePurpose.FIRST_SETUP, CodePurpose.PIN_RESET)
            or (purpose is CodePurpose.FIRST_SETUP and user.pin_hash is not None)
        )
        return blocked, refusal

    # --- api.auth_start ---------------------------------------------------------------------

    def _start(self, command: NumberCheck) -> AuthOutcome:
        user = self._by_phone(command.phone)
        if user is None:
            if self._unknown_pin_tries(command.phone) >= PIN_TRIES:
                self._remember(
                    command.phone,
                    command.device_id,
                    "start",
                    "pin_locked",
                    "unknown_number",
                    command.now,
                )
                return AuthOutcome(AuthOutcomeKind.PIN_LOCKED, refusal=SignInRefusal.UNKNOWN_NUMBER)
            self._remember(
                command.phone,
                command.device_id,
                "start",
                "pin_required",
                "unknown_number",
                command.now,
            )
            return AuthOutcome(AuthOutcomeKind.PIN_REQUIRED, refusal=SignInRefusal.UNKNOWN_NUMBER)
        if user.status is not UserStatus.ACTIVE or self._policy_for(user) is None:
            return AuthOutcome(AuthOutcomeKind.BLOCKED, refusal=SignInRefusal.INACTIVE)
        if user.pin_hash is None or user.pin_reset_required:
            purpose = CodePurpose.FIRST_SETUP if user.pin_hash is None else CodePurpose.PIN_RESET
            code = self._issue_code(
                user,
                purpose,
                command.device_id,
                command.code_hash,
                command.skip_cooldown,
                False,
                command.now,
            )
            return self._issued(AuthOutcomeKind.VERIFICATION_REQUIRED, user, code, purpose)
        trusted = self._trusted(
            user.user_id, command.device_id, command.device_token_hash or "", command.now
        )
        if self._locked_for(user, trusted):
            return AuthOutcome(AuthOutcomeKind.PIN_LOCKED, refusal=SignInRefusal.LOCKED)
        return AuthOutcome(AuthOutcomeKind.PIN_REQUIRED)

    # --- api.auth_sign_in -------------------------------------------------------------------

    def _sign_in(self, verdict: PinVerdict) -> AuthOutcome:  # noqa: PLR0911 - check order
        user = self._users.get(verdict.user_id) if verdict.user_id is not None else None
        if user is None:
            return self._refused(SignInRefusal.UNKNOWN_NUMBER)
        if user.status is not UserStatus.ACTIVE:
            return self._refused(SignInRefusal.INACTIVE)
        if user.pin_hash is None:
            return self._refused(SignInRefusal.NO_PIN)
        if user.pin_reset_required:
            return self._refused(SignInRefusal.RESET_REQUIRED)
        now = verdict.now
        trusted = self._trusted(user.user_id, verdict.device_id, None, now)
        policy = self._policy_for(user)
        pause = (policy.lockout_minutes if policy else _POLICY_DEFAULTS["lockout_minutes"]) * 60
        if self._locked_for(user, trusted):
            if trusted:
                return AuthOutcome(
                    AuthOutcomeKind.PAUSED, refusal=SignInRefusal.LOCKED, retry_after_seconds=pause
                )
            return self._refused(SignInRefusal.LOCKED)
        if not verdict.pin_ok or user.pin_hash != verdict.checked_pin_hash:
            count = self._count_wrong_pin(user, trusted)
            if trusted and count >= PIN_TRIES:
                return AuthOutcome(
                    AuthOutcomeKind.PAUSED,
                    refusal=SignInRefusal.WRONG_PIN,
                    retry_after_seconds=pause,
                )
            return self._refused(SignInRefusal.WRONG_PIN)
        if policy is None:
            return self._refused(SignInRefusal.INACTIVE)
        if not trusted:
            code = self._issue_code(
                user,
                CodePurpose.NEW_DEVICE,
                verdict.device_id,
                verdict.code_hash,
                verdict.skip_cooldown,
                False,
                now,
            )
            return self._issued(
                AuthOutcomeKind.VERIFICATION_REQUIRED, user, code, CodePurpose.NEW_DEVICE
            )
        user.failed_attempts = 0
        return self._issue_session(user, verdict.device_id, verdict.refresh_token_hash, policy, now)

    # --- api.auth_pin -----------------------------------------------------------------------

    def _pin(self, command: PinCheck) -> AuthOutcome:  # noqa: PLR0911 - check order
        now = command.now
        user = self._by_phone(command.phone)
        if user is None:
            tries = self._unknown_pin_tries(command.phone)
            if tries >= PIN_TRIES:
                self._remember(
                    command.phone, command.device_id, "pin", "pin_locked", "unknown_number", now
                )
                return AuthOutcome(AuthOutcomeKind.PIN_LOCKED, refusal=SignInRefusal.UNKNOWN_NUMBER)
            self._remember(
                command.phone, command.device_id, "pin", "refused", "unknown_number", now
            )
            return self._refused(SignInRefusal.UNKNOWN_NUMBER, PIN_TRIES - tries)
        policy = self._policy_for(user)
        if user.status is not UserStatus.ACTIVE or policy is None:
            return AuthOutcome(AuthOutcomeKind.BLOCKED, refusal=SignInRefusal.INACTIVE)
        if user.pin_hash is None or user.pin_reset_required:
            purpose = CodePurpose.FIRST_SETUP if user.pin_hash is None else CodePurpose.PIN_RESET
            code = self._issue_code(
                user,
                purpose,
                command.device_id,
                command.code_hash,
                command.skip_cooldown,
                False,
                now,
            )
            return self._issued(AuthOutcomeKind.VERIFICATION_REQUIRED, user, code, purpose)
        trusted = self._trusted(
            user.user_id, command.device_id, command.device_token_hash or "", now
        )
        if self._locked_for(user, trusted):
            return AuthOutcome(AuthOutcomeKind.PIN_LOCKED, refusal=SignInRefusal.LOCKED)
        if not command.pin_ok or user.pin_hash != command.checked_pin_hash:
            count = self._count_wrong_pin(user, trusted)
            if count >= PIN_TRIES:
                return AuthOutcome(AuthOutcomeKind.PIN_LOCKED, refusal=SignInRefusal.WRONG_PIN)
            return self._refused(SignInRefusal.WRONG_PIN, PIN_TRIES - count)
        if not trusted:
            code = self._issue_code(
                user,
                CodePurpose.NEW_DEVICE,
                command.device_id,
                command.code_hash,
                command.skip_cooldown,
                False,
                now,
            )
            return self._issued(
                AuthOutcomeKind.VERIFICATION_REQUIRED, user, code, CodePurpose.NEW_DEVICE
            )
        user.failed_attempts = 0
        return self._issue_session(user, command.device_id, command.refresh_token_hash, policy, now)

    # --- api.auth_check_code ----------------------------------------------------------------

    def _check_code(self, command: CodeEntry) -> AuthOutcome:  # noqa: PLR0911 - check order
        now = command.now
        user = self._by_phone(command.phone)
        if user is None:
            tries = (
                self._unknown_code_tries(command.phone, command.device_id, now)
                if command.purpose is CodePurpose.PIN_RESET
                else None
            )
            if tries is None:
                self._remember(
                    command.phone, command.device_id, "code", "refused", "code_expired", now
                )
                return self._refused(SignInRefusal.CODE_EXPIRED)
            if tries + 1 >= CODE_TRIES:
                self._remember(
                    command.phone, command.device_id, "code", "code_resent", "wrong_code", now
                )
                return AuthOutcome(
                    AuthOutcomeKind.CODE_RESENT,
                    refusal=SignInRefusal.WRONG_CODE,
                    purpose=command.purpose,
                )
            self._remember(command.phone, command.device_id, "code", "refused", "wrong_code", now)
            return self._refused(SignInRefusal.WRONG_CODE, CODE_TRIES - (tries + 1))
        refusal = None
        if user.status is not UserStatus.ACTIVE:
            refusal = SignInRefusal.INACTIVE
        elif command.purpose is not CodePurpose.FIRST_SETUP and user.pin_hash is None:
            refusal = SignInRefusal.NO_PIN
        elif command.purpose is CodePurpose.NEW_DEVICE and user.pin_reset_required:
            refusal = SignInRefusal.RESET_REQUIRED
        if refusal is not None or (
            command.purpose is CodePurpose.FIRST_SETUP and user.pin_hash is not None
        ):
            return self._refused(refusal)
        code, failure, voided, tries_left = self._matching_code(
            user, command.purpose, command.device_id, command.code_hash, now
        )
        if code is None:
            if voided:
                replacement = self._issue_code(
                    user,
                    command.purpose,
                    command.device_id,
                    command.replacement_code_hash,
                    False,
                    True,
                    now,
                )
                return self._issued(
                    AuthOutcomeKind.CODE_RESENT,
                    user,
                    replacement,
                    command.purpose,
                    masked=False,
                    refusal=SignInRefusal.WRONG_CODE,
                )
            return self._refused(failure, tries_left)
        if command.purpose is not CodePurpose.NEW_DEVICE:
            return AuthOutcome(AuthOutcomeKind.CODE_VERIFIED, purpose=command.purpose)
        policy = self._policy_for(user)
        if policy is None:
            return self._refused(SignInRefusal.INACTIVE)
        code.consumed = True
        user.failed_attempts = 0
        user.untrusted_failed_attempts = 0
        self._trust_device(
            user.user_id,
            command.device_id,
            command.device_name,
            command.device_token_hash,
            command.trust,
            command.trust_days,
            now,
        )
        outcome = self._issue_session(
            user, command.device_id, command.refresh_token_hash, policy, now
        )
        return replace(
            outcome, device_token_issued=command.trust and command.device_token_hash is not None
        )

    # --- api.auth_resend_code ---------------------------------------------------------------

    def _resend_code(self, command: CodeResend) -> AuthOutcome:
        now = command.now
        user = self._by_phone(command.phone)
        if user is None:
            self._remember(
                command.phone,
                command.device_id,
                "resend_code",
                "verification_required",
                "unknown_number",
                now,
            )
            return AuthOutcome(AuthOutcomeKind.VERIFICATION_REQUIRED, purpose=command.purpose)
        recent = any(
            c.user_id == user.user_id
            and c.purpose is command.purpose
            and c.device_id == command.device_id
            and c.created_at > now - CODE_LIFETIME
            and not c.withdrawn
            for c in self._codes
        )
        has_pin = user.pin_hash is not None
        allowed = (
            user.status is UserStatus.ACTIVE
            and self._policy_for(user) is not None
            and (
                (
                    command.purpose is CodePurpose.NEW_DEVICE
                    and has_pin
                    and not user.pin_reset_required
                    and recent
                )
                or (command.purpose is CodePurpose.FIRST_SETUP and not has_pin)
                or (
                    command.purpose is CodePurpose.PIN_RESET
                    and has_pin
                    and (user.pin_reset_required or recent)
                )
            )
        )
        code = (
            self._issue_code(
                user,
                command.purpose,
                command.device_id,
                command.code_hash,
                command.skip_cooldown,
                False,
                now,
            )
            if allowed
            else None
        )
        return self._issued(
            AuthOutcomeKind.VERIFICATION_REQUIRED, user, code, command.purpose, masked=False
        )

    # --- api.auth_verify_device -------------------------------------------------------------

    def _verify_device(self, command: DeviceVerification) -> AuthOutcome:  # noqa: PLR0911 - check order
        user = self._by_phone(command.phone)
        if user is None:
            return self._refused(SignInRefusal.UNKNOWN_NUMBER)
        if user.status is not UserStatus.ACTIVE:
            return self._refused(SignInRefusal.INACTIVE)
        if user.pin_hash is None:
            return self._refused(SignInRefusal.NO_PIN)
        if user.pin_reset_required:
            return self._refused(SignInRefusal.RESET_REQUIRED)
        code, failure, voided, _ = self._matching_code(
            user, CodePurpose.NEW_DEVICE, command.device_id, command.code_hash, command.now
        )
        if code is None:
            return self._replaced(user, failure, voided, CodePurpose.NEW_DEVICE, command)
        policy = self._policy_for(user)
        if policy is None:
            return self._refused(SignInRefusal.INACTIVE)
        code.consumed = True
        user.failed_attempts = 0
        user.untrusted_failed_attempts = 0
        self._trust_device(
            user.user_id, command.device_id, None, None, True, command.trust_days, command.now
        )
        return self._issue_session(
            user, command.device_id, command.refresh_token_hash, policy, command.now
        )

    def _replaced(
        self,
        user: FakeUser,
        failure: SignInRefusal | None,
        voided: bool,
        purpose: CodePurpose,
        command: DeviceVerification | CodeCheck,
    ) -> AuthOutcome:
        """A released route's refusal of a code; the third wrong try issues the replacement."""
        if not voided:
            return self._refused(failure)
        code = self._issue_code(
            user,
            purpose,
            command.device_id,
            command.replacement_code_hash,
            False,
            True,
            command.now,
        )
        return AuthOutcome(
            AuthOutcomeKind.REFUSED,
            refusal=failure,
            purpose=purpose,
            code_issued=code is not None,
            code_id=code.code_id if code else None,
            email=user.email if code else None,
        )

    # --- api.auth_request_code / verify_code / complete_pin ---------------------------------

    def _request_code(self, command: CodeRequest) -> AuthOutcome:
        user = self._by_phone(command.phone)
        operation = "forgot_pin" if command.purpose is CodePurpose.PIN_RESET else "request_code"
        if user is None:
            self._remember(
                command.phone,
                command.device_id,
                operation,
                "check_email",
                "unknown_number",
                command.now,
            )
            return AuthOutcome(
                AuthOutcomeKind.SILENT,
                refusal=SignInRefusal.UNKNOWN_NUMBER,
                purpose=command.purpose,
            )
        blocked, refusal = self._readiness(user, command.purpose)
        code = (
            None
            if blocked
            else self._issue_code(
                user,
                command.purpose,
                command.device_id,
                command.code_hash,
                command.skip_cooldown,
                False,
                command.now,
            )
        )
        if code is None:
            return AuthOutcome(AuthOutcomeKind.SILENT, refusal=refusal, purpose=command.purpose)
        return AuthOutcome(
            AuthOutcomeKind.CHECK_EMAIL,
            purpose=command.purpose,
            code_issued=True,
            code_id=code.code_id,
            email=user.email,
        )

    def _verify_code(self, command: CodeCheck) -> AuthOutcome:
        user = self._by_phone(command.phone)
        if user is None:
            return self._refused(SignInRefusal.UNKNOWN_NUMBER)
        blocked, refusal = self._readiness(user, command.purpose)
        if blocked:
            return self._refused(refusal)
        code, failure, voided, _ = self._matching_code(
            user, command.purpose, command.device_id, command.code_hash, command.now
        )
        if code is None:
            return self._replaced(user, failure, voided, command.purpose, command)
        return AuthOutcome(AuthOutcomeKind.CODE_VERIFIED, purpose=command.purpose)

    def _complete_pin(self, command: PinCompletion) -> AuthOutcome:  # noqa: PLR0911 - check order
        user = self._by_phone(command.phone)
        if user is None:
            return self._refused(SignInRefusal.UNKNOWN_NUMBER)
        blocked, refusal = self._readiness(user, command.purpose)
        if blocked:
            return self._refused(refusal)
        code, failure, _, _ = self._matching_code(
            user, command.purpose, command.device_id, command.code_hash, command.now
        )
        if code is None:
            return self._refused(failure)
        if command.purpose is CodePurpose.PIN_RESET:
            if command.checked_pin_hash != user.pin_hash:
                return self._refused(SignInRefusal.VERDICT_VOID)
            if command.new_pin_is_current:
                return AuthOutcome(
                    AuthOutcomeKind.INVALID_PIN,
                    refusal=SignInRefusal.PIN_RULE,
                    pin_problem=PinProblem.UNCHANGED,
                    minimum_pin_length=4,
                )
        policy = self._policy_for(user)
        if policy is None:
            return self._refused(SignInRefusal.INACTIVE)
        code.consumed = True
        user.pin_hash = command.pin_hash
        user.untrusted_failed_attempts = 0
        user.failed_attempts = 0
        user.pin_reset_required = False
        user.security_version += 1
        if command.purpose is CodePurpose.PIN_RESET:
            self._remove_devices(user.user_id, command.now)
        else:
            self._revoke_tokens(user.user_id)
            for other in self._codes:
                if other.user_id == user.user_id:
                    other.consumed = True
        self._trust_device(
            user.user_id,
            command.device_id,
            command.device_name,
            command.device_token_hash,
            command.trust,
            command.trust_days,
            command.now,
        )
        outcome = self._issue_session(
            user, command.device_id, command.refresh_token_hash, policy, command.now
        )
        return replace(
            outcome, device_token_issued=command.trust and command.device_token_hash is not None
        )

    # --- api.auth_change_pin ----------------------------------------------------------------

    def _change_pin(self, command: PinChange) -> AuthOutcome:
        user = self._users.get(command.user_id)
        if user is None:
            return self._refused(SignInRefusal.UNKNOWN_NUMBER)
        if user.status is not UserStatus.ACTIVE or user.pin_hash is None:
            return self._refused(SignInRefusal.INACTIVE)
        if user.failed_attempts >= PIN_TRIES:
            return AuthOutcome(AuthOutcomeKind.PIN_LOCKED, refusal=SignInRefusal.LOCKED)
        if not command.current_ok or user.pin_hash != command.checked_pin_hash:
            count = self._count_wrong_pin(user, True)
            if count >= PIN_TRIES:
                return AuthOutcome(AuthOutcomeKind.PIN_LOCKED, refusal=SignInRefusal.WRONG_PIN)
            return self._refused(SignInRefusal.WRONG_PIN, PIN_TRIES - count)
        user.pin_hash = command.pin_hash
        user.failed_attempts = 0
        user.untrusted_failed_attempts = 0
        return AuthOutcome(AuthOutcomeKind.PIN_CHANGED)

    # --- api.auth_refresh -------------------------------------------------------------------

    def _refresh(self, command: TokenRefresh) -> AuthOutcome:
        token = self._token_of(command.token_hash)
        if token is None or token.device_id != command.device_id:
            return self._refused(SignInRefusal.TOKEN_UNKNOWN)
        user = self._users[token.user_id]
        refused = self._refresh_refusal(user, token, command)
        if refused is not None:
            return refused
        policy = self._policy_for(user)
        if policy is None:
            return self._refused(SignInRefusal.INACTIVE)
        token.revoked = True
        return self._issue_session(
            user, command.device_id, command.new_token_hash, policy, command.now, signing_in=False
        )

    def _refresh_refusal(
        self, user: FakeUser, token: FakeToken, command: TokenRefresh
    ) -> AuthOutcome | None:
        now = command.now
        if user.status is not UserStatus.ACTIVE:
            self._revoke_tokens(user.user_id)
            return self._refused(SignInRefusal.INACTIVE)
        if token.revoked:
            self._revoke_tokens(user.user_id, command.device_id)
            return self._refused(SignInRefusal.TOKEN_REPLAYED)
        if now >= token.expires_at:
            return self._refused(SignInRefusal.TOKEN_EXPIRED)
        if user.failed_attempts >= PIN_TRIES:
            return self._refused(SignInRefusal.LOCKED)
        device = self._device(user.user_id, command.device_id)
        if device is None or not device.live(now):
            return self._refused(SignInRefusal.DEVICE_UNTRUSTED)
        return None


# --- tenancy: access, people, the change log and organization settings, in memory -----------

_LOCALIZATION_DEFAULTS: dict[str, Any] = {
    "locale": "en-GB",
    "time_zone": "Africa/Nairobi",
    "date_pattern": "medium",
    "hour12": False,
    "first_day_of_week": 1,
    "week_numbering": "iso8601",
    "currency": "KES",
    "use_grouping": True,
    "number_decimals": 2,
    "allow_locale_override": True,
    "allow_time_zone_override": False,
    "allow_hour12_override": True,
    "allow_theme_override": True,
}
_BRANDING_DEFAULTS: dict[str, Any] = {
    "display_name": "XCODE",
    "legal_name": "XCODE",
    "logo_light": None,
    "logo_dark": None,
    "logo_alt": "XCODE",
    "favicon": None,
    "primary": "#1D5FD6",
    "secondary": "#14213D",
    "accent": "#1E6B3A",
    "domain": None,
    "support_email": None,
    "terms_url": None,
    "privacy_url": None,
}
_POLICY_SECTION_DEFAULTS: dict[str, Any] = {
    "password_min_length": 12,
    "password_complexity": True,
    "password_history": 5,
    "pin_length": 4,
    "lockout_threshold": 5,
    "lockout_minutes": 15,
    "access_token_minutes": 10,
    "refresh_token_days": 30,
    "idle_unlock_seconds": 900,
    "allow_pin_sign_in": True,
}
_REVENUE_SECTION_DEFAULTS: dict[str, Any] = {
    "low_day_threshold": Decimal(4000),
    "gap_amber_percent": Decimal(10),
}
_SECTION_DEFAULTS = {
    "localization": _LOCALIZATION_DEFAULTS,
    "branding": _BRANDING_DEFAULTS,
    "securityPolicy": _POLICY_SECTION_DEFAULTS,
    "revenue": _REVENUE_SECTION_DEFAULTS,
}
_SETTING_WORDS = {
    "name": "the organization name",
    "hour12": "the 12-hour clock",
    "datePattern": "the date format",
    "firstDayOfWeek": "the first day of the week",
    "weekNumbering": "week numbering",
    "useGrouping": "digit grouping",
    "numberDecimals": "the decimal places",
    "allowLocaleOverride": "personal locales",
    "allowTimeZoneOverride": "personal time zones",
    "allowHour12Override": "personal clock formats",
    "allowThemeOverride": "personal themes",
    "logoLight": "the light logo",
    "logoDark": "the dark logo",
    "primary": "the primary colour",
    "secondary": "the secondary colour",
    "accent": "the accent colour",
    "passwordComplexity": "password complexity",
    "pinLength": "the PIN length",
    "lockoutThreshold": "the wrong PIN tries before a pause",
    "lockoutMinutes": "the pause in minutes",
    "allowPinSignIn": "PIN sign-in",
    "logoAlt": "the logo text",
    "lowDayThreshold": "the low-day threshold",
    "gapAmberPercent": "the amber band",
}
_WEEKDAYS = ("Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday")


def _compact(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)


def _camel(key: str) -> str:
    head, *rest = key.split("_")
    return head + "".join(part[:1].upper() + part[1:] for part in rest)


def _join(parts: list[str]) -> str:
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]


def _checked_section(section: str, merged: dict[str, Any]) -> dict[str, Any]:
    return _revenue_settings(merged) if section == "revenue" else merged


def _revenue_settings(values: dict[str, Any]) -> dict[str, Any]:
    """``tenancy.check_revenue_settings`` over the merged section: JSON numbers only, the
    threshold 0 to 999,999,999,999.99 and the amber band 0 to 100, two decimal places each."""
    numbers = (int, float, Decimal)
    if any(isinstance(v, bool) or not isinstance(v, numbers) for v in values.values()):
        raise RuleViolation(code="settings_wrong_type")
    read = {key: Decimal(str(value)) for key, value in values.items()}
    threshold, amber = read["low_day_threshold"], read["gap_amber_percent"]
    if (
        not Decimal(0) <= threshold <= Decimal("999999999999.99")
        or not Decimal(0) <= amber <= Decimal(100)
        or any(v != round(v, 2) for v in read.values())
    ):
        raise RuleViolation(code="revenue_settings_invalid")
    return read


def _setting_word(key: str) -> str:
    if key in _SETTING_WORDS:
        return _SETTING_WORDS[key]
    return "the " + re.sub(r"([a-z])([A-Z])", r"\1 \2", key).lower()


def _setting_value(key: str, value: Any) -> str:
    if value is None:
        return "none"
    if isinstance(value, bool):
        return "on" if value else "off"
    if key == "firstDayOfWeek" and isinstance(value, int) and 0 <= value <= 6:
        return _WEEKDAYS[value]
    if key == "gapAmberPercent" and isinstance(value, int | float):
        return f"{json.dumps(value)} per cent"
    return value if isinstance(value, str) else json.dumps(value)


def expand_permissions(keys: Iterable[str]) -> tuple[str, ...]:
    """``tenancy.expand_permissions``: the catalogue keys among ``keys`` with their
    dependencies, in catalogue order."""
    needs = _needs()
    held = {key for key in keys if key in needs}
    pending = list(held)
    while pending:
        for need in needs[pending.pop()]:
            if need not in held:
                held.add(need)
                pending.append(need)
    return tuple(key for key in needs if key in held)


def _modules(rights: Iterable[str]) -> list[tuple[str, int, int]]:
    held = set(rights)
    return [
        (
            group["name"],
            sum(item["key"] in held for item in group["items"]),
            len(group["items"]),
        )
        for group in _catalogue()["groups"]
    ]


def _months_back(day: date, months: int) -> date:
    index = day.year * 12 + day.month - 1 - months
    year, month = divmod(index, 12)
    following = date(year + (month + 1) // 12, (month + 1) % 12 + 1, 1)
    return date(year, month + 1, min(day.day, (following - timedelta(days=1)).day))


def earliest_writable(mode: str, count: int | None, since: date | None, today: date) -> date | None:
    """``tenancy.earliest_writable``: the first date a person may change on ``today``; ``None``
    for any date."""
    rolling = None
    if mode == "days" and count is not None:
        rolling = today - timedelta(days=count)
    elif mode == "months" and count is not None:
        rolling = _months_back(today, count)
    if rolling is None or since is None:
        return rolling or since
    return max(rolling, since)


def back_limit_words(mode: str, count: int | None, since: date | None) -> str:
    """``tenancy.back_limit_words``: the "Can change" words of the people list."""
    fixed = None if since is None else f"{since.day} {since:%B} {since.year}"
    if mode in ("days", "months") and count is not None:
        unit = "day" if mode == "days" else "month"
        words = "Today only" if count == 0 else f"{count} {unit}{'' if count == 1 else 's'} back"
        return words if fixed is None else f"{words}, not before {fixed}"
    return "Any date" if fixed is None else f"Not before {fixed}"


@dataclass(slots=True)
class FakeMember:
    """One person of the fake organization: membership, sign-in details, role and access."""

    user_id: UUID
    first_name: str
    last_name: str
    email: str
    phone: str
    role: str
    rights: tuple[str, ...]
    active: bool = True
    version: int = 1
    scope_mode: str = "all"
    company_ids: tuple[UUID, ...] = ()
    vehicle_ids: tuple[UUID, ...] = ()
    approval_limit: Decimal | None = None
    has_pin: bool = False
    pin_reset_required: bool = False
    lock: str | None = None
    last_signed_in_at: datetime | None = None
    back_limit_mode: str = "none"
    back_limit_count: int | None = None
    back_limit_from: date | None = None
    devices: list[PersonDevice] = field(default_factory=list)

    @property
    def status(self) -> SignInStatus:
        if not self.active:
            return SignInStatus.BLOCKED
        if not self.has_pin:
            return SignInStatus.NOT_SIGNED_IN
        if self.pin_reset_required:
            return SignInStatus.PIN_RESET_DUE
        if self.lock is not None:
            return SignInStatus.LOCKED
        return SignInStatus.ACTIVE

    @property
    def permissions(self) -> tuple[str, ...]:
        """What the member holds now: their catalogue rights, the legacy keys those imply and
        their role's hidden keys (``tenancy.effective_permissions``)."""
        return held_permissions(self.rights, self.role)

    def held(self) -> tuple[str, ...]:
        return self.permissions

    def sign_in_snapshot(self) -> str:
        words = {
            SignInStatus.ACTIVE: "Active",
            SignInStatus.NOT_SIGNED_IN: "Not signed in yet",
            SignInStatus.PIN_RESET_DUE: "PIN reset due",
            SignInStatus.LOCKED: "Locked",
            SignInStatus.BLOCKED: "Blocked",
        }
        devices = sorted(self.devices, key=lambda d: (d.trusted_at, str(d.id)))
        return _compact({"Status": words[self.status], "Devices": [d.name for d in devices]})

    def snapshot(self) -> str:
        limit = None
        if self.approval_limit is not None:
            normalised = self.approval_limit.normalize()
            limit = int(normalised) if normalised == normalised.to_integral() else float(normalised)
        return _compact(
            {
                "FirstName": self.first_name,
                "LastName": self.last_name,
                "Email": self.email,
                "PhoneNumber": self.phone,
                "Role": self.role,
                "Active": self.active,
                "ScopeMode": self.scope_mode,
                "CompanyIds": sorted(str(i) for i in self.company_ids),
                "VehicleIds": sorted(str(i) for i in self.vehicle_ids),
                "Permissions": sorted((*self.rights, *hidden_rights(self.role))),
                "ApprovalLimit": limit,
                "BackLimitMode": self.back_limit_mode,
                "BackLimitCount": self.back_limit_count,
                "BackLimitFrom": None
                if self.back_limit_from is None
                else self.back_limit_from.isoformat(),
                "Name": f"{self.first_name} {self.last_name}",
            }
        )


class FakeTenancyRepository:
    """In-memory ``TenancyRepository`` over one organization.

    ``tests/db/test_fakes_match_routines.py`` runs ``tests/support/tenancy_cases.py`` against
    this fake and the real routines: creating and updating a person (the shape refusals, the
    version rules, the change set and its reason, unchanged saves), saving a settings section
    (merge, changed and unchanged, one version per logged save) and paging the change log by
    offset and by version. Everything else answers the happy path of an all-companies Owner:
    no data-scope, anti-escalation or visibility rules, no validation beyond the shapes above
    and the back-dating limit; the people status and the sign-in pane come from the member's
    fields (``has_pin``, ``pin_reset_required``, ``lock``, ``devices``) as a test sets them.
    """

    def __init__(self) -> None:
        self.organization_id = uuid4()
        self.name = "My fleet"
        self.slug = "my-fleet"
        self.business_date: date | None = None
        self.settings_version = 1
        self.members: dict[UUID, FakeMember] = {}
        self.sections: dict[str, dict[str, Any]] = {
            name: dict(values) for name, values in _SECTION_DEFAULTS.items()
        }
        self.revenue_row = False
        self.logo: LogoUpload | None = None
        self.preference_rows: dict[UUID, UserPreferences] = {}
        self.log: list[HistoryEntry] = []

    # --- arranging state --------------------------------------------------------------------

    def add_member(
        self,
        *,
        email: str = "jane.doe@example.com",
        phone: str = "0712345678",
        role: str = "Owner",
        first_name: str = "Jane",
        last_name: str = "Doe",
    ) -> UUID:
        parsed = PhoneNumber.parse(phone)
        if parsed is None:
            raise ValueError(f"{phone!r} does not normalise to a phone number")
        member = FakeMember(
            user_id=uuid4(),
            first_name=first_name,
            last_name=last_name,
            email=email,
            phone=parsed.value,
            role=role,
            rights=role_rights(role),
        )
        self.members[member.user_id] = member
        return member.user_id

    # --- access and people ------------------------------------------------------------------

    async def access_catalog(self, context: TenantContext) -> tuple[PermissionGroup, ...]:
        self._enter(context)
        return tuple(
            PermissionGroup(
                name=group["name"],
                items=tuple(
                    PermissionItem(
                        key=item["key"],
                        label=item["label"],
                        needs=tuple(item["needs"]),
                        section=None
                        if item["section"] is None
                        else PermissionSection(item["section"]),
                    )
                    for item in group["items"]
                ),
            )
            for group in _catalogue()["groups"]
        )

    async def access_roles(self, context: TenantContext) -> tuple[AccessRole, ...]:
        self._enter(context, "people.view")
        return tuple(
            AccessRole(
                id=uuid5(self.organization_id, name), name=name, permissions=role_rights(name)
            )
            for name in sorted(role_names())
        )

    async def scope_options(self, context: TenantContext) -> ScopeOptions:
        member = self._enter(context)
        if not {"people.add", "people.edit"} & set(member.held()):
            raise Forbidden(code="permission_missing")
        return ScopeOptions(companies=(), vehicles=())

    async def my_scope(self, context: TenantContext) -> MyScope:
        member = self._enter(context)
        return MyScope(
            all_companies=True,
            companies=(),
            vehicles=(),
            can_change=back_limit_words(
                member.back_limit_mode, member.back_limit_count, member.back_limit_from
            ),
            earliest=earliest_writable(
                member.back_limit_mode,
                member.back_limit_count,
                member.back_limit_from,
                self._today(context),
            ),
        )

    async def list_people(self, query: PeopleQuery) -> PeoplePage:
        self._enter(query.context, "people.view")
        if not (1 <= query.page <= 100_000 and 1 <= query.page_size <= 100):
            raise RuleViolation(code="page_out_of_range")
        aliases = {"waiting": "not_signed_in", "none": "blocked", "all": None, "": None}
        status = query.status
        if status is not None:
            if status not in aliases and status not in {s.value for s in SignInStatus}:
                raise RuleViolation(code="people_filter_status_invalid")
            status = aliases.get(status, status)
        role = (query.role or "all").lower()
        ordered = sorted(
            (
                m
                for m in self.members.values()
                if (role in ("all", "") or m.role.lower() == role)
                and (status is None or m.status == status)
            ),
            key=lambda m: (m.last_name, m.first_name, str(m.user_id)),
        )
        start = (query.page - 1) * query.page_size
        page = ordered[start : start + query.page_size]
        return PeoplePage(items=tuple(self._person(m) for m in page), total=len(ordered))

    async def get_person(self, query: PersonQuery) -> Person:
        self._enter(query.context, "people.view")
        member = self.members.get(query.user_id)
        if member is None:
            raise NotFound(code="not_found")
        live = sorted(member.devices, key=lambda d: (d.last_used_at, str(d.id)), reverse=True)
        return replace(
            self._person(member),
            sign_in=PersonSignIn(
                status=member.status,
                lock=member.lock,
                last_signed_in_at=member.last_signed_in_at,
                email=member.email,
                devices=tuple(live),
            ),
        )

    async def create_person(self, command: PersonSave) -> WriteResult:
        self._enter(command.context, "people.add")
        fields = self._checked(command.details, self._today(command.context), creating=True)
        if any(
            m.email == fields["email"] or m.phone == fields["phone"] for m in self.members.values()
        ):
            raise RuleViolation(code="people_contact_taken")
        member = FakeMember(user_id=uuid4(), **fields)
        self.members[member.user_id] = member
        self._record(
            command.context,
            "people",
            member.user_id,
            "null",
            member.snapshot(),
            f"Added {member.first_name} {member.last_name} as {member.role}",
        )
        return WriteResult(id=member.user_id, version=1, outcome=WriteOutcome.CREATED)

    async def update_person(self, command: PersonSave) -> WriteResult:
        self._enter(command.context, "people.edit")
        if command.user_id is None:
            raise NotFound(code="not_found")
        fields = self._checked(command.details, self._today(command.context), creating=False)
        member = self.members.get(command.user_id)
        if member is None:
            raise NotFound(code="not_found")
        if fields["back_limit_mode"] is None:
            fields["back_limit_mode"] = member.back_limit_mode
            fields["back_limit_count"] = member.back_limit_count
            fields["back_limit_from"] = member.back_limit_from
        if command.expected_version is None:
            raise RuleViolation(code="people_version_required")
        if command.expected_version != member.version:
            raise Conflict(code="version_conflict")
        if command.user_id == command.context.actor_id:
            raise RuleViolation(code="people_self_edit")
        if any(
            (m.email == fields["email"] or m.phone == fields["phone"]) and m is not member
            for m in self.members.values()
        ):
            raise RuleViolation(code="people_contact_taken")
        changes = [
            word
            for word, changed in (
                (
                    "name",
                    (fields["first_name"], fields["last_name"])
                    != (member.first_name, member.last_name),
                ),
                (
                    "sign-in details",
                    (fields["email"], fields["phone"]) != (member.email, member.phone),
                ),
                ("role", fields["role"] != member.role),
                (
                    "single permissions",
                    set(fields["rights"]) ^ set(role_rights(fields["role"]))
                    != set(member.rights) ^ set(role_rights(member.role)),
                ),
                (
                    "data scope",
                    (fields["scope_mode"], set(fields["company_ids"]), set(fields["vehicle_ids"]))
                    != (member.scope_mode, set(member.company_ids), set(member.vehicle_ids)),
                ),
                ("approval limit", fields["approval_limit"] != member.approval_limit),
                (
                    "how far back they can change records",
                    (
                        fields["back_limit_mode"],
                        fields["back_limit_count"],
                        fields["back_limit_from"],
                    )
                    != (member.back_limit_mode, member.back_limit_count, member.back_limit_from),
                ),
            )
            if changed
        ]
        if not changes:
            return WriteResult(
                id=member.user_id, version=member.version, outcome=WriteOutcome.UNCHANGED
            )
        before = member.snapshot()
        for name, value in fields.items():
            setattr(member, name, value)
        member.version += 1
        self._record(
            command.context,
            "people",
            member.user_id,
            before,
            member.snapshot(),
            f"Changed {_join(changes)} for {member.first_name} {member.last_name}",
        )
        return WriteResult(id=member.user_id, version=member.version, outcome=WriteOutcome.UPDATED)

    async def set_person_active(self, command: PersonLifecycle) -> WriteResult:
        self._enter(command.context, "people.block")
        if command.user_id == command.context.actor_id:
            raise RuleViolation(code="people_self_deactivate")
        member = self.members.get(command.user_id)
        if member is None:
            raise NotFound(code="not_found")
        if member.active == command.active:
            return WriteResult(
                id=member.user_id, version=member.version, outcome=WriteOutcome.UNCHANGED
            )
        if command.expected_version != member.version:
            raise Conflict(code="version_conflict")
        reason = (command.reason or "").strip()
        if not command.active and not 1 <= len(reason) <= 500:
            raise RuleViolation(code="reason_length")
        before = member.snapshot()
        member.active = command.active
        member.version += 1
        name = f"{member.first_name} {member.last_name}"
        automatic = (
            f"Restored access for {name}" if command.active else f"Removed access for {name}"
        )
        if not command.active:
            automatic += f". Reason: {reason}" + ("" if reason[-1] in ".!?" else ".")
        self._record(
            command.context, "people", member.user_id, before, member.snapshot(), automatic
        )
        return WriteResult(id=member.user_id, version=member.version, outcome=WriteOutcome.UPDATED)

    async def sign_out_person(self, command: PersonSignOut) -> WriteResult:
        member = self._sign_in_target(command.context, command.user_id, "people_self_sign_out")
        if not member.devices:
            return WriteResult(
                id=member.user_id, version=member.version, outcome=WriteOutcome.UNCHANGED
            )
        before = member.sign_in_snapshot()
        member.devices.clear()
        self._record(
            command.context,
            "signIn",
            member.user_id,
            before,
            member.sign_in_snapshot(),
            f"Trusted device removed, {member.first_name} {member.last_name}",
        )
        return WriteResult(id=member.user_id, version=member.version, outcome=WriteOutcome.UPDATED)

    async def require_pin_reset(self, command: PersonPinReset) -> WriteResult:
        member = self._sign_in_target(command.context, command.user_id, "people_self_sign_in")
        if not member.has_pin or member.pin_reset_required:
            return WriteResult(
                id=member.user_id, version=member.version, outcome=WriteOutcome.UNCHANGED
            )
        before = member.sign_in_snapshot()
        member.devices.clear()
        member.pin_reset_required = True
        self._record(
            command.context,
            "signIn",
            member.user_id,
            before,
            member.sign_in_snapshot(),
            f"PIN reset required, {member.first_name} {member.last_name}",
        )
        return WriteResult(id=member.user_id, version=member.version, outcome=WriteOutcome.UPDATED)

    async def remove_person_device(self, command: PersonDeviceRemoval) -> WriteResult:
        member = self._sign_in_target(command.context, command.user_id, "people_self_sign_in")
        device = next((d for d in member.devices if d.id == command.device_id), None)
        if device is None:
            raise NotFound(code="not_found")
        before = member.sign_in_snapshot()
        member.devices.remove(device)
        self._record(
            command.context,
            "signIn",
            member.user_id,
            before,
            member.sign_in_snapshot(),
            f"Trusted device removed, {member.first_name} {member.last_name}",
        )
        return WriteResult(id=member.user_id, version=member.version, outcome=WriteOutcome.UPDATED)

    # --- change log -------------------------------------------------------------------------

    async def list_history(self, query: HistoryQuery) -> HistoryPage:
        self._enter(query.context, "audit.view")
        f = query.filter
        text = (f.text or "").strip() or None
        if f.from_date is not None and f.to_date is not None and f.from_date > f.to_date:
            raise RuleViolation(code="history_dates_order")
        if text is not None and len(text) > 200:
            raise RuleViolation(code="history_text_length")
        if f.before is not None and f.before < 1:
            raise RuleViolation(code="history_before_invalid")
        if not (1 <= f.page <= 100_000 and 1 <= f.page_size <= 100):
            raise RuleViolation(code="page_out_of_range")
        section = (f.section or "").strip() or None
        matching = [
            entry
            for entry in sorted(self.log, key=lambda e: -e.version)
            if (section is None or entry.section == section)
            and (
                text is None
                or text.lower() in entry.reason.lower()
                or text.lower() in entry.actor_name.lower()
            )
        ]
        if f.before is None:
            window = matching[(f.page - 1) * f.page_size :]
        else:
            window = [entry for entry in matching if entry.version < f.before]
        items = tuple(window[: f.page_size])
        has_more = len(window) > f.page_size
        return HistoryPage(
            items=items,
            total=len(matching) if f.include_total else None,
            has_more=has_more,
            next_before=items[-1].version if has_more else None,
        )

    # --- organization settings, logo, appearance, preferences -------------------------------

    async def organization_settings(self, context: TenantContext) -> OrganizationSettings:
        self._enter(context, "organization.manage")
        today = context.now.date()
        return OrganizationSettings(
            organization=OrganizationDetails(
                id=self.organization_id,
                slug=self.slug,
                name=self.name,
                business_date=self.business_date,
                settings_version=self.settings_version,
            ),
            localization=self._localization(),
            branding=self._branding(),
            security_policy=self._policy(),
            effective_business_date=self.business_date or today,
            calendar_date=today,
            effective=self._effective(context.actor_id),
            revenue=RevenueSettings(
                organization_id=self.organization_id, **self.sections["revenue"]
            ),
        )

    async def save_settings(self, command: SettingsSave) -> WriteResult:
        self._enter(command.context, "organization.manage")
        reason = (command.reason or "").strip() or None
        if reason is not None and len(reason) > 500:
            raise RuleViolation(code="reason_length")
        section = command.section
        value = command.value
        if section == "organization":
            if not isinstance(value, dict):
                raise RuleViolation(code="settings_not_object")
            name = str(value.get("name") or "").strip()
            slug = str(value.get("slug") or "").strip().lower()
            if not name or not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", slug):
                raise RuleViolation(code="organization_name_slug")
            if (name, slug) == (self.name, self.slug):
                return self._unchanged()
            before = _compact({"name": self.name, "slug": self.slug})
            self.name, self.slug = name, slug
            after = _compact({"name": name, "slug": slug})
            automatic = self._settings_reason(section, before, after)
        elif section == "businessDate":
            held = date.fromisoformat(value) if isinstance(value, str) else None
            if held == self.business_date:
                return self._unchanged()
            before = _compact(
                None if self.business_date is None else self.business_date.isoformat()
            )
            self.business_date = held
            after = _compact(None if held is None else held.isoformat())
            automatic = (
                "Returned the business date to the calendar"
                if held is None
                else f"Set the business date to {held.isoformat()}"
            )
        elif section in self.sections:
            if not isinstance(value, dict):
                raise RuleViolation(code="settings_not_object")
            patch = dict(value)
            if section == "localization" and "use_groupping" in patch:
                legacy = patch.pop("use_groupping")
                patch.setdefault("use_grouping", legacy)
            stored = self.sections[section]
            merged = _checked_section(section, {key: patch.get(key, stored[key]) for key in stored})
            row = section != "revenue" or self.revenue_row
            if row and merged == stored:
                return self._unchanged()
            before = self._section_snapshot(section) if row else "null"
            self.sections[section] = merged
            self.revenue_row = self.revenue_row or section == "revenue"
            after = self._section_snapshot(section)
            automatic = self._settings_reason(section, before, after)
        else:
            raise NotFound(code="not_found")
        final = (
            automatic
            if reason is None
            else f"{automatic}. Reason: {reason}" + ("" if reason[-1] in ".!?" else ".")
        )
        logged = "organization" if section == "revenue" else section
        version = self._record(command.context, logged, self.organization_id, before, after, final)
        return WriteResult(id=self.organization_id, version=version, outcome=WriteOutcome.UPDATED)

    async def save_logo(self, command: LogoSave) -> WriteResult:
        self._enter(command.context, "organization.manage")
        before = self._logo_snapshot(command.context.now)
        self.logo = command.logo
        version = self._record(
            command.context,
            "logo",
            self.organization_id,
            before,
            self._logo_snapshot(command.context.now),
            "Uploaded a new logo",
        )
        return WriteResult(id=self.organization_id, version=version, outcome=WriteOutcome.UPDATED)

    async def delete_logo(self, command: LogoRemoval) -> WriteResult:
        self._enter(command.context, "organization.manage")
        if self.logo is None:
            return self._unchanged()
        before = self._logo_snapshot(command.context.now)
        self.logo = None
        version = self._record(
            command.context, "logo", self.organization_id, before, "null", "Removed the logo"
        )
        return WriteResult(id=self.organization_id, version=version, outcome=WriteOutcome.UPDATED)

    async def appearance(self, context: TenantContext) -> Appearance:
        self._enter(context)
        effective = self._effective(context.actor_id)
        branding = effective.branding
        return Appearance(
            organization_name=self.name,
            settings_version=self.settings_version,
            business_date=self.business_date or context.now.date(),
            branding=AppearanceBranding(
                display_name=branding.display_name,
                logo_alt=branding.logo_alt,
                primary=branding.primary,
                secondary=branding.secondary,
                accent=branding.accent,
                logo=None if self.logo is None else self.logo.data_url,
            ),
            formats=effective.formats,
            theme_mode=effective.theme_mode,
            reduced_motion=effective.reduced_motion,
            font_scale=effective.font_scale,
            lockout_threshold=PIN_TRIES,
            lockout_minutes=effective.security_policy.lockout_minutes,
            idle_unlock_seconds=effective.security_policy.idle_unlock_seconds,
        )

    async def preferences(self, context: TenantContext) -> Preferences:
        self._enter(context)
        localization = self.sections["localization"]
        row = self._preference_row(context.actor_id)
        return Preferences(
            organization_id=self.organization_id,
            user_id=context.actor_id,
            locale=row.locale if localization["allow_locale_override"] else None,
            time_zone=row.time_zone if localization["allow_time_zone_override"] else None,
            hour12=row.hour12 if localization["allow_hour12_override"] else None,
            theme_mode=row.theme_mode if localization["allow_theme_override"] else None,
            reduced_motion=row.reduced_motion,
            font_scale=row.font_scale,
            allow_locale_override=localization["allow_locale_override"],
            allow_time_zone_override=localization["allow_time_zone_override"],
            allow_hour12_override=localization["allow_hour12_override"],
            allow_theme_override=localization["allow_theme_override"],
            organization=PreferenceDefaults(
                locale=localization["locale"],
                time_zone=localization["time_zone"],
                hour12=localization["hour12"],
            ),
        )

    async def save_preferences(self, command: PreferencesSave) -> UserPreferences:
        self._enter(command.context)
        c = command.choices
        if (c.theme_mode is not None and c.theme_mode not in ("light", "dark", "system")) or not (
            1 <= c.font_scale <= 3
        ):
            raise RuleViolation(code="preferences_accessibility")
        localization = self.sections["localization"]
        for given, flag, code in (
            (c.locale, "allow_locale_override", "preferences_locale_not_allowed"),
            (c.time_zone, "allow_time_zone_override", "preferences_time_zone_not_allowed"),
            (c.hour12, "allow_hour12_override", "preferences_hour12_not_allowed"),
            (c.theme_mode, "allow_theme_override", "preferences_theme_not_allowed"),
        ):
            if given is not None and not localization[flag]:
                raise RuleViolation(code=code)
        row = UserPreferences(
            organization_id=self.organization_id,
            user_id=command.context.actor_id,
            locale=c.locale,
            time_zone=c.time_zone,
            hour12=c.hour12,
            theme_mode=None if c.theme_mode is None else ThemeMode(c.theme_mode),
            reduced_motion=c.reduced_motion,
            font_scale=c.font_scale,
        )
        self.preference_rows[command.context.actor_id] = row
        return row

    # --- internals --------------------------------------------------------------------------

    def _enter(self, context: TenantContext, permission: str | None = None) -> FakeMember:
        member = self.members.get(context.actor_id)
        if context.organization_id != self.organization_id or member is None or not member.active:
            raise Forbidden(code="not_member")
        if permission is not None and permission not in member.held():
            raise Forbidden(code="permission_missing")
        return member

    def _today(self, context: TenantContext) -> date:
        zone = ZoneInfo(self.sections["localization"]["time_zone"])
        return self.business_date or context.now.astimezone(zone).date()

    def _sign_in_target(self, context: TenantContext, user_id: UUID, self_code: str) -> FakeMember:
        actor = self._enter(context, "people.sign_in")
        if user_id == context.actor_id:
            raise RuleViolation(code=self_code)
        member = self.members.get(user_id)
        if member is None:
            raise NotFound(code="not_found")
        if actor.role.lower() != "owner" and member.role.lower() == "owner":
            raise Forbidden(code="people_owner_edit")
        return member

    def _checked(self, details: PersonDetails, today: date, *, creating: bool) -> dict[str, Any]:
        first = (details.first_name or "").strip()
        last = (details.last_name or "").strip()
        if not first or not last or len(first) > 100 or len(last) > 100:
            raise RuleViolation(code="people_names_required")
        email = (details.email or "").strip().lower()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+", email) or len(email) > 320:
            raise RuleViolation(code="people_email_invalid")
        phone = PhoneNumber.parse(details.phone_number or "")
        if phone is None:
            raise RuleViolation(code="people_phone_invalid")
        if details.scope_mode not in ("all", "companies", "vehicles"):
            raise RuleViolation(code="people_scope_mode")
        if not details.permissions or len(set(details.permissions)) != len(details.permissions):
            raise RuleViolation(code="people_permissions_invalid")
        role = next((n for n in role_names() if n.lower() == (details.role or "").lower()), None)
        if role is None:
            raise RuleViolation(code="people_role_unknown")
        limit = details.back_limit
        mode = None if limit is None else limit.mode
        count = None if limit is None else limit.count
        since = None if limit is None else limit.from_date
        if mode is None:
            if count is not None or since is not None:
                raise RuleViolation(code="people_back_limit_invalid")
            if creating:
                mode, count = "days", 7
        elif (
            mode not in {m.value for m in BackLimitMode}
            or (mode == "none") != (count is None)
            or (mode == "days" and count is not None and not 0 <= count <= 3650)
            or (mode == "months" and count is not None and not 0 <= count <= 120)
        ):
            raise RuleViolation(code="people_back_limit_invalid")
        elif since is not None and since > today:
            raise RuleViolation(code="people_back_limit_date_future")
        if any(key not in _needs() for key in details.permissions):
            raise RuleViolation(code="people_permission_unknown")
        return {
            "first_name": first,
            "last_name": last,
            "email": email,
            "phone": phone.value,
            "role": role,
            "rights": expand_permissions(details.permissions),
            "scope_mode": details.scope_mode,
            "company_ids": tuple(details.company_ids) if details.scope_mode == "companies" else (),
            "vehicle_ids": tuple(details.vehicle_ids) if details.scope_mode == "vehicles" else (),
            "approval_limit": details.approval_limit,
            "back_limit_mode": mode,
            "back_limit_count": count,
            "back_limit_from": since,
        }

    def _person(self, member: FakeMember) -> Person:
        return Person(
            id=member.user_id,
            first_name=member.first_name,
            last_name=member.last_name,
            email=member.email,
            phone_number=member.phone,
            role=member.role,
            active=member.active,
            scope_mode=ScopeMode(member.scope_mode),
            company_ids=member.company_ids,
            vehicle_ids=member.vehicle_ids,
            permissions=member.rights,
            approval_limit=member.approval_limit,
            has_pin=member.has_pin,
            version=member.version,
            other_companies=0,
            other_vehicles=0,
            status=member.status,
            last_signed_in_at=member.last_signed_in_at,
            back_limit=BackLimit(
                mode=BackLimitMode(member.back_limit_mode),
                count=member.back_limit_count,
                from_date=member.back_limit_from,
            ),
            can_change=back_limit_words(
                member.back_limit_mode, member.back_limit_count, member.back_limit_from
            ),
            modules=tuple(
                ModuleAccess(name=name, held=held, total=total)
                for name, held, total in _modules(member.rights)
                if held
            ),
            everything=set(_needs()) <= set(member.rights),
            sign_in=None,
        )

    def _record(
        self,
        context: TenantContext,
        section: str,
        entity_id: UUID,
        before: str | None,
        after: str | None,
        reason: str,
    ) -> int:
        self.settings_version += 1
        actor = self.members.get(context.actor_id)
        self.log.append(
            HistoryEntry(
                version=self.settings_version,
                section=section,
                entity_id=entity_id,
                reason=reason,
                occurred_at=context.now,
                actor_id=context.actor_id,
                actor_name="" if actor is None else f"{actor.first_name} {actor.last_name}",
                before=before,
                after=after,
            )
        )
        return self.settings_version

    def _unchanged(self) -> WriteResult:
        return WriteResult(
            id=self.organization_id, version=self.settings_version, outcome=WriteOutcome.UNCHANGED
        )

    def _section_snapshot(self, section: str) -> str:
        values = {"organization_id": str(self.organization_id), **self.sections[section]}
        return _compact(
            {
                _camel(key): _number(value) if isinstance(value, Decimal) else value
                for key, value in values.items()
            }
        )

    def _settings_reason(self, section: str, before: str, after: str) -> str:
        old, new = json.loads(before), json.loads(after)
        if section == "revenue":
            old = self._as_money(old) if isinstance(old, dict) else old
            new = self._as_money(new)
        parts = [
            f"{_setting_word(key)} to {_setting_value(key, value)}"
            for key, value in new.items()
            if key != "organizationId" and (not isinstance(old, dict) or old.get(key) != value)
        ]
        return f"Changed {_join(parts)}" if parts else f"Changed the {section} settings"

    def _as_money(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        """A revenue snapshot as its reason shows it: the threshold as ``{CUR} {amount}``."""
        threshold = _formatted(Decimal(str(snapshot["lowDayThreshold"])))
        currency = self.sections["localization"]["currency"]
        return {**snapshot, "lowDayThreshold": f"{currency} {threshold}"}

    def _logo_snapshot(self, now: datetime) -> str:
        if self.logo is None:
            return "null"
        return _compact(
            {
                "contentType": self.logo.content_type,
                "bytes": len(self.logo.data),
                "updatedAt": now.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f+00:00"),
            }
        )

    def _localization(self) -> Localization:
        values = self.sections["localization"]
        return Localization(
            organization_id=self.organization_id,
            **{
                **values,
                "date_pattern": DatePattern(values["date_pattern"]),
                "week_numbering": WeekNumbering(values["week_numbering"]),
            },
        )

    def _branding(self) -> Branding:
        return Branding(organization_id=self.organization_id, **self.sections["branding"])

    def _policy(self) -> SecurityPolicy:
        return SecurityPolicy(
            organization_id=self.organization_id, **self.sections["securityPolicy"]
        )

    def _preference_row(self, user_id: UUID) -> UserPreferences:
        return self.preference_rows.get(user_id) or UserPreferences(
            organization_id=self.organization_id,
            user_id=user_id,
            locale=None,
            time_zone=None,
            hour12=None,
            theme_mode=None,
            reduced_motion=False,
            font_scale=1.0,
        )

    def _effective(self, user_id: UUID) -> EffectiveSettings:
        localization = self.sections["localization"]
        row = self._preference_row(user_id)
        locale = (
            row.locale
            if localization["allow_locale_override"] and row.locale
            else localization["locale"]
        )
        return EffectiveSettings(
            formats=EffectiveFormats(
                locale=locale,
                time_zone=row.time_zone
                if localization["allow_time_zone_override"] and row.time_zone
                else localization["time_zone"],
                date_pattern=DatePattern(localization["date_pattern"]),
                hour12=row.hour12
                if localization["allow_hour12_override"] and row.hour12 is not None
                else localization["hour12"],
                first_day_of_week=localization["first_day_of_week"],
                week_numbering=WeekNumbering(localization["week_numbering"]),
                currency=localization["currency"],
                use_grouping=localization["use_grouping"],
                number_decimals=localization["number_decimals"],
                direction="rtl"
                if locale.split("-")[0].lower() in ("ar", "fa", "he", "ur")
                else "ltr",
            ),
            branding=self._branding(),
            security_policy=self._policy(),
            theme_mode=(row.theme_mode or ThemeMode.SYSTEM)
            if localization["allow_theme_override"]
            else ThemeMode.LIGHT,
            reduced_motion=row.reduced_motion,
            font_scale=row.font_scale,
        )


# --- port doubles for the auth use-case tests ------------------------------------------------


class PinHasherSpy:
    """Delegates to a real ``PinHasher`` (a low-count ``Pbkdf2PinHasher``) and records each
    derivation in ``calls`` as ``pins.hash``, ``pins.verify`` or ``pins.dummy_verify``."""

    def __init__(self, inner: PinHasher, calls: list[str]) -> None:
        self._inner = inner
        self.calls = calls

    async def hash(self, pin: str) -> str:
        result = await self._inner.hash(pin)
        self.calls.append("pins.hash")
        return result

    async def verify(self, pin: str, stored: str) -> bool:
        result = await self._inner.verify(pin, stored)
        self.calls.append("pins.verify")
        return result

    async def dummy_verify(self, pin: str) -> bool:
        result = await self._inner.dummy_verify(pin)
        self.calls.append("pins.dummy_verify")
        return result

    @property
    def derivations(self) -> int:
        return sum(1 for call in self.calls if call.startswith("pins."))


class CodeMailerSpy:
    """Records ``mail.send_now`` and ``mail.send_later`` in ``calls``; ``send_now`` answers
    ``deliver`` (true unless a test sets it false). ``failure_callbacks`` keeps the
    ``on_failure`` of each queued mail so a test can run it as the queue would."""

    def __init__(self, calls: list[str]) -> None:
        self.calls = calls
        self.deliver = True
        self.mails: list[VerificationMail] = []
        self.failure_callbacks: list[Callable[[], Awaitable[None]]] = []

    async def send_now(self, mail: VerificationMail) -> bool:
        self.calls.append("mail.send_now")
        self.mails.append(mail)
        return self.deliver

    def send_later(
        self, mail: VerificationMail, *, on_failure: Callable[[], Awaitable[None]]
    ) -> None:
        self.calls.append("mail.send_later")
        self.mails.append(mail)
        self.failure_callbacks.append(on_failure)


class FixedSecrets:
    """A ``SecretSource`` whose code is fixed and whose refresh tokens are numbered, so a
    test knows what the service generated."""

    def __init__(self, code: str = "048213") -> None:
        self.code = code
        self._numbers: Iterator[int] = iter(range(1, 1_000_000))
        self.refresh_tokens: list[str] = []

    def verification_code(self) -> str:
        return self.code

    def refresh_token(self) -> str:
        token = f"refresh-token-{next(self._numbers)}"
        self.refresh_tokens.append(token)
        return token


# --- setup ---------------------------------------------------------------------------------

_REGISTRATION = re.compile(r"K[A-Z]{2}[0-9]{3}[A-Z]")
_MONEY_CAP = Decimal("999999999999.99")


def _number(amount: Decimal) -> int | float:
    """A snapshot amount: a JSON number with trailing zeros trimmed (``trim_scale``)."""
    normalised = amount.normalize()
    return int(normalised) if normalised == normalised.to_integral() else float(normalised)


def _money(amount: Decimal | None) -> Decimal:
    if amount is None or amount <= 0 or amount > _MONEY_CAP or round(amount, 2) != amount:
        raise RuleViolation(code="money_invalid")
    return amount


def _formatted(amount: Decimal) -> str:
    """``tenancy.fmt_money``: ``#,##0`` when whole, else ``#,##0.00``."""
    return f"{amount:,.0f}" if amount == amount.to_integral() else f"{amount:,.2f}"


def _typed_reason(reason: str | None) -> str | None:
    typed = (reason or "").strip()
    if len(typed) > 500:
        raise RuleViolation(code="reason_length")
    return typed or None


def _with_reason(automatic: str, typed: str | None) -> str:
    if typed is None:
        return automatic
    return f"{automatic}. Reason: {typed}" + ("" if typed[-1] in ".!?" else ".")


def _optional_iso(day: date | None) -> str | None:
    return None if day is None else day.isoformat()


@dataclass(slots=True)
class FakeCompany:
    id: UUID
    name: str
    archived_on: date | None = None


@dataclass(slots=True)
class FakeTargetSet:
    id: UUID
    starts_on: date
    days: tuple[Decimal, ...]


@dataclass(slots=True)
class FakeVehicle:
    """``sets`` are the target sets, one per start date."""

    id: UUID
    company_id: UUID
    registration: str
    joined_on: date
    fleet_number: str | None = None
    initial_investment: Decimal | None = None
    left_on: date | None = None
    sets: list[FakeTargetSet] = field(default_factory=list)
    away: list[AwayEntry] = field(default_factory=list)


@dataclass(slots=True)
class FakeVersion:
    id: UUID
    revision: int
    effective_from: date
    name: str
    kind: int
    amount: Decimal
    frequency: int
    day: int | None
    last_day: bool
    month: int | None
    start: date
    end: date | None
    expense_item_id: UUID | None
    bucket: int | None
    note: str | None
    shares: tuple[tuple[UUID, Decimal], ...]
    condition_min: Decimal | None = None
    condition_days: int | None = None


@dataclass(slots=True)
class FakeRecurring:
    id: UUID
    versions: list[FakeVersion] = field(default_factory=list)
    stopped_from: date | None = None
    pauses: list[tuple[date, date | None]] = field(default_factory=list)
    opened_on: date | None = None
    opening: dict[UUID, Decimal] = field(default_factory=dict)


@dataclass(slots=True)
class FakeCategory:
    id: UUID
    name: str
    bucket: int | None = None
    stopped_on: date | None = None
    main_category_id: UUID | None = None


@dataclass(slots=True)
class FakeMainCategory:
    id: UUID
    name: str


@dataclass(slots=True)
class FakeExpenseItem:
    id: UUID
    category_id: UUID
    name: str
    stopped_on: date | None = None


@dataclass(slots=True)
class FakeInvestment:
    id: UUID
    vehicle_id: UUID
    invested_on: date
    description: str
    amount: Decimal
    recorded_by: UUID
    recorded_at: datetime


class FakeSetupRepository:
    """In-memory ``SetupRepository`` over the organization of a ``FakeTenancyRepository``,
    whose members, settings version and change log it shares.

    ``tests/db/test_fakes_match_routines.py`` runs ``tests/support/setup_cases.py`` against
    this fake and the real routines: renaming a company, updating a vehicle with a target
    change, revising a scheduled item and deleting an investment entry, each with its refusals,
    unchanged saves, reasons, snapshots and the lists that show the result. Everything else
    answers as an all-companies caller with the permission would see it: no data scope, no
    revenue (so no revenue-dated refusal), and a vehicle report and investment ``returned``
    of zero, since the due days and the dated targets exist only in SQL."""

    def __init__(self, tenancy: FakeTenancyRepository | None = None) -> None:
        self.tenancy = tenancy or FakeTenancyRepository()
        self.companies: dict[UUID, FakeCompany] = {}
        self.vehicles: dict[UUID, FakeVehicle] = {}
        self.recurring: dict[UUID, FakeRecurring] = {}
        self.categories: dict[UUID, FakeCategory] = {}
        self.main_categories: dict[UUID, FakeMainCategory] = {}
        self.items: dict[UUID, FakeExpenseItem] = {}
        self.investments: dict[UUID, FakeInvestment] = {}

    # --- companies --------------------------------------------------------------------------

    async def list_companies(self, query: SetupPageQuery) -> CompanyPage:
        self._enter(query.context, "companies.view")
        _check_page(query.page, query.page_size)
        today = self._today(query.context)
        rows = sorted(self.companies.values(), key=lambda c: (c.name, str(c.id)))
        items = tuple(
            CompanySummary(
                id=c.id,
                name=c.name,
                vehicle_count=sum(
                    1
                    for v in self.vehicles.values()
                    if v.company_id == c.id and _in_fleet(v, today)
                ),
                active=_company_active(c, today),
                archived_on=c.archived_on,
            )
            for c in rows
        )
        return CompanyPage(items=_page(items, query.page, query.page_size), total=len(items))

    async def create_company(self, command: CompanySave) -> WriteResult:
        context = command.context
        self._enter(context, "companies.add")
        typed = _typed_reason(command.reason)
        name = _company_name(command.name)
        if self._company_taken(name, None):
            raise RuleViolation(code="company_name_taken")
        company = FakeCompany(id=uuid4(), name=name)
        self.companies[company.id] = company
        version = self._log(
            context,
            "companies",
            company.id,
            "null",
            self._company_snapshot(company),
            _with_reason(f"Added company {name}", typed),
        )
        return WriteResult(id=company.id, version=version, outcome=WriteOutcome.CREATED)

    async def rename_company(self, command: CompanySave) -> WriteResult:
        context = command.context
        self._enter(context, "companies.edit")
        typed = _typed_reason(command.reason)
        today = self._today(context)
        name = _company_name(command.name)
        company = self.companies.get(command.company_id) if command.company_id else None
        if company is None:
            raise NotFound(code="not_found")
        if company.archived_on is not None and company.archived_on <= today:
            raise RuleViolation(code="company_archived_rename")
        if self._company_taken(name, company.id):
            raise RuleViolation(code="company_name_taken")
        if name == company.name:
            return self._unchanged(company.id)
        before = self._company_snapshot(company)
        old, company.name = company.name, name
        version = self._log(
            context,
            "companies",
            company.id,
            before,
            self._company_snapshot(company),
            _with_reason(f"Renamed company {old} to {name}", typed),
        )
        return WriteResult(id=company.id, version=version, outcome=WriteOutcome.UPDATED)

    async def archive_company(self, command: CompanyLifecycle) -> WriteResult:
        context = command.context
        self._enter(context, "companies.edit")
        typed = _typed_reason(command.reason)
        today = self._today(context)
        company = self._company(command.company_id)
        if company.archived_on is None and any(
            v.company_id == company.id and (v.left_on is None or v.left_on > today)
            for v in self.vehicles.values()
        ):
            raise RuleViolation(code="company_has_vehicles")
        if company.archived_on == today:
            return self._unchanged(company.id)
        if company.archived_on is not None:
            raise RuleViolation(code="company_already_archived")
        before = self._company_snapshot(company)
        company.archived_on = today
        version = self._log(
            context,
            "companies",
            company.id,
            before,
            self._company_snapshot(company),
            _with_reason(f"Archived company {company.name}", typed),
        )
        return WriteResult(id=company.id, version=version, outcome=WriteOutcome.UPDATED)

    async def restore_company(self, command: CompanyLifecycle) -> WriteResult:
        context = command.context
        self._enter(context, "companies.edit")
        typed = _typed_reason(command.reason)
        company = self._company(command.company_id)
        if company.archived_on is None:
            return self._unchanged(company.id)
        before = self._company_snapshot(company)
        company.archived_on = None
        version = self._log(
            context,
            "companies",
            company.id,
            before,
            self._company_snapshot(company),
            _with_reason(f"Restored company {company.name}", typed),
        )
        return WriteResult(id=company.id, version=version, outcome=WriteOutcome.UPDATED)

    async def company_options(self, context: TenantContext) -> tuple[CompanyChoice, ...]:
        self._enter_any(context, "vehicles.add", "vehicles.edit")
        today = self._today(context)
        return tuple(
            CompanyChoice(id=c.id, name=c.name)
            for c in sorted(self.companies.values(), key=lambda c: (c.name, str(c.id)))
            if _company_active(c, today)
        )

    # --- vehicles ---------------------------------------------------------------------------

    async def list_vehicles(self, query: VehicleListQuery) -> VehiclePage:
        member = self._enter_any(query.context, "vehicles.view", "reports.investment")
        manages = "vehicles.view" in member.permissions
        _check_page(query.page, query.page_size)
        today = self._today(query.context)
        rows = sorted(
            (
                v
                for v in self.vehicles.values()
                if query.company_id is None or v.company_id == query.company_id
            ),
            key=lambda v: (v.registration, str(v.id)),
        )
        items = tuple(self._vehicle_summary(v, today, manages) for v in rows)
        return VehiclePage(items=_page(items, query.page, query.page_size), total=len(items))

    async def create_vehicle(self, command: VehicleSave) -> WriteResult:
        context, d = command.context, command.details
        self._enter(context, "vehicles.add")
        typed = _typed_reason(command.reason)
        registration = _registration(d.registration)
        fleet = _fleet_number(d.fleet_number)
        days = _day_targets(d.day_targets)
        investment = _investment_amount(d.initial_investment)
        today = self._today(context)
        joined_on = _joined(d.joined_on, today)
        company = self._share_company(d.company_id, today)
        if any(v.registration == registration for v in self.vehicles.values()):
            raise RuleViolation(code="vehicle_registration_taken")
        self._check_fleet(company.id, fleet, None)
        vehicle = FakeVehicle(
            id=uuid4(),
            company_id=company.id,
            registration=registration,
            joined_on=joined_on,
            fleet_number=fleet,
            initial_investment=investment,
            sets=[FakeTargetSet(id=uuid4(), starts_on=joined_on, days=days)],
        )
        self.vehicles[vehicle.id] = vehicle
        automatic = (
            f"Added vehicle {registration}, fleet number {fleet}, to {company.name} with a "
            f"weekly target of {self._currency()} {_formatted(sum(days, Decimal(0)))} from "
            f"{joined_on.isoformat()}"
        )
        version = self._log(
            context,
            "vehicles",
            vehicle.id,
            "null",
            self._vehicle_snapshot(vehicle),
            _with_reason(automatic, typed),
        )
        return WriteResult(id=vehicle.id, version=version, outcome=WriteOutcome.CREATED)

    async def update_vehicle(self, command: VehicleSave) -> WriteResult:
        context, d = command.context, command.details
        self._enter(context, "vehicles.edit")
        typed = _typed_reason(command.reason)
        registration = _registration(d.registration)
        fleet = _fleet_number(d.fleet_number)
        investment = _investment_amount(d.initial_investment)
        today = self._today(context)
        joined_on = _joined(d.joined_on, today)
        company = self._share_company(d.company_id, today)
        vehicle = self.vehicles.get(command.vehicle_id) if command.vehicle_id else None
        if vehicle is None:
            raise NotFound(code="not_found")
        if vehicle.left_on is not None:
            raise RuleViolation(code="vehicle_retired_edit")
        if registration != vehicle.registration:
            raise RuleViolation(code="vehicle_registration_change")
        self._check_fleet(company.id, fleet, vehicle.id)
        parts: list[str] = []
        if company.id != vehicle.company_id:
            parts.append(f"moved {registration} to {company.name}")
        if joined_on != vehicle.joined_on:
            parts.append(f"changed when {registration} joined the fleet to {joined_on.isoformat()}")
        if fleet != vehicle.fleet_number:
            parts.append(f"changed the fleet number of {registration} to {fleet}")
        if investment != vehicle.initial_investment:
            parts.append(
                f"cleared the initial investment of {registration}"
                if investment is None
                else f"changed the initial investment of {registration} to {self._currency()} "
                f"{_formatted(investment)}"
            )
        if not parts:
            return self._unchanged(vehicle.id)
        before = self._vehicle_snapshot(vehicle)
        first = min(vehicle.sets, key=lambda s: s.starts_on, default=None)
        if joined_on < vehicle.joined_on and first is not None and first.starts_on > joined_on:
            vehicle.sets.append(FakeTargetSet(id=uuid4(), starts_on=joined_on, days=first.days))
        vehicle.company_id, vehicle.joined_on = company.id, joined_on
        vehicle.fleet_number, vehicle.initial_investment = fleet, investment
        sentence = "; ".join(parts)
        version = self._log(
            context,
            "vehicles",
            vehicle.id,
            before,
            self._vehicle_snapshot(vehicle),
            _with_reason(sentence[:1].upper() + sentence[1:], typed),
        )
        return WriteResult(id=vehicle.id, version=version, outcome=WriteOutcome.UPDATED)

    async def retire_vehicle(self, command: VehicleRetirement) -> WriteResult:
        context = command.context
        self._enter(context, "vehicles.edit")
        typed = _typed_reason(command.reason)
        today = self._today(context)
        vehicle = self._vehicle(command.vehicle_id)
        left_on = command.left_on
        if left_on is None or left_on > today or left_on < vehicle.joined_on:
            raise RuleViolation(code="vehicle_leave_date_range")
        if vehicle.away and left_on < max(a.returned_on for a in vehicle.away):
            raise RuleViolation(code="vehicle_leave_before_return")
        if vehicle.left_on == left_on:
            return self._unchanged(vehicle.id)
        if vehicle.left_on is not None:
            raise RuleViolation(code="vehicle_already_retired")
        before = self._vehicle_snapshot(vehicle)
        vehicle.left_on = left_on
        version = self._log(
            context,
            "vehicles",
            vehicle.id,
            before,
            self._vehicle_snapshot(vehicle),
            _with_reason(
                f"Vehicle {vehicle.registration} left the fleet on {left_on.isoformat()}", typed
            ),
        )
        return WriteResult(id=vehicle.id, version=version, outcome=WriteOutcome.UPDATED)

    async def restore_vehicle(self, command: VehicleReturn) -> WriteResult:
        context = command.context
        self._enter(context, "vehicles.edit")
        typed = _typed_reason(command.reason)
        today = self._today(context)
        vehicle = self._vehicle(command.vehicle_id)
        if not _company_active(self.companies[vehicle.company_id], today):
            raise RuleViolation(code="vehicle_company_archived_restore")
        if vehicle.left_on is None:
            return self._unchanged(vehicle.id)
        returned_on = command.returned_on or today
        if returned_on < vehicle.left_on or returned_on > today:
            raise RuleViolation(code="vehicle_return_date_range")
        before = self._vehicle_snapshot(vehicle)
        automatic = (
            f"Vehicle {vehicle.registration} returned to the fleet on {returned_on.isoformat()}"
        )
        if returned_on > vehicle.left_on:
            vehicle.away.append(AwayEntry(left_on=vehicle.left_on, returned_on=returned_on))
            vehicle.away.sort(key=lambda a: a.left_on)
            last_day = returned_on - timedelta(days=1)
            automatic += (
                f"; it was away from {vehicle.left_on.isoformat()} to {last_day.isoformat()}"
            )
        vehicle.left_on = None
        version = self._log(
            context,
            "vehicles",
            vehicle.id,
            before,
            self._vehicle_snapshot(vehicle),
            _with_reason(automatic, typed),
        )
        return WriteResult(id=vehicle.id, version=version, outcome=WriteOutcome.UPDATED)

    async def vehicle_report(self, query: VehicleReportQuery) -> VehicleReport:
        self._enter(query.context, "vehicles.view")
        today = self._today(query.context)
        period = (query.period or "").strip()
        if period:
            if period == "week":
                first_day = self.tenancy.sections["localization"]["first_day_of_week"]
                first = today - timedelta(days=((today.isoweekday() % 7) - first_day + 7) % 7)
            elif period == "month":
                first = today.replace(day=1)
            else:
                raise RuleViolation(code="report_period_invalid")
            last = today
        else:
            if query.from_date is None or query.through is None:
                raise RuleViolation(code="report_range_required")
            first, last = query.from_date, query.through
            if last < first or (last - first).days > 366 or last > today:
                raise RuleViolation(code="report_range_invalid")
        self._vehicle(query.vehicle_id)
        zero = Decimal(0)
        return VehicleReport(
            vehicle_id=query.vehicle_id,
            from_date=first,
            through=last,
            money_in=zero,
            target=zero,
            repairs=zero,
            charges=zero,
            loans=zero,
            money_out=zero,
            net=zero,
            savings=zero,
            after_savings=zero,
            costs=zero,
            postings=(),
        )

    async def list_target_sets(self, query: VehicleQuery) -> tuple[TargetSetSummary, ...]:
        member = self._enter(query.context, "vehicles.view")
        today = self._today(query.context)
        vehicle = self._vehicle(query.vehicle_id)
        in_force = _set_on(vehicle, today)
        can_remove = "vehicles.target" in member.permissions
        return tuple(
            TargetSetSummary(
                id=s.id,
                starts_on=s.starts_on,
                days=s.days,
                week_total=sum(s.days, Decimal(0)),
                in_force=in_force is not None and s.id == in_force.id,
                can_remove=can_remove and s.starts_on > today,
            )
            for s in sorted(vehicle.sets, key=lambda s: s.starts_on, reverse=True)
        )

    async def save_target_set(self, command: TargetSetSave) -> WriteResult:
        context = command.context
        self._enter(context, "vehicles.target")
        if command.starts_on is None:
            raise RuleViolation(code="target_start_required")
        days = _day_targets(command.days)
        today = self._today(context)
        vehicle = self._vehicle(command.vehicle_id)
        if vehicle.left_on is not None:
            raise RuleViolation(code="vehicle_retired_edit")
        starts_on = command.starts_on
        if starts_on < today:
            raise RuleViolation(code="target_start_past")
        current = _set_on(vehicle, starts_on)
        if current is not None and current.days == days:
            raise RuleViolation(code="target_set_unchanged", detail={"date": starts_on.isoformat()})
        before = self._vehicle_snapshot(vehicle)
        existing = next((s for s in vehicle.sets if s.starts_on == starts_on), None)
        if existing is None:
            existing = FakeTargetSet(id=uuid4(), starts_on=starts_on, days=days)
            vehicle.sets.append(existing)
            outcome = WriteOutcome.CREATED
        else:
            existing.days = days
            outcome = WriteOutcome.UPDATED
        version = self._log(
            context,
            "vehicles",
            vehicle.id,
            before,
            self._vehicle_snapshot(vehicle),
            f"Target set, {vehicle.registration}",
        )
        return WriteResult(id=existing.id, version=version, outcome=outcome)

    async def remove_target_set(self, command: TargetSetRemoval) -> WriteResult:
        context = command.context
        self._enter(context, "vehicles.target")
        today = self._today(context)
        found = next(
            ((v, s) for v in self.vehicles.values() for s in v.sets if s.id == command.set_id),
            None,
        )
        if found is None:
            raise NotFound(code="not_found")
        vehicle, target_set = found
        if target_set.starts_on <= today:
            raise RuleViolation(code="target_set_started")
        before = self._vehicle_snapshot(vehicle)
        vehicle.sets.remove(target_set)
        version = self._log(
            context,
            "vehicles",
            vehicle.id,
            before,
            self._vehicle_snapshot(vehicle),
            f"Target removed before it started, {vehicle.registration}",
        )
        return WriteResult(id=target_set.id, version=version, outcome=WriteOutcome.UPDATED)

    # --- scheduled items --------------------------------------------------------------------

    async def list_recurring(self, query: RecurringListQuery) -> RecurringPage:
        kind = _filter_choice(
            query.kind, {"cost": 1, "savings": 2}, "recurring_filter_kind_invalid"
        )
        running = _filter_choice(
            query.status, {"running": True, "stopped": False}, "recurring_filter_status_invalid"
        )
        member = self._enter_any(query.context, "scheduled.view", "savings.view")
        _check_page(query.page, query.page_size)
        today = self._today(query.context)
        matching = [
            (self._running(r, today), r)
            for r in self.recurring.values()
            if (kind is None or r.versions[-1].kind == kind)
            and _kind_right(r.versions[-1].kind, "view") in member.permissions
            and (
                query.company_id is None
                or any(
                    self.vehicles[v].company_id == query.company_id
                    for v, _ in r.versions[-1].shares
                )
            )
        ]
        rows = sorted(
            ((runs, r) for runs, r in matching if running is None or runs == running),
            key=lambda row: (not row[0], row[1].versions[-1].name, str(row[1].id)),
        )
        items = tuple(self._recurring_summary(r, today) for _, r in rows)
        return RecurringPage(items=_page(items, query.page, query.page_size), total=len(items))

    def _running(self, item: FakeRecurring, today: date) -> bool:
        current = item.versions[-1]
        return (
            (item.stopped_from is None or item.stopped_from > today)
            and (current.end is None or current.end >= today)
            and any(_in_fleet(self.vehicles[v], today) for v, _ in current.shares)
        )

    async def vehicle_options(self, context: TenantContext) -> tuple[ShareVehicle, ...]:
        self._enter_any(context, "scheduled.add", "scheduled.edit", "savings.add", "savings.edit")
        today = self._today(context)
        return tuple(
            ShareVehicle(
                id=v.id,
                company_id=v.company_id,
                company_name=self.companies[v.company_id].name,
                registration=v.registration,
                active=True,
                fleet_number=v.fleet_number,
            )
            for v in sorted(self.vehicles.values(), key=lambda v: (v.registration, str(v.id)))
            if v.joined_on <= today
            and v.left_on is None
            and _company_active(self.companies[v.company_id], today)
        )

    async def create_recurring(self, command: RecurringSave) -> WriteResult:
        member = self._enter_any(command.context, "scheduled.add", "savings.add")
        kind = command.definition.kind
        if kind in (1, 2) and _kind_right(kind, "add") not in member.permissions:
            raise Forbidden(code="permission_missing")
        return self._save_recurring(command, None)

    async def revise_recurring(self, command: RecurringSave) -> WriteResult:
        self._enter_any(command.context, "scheduled.edit", "savings.edit")
        if command.item_id is None:
            raise NotFound(code="not_found")
        return self._save_recurring(command, command.item_id)

    async def stop_recurring(self, command: RecurringStop) -> WriteResult:
        context = command.context
        member = self._enter_any(context, "scheduled.edit", "savings.edit")
        typed = (command.reason or "").strip()
        if not 1 <= len(typed) <= 500:
            raise RuleViolation(code="reason_length")
        if command.confirmed is not True:
            raise RuleViolation(code="recurring_stop_confirm")
        today = self._today(context)
        item = self._kind_item(command.item_id, member)
        if item.stopped_from == today:
            return self._unchanged(item.id)
        if item.stopped_from is not None and item.stopped_from > today:
            raise RuleViolation(code="recurring_stop_later_pending")
        if item.stopped_from is not None:
            raise RuleViolation(code="recurring_already_stopped")
        before = self._recurring_snapshot(item)
        item.stopped_from = today
        automatic = _recurring_reason(item.versions[-1].kind, item.versions[-1].name)
        version = self._log(
            context,
            "recurring",
            item.id,
            before,
            self._recurring_snapshot(item),
            _with_reason(automatic, typed),
        )
        return WriteResult(id=item.id, version=version, outcome=WriteOutcome.UPDATED)

    async def cancel_recurring_stop(self, command: RecurringCancelStop) -> WriteResult:
        context = command.context
        member = self._enter_any(context, "scheduled.edit", "savings.edit")
        today = self._today(context)
        item = self._kind_item(command.item_id, member)
        if item.stopped_from is None:
            return self._unchanged(item.id)
        if item.stopped_from <= today:
            raise RuleViolation(code="recurring_stop_in_effect")
        before = self._recurring_snapshot(item)
        item.stopped_from = None
        version = self._log(
            context,
            "recurring",
            item.id,
            before,
            self._recurring_snapshot(item),
            _recurring_reason(item.versions[-1].kind, item.versions[-1].name),
        )
        return WriteResult(id=item.id, version=version, outcome=WriteOutcome.UPDATED)

    async def pause_recurring(self, command: RecurringPause) -> WriteResult:
        return self._toggle_pause(command, pause=True)

    async def resume_recurring(self, command: RecurringPause) -> WriteResult:
        return self._toggle_pause(command, pause=False)

    def _toggle_pause(self, command: RecurringPause, *, pause: bool) -> WriteResult:
        context = command.context
        member = self._enter_any(context, "scheduled.pause", "savings.pause")
        today = self._today(context)
        item = self._recurring(command.item_id)
        current = item.versions[-1]
        if _kind_right(current.kind, "view") not in member.permissions:
            raise NotFound(code="not_found")
        if _kind_right(current.kind, "pause") not in member.permissions:
            raise Forbidden(code="permission_missing")
        stopped = item.stopped_from is not None and item.stopped_from <= today
        open_at = next((i for i, (_, through) in enumerate(item.pauses) if through is None), None)
        if pause and stopped:
            raise RuleViolation(code="recurring_already_stopped")
        if (open_at is not None) == pause:
            return self._unchanged(item.id)
        if stopped:
            raise RuleViolation(code="recurring_already_stopped")
        before = self._recurring_snapshot(item)
        if pause:
            item.pauses.append((today, None))
        else:
            assert open_at is not None
            start = item.pauses[open_at][0]
            item.pauses[open_at] = (start, max(today, start) - timedelta(days=1))
        version = self._log(
            context,
            "recurring",
            item.id,
            before,
            self._recurring_snapshot(item),
            _recurring_reason(current.kind, current.name),
        )
        return WriteResult(id=item.id, version=version, outcome=WriteOutcome.UPDATED)

    async def recurring_runs(self, query: RecurringRunsQuery) -> RecurringRuns:
        """The routine's runs; a held share's revenue is 0 here, as this fake keeps no revenue
        records, and no run is ever decided."""
        member = self._enter_any(query.context, "scheduled.view", "savings.view")
        today = self._today(query.context)
        item = self._recurring(query.item_id)
        current = item.versions[-1]
        if _kind_right(current.kind, "view") not in member.permissions:
            raise NotFound(code="not_found")
        start = min(v.start for v in item.versions)
        runs = self._item_runs(item, start, today, today)
        dates = sorted({day for day, _, _ in runs}, reverse=True)

        def posted(day: date) -> Decimal:
            return sum(
                (a for d, _, (a, s) in runs if d == day and s in (RunState.POSTED, RunState.SAVED)),
                Decimal(0),
            )

        return RecurringRuns(
            id=item.id,
            name=current.name,
            kind=RecurringKind(current.kind),
            start=start,
            total=sum((posted(d) for d in dates), Decimal(0)),
            run_count=len(dates),
            runs=tuple(
                RecurringRun(
                    date=day,
                    amount=posted(day),
                    shares=tuple(
                        RecurringRunShare(
                            vehicle_id=vehicle_id,
                            registration=self.vehicles[vehicle_id].registration,
                            amount=amount,
                            state=state,
                            revenue=Decimal(0) if state is RunState.HELD else None,
                        )
                        for d, vehicle_id, (amount, state) in sorted(
                            runs, key=lambda r: (self.vehicles[r[1]].registration, str(r[1]))
                        )
                        if d == day
                    ),
                )
                for day in dates[:10]
            ),
        )

    async def recurring_month(self, context: TenantContext) -> RecurringMonth:
        member = self._enter_any(context, "scheduled.view", "savings.view")
        today = self._today(context)
        first = today.replace(day=1)
        last = (first + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        costs = "scheduled.view" in member.permissions
        savings = "savings.view" in member.permissions
        counts = {(kind, paused): 0 for kind in (1, 2) for paused in (False, True)}
        costs_due = saved = balance = Decimal(0)
        for item in self.recurring.values():
            current = item.versions[-1]
            if _kind_right(current.kind, "view") not in member.permissions:
                continue
            live = (item.stopped_from is None or item.stopped_from > today) and (
                current.end is None or current.end >= today
            )
            if live:
                counts[(current.kind, any(t is None for _, t in item.pauses))] += 1
            if current.kind == 2:
                balance += self._saving_balance(item, today)
            for day, _, (amount, state) in self._item_runs(item, first, last, last):
                if state is RunState.POSTED:
                    costs_due += amount
                elif state is RunState.SAVED and day <= today:
                    saved += amount
        return RecurringMonth(
            from_date=first,
            to_date=last,
            costs_due=costs_due if costs else None,
            saved=saved if savings else None,
            savings_balance=balance if savings else None,
            running_costs=counts[(1, False)] if costs else None,
            paused_costs=counts[(1, True)] if costs else None,
            running_savings=counts[(2, False)] if savings else None,
            paused_savings=counts[(2, True)] if savings else None,
        )

    def _item_runs(
        self, item: FakeRecurring, first: date, last: date, today: date
    ) -> list[tuple[date, UUID, tuple[Decimal, RunState]]]:
        """``setup.scheduled_runs`` of one item: (day, vehicle, (amount, state))."""
        runs = []
        for index, version in enumerate(item.versions):
            state = (
                RunState.POSTED
                if version.kind == 1
                else RunState.SAVED
                if version.condition_min is None
                else RunState.HELD
            )
            for vehicle_id, amount in version.shares:
                vehicle = self.vehicles[vehicle_id]
                end = min(last, today)
                if vehicle.left_on is not None and vehicle.left_on <= end:
                    end = vehicle.left_on - timedelta(days=1)
                for day in _version_days(item, index, max(first, vehicle.joined_on), end):
                    runs.append((day, vehicle_id, (amount, state)))
        return runs

    def _saving_balance(self, item: FakeRecurring, today: date) -> Decimal:
        opening = Decimal(0)
        start = min(v.start for v in item.versions)
        if item.opened_on is not None:
            start = max(start, item.opened_on + timedelta(days=1))
            if item.opened_on <= today:
                opening = sum(item.opening.values(), Decimal(0))
        return opening + sum(
            (
                amount
                for _, _, (amount, state) in self._item_runs(item, start, today, today)
                if state is RunState.SAVED
            ),
            Decimal(0),
        )

    # --- expense catalogue ------------------------------------------------------------------

    async def list_expense_categories(self, query: SetupPageQuery) -> ExpenseCategoryPage:
        self._enter_any(query.context, "catalog.view", "expenses.view", "scheduled.view")
        _check_page(query.page, query.page_size)
        today = self._today(query.context)
        rows = sorted(self.categories.values(), key=lambda c: (c.name, str(c.id)))
        items = tuple(
            ExpenseCategorySummary(
                id=c.id,
                name=c.name,
                bucket=None if c.bucket is None else ExpenseBucket(c.bucket),
                active=_in_use(c.stopped_on, today),
                stopped_on=c.stopped_on,
                items=tuple(
                    ExpenseItemSummary(
                        id=i.id,
                        category_id=c.id,
                        name=i.name,
                        active=_in_use(i.stopped_on, today),
                        stopped_on=i.stopped_on,
                    )
                    for i in sorted(self.items.values(), key=lambda i: (i.name, str(i.id)))
                    if i.category_id == c.id
                ),
                main_category_id=c.main_category_id,
                main_category_name=self._main_name(c.main_category_id),
            )
            for c in rows
        )
        return ExpenseCategoryPage(
            items=_page(items, query.page, query.page_size), total=len(items)
        )

    async def expense_item_options(self, context: TenantContext) -> tuple[ExpenseItemChoice, ...]:
        self._enter_any(
            context,
            "catalog.view",
            "expenses.view",
            "expenses.capture",
            "scheduled.view",
            "scheduled.add",
            "scheduled.edit",
            "pettycash.spend",
        )
        today = self._today(context)
        choices = [
            (self.categories[i.category_id], i)
            for i in self.items.values()
            if _in_use(i.stopped_on, today)
            and _in_use(self.categories[i.category_id].stopped_on, today)
        ]
        choices.sort(key=lambda pair: (pair[0].name, pair[1].name, str(pair[1].id)))
        return tuple(
            ExpenseItemChoice(
                id=i.id,
                name=i.name,
                category_id=c.id,
                category_name=c.name,
                bucket=None if c.bucket is None else ExpenseBucket(c.bucket),
                main_category_id=c.main_category_id,
                main_category_name=self._main_name(c.main_category_id),
            )
            for c, i in choices
        )

    async def create_expense_category(self, command: ExpenseCategorySave) -> WriteResult:
        context = command.context
        self._enter(context, "catalog.add")
        name = _catalogue_name(command.name)
        main = self._main(command.main_category_id)
        if any(c.name.upper() == name.upper() for c in self.categories.values()):
            raise RuleViolation(code="expense_category_taken")
        category = FakeCategory(
            id=uuid4(), name=name, main_category_id=None if main is None else main.id
        )
        self.categories[category.id] = category
        version = self._log(
            context,
            "expenses",
            category.id,
            "null",
            self._category_snapshot(category),
            f"Added expense category {name}" + ("" if main is None else f" under {main.name}"),
        )
        return WriteResult(id=category.id, version=version, outcome=WriteOutcome.CREATED)

    async def update_expense_category(self, command: ExpenseCategorySave) -> WriteResult:
        context = command.context
        self._enter(context, "catalog.edit")
        name = _catalogue_name(command.name)
        category = self.categories.get(command.category_id) if command.category_id else None
        if category is None:
            raise NotFound(code="not_found")
        main_id = (
            command.main_category_id if command.main_category_given else category.main_category_id
        )
        main = self._main(main_id)
        if any(
            c.name.upper() == name.upper() and c is not category for c in self.categories.values()
        ):
            raise RuleViolation(code="expense_category_taken")
        parts = []
        if name != category.name:
            parts.append(f"Renamed expense category {category.name} to {name}")
        if main_id != category.main_category_id:
            where = "no main category" if main is None else f"main category {main.name}"
            parts.append(
                f"moved to {where}" if parts else f"Moved expense category {name} to {where}"
            )
        if not parts:
            return self._unchanged(category.id)
        automatic = ", ".join(parts)
        before = self._category_snapshot(category)
        category.name, category.main_category_id = name, main_id
        version = self._log(
            context, "expenses", category.id, before, self._category_snapshot(category), automatic
        )
        return WriteResult(id=category.id, version=version, outcome=WriteOutcome.UPDATED)

    async def set_expense_category_stopped(self, command: ExpenseLifecycle) -> WriteResult:
        self._enter(command.context, "catalog.stop")
        category = self.categories.get(command.id)
        if category is None:
            raise NotFound(code="not_found")
        return self._set_stopped(command, category, "expense category", self._category_snapshot)

    async def create_expense_item(self, command: ExpenseItemCreate) -> WriteResult:
        context = command.context
        self._enter(context, "catalog.add")
        category = self.categories.get(command.category_id)
        if category is None:
            raise NotFound(code="not_found")
        name = _catalogue_name(command.name)
        if self._item_taken(category.id, name, None):
            raise RuleViolation(code="expense_item_taken")
        item = FakeExpenseItem(id=uuid4(), category_id=category.id, name=name)
        self.items[item.id] = item
        version = self._log(
            context,
            "expenses",
            item.id,
            "null",
            self._item_snapshot(item),
            f"Added expense item {name} under {category.name}",
        )
        return WriteResult(id=item.id, version=version, outcome=WriteOutcome.CREATED)

    async def rename_expense_item(self, command: ExpenseItemRename) -> WriteResult:
        context = command.context
        self._enter(context, "catalog.edit")
        name = _catalogue_name(command.name)
        item = self.items.get(command.item_id)
        if item is None:
            raise NotFound(code="not_found")
        if self._item_taken(item.category_id, name, item.id):
            raise RuleViolation(code="expense_item_taken")
        if name == item.name:
            return self._unchanged(item.id)
        before = self._item_snapshot(item)
        old, item.name = item.name, name
        version = self._log(
            context,
            "expenses",
            item.id,
            before,
            self._item_snapshot(item),
            f"Renamed expense item {old} to {name}",
        )
        return WriteResult(id=item.id, version=version, outcome=WriteOutcome.UPDATED)

    async def set_expense_item_stopped(self, command: ExpenseLifecycle) -> WriteResult:
        self._enter(command.context, "catalog.stop")
        item = self.items.get(command.id)
        if item is None:
            raise NotFound(code="not_found")
        return self._set_stopped(command, item, "expense item", self._item_snapshot)

    async def list_expense_main_categories(self, query: SetupPageQuery) -> MainCategoryPage:
        self._enter_any(query.context, "catalog.view", "expenses.view", "scheduled.view")
        _check_page(query.page, query.page_size)
        rows = sorted(self.main_categories.values(), key=lambda m: (m.name, str(m.id)))
        items = tuple(
            MainCategorySummary(
                id=m.id,
                name=m.name,
                category_count=sum(
                    1 for c in self.categories.values() if c.main_category_id == m.id
                ),
                item_count=sum(
                    1
                    for i in self.items.values()
                    if self.categories[i.category_id].main_category_id == m.id
                ),
            )
            for m in rows
        )
        return MainCategoryPage(
            items=_page(items, query.page, query.page_size),
            total=len(items),
            categories_without_main=sum(
                1 for c in self.categories.values() if c.main_category_id is None
            ),
        )

    async def create_expense_main_category(self, command: MainCategorySave) -> WriteResult:
        context = command.context
        self._enter(context, "catalog.add")
        name = _catalogue_name(command.name)
        if self._main_taken(name, None):
            raise RuleViolation(code="expense_main_taken")
        main = FakeMainCategory(id=uuid4(), name=name)
        self.main_categories[main.id] = main
        version = self._log(
            context,
            "expenses",
            main.id,
            "null",
            self._main_snapshot(main),
            f"Added main category {name}",
        )
        return WriteResult(id=main.id, version=version, outcome=WriteOutcome.CREATED)

    async def rename_expense_main_category(self, command: MainCategorySave) -> WriteResult:
        context = command.context
        self._enter(context, "catalog.edit")
        name = _catalogue_name(command.name)
        main = (
            self.main_categories.get(command.main_category_id) if command.main_category_id else None
        )
        if main is None:
            raise NotFound(code="not_found")
        if self._main_taken(name, main.id):
            raise RuleViolation(code="expense_main_taken")
        if name == main.name:
            return self._unchanged(main.id)
        before = self._main_snapshot(main)
        old, main.name = main.name, name
        version = self._log(
            context,
            "expenses",
            main.id,
            before,
            self._main_snapshot(main),
            f"Renamed main category {old} to {name}",
        )
        return WriteResult(id=main.id, version=version, outcome=WriteOutcome.UPDATED)

    # --- investment -------------------------------------------------------------------------

    async def get_investment(self, query: VehicleQuery) -> InvestmentSummary:
        self._enter(query.context, "reports.investment")
        self._vehicle(query.vehicle_id)
        entries = sorted(
            (e for e in self.investments.values() if e.vehicle_id == query.vehicle_id),
            key=lambda e: (e.invested_on, e.recorded_at, str(e.id)),
        )
        total = sum((e.amount for e in entries), Decimal(0))
        returned = Decimal(0)
        percent = None
        if total:
            percent = (returned / total * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP)
        return InvestmentSummary(
            vehicle_id=query.vehicle_id,
            total_invested=total,
            returned=returned,
            percent_paid_off=percent,
            entries=tuple(
                InvestmentEntry(
                    id=e.id,
                    invested_on=e.invested_on,
                    description=e.description,
                    amount=e.amount,
                    recorded_by=self._member_name(e.recorded_by),
                    recorded_at=e.recorded_at,
                )
                for e in entries
            ),
        )

    async def create_investment(self, command: InvestmentCreate) -> WriteResult:
        context = command.context
        self._enter(context, "vehicles.edit")
        vehicle = self._vehicle(command.vehicle_id)
        invested_on, description, amount = self._investment(command.details, context)
        entry = FakeInvestment(
            id=uuid4(),
            vehicle_id=vehicle.id,
            invested_on=invested_on,
            description=description,
            amount=amount,
            recorded_by=context.actor_id,
            recorded_at=context.now,
        )
        self.investments[entry.id] = entry
        version = self._log(
            context,
            "investment",
            vehicle.id,
            "null",
            self._investment_snapshot(entry),
            f"Recorded investment {description} on {vehicle.registration}",
        )
        return WriteResult(id=entry.id, version=version, outcome=WriteOutcome.CREATED)

    async def update_investment(self, command: InvestmentUpdate) -> WriteResult:
        context = command.context
        self._enter(context, "vehicles.edit")
        entry = self.investments.get(command.entry_id)
        if entry is None:
            raise NotFound(code="not_found")
        invested_on, description, amount = self._investment(command.details, context)
        if (entry.invested_on, entry.description, entry.amount) == (
            invested_on,
            description,
            amount,
        ):
            return self._unchanged(entry.id)
        before = self._investment_snapshot(entry)
        entry.invested_on, entry.description, entry.amount = invested_on, description, amount
        vehicle = self.vehicles[entry.vehicle_id]
        version = self._log(
            context,
            "investment",
            vehicle.id,
            before,
            self._investment_snapshot(entry),
            f"Changed investment {description} on {vehicle.registration}",
        )
        return WriteResult(id=entry.id, version=version, outcome=WriteOutcome.UPDATED)

    async def delete_investment(self, command: InvestmentRemoval) -> WriteResult:
        context = command.context
        self._enter(context, "vehicles.edit")
        entry = self.investments.pop(command.entry_id, None)
        if entry is None:
            raise NotFound(code="not_found")
        vehicle = self.vehicles[entry.vehicle_id]
        version = self._log(
            context,
            "investment",
            vehicle.id,
            self._investment_snapshot(entry),
            "null",
            f"Removed investment {entry.description} on {vehicle.registration}",
        )
        return WriteResult(id=entry.id, version=version, outcome=WriteOutcome.UPDATED)

    # --- the scheduled item save ------------------------------------------------------------

    def _save_recurring(self, command: RecurringSave, item_id: UUID | None) -> WriteResult:
        context, d = command.context, command.definition
        member = self._enter(context)
        typed = _typed_reason(command.reason)
        today = self._today(context)
        name, bucket = self._named(d, today)
        if not _schedule_valid(d.frequency, d.day, d.last_day, d.month):
            raise RuleViolation(code="recurring_schedule_shape")
        if item_id is None:
            item = FakeRecurring(id=uuid4())
        else:
            item = self._kind_item(item_id, member)
        current = item.versions[-1] if item.versions else None
        start = (current.start if current is not None else today) if d.kind == 2 else d.start
        amount, note, shares = _checked_definition(d, name, start)
        if current is not None and _kind_right(d.kind, "edit") not in member.permissions:
            raise Forbidden(code="permission_missing")
        start = _new_save_start(d, start, current, today)
        self._check_shares(shares, current, today)
        condition, opening = _checked_saving(d, item, current, shares, today)
        if current is None:
            before = "null"
            effective, revision = start, 1
            automatic = _recurring_reason(d.kind, name)
            outcome = WriteOutcome.CREATED
        else:
            parts = _recurring_changes(current, d, name, bucket, amount, start, note, shares)
            if (current.condition_min, current.condition_days) != condition:
                parts.append("revenue rule")
            if opening is not None and opening != (item.opened_on, item.opening):
                parts.append("opening balance")
            if not parts:
                return self._unchanged(item.id)
            if item.stopped_from is not None and item.stopped_from <= today:
                raise RuleViolation(code="recurring_stopped_edit")
            if current.start < today and start != current.start:
                raise RuleViolation(code="recurring_running_start_change")
            before = self._recurring_snapshot(item)
            effective = today if current.start < today or start >= today else start
            revision = current.revision + 1
            automatic = _recurring_reason(d.kind, name)
            outcome = WriteOutcome.UPDATED
        item.versions.append(
            FakeVersion(
                id=uuid4(),
                revision=revision,
                effective_from=effective,
                name=name,
                kind=d.kind,
                amount=amount,
                frequency=d.frequency,
                day=d.day,
                last_day=d.last_day,
                month=d.month,
                start=start,
                end=d.end,
                expense_item_id=d.expense_item_id,
                bucket=bucket,
                note=note,
                shares=shares,
                condition_min=condition[0],
                condition_days=condition[1],
            )
        )
        if opening is not None:
            item.opened_on, item.opening = opening
        self.recurring[item.id] = item
        version = self._log(
            context,
            "recurring",
            item.id,
            before,
            self._recurring_snapshot(item),
            _with_reason(automatic, typed),
        )
        return WriteResult(id=item.id, version=version, outcome=outcome)

    def _named(self, d: RecurringDefinition, today: date) -> tuple[str, int | None]:
        """The saved name and bucket: a cost takes both from its expense item in use."""
        if d.kind != 1:
            if d.expense_item_id is not None:
                raise RuleViolation(code="recurring_savings_item")
            return (d.name or "").strip(), None
        if d.expense_item_id is None:
            return (d.name or "").strip(), None
        expense = self.items.get(d.expense_item_id)
        category = None if expense is None else self.categories[expense.category_id]
        if (
            expense is None
            or category is None
            or not _in_use(expense.stopped_on, today)
            or not _in_use(category.stopped_on, today)
        ):
            raise RuleViolation(code="recurring_item_not_in_use")
        return expense.name, category.bucket

    def _check_shares(
        self,
        shares: tuple[tuple[UUID, Decimal], ...],
        current: FakeVersion | None,
        today: date,
    ) -> None:
        """The first share whose vehicle is unknown, or (new to the item) out of the fleet or in
        a company not in use, decides the refusal."""
        on_item = {v for v, _ in current.shares} if current else set()
        for vehicle_id, _ in shares:
            vehicle = self.vehicles.get(vehicle_id)
            if vehicle is None:
                raise NotFound(code="not_found")
            company = self.companies[vehicle.company_id]
            if vehicle_id not in on_item and (
                not _in_fleet(vehicle, today) or not _company_active(company, today)
            ):
                raise RuleViolation(code="recurring_share_inactive")

    # --- shared -----------------------------------------------------------------------------

    def _enter(self, context: TenantContext, permission: str | None = None) -> FakeMember:
        return self.tenancy._enter(context, permission)

    def _enter_any(self, context: TenantContext, *permissions: str) -> FakeMember:
        member = self._enter(context)
        if not any(p in member.permissions for p in permissions):
            raise Forbidden(code="permission_missing")
        return member

    def _today(self, context: TenantContext) -> date:
        return self.tenancy.business_date or context.now.date()

    def _currency(self) -> str:
        return str(self.tenancy.sections["localization"]["currency"])

    def _member_name(self, user_id: UUID) -> str:
        member = self.tenancy.members.get(user_id)
        return "" if member is None else f"{member.first_name} {member.last_name}"

    def _log(
        self,
        context: TenantContext,
        section: str,
        entity_id: UUID,
        before: str,
        after: str,
        reason: str,
    ) -> int:
        return self.tenancy._record(context, section, entity_id, before, after, reason)

    def _unchanged(self, entity_id: UUID) -> WriteResult:
        return WriteResult(
            id=entity_id, version=self.tenancy.settings_version, outcome=WriteOutcome.UNCHANGED
        )

    def _company(self, company_id: UUID) -> FakeCompany:
        company = self.companies.get(company_id)
        if company is None:
            raise NotFound(code="not_found")
        return company

    def _company_taken(self, name: str, other_than: UUID | None) -> bool:
        return any(
            c.name.upper() == name.upper() and c.id != other_than for c in self.companies.values()
        )

    def _share_company(self, company_id: UUID | None, today: date) -> FakeCompany:
        company = self.companies.get(company_id) if company_id else None
        if company is None:
            raise NotFound(code="not_found")
        if not _company_active(company, today):
            raise RuleViolation(code="vehicle_company_inactive")
        return company

    def _check_fleet(self, company_id: UUID, fleet: str, other_than: UUID | None) -> None:
        if any(
            v.company_id == company_id
            and v.fleet_number is not None
            and v.fleet_number.upper() == fleet.upper()
            and v.id != other_than
            for v in self.vehicles.values()
        ):
            raise RuleViolation(code="vehicle_fleet_taken", detail={"fleet": fleet})

    def _main(self, main_id: UUID | None) -> FakeMainCategory | None:
        if main_id is None:
            return None
        main = self.main_categories.get(main_id)
        if main is None:
            raise NotFound(code="not_found")
        return main

    def _main_name(self, main_id: UUID | None) -> str | None:
        main = None if main_id is None else self.main_categories.get(main_id)
        return None if main is None else main.name

    def _main_taken(self, name: str, other_than: UUID | None) -> bool:
        return any(
            m.name.upper() == name.upper() and m.id != other_than
            for m in self.main_categories.values()
        )

    def _kind_item(self, item_id: UUID, member: FakeMember) -> FakeRecurring:
        """The item, not found when the caller cannot view its kind; then the edit right of
        its kind."""
        item = self._recurring(item_id)
        kind = item.versions[-1].kind
        if _kind_right(kind, "view") not in member.permissions:
            raise NotFound(code="not_found")
        if _kind_right(kind, "edit") not in member.permissions:
            raise Forbidden(code="permission_missing")
        return item

    def _vehicle(self, vehicle_id: UUID) -> FakeVehicle:
        vehicle = self.vehicles.get(vehicle_id)
        if vehicle is None:
            raise NotFound(code="not_found")
        return vehicle

    def _recurring(self, item_id: UUID) -> FakeRecurring:
        item = self.recurring.get(item_id)
        if item is None:
            raise NotFound(code="not_found")
        return item

    def _item_taken(self, category_id: UUID, name: str, other_than: UUID | None) -> bool:
        return any(
            i.category_id == category_id and i.name.upper() == name.upper() and i.id != other_than
            for i in self.items.values()
        )

    def _set_stopped(
        self,
        command: ExpenseLifecycle,
        record: FakeCategory | FakeExpenseItem,
        noun: str,
        snapshot: Callable[[Any], str],
    ) -> WriteResult:
        today = self._today(command.context)
        if command.stopped:
            if record.stopped_on == today:
                return self._unchanged(record.id)
            if record.stopped_on is not None:
                raise RuleViolation(code="expense_already_stopped")
        elif record.stopped_on is None:
            return self._unchanged(record.id)
        before = snapshot(record)
        record.stopped_on = today if command.stopped else None
        turned = "Turned off" if command.stopped else "Turned on"
        version = self._log(
            command.context,
            "expenses",
            record.id,
            before,
            snapshot(record),
            f"{turned} {noun} {record.name}",
        )
        return WriteResult(id=record.id, version=version, outcome=WriteOutcome.UPDATED)

    def _investment(
        self, details: InvestmentDetails, context: TenantContext
    ) -> tuple[date, str, Decimal]:
        if details.invested_on is None or details.invested_on > self._today(context):
            raise RuleViolation(code="investment_date_invalid")
        description = (details.description or "").strip()
        if not 1 <= len(description) <= 160:
            raise RuleViolation(code="investment_description_length")
        return details.invested_on, description, _money(details.amount)

    def _vehicle_summary(self, v: FakeVehicle, today: date, manages: bool) -> VehicleSummary:
        active = _in_fleet(v, today)
        posting = {
            item.id
            for item in self.recurring.values()
            if any(vehicle == v.id for vehicle, _ in item.versions[-1].shares)
            and (item.versions[-1].end is None or item.versions[-1].end >= today)
            and (item.stopped_from is None or item.stopped_from > today)
        }
        return VehicleSummary(
            id=v.id,
            company_id=v.company_id,
            company_name=self.companies[v.company_id].name,
            registration=v.registration,
            joined_on=v.joined_on,
            left_on=v.left_on,
            active=active,
            weekly_target=(_target_held(v, today) if active else Decimal(0)) if manages else None,
            targets=tuple(
                TargetEntry(
                    effective_from=s.starts_on,
                    weekly_amount=sum(s.days, Decimal(0)),
                    revision=number,
                )
                for number, s in enumerate(
                    sorted((s for s in v.sets if s.starts_on <= today), key=lambda s: s.starts_on),
                    start=1,
                )
            )
            if manages
            else (),
            recurring_items=(len(posting) if active else 0) if manages else None,
            away=tuple(v.away),
            fleet_number=v.fleet_number,
            initial_investment=v.initial_investment,
            day_targets=(
                in_force.days if manages and (in_force := _set_on(v, today)) is not None else None
            ),
            next_target=next(
                (
                    NextTarget(
                        starts_on=s.starts_on,
                        day_targets=s.days,
                        weekly_target=sum(s.days, Decimal(0)),
                    )
                    for s in sorted(v.sets, key=lambda s: s.starts_on)
                    if s.starts_on > today
                ),
                None,
            )
            if manages
            else None,
        )

    def _recurring_summary(self, item: FakeRecurring, today: date) -> RecurringSummary:
        version = item.versions[-1]
        shares = sorted(version.shares, key=lambda s: (self.vehicles[s[0]].registration, str(s[0])))
        allocations = tuple(
            ShareSummary(
                vehicle_id=vehicle_id,
                amount=amount,
                registration=self.vehicles[vehicle_id].registration,
                active=_in_fleet(self.vehicles[vehicle_id], today),
            )
            for vehicle_id, amount in shares
        )
        expense = self.items.get(version.expense_item_id) if version.expense_item_id else None
        return RecurringSummary(
            id=item.id,
            version_id=version.id,
            revision=version.revision,
            name=version.name,
            kind=RecurringKind(version.kind),
            amount=sum((a.amount for a in allocations), Decimal(0)),
            frequency=RecurrenceFrequency(version.frequency),
            day=version.day,
            last_day=version.last_day,
            start_on=version.start,
            end_on=version.end,
            stopped_from=item.stopped_from,
            allocations=allocations,
            partial=False,
            expense_item_id=version.expense_item_id,
            expense_item_name=None if expense is None else expense.name,
            bucket=ExpenseBucket(version.bucket or 2) if version.kind == 1 else None,
            note=version.note,
            month=version.month,
            active_amount=sum((a.amount for a in allocations if a.active), Decimal(0)),
            **self._recurring_runs_summary(item, today),
        )

    def _recurring_runs_summary(self, item: FakeRecurring, today: date) -> dict[str, Any]:
        """The list's pause, last run, balance, rule, opening and next run."""
        version = item.versions[-1]
        saving = version.kind == 2
        runs = (
            self._item_runs(item, min(v.start for v in item.versions), today, today)
            if saving
            else []
        )
        last = max((day for day, _, _ in runs), default=None)
        latest = [state for day, _, (_, state) in runs if day == last]
        upcoming = [
            day
            for day in _version_days(
                item, len(item.versions) - 1, today + timedelta(days=1), today + timedelta(days=400)
            )
            if any(_in_fleet(self.vehicles[vehicle_id], day) for vehicle_id, _ in version.shares)
        ]
        return {
            "paused_from": next((start for start, t in item.pauses if t is None), None),
            "last_run": last,
            "last_run_vehicles": len(latest),
            "balance": self._saving_balance(item, today) if saving else None,
            "last_run_states": RunStates(
                saved=latest.count(RunState.SAVED),
                skipped=latest.count(RunState.SKIPPED),
                held=latest.count(RunState.HELD),
            )
            if saving
            else None,
            "condition": None
            if version.condition_min is None or version.condition_days is None
            else RevenueRule(min=version.condition_min, days=version.condition_days),
            "opening": None
            if item.opened_on is None
            else OpeningSummary(date=item.opened_on, total=sum(item.opening.values(), Decimal(0))),
            "next_run": upcoming[0] if upcoming else None,
        }

    def _company_snapshot(self, company: FakeCompany) -> str:
        return _compact(
            {
                "Id": str(company.id),
                "Name": company.name,
                "ArchivedOn": _optional_iso(company.archived_on),
                "Active": company.archived_on is None,
            }
        )

    def _vehicle_snapshot(self, vehicle: FakeVehicle) -> str:
        return _compact(
            {
                "Id": str(vehicle.id),
                "Registration": vehicle.registration,
                "FleetNumber": vehicle.fleet_number,
                "CompanyId": str(vehicle.company_id),
                "JoinedOn": vehicle.joined_on.isoformat(),
                "LeftOn": _optional_iso(vehicle.left_on),
                "InitialInvestment": None
                if vehicle.initial_investment is None
                else _number(vehicle.initial_investment),
                "TargetSets": [
                    {"StartsOn": s.starts_on.isoformat()}
                    | {day: _number(amount) for day, amount in zip(_SET_DAYS, s.days, strict=True)}
                    for s in sorted(vehicle.sets, key=lambda s: s.starts_on)
                ],
                "Away": [
                    {"LeftOn": a.left_on.isoformat(), "ReturnedOn": a.returned_on.isoformat()}
                    for a in vehicle.away
                ],
            }
        )

    def _recurring_snapshot(self, item: FakeRecurring) -> str:
        return _compact(
            {
                "Id": str(item.id),
                "StoppedFrom": _optional_iso(item.stopped_from),
                "PausedFrom": next(
                    (start.isoformat() for start, through in item.pauses if through is None), None
                ),
                "Pauses": [
                    {"From": start.isoformat(), "Through": _optional_iso(through)}
                    for start, through in sorted(item.pauses, key=lambda p: p[0])
                ],
                "Versions": [
                    {
                        "Id": str(v.id),
                        "Revision": v.revision,
                        "EffectiveFrom": v.effective_from.isoformat(),
                        "Name": v.name,
                        "Kind": v.kind,
                        "Amount": _number(v.amount),
                        "Frequency": v.frequency,
                        "Day": v.day,
                        "LastDay": v.last_day,
                        "Month": v.month,
                        "Start": v.start.isoformat(),
                        "End": _optional_iso(v.end),
                        "ExpenseItemId": None
                        if v.expense_item_id is None
                        else str(v.expense_item_id),
                        "Bucket": v.bucket,
                        "Note": v.note,
                        "Allocations": [
                            {"VehicleId": str(vehicle), "Amount": _number(amount)}
                            for vehicle, amount in sorted(v.shares, key=lambda s: str(s[0]))
                        ],
                        "ConditionMin": None
                        if v.condition_min is None
                        else _number(v.condition_min),
                        "ConditionDays": v.condition_days,
                    }
                    for v in item.versions
                ],
                "Opening": None
                if item.opened_on is None
                else {
                    "Date": item.opened_on.isoformat(),
                    "Amounts": [
                        {"VehicleId": str(vehicle), "Amount": _number(amount)}
                        for vehicle, amount in sorted(item.opening.items(), key=lambda s: str(s[0]))
                    ],
                },
            }
        )

    def _category_snapshot(self, category: FakeCategory) -> str:
        return _compact(
            {
                "Id": str(category.id),
                "Name": category.name,
                "MainCategoryId": None
                if category.main_category_id is None
                else str(category.main_category_id),
                "StoppedOn": _optional_iso(category.stopped_on),
            }
        )

    def _main_snapshot(self, main: FakeMainCategory) -> str:
        return _compact({"Id": str(main.id), "Name": main.name})

    def _item_snapshot(self, item: FakeExpenseItem) -> str:
        return _compact(
            {
                "Id": str(item.id),
                "CategoryId": str(item.category_id),
                "Name": item.name,
                "StoppedOn": _optional_iso(item.stopped_on),
            }
        )

    def _investment_snapshot(self, entry: FakeInvestment) -> str:
        return _compact(
            {
                "Id": str(entry.id),
                "VehicleId": str(entry.vehicle_id),
                "Date": entry.invested_on.isoformat(),
                "Description": entry.description,
                "Amount": _number(entry.amount),
            }
        )


def _check_page(page: int, page_size: int) -> None:
    if not 1 <= page <= 100_000 or not 1 <= page_size <= 100:
        raise RuleViolation(code="page_out_of_range")


def _filter_choice[T](text: str | None, choices: dict[str, T], code: str) -> T | None:
    if text is None or text in {"", "all"}:
        return None
    if text not in choices:
        raise RuleViolation(code=code)
    return choices[text]


def _page[T](items: tuple[T, ...], page: int, page_size: int) -> tuple[T, ...]:
    return items[(page - 1) * page_size : page * page_size]


def _company_name(name: str | None) -> str:
    trimmed = (name or "").strip()
    if not 1 <= len(trimmed) <= 160:
        raise RuleViolation(code="company_name_length")
    return trimmed


def _catalogue_name(name: str | None) -> str:
    trimmed = (name or "").strip()
    if not 1 <= len(trimmed) <= 100:
        raise RuleViolation(code="expense_name_length")
    return trimmed


def _registration(registration: str | None) -> str:
    compact = (registration or "").strip().upper().replace(" ", "")
    if not _REGISTRATION.fullmatch(compact):
        raise RuleViolation(code="vehicle_registration_format")
    return f"{compact[:3]} {compact[3:]}"


def _joined(joined_on: date | None, today: date) -> date:
    if joined_on is None or joined_on > today:
        raise RuleViolation(code="vehicle_joined_future")
    return joined_on


_SET_DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


def _set_on(vehicle: FakeVehicle, day: date) -> FakeTargetSet | None:
    """The target set in force on ``day``: the latest start on or before it."""
    started = [s for s in vehicle.sets if s.starts_on <= day]
    return max(started, key=lambda s: s.starts_on) if started else None


def _target_held(vehicle: FakeVehicle, day: date) -> Decimal:
    """The weekly total of the target set in force on ``day``."""
    held = _set_on(vehicle, day)
    return Decimal(0) if held is None else sum(held.days, Decimal(0))


def _fleet_number(value: str | None) -> str:
    fleet = (value or "").strip()
    if not fleet:
        raise RuleViolation(code="vehicle_fleet_required")
    if len(fleet) > 20:
        raise RuleViolation(code="vehicle_fleet_length")
    return fleet


def _day_targets(days: tuple[Decimal | None, ...] | None) -> tuple[Decimal, ...]:
    if days is None or len(days) != 7 or any(d is None for d in days):
        raise RuleViolation(code="target_days_required")
    return tuple(_money(d) for d in days)


def _investment_amount(amount: Decimal | None) -> Decimal | None:
    """The initial investment: empty for null or 0, else a positive amount."""
    return None if amount is None or amount == 0 else _money(amount)


def _kind_right(kind: int, verb: str) -> str:
    return f"{'savings' if kind == 2 else 'scheduled'}.{verb}"


def _recurring_reason(kind: int, name: str) -> str:
    return f"{'Saving' if kind == 2 else 'Scheduled expense'}, {name}"


def _company_active(company: FakeCompany, day: date) -> bool:
    return company.archived_on is None or company.archived_on > day


def _in_fleet(vehicle: FakeVehicle, day: date) -> bool:
    return vehicle.joined_on <= day and (vehicle.left_on is None or vehicle.left_on > day)


def _in_use(stopped_on: date | None, day: date) -> bool:
    return stopped_on is None or stopped_on > day


def _schedule_valid(frequency: int, day: int | None, last_day: bool, month: int | None) -> bool:
    month_day = (day is not None and 1 <= day <= 28 and not last_day) or (last_day and day is None)
    if frequency == 1:
        return day is None and not last_day and month is None
    if frequency == 2:
        return day is not None and 0 <= day <= 6 and not last_day and month is None
    if frequency == 3:
        return month_day and month is None
    if frequency == 4:
        return month_day and month is not None and 1 <= month <= 12
    return False


def _checked_definition(
    d: RecurringDefinition, name: str, start: date | None
) -> tuple[Decimal, str | None, tuple[tuple[UUID, Decimal], ...]]:
    """The definition checks in the routine's order: name, amount, kind, note, dates, shares."""
    if not 1 <= len(name) <= 160:
        raise RuleViolation(code="recurring_name_length")
    amount = _money(d.amount)
    if d.kind not in (1, 2):
        raise RuleViolation(code="recurring_kind_invalid")
    note = (d.note or "").strip() or None
    if note is not None and len(note) > 200:
        raise RuleViolation(code="recurring_note_length")
    if start is not None and d.end is not None and d.end < start:
        raise RuleViolation(code="recurring_end_before_start")
    vehicles = [s.vehicle_id for s in d.allocations]
    if (
        not 1 <= len(vehicles) <= 500
        or any(v is None or v.int == 0 for v in vehicles)
        or len(set(vehicles)) != len(vehicles)
    ):
        raise RuleViolation(code="recurring_allocations_count")
    shares = tuple((s.vehicle_id, _money(s.amount)) for s in d.allocations if s.vehicle_id)
    if sum((a for _, a in shares), Decimal(0)) != amount:
        raise RuleViolation(code="recurring_allocation_sum")
    return amount, note, shares


def _due_on(version: FakeVersion, day: date) -> bool:
    if version.frequency == 1:
        return True
    if version.frequency == 2:
        return day.isoweekday() % 7 == version.day
    month_day = (day + timedelta(days=1)).day == 1 if version.last_day else day.day == version.day
    return month_day and (version.frequency == 3 or day.month == version.month)


def _version_days(item: FakeRecurring, index: int, first: date, last: date) -> list[date]:
    """``setup.recurring_due_days`` of one version: in charge, started, not ended, before the
    stop, on its schedule and outside every pause."""
    version = item.versions[index]
    bounds = [last]
    if version.end is not None:
        bounds.append(version.end)
    later = [v.effective_from for v in item.versions if v.revision > version.revision]
    if later:
        bounds.append(min(later) - timedelta(days=1))
    if item.stopped_from is not None:
        bounds.append(item.stopped_from - timedelta(days=1))
    day, end = max(first, version.effective_from, version.start), min(bounds)
    days = []
    while day <= end:
        paused = any(
            start <= day and (through is None or day <= through) for start, through in item.pauses
        )
        if _due_on(version, day) and not paused:
            days.append(day)
        day += timedelta(days=1)
    return days


def _new_save_start(
    d: RecurringDefinition, start: date | None, current: FakeVersion | None, today: date
) -> date:
    """The rules of a new save; the start, which it requires (a saving's is the business
    date when new, else kept)."""
    if d.frequency == 1 and d.kind == 1:
        raise RuleViolation(code="recurring_daily_retired")
    if d.kind == 1 and d.expense_item_id is None:
        raise RuleViolation(code="recurring_cost_needs_item")
    if start is None:
        raise RuleViolation(code="recurring_start_required")
    if start < today.replace(day=1) and (current is None or start != current.start):
        raise RuleViolation(code="recurring_start_too_early")
    return start


def _checked_saving(
    d: RecurringDefinition,
    item: FakeRecurring,
    current: FakeVersion | None,
    shares: tuple[tuple[UUID, Decimal], ...],
    today: date,
) -> tuple[tuple[Decimal | None, int | None], tuple[date | None, dict[UUID, Decimal]] | None]:
    """The saving's rule, its opening (None keeps the stored one) and its end, in order."""
    condition = _checked_condition(d)
    opening = _checked_opening(d, item, shares, today)
    stored_end = None if current is None else current.end
    if d.kind == 2 and d.end is not None and d.end != stored_end:
        raise RuleViolation(code="recurring_savings_end")
    return condition, opening


def _checked_condition(d: RecurringDefinition) -> tuple[Decimal | None, int | None]:
    if d.condition is None:
        return None, None
    if d.kind == 1:
        raise RuleViolation(code="recurring_condition_on_cost")
    minimum = d.condition.min
    if minimum is None or minimum <= 0 or minimum > _MONEY_CAP or round(minimum, 2) != minimum:
        raise RuleViolation(code="recurring_condition_min")
    if d.condition.days not in (1, 7, 30):
        raise RuleViolation(code="recurring_condition_days")
    return minimum, d.condition.days


def _checked_opening(
    d: RecurringDefinition,
    item: FakeRecurring,
    shares: tuple[tuple[UUID, Decimal], ...],
    today: date,
) -> tuple[date | None, dict[UUID, Decimal]] | None:
    """The opening to store, or None to keep the stored one."""
    if d.keep_opening and not (d.kind == 1 and item.opened_on is not None):
        return None
    if d.opening is None or d.keep_opening:
        return None, {}
    if d.kind == 1:
        raise RuleViolation(code="recurring_opening_on_cost")
    if d.opening.date is None or d.opening.date > today:
        raise RuleViolation(code="recurring_opening_future")
    for a in d.opening.amounts:
        if a.amount != 0:
            _money(a.amount)
    vehicles = [a.vehicle_id for a in d.opening.amounts]
    if any(v not in {s for s, _ in shares} for v in vehicles) or len(set(vehicles)) != len(
        vehicles
    ):
        raise RuleViolation(code="recurring_opening_vehicle")
    amounts = {a.vehicle_id: a.amount for a in d.opening.amounts if a.vehicle_id and a.amount}
    return (d.opening.date, amounts) if amounts else (None, {})


def _recurring_changes(
    current: FakeVersion,
    d: RecurringDefinition,
    name: str,
    bucket: int | None,
    amount: Decimal,
    start: date,
    note: str | None,
    shares: tuple[tuple[UUID, Decimal], ...],
) -> list[str]:
    """The words of ``Changed the ... of {name}``, in the routine's order."""
    parts = []
    if d.kind != current.kind:
        parts.append("type")
    if d.expense_item_id != current.expense_item_id:
        parts.append("expense item")
    elif name != current.name:
        parts.append("name")
    if bucket != current.bucket:
        parts.append("bucket")
    if amount != current.amount:
        parts.append("amount")
    if (d.frequency, d.day, d.last_day, d.month) != (
        current.frequency,
        current.day,
        current.last_day,
        current.month,
    ):
        parts.append("schedule")
    if start != current.start:
        parts.append("start date")
    if d.end != current.end:
        parts.append("end date")
    if set(shares) != set(current.shares):
        parts.append("vehicles")
    if note != current.note:
        parts.append("note")
    return parts


# --- revenue -------------------------------------------------------------------------------

_MONTH_ABBREVIATIONS = (
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
)
_INT32 = 2**31


@dataclass(slots=True)
class FakeRevenueRecord:
    id: UUID
    vehicle_id: UUID
    business_date: date
    amount: Decimal | None
    reason: NoEarningsReason | None
    note: str | None
    captured_at: datetime
    captured_by: UUID
    updated_at: datetime
    updated_by: UUID
    corrected_after_date: bool = False
    version: int = 1


@dataclass(frozen=True, slots=True)
class _FakeDay:
    """``revenue.vehicle_day``: one day of one vehicle with its record, if any."""

    vehicle_id: UUID
    day: date
    active: bool
    target: Decimal
    counted: bool
    record: FakeRevenueRecord | None


class FakeRevenueRepository:
    """In-memory ``RevenueRepository`` over the fleet of a ``FakeSetupRepository``, whose
    organization, members, settings and change log it shares.

    ``tests/db/test_fakes_match_routines.py`` runs ``tests/support/revenue_cases.py`` against
    this fake and the real routines: the capture's steps in order (shape against the low-day
    threshold, the vehicle, an identical replay whatever the version, the date and the limit, a
    future day, a day out of the fleet, the permission of the path before anything stored is
    shown, the back-dating limit at the capture time, a stale version with the stored cell as
    ``current``), the change-log rows and their snapshots, and the week grid and dashboard that
    show the result. Every vehicle and company is visible, as to an all-companies caller, and no
    two saves race."""

    def __init__(self, setup: FakeSetupRepository | None = None) -> None:
        self.setup = setup or FakeSetupRepository()
        self.records: dict[tuple[UUID, date], FakeRevenueRecord] = {}

    async def capture(self, command: RevenueCapture) -> CaptureResult:
        context = command.context
        member = self.setup._enter_any(context, "revenue.capture", "revenue.correct")
        permissions = member.permissions
        amount, reason, note = _revenue_entry(command)
        vehicle = self.setup._vehicle(command.vehicle_id)
        today = self.setup._today(context)
        day = command.day
        record = self.records.get((vehicle.id, day))
        if record is not None and (record.amount, record.reason, record.note) == (
            amount,
            reason,
            note,
        ):
            return CaptureResult(record.id, record.version, CaptureOutcome.REPLAYED)
        _revenue_low_day(amount, reason, self._threshold(), self.setup._currency())
        if day == date.min or day > today:
            raise RuleViolation(code="revenue_future_date")
        if not _revenue_active(vehicle, day):
            if _revenue_away(vehicle, day):
                raise RuleViolation(code="revenue_vehicle_away")
            raise RuleViolation(code="revenue_vehicle_inactive")
        if record is None and "revenue.capture" not in permissions:
            raise Forbidden(code="revenue_capture_permission")
        if record is not None and "revenue.correct" not in permissions:
            raise Forbidden(code="revenue_correct_permission")
        self._check_writable(member, day, command.captured_at or context.now, context.now)
        if record is not None and command.expected_version != record.version:
            current = _revenue_cell(
                self._days(vehicle.id, day, day, today)[0],
                today,
                "revenue.capture" in permissions,
                "revenue.correct" in permissions,
                self._earliest(member, today),
            )
            raise Conflict(
                code="revenue_version_conflict", detail={"current": _cell_document(current)}
            )
        which = f" for {vehicle.registration} on {_day_words(day)}"
        if record is None:
            record = FakeRevenueRecord(
                id=uuid4(),
                vehicle_id=vehicle.id,
                business_date=day,
                amount=amount,
                reason=reason,
                note=note,
                captured_at=context.now,
                captured_by=context.actor_id,
                updated_at=context.now,
                updated_by=context.actor_id,
            )
            self.records[(vehicle.id, day)] = record
            before = "null"
            if amount is None and reason is not None:
                words = f"Recorded no revenue{which}: {reason.label}"
            elif reason is not None:
                words = f"Recorded revenue{which}: {reason.label}"
            else:
                words = "Recorded revenue" + which
            outcome = CaptureOutcome.CREATED
        else:
            before = _record_snapshot(record)
            record.amount = amount
            record.reason = reason
            record.note = note
            record.updated_at = context.now
            record.updated_by = context.actor_id
            record.corrected_after_date = record.corrected_after_date or day < today
            record.version += 1
            words = ("Corrected revenue" if day < today else "Updated revenue") + which
            outcome = CaptureOutcome.UPDATED
        self.setup._log(context, "revenue", record.id, before, _record_snapshot(record), words)
        return CaptureResult(record.id, record.version, outcome)

    async def day(self, query: RevenueDayQuery) -> RevenueDay:
        context = query.context
        member = self.setup._enter(context, "revenue.view")
        today = self.setup._today(context)
        day = query.day or today
        if day > today or day < today - timedelta(days=3650):
            raise RuleViolation(code="revenue_day_date_range")
        capture = "revenue.capture" in member.permissions
        correct = "revenue.correct" in member.permissions
        earliest = self._earliest(member, today)
        fleet = sorted(
            (
                v
                for v in self.setup.vehicles.values()
                if (query.company_id is None or v.company_id == query.company_id)
                and _revenue_active(v, day)
            ),
            key=lambda v: (v.registration, v.id),
        )

        def last_week(vehicle_id: UUID) -> LastWeek | None:
            record = self.records.get((vehicle_id, day - timedelta(days=7)))
            if record is None:
                return None
            return LastWeek(
                amount=record.amount, reason=None if record.reason is None else record.reason.label
            )

        return RevenueDay(
            business_date=today,
            date=day,
            vehicles=tuple(
                RevenueDayVehicle(
                    id=v.id,
                    company_id=v.company_id,
                    registration=v.registration,
                    fleet_number=v.fleet_number,
                    day=_revenue_cell(
                        self._days(v.id, day, day, today)[0], today, capture, correct, earliest
                    ),
                    last_week=last_week(v.id),
                )
                for v in fleet[:500]
            ),
            truncated=len(fleet) > 500,
        )

    async def save_day(self, command: RevenueDaySave) -> RevenueDayResult:
        """Each row through ``capture`` in ascending vehicle id, all or none: a refusal puts
        the records and the change log back as they were."""
        context = command.context
        self.setup._enter_any(context, "revenue.capture", "revenue.correct")
        rows = command.rows
        if not rows:
            raise RuleViolation(code="revenue_day_rows_required")
        if len(rows) > 500:
            raise RuleViolation(code="revenue_day_rows_limit")
        ids = [r.vehicle_id for r in rows if r.vehicle_id is not None]
        if len(set(ids)) != len(ids):
            raise RuleViolation(code="revenue_day_vehicle_repeated")
        vehicles = [self.setup.vehicles.get(r.vehicle_id) if r.vehicle_id else None for r in rows]
        if any(v is None for v in vehicles):
            raise NotFound(code="not_found")
        captures = [
            RevenueCapture(
                context, r.vehicle_id, command.day, r.amount, r.reason, r.note, r.version, None
            )
            for r in rows
            if r.vehicle_id is not None
        ]
        registrations = {v.id: v.registration for v in vehicles if v is not None}
        tenancy = self.setup.tenancy
        records, log, version = (
            copy.deepcopy(self.records),
            len(tenancy.log),
            tenancy.settings_version,
        )
        saved: dict[UUID, CaptureResult] = {}
        try:
            for capture in captures:
                try:
                    _revenue_entry(capture)
                except RuleViolation as refusal:
                    raise _named(refusal, registrations[capture.vehicle_id]) from None
            for capture in sorted(captures, key=lambda c: c.vehicle_id):
                try:
                    saved[capture.vehicle_id] = await self.capture(capture)
                except RuleViolation as refusal:
                    raise _named(refusal, registrations[capture.vehicle_id]) from None
                except Conflict as conflict:
                    if conflict.code != "revenue_version_conflict":
                        raise
                    raise Conflict(
                        code="revenue_day_conflict",
                        detail={
                            "vehicle_id": str(capture.vehicle_id),
                            "registration": registrations[capture.vehicle_id],
                            "current": conflict.detail.get("current"),
                        },
                    ) from None
        except Exception:
            self.records = records
            del tenancy.log[log:]
            tenancy.settings_version = version
            raise
        return RevenueDayResult(
            rows=tuple(
                RevenueDaySaved(
                    vehicle_id=c.vehicle_id,
                    id=saved[c.vehicle_id].id,
                    version=saved[c.vehicle_id].version,
                )
                for c in captures
            )
        )

    async def week(self, query: RevenueWeekQuery) -> RevenueWeek:
        context = query.context
        member = self.setup._enter(context, "revenue.view")
        permissions = member.permissions
        capture = "revenue.capture" in permissions
        correct = "revenue.correct" in permissions
        today = self.setup._today(context)
        earliest = self._earliest(member, today)
        threshold = self._threshold()
        amber = self._amber()
        paged = query.vehicle_id is None and (query.page is not None or query.page_size is not None)
        page, size = 1, 500
        if paged:
            page = 1 if query.page is None else query.page
            size = 100 if query.page_size is None else query.page_size
            _check_page(page, size)
        search = (query.q or "").strip().casefold()
        if len(search) > 40:
            raise RuleViolation(code="revenue_search_length")
        current_start = self._week_start(today)
        start = self._week_start(query.week_start or today)
        if start > current_start or start < current_start - timedelta(days=3650):
            raise RuleViolation(code="revenue_week_range")
        through = start + timedelta(days=6)
        grid = sorted(
            (
                v
                for v in self.setup.vehicles.values()
                if (query.company_id is None or v.company_id == query.company_id)
                and (
                    not search
                    or search in v.registration.casefold()
                    or search in (v.fleet_number or "").casefold()
                )
                and (
                    _in_week(v, start, through)
                    if query.vehicle_id is None
                    else v.id == query.vehicle_id
                )
            ),
            key=lambda v: (v.registration, v.id),
        )
        unknown = query.vehicle_id is not None and query.vehicle_id not in self.setup.vehicles
        if unknown and not grid:
            raise NotFound(code="not_found")
        shown = grid[(page - 1) * size : page * size]
        companies = tuple(
            CompanyChoice(id=c.id, name=c.name)
            for c in sorted(self.setup.companies.values(), key=lambda c: (c.name, c.id))
            if _company_active(c, today)
            or any(
                v.company_id == c.id and _in_week(v, start, through)
                for v in self.setup.vehicles.values()
            )
        )
        days = {v.id: self._days(v.id, start, through, today) for v in grid}
        missing = {v.id: self._earliest_missing(v, today) for v in grid}
        rows = []
        for v in shown:
            amount, target = _counted_sums(days[v.id])
            rows.append(
                RevenueVehicleWeek(
                    id=v.id,
                    company_id=v.company_id,
                    company_name=self.setup.companies[v.company_id].name,
                    registration=v.registration,
                    joined_on=v.joined_on,
                    left_on=v.left_on,
                    earliest_missing=missing[v.id],
                    fleet_number=v.fleet_number,
                    days=tuple(
                        _revenue_cell(d, today, capture, correct, earliest) for d in days[v.id]
                    ),
                    total_amount=_half_even(amount),
                    total_expected=_half_even(target),
                    percent=_percent(amount, target),
                    gap=_half_even(amount - target),
                    gap_band=_gap_band(amount - target, target, amber),
                    below_threshold_days=_low_days(days[v.id], threshold),
                )
            )
        every_day = [d for v in grid for d in days[v.id]]
        amount, target = _counted_sums(every_day)
        day_totals = []
        for offset in range(7):
            on = start + timedelta(days=offset)
            that_day = [d for d in every_day if d.day == on]
            shown_amount = sum(
                (_amount_of(d) for d in that_day if d.active and d.day <= today), Decimal(0)
            )
            counted_target = sum((d.target for d in that_day if d.counted), Decimal(0))
            day_totals.append(
                RevenueDayTotal(
                    day=on,
                    amount=_half_even(shown_amount),
                    expected=_half_even(counted_target),
                )
            )
        gaps = []
        for order, v in enumerate(grid):
            gap = missing[v.id]
            if gap is None:
                on_today = [d for d in days[v.id] if d.day == today]
                if on_today and on_today[0].active and on_today[0].record is None:
                    gap = today
            if gap is not None:
                gaps.append((gap, order, v.id))
        first = min(gaps) if gaps else None
        return RevenueWeek(
            week_start=start,
            week_through=through,
            current_week_start=current_start,
            business_date=today,
            companies=companies,
            vehicles=tuple(rows),
            total_amount=_half_even(amount),
            total_expected=_half_even(target),
            percent=_percent(amount, target),
            page_number=page,
            page_size=size,
            total_vehicles=len(grid),
            truncated=not paged and query.vehicle_id is None and len(grid) > 500,
            day_totals=tuple(day_totals),
            first_gap=None if first is None else RevenueGap(vehicle_id=first[2], day=first[0]),
            low_day_threshold=threshold,
            gap_amber_percent=amber,
            gap=_half_even(amount - target),
            gap_band=_gap_band(amount - target, target, amber),
            below_threshold_days=_low_days(every_day, threshold),
            missing_days=sum(1 for d in every_day if d.counted and d.record is None),
        )

    async def dashboard(self, query: RevenueDashboardQuery) -> RevenueDashboard:
        context = query.context
        permissions = self.setup._enter_any(context, "dash.net", "dash.gaps").permissions
        today = self.setup._today(context)
        period = query.period if query.period is not None else "week"
        starts = {
            "today": today,
            "week": self._week_start(today),
            "month": today.replace(day=1),
        }
        if period not in starts:
            raise RuleViolation(code="dashboard_period_invalid")
        start = starts[period]
        fleet = [
            v
            for v in self.setup.vehicles.values()
            if (query.company_id is None or v.company_id == query.company_id)
            and v.joined_on <= today
            and (v.left_on is None or v.left_on > start)
        ]
        revenue = target = Decimal(0)
        captured = vehicles_today = missing_days = missing_vehicles = edited = 0
        for v in fleet:
            days = [d for d in self._days(v.id, start, today, today) if d.active]
            revenue += sum((_amount_of(d) for d in days), Decimal(0))
            target += sum((d.target for d in days if d.counted), Decimal(0))
            gaps = sum(1 for d in days if d.day < today and d.record is None)
            missing_days += gaps
            missing_vehicles += 1 if gaps else 0
            on_today = [d for d in days if d.day == today]
            vehicles_today += len(on_today)
            captured += sum(1 for d in on_today if d.record is not None)
            edited += sum(1 for d in days if d.record is not None and d.record.corrected_after_date)
        shows_revenue = "dash.net" in permissions
        shows_capture = shows_gaps = "dash.gaps" in permissions
        return RevenueDashboard(
            period=DashboardPeriod(period),
            from_date=start,
            through=today,
            business_date=today,
            revenue=_half_even(revenue) if shows_revenue else None,
            expected=_half_even(target) if shows_revenue else None,
            percent=_percent(revenue, target) if shows_revenue else None,
            captured_today=captured if shows_capture else None,
            vehicles_today=vehicles_today if shows_capture else None,
            missing_days=missing_days if shows_gaps else None,
            missing_vehicles=missing_vehicles if shows_gaps else None,
            edited_records=edited if shows_revenue else None,
        )

    def _week_start(self, day: date) -> date:
        first_day = self.setup.tenancy.sections["localization"]["first_day_of_week"]
        return day - timedelta(days=((day.isoweekday() % 7) - first_day + 7) % 7)

    def _threshold(self) -> Decimal:
        return Decimal(self.setup.tenancy.sections["revenue"]["low_day_threshold"])

    def _amber(self) -> Decimal:
        return Decimal(self.setup.tenancy.sections["revenue"]["gap_amber_percent"])

    def _business_date(self, moment: datetime) -> date:
        """``tenancy.business_date``: the held date, else the calendar date of ``moment`` in
        the organization's zone."""
        tenancy = self.setup.tenancy
        zone = ZoneInfo(tenancy.sections["localization"]["time_zone"])
        return tenancy.business_date or moment.astimezone(zone).date()

    def _check_writable(
        self, member: FakeMember, day: date, captured: datetime, now: datetime
    ) -> None:
        """``tenancy.check_writable`` as of the capture time held to the last 72 hours."""
        earliest = self._earliest(
            member, self._business_date(max(min(captured, now), now - _OFFLINE))
        )
        if earliest is not None and day < earliest:
            raise RuleViolation(code="record_too_old", detail={"earliest": earliest.isoformat()})

    def _earliest(self, member: FakeMember, today: date) -> date | None:
        return earliest_writable(
            member.back_limit_mode, member.back_limit_count, member.back_limit_from, today
        )

    def _days(self, vehicle_id: UUID, first: date, last: date, today: date) -> list[_FakeDay]:
        vehicle = self.setup.vehicles[vehicle_id]
        days = []
        for offset in range((last - first).days + 1):
            day = first + timedelta(days=offset)
            active = _revenue_active(vehicle, day)
            record = self.records.get((vehicle_id, day))
            days.append(
                _FakeDay(
                    vehicle_id=vehicle_id,
                    day=day,
                    active=active,
                    target=_day_target(vehicle, day) if active else Decimal(0),
                    counted=active and (day < today or record is not None),
                    record=record,
                )
            )
        return days

    def _earliest_missing(self, vehicle: FakeVehicle, today: date) -> date | None:
        end = vehicle.left_on if vehicle.left_on is not None and vehicle.left_on < today else today
        day = vehicle.joined_on
        while day < end:
            if not _revenue_away(vehicle, day) and (vehicle.id, day) not in self.records:
                return day
            day += timedelta(days=1)
        return None


_OFFLINE = timedelta(hours=72)


def _named(refusal: RuleViolation, registration: str) -> RuleViolation:
    """A day save's refused row: the same code, its detail naming the vehicle."""
    return RuleViolation(
        code=refusal.code, detail={**refusal.detail, "vehicle_registration": registration}
    )


def _revenue_entry(
    command: RevenueCapture,
) -> tuple[Decimal | None, NoEarningsReason | None, str | None]:
    """The capture's shape checks, in the routine's order: the reason, the amount (0 with a
    reason is none) and the trimmed note."""
    reason = _revenue_reason(command.reason)
    note = (command.note or "").strip() or None
    amount = None if command.amount == 0 and reason is not None else command.amount
    if amount is not None:
        _money(amount)
    if amount is None and reason is None:
        raise RuleViolation(code="revenue_entry_required")
    if note is not None and len(note) > 80:
        raise RuleViolation(code="revenue_note_length")
    if note is not None and reason is not NoEarningsReason.OTHER:
        raise RuleViolation(code="revenue_note_without_other")
    return amount, reason, note


def _revenue_low_day(
    amount: Decimal | None, reason: NoEarningsReason | None, threshold: Decimal, currency: str
) -> None:
    """The capture's threshold checks, after the identical replay."""
    words = {"currency": currency, "threshold": _formatted(threshold)}
    if amount is not None and amount < threshold and reason is None:
        raise RuleViolation(code="revenue_low_needs_reason", detail=words)
    if amount is not None and amount >= threshold and reason is not None:
        raise RuleViolation(code="revenue_amount_with_reason", detail=words)


def _day_target(vehicle: FakeVehicle, day: date) -> Decimal:
    """``setup.day_target`` for a day in the fleet: that weekday's figure of the set in force."""
    held = _set_on(vehicle, day)
    return Decimal(0) if held is None else held.days[day.isoweekday() - 1]


def _gap_band(gap: Decimal, target: Decimal, amber: Decimal) -> GapBand | None:
    """``revenue.gap_band``."""
    if target == 0:
        return None
    if gap >= 0:
        return GapBand.GREEN
    return GapBand.AMBER if -gap * 100 <= target * amber else GapBand.RED


def _low_days(days: Iterable[_FakeDay], threshold: Decimal) -> int:
    """Days that count whose record holds a reason alone or an amount below the threshold."""
    return sum(
        1
        for d in days
        if d.counted
        and d.record is not None
        and (d.record.amount is None or d.record.amount < threshold)
    )


def _revenue_reason(text: str | None) -> NoEarningsReason | None:
    """``revenue.reason_code`` of the trimmed text: a label, or a label without its spaces."""
    trimmed = (text or "").strip()
    if not trimmed:
        return None
    for reason in NoEarningsReason:
        if trimmed in (reason.label, reason.label.replace(" ", "")):
            return reason
    raise RuleViolation(code="revenue_reason_invalid")


def _revenue_away(vehicle: FakeVehicle, day: date) -> bool:
    return any(a.left_on <= day < a.returned_on for a in vehicle.away)


def _revenue_active(vehicle: FakeVehicle, day: date) -> bool:
    return _in_fleet(vehicle, day) and not _revenue_away(vehicle, day)


def _in_week(vehicle: FakeVehicle, start: date, through: date) -> bool:
    return vehicle.joined_on <= through and (vehicle.left_on is None or vehicle.left_on > start)


def _revenue_cell(
    day: _FakeDay, today: date, capture: bool, correct: bool, earliest: date | None
) -> RevenueCell:
    """``revenue.cell``."""
    record = day.record
    if not day.active:
        status = CellStatus.NONE
    elif day.day > today:
        status = CellStatus.FUTURE
    elif record is None:
        status = CellStatus.MISSING
    elif record.amount is not None:
        status = CellStatus.AMOUNT
    else:
        status = CellStatus.REASON
    if earliest is not None and day.day < earliest:
        can_edit = False
    elif status is CellStatus.MISSING:
        can_edit = capture
    elif status in (CellStatus.AMOUNT, CellStatus.REASON):
        can_edit = correct
    else:
        can_edit = False
    return RevenueCell(
        day=day.day,
        status=status,
        expected=_half_even(day.target),
        amount=None if record is None else record.amount,
        reason=None if record is None or record.reason is None else record.reason.label,
        note=None if record is None else record.note,
        can_edit=can_edit,
        edited_after_capture=record is not None and record.corrected_after_date,
        version=None if record is None else record.version,
    )


def _amount_of(day: _FakeDay) -> Decimal:
    if day.record is None or day.record.amount is None:
        return Decimal(0)
    return day.record.amount


def _counted_sums(days: Iterable[_FakeDay]) -> tuple[Decimal, Decimal]:
    counted = [d for d in days if d.counted]
    return (
        sum((_amount_of(d) for d in counted), Decimal(0)),
        sum((d.target for d in counted), Decimal(0)),
    )


def _half_even(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)


def _percent(amount: Decimal, target: Decimal) -> int | None:
    """``revenue.percent``: the amount against the sum of the day targets, rounded half away
    from zero and held to a 32-bit integer; null without a target."""
    if target == 0:
        return None
    value = int((amount * 100 / target).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    return max(min(value, _INT32 - 1), -_INT32)


def _day_words(day: date) -> str:
    """``tenancy.fmt_day``: ``8 Oct 2026``."""
    return f"{day.day} {_MONTH_ABBREVIATIONS[day.month - 1]} {day.year}"


def _instant_text(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f+00:00")


def _record_snapshot(record: FakeRevenueRecord) -> str:
    """``revenue.record_snapshot``."""
    return _compact(
        {
            "Id": str(record.id),
            "VehicleId": str(record.vehicle_id),
            "BusinessDate": record.business_date.isoformat(),
            "Amount": None if record.amount is None else _number(record.amount),
            "Reason": None if record.reason is None else record.reason.snapshot_name,
            "Note": record.note,
            "CapturedAt": _instant_text(record.captured_at),
            "CapturedBy": str(record.captured_by),
            "UpdatedAt": _instant_text(record.updated_at),
            "UpdatedBy": str(record.updated_by),
            "CorrectedAfterDate": record.corrected_after_date,
            "Version": record.version,
        }
    )


def _cell_document(cell: RevenueCell) -> dict[str, Any]:
    """The ``current`` member of the stale-version refusal's detail, as ``revenue.cell``
    sends it."""
    return {
        "day": cell.day.isoformat(),
        "status": cell.status.value,
        "expected": cell.expected,
        "amount": cell.amount,
        "reason": cell.reason,
        "note": cell.note,
        "can_edit": cell.can_edit,
        "edited_after_capture": cell.edited_after_capture,
        "version": cell.version,
    }


# --- petty cash ------------------------------------------------------------------------------

_PC_BLANKS = "".join(
    map(
        chr,
        (
            *range(0x09, 0x0E),
            0x20,
            0x85,
            0xA0,
            0x1680,
            *range(0x2000, 0x200B),
            0x2028,
            0x2029,
            0x202F,
            0x205F,
            0x3000,
        ),
    )
)
_PC_NO_ID = UUID(int=0)
_PC_LARGEST = Decimal("999999999999.99")
_PC_WIDE = Context(prec=60)
_PC_KINDS = {"cash": 1, "expense": 2, "credit": 3}
_PC_STATUS_WORDS = frozenset({"waiting", "approved", "sentBack", "rejected"})


@dataclass(slots=True)
class FakePettyCashEntry:
    id: UUID
    holder_id: UUID
    kind: int
    entry_date: date
    vehicle_id: UUID | None
    expense_item_id: UUID | None
    units: Decimal
    unit_amount: Decimal
    payee: str | None
    note: str | None
    reimbursable: bool
    status: int | None
    recorded_by: UUID
    recorded_at: datetime
    updated_by: UUID
    updated_at: datetime
    sent_back_note: str | None = None
    reject_reason: str | None = None
    reopen_reason: str | None = None
    reviewed_by: UUID | None = None
    reviewed_at: datetime | None = None
    removed_by: UUID | None = None
    removed_at: datetime | None = None
    removal_reason: str | None = None
    version: int = 1
    group_id: UUID | None = None
    group_total: Decimal | None = None
    group_units: Decimal | None = None
    group_unit_amount: Decimal | None = None

    @property
    def total(self) -> Decimal:
        return _pc_round(self.units * self.unit_amount, 2)


@dataclass(frozen=True, slots=True)
class _PcLine:
    """A line as the routines read it: kind code, texts trimmed, the empty id as none."""

    kind: int | None
    day: date | None
    unit_amount: Decimal | None
    units: Decimal
    vehicle_id: UUID | None
    expense_item_id: UUID | None
    payee: str | None
    note: str | None
    reimbursable: bool


@dataclass(frozen=True, slots=True)
class _PcActor:
    """The caller as one routine sees it: effective rights, visible vehicles, approval limit
    and back-dating limit, read once."""

    member: FakeMember
    held: tuple[str, ...]
    vehicles: frozenset[UUID]
    today: date
    earliest: date | None

    @property
    def id(self) -> UUID:
        return self.member.user_id

    @property
    def view_all(self) -> bool:
        return "pettycash.view_all" in self.held

    @property
    def limit(self) -> Decimal | None:
        return self.member.approval_limit

    def holds(self, *rights: str) -> bool:
        return any(f"pettycash.{right}" in self.held for right in rights)


class FakePettyCashRepository:
    """In-memory ``PettyCashRepository`` over the organization of a ``FakeSetupRepository``,
    whose members, fleet, expense catalogue, settings and change log it shares.

    ``tests/db/test_fakes_match_routines.py`` runs ``tests/support/pettycash_cases.py``
    against this fake and the real routines: every write's steps in order (the line checks,
    the holder rules, the dates and the back-dating limit, the vehicle and item, the float
    guard with the balance after, the reviewer rule, the version with the entry as it is now
    as ``current``, the replays), the change-log rows and their snapshots, and the overview,
    list, options and dashboard that show the result. No two saves race."""

    def __init__(self, setup: FakeSetupRepository | None = None) -> None:
        self.setup = setup or FakeSetupRepository()
        self.stored: dict[UUID, FakePettyCashEntry] = {}

    # --- reads ----------------------------------------------------------------------------

    async def overview(self, query: PettyCashOverviewQuery) -> PettyCashOverview:
        actor = self._enter(query.context, "view")
        today = actor.today
        if query.from_date is not None or query.to_date is not None:
            _pc_check_period(query.from_date, query.to_date, today)
            assert query.from_date is not None and query.to_date is not None
            first, last, day = query.from_date, query.to_date, query.to_date
            period = OverviewPeriod.DAY if first == last else OverviewPeriod.RANGE
        else:
            day = query.day or today
            _pc_check_date(day, today)
            word = _pc_trim(query.period) or "day"
            if word == "day":
                first = last = day
            elif word == "week":
                first = self._week_start(day)
                last = first + timedelta(days=6)
            else:
                raise RuleViolation(code="pettycash_period_invalid")
            period = OverviewPeriod(word)
        holders = self._visible_holders(actor)
        chosen = [h for h in holders if query.holder_id is None or h.id == query.holder_id]
        if query.holder_id is not None and not chosen:
            raise NotFound(code="not_found")
        ids = {h.id for h in chosen}
        seen = [e for e in self._visible(actor) if e.holder_id in ids]

        def position(e: FakePettyCashEntry) -> int:
            return 0 if e.entry_date < first else 1 if e.entry_date <= last else 2

        within = [e for e in seen if position(e) == 1]
        opening = _pc_sum(_pc_effect(e) for e in seen if position(e) == 0)
        cash = _pc_sum(e.total for e in within if e.kind == 1)
        spent = _pc_sum(e.total for e in within if e.kind == 2 and e.status != 4)
        credit = _pc_sum(e.total for e in within if e.kind == 3)
        waiting = [e for e in within if _pc_ready(e)]
        figures = PettyCashFigures(
            opening_balance=opening,
            cash_received=cash,
            expenses=spent,
            credit_notes=credit,
            money_out=spent + credit,
            closing_balance=opening + cash - spent - credit,
            waiting=_pc_sum(e.total for e in waiting),
            waiting_count=len(waiting),
        )
        floats = tuple(self._float_row(h, [e for e in seen if e.holder_id == h.id]) for h in chosen)
        permissions = PettyCashPermissions(
            holder_id=actor.id if actor.holds("spend") else None,
            can_spend=actor.holds("spend"),
            can_view_all=actor.view_all,
            can_issue=actor.holds("issue"),
            can_issue_negative=actor.holds("issue_negative"),
            can_approve_item=actor.holds("approve_item"),
            can_approve_day=actor.holds("approve_day"),
            approval_limit=actor.limit,
            can_view=actor.holds("view"),
            can_spend_other=actor.holds("spend_other"),
            can_edit_own=actor.holds("edit_own"),
            can_edit=actor.holds("edit"),
            can_delete_own=actor.holds("delete_own"),
            can_delete=actor.holds("delete"),
            can_delete_approved=actor.holds("delete_approved"),
            can_send_back=actor.holds("send_back"),
            can_reject=actor.holds("reject"),
            can_reopen=actor.holds("reopen"),
            can_credit=actor.holds("credit"),
            can_delete_cash=actor.holds("delete_cash"),
            earliest_date=actor.earliest,
        )
        return PettyCashOverview(
            business_date=today,
            day=day,
            period=period,
            from_date=first,
            to_date=last,
            permissions=permissions,
            holders=tuple(holders),
            figures=figures,
            floats=floats,
        )

    async def entries(self, query: PettyCashEntryQuery) -> PettyCashEntryPage:
        actor = self._enter(query.context, "view")
        page = query.page
        size = query.page_size
        if page is None or size is None:
            raise RuleViolation(code="page_out_of_range")
        _check_page(page, size)
        if (
            query.from_date is not None
            and query.to_date is not None
            and query.from_date > query.to_date
        ):
            raise RuleViolation(code="history_dates_order")
        text = _pc_trim(query.q)
        if text is not None and len(text) > 200:
            raise RuleViolation(code="history_text_length")
        kinds = [_PC_KINDS.get(_pc_trim(word) or "") for word in query.kinds or ()]
        if None in kinds:
            raise RuleViolation(code="pettycash_kind_invalid")
        statuses = list(query.statuses or ())
        if any(word not in _PC_STATUS_WORDS for word in statuses):
            raise RuleViolation(code="pettycash_status_invalid")
        self._check_holder(actor, query.holder_id)

        def matches(e: FakePettyCashEntry) -> bool:
            if text is None:
                return True
            item = self.setup.items.get(e.expense_item_id) if e.expense_item_id else None
            vehicle = self.setup.vehicles.get(e.vehicle_id) if e.vehicle_id else None
            fields = (
                e.note,
                e.payee,
                self._name(e.holder_id),
                None if vehicle is None else vehicle.registration,
                None if item is None else item.name,
            )
            return any(f is not None and text.lower() in f.lower() for f in fields)

        found = sorted(
            (
                e
                for e in self._visible(actor)
                if (query.holder_id is None or e.holder_id == query.holder_id)
                and (query.from_date is None or e.entry_date >= query.from_date)
                and (query.to_date is None or e.entry_date <= query.to_date)
                and (not kinds or e.kind in kinds)
                and (not statuses or _pc_status_word(e) in statuses)
                and matches(e)
            ),
            key=lambda e: (e.entry_date, e.kind, e.id),
        )
        shown = found[(page - 1) * size : page * size]
        return PettyCashEntryPage(
            items=tuple(self._document(e, actor) for e in shown), total=len(found)
        )

    async def options(self, query: PettyCashOptionsQuery) -> PettyCashOptions:
        actor = self._enter(
            query.context, "spend", "spend_other", "edit_own", "edit", "issue", "credit"
        )
        day = query.day or actor.today
        _pc_check_date(day, actor.today)
        vehicles: tuple[PettyCashVehicleOption, ...] = ()
        items: tuple[PettyCashItemOption, ...] = ()
        if actor.holds("spend", "spend_other", "edit_own", "edit"):
            vehicles = tuple(
                PettyCashVehicleOption(
                    id=v.id,
                    company_id=v.company_id,
                    company_name=self.setup.companies[v.company_id].name,
                    registration=v.registration,
                    active=True,
                    fleet_number=v.fleet_number,
                )
                for v in sorted(self.setup.vehicles.values(), key=lambda v: (v.registration, v.id))
                if v.id in actor.vehicles and _revenue_active(v, day)
            )
            listed = []
            for item in self.setup.items.values():
                category = self.setup.categories[item.category_id]
                if _in_use(item.stopped_on, day) and _in_use(category.stopped_on, day):
                    listed.append((category.name, item.name, item.id, category))
            items = tuple(
                PettyCashItemOption(
                    id=item_id,
                    name=name,
                    category_id=category.id,
                    category_name=category.name,
                    bucket=_pc_bucket(category),
                )
                for _, name, item_id, category in sorted(listed, key=lambda r: r[:3])
            )
        holders: tuple[PettyCashHolder, ...] = ()
        if actor.holds("spend_other", "issue", "credit"):
            holders = tuple(h for h in self._holders() if h.active)
        return PettyCashOptions(vehicles=vehicles, items=items, holders=holders)

    async def dashboard(self, context: TenantContext) -> PettyCashDashboard:
        member = self.setup.tenancy._enter(context)
        if "dash.pettycash" not in member.held():
            raise Forbidden(code="permission_missing")
        actor = self._actor(context, member)
        card = None
        if actor.holds("spend"):
            own = [
                e
                for e in self.stored.values()
                if e.holder_id == actor.id and e.kind == 2 and e.removed_at is None
            ]
            month = actor.today.replace(day=1)
            card = PettyCashFloatCard(
                balance=self._balance(actor.id),
                waiting_count=sum(1 for e in own if _pc_ready(e)),
                waiting_total=_pc_sum(e.total for e in own if _pc_ready(e)),
                sent_back_count=sum(
                    1 for e in own if e.status == 1 and e.sent_back_note is not None
                ),
                approved_this_month=_pc_sum(
                    e.total for e in own if e.status == 2 and month <= e.entry_date <= actor.today
                ),
            )
        approvals = None
        if actor.holds("approve_item"):
            waiting = [e for e in self._visible(actor) if _pc_ready(e)]
            groups: dict[UUID, list[FakePettyCashEntry]] = {}
            for e in waiting:
                groups.setdefault(e.holder_id, []).append(e)
            rows = sorted(
                (
                    PettyCashApprovalHolder(
                        holder_id=holder,
                        name=self._name(holder) or "",
                        count=len(group),
                        total=_pc_sum(e.total for e in group),
                        oldest=min(e.entry_date for e in group),
                    )
                    for holder, group in groups.items()
                ),
                key=lambda r: (r.oldest, r.name, r.holder_id),
            )
            limit = actor.limit
            approvals = PettyCashApprovalsCard(
                count=len(waiting),
                total=_pc_sum(e.total for e in waiting),
                approval_limit=limit,
                above_limit=sum(1 for e in waiting if limit is not None and abs(e.total) > limit),
                holders=tuple(rows),
            )
        return PettyCashDashboard(float_card=card, approvals=approvals)

    # --- writes ---------------------------------------------------------------------------

    async def create(self, command: PettyCashCreate) -> PettyCashSaved:
        context = command.context
        actor = self._enter(context, "spend", "spend_other", "issue", "credit")
        shared = bool(command.allocations)
        parts: list[tuple[UUID, Decimal, Decimal]] = []
        if shared and _PC_KINDS.get(_pc_trim(command.line.kind) or "") == 2:
            given = command.line
            parts = _expense_check_purchase(
                given.day,
                None if given.expense_item_id == _PC_NO_ID else given.expense_item_id,
                Decimal(1) if given.units is None else given.units,
                given.unit_amount,
                _pc_trim(given.note),
                command.allocations,
            )
            if _pc_trim(given.payee) is not None or given.reimbursable:
                raise RuleViolation(code="pettycash_line_expense_payee")
            line = _pc_line(replace(given, vehicle_id=parts[0][0]))
        else:
            line = _pc_line(command.line)
            if shared:
                code = (
                    "pettycash_line_credit_vehicle"
                    if line.kind == 3
                    else "pettycash_line_cash_shape"
                )
                raise RuleViolation(code=code)
        entry_id = None if command.id == _PC_NO_ID else command.id
        if entry_id is not None and entry_id in self.stored:
            stored = self.stored[entry_id]
            if stored.recorded_by != actor.id:
                raise Conflict(code="pettycash_already_saved", detail={"current": None})
            return self._saved(stored, SaveOutcome.REPLAYED)
        holder = self._holder_for(line.kind, command.line.holder_id, actor)
        status = 1 if line.kind == 2 else None
        assert line.kind is not None and line.day is not None and line.unit_amount is not None
        _pc_check_date(line.day, actor.today)
        self._check_writable(line.day, actor)
        if len(parts) > 1:
            for index, (vehicle_id, _, _) in enumerate(parts):
                self._check_expense(
                    vehicle_id, line.expense_item_id, line.day, actor, True, index == 0
                )
        elif line.kind == 2:
            self._check_expense(line.vehicle_id, line.expense_item_id, line.day, actor, True, True)
        total = _pc_round(line.units * line.unit_amount, 2)
        self._guard(holder, line.kind, _pc_effect_of(line.kind, status, total), actor)
        if len(parts) > 1:
            group = entry_id or uuid4()
            made = []
            for index, (vehicle_id, units, unit_amount) in enumerate(parts):
                part = FakePettyCashEntry(
                    id=group if index == 0 else uuid4(),
                    holder_id=holder,
                    kind=2,
                    entry_date=line.day,
                    vehicle_id=vehicle_id,
                    expense_item_id=line.expense_item_id,
                    units=units,
                    unit_amount=unit_amount,
                    payee=None,
                    note=line.note,
                    reimbursable=False,
                    status=status,
                    recorded_by=actor.id,
                    recorded_at=context.now,
                    updated_by=actor.id,
                    updated_at=context.now,
                    group_id=group,
                    group_total=total,
                    group_units=line.units,
                    group_unit_amount=line.unit_amount,
                )
                self.stored[part.id] = part
                made.append(part)
            for part in made:
                self._log(context, part, "null", "Recorded", None)
            return self._saved(made[0], SaveOutcome.CREATED)
        entry = FakePettyCashEntry(
            id=entry_id or uuid4(),
            holder_id=holder,
            kind=line.kind,
            entry_date=line.day,
            vehicle_id=line.vehicle_id,
            expense_item_id=line.expense_item_id,
            units=line.units,
            unit_amount=line.unit_amount,
            payee=line.payee,
            note=line.note,
            reimbursable=line.reimbursable,
            status=status,
            recorded_by=actor.id,
            recorded_at=context.now,
            updated_by=actor.id,
            updated_at=context.now,
        )
        self.stored[entry.id] = entry
        self._log(context, entry, "null", "Recorded", None)
        return self._saved(entry, SaveOutcome.CREATED)

    async def update(self, command: PettyCashUpdate) -> PettyCashSaved:
        context = command.context
        actor = self._enter(context, "edit_own", "edit")
        line = _pc_line(command.line)
        assert line.day is not None and line.unit_amount is not None
        entry = self._entry(command.entry_id, actor)
        if entry.kind != line.kind:
            raise RuleViolation(code="pettycash_kind_change")
        asked = command.line.holder_id
        if asked is not None and asked != entry.holder_id:
            raise RuleViolation(code="pettycash_holder_change")
        if entry.kind != 2:
            raise RuleViolation(code="pettycash_change_cash")
        if entry.sent_back_note is None and (
            entry.entry_date,
            entry.vehicle_id,
            entry.expense_item_id,
            entry.units,
            entry.unit_amount,
            entry.reimbursable,
            entry.payee,
            entry.note,
        ) == (
            line.day,
            line.vehicle_id,
            line.expense_item_id,
            line.units,
            line.unit_amount,
            line.reimbursable,
            line.payee,
            line.note,
        ):
            return self._saved(entry, SaveOutcome.REPLAYED)
        _pc_authorize_change(entry, actor)
        moved = line.day != entry.entry_date
        if moved:
            _pc_check_date(line.day, actor.today)
        self._check_writable(entry.entry_date, actor)
        self._check_writable(line.day, actor)
        self._check_version(entry, command.expected_version, actor)
        self._check_expense(
            line.vehicle_id,
            line.expense_item_id,
            line.day,
            actor,
            moved or line.vehicle_id != entry.vehicle_id,
            moved or line.expense_item_id != entry.expense_item_id,
        )
        if (
            entry.group_id is not None
            and line.vehicle_id != entry.vehicle_id
            and any(
                e.group_id == entry.group_id and e.vehicle_id == line.vehicle_id
                for e in self.stored.values()
            )
        ):
            vehicle = self.setup.vehicles.get(line.vehicle_id) if line.vehicle_id else None
            raise RuleViolation(
                code="expense_purchase_has_vehicle",
                detail={"registration": None if vehicle is None else vehicle.registration},
            )
        if (line.expense_item_id, line.units, line.unit_amount) != (
            entry.expense_item_id,
            entry.units,
            entry.unit_amount,
        ):
            entry.group_id = None
            entry.group_total = None
            entry.group_units = None
            entry.group_unit_amount = None
        before = _pc_snapshot(entry)
        entry.entry_date = line.day
        entry.vehicle_id = line.vehicle_id
        entry.expense_item_id = line.expense_item_id
        entry.units = line.units
        entry.unit_amount = line.unit_amount
        entry.payee = line.payee
        entry.note = line.note
        entry.reimbursable = line.reimbursable
        entry.status = 1
        entry.sent_back_note = None
        entry.reviewed_by = None
        entry.reviewed_at = None
        self._touch(entry, context)
        self._log(context, entry, before, "Changed", None)
        return self._saved(entry, SaveOutcome.SAVED)

    async def approve(self, command: PettyCashDecision) -> PettyCashSaved:
        context = command.context
        actor = self._enter(context, "approve_item")
        entry = self._entry(command.entry_id, actor)
        if entry.status == 2 and entry.reviewed_by == actor.id:
            return self._saved(entry, SaveOutcome.REPLAYED)
        _pc_authorize_review(entry, actor)
        self._check_version(entry, command.expected_version, actor)
        if entry.status != 1:
            raise RuleViolation(code="pettycash_not_waiting")
        if entry.sent_back_note is not None:
            raise RuleViolation(code="pettycash_sent_back")
        self._approve(entry, context)
        return self._saved(entry, SaveOutcome.SAVED)

    async def send_back(self, command: PettyCashDecision) -> PettyCashSaved:
        context = command.context
        actor = self._enter(context, "send_back")
        comment = _pc_trim(command.text)
        entry = self._entry(command.entry_id, actor)
        if (
            entry.status == 1
            and comment is not None
            and entry.sent_back_note == comment
            and entry.reviewed_by == actor.id
        ):
            return self._saved(entry, SaveOutcome.REPLAYED)
        _pc_authorize_review(entry, actor)
        self._check_version(entry, command.expected_version, actor)
        if entry.status != 1:
            raise RuleViolation(code="pettycash_not_waiting")
        if entry.sent_back_note is not None:
            raise RuleViolation(code="pettycash_already_sent_back")
        if comment is None:
            raise RuleViolation(code="pettycash_comment_required")
        if len(comment) > 200:
            raise RuleViolation(code="pettycash_comment_length")
        before = _pc_snapshot(entry)
        entry.sent_back_note = comment
        entry.reviewed_by = actor.id
        entry.reviewed_at = context.now
        self._touch(entry, context)
        self._log(context, entry, before, "Sent back", comment)
        return self._saved(entry, SaveOutcome.SAVED)

    async def reject(self, command: PettyCashDecision) -> PettyCashSaved:
        context = command.context
        actor = self._enter(context, "reject")
        reason = _pc_trim(command.text)
        entry = self._entry(command.entry_id, actor)
        if (
            entry.status == 4
            and reason is not None
            and entry.reject_reason == reason
            and entry.reviewed_by == actor.id
        ):
            return self._saved(entry, SaveOutcome.REPLAYED)
        _pc_authorize_review(entry, actor)
        self._check_version(entry, command.expected_version, actor)
        if entry.status != 1:
            raise RuleViolation(code="pettycash_not_waiting")
        if reason is None:
            raise RuleViolation(code="pettycash_reject_reason_required")
        if len(reason) > 200:
            raise RuleViolation(code="pettycash_decision_reason_length")
        before = _pc_snapshot(entry)
        entry.status = 4
        entry.reject_reason = reason
        entry.sent_back_note = None
        entry.reviewed_by = actor.id
        entry.reviewed_at = context.now
        self._touch(entry, context)
        self._log(context, entry, before, "Rejected", reason)
        return self._saved(entry, SaveOutcome.SAVED)

    async def reopen(self, command: PettyCashDecision) -> PettyCashSaved:
        context = command.context
        actor = self._enter(context, "reopen")
        reason = _pc_trim(command.text)
        entry = self._entry(command.entry_id, actor)
        self._check_writable(entry.entry_date, actor)
        self._check_version(entry, command.expected_version, actor)
        if entry.status not in (2, 4):
            raise RuleViolation(code="pettycash_not_decided")
        if reason is None:
            raise RuleViolation(code="pettycash_reopen_reason_required")
        if len(reason) > 200:
            raise RuleViolation(code="pettycash_decision_reason_length")
        before = _pc_snapshot(entry)
        entry.status = 1
        entry.reject_reason = None
        entry.sent_back_note = None
        entry.reviewed_by = None
        entry.reviewed_at = None
        entry.reopen_reason = reason
        self._touch(entry, context)
        self._log(context, entry, before, "Reopened", reason)
        return self._saved(entry, SaveOutcome.SAVED)

    async def remove(self, command: PettyCashDecision) -> PettyCashSaved:
        context = command.context
        actor = self._enter(context, "delete_own", "delete", "delete_approved", "delete_cash")
        reason = _pc_trim(command.text)
        if reason is not None and len(reason) > 500:
            raise RuleViolation(code="reason_length")
        entry = self._entry(command.entry_id, actor)
        _pc_authorize_remove(entry, actor, reason)
        self._check_writable(entry.entry_date, actor)
        self._check_version(entry, command.expected_version, actor)
        self._guard(entry.holder_id, entry.kind, -_pc_effect(entry), actor)
        before = _pc_snapshot(entry)
        entry.removed_by = actor.id
        entry.removed_at = context.now
        entry.removal_reason = reason
        self._touch(entry, context)
        self._log(context, entry, before, "Removed", reason)
        return self._saved(entry, SaveOutcome.SAVED)

    async def approve_day(self, command: PettyCashDayApproval) -> PettyCashApproved:
        context = command.context
        actor = self._enter(context, "approve_day")
        first = command.day or date.min
        if command.to is None:
            _pc_check_date(first, actor.today)
            last = first
        else:
            _pc_check_period(command.day, command.to, actor.today)
            last = command.to
        self._check_holder(actor, command.holder_id)
        waiting = sorted(
            (
                e
                for e in self._visible(actor)
                if _pc_ready(e)
                and first <= e.entry_date <= last
                and (command.holder_id is None or e.holder_id == command.holder_id)
            ),
            key=lambda e: e.id,
        )
        approved = 0
        total = Decimal(0)
        limit = actor.limit
        for entry in waiting:
            if actor.id in (entry.holder_id, entry.recorded_by) or (
                limit is not None and abs(entry.total) > limit
            ):
                continue
            self._approve(entry, context)
            approved += 1
            total += entry.total
        return PettyCashApproved(approved=approved, total=total, skipped=len(waiting) - approved)

    async def approve_entries(self, command: PettyCashEntriesApproval) -> PettyCashApproved:
        context = command.context
        actor = self._enter(context, "approve_item")
        asked: dict[UUID, int | None] = {}
        for ticked in command.entries:
            asked.setdefault(ticked.id, ticked.version)
        if not asked:
            raise RuleViolation(code="pettycash_approve_none")
        if len(asked) > 100:
            raise RuleViolation(code="pettycash_approve_many")
        chosen = []
        for entry_id, version in asked.items():
            entry = self._entry(entry_id, actor)
            if entry.status == 2:
                continue
            _pc_authorize_review(entry, actor)
            self._check_version(entry, version, actor)
            chosen.append(entry)
        for entry in chosen:
            if entry.status != 1:
                raise RuleViolation(code="pettycash_not_waiting")
            if entry.sent_back_note is not None:
                raise RuleViolation(code="pettycash_sent_back")
        total = Decimal(0)
        for entry in chosen:
            self._approve(entry, context)
            total += entry.total
        return PettyCashApproved(
            approved=len(chosen), total=total, skipped=len(asked) - len(chosen)
        )

    # --- shared ---------------------------------------------------------------------------

    def _holder_for(self, kind: int | None, asked: UUID | None, actor: _PcActor) -> UUID:
        """The float an entry goes to: an expense to the caller's own (or, with spend_other,
        to another keeper's), a credit note to the one named or the caller's, cash to the one
        named."""
        if kind == 2:
            if asked is None or asked == actor.id:
                if not actor.holds("spend"):
                    raise Forbidden(code="pettycash_spend_permission")
                return actor.id
            if not actor.holds("spend_other"):
                if actor.holds("spend"):
                    raise RuleViolation(code="pettycash_own_float_only")
                raise Forbidden(code="pettycash_spend_permission")
            holder = asked
        elif kind == 3:
            if not actor.holds("credit"):
                raise Forbidden(code="pettycash_credit_permission")
            holder = actor.id if asked is None else asked
        else:
            if not actor.holds("issue"):
                raise Forbidden(code="pettycash_cash_permission")
            if asked is None:
                raise RuleViolation(code="pettycash_holder_required")
            holder = asked
        if not self._is_holder(holder):
            raise RuleViolation(code="pettycash_holder_not_holder")
        return holder

    def _enter(self, context: TenantContext, *rights: str) -> _PcActor:
        member = self.setup.tenancy._enter(context)
        held = member.held()
        if not any(f"pettycash.{right}" in held for right in rights):
            raise Forbidden(code="permission_missing")
        return self._actor(context, member)

    def _actor(self, context: TenantContext, member: FakeMember) -> _PcActor:
        today = self.setup.tenancy._today(context)
        if member.scope_mode == "all":
            vehicles = frozenset(self.setup.vehicles)
        elif member.scope_mode == "companies":
            vehicles = frozenset(
                v.id for v in self.setup.vehicles.values() if v.company_id in member.company_ids
            )
        else:
            vehicles = frozenset(v for v in member.vehicle_ids if v in self.setup.vehicles)
        earliest = earliest_writable(
            member.back_limit_mode, member.back_limit_count, member.back_limit_from, today
        )
        return _PcActor(member, member.held(), vehicles, today, earliest)

    def _week_start(self, day: date) -> date:
        first_day = self.setup.tenancy.sections["localization"]["first_day_of_week"]
        return day - timedelta(days=((day.isoweekday() % 7) - first_day + 7) % 7)

    def _name(self, user_id: UUID | None) -> str | None:
        member = None if user_id is None else self.setup.tenancy.members.get(user_id)
        return None if member is None else f"{member.first_name} {member.last_name}".strip(" ")

    def _is_holder(self, user_id: UUID) -> bool:
        member = self.setup.tenancy.members.get(user_id)
        return member is not None and member.active and "pettycash.spend" in member.held()

    def _holders(self) -> list[PettyCashHolder]:
        rows = []
        for member in self.setup.tenancy.members.values():
            active = self._is_holder(member.user_id)
            if active or any(
                e.holder_id == member.user_id and e.removed_at is None for e in self.stored.values()
            ):
                rows.append(
                    PettyCashHolder(member.user_id, self._name(member.user_id) or "", active)
                )
        return sorted(rows, key=lambda h: (h.name.upper(), h.id))

    def _visible_holders(self, actor: _PcActor) -> list[PettyCashHolder]:
        return [h for h in self._holders() if actor.view_all or h.id == actor.id]

    def _check_holder(self, actor: _PcActor, holder_id: UUID | None) -> None:
        if holder_id is not None and all(h.id != holder_id for h in self._visible_holders(actor)):
            raise NotFound(code="not_found")

    def _visible(self, actor: _PcActor) -> list[FakePettyCashEntry]:
        return [e for e in self.stored.values() if _pc_visible(e, actor)]

    def _entry(self, entry_id: UUID, actor: _PcActor) -> FakePettyCashEntry:
        entry = self.stored.get(entry_id)
        if entry is None or not _pc_visible(entry, actor):
            raise NotFound(code="not_found")
        return entry

    def _balance(self, holder_id: UUID) -> Decimal:
        return _pc_sum(
            _pc_effect(e)
            for e in self.stored.values()
            if e.holder_id == holder_id and e.removed_at is None
        )

    def _guard(self, holder_id: UUID, kind: int, delta: Decimal, actor: _PcActor) -> None:
        if kind != 1 or delta >= 0:
            return
        after = self._balance(holder_id) + delta
        if after < 0 and "pettycash.issue_negative" not in actor.held:
            raise RuleViolation(code="pettycash_below_zero", detail={"balance_after": after})

    def _check_writable(self, day: date, actor: _PcActor) -> None:
        if actor.earliest is not None and day < actor.earliest:
            raise RuleViolation(
                code="record_too_old", detail={"earliest": actor.earliest.isoformat()}
            )

    def _check_expense(
        self,
        vehicle_id: UUID | None,
        item_id: UUID | None,
        day: date,
        actor: _PcActor,
        check_vehicle: bool,
        check_item: bool,
    ) -> None:
        if check_vehicle:
            if vehicle_id is None or vehicle_id not in actor.vehicles:
                raise RuleViolation(code="pettycash_vehicle_scope")
            if not _revenue_active(self.setup.vehicles[vehicle_id], day):
                raise RuleViolation(code="pettycash_vehicle_inactive")
        if check_item:
            item = None if item_id is None else self.setup.items.get(item_id)
            category = None if item is None else self.setup.categories.get(item.category_id)
            if (
                item is None
                or category is None
                or not _in_use(item.stopped_on, day)
                or not _in_use(category.stopped_on, day)
            ):
                raise RuleViolation(code="pettycash_item_inactive")

    def _check_version(
        self, entry: FakePettyCashEntry, expected: int | None, actor: _PcActor
    ) -> None:
        if expected != entry.version:
            current = dataclasses.asdict(self._document(entry, actor))
            raise Conflict(code="pettycash_entry_changed", detail={"current": current})

    def _approve(self, entry: FakePettyCashEntry, context: TenantContext) -> None:
        before = _pc_snapshot(entry)
        entry.status = 2
        entry.reviewed_by = context.actor_id
        entry.reviewed_at = context.now
        self._touch(entry, context)
        self._log(context, entry, before, "Approved", None)

    def _touch(self, entry: FakePettyCashEntry, context: TenantContext) -> None:
        entry.updated_by = context.actor_id
        entry.updated_at = context.now
        entry.version += 1

    def _log(
        self,
        context: TenantContext,
        entry: FakePettyCashEntry,
        before: str,
        verb: str,
        typed: str | None,
    ) -> None:
        reason = _pc_compose(f"{verb} {self._describe(entry)}", typed)
        self.setup._log(context, "pettycash", entry.id, before, _pc_snapshot(entry), reason)

    def _describe(self, entry: FakePettyCashEntry) -> str:
        holder = self._name(entry.holder_id) or "someone"
        if entry.kind == 2:
            vehicle = self.setup.vehicles.get(entry.vehicle_id) if entry.vehicle_id else None
            where = "a vehicle" if vehicle is None else vehicle.registration
            return f"{holder}'s petty cash spending on {where} for {_day_words(entry.entry_date)}"
        if entry.kind == 3:
            if entry.payee is not None:
                return f"{holder}'s petty cash credit note paying {entry.payee}"
            if entry.note is not None:
                return f"{holder}'s petty cash credit note, {entry.note}"
            return f"{holder}'s petty cash credit note"
        if entry.total < 0:
            return f"petty cash taken back from {holder}"
        return f"petty cash given to {holder}"

    def _saved(self, entry: FakePettyCashEntry, outcome: SaveOutcome) -> PettyCashSaved:
        return PettyCashSaved(
            id=entry.id,
            version=entry.version,
            status=_pc_status_word(entry),
            balance=self._balance(entry.holder_id),
            outcome=outcome,
        )

    def _float_row(self, holder: PettyCashHolder, seen: list[FakePettyCashEntry]) -> PettyCashFloat:
        cash = _pc_sum(e.total for e in seen if e.kind == 1)
        credit = _pc_sum(e.total for e in seen if e.kind == 3)
        spent = _pc_sum(e.total for e in seen if e.kind == 2 and e.status != 4)
        waiting = [e for e in seen if _pc_ready(e)]
        given = [e.entry_date for e in seen if e.kind == 1]
        return PettyCashFloat(
            holder_id=holder.id,
            name=holder.name,
            active=holder.active,
            cash_received=cash,
            credit_notes=credit,
            expenses=spent,
            waiting=_pc_sum(e.total for e in waiting),
            waiting_count=len(waiting),
            approved=_pc_sum(e.total for e in seen if e.kind == 2 and e.status == 2),
            sent_back=_pc_sum(
                e.total
                for e in seen
                if e.kind == 2 and e.status == 1 and e.sent_back_note is not None
            ),
            balance=cash - credit - spent,
            last_cash_on=max(given) if given else None,
            rejected=_pc_sum(e.total for e in seen if e.kind == 2 and e.status == 4),
        )

    def _document(self, entry: FakePettyCashEntry, actor: _PcActor) -> PettyCashEntry:
        vehicle = self.setup.vehicles.get(entry.vehicle_id) if entry.vehicle_id else None
        item = self.setup.items.get(entry.expense_item_id) if entry.expense_item_id else None
        category = None if item is None else self.setup.categories.get(item.category_id)
        flags = _pc_flags(entry, actor)
        status = _pc_status_word(entry)
        return PettyCashEntry(
            id=entry.id,
            kind=EntryKind(_PC_KIND_WORDS[entry.kind]),
            holder_id=entry.holder_id,
            holder_name=self._name(entry.holder_id) or "",
            entry_date=entry.entry_date,
            vehicle_id=entry.vehicle_id,
            registration=None if vehicle is None else vehicle.registration,
            expense_item_id=entry.expense_item_id,
            expense_item_name=None if item is None else item.name,
            bucket=None if category is None else _pc_bucket(category),
            units=entry.units,
            unit_amount=entry.unit_amount,
            total=entry.total,
            payee=entry.payee,
            note=entry.note,
            reimbursable=entry.reimbursable,
            status=None if status is None else EntryState(status),
            sent_back_note=entry.sent_back_note,
            reviewed_by_name=self._name(entry.reviewed_by),
            reviewed_at=entry.reviewed_at,
            recorded_by_name=self._name(entry.recorded_by) or "",
            recorded_at=entry.recorded_at,
            updated_at=entry.updated_at,
            version=entry.version,
            can_edit=flags.can_edit,
            can_remove=flags.can_remove,
            can_review=flags.can_review,
            above_limit=flags.above_limit,
            reject_reason=entry.reject_reason,
            reopen_reason=entry.reopen_reason,
            can_send_back=flags.can_send_back,
            can_reject=flags.can_reject,
            can_reopen=flags.can_reopen,
            group=self._group(entry),
        )

    def _group(self, entry: FakePettyCashEntry) -> PettyCashGroup | None:
        if entry.group_id is None:
            return None
        assert entry.group_total is not None and entry.group_units is not None
        assert entry.group_unit_amount is not None
        size = sum(
            1
            for e in self.stored.values()
            if e.group_id == entry.group_id and e.removed_at is None and e.status != 4
        )
        return PettyCashGroup(
            entry.group_id, size, entry.group_total, entry.group_units, entry.group_unit_amount
        )


_PC_KIND_WORDS = {code: word for word, code in _PC_KINDS.items()}


def _pc_trim(value: str | None) -> str | None:
    """``tenancy.trim_text``: white space trimmed at both ends, blank as none."""
    return None if value is None else value.strip(_PC_BLANKS) or None


def _pc_round(value: Decimal, places: int) -> Decimal:
    return value.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP, context=_PC_WIDE)


def _pc_sum(values: Iterable[Decimal]) -> Decimal:
    return sum(values, Decimal(0))


def _pc_effect_of(kind: int, status: int | None, total: Decimal) -> Decimal:
    """``pettycash.effect``: cash adds, a credit note and an expense take away, a rejected
    expense nothing."""
    if kind == 1:
        return total
    if status == 4:
        return Decimal(0)
    return -total


def _pc_effect(entry: FakePettyCashEntry) -> Decimal:
    return _pc_effect_of(entry.kind, entry.status, entry.total)


def _pc_status_word(entry: FakePettyCashEntry) -> str | None:
    if entry.status == 1:
        return "waiting" if entry.sent_back_note is None else "sentBack"
    return {2: "approved", 4: "rejected"}.get(entry.status or 0)


def _pc_ready(entry: FakePettyCashEntry) -> bool:
    """A waiting expense that is not sent back: what an approver acts on."""
    return entry.kind == 2 and entry.status == 1 and entry.sent_back_note is None


def _pc_bucket(category: FakeCategory) -> ExpenseBucket | None:
    bucket: int | None = category.bucket
    return None if bucket is None else ExpenseBucket(bucket)


def _pc_visible(entry: FakePettyCashEntry, actor: _PcActor) -> bool:
    return entry.removed_at is None and (
        entry.holder_id == actor.id
        or (actor.view_all and (entry.vehicle_id is None or entry.vehicle_id in actor.vehicles))
    )


def _pc_check_date(day: date, today: date) -> None:
    if day > today:
        raise RuleViolation(code="pettycash_future_date")
    if day < today - timedelta(days=3650):
        raise RuleViolation(code="pettycash_too_old")


def _pc_check_period(first: date | None, last: date | None, today: date) -> None:
    if first is None or last is None:
        raise RuleViolation(code="pettycash_range_both")
    if first > last:
        raise RuleViolation(code="history_dates_order")
    if (last - first).days + 1 > 367:
        raise RuleViolation(code="pettycash_range_length")
    if first > today:
        raise RuleViolation(code="pettycash_range_start")
    if first < today - timedelta(days=3650):
        raise RuleViolation(code="pettycash_too_old")


def _pc_line(line: PettyCashLine) -> _PcLine:  # noqa: PLR0912 - check order
    """``pettycash.check_line`` on the line as the routines read it."""
    kind = _PC_KINDS.get(_pc_trim(line.kind) or "")
    units = Decimal(1) if line.units is None else line.units
    vehicle = None if line.vehicle_id == _PC_NO_ID else line.vehicle_id
    item = None if line.expense_item_id == _PC_NO_ID else line.expense_item_id
    payee = _pc_trim(line.payee)
    note = _pc_trim(line.note)
    amount = line.unit_amount
    if kind is None:
        raise RuleViolation(code="pettycash_kind_invalid")
    if line.day is None or line.day == date.min:
        raise RuleViolation(code="pettycash_line_date_required")
    if amount is None or amount == 0:
        raise RuleViolation(code="pettycash_line_amount_zero")
    if amount != _pc_round(amount, 2) or abs(amount) > _PC_LARGEST:
        raise RuleViolation(code="pettycash_line_amount_decimals")
    if units <= 0 or units > Decimal("999999999.999") or units != _pc_round(units, 3):
        raise RuleViolation(code="pettycash_line_units")
    if kind != 2 and units != 1:
        raise RuleViolation(code="pettycash_line_units_only_expense")
    total = _pc_round(units * amount, 2)
    if total == 0:
        raise RuleViolation(code="pettycash_line_total_zero")
    if abs(total) > _PC_LARGEST:
        raise RuleViolation(code="pettycash_line_total_large")
    if note is not None and len(note) > 80:
        raise RuleViolation(code="pettycash_line_note_length")
    if kind == 2:
        if vehicle is None:
            raise RuleViolation(code="pettycash_line_vehicle_required")
        if item is None:
            raise RuleViolation(code="pettycash_line_item_required")
        if payee is not None or line.reimbursable:
            raise RuleViolation(code="pettycash_line_expense_payee")
    elif kind == 3:
        if vehicle is not None or item is not None:
            raise RuleViolation(code="pettycash_line_credit_vehicle")
        if payee is not None and len(payee) > 80:
            raise RuleViolation(code="pettycash_line_payee_length")
    elif vehicle is not None or item is not None or payee is not None or line.reimbursable:
        raise RuleViolation(code="pettycash_line_cash_shape")
    return _PcLine(kind, line.day, amount, units, vehicle, item, payee, note, line.reimbursable)


def _pc_authorize_change(entry: FakePettyCashEntry, actor: _PcActor) -> None:
    if entry.status != 1:
        raise RuleViolation(code="pettycash_change_decided")
    if actor.holds("edit"):
        return
    if entry.holder_id == actor.id:
        if not actor.holds("edit_own"):
            raise Forbidden(code="pettycash_change_own_permission")
        return
    raise Forbidden(code="pettycash_change_other_permission")


def _pc_authorize_remove(entry: FakePettyCashEntry, actor: _PcActor, reason: str | None) -> None:
    if entry.kind != 2:
        if not actor.holds("delete_cash"):
            raise Forbidden(code="pettycash_delete_cash_permission")
        needs_reason = True
    elif entry.status == 4:
        raise RuleViolation(code="pettycash_delete_rejected")
    elif entry.status == 2:
        if not actor.holds("delete_approved"):
            raise Forbidden(code="pettycash_delete_approved_permission")
        needs_reason = True
    else:
        if entry.holder_id == actor.id:
            if not actor.holds("delete_own", "delete"):
                raise Forbidden(code="pettycash_delete_own_permission")
        elif not actor.holds("delete"):
            raise Forbidden(code="pettycash_delete_other_permission")
        needs_reason = False
    if needs_reason and reason is None:
        raise RuleViolation(code="reason_length")


def _pc_authorize_review(entry: FakePettyCashEntry, actor: _PcActor) -> None:
    if entry.kind == 1:
        raise RuleViolation(code="pettycash_cash_not_reviewed")
    if entry.kind == 3:
        raise RuleViolation(code="pettycash_credit_not_reviewed")
    if entry.holder_id == actor.id:
        raise Forbidden(code="pettycash_own_float_review")
    if entry.recorded_by == actor.id:
        raise Forbidden(code="pettycash_own_entry_review")
    if actor.limit is not None and abs(entry.total) > actor.limit:
        raise Forbidden(code="pettycash_above_limit")


@dataclass(frozen=True, slots=True)
class _PcFlags:
    can_edit: bool
    can_remove: bool
    can_review: bool
    above_limit: bool
    can_send_back: bool
    can_reject: bool
    can_reopen: bool


def _pc_flags(entry: FakePettyCashEntry, actor: _PcActor) -> _PcFlags:
    """``pettycash.flags``: what the caller may do with the entry now."""
    expense = entry.kind == 2
    waiting = expense and entry.status == 1
    own = entry.holder_id == actor.id
    within = actor.limit is None or abs(entry.total) <= actor.limit
    writable = actor.earliest is None or entry.entry_date >= actor.earliest
    ready = waiting and entry.sent_back_note is None
    reviewer = not own and entry.recorded_by != actor.id and within
    if not expense:
        removable = actor.holds("delete_cash")
    elif entry.status == 1:
        removable = actor.holds("delete") or (own and actor.holds("delete_own"))
    elif entry.status == 2:
        removable = actor.holds("delete_approved")
    else:
        removable = False
    return _PcFlags(
        can_edit=writable
        and waiting
        and (actor.holds("edit") or (own and actor.holds("edit_own"))),
        can_remove=writable and removable,
        can_review=ready and reviewer and actor.holds("approve_item"),
        above_limit=ready and not within,
        can_send_back=ready and reviewer and actor.holds("send_back"),
        can_reject=waiting and reviewer and actor.holds("reject"),
        can_reopen=writable and expense and entry.status in (2, 4) and actor.holds("reopen"),
    )


def _pc_compose(automatic: str, typed: str | None) -> str:
    """``tenancy.compose_reason``: the typed reason after the automatic words, within 500
    characters, the automatic words giving way first but keeping 100."""
    if not typed:
        return automatic if len(automatic) <= 500 else automatic[:497] + "..."
    suffix = f". Reason: {typed}" + ("" if typed[-1] in ".!?" else ".")
    if len(automatic) + len(suffix) > 500:
        room = max(500 - len(suffix), 100)
        if len(automatic) > room:
            automatic = automatic[: room - 3] + "..."
    result = automatic + suffix
    return result if len(result) <= 500 else result[:497] + "..."


def _pc_snapshot(entry: FakePettyCashEntry) -> str:
    """``pettycash.entry_snapshot``."""

    def instant(moment: datetime | None) -> str | None:
        return None if moment is None else _instant_text(moment)

    def text(value: UUID | None) -> str | None:
        return None if value is None else str(value)

    return _compact(
        {
            "Id": str(entry.id),
            "HolderId": str(entry.holder_id),
            "Kind": _PC_KIND_WORDS[entry.kind].capitalize(),
            "Date": entry.entry_date.isoformat(),
            "VehicleId": text(entry.vehicle_id),
            "ExpenseItemId": text(entry.expense_item_id),
            "Units": _number(entry.units),
            "UnitAmount": _number(entry.unit_amount),
            "Total": _number(entry.total),
            "Payee": entry.payee,
            "Note": entry.note,
            "Reimbursable": entry.reimbursable,
            "Status": {1: "Waiting", 2: "Approved", 4: "Rejected"}.get(entry.status or 0),
            "SentBackNote": entry.sent_back_note,
            "RejectReason": entry.reject_reason,
            "ReopenReason": entry.reopen_reason,
            "ReviewedBy": text(entry.reviewed_by),
            "ReviewedAt": instant(entry.reviewed_at),
            "RecordedBy": str(entry.recorded_by),
            "RecordedAt": instant(entry.recorded_at),
            "UpdatedBy": str(entry.updated_by),
            "UpdatedAt": instant(entry.updated_at),
            "RemovedBy": text(entry.removed_by),
            "RemovedAt": instant(entry.removed_at),
            "RemovalReason": entry.removal_reason,
            "Version": entry.version,
        }
    )


# --- central expenses ----------------------------------------------------------------------


@dataclass(slots=True)
class FakeCentralExpense:
    id: UUID
    entry_date: date
    vehicle_id: UUID
    expense_item_id: UUID
    units: Decimal
    unit_amount: Decimal
    note: str | None
    group_id: UUID
    group_size: int
    group_total: Decimal
    group_units: Decimal
    group_unit_amount: Decimal
    recorded_by: UUID
    recorded_at: datetime
    updated_by: UUID
    updated_at: datetime
    removed_by: UUID | None = None
    removed_at: datetime | None = None
    removal_reason: str | None = None
    version: int = 1

    @property
    def total(self) -> Decimal:
        return _pc_round(self.units * self.unit_amount, 2)


_EXPENSE_SOURCES = {"central": 1, "pettycash": 2, "scheduled": 3}


class FakeExpensesRepository:
    """In-memory ``ExpensesRepository`` over the organization of a ``FakeSetupRepository``
    (members, scope, fleet, catalogue, scheduled items, settings and change log) and, when
    given, the approved expenses of a ``FakePettyCashRepository``.

    ``tests/db/test_fakes_match_routines.py`` runs ``tests/support/expenses_cases.py`` against
    this fake and the real routines: the purchase checks in order, the split into rows, the
    retried purchase, the change and remove steps with the group detachment, the version
    conflict with ``current``, the reasons and snapshots, and the ledger and options that show
    the result. No two saves race."""

    def __init__(
        self,
        setup: FakeSetupRepository | None = None,
        pettycash: FakePettyCashRepository | None = None,
    ) -> None:
        self.setup = setup or FakeSetupRepository()
        self.pettycash = pettycash
        self.stored: dict[UUID, FakeCentralExpense] = {}

    # --- reads ----------------------------------------------------------------------------

    async def ledger(self, query: ExpenseLedgerQuery) -> ExpenseLedger:
        actor = self._enter(query.context, "expenses.view")
        if not (1 <= query.page <= 100000 and 1 <= query.page_size <= 100):
            raise RuleViolation(code="page_out_of_range")
        source = _expense_check_ledger(query.from_date, query.to_date, query.source, query.q)
        assert query.from_date is not None and query.to_date is not None
        rows = self._rows(actor, query.from_date, query.to_date)
        matched = [r for r in rows if _expense_matches(r, source, _pc_trim(query.q))]
        matched.sort(key=_expense_order)
        start = (query.page - 1) * query.page_size
        return ExpenseLedger(
            business_date=actor.today,
            from_date=query.from_date,
            to_date=query.to_date,
            permissions=ExpensePermissions(can_record=actor.capture, can_correct=actor.correct),
            figures=ExpenseFigures(
                total=_pc_sum(r.total for r, _ in rows),
                central=_pc_sum(r.total for r, _ in rows if r.source is ExpenseSource.CENTRAL),
                petty_cash=_pc_sum(
                    r.total for r, _ in rows if r.source is ExpenseSource.PETTY_CASH
                ),
                scheduled=_pc_sum(r.total for r, _ in rows if r.source is ExpenseSource.SCHEDULED),
            ),
            items=tuple(r for r, _ in matched[start : start + query.page_size]),
            page_number=query.page,
            page_size=query.page_size,
            total=len(matched),
            amount=_pc_sum(r.total for r, _ in matched),
        )

    async def options(self, query: ExpenseOptionsQuery) -> ExpenseOptions:
        actor = self._enter(query.context, "expenses.capture", "expenses.correct")
        day = query.day or actor.today
        _expense_check_date(day, actor.today)
        vehicles = tuple(
            ExpenseVehicleOption(
                id=v.id,
                company_id=v.company_id,
                company_name=self.setup.companies[v.company_id].name,
                registration=v.registration,
                active=True,
                fleet_number=v.fleet_number,
            )
            for v in sorted(self.setup.vehicles.values(), key=lambda v: (v.registration, v.id))
            if v.id in actor.vehicles and _revenue_active(v, day)
        )
        listed = []
        for item in self.setup.items.values():
            category = self.setup.categories[item.category_id]
            if _in_use(item.stopped_on, day) and _in_use(category.stopped_on, day):
                listed.append((category.name, item.name, item.id, category))
        items = tuple(
            ExpenseItemOption(
                id=item_id,
                name=name,
                category_id=category.id,
                category_name=category.name,
                bucket=ExpenseBucket(category.bucket or 2),
                main_category_name=self._main_name(category),
            )
            for _, name, item_id, category in sorted(listed, key=lambda r: r[:3])
        )
        return ExpenseOptions(vehicles=vehicles, items=items)

    # --- writes ---------------------------------------------------------------------------

    async def record(self, command: ExpensePurchase) -> ExpenseRecorded:
        context = command.context
        actor = self._enter(context, "expenses.capture")
        note = _pc_trim(command.note)
        rows = _expense_check_purchase(
            command.day,
            command.expense_item_id,
            command.units,
            command.unit_amount,
            note,
            command.allocations,
        )
        purchase = None if command.id == _PC_NO_ID else command.id
        if purchase is not None:
            retried = self._retried(purchase, actor.id)
            if retried is not None:
                return retried
        assert command.day is not None and command.expense_item_id is not None
        assert command.units is not None and command.unit_amount is not None
        _expense_check_date(command.day, actor.today)
        self._check_writable(command.day, actor)
        for vehicle_id, _, _ in rows:
            self._check_vehicle(vehicle_id, command.day, actor)
        self._check_item(command.expense_item_id, command.day)
        group = purchase or uuid4()
        total = _pc_round(command.units * command.unit_amount, 2)
        made = []
        for vehicle_id, units, unit_amount in rows:
            row = FakeCentralExpense(
                id=group if len(rows) == 1 else uuid4(),
                entry_date=command.day,
                vehicle_id=vehicle_id,
                expense_item_id=command.expense_item_id,
                units=units,
                unit_amount=unit_amount,
                note=note,
                group_id=group,
                group_size=len(rows),
                group_total=total,
                group_units=command.units,
                group_unit_amount=command.unit_amount,
                recorded_by=actor.id,
                recorded_at=context.now,
                updated_by=actor.id,
                updated_at=context.now,
            )
            self.stored[row.id] = row
            made.append(row)
        for row in made:
            self._log(context, row, "null", "Recorded", None)
        return ExpenseRecorded(ids=tuple(r.id for r in made), total=total)

    async def change(self, command: ExpenseChange) -> ExpenseSaved:
        context = command.context
        actor = self._enter(context, "expenses.capture", "expenses.correct")
        note = _pc_trim(command.note)
        line = _expense_line(
            command.day,
            command.unit_amount,
            command.units,
            command.vehicle_id,
            command.expense_item_id,
            note,
        )
        row = self._row(command.entry_id, actor)
        day, vehicle_id, item_id, units, unit_amount = line
        if (row.entry_date, row.vehicle_id, row.expense_item_id, row.units, row.unit_amount) == (
            day,
            vehicle_id,
            item_id,
            units,
            unit_amount,
        ) and row.note == note:
            return ExpenseSaved(id=row.id, version=row.version)
        moved = day != row.entry_date
        other_vehicle = vehicle_id != row.vehicle_id
        if not actor.correct:
            _expense_authorize(row, actor)
            if moved:
                raise Forbidden(code="expense_change_date")
        self._check_writable(row.entry_date, actor)
        self._check_version(row, command.expected_version, actor)
        if moved:
            _expense_check_date(day, actor.today)
            self._check_writable(day, actor)
        if moved or other_vehicle:
            registration = self._check_vehicle(vehicle_id, day, actor)
            if other_vehicle and any(
                r.group_id == row.group_id and r.vehicle_id == vehicle_id
                for r in self.stored.values()
            ):
                raise RuleViolation(
                    code="expense_purchase_has_vehicle", detail={"registration": registration}
                )
        if moved or item_id != row.expense_item_id:
            self._check_item(item_id, day)
        before = _expense_snapshot(row)
        detach = (
            item_id != row.expense_item_id or units != row.units or unit_amount != row.unit_amount
        )
        row.entry_date = day
        row.vehicle_id = vehicle_id
        row.expense_item_id = item_id
        row.units = units
        row.unit_amount = unit_amount
        row.note = note
        if detach:
            row.group_size = 1
            row.group_total = row.total
            row.group_units = units
            row.group_unit_amount = unit_amount
        self._touch(row, context)
        self._log(context, row, before, "Changed", None)
        return ExpenseSaved(id=row.id, version=row.version)

    async def remove(self, command: ExpenseRemoval) -> ExpenseSaved:
        context = command.context
        actor = self._enter(context, "expenses.capture", "expenses.correct")
        reason = _typed_reason(command.reason)
        if reason is None:
            raise RuleViolation(code="reason_length")
        row = self._row(command.entry_id, actor)
        if not actor.correct:
            _expense_authorize(row, actor)
        self._check_writable(row.entry_date, actor)
        self._check_version(row, command.expected_version, actor)
        before = _expense_snapshot(row)
        row.removed_by = actor.id
        row.removed_at = context.now
        row.removal_reason = reason
        self._touch(row, context)
        self._log(context, row, before, "Removed", reason)
        return ExpenseSaved(id=row.id, version=row.version)

    # --- helpers --------------------------------------------------------------------------

    def _enter(self, context: TenantContext, *rights: str) -> _ExActor:
        member = self.setup.tenancy._enter(context)
        held = member.held()
        if not any(right in held for right in rights):
            raise Forbidden(code="permission_missing")
        today = self.setup.tenancy._today(context)
        if member.scope_mode == "all":
            vehicles = frozenset(self.setup.vehicles)
        elif member.scope_mode == "companies":
            vehicles = frozenset(
                v.id for v in self.setup.vehicles.values() if v.company_id in member.company_ids
            )
        else:
            vehicles = frozenset(v for v in member.vehicle_ids if v in self.setup.vehicles)
        earliest = earliest_writable(
            member.back_limit_mode, member.back_limit_count, member.back_limit_from, today
        )
        return _ExActor(member, held, vehicles, today, earliest)

    def _main_name(self, category: FakeCategory | None) -> str | None:
        if category is None or category.main_category_id is None:
            return None
        main = self.setup.main_categories.get(category.main_category_id)
        return None if main is None else main.name

    def _window(
        self, vehicle: FakeVehicle, first: date, last: date, today: date
    ) -> tuple[date, date]:
        """``setup.report_window``: empty when the first day is after the last."""
        end = min(last, today)
        if vehicle.left_on is not None and vehicle.left_on <= end:
            end = vehicle.left_on - timedelta(days=1)
        return max(first, vehicle.joined_on), end

    def _rows(
        self, actor: _ExActor, first: date, last: date
    ) -> list[tuple[ExpenseLedgerRow, tuple[str, ...]]]:
        """``expenses.ledger_rows``: each row with the texts the search reads."""

        def inside(vehicle_id: UUID | None, day: date) -> bool:
            if vehicle_id is None or vehicle_id not in actor.vehicles:
                return False
            start, end = self._window(self.setup.vehicles[vehicle_id], first, last, actor.today)
            return start <= day <= end

        rows = [
            self._central_row(row, actor)
            for row in self.stored.values()
            if row.removed_at is None and inside(row.vehicle_id, row.entry_date)
        ]
        rows.extend(
            self._petty_row(entry)
            for entry in (self.pettycash.stored.values() if self.pettycash else ())
            if entry.kind == 2
            and entry.status == 2
            and entry.removed_at is None
            and inside(entry.vehicle_id, entry.entry_date)
        )
        for item in self.setup.recurring.values():
            for index, version in enumerate(item.versions):
                if version.kind != 1:
                    continue
                for vehicle_id, amount in version.shares:
                    if vehicle_id not in actor.vehicles:
                        continue
                    vehicle = self.setup.vehicles[vehicle_id]
                    start, end = self._window(vehicle, first, last, actor.today)
                    for day in _version_days(item, index, start, end):
                        rows.append(self._scheduled_row(item, version, vehicle, day, amount))
        return rows

    def _names(self, item_id: UUID | None) -> tuple[str | None, str | None, int | None, str | None]:
        item = None if item_id is None else self.setup.items.get(item_id)
        category = None if item is None else self.setup.categories.get(item.category_id)
        return (
            None if item is None else item.name,
            None if category is None else category.name,
            None if category is None else category.bucket,
            self._main_name(category),
        )

    def _central_row(
        self, row: FakeCentralExpense, actor: _ExActor
    ) -> tuple[ExpenseLedgerRow, tuple[str, ...]]:
        vehicle = self.setup.vehicles[row.vehicle_id]
        item_name, category_name, bucket, main = self._names(row.expense_item_id)
        recorder = self._member_name(row.recorded_by)
        editable = (
            actor.correct
            or (actor.capture and row.recorded_by == actor.id and row.entry_date == actor.today)
        ) and (actor.earliest is None or row.entry_date >= actor.earliest)
        document = ExpenseLedgerRow(
            id=str(row.id),
            source=ExpenseSource.CENTRAL,
            entry_date=row.entry_date,
            vehicle_id=row.vehicle_id,
            registration=vehicle.registration,
            expense_item_id=row.expense_item_id,
            item_name=item_name or "",
            category_name=category_name,
            bucket=ExpenseBucket(bucket or 2),
            units=row.units,
            unit_amount=row.unit_amount,
            total=row.total,
            note=row.note,
            recorded_by_name=recorder,
            holder_name=None,
            schedule_id=None,
            group=None
            if row.group_size <= 1
            else ExpenseGroup(
                row.group_id,
                row.group_size,
                row.group_total,
                row.group_units,
                row.group_unit_amount,
            ),
            version=row.version,
            can_edit=editable,
            can_remove=editable,
            main_category_name=main,
            fleet_number=vehicle.fleet_number,
        )
        texts = (
            vehicle.registration,
            item_name or "",
            category_name or "",
            row.note or "",
            recorder,
        )
        return document, texts

    def _petty_row(self, entry: FakePettyCashEntry) -> tuple[ExpenseLedgerRow, tuple[str, ...]]:
        assert entry.vehicle_id is not None
        vehicle = self.setup.vehicles[entry.vehicle_id]
        item_name, category_name, bucket, main = self._names(entry.expense_item_id)
        holder = self._member_name(entry.holder_id)
        size = None
        if entry.group_id is not None and self.pettycash is not None:
            size = sum(
                1
                for e in self.pettycash.stored.values()
                if e.group_id == entry.group_id and e.removed_at is None and e.status != 4
            )
        document = ExpenseLedgerRow(
            id=str(entry.id),
            source=ExpenseSource.PETTY_CASH,
            entry_date=entry.entry_date,
            vehicle_id=entry.vehicle_id,
            registration=vehicle.registration,
            expense_item_id=entry.expense_item_id,
            item_name=item_name or "",
            category_name=category_name,
            bucket=ExpenseBucket(bucket or 2),
            units=entry.units,
            unit_amount=entry.unit_amount,
            total=entry.total,
            note=entry.note,
            recorded_by_name=self._member_name(entry.recorded_by),
            holder_name=holder,
            schedule_id=None,
            group=None
            if size is None or size <= 1
            else ExpenseGroup(
                entry.group_id,  # type: ignore[arg-type]
                size,
                entry.group_total,  # type: ignore[arg-type]
                entry.group_units,  # type: ignore[arg-type]
                entry.group_unit_amount,  # type: ignore[arg-type]
            ),
            version=None,
            can_edit=False,
            can_remove=False,
            main_category_name=main,
            fleet_number=vehicle.fleet_number,
        )
        texts = (
            vehicle.registration,
            item_name or "",
            category_name or "",
            entry.note or "",
            holder,
        )
        return document, texts

    def _scheduled_row(
        self,
        item: FakeRecurring,
        version: FakeVersion,
        vehicle: FakeVehicle,
        day: date,
        amount: Decimal,
    ) -> tuple[ExpenseLedgerRow, tuple[str, ...]]:
        _, category_name, _, main = self._names(version.expense_item_id)
        document = ExpenseLedgerRow(
            id=f"{item.id}:{day.isoformat()}:{vehicle.id}",
            source=ExpenseSource.SCHEDULED,
            entry_date=day,
            vehicle_id=vehicle.id,
            registration=vehicle.registration,
            expense_item_id=version.expense_item_id,
            item_name=version.name,
            category_name=category_name,
            bucket=ExpenseBucket(version.bucket or 2),
            units=Decimal(1),
            unit_amount=amount,
            total=amount,
            note=version.note,
            recorded_by_name=None,
            holder_name=None,
            schedule_id=item.id,
            group=None,
            version=None,
            can_edit=False,
            can_remove=False,
            main_category_name=main,
            fleet_number=vehicle.fleet_number,
        )
        texts = (vehicle.registration, version.name, category_name or "", version.note or "")
        return document, texts

    def _member_name(self, user_id: UUID) -> str:
        member = self.setup.tenancy.members.get(user_id)
        return "" if member is None else f"{member.first_name} {member.last_name}".strip(" ")

    def _retried(self, purchase: UUID, actor_id: UUID) -> ExpenseRecorded | None:
        rows = sorted(
            (r for r in self.stored.values() if purchase in (r.group_id, r.id)),
            key=lambda r: r.id,
        )
        if not rows:
            return None
        if any(r.group_id != purchase or r.recorded_by != actor_id for r in rows):
            raise Conflict(code="expense_saved_by_other")
        return ExpenseRecorded(ids=tuple(r.id for r in rows), total=rows[0].group_total)

    def _row(self, row_id: UUID, actor: _ExActor) -> FakeCentralExpense:
        row = self.stored.get(row_id)
        if row is None or row.removed_at is not None or row.vehicle_id not in actor.vehicles:
            raise NotFound(code="not_found")
        return row

    def _check_writable(self, day: date, actor: _ExActor) -> None:
        if actor.earliest is not None and day < actor.earliest:
            raise RuleViolation(
                code="record_too_old", detail={"earliest": actor.earliest.isoformat()}
            )

    def _check_vehicle(self, vehicle_id: UUID, day: date, actor: _ExActor) -> str:
        vehicle = self.setup.vehicles.get(vehicle_id)
        if vehicle is None or vehicle_id not in actor.vehicles:
            raise RuleViolation(code="expense_vehicle_not_yours")
        if not _revenue_active(vehicle, day):
            raise RuleViolation(
                code="expense_vehicle_inactive", detail={"registration": vehicle.registration}
            )
        return vehicle.registration

    def _check_item(self, item_id: UUID, day: date) -> None:
        item = self.setup.items.get(item_id)
        category = None if item is None else self.setup.categories.get(item.category_id)
        if (
            item is None
            or category is None
            or not _in_use(item.stopped_on, day)
            or not _in_use(category.stopped_on, day)
        ):
            raise RuleViolation(code="expense_item_not_in_use")

    def _check_version(
        self, row: FakeCentralExpense, expected: int | None, actor: _ExActor
    ) -> None:
        if expected is None:
            raise RuleViolation(code="expense_version_required")
        if expected != row.version:
            vehicle = self.setup.vehicles[row.vehicle_id]
            start, end = self._window(vehicle, row.entry_date, row.entry_date, actor.today)
            current = None
            if start <= row.entry_date <= end:
                current = dataclasses.asdict(self._central_row(row, actor)[0])
            raise Conflict(code="expense_version_conflict", detail={"current": current})

    def _touch(self, row: FakeCentralExpense, context: TenantContext) -> None:
        row.updated_by = context.actor_id
        row.updated_at = context.now
        row.version += 1

    def _log(
        self,
        context: TenantContext,
        row: FakeCentralExpense,
        before: str,
        verb: str,
        typed: str | None,
    ) -> None:
        vehicle = self.setup.vehicles[row.vehicle_id]
        item = self.setup.items[row.expense_item_id]
        currency = self.setup.tenancy.sections["localization"]["currency"]
        subject = (
            f"central expense on {vehicle.registration} for {_day_words(row.entry_date)}: "
            f"{item.name}, {currency} {_formatted(row.total)}"
        )
        reason = _pc_compose(f"{verb} {subject}", typed)
        self.setup._log(context, "centralexpenses", row.id, before, _expense_snapshot(row), reason)


@dataclass(frozen=True, slots=True)
class _ExActor:
    member: FakeMember
    held: tuple[str, ...]
    vehicles: frozenset[UUID]
    today: date
    earliest: date | None

    @property
    def id(self) -> UUID:
        return self.member.user_id

    @property
    def capture(self) -> bool:
        return "expenses.capture" in self.held

    @property
    def correct(self) -> bool:
        return "expenses.correct" in self.held


def _expense_check_date(day: date, today: date) -> None:
    if day > today:
        raise RuleViolation(code="expense_date_future")
    if day < today - timedelta(days=3650):
        raise RuleViolation(code="expense_date_too_old")


def _expense_check_ledger(
    first: date | None, last: date | None, source: str | None, q: str | None
) -> int | None:
    """``expenses.check_ledger``; the source's order (NULL for all)."""
    word = (_pc_trim(source) or "").lower() or None
    if first is None or last is None:
        raise RuleViolation(code="expense_period_required")
    if first > last:
        raise RuleViolation(code="expense_period_order")
    if (last - first).days > 366:
        raise RuleViolation(code="expense_period_length")
    if word is not None and word not in _EXPENSE_SOURCES:
        raise RuleViolation(code="expense_source_invalid")
    text = _pc_trim(q)
    if text is not None and len(text) > 200:
        raise RuleViolation(code="expense_search_length")
    return None if word is None else _EXPENSE_SOURCES[word]


def _expense_matches(
    row: tuple[ExpenseLedgerRow, tuple[str, ...]], source: int | None, q: str | None
) -> bool:
    document, texts = row
    if source is not None and _EXPENSE_SOURCES[document.source.value] != source:
        return False
    return q is None or any(q.casefold() in text.casefold() for text in texts)


def _expense_order(row: tuple[ExpenseLedgerRow, tuple[str, ...]]) -> tuple[Any, ...]:
    document = row[0]
    return (
        -document.entry_date.toordinal(),
        _EXPENSE_SOURCES[document.source.value],
        document.registration.encode(),
        document.id.encode(),
    )


def _expense_line(
    day: date | None,
    unit_amount: Decimal | None,
    units: Decimal | None,
    vehicle_id: UUID | None,
    item_id: UUID | None,
    note: str | None,
) -> tuple[date, UUID, UUID, Decimal, Decimal]:
    """``pettycash.check_line`` of an expense line (units are required here)."""
    line = _pc_line(
        PettyCashLine(
            "expense",
            day,
            unit_amount,
            None,
            vehicle_id,
            item_id,
            Decimal(0) if units is None else units,
            None,
            note,
            False,
        )
    )
    assert line.day is not None and line.vehicle_id is not None and line.expense_item_id is not None
    assert line.unit_amount is not None
    return line.day, line.vehicle_id, line.expense_item_id, line.units, line.unit_amount


def _expense_check_purchase(
    day: date | None,
    item_id: UUID | None,
    units: Decimal | None,
    unit_amount: Decimal | None,
    note: str | None,
    allocations: tuple[ExpenseAllocation, ...] | None,
) -> list[tuple[UUID, Decimal, Decimal]]:
    """``expenses.check_purchase``: the rows of a purchase, in the order sent."""
    vehicles = [a.vehicle_id for a in allocations or ()]
    if (
        allocations is None
        or not 1 <= len(allocations) <= 50
        or any(v is None or v == _PC_NO_ID for v in vehicles)
        or len(set(vehicles)) != len(vehicles)
    ):
        raise RuleViolation(code="expense_vehicles_invalid")
    _expense_line(day, unit_amount, units, vehicles[0], item_id, note)
    assert units is not None and unit_amount is not None
    amounts = [a.amount for a in allocations]
    if any(a is None or a == 0 or a != _pc_round(a, 2) for a in amounts):
        raise RuleViolation(code="expense_allocation_amount")
    total = _pc_round(units * unit_amount, 2)
    exact = [a for a in amounts if a is not None]
    if any((a > 0) != (total > 0) for a in exact):
        raise RuleViolation(code="expense_allocation_sign")
    if _pc_sum(exact) != total:
        raise RuleViolation(code="expense_allocation_sum")
    ids = [v for v in vehicles if v is not None]
    if len(ids) == 1:
        return [(ids[0], units, unit_amount)]
    share = units / len(ids)
    if (
        len(set(exact)) == 1
        and share == _pc_round(share, 3)
        and _pc_round(_pc_round(share, 3) * unit_amount, 2) == exact[0]
    ):
        return [(v, _pc_round(share, 3), unit_amount) for v in ids]
    return [(v, Decimal(1), a) for v, a in zip(ids, exact, strict=True)]


def _expense_authorize(row: FakeCentralExpense, actor: _ExActor) -> None:
    """Capture alone: only the actor's own row of the business date."""
    if row.recorded_by != actor.id:
        raise Forbidden(code="expense_change_other")
    if row.entry_date != actor.today:
        raise Forbidden(code="expense_change_earlier_day")


def _expense_snapshot(row: FakeCentralExpense) -> str:
    """``expenses.entry_snapshot``."""

    def instant(moment: datetime | None) -> str | None:
        return None if moment is None else _instant_text(moment)

    return _compact(
        {
            "Id": str(row.id),
            "Date": row.entry_date.isoformat(),
            "VehicleId": str(row.vehicle_id),
            "ExpenseItemId": str(row.expense_item_id),
            "Units": _number(row.units),
            "UnitAmount": _number(row.unit_amount),
            "Total": _number(row.total),
            "Note": row.note,
            "GroupId": str(row.group_id),
            "GroupSize": row.group_size,
            "GroupTotal": _number(row.group_total),
            "GroupUnits": _number(row.group_units),
            "GroupUnitAmount": _number(row.group_unit_amount),
            "RecordedBy": str(row.recorded_by),
            "RecordedAt": instant(row.recorded_at),
            "UpdatedBy": str(row.updated_by),
            "UpdatedAt": instant(row.updated_at),
            "RemovedBy": None if row.removed_by is None else str(row.removed_by),
            "RemovedAt": instant(row.removed_at),
            "RemovalReason": row.removal_reason,
            "Version": row.version,
        }
    )


# --- reports: the catalogue, two builders, the exports' log ------------------------------

_FLEET_REPORTS = ("net", "target", "moneyOut", "gaps", "savings")
_PETTYCASH_REPORTS = (
    "cashBook",
    "managers",
    "vehicles",
    "items",
    "waiting",
    "sentBack",
    "rejected",
)
_REPORT_TITLES = {
    "net": "Net by vehicle",
    "target": "Revenue against target",
    "moneyOut": "Money out",
    "gaps": "Capture gaps",
    "savings": "Savings",
    "investment": "Investment",
    "cashBook": "Cash book",
    "managers": "By manager",
    "vehicles": "By vehicle",
    "items": "By item",
    "waiting": "Waiting for approval",
    "sentBack": "Sent back",
    "rejected": "Rejected and reopened",
}
_XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@dataclass(frozen=True, slots=True)
class _FakeTable:
    """A whole report before search and paging, as ``reports.build`` answers it."""

    group: str
    report: str
    title: str
    from_date: date | None
    to_date: date | None
    business_date: date
    headline: ReportFigure
    figures: tuple[ReportFigure, ...]
    columns: tuple[ReportColumn, ...]
    rows: tuple[tuple[Any, ...], ...]


def _rp_column(key: str, label: str, kind: str, total: bool = False) -> ReportColumn:
    return ReportColumn(key, label, CellKind(kind), total)


def _rp_figure(label: str, value: Decimal | int, kind: str) -> ReportFigure:
    return ReportFigure(label, Decimal(value), CellKind(kind))


def _rp_cell_text(cell: Any, kind: CellKind) -> str | None:
    """``reports.cell_text``: what a cell shows, for the search."""
    if cell is None:
        return None
    if isinstance(cell, Decimal | int) and not isinstance(cell, bool):
        amount = Decimal(cell)
        plain = format(amount, "f")
        if "." in plain:
            plain = plain.rstrip("0").rstrip(".")
        return f"{plain} {_formatted(amount)}"
    text = str(cell)
    if kind == CellKind.DATE:
        return f"{text} {_day_words(date.fromisoformat(text))}"
    return text


def _rp_matching(table: _FakeTable, q: str | None) -> list[tuple[Any, ...]]:
    if q is None:
        return list(table.rows)
    words = q.lower().split()
    kept = []
    for row in table.rows:
        shown = " | ".join(
            text
            for text in (
                _rp_cell_text(cell, column.kind)
                for cell, column in zip(row, table.columns, strict=False)
            )
            if text is not None
        ).lower()
        if all(word in shown for word in words):
            kept.append(row)
    return kept


def _rp_totals(
    columns: tuple[ReportColumn, ...], rows: list[tuple[Any, ...]]
) -> tuple[Decimal | None, ...]:
    totals: list[Decimal | None] = []
    for index, column in enumerate(columns):
        if not column.sum:
            totals.append(None)
            continue
        total = Decimal(0)
        for row in rows:
            cell = row[index] if index < len(row) else None
            if isinstance(cell, Decimal | int) and not isinstance(cell, bool):
                total += Decimal(cell)
        totals.append(total)
    return tuple(totals)


def _rp_period(first: date | None, last: date | None, today: date) -> tuple[date, date]:
    if first is None or last is None:
        raise RuleViolation(code="report_period_both")
    if first > last:
        raise RuleViolation(code="report_period_order")
    if (last - first).days + 1 > 367:
        raise RuleViolation(code="report_period_length")
    if first > today:
        raise RuleViolation(code="report_period_future")
    return first, min(last, today)


def _rp_format(text: str | None) -> str:
    word = (_pc_trim(text) or "xlsx").lower()
    if word not in ("xlsx", "pdf"):
        raise RuleViolation(code="export_format_invalid")
    return word


def _rp_search(text: str | None) -> str | None:
    trimmed = _pc_trim(text)
    if trimmed is not None and len(trimmed) > 200:
        raise RuleViolation(code="report_search_length")
    return trimmed


def _rp_period_words(first: date | None, last: date | None) -> str | None:
    if first is None or last is None:
        return None
    if first == last:
        return _day_words(first)
    return f"{_day_words(first)} to {_day_words(last)}"


def _rp_jsonb_order(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Keys as jsonb stores them: by length, then by bytes."""
    return dict(sorted(snapshot.items(), key=lambda kv: (len(kv[0]), kv[0].encode())))


class FakeReportsRepository:
    """In-memory ``ReportsRepository`` over the fleet of a ``FakeSetupRepository`` and the
    records of the ``FakeRevenueRepository`` sharing it.

    ``tests/db/test_fakes_match_routines.py`` runs ``tests/support/reports_cases.py`` against
    this fake and the real routines. The catalogue, the rights, the page, search and period
    checks, the search over what the cells show, the paging and the footer, the Net by vehicle
    and Capture gaps builders (the setup fake posts no money out, so net is the revenue and the
    net table has no main-category columns) and the exports' document and audit row with the
    10,000-row cap are real. Every other builder answers an empty table with its title and no
    columns, and the three screen exports an empty document, so the parity cases keep to the
    builders above."""

    def __init__(
        self,
        setup: FakeSetupRepository | None = None,
        revenue: FakeRevenueRepository | None = None,
    ) -> None:
        self.setup = setup or FakeSetupRepository()
        self.revenue = revenue or FakeRevenueRepository(self.setup)

    async def access(self, context: TenantContext) -> ReportsAccess:
        member = self.setup._enter(context, "reports.view")
        today = self.setup._today(context)
        held = member.permissions
        petty = "pettycash.reports" in held
        fleet = (*_FLEET_REPORTS, "investment") if "reports.investment" in held else _FLEET_REPORTS
        localization = self.setup.tenancy.sections["localization"]
        return ReportsAccess(
            business_date=today,
            first_day_of_week=int(localization["first_day_of_week"]),
            fleet=fleet,
            petty_cash=_PETTYCASH_REPORTS if petty else (),
            holders=tuple(self._holders(member)) if petty else (),
            can_export="reports.export" in held,
        )

    async def report(self, query: ReportQuery) -> ReportTable:
        member = self.setup._enter(query.context, "reports.view")
        page, size = query.page or 0, query.page_size or 0
        if not (1 <= page <= 100_000 and 1 <= size <= 100):
            raise RuleViolation(code="page_out_of_range")
        q = _rp_search(query.q)
        today = self.setup._today(query.context)
        table = self._build(member, query, today)
        rows = _rp_matching(table, q)
        return ReportTable(
            group=table.group,
            report=table.report,
            title=table.title,
            from_date=table.from_date,
            to_date=table.to_date,
            business_date=table.business_date,
            headline=table.headline,
            figures=table.figures,
            columns=table.columns,
            rows=tuple(rows[(page - 1) * size : page * size]),
            page_number=page,
            page_size=size,
            total=len(rows),
            totals=_rp_totals(table.columns, rows),
        )

    async def export_report(self, query: ReportExportQuery) -> ReportDocument:
        member = self.setup._enter(query.context, "reports.export")
        if "reports.view" not in member.permissions:
            raise Forbidden(code="permission_missing")
        word = _rp_format(query.format)
        q = _rp_search(query.q)
        today = self.setup._today(query.context)
        table = self._build(member, query, today)
        rows = _rp_matching(table, q)
        self._cap(len(rows))
        if query.group == "pettycash":
            names = {h.id: h.name for h in self._holders(member)}
            filters = names.get(query.holder_id, "All floats") if query.holder_id else "All floats"
        else:
            company = self.setup.companies.get(query.company_id) if query.company_id else None
            filters = company.name if company is not None else "All companies"
        snapshot = {
            "group": query.group,
            "report": query.report,
            "from": None if table.from_date is None else table.from_date.isoformat(),
            "to": None if table.to_date is None else table.to_date.isoformat(),
            "holderId": None if query.holder_id is None else str(query.holder_id),
            "companyId": None if query.company_id is None else str(query.company_id),
            "q": q,
            "rows": len(rows),
            "format": word,
        }
        return self._exported(
            query.context, member, table, rows, filters=filters, q=q, word=word, snapshot=snapshot
        )

    async def export_revenue(self, query: RevenueExportQuery) -> ReportDocument:
        member = self.setup._enter(query.context, "revenue.export")
        if "revenue.view" not in member.permissions:
            raise Forbidden(code="permission_missing")
        word = _rp_format(query.format)
        today = self.setup._today(query.context)
        start = query.week_start or today
        table = self._empty("revenue", "week", "Revenue", start, today, today)
        snapshot = {
            "screen": "revenue",
            "weekStart": start.isoformat(),
            "companyId": None if query.company_id is None else str(query.company_id),
            "rows": 0,
            "format": word,
        }
        return self._exported(
            query.context,
            member,
            table,
            [],
            filters="All companies",
            q=None,
            word=word,
            snapshot=snapshot,
        )

    async def export_expenses(self, query: ExpenseExportQuery) -> ReportDocument:
        member = self.setup._enter(query.context, "expenses.export")
        if "expenses.view" not in member.permissions:
            raise Forbidden(code="permission_missing")
        word = _rp_format(query.format)
        today = self.setup._today(query.context)
        first, last = query.from_date or today, min(query.to_date or today, today)
        table = self._empty("expenses", "ledger", "Central expenses", first, last, today)
        q = _pc_trim(query.q)
        snapshot = {
            "screen": "expenses",
            "from": first.isoformat(),
            "to": (query.to_date or today).isoformat(),
            "source": _pc_trim(query.source),
            "q": q,
            "rows": 0,
            "format": word,
        }
        return self._exported(
            query.context,
            member,
            table,
            [],
            filters="All sources",
            q=q,
            word=word,
            snapshot=snapshot,
        )

    async def export_pettycash(self, query: PettyCashExportQuery) -> ReportDocument:
        member = self.setup._enter(query.context, "pettycash.export")
        if "pettycash.view" not in member.permissions:
            raise Forbidden(code="permission_missing")
        word = _rp_format(query.format)
        view = _pc_trim(query.view)
        if view not in ("expenses", "cash"):
            raise RuleViolation(code="pettycash_export_view_invalid")
        today = self.setup._today(query.context)
        first, last = query.from_date or today, min(query.to_date or today, today)
        title = "Petty cash, expenses" if view == "expenses" else "Petty cash, cash received"
        table = self._empty("pettycash", view, title, first, last, today)
        q = _pc_trim(query.q)
        snapshot = {
            "screen": "pettycash",
            "from": first.isoformat(),
            "to": (query.to_date or today).isoformat(),
            "holderId": None if query.holder_id is None else str(query.holder_id),
            "view": view,
            "status": None if query.statuses is None else list(query.statuses),
            "q": q,
            "rows": 0,
            "format": word,
        }
        return self._exported(
            query.context,
            member,
            table,
            [],
            filters="All floats",
            q=q,
            word=word,
            snapshot=snapshot,
        )

    # --- internals --------------------------------------------------------------------------

    def _holders(self, member: FakeMember) -> list[ReportHolder]:
        view_all = "pettycash.view_all" in member.permissions
        members = sorted(
            self.setup.tenancy.members.values(),
            key=lambda m: (f"{m.first_name} {m.last_name}".strip().upper(), str(m.user_id)),
        )
        return [
            ReportHolder(m.user_id, f"{m.first_name} {m.last_name}".strip(), True)
            for m in members
            if "pettycash.spend" in m.permissions and (view_all or m.user_id == member.user_id)
        ]

    def _visible(self, member: FakeMember, company_id: UUID | None) -> list[FakeVehicle]:
        if member.scope_mode == "all":
            ids = set(self.setup.vehicles)
        elif member.scope_mode == "companies":
            ids = {v.id for v in self.setup.vehicles.values() if v.company_id in member.company_ids}
        else:
            ids = {v for v in member.vehicle_ids if v in self.setup.vehicles}
        return sorted(
            (
                v
                for v in self.setup.vehicles.values()
                if v.id in ids and (company_id is None or v.company_id == company_id)
            ),
            key=lambda v: (v.registration, str(v.id)),
        )

    def _build(
        self, member: FakeMember, query: ReportQuery | ReportExportQuery, today: date
    ) -> _FakeTable:
        if query.group == "fleet":
            if query.report not in (*_FLEET_REPORTS, "investment"):
                raise NotFound(code="not_found")
            if query.report == "investment":
                if "reports.investment" not in member.permissions:
                    raise Forbidden(code="report_investment_permission")
                return self._empty(
                    "fleet", "investment", _REPORT_TITLES["investment"], None, None, today
                )
            first, last = _rp_period(query.from_date, query.to_date, today)
            vehicles = self._visible(member, query.company_id)
            if query.report == "net":
                return self._net(vehicles, first, last, today)
            if query.report == "gaps":
                return self._gaps(vehicles, first, last, today)
            title = _REPORT_TITLES[query.report]
            return self._empty("fleet", query.report, title, first, last, today)
        if query.group == "pettycash":
            if query.report not in _PETTYCASH_REPORTS:
                raise NotFound(code="not_found")
            if "pettycash.reports" not in member.permissions:
                raise Forbidden(code="report_pettycash_permission")
            holders = [h for h in self._holders(member) if query.holder_id in (None, h.id)]
            if query.holder_id is not None and not holders:
                raise NotFound(code="not_found")
            title = _REPORT_TITLES[query.report]
            if query.report == "waiting":
                return self._empty("pettycash", "waiting", title, None, None, today)
            first, last = _rp_period(query.from_date, query.to_date, today)
            return self._empty("pettycash", query.report, title, first, last, today)
        raise NotFound(code="not_found")

    def _window(
        self, vehicle: FakeVehicle, first: date, last: date, today: date
    ) -> tuple[date, date] | None:
        start = max(first, vehicle.joined_on)
        end = min(last, today)
        if vehicle.left_on is not None and vehicle.left_on <= end:
            end = vehicle.left_on - timedelta(days=1)
        return (start, end) if start <= end else None

    def _net(self, vehicles: list[FakeVehicle], first: date, last: date, today: date) -> _FakeTable:
        lines = []
        for vehicle in vehicles:
            window = self._window(vehicle, first, last, today)
            if window is None:
                continue
            revenue = sum(
                (
                    r.amount
                    for (vehicle_id, day), r in self.revenue.records.items()
                    if vehicle_id == vehicle.id
                    and window[0] <= day <= window[1]
                    and r.amount is not None
                ),
                Decimal(0),
            )
            company = self.setup.companies[vehicle.company_id].name
            row = (vehicle.registration, company, revenue, Decimal(0), revenue, Decimal(0))
            lines.append((vehicle, row))
        lines.sort(key=lambda item: (-item[1][4], item[0].registration, str(item[0].id)))
        rows = tuple(row for _, row in lines)
        revenue_total = sum((row[2] for row in rows), Decimal(0))
        return _FakeTable(
            "fleet",
            "net",
            "Net by vehicle",
            first,
            last,
            today,
            _rp_figure("Net", revenue_total, "net"),
            (
                _rp_figure("Revenue", revenue_total, "money"),
                _rp_figure("Money out", 0, "money"),
                _rp_figure("Saved", 0, "money"),
            ),
            (
                _rp_column("vehicle", "Vehicle", "vehicle"),
                _rp_column("company", "Company", "text"),
                _rp_column("revenue", "Revenue", "money", True),
                _rp_column("moneyOut", "Money out", "money", True),
                _rp_column("net", "Net", "net", True),
                _rp_column("saved", "Saved", "money", True),
            ),
            rows,
        )

    def _gaps(
        self, vehicles: list[FakeVehicle], first: date, last: date, today: date
    ) -> _FakeTable:
        lines = []
        for vehicle in vehicles:
            window = self._window(vehicle, first, last, today)
            if window is None:
                continue
            company = self.setup.companies[vehicle.company_id].name
            day = window[0]
            while day <= window[1]:
                active = _revenue_active(vehicle, day)
                record = self.revenue.records.get((vehicle.id, day))
                if active and (day < today or record is not None) and record is None:
                    row = (day.isoformat(), vehicle.registration, company, "Revenue not captured")
                    lines.append((day, vehicle, row))
                day += timedelta(days=1)
        lines.sort(key=lambda item: (item[0], item[1].registration, str(item[1].id)))
        rows = tuple(row for _, _, row in lines)
        return _FakeTable(
            "fleet",
            "gaps",
            "Capture gaps",
            first,
            last,
            today,
            _rp_figure("Missing days", len(rows), "count"),
            (_rp_figure("Vehicles with gaps", len({v.id for _, v, _ in lines}), "count"),),
            (
                _rp_column("date", "Date", "date"),
                _rp_column("vehicle", "Vehicle", "vehicle"),
                _rp_column("company", "Company", "text"),
                _rp_column("missing", "What is missing", "text"),
            ),
            rows,
        )

    def _empty(
        self,
        group: str,
        report: str,
        title: str,
        first: date | None,
        last: date | None,
        today: date,
    ) -> _FakeTable:
        return _FakeTable(
            group, report, title, first, last, today, _rp_figure(title, 0, "money"), (), (), ()
        )

    def _cap(self, count: int) -> None:
        if count > 10_000:
            raise RuleViolation(code="export_too_many_rows", detail={"count": f"{count:,}"})

    def _exported(
        self,
        context: TenantContext,
        member: FakeMember,
        table: _FakeTable,
        rows: list[tuple[Any, ...]],
        *,
        filters: str,
        q: str | None,
        word: str,
        snapshot: dict[str, Any],
    ) -> ReportDocument:
        period = _rp_period_words(table.from_date, table.to_date)
        sections = self.setup.tenancy.sections
        reason = f"Exported {table.title}"
        if period is not None:
            reason += f" for {period}"
        if q is not None:
            reason += f', searched for "{q}"'
        reason += " to " + ("PDF" if word == "pdf" else "Excel")
        after = _compact(_rp_jsonb_order(snapshot))
        self.setup._log(context, "reports", uuid4(), "null", after, reason)
        return ReportDocument(
            group=table.group,
            report=table.report,
            title=table.title,
            from_date=table.from_date,
            to_date=table.to_date,
            business_date=table.business_date,
            headline=table.headline,
            figures=table.figures,
            columns=table.columns,
            rows=tuple(rows),
            total=len(rows),
            totals=_rp_totals(table.columns, rows),
            organization=sections["branding"].get("display_name") or "XCODE",
            period=period,
            filters=filters,
            exported_by=f"{member.first_name} {member.last_name}".strip(),
            exported_on=context.now,
            currency=sections["localization"].get("currency"),
            file_name=f"{table.title}{'' if period is None else ' ' + period}.{word}",
            content_type="application/pdf" if word == "pdf" else _XLSX_TYPE,
        )
