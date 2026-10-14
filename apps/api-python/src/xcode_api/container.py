"""Composition root: the ``Container`` of adapters and use cases.

``build_container`` builds the real routine gateways from the pool by default; tests and the
``openapi`` command substitute ``ops``, ``identity``, ``tenancy``, ``setup``, ``revenue``,
``pettycash``, ``expenses`` (and any other port) through the keyword arguments.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from psycopg_pool import AsyncConnectionPool

from .application.access.create_person import CreatePerson
from .application.access.get_access_catalog import GetAccessCatalog
from .application.access.get_my_scope import GetMyScope
from .application.access.get_person import GetPerson
from .application.access.get_scope_options import GetScopeOptions
from .application.access.list_access_roles import ListAccessRoles
from .application.access.list_people import ListPeople
from .application.access.remove_person_device import RemovePersonDevice
from .application.access.require_pin_reset import RequirePinReset
from .application.access.set_person_active import SetPersonActive
from .application.access.sign_out_person import SignOutPerson
from .application.access.update_person import UpdatePerson
from .application.auth.change_pin import ChangePin
from .application.auth.common import CodeDelivery
from .application.auth.complete_pin import CompletePin
from .application.auth.enter_code import EnterCode
from .application.auth.enter_pin import EnterPin
from .application.auth.get_session import GetSession
from .application.auth.list_trusted_devices import ListTrustedDevices
from .application.auth.refresh import Refresh
from .application.auth.remove_trusted_device import RemoveTrustedDevice
from .application.auth.request_code import RequestCode
from .application.auth.resend_code import ResendCode
from .application.auth.resolve_session import ResolveSession
from .application.auth.revoke_device import RevokeDevice
from .application.auth.sign_in import SignIn
from .application.auth.sign_out import SignOut
from .application.auth.start_sign_in import StartSignIn
from .application.auth.verify_code import VerifyCode
from .application.auth.verify_device import VerifyDevice
from .application.expenses.change_expense import ChangeExpense
from .application.expenses.export_ledger import ExportExpenseLedger
from .application.expenses.get_ledger import GetExpenseLedger
from .application.expenses.get_options import GetExpenseOptions
from .application.expenses.record_expense import RecordExpense
from .application.expenses.remove_expense import RemoveExpense
from .application.ops.check_readiness import CheckReadiness
from .application.organization.delete_organization_logo import DeleteOrganizationLogo
from .application.organization.get_appearance import GetAppearance
from .application.organization.get_organization_settings import GetOrganizationSettings
from .application.organization.get_preferences import GetPreferences
from .application.organization.list_history import ListHistory
from .application.organization.update_organization_logo import UpdateOrganizationLogo
from .application.organization.update_organization_settings import UpdateOrganizationSettings
from .application.organization.update_preferences import UpdatePreferences
from .application.pettycash.approve_day import ApprovePettyCashDay
from .application.pettycash.approve_entries import ApprovePettyCashEntries
from .application.pettycash.approve_entry import ApprovePettyCashEntry
from .application.pettycash.create_entry import CreatePettyCashEntry
from .application.pettycash.export_entries import ExportPettyCashEntries
from .application.pettycash.get_dashboard import GetPettyCashDashboard
from .application.pettycash.get_options import GetPettyCashOptions
from .application.pettycash.get_overview import GetPettyCashOverview
from .application.pettycash.list_entries import ListPettyCashEntries
from .application.pettycash.reject_entry import RejectPettyCashEntry
from .application.pettycash.remove_entry import RemovePettyCashEntry
from .application.pettycash.reopen_entry import ReopenPettyCashEntry
from .application.pettycash.send_back_entry import SendBackPettyCashEntry
from .application.pettycash.update_entry import UpdatePettyCashEntry
from .application.ports import (
    Clock,
    Mailer,
    PinHasher,
    RateLimiter,
    ReportFileWriter,
    SecretSource,
    TokenIssuer,
)
from .application.reports.export_report import ExportReport
from .application.reports.get_report import GetReport
from .application.reports.get_reports_access import GetReportsAccess
from .application.repositories import (
    ExpensesRepository,
    IdentityRepository,
    OpsRepository,
    PettyCashRepository,
    ReportsRepository,
    RevenueRepository,
    SetupRepository,
    TenancyRepository,
)
from .application.revenue.capture_revenue import CaptureRevenue
from .application.revenue.export_week import ExportRevenueWeek
from .application.revenue.get_dashboard import GetRevenueDashboard
from .application.revenue.get_day import GetRevenueDay
from .application.revenue.get_week import GetRevenueWeek
from .application.revenue.save_day import SaveRevenueDay
from .application.setup.archive_company import ArchiveCompany
from .application.setup.cancel_recurring_stop import CancelRecurringStop
from .application.setup.create_company import CreateCompany
from .application.setup.create_expense_category import CreateExpenseCategory
from .application.setup.create_expense_item import CreateExpenseItem
from .application.setup.create_expense_main_category import CreateExpenseMainCategory
from .application.setup.create_investment import CreateInvestment
from .application.setup.create_recurring import CreateRecurring
from .application.setup.create_vehicle import CreateVehicle
from .application.setup.delete_investment import DeleteInvestment
from .application.setup.get_investment import GetInvestment
from .application.setup.get_recurring_runs import GetRecurringRuns
from .application.setup.get_recurring_summary import GetRecurringSummary
from .application.setup.get_vehicle_report import GetVehicleReport
from .application.setup.list_companies import ListCompanies
from .application.setup.list_company_options import ListCompanyOptions
from .application.setup.list_expense_categories import ListExpenseCategories
from .application.setup.list_expense_item_options import ListExpenseItemOptions
from .application.setup.list_expense_main_categories import ListExpenseMainCategories
from .application.setup.list_recurring import ListRecurring
from .application.setup.list_target_sets import ListTargetSets
from .application.setup.list_vehicle_options import ListVehicleOptions
from .application.setup.list_vehicles import ListVehicles
from .application.setup.pause_recurring import PauseRecurring
from .application.setup.remove_target_set import RemoveTargetSet
from .application.setup.rename_company import RenameCompany
from .application.setup.rename_expense_item import RenameExpenseItem
from .application.setup.rename_expense_main_category import RenameExpenseMainCategory
from .application.setup.restore_company import RestoreCompany
from .application.setup.restore_vehicle import RestoreVehicle
from .application.setup.resume_recurring import ResumeRecurring
from .application.setup.retire_vehicle import RetireVehicle
from .application.setup.revise_recurring import ReviseRecurring
from .application.setup.save_target_set import SaveTargetSet
from .application.setup.set_expense_category_stopped import SetExpenseCategoryStopped
from .application.setup.set_expense_item_stopped import SetExpenseItemStopped
from .application.setup.stop_recurring import StopRecurring
from .application.setup.update_expense_category import UpdateExpenseCategory
from .application.setup.update_investment import UpdateInvestment
from .application.setup.update_vehicle import UpdateVehicle
from .db.contract import EXPECTED_CONTRACT_VERSION
from .db.routines.expenses import ExpensesRoutines
from .db.routines.identity import IdentityRoutines
from .db.routines.ops import OpsRoutines
from .db.routines.pettycash import PettyCashRoutines
from .db.routines.reports import ReportsRoutines
from .db.routines.revenue import RevenueRoutines
from .db.routines.setup import SetupRoutines
from .db.routines.tenancy import TenancyRoutines
from .domain.reports import ExportFormat
from .infra.clock import SystemClock
from .infra.exports.pdf import ReportLabAdapter
from .infra.exports.xlsx import XlsxWriterAdapter
from .infra.mail import LogMailer, MailQueue, SmtpMailer, VerificationMailer
from .infra.rate_limit import MemoryRateLimiter, PostgresRateLimiter
from .security.device_tokens import RandomDeviceTokens
from .security.digests import KeyedDigester
from .security.pins import Pbkdf2PinHasher
from .security.secret_source import RandomSecretSource
from .security.tokens import JwtTokenIssuer
from .settings import Environment, Settings


@dataclass(frozen=True, slots=True)
class Container:
    settings: Settings
    clock: Clock
    mail_queue: MailQueue
    rate_limiter: RateLimiter
    ops: OpsRepository
    identity: IdentityRepository
    pin_hasher: PinHasher
    token_issuer: TokenIssuer
    check_readiness: CheckReadiness
    sign_in: SignIn
    verify_device: VerifyDevice
    request_code: RequestCode
    verify_code: VerifyCode
    complete_pin: CompletePin
    refresh: Refresh
    sign_out: SignOut
    revoke_device: RevokeDevice
    resolve_session: ResolveSession
    get_session: GetSession
    start_sign_in: StartSignIn
    enter_pin: EnterPin
    enter_code: EnterCode
    resend_code: ResendCode
    change_pin: ChangePin
    list_trusted_devices: ListTrustedDevices
    remove_trusted_device: RemoveTrustedDevice
    tenancy: TenancyRepository
    get_access_catalog: GetAccessCatalog
    list_access_roles: ListAccessRoles
    get_scope_options: GetScopeOptions
    get_my_scope: GetMyScope
    list_people: ListPeople
    get_person: GetPerson
    create_person: CreatePerson
    update_person: UpdatePerson
    set_person_active: SetPersonActive
    sign_out_person: SignOutPerson
    require_pin_reset: RequirePinReset
    remove_person_device: RemovePersonDevice
    list_history: ListHistory
    get_organization_settings: GetOrganizationSettings
    update_organization_settings: UpdateOrganizationSettings
    update_organization_logo: UpdateOrganizationLogo
    delete_organization_logo: DeleteOrganizationLogo
    get_appearance: GetAppearance
    get_preferences: GetPreferences
    update_preferences: UpdatePreferences
    setup: SetupRepository
    list_companies: ListCompanies
    create_company: CreateCompany
    rename_company: RenameCompany
    archive_company: ArchiveCompany
    restore_company: RestoreCompany
    list_company_options: ListCompanyOptions
    list_vehicles: ListVehicles
    create_vehicle: CreateVehicle
    update_vehicle: UpdateVehicle
    retire_vehicle: RetireVehicle
    restore_vehicle: RestoreVehicle
    get_vehicle_report: GetVehicleReport
    list_target_sets: ListTargetSets
    save_target_set: SaveTargetSet
    remove_target_set: RemoveTargetSet
    list_recurring: ListRecurring
    list_vehicle_options: ListVehicleOptions
    create_recurring: CreateRecurring
    revise_recurring: ReviseRecurring
    stop_recurring: StopRecurring
    cancel_recurring_stop: CancelRecurringStop
    pause_recurring: PauseRecurring
    resume_recurring: ResumeRecurring
    get_recurring_runs: GetRecurringRuns
    get_recurring_summary: GetRecurringSummary
    list_expense_categories: ListExpenseCategories
    list_expense_item_options: ListExpenseItemOptions
    create_expense_category: CreateExpenseCategory
    update_expense_category: UpdateExpenseCategory
    set_expense_category_stopped: SetExpenseCategoryStopped
    create_expense_item: CreateExpenseItem
    rename_expense_item: RenameExpenseItem
    set_expense_item_stopped: SetExpenseItemStopped
    list_expense_main_categories: ListExpenseMainCategories
    create_expense_main_category: CreateExpenseMainCategory
    rename_expense_main_category: RenameExpenseMainCategory
    get_investment: GetInvestment
    create_investment: CreateInvestment
    update_investment: UpdateInvestment
    delete_investment: DeleteInvestment
    revenue: RevenueRepository
    get_revenue_week: GetRevenueWeek
    get_revenue_dashboard: GetRevenueDashboard
    capture_revenue: CaptureRevenue
    get_revenue_day: GetRevenueDay
    save_revenue_day: SaveRevenueDay
    pettycash: PettyCashRepository
    get_pettycash_overview: GetPettyCashOverview
    list_pettycash_entries: ListPettyCashEntries
    get_pettycash_options: GetPettyCashOptions
    get_pettycash_dashboard: GetPettyCashDashboard
    create_pettycash_entry: CreatePettyCashEntry
    update_pettycash_entry: UpdatePettyCashEntry
    approve_pettycash_entry: ApprovePettyCashEntry
    send_back_pettycash_entry: SendBackPettyCashEntry
    reject_pettycash_entry: RejectPettyCashEntry
    reopen_pettycash_entry: ReopenPettyCashEntry
    remove_pettycash_entry: RemovePettyCashEntry
    approve_pettycash_day: ApprovePettyCashDay
    approve_pettycash_entries: ApprovePettyCashEntries
    expenses: ExpensesRepository
    get_expense_ledger: GetExpenseLedger
    get_expense_options: GetExpenseOptions
    record_expense: RecordExpense
    change_expense: ChangeExpense
    remove_expense: RemoveExpense
    reports: ReportsRepository
    export_writers: Mapping[ExportFormat, ReportFileWriter]
    get_reports_access: GetReportsAccess
    get_report: GetReport
    export_report: ExportReport
    export_revenue_week: ExportRevenueWeek
    export_expense_ledger: ExportExpenseLedger
    export_pettycash_entries: ExportPettyCashEntries


def build_container(
    settings: Settings,
    pool: AsyncConnectionPool[Any] | None = None,
    *,
    ops: OpsRepository | None = None,
    identity: IdentityRepository | None = None,
    tenancy: TenancyRepository | None = None,
    setup: SetupRepository | None = None,
    revenue: RevenueRepository | None = None,
    pettycash: PettyCashRepository | None = None,
    expenses: ExpensesRepository | None = None,
    reports: ReportsRepository | None = None,
    export_writers: Mapping[ExportFormat, ReportFileWriter] | None = None,
    clock: Clock | None = None,
    mailer: Mailer | None = None,
    rate_limiter: RateLimiter | None = None,
    pin_hasher: PinHasher | None = None,
    secrets: SecretSource | None = None,
) -> Container:
    if (
        ops is None
        or identity is None
        or tenancy is None
        or setup is None
        or revenue is None
        or pettycash is None
    ):
        if pool is None:
            raise ValueError(
                "build_container needs a pool or the ops, identity, tenancy, setup, revenue and"
                " pettycash ports"
            )
        ops = ops or OpsRoutines(pool)
        identity = identity or IdentityRoutines(pool)
        tenancy = tenancy or TenancyRoutines(pool)
        setup = setup or SetupRoutines(pool)
        revenue = revenue or RevenueRoutines(pool)
        pettycash = pettycash or PettyCashRoutines(pool)
    if expenses is None:
        if pool is None:
            raise ValueError("build_container needs a pool or the expenses port")
        expenses = ExpensesRoutines(pool)
    if reports is None:
        if pool is None:
            raise ValueError("build_container needs a pool or the reports port")
        reports = ReportsRoutines(pool)
    export_writers = export_writers or _default_export_writers()
    clock = clock or SystemClock()
    mailer = mailer or _default_mailer(settings)
    mail_queue = MailQueue(mailer)
    code_mailer = VerificationMailer(
        mailer, mail_queue, timeout_seconds=settings.email_timeout_seconds
    )
    rate_limiter = rate_limiter or _default_rate_limiter(settings, ops)
    pin_hasher = pin_hasher or Pbkdf2PinHasher(settings.auth_pin_iterations)
    secrets = secrets or RandomSecretSource()
    digests = KeyedDigester(settings.auth_signing_key)
    tokens = JwtTokenIssuer(
        signing_key=settings.auth_signing_key,
        previous_keys=settings.auth_previous_signing_keys,
        issuer=settings.auth_issuer,
        audience=settings.auth_audience,
    )
    device_tokens = RandomDeviceTokens()
    delivery = CodeDelivery(identity, clock, code_mailer)
    development_codes = settings.development_codes
    trust_days = settings.auth_trust_lifetime_days
    return Container(
        settings=settings,
        clock=clock,
        mail_queue=mail_queue,
        rate_limiter=rate_limiter,
        ops=ops,
        identity=identity,
        pin_hasher=pin_hasher,
        token_issuer=tokens,
        check_readiness=CheckReadiness(
            ops,
            expected_contract_version=EXPECTED_CONTRACT_VERSION,
            shared_limiter=(
                (rate_limiter, clock) if settings.rate_limit_backend == "postgres" else None
            ),
        ),
        sign_in=SignIn(
            identity,
            clock,
            pins=pin_hasher,
            digests=digests,
            secrets=secrets,
            tokens=tokens,
            delivery=delivery,
            development_codes=development_codes,
        ),
        verify_device=VerifyDevice(
            identity, clock, digests, secrets, tokens, delivery=delivery, trust_days=trust_days
        ),
        request_code=RequestCode(
            identity, clock, digests, secrets, delivery, development_codes=development_codes
        ),
        verify_code=VerifyCode(identity, clock, digests, secrets, delivery),
        complete_pin=CompletePin(
            identity,
            clock,
            pins=pin_hasher,
            digests=digests,
            secrets=secrets,
            device_tokens=device_tokens,
            tokens=tokens,
            trust_days=trust_days,
        ),
        refresh=Refresh(identity, clock, digests, secrets, tokens),
        sign_out=SignOut(identity, clock, digests),
        revoke_device=RevokeDevice(identity, clock),
        resolve_session=ResolveSession(tokens, identity, clock),
        get_session=GetSession(),
        start_sign_in=StartSignIn(
            identity,
            clock,
            digests=digests,
            secrets=secrets,
            device_tokens=device_tokens,
            delivery=delivery,
            development_codes=development_codes,
        ),
        enter_pin=EnterPin(
            identity,
            clock,
            pins=pin_hasher,
            digests=digests,
            secrets=secrets,
            device_tokens=device_tokens,
            tokens=tokens,
            delivery=delivery,
            development_codes=development_codes,
        ),
        enter_code=EnterCode(
            identity,
            clock,
            digests=digests,
            secrets=secrets,
            device_tokens=device_tokens,
            tokens=tokens,
            delivery=delivery,
            trust_days=trust_days,
        ),
        resend_code=ResendCode(
            identity,
            clock,
            digests=digests,
            secrets=secrets,
            delivery=delivery,
            development_codes=development_codes,
        ),
        change_pin=ChangePin(identity, clock, pins=pin_hasher),
        list_trusted_devices=ListTrustedDevices(identity, clock),
        remove_trusted_device=RemoveTrustedDevice(identity, clock),
        tenancy=tenancy,
        get_access_catalog=GetAccessCatalog(tenancy, clock),
        list_access_roles=ListAccessRoles(tenancy, clock),
        get_scope_options=GetScopeOptions(tenancy, clock),
        get_my_scope=GetMyScope(tenancy, clock),
        list_people=ListPeople(tenancy, clock),
        get_person=GetPerson(tenancy, clock),
        create_person=CreatePerson(tenancy, clock),
        update_person=UpdatePerson(tenancy, clock),
        set_person_active=SetPersonActive(tenancy, clock),
        sign_out_person=SignOutPerson(tenancy, clock),
        require_pin_reset=RequirePinReset(tenancy, clock),
        remove_person_device=RemovePersonDevice(tenancy, clock),
        list_history=ListHistory(tenancy, clock),
        get_organization_settings=GetOrganizationSettings(tenancy, clock),
        update_organization_settings=UpdateOrganizationSettings(tenancy, clock),
        update_organization_logo=UpdateOrganizationLogo(tenancy, clock),
        delete_organization_logo=DeleteOrganizationLogo(tenancy, clock),
        get_appearance=GetAppearance(tenancy, clock),
        get_preferences=GetPreferences(tenancy, clock),
        update_preferences=UpdatePreferences(tenancy, clock),
        setup=setup,
        list_companies=ListCompanies(setup, clock),
        create_company=CreateCompany(setup, clock),
        rename_company=RenameCompany(setup, clock),
        archive_company=ArchiveCompany(setup, clock),
        restore_company=RestoreCompany(setup, clock),
        list_company_options=ListCompanyOptions(setup, clock),
        list_vehicles=ListVehicles(setup, clock),
        create_vehicle=CreateVehicle(setup, clock),
        update_vehicle=UpdateVehicle(setup, clock),
        retire_vehicle=RetireVehicle(setup, clock),
        restore_vehicle=RestoreVehicle(setup, clock),
        get_vehicle_report=GetVehicleReport(setup, clock),
        list_target_sets=ListTargetSets(setup, clock),
        save_target_set=SaveTargetSet(setup, clock),
        remove_target_set=RemoveTargetSet(setup, clock),
        list_recurring=ListRecurring(setup, clock),
        list_vehicle_options=ListVehicleOptions(setup, clock),
        create_recurring=CreateRecurring(setup, clock),
        revise_recurring=ReviseRecurring(setup, clock),
        stop_recurring=StopRecurring(setup, clock),
        cancel_recurring_stop=CancelRecurringStop(setup, clock),
        pause_recurring=PauseRecurring(setup, clock),
        resume_recurring=ResumeRecurring(setup, clock),
        get_recurring_runs=GetRecurringRuns(setup, clock),
        get_recurring_summary=GetRecurringSummary(setup, clock),
        list_expense_categories=ListExpenseCategories(setup, clock),
        list_expense_item_options=ListExpenseItemOptions(setup, clock),
        create_expense_category=CreateExpenseCategory(setup, clock),
        update_expense_category=UpdateExpenseCategory(setup, clock),
        set_expense_category_stopped=SetExpenseCategoryStopped(setup, clock),
        create_expense_item=CreateExpenseItem(setup, clock),
        rename_expense_item=RenameExpenseItem(setup, clock),
        set_expense_item_stopped=SetExpenseItemStopped(setup, clock),
        list_expense_main_categories=ListExpenseMainCategories(setup, clock),
        create_expense_main_category=CreateExpenseMainCategory(setup, clock),
        rename_expense_main_category=RenameExpenseMainCategory(setup, clock),
        get_investment=GetInvestment(setup, clock),
        create_investment=CreateInvestment(setup, clock),
        update_investment=UpdateInvestment(setup, clock),
        delete_investment=DeleteInvestment(setup, clock),
        revenue=revenue,
        get_revenue_week=GetRevenueWeek(revenue, clock),
        get_revenue_dashboard=GetRevenueDashboard(revenue, clock),
        capture_revenue=CaptureRevenue(revenue, clock),
        get_revenue_day=GetRevenueDay(revenue, clock),
        save_revenue_day=SaveRevenueDay(revenue, clock),
        pettycash=pettycash,
        get_pettycash_overview=GetPettyCashOverview(pettycash, clock),
        list_pettycash_entries=ListPettyCashEntries(pettycash, clock),
        get_pettycash_options=GetPettyCashOptions(pettycash, clock),
        get_pettycash_dashboard=GetPettyCashDashboard(pettycash, clock),
        create_pettycash_entry=CreatePettyCashEntry(pettycash, clock),
        update_pettycash_entry=UpdatePettyCashEntry(pettycash, clock),
        approve_pettycash_entry=ApprovePettyCashEntry(pettycash, clock),
        send_back_pettycash_entry=SendBackPettyCashEntry(pettycash, clock),
        reject_pettycash_entry=RejectPettyCashEntry(pettycash, clock),
        reopen_pettycash_entry=ReopenPettyCashEntry(pettycash, clock),
        remove_pettycash_entry=RemovePettyCashEntry(pettycash, clock),
        approve_pettycash_day=ApprovePettyCashDay(pettycash, clock),
        approve_pettycash_entries=ApprovePettyCashEntries(pettycash, clock),
        expenses=expenses,
        get_expense_ledger=GetExpenseLedger(expenses, clock),
        get_expense_options=GetExpenseOptions(expenses, clock),
        record_expense=RecordExpense(expenses, clock),
        change_expense=ChangeExpense(expenses, clock),
        remove_expense=RemoveExpense(expenses, clock),
        reports=reports,
        export_writers=export_writers,
        get_reports_access=GetReportsAccess(reports, clock),
        get_report=GetReport(reports, clock),
        export_report=ExportReport(reports, export_writers, clock),
        export_revenue_week=ExportRevenueWeek(reports, export_writers, clock),
        export_expense_ledger=ExportExpenseLedger(reports, export_writers, clock),
        export_pettycash_entries=ExportPettyCashEntries(reports, export_writers, clock),
    )


def _default_export_writers() -> Mapping[ExportFormat, ReportFileWriter]:
    return {ExportFormat.XLSX: XlsxWriterAdapter(), ExportFormat.PDF: ReportLabAdapter()}


def _default_mailer(settings: Settings) -> Mailer:
    if settings.mail_backend == "log":
        return LogMailer(reveal_body=settings.env is not Environment.production)
    return SmtpMailer(
        host=settings.email_host,
        port=settings.email_port,
        sender=settings.email_from,
        username=settings.email_username,
        password=settings.email_password,
        timeout_seconds=settings.email_timeout_seconds,
        tls=settings.email_tls,
        allow_plaintext=settings.is_development,
    )


def _default_rate_limiter(settings: Settings, ops: OpsRepository) -> RateLimiter:
    if settings.rate_limit_backend == "postgres":
        return PostgresRateLimiter(ops)
    return MemoryRateLimiter()
