"""Parity cases for ``FakeSetupRepository``: each case runs the same calls against the fake and
against ``SetupRoutines`` on PostgreSQL, reading the change log through the tenancy repository
of the same world, and the two observations must be equal (``tenancy_cases.normalised``).

The business date is the calendar date of ``tenancy_cases.NOW`` (2026-10-09) in both worlds.
Every version in these cases has one share and every entry its own date, so no observation
depends on the order of generated ids."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from xcode_api.application.repositories import SetupRepository, TenancyRepository
from xcode_api.domain.setup import (
    CompanySave,
    ExpenseCategorySave,
    ExpenseItemCreate,
    InvestmentCreate,
    InvestmentDetails,
    InvestmentRemoval,
    InvestmentUpdate,
    MainCategorySave,
    OpeningAmount,
    RecurringCancelStop,
    RecurringDefinition,
    RecurringListQuery,
    RecurringPause,
    RecurringRunsQuery,
    RecurringSave,
    RecurringStop,
    SavingCondition,
    SavingOpening,
    SetupPageQuery,
    Share,
    TargetSetRemoval,
    TargetSetSave,
    VehicleDetails,
    VehicleListQuery,
    VehicleQuery,
    VehicleSave,
)
from xcode_api.domain.tenancy import HistoryQuery

from .fakes import FakeSetupRepository, FakeTenancyRepository
from .scenario import Conn
from .setup_rows import split_week
from .tenancy_cases import TenancyWorld, history
from .tenancy_cases import database_world as tenancy_database_world
from .tenancy_cases import fake_world as tenancy_fake_world

UNKNOWN = UUID(int=1)


def days(*amounts: int | str) -> tuple[Decimal, ...]:
    return tuple(Decimal(a) for a in amounts)


@dataclass
class SetupWorld:
    """The setup repository under test and the tenancy world whose Owner acts and whose
    change log is read; ``seen`` is the observation."""

    setup: SetupRepository
    tenancy: TenancyWorld

    @property
    def seen(self) -> list[Any]:
        return self.tenancy.seen

    async def record(self, call: Awaitable[Any]) -> Any:
        return await self.tenancy.record(call)

    async def history(self, section: str) -> None:
        tenancy = self.tenancy
        await self.record(
            tenancy.repository.list_history(HistoryQuery(tenancy.owner, history(section=section)))
        )

    async def company(self, name: str, reason: str | None = None) -> UUID:
        result = await self.record(
            self.setup.create_company(CompanySave(self.tenancy.owner, None, name, reason))
        )
        assert result is not None
        return UUID(str(result.id))

    async def vehicle(
        self,
        company: UUID,
        registration: str,
        joined: date,
        target: int,
        fleet: str | None = None,
        investment: Decimal | None = None,
    ) -> UUID:
        """A vehicle whose seven day figures split ``target`` as the migration does; the fleet
        number defaults to the last four characters of the registration."""
        number = fleet or registration.replace(" ", "")[-4:].upper()
        details = VehicleDetails(
            company, registration, number, joined, split_week(target), investment
        )
        result = await self.record(
            self.setup.create_vehicle(VehicleSave(self.tenancy.owner, None, details, None))
        )
        assert result is not None
        return UUID(str(result.id))


def fake_world() -> SetupWorld:
    tenancy = tenancy_fake_world()
    assert isinstance(tenancy.repository, FakeTenancyRepository)
    return SetupWorld(FakeSetupRepository(tenancy.repository), tenancy)


def database_world(
    setup: SetupRepository, tenancy: TenancyRepository, operator: Conn
) -> SetupWorld:
    return SetupWorld(setup, tenancy_database_world(tenancy, operator))


async def rename_a_company(world: SetupWorld) -> None:
    owner = world.tenancy.owner
    north = await world.company("North Star")
    south = await world.company("South Line", "Second depot")
    await world.record(world.setup.create_company(CompanySave(owner, None, " north star ", None)))

    async def rename(company: UUID, name: str, reason: str | None = None) -> None:
        await world.record(world.setup.rename_company(CompanySave(owner, company, name, reason)))

    await rename(south, " NORTH STAR")
    await rename(south, "   ")
    await rename(UNKNOWN, "Coast Line")
    await rename(south, " South Line ")
    await rename(south, "Coast Line", "New owners")
    await rename(north, "North Star Fleet")
    await world.record(world.setup.list_companies(SetupPageQuery(owner, 1, 25)))
    await world.history("companies")


async def create_and_update_a_vehicle(world: SetupWorld) -> None:
    owner = world.tenancy.owner
    north = await world.company("North Star")
    south = await world.company("South Line")
    await world.vehicle(south, "KDC 200B", date(2026, 10, 1), 3500, fleet="S-7")

    async def create(details: VehicleDetails) -> None:
        await world.record(world.setup.create_vehicle(VehicleSave(owner, None, details, None)))

    week = days(1000, 1000, 1000, 1000, 1000, 1200, 800)
    await create(VehicleDetails(north, "KDB 111A", None, date(2026, 10, 1), week, None))
    await create(VehicleDetails(north, "KDB 111A", "N-1", date(2026, 10, 1), week[:6], None))
    await create(
        VehicleDetails(north, "KDB 111A", "N-1", date(2026, 10, 1), (*week[:6], None), None)
    )
    await create(VehicleDetails(south, "KDB 111A", " s-7 ", date(2026, 10, 1), week, None))
    await create(VehicleDetails(north, "KDB 111A", "N-1", date(2026, 10, 1), week, Decimal(-1)))
    await create(VehicleDetails(north, "KDB 111A", "N-1", date(2026, 10, 1), week, Decimal(0)))
    kda = await world.vehicle(
        north, "kda482m", date(2026, 10, 1), 7000, fleet=" n-2 ", investment=Decimal("2500000")
    )

    async def update(
        company: UUID, joined: date, fleet: str | None, investment: Decimal | None
    ) -> None:
        details = VehicleDetails(company, "KDA 482M", fleet, joined, None, investment)
        await world.record(world.setup.update_vehicle(VehicleSave(owner, kda, details, None)))

    await update(north, date(2026, 10, 1), "n-2", Decimal("2500000.00"))
    await update(north, date(2026, 10, 1), "", Decimal("2500000"))
    await update(north, date(2026, 10, 12), "N-2", Decimal("2500000"))
    await update(south, date(2026, 10, 1), "S-7", Decimal("2500000"))
    await update(north, date(2026, 10, 1), "N-3", Decimal("2600000.50"))
    await update(north, date(2026, 10, 1), "N-3", None)
    await update(south, date(2026, 9, 28), "S-8", Decimal(0))
    await world.record(world.setup.list_target_sets(VehicleQuery(owner, kda)))
    for company in (None, north, south):
        await world.record(world.setup.list_vehicles(VehicleListQuery(owner, company, 1, 25)))
    await world.history("vehicles")


async def set_and_remove_targets(world: SetupWorld) -> None:
    owner = world.tenancy.owner
    north = await world.company("North Star")
    kda = await world.vehicle(north, "KDA 482M", date(2026, 10, 1), 7000)

    async def save(starts_on: date | None, figures: Any, vehicle: UUID = kda) -> Any:
        return await world.record(
            world.setup.save_target_set(TargetSetSave(owner, vehicle, starts_on, figures))
        )

    async def remove(set_id: UUID) -> None:
        await world.record(world.setup.remove_target_set(TargetSetRemoval(owner, set_id)))

    week = days(1000, 1000, 1000, 1000, 1000, 1500, 500)
    await save(None, week)
    await save(date(2026, 10, 9), week[:6])
    await save(date(2026, 10, 9), (*week[:6], Decimal(0)))
    await save(date(2026, 10, 8), week)
    await save(date(2026, 10, 9), split_week(7000))
    await save(date(2026, 10, 9), week, UNKNOWN)
    started = await save(date(2026, 10, 9), week)
    await save(date(2026, 10, 9), days(1100, 1000, 1000, 1000, 1000, 1500, 500))
    later = await save(date(2026, 10, 20), days("1200.50", 1200, 1200, 1200, 1200, 1500, 500))
    await save(date(2026, 10, 25), days("1200.50", 1200, 1200, 1200, 1200, 1500, 500))
    await save(date(2026, 10, 27), days(900, 900, 900, 900, 900, 900, 900))
    await world.record(world.setup.list_target_sets(VehicleQuery(owner, kda)))
    await world.record(world.setup.list_target_sets(VehicleQuery(owner, UNKNOWN)))
    await world.record(world.setup.list_vehicles(VehicleListQuery(owner, None, 1, 25)))
    await remove(later.id)
    await remove(later.id)
    await remove(started.id)
    await remove(UNKNOWN)
    await world.record(world.setup.list_target_sets(VehicleQuery(owner, kda)))
    await world.record(world.setup.list_vehicles(VehicleListQuery(owner, None, 1, 25)))
    await world.history("vehicles")


async def arrange_main_categories(world: SetupWorld) -> None:
    owner = world.tenancy.owner

    async def create_main(name: str) -> Any:
        return await world.record(
            world.setup.create_expense_main_category(MainCategorySave(owner, None, name))
        )

    async def rename_main(main: UUID, name: str) -> None:
        await world.record(
            world.setup.rename_expense_main_category(MainCategorySave(owner, main, name))
        )

    async def category(
        category_id: UUID | None, name: str, main: UUID | None, given: bool = True
    ) -> Any:
        command = ExpenseCategorySave(owner, category_id, name, main, given)
        if category_id is None:
            return await world.record(world.setup.create_expense_category(command))
        return await world.record(world.setup.update_expense_category(command))

    await world.record(world.setup.list_expense_main_categories(SetupPageQuery(owner, 1, 25)))
    repairs = await create_main(" Repairs ")
    await create_main("REPAIRS")
    await create_main("   ")
    finance = await create_main("Finance")
    await rename_main(repairs.id, "Repairs")
    await rename_main(repairs.id, "finance")
    await rename_main(UNKNOWN, "Fuel")
    await rename_main(repairs.id, "Repairs and service")
    tyres = await category(None, "Tyres", repairs.id)
    await category(None, "Loans", UNKNOWN)
    loans = await category(None, "Loans", None)
    await world.record(
        world.setup.create_expense_item(ExpenseItemCreate(owner, tyres.id, "Front pair"))
    )
    await category(tyres.id, "Tyres", repairs.id)
    await category(tyres.id, "Tyres and tubes", None, False)
    await category(loans.id, "Loans", finance.id)
    await category(loans.id, "Bank loans", UNKNOWN)
    await category(tyres.id, "Tyres and tubes", None)
    await category(loans.id, "Bank loans", finance.id)
    await world.record(world.setup.list_expense_main_categories(SetupPageQuery(owner, 1, 25)))
    await world.record(world.setup.list_expense_main_categories(SetupPageQuery(owner, 2, 1)))
    await world.record(world.setup.list_expense_categories(SetupPageQuery(owner, 1, 25)))
    await world.history("expenses")


async def revise_a_scheduled_item(world: SetupWorld) -> None:
    owner = world.tenancy.owner
    category = await world.record(
        world.setup.create_expense_category(
            ExpenseCategorySave(owner, None, "Insurance", None, False)
        )
    )
    cover = await world.record(
        world.setup.create_expense_item(
            ExpenseItemCreate(owner, category.id, "Comprehensive cover")
        )
    )
    north = await world.company("North Star")
    kda = await world.vehicle(north, "KDA 482M", date(2026, 10, 1), 7000)
    kdb = await world.vehicle(north, "KDB 111A", date(2026, 10, 1), 7000)

    def cost(amount: int, *shares: tuple[UUID, int], start: date = date(2026, 10, 1)) -> Any:
        return RecurringDefinition(
            name="Ignored for a cost",
            kind=1,
            amount=Decimal(amount),
            frequency=3,
            day=15,
            last_day=False,
            start=start,
            end=None,
            allocations=tuple(Share(v, Decimal(a)) for v, a in shares),
            expense_item_id=cover.id,
            note=None,
            month=None,
        )

    async def save(item: UUID | None, definition: Any, reason: str | None = None) -> Any:
        command = RecurringSave(owner, item, definition, reason)
        if item is None:
            return await world.record(world.setup.create_recurring(command))
        return await world.record(world.setup.revise_recurring(command))

    item = await save(None, cost(6000, (kda, 6000)))
    await save(item.id, cost(6000, (kda, 6000)))
    await save(item.id, cost(6500, (kda, 6000)))
    await save(item.id, cost(6500, (kdb, 6500)), "Moved to the new bus")
    await save(item.id, cost(6500, (kdb, 6500), start=date(2026, 10, 20)))
    await save(UNKNOWN, cost(6500, (kdb, 6500)))
    saving = RecurringDefinition(
        name=" Owner savings ",
        kind=2,
        amount=Decimal(1000),
        frequency=2,
        day=5,
        last_day=False,
        start=date(2026, 10, 12),
        end=None,
        allocations=(Share(kda, Decimal(1000)),),
        expense_item_id=None,
        note=None,
        month=None,
    )
    savings = await save(None, saving)
    await save(savings.id, replace(saving, note=" Every Friday ", start=date(2026, 10, 15)))
    await world.record(
        world.setup.stop_recurring(RecurringStop(owner, savings.id, False, "Paid off"))
    )
    await world.record(
        world.setup.stop_recurring(RecurringStop(owner, savings.id, True, "Paid off"))
    )
    await world.record(world.setup.cancel_recurring_stop(RecurringCancelStop(owner, savings.id)))
    for kind, company, status in (
        (None, None, None),
        ("savings", None, "stopped"),
        ("cost", north, "running"),
        ("", UNKNOWN, "all"),
        ("fuel", None, None),
        (None, None, "paused"),
    ):
        query = RecurringListQuery(owner, kind, company, status, 1, 25)
        await world.record(world.setup.list_recurring(query))
    await world.history("recurring")


async def delete_an_investment(world: SetupWorld) -> None:
    owner = world.tenancy.owner
    north = await world.company("North Star")
    kda = await world.vehicle(north, "KDA 482M", date(2026, 10, 1), 7000)

    def entry(day: int, description: str, amount: str) -> InvestmentDetails:
        return InvestmentDetails(date(2026, 10, day), description, Decimal(amount))

    purchase = await world.record(
        world.setup.create_investment(InvestmentCreate(owner, kda, entry(2, "Purchase", "15000")))
    )
    deposit = await world.record(
        world.setup.create_investment(InvestmentCreate(owner, kda, entry(3, "Deposit", "5000.25")))
    )
    await world.record(world.setup.get_investment(VehicleQuery(owner, kda)))
    for details in (entry(3, " Deposit ", "5000.25"), entry(3, "Deposit", "5000.50")):
        await world.record(
            world.setup.update_investment(InvestmentUpdate(owner, deposit.id, details))
        )
    for _ in range(2):
        await world.record(world.setup.delete_investment(InvestmentRemoval(owner, purchase.id)))
    await world.record(
        world.setup.update_investment(
            InvestmentUpdate(owner, purchase.id, entry(2, "Purchase", "1"))
        )
    )
    await world.record(world.setup.get_investment(VehicleQuery(owner, kda)))
    await world.history("investment")


async def pause_and_run_scheduled_items(world: SetupWorld) -> None:
    """A saving with a revenue rule and an opening, a plain saving and a weekly cost: their
    runs, the month summary and the list, around a pause and a resume."""
    owner = world.tenancy.owner
    category = await world.record(
        world.setup.create_expense_category(ExpenseCategorySave(owner, None, "Fees", None, False))
    )
    fees = await world.record(
        world.setup.create_expense_item(ExpenseItemCreate(owner, category.id, "Stage fees"))
    )
    north = await world.company("North Star")
    kda = await world.vehicle(north, "KDA 482M", date(2026, 9, 1), 7000)

    def item(
        name: str, kind: int, frequency: int, day: int | None, **more: Any
    ) -> RecurringDefinition:
        return RecurringDefinition(
            name=name,
            kind=kind,
            amount=Decimal(300),
            frequency=frequency,
            day=day,
            last_day=False,
            start=date(2026, 10, 1),
            end=None,
            allocations=(Share(kda, Decimal(300)),),
            expense_item_id=fees.id if kind == 1 else None,
            note=None,
            month=None,
            **more,
        )

    ruled = await world.record(
        world.setup.create_recurring(
            RecurringSave(
                owner,
                None,
                item(
                    "Fuel fund",
                    2,
                    1,
                    None,
                    condition=SavingCondition(Decimal(5000), 1),
                    opening=SavingOpening(date(2026, 10, 1), (OpeningAmount(kda, Decimal(800)),)),
                ),
                None,
            )
        )
    )
    plain = await world.record(
        world.setup.create_recurring(
            RecurringSave(owner, None, item("Owner savings", 2, 2, 5), None)
        )
    )
    cost = await world.record(
        world.setup.create_recurring(RecurringSave(owner, None, item("Fees", 1, 2, 5), None))
    )
    for target in (ruled.id, plain.id, cost.id, UNKNOWN):
        await world.record(world.setup.recurring_runs(RecurringRunsQuery(owner, target)))
    await world.record(world.setup.recurring_month(owner))
    await world.record(world.setup.pause_recurring(RecurringPause(owner, plain.id)))
    await world.record(world.setup.pause_recurring(RecurringPause(owner, plain.id)))
    await world.record(world.setup.pause_recurring(RecurringPause(owner, UNKNOWN)))
    await world.record(
        world.setup.list_recurring(RecurringListQuery(owner, None, None, None, 1, 25))
    )
    await world.record(world.setup.recurring_month(owner))
    await world.record(world.setup.resume_recurring(RecurringPause(owner, plain.id)))
    await world.record(world.setup.resume_recurring(RecurringPause(owner, plain.id)))
    await world.record(world.setup.recurring_runs(RecurringRunsQuery(owner, plain.id)))
    await world.record(
        world.setup.list_recurring(RecurringListQuery(owner, None, None, None, 1, 25))
    )
    await world.history("recurring")


@dataclass(frozen=True)
class SetupCase:
    name: str
    run: Callable[[SetupWorld], Awaitable[None]]


CASES = (
    SetupCase("rename_a_company", rename_a_company),
    SetupCase("create_and_update_a_vehicle", create_and_update_a_vehicle),
    SetupCase("set_and_remove_targets", set_and_remove_targets),
    SetupCase("arrange_main_categories", arrange_main_categories),
    SetupCase("revise_a_scheduled_item", revise_a_scheduled_item),
    SetupCase("delete_an_investment", delete_an_investment),
    SetupCase("pause_and_run_scheduled_items", pause_and_run_scheduled_items),
)
