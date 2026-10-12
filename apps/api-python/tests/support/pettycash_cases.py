"""Parity cases for ``FakePettyCashRepository``: each case runs the same calls against the
fake and against ``PettyCashRoutines`` on PostgreSQL, arranging the fleet and the expense
catalogue through the setup repository and the people through the tenancy repository of the
same world, and reading the change log there; the two observations must be equal
(``tenancy_cases.normalised``).

A refusal is observed with its detail: a 409's ``current`` entry is read as the routine's
document would be (instants compared as instants, whatever zone the database writes them in),
the float guard's ``balance_after`` and the back-dating limit's ``earliest`` as sent. Entries
carry client-chosen ids, so the orders that end on the id are the same in both worlds. The
business date is the calendar date of ``tenancy_cases.NOW`` (2026-10-09, a Friday); every
call runs a minute after the one before."""

from __future__ import annotations

import dataclasses
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from xcode_api.application.repositories import (
    PettyCashRepository,
    SetupRepository,
    TenancyRepository,
)
from xcode_api.db.types import document
from xcode_api.domain.errors import DomainRefusal
from xcode_api.domain.pettycash import (
    PettyCashCreate,
    PettyCashDayApproval,
    PettyCashDecision,
    PettyCashEntriesApproval,
    PettyCashEntry,
    PettyCashEntryQuery,
    PettyCashLine,
    PettyCashOptionsQuery,
    PettyCashOverviewQuery,
    PettyCashTicked,
    PettyCashUpdate,
)
from xcode_api.domain.setup import ExpenseCategorySave, ExpenseItemCreate
from xcode_api.domain.tenancy import PersonDetails, PersonSave, TenantContext

from .fakes import FakePettyCashRepository, FakeSetupRepository, expand_permissions, role_rights
from .revenue_cases import comparable
from .scenario import Conn
from .setup_cases import SetupWorld
from .setup_cases import database_world as setup_database_world
from .setup_cases import fake_world as setup_fake_world
from .tenancy_cases import NOW

TODAY = date(2026, 10, 9)
UNKNOWN = UUID(int=1)
REVIEWER_RIGHTS = (
    "pettycash.view_all",
    "pettycash.issue",
    "pettycash.credit",
    "pettycash.approve_item",
    "pettycash.approve_day",
    "pettycash.send_back",
    "pettycash.reject",
    "pettycash.reopen",
    "pettycash.delete",
    "pettycash.delete_approved",
    "pettycash.delete_cash",
    "dash.pettycash",
)


def entry_id(n: int) -> UUID:
    return UUID(f"00000000-0000-4000-8000-{n:012d}")


def _observed(detail: dict[str, Any]) -> dict[str, Any]:
    seen = dict(detail)
    current = seen.get("current")
    if current is not None:
        record = document(current, PettyCashEntry, "current")
        seen["current"] = dataclasses.asdict(record)
    return comparable(seen)


@dataclass
class PettyCashWorld:
    pettycash: PettyCashRepository
    setup: SetupWorld
    minutes: int = field(default=0)

    @property
    def seen(self) -> list[Any]:
        return self.setup.seen

    @property
    def owner(self) -> TenantContext:
        return self.setup.tenancy.owner

    def later(self, who: TenantContext) -> TenantContext:
        self.minutes += 1
        return replace(who, now=NOW + timedelta(minutes=self.minutes))

    async def record(self, call: Awaitable[Any]) -> Any:
        detail: dict[str, Any] = {}

        async def watched() -> Any:
            try:
                return await call
            except DomainRefusal as refusal:
                detail.update(refusal.detail)
                raise

        result = await self.setup.record(watched())
        if detail:
            self.seen.append(("detail", _observed(detail)))
        return result

    async def person(
        self, first: str, last: str, n: int, role: str, extra: tuple[str, ...] = (), **more: Any
    ) -> TenantContext:
        details = PersonDetails(
            first_name=first,
            last_name=last,
            email=f"{first.lower()}@example.com",
            phone_number=f"07220001{n:02d}",
            role=role,
            scope_mode="all",
            company_ids=(),
            vehicle_ids=(),
            permissions=expand_permissions((*role_rights(role), *extra)),
            approval_limit=more.get("approval_limit"),
        )
        tenancy = self.setup.tenancy
        created = await tenancy.record(
            tenancy.repository.create_person(PersonSave(self.owner, None, details, None))
        )
        return replace(self.owner, actor_id=UUID(str(created.id)))

    async def catalogue_item(self, category: str, item: str) -> UUID:
        setup = self.setup.setup
        made = await self.record(
            setup.create_expense_category(
                ExpenseCategorySave(self.owner, None, category, None, False)
            )
        )
        added = await self.record(
            setup.create_expense_item(ExpenseItemCreate(self.owner, UUID(str(made.id)), item))
        )
        return UUID(str(added.id))


def fake_world() -> PettyCashWorld:
    setup = setup_fake_world()
    assert isinstance(setup.setup, FakeSetupRepository)
    return PettyCashWorld(FakePettyCashRepository(setup.setup), setup)


def database_world(
    pettycash: PettyCashRepository,
    setup: SetupRepository,
    tenancy: TenancyRepository,
    operator: Conn,
) -> PettyCashWorld:
    return PettyCashWorld(pettycash, setup_database_world(setup, tenancy, operator))


def line(
    kind: str | None,
    day: date | None,
    amount: Decimal | int | str | None,
    *,
    holder: UUID | None = None,
    vehicle: UUID | None = None,
    item: UUID | None = None,
    units: Decimal | int | str | None = None,
    payee: str | None = None,
    note: str | None = None,
) -> PettyCashLine:
    return PettyCashLine(
        kind,
        day,
        None if amount is None else Decimal(amount),
        holder,
        vehicle,
        item,
        None if units is None else Decimal(units),
        payee,
        note,
        False,
    )


async def keep_a_float(world: PettyCashWorld) -> None:
    """Cash given, expenses recorded, refused, reviewed, changed and removed by a float keeper,
    a reviewer and the owner, then every read of the result and the change log."""
    north = await world.setup.company("North Star")
    kda = await world.setup.vehicle(north, "KDA 482M", date(2026, 10, 1), 7000)
    kdb = await world.setup.vehicle(north, "KDB 111A", date(2026, 10, 1), 3500)
    tyres = await world.catalogue_item("Repairs", "Tyres")
    clerk = await world.person("Wanjiru", "Kamau", 1, "Fleet manager")
    reviewer = await world.person(
        "Peter", "Otieno", 2, "Office admin", REVIEWER_RIGHTS, approval_limit=Decimal(5000)
    )
    owner = world.owner
    stranger = replace(owner, actor_id=UNKNOWN)
    pc = world.pettycash

    async def create(who: TenantContext, n: int | None, entry: PettyCashLine) -> None:
        chosen = None if n is None else entry_id(n)
        await world.record(pc.create(PettyCashCreate(world.later(who), chosen, entry)))

    async def update(who: TenantContext, n: int, entry: PettyCashLine, version: int) -> None:
        command = PettyCashUpdate(world.later(who), entry_id(n), entry, version)
        await world.record(pc.update(command))

    def decision(who: TenantContext, n: int, version: int | None, text: str | None = None) -> Any:
        return PettyCashDecision(world.later(who), entry_id(n), version, text)

    def expense(day: date, amount: Any, vehicle: UUID = kda, **more: Any) -> PettyCashLine:
        return line("expense", day, amount, vehicle=vehicle, item=tyres, **more)

    clerk_id = clerk.actor_id
    await create(owner, 1, line("cash", TODAY - timedelta(days=2), 1000, holder=clerk_id))
    await create(owner, 1, line("cash", TODAY, 5, holder=clerk_id))
    await create(reviewer, 1, line("cash", TODAY, 5, holder=clerk_id))
    await create(clerk, 2, expense(TODAY - timedelta(days=1), 150, units=2, note=" new tyres "))
    await create(clerk, 3, expense(TODAY, 50, vehicle=kdb))
    await create(clerk, 4, line(" bogus ", TODAY, 10))
    await create(clerk, 4, line("expense", TODAY, 10, item=tyres))
    await create(clerk, 4, expense(TODAY, "10.005"))
    await create(clerk, 4, expense(TODAY, 10, units="1.5", payee="Shell"))
    await create(clerk, 4, expense(TODAY + timedelta(days=1), 10))
    await create(clerk, 4, expense(TODAY - timedelta(days=10), 10))
    await create(clerk, 4, expense(TODAY, 10, holder=owner.actor_id))
    await create(clerk, 4, expense(TODAY, 10, vehicle=UNKNOWN))
    await create(clerk, 4, line("cash", TODAY, 10, holder=clerk_id))
    await create(reviewer, 4, line("cash", TODAY, -700, holder=clerk_id))
    await create(reviewer, 4, line("cash", TODAY, -100, holder=reviewer.actor_id))
    await create(owner, 5, line("credit", TODAY, 25, holder=clerk_id, payee=" Shell "))

    await world.record(pc.approve(decision(reviewer, 2, 1)))
    await world.record(pc.approve(decision(reviewer, 2, 1)))
    await world.record(pc.approve(decision(reviewer, 3, 5)))
    await world.record(pc.approve(decision(reviewer, 1, 1)))
    await world.record(pc.approve(decision(clerk, 3, 1)))
    await world.record(pc.send_back(decision(reviewer, 3, 1, "  ")))
    await world.record(pc.send_back(decision(reviewer, 3, 1, " Attach the receipt ")))
    await world.record(pc.send_back(decision(reviewer, 3, 1, "Attach the receipt")))
    await update(clerk, 3, expense(TODAY, 50, vehicle=kdb), 2)
    await world.record(pc.reject(decision(reviewer, 3, 3, "Not a company cost")))
    await world.record(pc.reopen(decision(reviewer, 3, 3, "Check again")))
    await world.record(pc.reopen(decision(reviewer, 3, 4, "Check again")))
    await update(clerk, 3, expense(TODAY, 60, vehicle=kdb), 4)
    await update(clerk, 3, expense(TODAY, 60, vehicle=kdb), 5)
    await update(clerk, 3, line("cash", TODAY, 60), 6)
    await update(clerk, 2, expense(TODAY, 1), 2)
    await create(clerk, 6, expense(TODAY, 40))
    await create(clerk, 7, expense(TODAY, 7000))
    ticked = (PettyCashTicked(entry_id(3), 6), PettyCashTicked(entry_id(2), 2))
    await world.record(pc.approve_entries(PettyCashEntriesApproval(world.later(reviewer), ())))
    await world.record(pc.approve_entries(PettyCashEntriesApproval(world.later(reviewer), ticked)))
    day = PettyCashDayApproval(world.later(reviewer), TODAY, None, None)
    await world.record(pc.approve_day(day))
    await world.record(pc.remove(decision(reviewer, 5, 1)))
    await world.record(pc.remove(decision(reviewer, 5, 1, " Recorded twice ")))
    await world.record(pc.remove(decision(clerk, 6, 2)))
    await world.record(pc.remove(decision(stranger, 6, 2)))
    await world.record(pc.remove(decision(reviewer, 1, 1, "Given twice")))

    for who in (owner, clerk, reviewer):
        query = PettyCashOverviewQuery(world.later(who), None, None, None, None, None)
        await world.record(pc.overview(query))
    week = PettyCashOverviewQuery(world.later(reviewer), TODAY, " week ", clerk_id, None, None)
    await world.record(pc.overview(week))
    span = PettyCashOverviewQuery(
        world.later(owner), None, None, None, TODAY - timedelta(days=1), TODAY
    )
    await world.record(pc.overview(span))
    await world.record(
        pc.overview(PettyCashOverviewQuery(world.later(owner), None, "year", None, None, None))
    )
    for who, kinds, statuses, text in (
        (owner, None, None, None),
        (reviewer, ("expense", "cash"), ("approved",), None),
        (owner, None, None, "tyre"),
        (clerk, ("bogus",), None, None),
    ):
        listing = PettyCashEntryQuery(
            world.later(who), None, None, None, kinds, statuses, text, 1, 100
        )
        await world.record(pc.entries(listing))
    for who in (owner, clerk, reviewer):
        await world.record(pc.options(PettyCashOptionsQuery(world.later(who), None)))
        await world.record(pc.dashboard(world.later(who)))
    await world.setup.history("pettycash")


@dataclass(frozen=True)
class PettyCashCase:
    name: str
    run: Callable[[PettyCashWorld], Awaitable[None]]


CASES = (PettyCashCase("keep_a_float", keep_a_float),)
