"""Parity cases for ``FakeRevenueRepository``: each case runs the same calls against the fake
and against ``RevenueRoutines`` on PostgreSQL, arranging the fleet through the setup repository
and reading the change log through the tenancy repository of the same world; the two
observations must be equal (``tenancy_cases.normalised``).

A refusal is observed with its detail, so a stale save's ``current`` cell is compared too. The
business date is the calendar date of ``tenancy_cases.NOW`` (2026-10-09); every call runs a
minute after the one before, and a call a day later sees the next business date."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from xcode_api.application.repositories import RevenueRepository, SetupRepository, TenancyRepository
from xcode_api.domain.errors import DomainRefusal
from xcode_api.domain.revenue import RevenueCapture, RevenueDashboardQuery, RevenueWeekQuery
from xcode_api.domain.setup import VehicleRetirement, VehicleReturn
from xcode_api.domain.tenancy import PersonSave, SettingsSave, TenantContext

from .fakes import FakeRevenueRepository, FakeSetupRepository
from .scenario import Conn
from .setup_cases import SetupWorld
from .setup_cases import database_world as setup_database_world
from .setup_cases import fake_world as setup_fake_world
from .tenancy_cases import NOW, jane

UNKNOWN = UUID(int=1)
TODAY = date(2026, 10, 9)


def comparable(value: Any) -> Any:
    """A refusal detail with its JSON numbers read as decimals, as the routine's document is."""
    if isinstance(value, float):
        return Decimal(repr(value))
    if isinstance(value, dict):
        return {key: comparable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [comparable(item) for item in value]
    return value


@dataclass
class RevenueWorld:
    revenue: RevenueRepository
    setup: SetupWorld
    minutes: int = field(default=0)

    @property
    def seen(self) -> list[Any]:
        return self.setup.seen

    @property
    def owner(self) -> TenantContext:
        return self.setup.tenancy.owner

    def later(self, who: TenantContext, days: int = 0) -> TenantContext:
        self.minutes += 1
        return replace(who, now=NOW + timedelta(days=days, minutes=self.minutes))

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
            self.seen.append(("detail", comparable(detail)))
        return result

    async def clerk(self) -> TenantContext:
        tenancy = self.setup.tenancy
        created = await tenancy.record(
            tenancy.repository.create_person(PersonSave(self.owner, None, jane(), None))
        )
        return replace(self.owner, actor_id=UUID(str(created.id)))


def fake_world() -> RevenueWorld:
    setup = setup_fake_world()
    assert isinstance(setup.setup, FakeSetupRepository)
    return RevenueWorld(FakeRevenueRepository(setup.setup), setup)


def database_world(
    revenue: RevenueRepository, setup: SetupRepository, tenancy: TenancyRepository, operator: Conn
) -> RevenueWorld:
    return RevenueWorld(revenue, setup_database_world(setup, tenancy, operator))


async def capture_a_week(world: RevenueWorld) -> None:
    owner = world.owner
    north = await world.setup.company("North Star")
    kda = await world.setup.vehicle(north, "KDA 482M", date(2026, 10, 1), 7000)
    kdb = await world.setup.vehicle(north, "KDB 111A", date(2026, 10, 1), 3500)
    await world.record(
        world.setup.setup.retire_vehicle(
            VehicleRetirement(world.later(owner), kdb, date(2026, 10, 3), None)
        )
    )
    await world.record(
        world.setup.setup.restore_vehicle(
            VehicleReturn(world.later(owner), kdb, date(2026, 10, 5), None)
        )
    )
    clerk = await world.clerk()
    tenancy = world.setup.tenancy
    await tenancy.record(
        tenancy.repository.save_settings(
            SettingsSave(
                world.later(owner),
                "revenue",
                {"low_day_threshold": 400, "gap_amber_percent": 25},
                None,
                None,
            )
        )
    )

    async def save(
        who: TenantContext,
        vehicle: UUID,
        day: date,
        amount: Decimal | int | None = None,
        reason: str | None = None,
        note: str | None = None,
        version: int | None = None,
        *,
        days_later: int = 0,
        captured_at: datetime | None = None,
    ) -> None:
        money = None if amount is None else Decimal(amount)
        command = RevenueCapture(
            world.later(who, days_later), vehicle, day, money, reason, note, version, captured_at
        )
        await world.record(world.revenue.capture(command))

    october = {day: date(2026, 10, day) for day in range(1, 11)}
    await save(owner, kda, TODAY, Decimal("10.001"))
    await save(owner, kda, TODAY, None, "no crew")
    await save(owner, kda, TODAY, None, "Garage", "Late")
    await save(owner, UNKNOWN, TODAY, 500)
    await save(owner, kda, october[10], 500)
    await save(owner, kda, date(2026, 9, 30), 500)
    await save(owner, kdb, october[4], 500)
    await save(clerk, kda, october[8], Decimal("1500.50"))
    await save(clerk, kda, october[8], Decimal("1500.5"), version=4)
    await save(clerk, kda, october[8], 1600, version=1)
    await save(owner, kda, october[8], 1600)
    await save(owner, kda, october[8], 1600, version=1)
    await save(clerk, kda, october[8], Decimal("1500.50"), version=1)
    await save(owner, kda, october[7], None, " NoCrew ")
    await save(owner, kda, october[6], None, "Other", "  Engine knock ")
    await save(owner, kda, october[6], None, "Other", "Engine knock", version=7)
    await save(owner, kdb, october[2], 800)
    await save(clerk, kda, TODAY, 900)
    await save(clerk, kda, TODAY, 950, version=1)
    await save(clerk, kda, TODAY, None, "Garage", version=2)
    await save(clerk, kda, TODAY, 950, days_later=1)
    await save(clerk, kda, TODAY, None, "Garage", version=3, days_later=1)
    await save(owner, kda, october[5], 399)
    await save(owner, kda, october[5], 399, "Garage")
    await save(owner, kda, october[4], 400, "Garage")
    await save(owner, kda, october[4], 0)
    await save(owner, kda, october[3], 0, "Arrest")
    await save(owner, kda, october[2], None, "Other")
    await save(clerk, kda, october[1], 1500)
    await save(clerk, kda, october[1], 1500, captured_at=NOW - timedelta(days=3))
    await save(owner, kda, october[5], 300, "Arrest", version=1)
    for threshold, vehicle, day, amount, reason in (
        (1000, kdb, october[2], 800, None),
        (200, kda, october[5], 300, "Arrest"),
    ):
        settings = {"low_day_threshold": threshold}
        await tenancy.record(
            tenancy.repository.save_settings(
                SettingsSave(world.later(owner), "revenue", settings, None, None)
            )
        )
        await save(clerk, vehicle, day, amount, reason, version=9)
        await save(owner, vehicle, day, amount + 1, reason, version=1)
    for who in (owner, clerk):
        await world.record(
            world.revenue.week(RevenueWeekQuery(who, None, None, None, None, None, None))
        )
    await world.record(
        world.revenue.week(RevenueWeekQuery(owner, october[1], north, None, 2, 1, None))
    )
    await world.record(
        world.revenue.week(RevenueWeekQuery(owner, date(2026, 9, 28), None, kdb, 0, 0, None))
    )
    for q in ("kdb", " 482", "x" * 41):
        await world.record(world.revenue.week(RevenueWeekQuery(owner, None, None, None, 1, 5, q)))
    for who, period in ((owner, "month"), (owner, "today"), (clerk, None), (clerk, "year")):
        await world.record(world.revenue.dashboard(RevenueDashboardQuery(who, period, None)))
    await world.setup.history("revenue")
    await world.setup.history("organization")


@dataclass(frozen=True)
class RevenueCase:
    name: str
    run: Callable[[RevenueWorld], Awaitable[None]]


CASES = (RevenueCase("capture_a_week", capture_a_week),)
