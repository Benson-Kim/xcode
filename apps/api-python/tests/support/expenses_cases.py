"""Parity cases for ``FakeExpensesRepository``: each case runs the same calls against the fake
and against ``ExpensesRoutines`` on PostgreSQL, arranging the fleet, the catalogue, a scheduled
cost and the people through the repositories of the petty-cash world (whose approved expenses
the ledger lists) and reading the change log there; the two observations must be equal
(``tenancy_cases.normalised``).

A refusal is observed with its detail: a 409's ``current`` row is read as the routine's
document would be. Purchases carry client-chosen ids; the rows of a purchase over several
vehicles get server ids, so they are observed through the ledger (ordered by day, source and
registration, ties broken by what the rows hold) and the retried purchase answers them,
never compared by id themselves. The business date is the calendar date of
``tenancy_cases.NOW`` (2026-10-09, a Friday); every call runs a minute after the one before."""

from __future__ import annotations

import dataclasses
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from xcode_api.application.repositories import (
    ExpensesRepository,
    PettyCashRepository,
    SetupRepository,
    TenancyRepository,
)
from xcode_api.db.types import document
from xcode_api.domain.errors import DomainRefusal
from xcode_api.domain.expenses import (
    ExpenseAllocation,
    ExpenseChange,
    ExpenseLedger,
    ExpenseLedgerQuery,
    ExpenseLedgerRow,
    ExpenseOptionsQuery,
    ExpensePurchase,
    ExpenseRecorded,
    ExpenseRemoval,
)
from xcode_api.domain.pettycash import PettyCashCreate, PettyCashDecision
from xcode_api.domain.setup import RecurringDefinition, RecurringSave, Share
from xcode_api.domain.tenancy import TenantContext

from .fakes import FakeExpensesRepository, FakePettyCashRepository
from .pettycash_cases import REVIEWER_RIGHTS, PettyCashWorld, entry_id, line
from .pettycash_cases import database_world as pettycash_database_world
from .pettycash_cases import fake_world as pettycash_fake_world
from .revenue_cases import comparable
from .scenario import Conn

TODAY = date(2026, 10, 9)
UNKNOWN = UUID(int=1)


def purchase_id(n: int) -> UUID:
    return UUID(f"00000000-0000-4000-9000-{n:012d}")


def _observed(detail: dict[str, Any]) -> dict[str, Any]:
    seen = dict(detail)
    current = seen.get("current")
    if current is not None:
        record = document(current, ExpenseLedgerRow, "current")
        seen["current"] = dataclasses.asdict(_without_ids(record))
    return comparable(seen)


def _without_ids(row: ExpenseLedgerRow) -> ExpenseLedgerRow:
    """A row of a purchase over several vehicles has a server id in each world."""
    group = None if row.group is None else replace(row.group, id=UUID(int=0))
    return replace(row, group=group)


@dataclass
class ExpensesWorld:
    expenses: ExpensesRepository
    pettycash: PettyCashWorld
    minutes: int = field(default=0)
    rows: dict[str, UUID] = field(default_factory=dict)

    @property
    def seen(self) -> list[Any]:
        return self.pettycash.seen

    @property
    def owner(self) -> TenantContext:
        return self.pettycash.owner

    def later(self, who: TenantContext) -> TenantContext:
        return self.pettycash.later(who)

    async def record(self, call: Awaitable[Any]) -> Any:
        detail: dict[str, Any] = {}

        async def watched() -> Any:
            try:
                return await call
            except DomainRefusal as refusal:
                detail.update(refusal.detail)
                raise

        result = await self.pettycash.setup.record(_anonymous(watched()))
        if detail:
            self.seen.append(("detail", _observed(detail)))
        return result

    async def ledger(self, who: TenantContext, **more: Any) -> ExpenseLedger | None:
        query = ExpenseLedgerQuery(
            self.later(who),
            more.get("first", TODAY - timedelta(days=8)),
            more.get("last", TODAY),
            more.get("source"),
            more.get("q"),
            more.get("page", 1),
            more.get("size", 100),
        )
        ledger: ExpenseLedger | None = await self.record(
            _named_rows(self, self.expenses.ledger(query))
        )
        return ledger


async def _anonymous(call: Awaitable[Any]) -> Any:
    """Server-made row ids are replaced by their position in the observation."""
    result = await call
    if isinstance(result, ExpenseRecorded) and len(result.ids) > 1:
        return replace(result, ids=tuple(UUID(int=n) for n in range(1, len(result.ids) + 1)))
    if isinstance(result, ExpenseLedger):
        items = []
        ordered = sorted(result.items, key=_tie_free)
        for n, row in enumerate(ordered, start=1):
            plain = _without_ids(row)
            if row.source.value == "central" and row.group is not None:
                plain = replace(plain, id=f"part-{n}")
            items.append(plain)
        return replace(result, items=tuple(items))
    return result


def _tie_free(row: ExpenseLedgerRow) -> tuple[Any, ...]:
    """The ledger's order with ties of the same day, source and vehicle broken by what the
    row holds instead of its id, which the server chose differently in each world."""
    sources = {"central": 1, "pettycash": 2, "scheduled": 3}
    return (
        -row.entry_date.toordinal(),
        sources[row.source.value],
        row.registration.encode(),
        row.total,
        row.note or "",
        row.recorded_by_name or "",
    )


async def _named_rows(world: ExpensesWorld, call: Awaitable[ExpenseLedger]) -> ExpenseLedger:
    """Remembers each central row of a shared purchase by registration and date, so later steps
    can change it in either world."""
    ledger = await call
    for row in ledger.items:
        if row.source.value == "central":
            world.rows[_key(row.registration, row.entry_date, row.total)] = UUID(row.id)
    return ledger


def _key(registration: str, day: date, total: Decimal) -> str:
    return f"{registration} {day.isoformat()} {int(total * 100)}"


def fake_world() -> ExpensesWorld:
    pettycash = pettycash_fake_world()
    assert isinstance(pettycash.pettycash, FakePettyCashRepository)
    fake = FakeExpensesRepository(pettycash.pettycash.setup, pettycash.pettycash)
    return ExpensesWorld(fake, pettycash)


def database_world(
    expenses: ExpensesRepository,
    pettycash: PettyCashRepository,
    setup: SetupRepository,
    tenancy: TenancyRepository,
    operator: Conn,
) -> ExpensesWorld:
    return ExpensesWorld(expenses, pettycash_database_world(pettycash, setup, tenancy, operator))


def parts(*pairs: tuple[UUID | None, Any]) -> tuple[ExpenseAllocation, ...]:
    return tuple(ExpenseAllocation(v, None if a is None else Decimal(str(a))) for v, a in pairs)


async def keep_the_ledger(world: ExpensesWorld) -> None:
    """Purchases recorded, refused, retried, changed and removed by a recorder, a corrector and
    the owner, a petty-cash expense approved and a scheduled cost running, then the ledger by
    source and search, the options and the change log."""
    pw = world.pettycash
    north = await pw.setup.company("North Star")
    south = await pw.setup.company("South Star")
    kda = await pw.setup.vehicle(north, "KDA 482M", date(2026, 10, 1), 7000)
    kdb = await pw.setup.vehicle(north, "KDB 111A", date(2026, 10, 1), 3500)
    kdc = await pw.setup.vehicle(south, "KDC 222C", date(2026, 10, 3), 3500)
    tyres = await pw.catalogue_item("Repairs", "Tyres")
    clerk = await pw.person("Wanjiru", "Kamau", 1, "Fleet manager", ("expenses.capture",))
    admin = await pw.person(
        "Peter", "Otieno", 2, "Office admin", REVIEWER_RIGHTS, approval_limit=Decimal(5000)
    )
    owner = world.owner
    stranger = replace(owner, actor_id=UNKNOWN)
    ex = world.expenses

    await pw.record(
        pw.setup.setup.create_recurring(
            RecurringSave(
                owner,
                None,
                RecurringDefinition(
                    name="Ignored for a cost",
                    kind=1,
                    amount=Decimal(600),
                    frequency=3,
                    day=5,
                    last_day=False,
                    start=date(2026, 10, 1),
                    end=None,
                    allocations=(Share(kda, Decimal(400)), Share(kdc, Decimal(200))),
                    expense_item_id=tyres,
                    note="Monthly tyre plan",
                    month=None,
                ),
                None,
            )
        )
    )
    await pw.record(
        pw.pettycash.create(
            PettyCashCreate(
                pw.later(owner), entry_id(1), line("cash", TODAY, 500, holder=clerk.actor_id)
            )
        )
    )
    await pw.record(
        pw.pettycash.create(
            PettyCashCreate(
                pw.later(clerk),
                entry_id(2),
                line("expense", TODAY - timedelta(days=1), 120, vehicle=kdb, item=tyres),
            )
        )
    )
    await pw.record(pw.pettycash.approve(PettyCashDecision(pw.later(admin), entry_id(2), 1, None)))

    async def buy(
        who: TenantContext,
        n: int | None,
        units: Any,
        amount: Any,
        shares: tuple[ExpenseAllocation, ...] | None,
        *,
        day: date = TODAY,
        item: UUID | None = tyres,
        note: str | None = None,
    ) -> Any:
        command = ExpensePurchase(
            world.later(who),
            None if n is None else purchase_id(n),
            day,
            item,
            Decimal(str(units)),
            Decimal(str(amount)),
            note,
            shares,
        )
        return await world.record(ex.record(command))

    await buy(owner, 1, 2, 100, parts((kda, 100), (kdb, 100)), note=" Front pair ")
    await buy(owner, 1, 1, 5, parts((kda, 5)))
    await buy(clerk, 1, 1, 5, parts((kda, 5)))
    await buy(clerk, 2, 1, 300, parts((kda, 300)))
    await buy(clerk, 3, 1, 300, parts((kdc, 300)))
    await buy(admin, 4, 3, "33.33", parts((kda, "33.34"), (kdb, "33.33"), (kdc, "33.32")))
    await buy(admin, 4, 1, 100, parts((kda, "33.34"), (kdb, "33.33"), (kdc, "33.33")))
    await buy(
        admin, 5, 1, -90, parts((kda, -30), (kdb, -30), (kdc, -30)), day=TODAY - timedelta(days=2)
    )
    for refused in (
        parts(),
        parts((kda, 50), (kda, 50)),
        parts((None, 100)),
        parts((kda, "50.005"), (kdb, "49.995")),
        parts((kda, 150), (kdb, -50)),
        parts((kda, 60), (kdb, 50)),
    ):
        await buy(admin, 6, 1, 100, refused)
    await buy(admin, 6, 1, 0, parts((kda, 0)))
    await buy(admin, 6, 1, 100, parts((kda, 100)), day=TODAY + timedelta(days=1))
    await buy(admin, 6, 1, 100, parts((UNKNOWN, 100)))
    await buy(admin, 6, 1, 100, parts((kdc, 100)), day=date(2026, 10, 2))
    await buy(admin, 6, 1, 100, parts((kda, 100)), item=UNKNOWN)
    await buy(stranger, 6, 1, 100, parts((kda, 100)))

    await world.ledger(owner)
    own = purchase_id(2)

    async def change(who: TenantContext, row: UUID, version: int | None, **more: Any) -> None:
        command = ExpenseChange(
            world.later(who),
            row,
            more.get("day", TODAY),
            more.get("vehicle", kda),
            more.get("item", tyres),
            Decimal(str(more.get("units", 1))),
            Decimal(str(more.get("amount", 300))),
            more.get("note"),
            version,
        )
        await world.record(ex.change(command))

    await change(clerk, own, None)
    await change(clerk, own, 1, note="Retread")
    await change(clerk, own, 1, note="Retread again")
    await change(clerk, own, 2, day=TODAY - timedelta(days=1))
    await change(clerk, purchase_id(3), 1, vehicle=kdc, note="South")
    await change(clerk, world.rows[_key("KDA 482M", TODAY, Decimal(100))], 1, units=2, amount=50)
    shared = world.rows[_key("KDB 111A", TODAY, Decimal(100))]
    await change(admin, shared, 1, vehicle=kdb, units=1, amount=100, note="Rear pair")
    await change(admin, shared, 2, vehicle=kda, units=1, amount=100, note="Rear pair")
    await change(admin, shared, 2, vehicle=kdc, units=2, amount=50, day=TODAY - timedelta(days=1))
    await change(admin, UNKNOWN, 1)
    await change(admin, own, 2, amount=0)

    async def remove(
        who: TenantContext, row: UUID, version: int | None, reason: str | None
    ) -> None:
        await world.record(ex.remove(ExpenseRemoval(world.later(who), row, version, reason)))

    await remove(admin, own, 2, "  ")
    await remove(admin, own, 2, "Bought twice")
    await remove(admin, own, 3, " Bought twice ")
    await remove(admin, own, 4, "Again")

    await world.ledger(owner)
    await world.ledger(clerk)
    await world.ledger(owner, source=" Central ")
    await world.ledger(owner, source="scheduled", q="TYRE")
    await world.ledger(owner, q="wanjiru")
    await world.ledger(owner, q="retread")
    await world.ledger(admin, source="scheduled", page=2, size=1)
    await world.ledger(owner, first=TODAY, last=TODAY - timedelta(days=1))
    await world.ledger(owner, source="fuel")
    for who, day in ((owner, None), (clerk, None), (admin, date(2026, 10, 2))):
        await world.record(ex.options(ExpenseOptionsQuery(world.later(who), day)))
    await world.record(
        ex.options(ExpenseOptionsQuery(world.later(owner), TODAY + timedelta(days=1)))
    )
    await pw.setup.history("centralexpenses")


@dataclass(frozen=True)
class ExpensesCase:
    name: str
    run: Callable[[ExpensesWorld], Awaitable[None]]


CASES = (ExpensesCase("keep_the_ledger", keep_the_ledger),)
