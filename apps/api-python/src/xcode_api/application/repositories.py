"""Repository Protocols: one async method per PostgreSQL routine.

``IdentityRepository`` (the ``api.auth_*`` routines), ``TenancyRepository`` (access, people, the
change log, organization settings and preferences), ``SetupRepository`` (companies, vehicles,
scheduled items, the expense catalogue, investment), ``RevenueRepository`` (the week grid, the
dashboard, capture), ``PettyCashRepository`` (petty cash) and ``OpsRepository`` exist so far;
the other per-context repositories arrive with their features. Implementations ("routine
gateways") live in ``db/routines/`` and own the connection, transaction, retry policy and
SQLSTATE translation. A business refusal of an auth routine is an ``AuthOutcome``, never an
exception; the only refusal raised is ``SessionInvalid`` from ``resolve_session``.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from ..domain.identity import (
    AccountLookup,
    AccountState,
    AccountSummary,
    AuthOutcome,
    ClearedPause,
    CodeCheck,
    CodeEntry,
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
    PinVerdict,
    ProvisionedUser,
    RemovedUser,
    RevokedSessions,
    SeededDemo,
    SessionCheck,
    SessionContext,
    TokenRefresh,
    TokenSignOut,
    TrustedDeviceView,
    UserLookup,
    UserProvisioning,
)
from ..domain.pettycash import (
    PettyCashApproved,
    PettyCashCreate,
    PettyCashDashboard,
    PettyCashDayApproval,
    PettyCashDecision,
    PettyCashEntriesApproval,
    PettyCashEntryPage,
    PettyCashEntryQuery,
    PettyCashOptions,
    PettyCashOptionsQuery,
    PettyCashOverview,
    PettyCashOverviewQuery,
    PettyCashSaved,
    PettyCashUpdate,
)
from ..domain.revenue import (
    CaptureResult,
    RevenueCapture,
    RevenueDashboard,
    RevenueDashboardQuery,
    RevenueWeek,
    RevenueWeekQuery,
)
from ..domain.setup import (
    CompanyChoice,
    CompanyLifecycle,
    CompanyPage,
    CompanySave,
    ExpenseCategoryPage,
    ExpenseCategorySave,
    ExpenseItemChoice,
    ExpenseItemCreate,
    ExpenseItemRename,
    ExpenseLifecycle,
    InvestmentCreate,
    InvestmentRemoval,
    InvestmentSummary,
    InvestmentUpdate,
    MainCategoryPage,
    MainCategorySave,
    RecurringCancelStop,
    RecurringListQuery,
    RecurringPage,
    RecurringSave,
    RecurringStop,
    SetupPageQuery,
    ShareVehicle,
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
)
from ..domain.tenancy import (
    AccessRole,
    Appearance,
    HistoryPage,
    HistoryQuery,
    LogoRemoval,
    LogoSave,
    MyScope,
    OrganizationSettings,
    PeoplePage,
    PeopleQuery,
    PermissionGroup,
    Person,
    PersonDeviceRemoval,
    PersonLifecycle,
    PersonPinReset,
    PersonQuery,
    PersonSave,
    PersonSignOut,
    Preferences,
    PreferencesSave,
    ScopeOptions,
    SettingsSave,
    TenantContext,
    UserPreferences,
)
from ..domain.values import WriteResult
from .ports import RateLimitDecision


@runtime_checkable
class OpsRepository(Protocol):
    """Operations and metadata routines (``api.ops_*`` / ``api.meta_*``)."""

    async def ping(self) -> None:
        """Run the cheapest round trip that proves the database answers (``SELECT 1``).

        Raises on any connection or query failure; never returns a value.
        """
        ...

    async def contract_version(self) -> int:
        """Return ``api.meta_contract_version()``: the routine-contract version the
        connected database exposes, compared at startup with the version the package
        expects."""
        ...

    async def rate_limit_hit(
        self, key: str, limit: int, window_seconds: int, now: datetime
    ) -> RateLimitDecision:
        """Charge one hit against the fixed window ``key`` via ``api.rate_limit_hit`` and
        return the decision. Backs the ``PostgresRateLimiter`` adapter."""
        ...

    async def record_operator_action(
        self,
        operator: str,
        action: str,
        target: str,
        detail: Mapping[str, Any],
    ) -> None:
        """Append one row to ``ops.operator_actions`` naming the operator, the action, its
        target and non-secret structured detail."""
        ...

    async def provision_user(self, command: UserProvisioning) -> ProvisionedUser:
        """``api.ops_provision_user``: create or re-activate a person in the single
        organization; raises ``RuleViolation`` (bad email, phone, role, names) or ``Conflict``
        (``people_contact_taken``, ``organization_not_single``)."""
        ...

    async def remove_user(self, command: OperatorRequest) -> RemovedUser:
        """``api.ops_remove_user``; raises ``NotFound`` for an unknown email."""
        ...

    async def clear_pause(self, command: OperatorRequest) -> ClearedPause:
        """``api.ops_clear_pause`` (never the untrusted-device cap); ``NotFound`` as above."""
        ...

    async def revoke_sessions(self, command: OperatorRequest) -> RevokedSessions:
        """``api.ops_revoke_sessions``; ``NotFound`` as above."""
        ...

    async def account_state(self, command: OperatorRequest) -> AccountSummary:
        """``api.ops_account_state``; ``NotFound`` as above."""
        ...

    async def unassigned_user_count(self) -> int:
        """``api.meta_unassigned_user_count``: active users without an active membership."""
        ...

    async def seed_demo(self, command: DemoSeeding) -> SeededDemo:
        """``api.ops_seed_demo`` (development only): the demo organization, idempotent;
        raises ``Forbidden`` (``seed_development_only``) outside development and
        ``Conflict`` (``seed_exists``, ``organization_not_single``) beside other data."""
        ...


@runtime_checkable
class IdentityRepository(Protocol):
    """Authentication routines (``api.auth_*``); ``docs/07-auth.md`` section 3 has each
    routine's check order."""

    async def account_lookup(self, query: AccountLookup) -> AccountState | None:
        """``api.auth_account_lookup``: the account behind a phone number, or ``None`` for an
        unknown or non-normalising number (recorded as ``unknown_number`` on a PIN try)."""
        ...

    async def account_lookup_user(self, query: UserLookup) -> AccountState | None:
        """``api.auth_account_lookup_user``: the signed-in person's account state (N07)."""
        ...

    async def start(self, command: NumberCheck) -> AuthOutcome:
        """``api.auth_start``: the number step (N01)."""
        ...

    async def sign_in(self, verdict: PinVerdict) -> AuthOutcome:
        """``api.auth_sign_in``: record the PIN verdict and decide (A01, A02)."""
        ...

    async def pin(self, command: PinCheck) -> AuthOutcome:
        """``api.auth_pin``: record the PIN verdict and decide (N02)."""
        ...

    async def check_code(self, command: CodeEntry) -> AuthOutcome:
        """``api.auth_check_code``: the code step (N03)."""
        ...

    async def resend_code(self, command: CodeResend) -> AuthOutcome:
        """``api.auth_resend_code``: always ``verification_required``, issued or not (N04)."""
        ...

    async def verify_device(self, command: DeviceVerification) -> AuthOutcome:
        """``api.auth_verify_device`` (A03)."""
        ...

    async def request_code(self, command: CodeRequest) -> AuthOutcome:
        """``api.auth_request_code``: ``check_email`` with the code id and address, or
        ``silent`` (A04, A07)."""
        ...

    async def verify_code(self, command: CodeCheck) -> AuthOutcome:
        """``api.auth_verify_code``: ``code_verified`` or ``refused`` (A05, A08)."""
        ...

    async def complete_pin(self, command: PinCompletion) -> AuthOutcome:
        """``api.auth_complete_pin``: ``authenticated``, ``invalid_pin`` or ``refused``
        (A06, A09, N06)."""
        ...

    async def change_pin(self, command: PinChange) -> AuthOutcome:
        """``api.auth_change_pin``: ``pin_changed``, ``refused`` or ``pin_locked`` (N07)."""
        ...

    async def refresh(self, command: TokenRefresh) -> AuthOutcome:
        """``api.auth_refresh``: rotation with freshly read claims (A10)."""
        ...

    async def sign_out(self, command: TokenSignOut) -> AuthOutcome:
        """``api.auth_sign_out``: always ``signed_out`` (A11)."""
        ...

    async def revoke_device(self, command: DeviceRevocation) -> AuthOutcome:
        """``api.auth_revoke_device``: always ``device_revoked`` (A12)."""
        ...

    async def device_list(self, query: DeviceListing) -> tuple[TrustedDeviceView, ...]:
        """``api.auth_device_list``: the person's live remembered devices (N08)."""
        ...

    async def device_remove(self, command: DeviceRemoval) -> AuthOutcome:
        """``api.auth_device_remove``: ``device_revoked``; raises ``NotFound`` for a row that
        is not the person's and live (N09)."""
        ...

    async def withdraw_code(self, command: CodeWithdrawal) -> None:
        """``api.auth_withdraw_code`` after a failed send: the code neither starts the cooldown
        nor counts toward the caps."""
        ...

    async def resolve_session(self, check: SessionCheck) -> SessionContext:
        """``api.auth_resolve_session``: raises ``SessionInvalid`` unless the user is active,
        the security version matches and the device row is live."""
        ...


@runtime_checkable
class TenancyRepository(Protocol):
    """Access, people, change-log and organization routines (``docs/05-routines.md`` sections
    4.1, 4.4 and 4.8). Every routine enters the organization of the context first, so a caller
    without the membership or permission gets ``Forbidden``; refusals arrive as the typed
    domain refusals with the routine's code."""

    async def access_catalog(self, context: TenantContext) -> tuple[PermissionGroup, ...]:
        """``api.access_catalog_list``: the permission catalogue, for any member."""
        ...

    async def access_roles(self, context: TenantContext) -> tuple[AccessRole, ...]:
        """``api.access_role_list`` (``people.view``): roles by name with expanded defaults."""
        ...

    async def scope_options(self, context: TenantContext) -> ScopeOptions:
        """``api.access_scope_options`` (``people.add`` or ``people.edit``): what the actor may
        hand on."""
        ...

    async def my_scope(self, context: TenantContext) -> MyScope:
        """``api.access_my_scope``: the actor's own companies and vehicles."""
        ...

    async def list_people(self, query: PeopleQuery) -> PeoplePage:
        """``api.people_list`` (``people.view``); ``RuleViolation page_out_of_range``,
        ``people_filter_status_invalid``."""
        ...

    async def get_person(self, query: PersonQuery) -> Person:
        """``api.people_get``; ``NotFound`` for a person the actor cannot see."""
        ...

    async def create_person(self, command: PersonSave) -> WriteResult:
        """``api.people_create``: the people rules in their contract order."""
        ...

    async def update_person(self, command: PersonSave) -> WriteResult:
        """``api.people_update``: ``unchanged`` when nothing differs; ``Conflict
        version_conflict`` for a stale version."""
        ...

    async def set_person_active(self, command: PersonLifecycle) -> WriteResult:
        """``api.people_set_active``: activate or deactivate; ``unchanged`` when already so."""
        ...

    async def sign_out_person(self, command: PersonSignOut) -> WriteResult:
        """``api.people_sign_out`` (``people.sign_in``): remove every trusted device and refresh
        token of the person; ``unchanged`` when none is left."""
        ...

    async def require_pin_reset(self, command: PersonPinReset) -> WriteResult:
        """``api.people_pin_reset`` (``people.sign_in``): remove the person's devices and make
        their next sign-in a reset; ``unchanged`` without a PIN or with a reset due."""
        ...

    async def remove_person_device(self, command: PersonDeviceRemoval) -> WriteResult:
        """``api.people_device_remove`` (``people.sign_in``): remove one live trusted device of
        the person; ``NotFound`` for any other row."""
        ...

    async def list_history(self, query: HistoryQuery) -> HistoryPage:
        """``api.history_list`` (``audit.view``): the visible change log, filtered and paged."""
        ...

    async def organization_settings(self, context: TenantContext) -> OrganizationSettings:
        """``api.organization_settings_get`` (``organization.manage``)."""
        ...

    async def save_settings(self, command: SettingsSave) -> WriteResult:
        """``api.organization_settings_set``: ``NotFound`` for an unknown section, ``unchanged``
        when the merged section equals the stored one."""
        ...

    async def save_logo(self, command: LogoSave) -> WriteResult:
        """``api.organization_logo_set``."""
        ...

    async def delete_logo(self, command: LogoRemoval) -> WriteResult:
        """``api.organization_logo_delete``: ``unchanged`` when there is no logo."""
        ...

    async def appearance(self, context: TenantContext) -> Appearance:
        """``api.organization_appearance_get``, for any member."""
        ...

    async def preferences(self, context: TenantContext) -> Preferences:
        """``api.preferences_get``: the actor's own preferences."""
        ...

    async def save_preferences(self, command: PreferencesSave) -> UserPreferences:
        """``api.preferences_set``: the saved row."""
        ...


@runtime_checkable
class SetupRepository(Protocol):
    """Company, vehicle, scheduled item, expense catalogue and investment routines
    (``docs/05-routines.md`` sections 4.2, 4.3, 4.5 and 4.6). Each routine enters the
    organization of the context with its permission first; a record outside the caller's
    reach is ``NotFound``; refusals arrive as the typed domain refusals with the routine's
    code. A write that changes nothing answers ``unchanged`` and logs nothing."""

    async def list_companies(self, query: SetupPageQuery) -> CompanyPage:
        """``api.setup_company_list`` (``companies.view``): visible companies by name."""
        ...

    async def create_company(self, command: CompanySave) -> WriteResult:
        """``api.setup_company_create``: needs the all-companies scope."""
        ...

    async def rename_company(self, command: CompanySave) -> WriteResult:
        """``api.setup_company_rename``: an archived company cannot be renamed."""
        ...

    async def archive_company(self, command: CompanyLifecycle) -> WriteResult:
        """``api.setup_company_archive``: every vehicle must have left first."""
        ...

    async def restore_company(self, command: CompanyLifecycle) -> WriteResult:
        """``api.setup_company_restore``: clears the archive date."""
        ...

    async def company_options(self, context: TenantContext) -> tuple[CompanyChoice, ...]:
        """``api.setup_company_options`` (``vehicles.add`` or ``vehicles.edit``): visible
        companies in use."""
        ...

    async def list_vehicles(self, query: VehicleListQuery) -> VehiclePage:
        """``api.setup_vehicle_list`` (``vehicles.view`` or ``reports.investment``), of one
        company when asked: targets and the scheduled item count only for ``vehicles.view``."""
        ...

    async def create_vehicle(self, command: VehicleSave) -> WriteResult:
        """``api.setup_vehicle_create`` (``vehicles.add``): the vehicle with its fleet number
        and its first target set from the join date."""
        ...

    async def update_vehicle(self, command: VehicleSave) -> WriteResult:
        """``api.setup_vehicle_update`` (``vehicles.edit``): company, join date, fleet number
        and initial investment; never the targets."""
        ...

    async def retire_vehicle(self, command: VehicleRetirement) -> WriteResult:
        """``api.setup_vehicle_retire``: the vehicle leaves the fleet on ``left_on``."""
        ...

    async def restore_vehicle(self, command: VehicleReturn) -> WriteResult:
        """``api.setup_vehicle_restore``: back in the fleet, the days away recorded."""
        ...

    async def vehicle_report(self, query: VehicleReportQuery) -> VehicleReport:
        """``api.setup_vehicle_report`` (``vehicles.view``): money in, target, postings."""
        ...

    async def list_target_sets(self, query: VehicleQuery) -> tuple[TargetSetSummary, ...]:
        """``api.setup_target_set_list`` (``vehicles.view``): the vehicle's sets, newest first."""
        ...

    async def save_target_set(self, command: TargetSetSave) -> WriteResult:
        """``api.setup_target_set_save`` (``vehicles.target``): a set from today or later; the
        set already starting that day is replaced."""
        ...

    async def remove_target_set(self, command: TargetSetRemoval) -> WriteResult:
        """``api.setup_target_set_remove`` (``vehicles.target``): only a set not yet started."""
        ...

    async def list_recurring(self, query: RecurringListQuery) -> RecurringPage:
        """``api.setup_recurring_list`` (``scheduled.view`` or ``savings.view``): items of the
        kinds the caller can view as their latest version with the shares in reach, filtered by
        kind, company and status, running ones first."""
        ...

    async def vehicle_options(self, context: TenantContext) -> tuple[ShareVehicle, ...]:
        """``api.setup_vehicle_options`` (an add or edit right of either kind): vehicles a
        share can use."""
        ...

    async def create_recurring(self, command: RecurringSave) -> WriteResult:
        """``api.setup_recurring_create``: a new item with its first version."""
        ...

    async def revise_recurring(self, command: RecurringSave) -> WriteResult:
        """``api.setup_recurring_revise``: a new version when anything differs."""
        ...

    async def stop_recurring(self, command: RecurringStop) -> WriteResult:
        """``api.setup_recurring_stop``: no posting from the business date on."""
        ...

    async def cancel_recurring_stop(self, command: RecurringCancelStop) -> WriteResult:
        """``api.setup_recurring_cancel_stop``: only a stop that is not yet in effect."""
        ...

    async def list_expense_categories(self, query: SetupPageQuery) -> ExpenseCategoryPage:
        """``api.setup_expense_category_list``: categories by name with their items."""
        ...

    async def expense_item_options(self, context: TenantContext) -> tuple[ExpenseItemChoice, ...]:
        """``api.setup_expense_item_options``: items in use in categories in use."""
        ...

    async def create_expense_category(self, command: ExpenseCategorySave) -> WriteResult:
        """``api.setup_expense_category_create`` (``catalog.add``)."""
        ...

    async def update_expense_category(self, command: ExpenseCategorySave) -> WriteResult:
        """``api.setup_expense_category_update`` (``catalog.edit``): the name, the main
        category or both."""
        ...

    async def set_expense_category_stopped(self, command: ExpenseLifecycle) -> WriteResult:
        """``api.setup_expense_category_set_stopped``: turned off from the business date."""
        ...

    async def create_expense_item(self, command: ExpenseItemCreate) -> WriteResult:
        """``api.setup_expense_item_create``: the new item's id."""
        ...

    async def rename_expense_item(self, command: ExpenseItemRename) -> WriteResult:
        """``api.setup_expense_item_rename``."""
        ...

    async def set_expense_item_stopped(self, command: ExpenseLifecycle) -> WriteResult:
        """``api.setup_expense_item_set_stopped``: turned off from the business date."""
        ...

    async def list_expense_main_categories(self, query: SetupPageQuery) -> MainCategoryPage:
        """``api.setup_expense_main_category_list``: main categories by name with their counts,
        and the count of categories without one."""
        ...

    async def create_expense_main_category(self, command: MainCategorySave) -> WriteResult:
        """``api.setup_expense_main_category_create`` (``catalog.add``)."""
        ...

    async def rename_expense_main_category(self, command: MainCategorySave) -> WriteResult:
        """``api.setup_expense_main_category_rename`` (``catalog.edit``)."""
        ...

    async def get_investment(self, query: VehicleQuery) -> InvestmentSummary:
        """``api.setup_investment_get`` (``reports.investment``): entries, total and what came
        back."""
        ...

    async def create_investment(self, command: InvestmentCreate) -> WriteResult:
        """``api.setup_investment_create`` (``vehicles.edit``): the new entry's id."""
        ...

    async def update_investment(self, command: InvestmentUpdate) -> WriteResult:
        """``api.setup_investment_update``."""
        ...

    async def delete_investment(self, command: InvestmentRemoval) -> WriteResult:
        """``api.setup_investment_delete``: the one hard delete; answers ``updated``."""
        ...


@runtime_checkable
class RevenueRepository(Protocol):
    """The revenue routines (``docs/05-routines.md`` section 4.7): the week grid, the dashboard
    cards and the capture that phones also replay. A vehicle outside the caller's view is
    ``NotFound``; refusals arrive as the typed domain refusals with the routine's code, a
    version conflict carrying the stored cell as ``current`` in its detail."""

    async def week(self, query: RevenueWeekQuery) -> RevenueWeek:
        """``api.revenue_week_get`` (``revenue.view``): one page of the week grid with the
        whole grid's totals, day totals and first gap."""
        ...

    async def dashboard(self, query: RevenueDashboardQuery) -> RevenueDashboard:
        """``api.revenue_dashboard_get`` (any ``dash.*`` card): each card null without its own
        permission."""
        ...

    async def capture(self, command: RevenueCapture) -> CaptureResult:
        """``api.revenue_capture``: created, updated, or an identical entry replayed."""
        ...


@runtime_checkable
class PettyCashRepository(Protocol):
    """The petty-cash routines (``docs/05-routines.md`` section 4.9). An entry or float outside
    the caller's view is ``NotFound``; refusals arrive as the typed domain refusals with the
    routine's code, a version conflict carrying the entry as it is now as ``current`` and the
    float guard the balance it would leave as ``balance_after``."""

    async def overview(self, query: PettyCashOverviewQuery) -> PettyCashOverview:
        """``api.pettycash_overview_get`` (``pettycash.view``): the caller's rights, the floats
        they may see, the figures of the chosen days and one row per float."""
        ...

    async def entries(self, query: PettyCashEntryQuery) -> PettyCashEntryPage:
        """``api.pettycash_entry_list`` (``pettycash.view``): one page of the entries the caller
        may see, by date, kind, id."""
        ...

    async def options(self, query: PettyCashOptionsQuery) -> PettyCashOptions:
        """``api.pettycash_options_get``: the choices of the entry form on its date."""
        ...

    async def dashboard(self, context: TenantContext) -> PettyCashDashboard:
        """``api.pettycash_dashboard_get`` (``dash.pettycash``): each card null without its own
        permission."""
        ...

    async def create(self, command: PettyCashCreate) -> PettyCashSaved:
        """``api.pettycash_entry_create``: created, or the caller's own earlier save of the same
        id replayed."""
        ...

    async def update(self, command: PettyCashUpdate) -> PettyCashSaved:
        """``api.pettycash_entry_update``: a waiting expense changed (and waiting again), or an
        identical line replayed."""
        ...

    async def approve(self, command: PettyCashDecision) -> PettyCashSaved:
        """``api.pettycash_entry_approve``."""
        ...

    async def send_back(self, command: PettyCashDecision) -> PettyCashSaved:
        """``api.pettycash_entry_send_back``: ``text`` is the comment."""
        ...

    async def reject(self, command: PettyCashDecision) -> PettyCashSaved:
        """``api.pettycash_entry_reject``: ``text`` is the reason."""
        ...

    async def reopen(self, command: PettyCashDecision) -> PettyCashSaved:
        """``api.pettycash_entry_reopen``: ``text`` is the reason."""
        ...

    async def remove(self, command: PettyCashDecision) -> PettyCashSaved:
        """``api.pettycash_entry_remove``: ``text`` is the reason (optional for a waiting
        expense)."""
        ...

    async def approve_day(self, command: PettyCashDayApproval) -> PettyCashApproved:
        """``api.pettycash_day_approve``: every waiting expense of the days the caller may
        approve; the rest are skipped."""
        ...

    async def approve_entries(self, command: PettyCashEntriesApproval) -> PettyCashApproved:
        """``api.pettycash_entries_approve``: the ticked entries, all or none."""
        ...
