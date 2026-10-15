"""Builders shared by the setup routine tests: vehicle targets and away periods, expense
catalogue rows, scheduled items with their versions and shares, investment entries and revenue
records, inserted as ``xcode_owner`` where a test needs history no routine can write (dated
versions, past targets) or many rows at once without the change log (revenue records); and
the calls of the ``api.setup_*`` routines as ``xcode_app``."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Any
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from .scenario import T0, Conn, call
from .tenancy import REQUEST, Member, add_company, add_vehicle, refused, write

Amount = Decimal | int


def _one(conn: Conn, sql: str, params: Sequence[Any]) -> UUID:
    row = conn.execute(sql, params).fetchone()
    assert row is not None
    return UUID(str(row["id"]))


def split_week(weekly: Amount) -> tuple[Decimal, ...]:
    """A weekly target as seven day figures the way migration 0010 split them: Monday to
    Saturday a seventh rounded to the cent, Sunday the rest."""
    day = (Decimal(weekly) / 7).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
    return (day,) * 6 + (Decimal(weekly) - 6 * day,)


def add_target_set(
    owner: Conn,
    org: UUID,
    vehicle: UUID,
    starts_on: date,
    days: Sequence[Amount],
    *,
    created_by: UUID | None = None,
) -> UUID:
    return _one(
        owner,
        "INSERT INTO setup.vehicle_target_sets (organization_id, vehicle_id, starts_on, monday, "
        "tuesday, wednesday, thursday, friday, saturday, sunday, created_by) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
        "ON CONFLICT (organization_id, vehicle_id, starts_on) DO UPDATE SET "
        "monday = excluded.monday, tuesday = excluded.tuesday, wednesday = excluded.wednesday, "
        "thursday = excluded.thursday, friday = excluded.friday, saturday = excluded.saturday, "
        "sunday = excluded.sunday RETURNING id",
        (org, vehicle, starts_on, *days, created_by),
    )


def add_target(
    owner: Conn, org: UUID, vehicle: UUID, revision: int, effective_from: date, amount: Amount
) -> None:
    """A weekly target from ``effective_from`` as a target set split by ``split_week``. Callers
    add revisions in order, so a later one on the same date replaces the set, as the higher
    revision of the weekly-target rows did."""
    assert revision >= 1
    add_target_set(owner, org, vehicle, effective_from, split_week(amount))


def add_away(owner: Conn, org: UUID, vehicle: UUID, left_on: date, returned_on: date) -> None:
    owner.execute(
        "INSERT INTO setup.vehicle_away_periods (organization_id, vehicle_id, left_on, "
        "returned_on) VALUES (%s, %s, %s, %s)",
        (org, vehicle, left_on, returned_on),
    )


def add_main_category(owner: Conn, org: UUID, name: str) -> UUID:
    return _one(
        owner,
        "INSERT INTO setup.expense_main_categories (organization_id, name) "
        "VALUES (%s, %s) RETURNING id",
        (org, name),
    )


def add_category(
    owner: Conn,
    org: UUID,
    name: str,
    *,
    bucket: int | None = 2,
    stopped_on: date | None = None,
    main_category: UUID | None = None,
) -> UUID:
    return _one(
        owner,
        "INSERT INTO setup.expense_categories (organization_id, name, bucket, stopped_on, "
        "main_category_id) VALUES (%s, %s, %s, %s, %s) RETURNING id",
        (org, name, bucket, stopped_on, main_category),
    )


def add_item(
    owner: Conn, org: UUID, category: UUID, name: str, *, stopped_on: date | None = None
) -> UUID:
    return _one(
        owner,
        "INSERT INTO setup.expense_items (organization_id, category_id, name, stopped_on) "
        "VALUES (%s, %s, %s, %s) RETURNING id",
        (org, category, name, stopped_on),
    )


def add_record(
    owner: Conn,
    org: UUID,
    vehicle: UUID,
    day: date,
    amount: Amount | None,
    *,
    recorder: UUID,
    reason: int | None = None,
) -> UUID:
    """A revenue record seeded as owner, without the capture routine's change-log row."""
    return _one(
        owner,
        "INSERT INTO revenue.records (organization_id, vehicle_id, business_date, amount, reason, "
        "captured_at, captured_by, updated_at, updated_by) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
        (org, vehicle, day, amount, reason, T0, recorder, T0, recorder),
    )


def add_investment(
    owner: Conn,
    org: UUID,
    vehicle: UUID,
    invested_on: date,
    description: str,
    amount: Amount,
    *,
    recorder: UUID,
    recorded_at: datetime = T0,
) -> UUID:
    return _one(
        owner,
        "INSERT INTO setup.vehicle_investments (organization_id, vehicle_id, invested_on, "
        "description, amount, recorded_by, recorded_at) VALUES (%s, %s, %s, %s, %s, %s, %s) "
        "RETURNING id",
        (org, vehicle, invested_on, description, amount, recorder, recorded_at),
    )


@dataclass(frozen=True, slots=True)
class Version:
    """One stored version of a scheduled item; ``start_on`` defaults to ``effective_from``."""

    effective_from: date
    shares: Mapping[UUID, Amount]
    name: str = "Insurance"
    kind: int = 1
    frequency: int = 3
    day: int | None = 15
    last_day: bool = False
    month: int | None = None
    start_on: date | None = None
    end_on: date | None = None
    expense_item_id: UUID | None = None
    bucket: int | None = None
    note: str | None = None


def add_schedule(
    owner: Conn, org: UUID, *versions: Version, stopped_from: date | None = None
) -> tuple[UUID, list[UUID]]:
    """A scheduled item with its versions (revision 1, 2, ... in order) and their shares, in
    one transaction so the share-sum constraint trigger sees each version complete."""
    with owner.transaction():
        item = _one(
            owner,
            "INSERT INTO setup.recurring_items (organization_id, stopped_from) VALUES (%s, %s) "
            "RETURNING id",
            (org, stopped_from),
        )
        ids: list[UUID] = []
        for revision, v in enumerate(versions, start=1):
            amount = sum((Decimal(a) for a in v.shares.values()), Decimal(0))
            version = _one(
                owner,
                "INSERT INTO setup.recurring_versions (organization_id, item_id, revision, "
                "effective_from, name, kind, amount, frequency, day, last_day, month, start_on, "
                "end_on, expense_item_id, bucket, note) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
                "RETURNING id",
                (
                    org,
                    item,
                    revision,
                    v.effective_from,
                    v.name,
                    v.kind,
                    amount,
                    v.frequency,
                    v.day,
                    v.last_day,
                    v.month,
                    v.start_on or v.effective_from,
                    v.end_on,
                    v.expense_item_id,
                    v.bucket,
                    v.note,
                ),
            )
            for vehicle, share in v.shares.items():
                owner.execute(
                    "INSERT INTO setup.recurring_allocations (organization_id, version_id, "
                    "vehicle_id, amount) VALUES (%s, %s, %s, %s)",
                    (org, version, vehicle, share),
                )
            ids.append(version)
    return item, ids


def shares(*pairs: tuple[UUID, Amount]) -> Jsonb:
    """The ``p_allocations`` argument: ``[{vehicle_id, amount}]`` in the order given."""
    return Jsonb([{"vehicle_id": str(v), "amount": str(a)} for v, a in pairs])


# --- calls of the api.setup_* routines as xcode_app ---------------------------------------


def read(app: Conn, routine: str, who: Member, *args: Any, now: datetime = T0) -> Any:
    return call(app, routine, who.id, who.org, REQUEST, *args, now)


def run(app: Conn, routine: str, who: Member, *args: Any, now: datetime = T0) -> dict[str, Any]:
    return write(app, routine, who.id, who.org, REQUEST, *args, now)


def refuses(
    app: Conn,
    routine: str,
    who: Member,
    args: Sequence[Any],
    sqlstate: str,
    code: str,
    *,
    now: datetime = T0,
) -> psycopg.Error:
    return refused(app, routine, [who.id, who.org, REQUEST, *args, now], sqlstate, code)


@dataclass(frozen=True, slots=True)
class Definition:
    """The fields of a scheduled item save after the three standard arguments and the item id;
    ``args()`` lists them in routine order."""

    allocations: Jsonb
    amount: Amount
    name: str | None = "Office rent"
    kind: int = 2
    frequency: int = 3
    day: int | None = 15
    last_day: bool = False
    start: date | None = None
    end: date | None = None
    expense_item_id: UUID | None = None
    note: str | None = None
    month: int | None = None
    reason: str | None = None
    condition: Jsonb | None = None
    opening: Jsonb | None = None

    def args(self) -> list[Any]:
        return [
            self.name,
            self.kind,
            self.amount,
            self.frequency,
            self.day,
            self.last_day,
            self.start,
            self.end,
            self.allocations,
            self.expense_item_id,
            self.note,
            self.month,
            self.condition,
            self.opening,
            self.reason,
        ]


def change_rows(owner: Conn, org: UUID, section: str) -> list[dict[str, Any]]:
    return owner.execute(
        "SELECT * FROM tenancy.change_log WHERE organization_id = %s AND section = %s "
        "ORDER BY version",
        (org, section),
    ).fetchall()


def reasons(owner: Conn, org: UUID, section: str) -> list[str]:
    return [str(r["reason"]) for r in change_rows(owner, org, section)]


@dataclass(frozen=True, slots=True)
class ReportFleet:
    """The report scenario: company Report Fleet, KDA 482M (joined 2026-02-01, 7,000 a week
    raised to 14,000 from 2026-03-16, 1,500 recorded each day from 1 to 29 March) and KDB 111A,
    with eight scheduled items, all but Stage fee posting to KDA 482M."""

    company: UUID
    kda: UUID
    kdb: UUID
    items: Mapping[str, UUID]


def seed_report_fleet(owner: Conn, org: UUID, recorder: UUID) -> ReportFleet:
    company = add_company(owner, org, "Report Fleet")
    kda = add_vehicle(owner, org, company, "KDA 482M", joined_on=date(2026, 2, 1))
    kdb = add_vehicle(owner, org, company, "KDB 111A", joined_on=date(2026, 2, 1))
    add_target(owner, org, kda, 1, date(2026, 2, 1), 7000)
    add_target(owner, org, kda, 2, date(2026, 3, 16), 14000)
    add_target(owner, org, kdb, 1, date(2026, 2, 1), 7000)
    for day in range(1, 30):
        add_record(owner, org, kda, date(2026, 3, day), 1500, recorder=recorder)
    february, march = date(2026, 2, 1), date(2026, 3, 1)
    items: dict[str, UUID] = {}
    items["Service"], _ = add_schedule(
        owner,
        org,
        Version(february, {kda: 2000}, name="Service", day=10, bucket=1),
        Version(
            date(2026, 3, 20), {kda: 2500}, name="Service", day=25, bucket=1, start_on=february
        ),
    )
    items["Parking"], _ = add_schedule(
        owner,
        org,
        Version(february, {kda: 300}, name="Parking", frequency=2, day=1, bucket=2),
        stopped_from=date(2026, 3, 23),
    )
    items["Tyres"], _ = add_schedule(
        owner, org, Version(march, {kda: 100, kdb: 100}, name="Tyres", frequency=2, day=0, bucket=1)
    )
    items["Crew lunch"], _ = add_schedule(
        owner,
        org,
        Version(
            march,
            {kda: 50},
            name="Crew lunch",
            frequency=1,
            day=None,
            end_on=date(2026, 3, 5),
            bucket=2,
        ),
    )
    items["Loan repayment"], _ = add_schedule(
        owner,
        org,
        Version(february, {kda: 10000}, name="Loan repayment", day=None, last_day=True, bucket=3),
    )
    items["Insurance"], _ = add_schedule(
        owner, org, Version(march, {kda: 6000}, name="Insurance", frequency=4, month=3, bucket=2)
    )
    items["Owner savings"], _ = add_schedule(
        owner, org, Version(march, {kda: 1000}, name="Owner savings", kind=2, frequency=2, day=5)
    )
    items["Stage fee"], _ = add_schedule(
        owner, org, Version(march, {kdb: 400}, name="Stage fee", frequency=2, day=2, bucket=2)
    )
    return ReportFleet(company=company, kda=kda, kdb=kdb, items=items)
