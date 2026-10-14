"""Parity cases for ``FakeReportsRepository``: each case runs the same calls against the fake
and against ``ReportsRoutines`` on PostgreSQL, arranging the fleet through the setup repository
and the records through the revenue repository of the same world, and reading the change log
through its tenancy repository; the two observations must be equal
(``tenancy_cases.normalised``).

The fake builds Net by vehicle and Capture gaps and logs exports; the other builders answer an
empty table, so the cases keep to those two reports, the catalogue, the checks and an export.
The business date is the calendar date of ``tenancy_cases.NOW`` (2026-10-09); every call runs a
minute after the one before."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from xcode_api.application.repositories import (
    ReportsRepository,
    RevenueRepository,
    SetupRepository,
    TenancyRepository,
)
from xcode_api.domain.errors import DomainRefusal
from xcode_api.domain.reports import ReportExportQuery, ReportQuery
from xcode_api.domain.revenue import RevenueCapture
from xcode_api.domain.tenancy import TenantContext

from .fakes import FakeReportsRepository, FakeRevenueRepository, FakeSetupRepository
from .revenue_cases import comparable
from .scenario import Conn
from .setup_cases import SetupWorld
from .setup_cases import database_world as setup_database_world
from .setup_cases import fake_world as setup_fake_world
from .tenancy_cases import NOW

TODAY = date(2026, 10, 9)


@dataclass
class ReportsWorld:
    reports: ReportsRepository
    revenue: RevenueRepository
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
            self.seen.append(("detail", comparable(detail)))
        return result


def fake_world() -> ReportsWorld:
    setup = setup_fake_world()
    assert isinstance(setup.setup, FakeSetupRepository)
    revenue = FakeRevenueRepository(setup.setup)
    return ReportsWorld(FakeReportsRepository(setup.setup, revenue), revenue, setup)


def database_world(
    reports: ReportsRepository,
    revenue: RevenueRepository,
    setup: SetupRepository,
    tenancy: TenancyRepository,
    operator: Conn,
) -> ReportsWorld:
    return ReportsWorld(reports, revenue, setup_database_world(setup, tenancy, operator))


async def read_the_net_and_the_gaps(world: ReportsWorld) -> None:
    """A fleet of two vehicles with three captured days: the catalogue, Net by vehicle with and
    without a search, Capture gaps, the period and query refusals, an unknown report, and an
    Excel export of the net with its change-log row."""
    owner = world.owner
    north = await world.setup.company("North Star")
    kda = await world.setup.vehicle(north, "KDA 482M", date(2026, 10, 1), 7000)
    kdb = await world.setup.vehicle(north, "KDB 111A", date(2026, 10, 5), 3500)
    for day, amount in ((1, 4500), (2, 5200), (3, 0)):
        capture = RevenueCapture(
            world.later(owner), kda, date(2026, 10, day), Decimal(amount), None, None, None, None
        )
        await world.record(world.revenue.capture(capture))

    def report(
        group: str,
        name: str,
        first: date | None = date(2026, 10, 1),
        last: date | None = TODAY,
        *,
        q: str | None = None,
        page: int = 1,
        size: int = 50,
        company: Any = None,
    ) -> ReportQuery:
        return ReportQuery(
            world.later(owner), group, name, first, last, company, None, q, page, size
        )

    await world.record(world.reports.access(world.later(owner)))
    await world.record(world.reports.report(report("fleet", "net")))
    await world.record(world.reports.report(report("fleet", "net", q=" kda 4,500 ")))
    await world.record(world.reports.report(report("fleet", "net", q="nothing like it")))
    await world.record(world.reports.report(report("fleet", "net", page=2, size=1)))
    await world.record(world.reports.report(report("fleet", "net", company=north)))
    await world.record(world.reports.report(report("fleet", "gaps")))
    await world.record(world.reports.report(report("fleet", "gaps", q="KDB")))
    await world.record(
        world.reports.report(report("fleet", "gaps", date(2026, 10, 6), date(2026, 10, 20)))
    )
    await world.record(world.reports.report(report("fleet", "nothing")))
    await world.record(world.reports.report(report("nowhere", "net")))
    await world.record(world.reports.report(report("fleet", "net", None, TODAY)))
    await world.record(world.reports.report(report("fleet", "net", TODAY, date(2026, 10, 1))))
    await world.record(world.reports.report(report("fleet", "net", date(2025, 10, 1), TODAY)))
    await world.record(
        world.reports.report(
            report("fleet", "net", TODAY + timedelta(days=1), TODAY + timedelta(days=2))
        )
    )
    await world.record(world.reports.report(report("fleet", "net", page=0)))
    await world.record(world.reports.report(report("fleet", "net", size=101)))
    await world.record(world.reports.report(report("fleet", "net", q="x" * 201)))
    await world.record(
        world.reports.export_report(
            ReportExportQuery(
                world.later(owner), "fleet", "net", date(2026, 10, 1), TODAY, None, None, None, None
            )
        )
    )
    await world.record(
        world.reports.export_report(
            ReportExportQuery(
                world.later(owner),
                "fleet",
                "gaps",
                date(2026, 10, 5),
                TODAY,
                None,
                None,
                " KDA ",
                " PDF ",
            )
        )
    )
    await world.record(
        world.reports.export_report(
            ReportExportQuery(
                world.later(owner),
                "fleet",
                "net",
                date(2026, 10, 1),
                TODAY,
                None,
                None,
                None,
                "csv",
            )
        )
    )
    await world.setup.history("reports")
    del kdb


@dataclass(frozen=True)
class ReportsCase:
    name: str
    run: Callable[[ReportsWorld], Awaitable[None]]


CASES = (ReportsCase("read_the_net_and_the_gaps", read_the_net_and_the_gaps),)
