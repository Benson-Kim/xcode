"""The revenue helpers (``docs/05-routines.md`` section 2.4), called as ``xcode_api_executor``
under row-level security inside the organization: the cell status table and who may open a
cell, a vehicle's days against the setup predicates, the earliest missing day around away
periods and a leave date, the week totals, the gap and its band, the low days, the percent,
the reason spellings and the record snapshot.

Companies, vehicles, targets, away periods and records are inserted as ``xcode_owner``: the
dated history the helpers read is older than any routine could write."""

from __future__ import annotations

import json
import random
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest

from ..support.scenario import T0, Conn
from ..support.setup_rows import add_away, add_record, add_target
from ..support.tenancy import Member, add_company, add_vehicle, provision_member, set_localization

TODAY = date(2026, 10, 9)
WEEK = date(2026, 10, 5)


@dataclass(frozen=True, slots=True)
class Yard:
    owner: Member
    north: UUID


@pytest.fixture
def yard(operator_conn: Conn, owner_conn: Conn) -> Yard:
    owner = provision_member(operator_conn, 1, "Owner", "Olive", "Owner")
    return Yard(owner=owner, north=add_company(owner_conn, owner.org, "North Star"))


@contextmanager
def _as(conn: Conn, who: Member) -> Iterator[None]:
    with conn.transaction():
        conn.execute(
            "SELECT tenancy.enter_organization(%s, %s, 'req-revenue-helpers', NULL)",
            (who.id, who.org),
        )
        yield


def _scalar(conn: Conn, query: str, params: Any = ()) -> Any:
    row = conn.execute(query, params).fetchone()
    assert row is not None
    return next(iter(row.values()))


def _vehicle(
    owner_conn: Conn,
    yard: Yard,
    registration: str,
    *,
    joined_on: date = date(2026, 9, 1),
    left_on: date | None = None,
    target: int = 1000,
) -> UUID:
    vehicle = add_vehicle(
        owner_conn, yard.owner.org, yard.north, registration, joined_on=joined_on, left_on=left_on
    )
    add_target(owner_conn, yard.owner.org, vehicle, 1, joined_on, target)
    return vehicle


def _record(owner_conn: Conn, yard: Yard, vehicle: UUID, day: date, amount: int = 500) -> UUID:
    return add_record(owner_conn, yard.owner.org, vehicle, day, amount, recorder=yard.owner.id)


def _week(
    executor: Conn,
    yard: Yard,
    vehicle: UUID,
    start: date = WEEK,
    *,
    threshold: int = 4000,
    amber: int = 10,
) -> dict[str, Any]:
    with _as(executor, yard.owner):
        return _scalar(
            executor,
            "SELECT revenue.vehicle_week("
            "array_agg(d ORDER BY d.day), %s, true, true, NULL, %s, %s) "
            "FROM revenue.vehicle_days(ARRAY[%s]::uuid[], %s, %s, %s) AS d",
            (TODAY, threshold, amber, vehicle, start, start + timedelta(days=6), TODAY),
        )


# --- the cell -----------------------------------------------------------------------------


def _cell(
    executor: Conn,
    *,
    day: date,
    active: bool = True,
    amount: int | None = None,
    reason: int | None = None,
    capture: bool = True,
    correct: bool = True,
    earliest: date | None = None,
) -> dict[str, Any]:
    recorded = amount is not None or reason is not None
    labels = {1: "Garage", 3: "No Crew"}
    return _scalar(
        executor,
        "SELECT revenue.cell(ROW(%s, %s, %s, false, %s, %s, %s, %s, %s, %s, NULL, false, %s)"
        "::revenue.vehicle_day, %s, %s, %s, %s)",
        (
            UUID(int=7),
            day,
            active,
            1000 if active else 0,
            active and (day < TODAY or recorded),
            UUID(int=8) if recorded else None,
            amount,
            reason,
            labels.get(reason) if reason else None,
            3 if recorded else None,
            TODAY,
            capture,
            correct,
            earliest,
        ),
    )


@pytest.mark.parametrize(
    ("day", "active", "amount", "reason", "status"),
    [
        (date(2026, 10, 8), False, None, None, "none"),
        (date(2026, 10, 8), False, 500, None, "none"),
        (date(2026, 10, 10), True, None, None, "future"),
        (date(2026, 10, 8), True, None, None, "missing"),
        (TODAY, True, None, None, "missing"),
        (date(2026, 10, 8), True, 500, None, "amount"),
        (date(2026, 10, 8), True, None, 3, "reason"),
        (date(2026, 10, 8), True, 500, 1, "amount"),
    ],
)
def test_a_cell_is_none_future_missing_amount_or_reason(
    executor: Conn, day: date, active: bool, amount: int | None, reason: int | None, status: str
) -> None:
    cell = _cell(executor, day=day, active=active, amount=amount, reason=reason)
    assert cell["status"] == status
    assert cell["day"] == day.isoformat()
    assert cell["expected"] == (1000 if active else 0)
    if status in ("amount", "reason"):
        assert cell["version"] == 3
        assert cell["reason"] == {None: None, 1: "Garage", 3: "No Crew"}[reason]
        assert cell["amount"] == amount


@pytest.mark.parametrize(
    ("day", "amount", "capture", "correct", "earliest", "can_edit"),
    [
        (date(2026, 10, 8), None, True, False, None, True),
        (date(2026, 10, 8), None, False, True, None, False),
        (date(2026, 9, 1), None, True, False, None, True),
        (TODAY, 500, True, False, None, False),
        (TODAY, 500, False, True, None, True),
        (TODAY, 500, False, False, None, False),
        (date(2026, 10, 8), 500, True, False, None, False),
        (date(2026, 10, 8), 500, False, True, None, True),
        (date(2026, 10, 10), None, True, True, None, False),
        (date(2026, 10, 8), None, True, True, TODAY, False),
        (date(2026, 10, 8), 500, True, True, TODAY, False),
        (date(2026, 10, 8), None, True, True, date(2026, 10, 8), True),
        (TODAY, 500, True, True, TODAY, True),
    ],
)
def test_who_may_open_a_cell_follows_its_status_day_and_limit(
    executor: Conn,
    day: date,
    amount: int | None,
    capture: bool,
    correct: bool,
    earliest: date | None,
    can_edit: bool,
) -> None:
    cell = _cell(
        executor, day=day, amount=amount, capture=capture, correct=correct, earliest=earliest
    )
    assert cell["can_edit"] is can_edit


def test_a_day_out_of_the_fleet_never_opens(executor: Conn) -> None:
    cell = _cell(executor, day=date(2026, 10, 8), active=False, amount=500)
    assert (cell["status"], cell["can_edit"], cell["expected"]) == ("none", False, 0)


# --- a vehicle's days and its week --------------------------------------------------------


def test_each_day_expects_its_own_figure_and_the_week_sums_them(
    executor: Conn, owner_conn: Conn, yard: Yard
) -> None:
    kda = _vehicle(owner_conn, yard, "KDA 482M")
    last_week = WEEK - timedelta(days=7)
    week = _week(executor, yard, kda, last_week)
    # 1,000 a week splits as six days of 142.86 and a Sunday of 142.84.
    assert [cell["expected"] for cell in week["days"]] == [142.86] * 6 + [142.84]
    assert Decimal(str(week["total_expected"])) == Decimal("1000.00")
    for offset in range(5):
        _record(owner_conn, yard, kda, WEEK + timedelta(days=offset), 200)
    week = _week(executor, yard, kda)
    # Four days before the business date and the recorded business date count.
    assert Decimal(str(week["total_expected"])) == Decimal("714.30")
    assert Decimal(str(week["total_amount"])) == Decimal("1000.00")
    assert week["percent"] == 140
    assert Decimal(str(week["gap"])) == Decimal("285.70")


def test_the_week_counts_days_before_the_business_date_and_recorded_days_only(
    executor: Conn, owner_conn: Conn, yard: Yard
) -> None:
    kda = _vehicle(owner_conn, yard, "KDA 482M", joined_on=date(2026, 10, 7), target=7000)
    week = _week(executor, yard, kda)
    assert [cell["status"] for cell in week["days"]] == [
        "none",
        "none",
        "missing",
        "missing",
        "missing",
        "future",
        "future",
    ]
    assert week["total_expected"] == 2000
    assert week["total_amount"] == 0
    assert week["percent"] == 0
    _record(owner_conn, yard, kda, TODAY, 1500)
    week = _week(executor, yard, kda)
    assert week["total_expected"] == 3000
    assert week["percent"] == 50


def test_a_week_with_nothing_expected_has_no_percent(
    executor: Conn, owner_conn: Conn, yard: Yard
) -> None:
    kda = _vehicle(owner_conn, yard, "KDA 482M", joined_on=TODAY)
    week = _week(executor, yard, kda)
    assert (week["total_expected"], week["percent"]) == (0, None)


def test_vehicle_days_agree_with_the_setup_predicates_day_by_day(
    executor: Conn, owner_conn: Conn, yard: Yard
) -> None:
    rng = random.Random(20261009)  # noqa: S311 - a seeded sample, not a secret
    org = yard.owner.org
    vehicles = []
    for n in range(12):
        joined = date(2026, 8, 1) + timedelta(days=rng.randrange(40))
        left = joined + timedelta(days=rng.randrange(5, 60)) if n % 3 == 0 else None
        vehicle = add_vehicle(
            owner_conn,
            org,
            yard.north,
            f"KD{chr(65 + n)} {100 + n}A",
            joined_on=joined,
            left_on=left,
        )
        effective = joined
        for revision in range(1, rng.randrange(2, 5)):
            add_target(owner_conn, org, vehicle, revision, effective, rng.randrange(700, 9000))
            effective += timedelta(days=rng.choice((0, 3, 11)))
        start = joined + timedelta(days=rng.randrange(1, 10))
        add_away(owner_conn, org, vehicle, start, start + timedelta(days=rng.randrange(1, 6)))
        for offset in rng.sample(range(70), 20):
            _record(owner_conn, yard, vehicle, date(2026, 8, 1) + timedelta(days=offset))
        vehicles.append(vehicle)
    with _as(executor, yard.owner):
        rows = executor.execute(
            "SELECT d.vehicle_id, d.day, d.active, d.away, d.target, d.counted, "
            "d.record_id IS NOT NULL AS recorded, "
            "setup.vehicle_active_on(d.vehicle_id, d.day) AS active_on, "
            "setup.vehicle_away_on(d.vehicle_id, d.day) AS away_on, "
            "setup.day_target(d.vehicle_id, d.day) AS target_on "
            "FROM revenue.vehicle_days(%s, %s, %s, %s) AS d",
            (vehicles, date(2026, 7, 25), date(2026, 10, 12), TODAY),
        ).fetchall()
    assert len(rows) == 12 * 80
    for row in rows:
        assert (row["active"], row["away"], row["target"]) == (
            row["active_on"],
            row["away_on"],
            row["target_on"],
        ), row
        assert row["counted"] == (row["active"] and (row["day"] < TODAY or row["recorded"]))


# --- the earliest missing day ------------------------------------------------------------


def _earliest(executor: Conn, yard: Yard, vehicles: list[UUID]) -> dict[UUID, date | None]:
    with _as(executor, yard.owner):
        rows = executor.execute(
            "SELECT * FROM revenue.earliest_missing(%s, %s)", (vehicles, TODAY)
        ).fetchall()
    return {UUID(str(r["vehicle_id"])): r["earliest_missing"] for r in rows}


def test_the_earliest_missing_day_skips_away_days_and_stops_at_the_leave_date(
    executor: Conn, owner_conn: Conn, yard: Yard
) -> None:
    org = yard.owner.org
    oct1 = date(2026, 10, 1)

    def days(first: int, last: int) -> list[date]:
        return [date(2026, 10, d) for d in range(first, last + 1)]

    def fleet(registration: str, recorded: list[date], **kwargs: Any) -> UUID:
        vehicle = _vehicle(owner_conn, yard, registration, joined_on=oct1, **kwargs)
        for day in recorded:
            _record(owner_conn, yard, vehicle, day)
        return vehicle

    after_away = fleet("KDA 100A", days(1, 2))
    add_away(owner_conn, org, after_away, date(2026, 10, 3), date(2026, 10, 5))
    covered_by_away = fleet("KDB 100A", days(1, 2) + days(5, 8))
    add_away(owner_conn, org, covered_by_away, date(2026, 10, 3), date(2026, 10, 5))
    left = fleet("KDC 100A", days(1, 3), left_on=date(2026, 10, 4))
    complete = fleet("KDD 100A", days(1, 8))
    empty = fleet("KDE 100A", [])
    hole = fleet("KDF 100A", [oct1, date(2026, 10, 3)])
    tail = fleet("KDG 100A", days(1, 4))
    away_at_join = fleet("KDH 100A", [])
    add_away(owner_conn, org, away_at_join, oct1, date(2026, 10, 3))
    joins_today = _vehicle(owner_conn, yard, "KDJ 100A", joined_on=TODAY)
    found = _earliest(
        executor,
        yard,
        [after_away, covered_by_away, left, complete, empty, hole, tail, away_at_join, joins_today],
    )
    assert found == {
        after_away: date(2026, 10, 5),
        covered_by_away: None,
        left: None,
        complete: None,
        empty: oct1,
        hole: date(2026, 10, 2),
        tail: date(2026, 10, 5),
        away_at_join: date(2026, 10, 3),
        joins_today: None,
    }


def test_the_earliest_missing_day_agrees_with_a_day_by_day_walk(
    executor: Conn, owner_conn: Conn, yard: Yard
) -> None:
    rng = random.Random(7)  # noqa: S311 - a seeded sample, not a secret
    org = yard.owner.org
    vehicles = []
    for n in range(16):
        joined = date(2026, 9, 1) + timedelta(days=rng.randrange(30))
        left = joined + timedelta(days=rng.randrange(1, 40)) if n % 4 == 0 else None
        vehicle = _vehicle(
            owner_conn, yard, f"KE{chr(65 + n)} {200 + n}B", joined_on=joined, left_on=left
        )
        if n % 2:
            start = joined + timedelta(days=rng.randrange(0, 8))
            add_away(owner_conn, org, vehicle, start, start + timedelta(days=rng.randrange(1, 5)))
        span = (TODAY - joined).days
        for offset in rng.sample(range(span), rng.randrange(0, span)) if span > 0 else []:
            _record(owner_conn, yard, vehicle, joined + timedelta(days=offset))
        vehicles.append(vehicle)
    with _as(executor, yard.owner):
        walked = {
            UUID(str(r["id"])): r["day"]
            for r in executor.execute(
                "SELECT f.id, (SELECT min(g.day::date) "
                "FROM generate_series(f.joined_on, %s - 1, interval '1 day') AS g (day) "
                "WHERE setup.vehicle_active_on(f.id, g.day::date) AND NOT EXISTS ("
                "SELECT 1 FROM revenue.records AS r WHERE r.vehicle_id = f.id "
                "AND r.business_date = g.day::date)) AS day "
                "FROM setup.fleet_vehicles AS f WHERE f.id = ANY (%s)",
                (TODAY, vehicles),
            )
        }
    assert _earliest(executor, yard, vehicles) == walked


# --- percent, rounding, reasons, week start, snapshot ------------------------------------


@pytest.mark.parametrize(
    ("amount", "target", "percent"),
    [
        ("1", "200", 1),
        ("1", "300", 0),
        ("5050", "10000", 51),
        ("-1", "200", -1),
        ("1000", "1000", 100),
        ("0", "1000", 0),
        ("500", "0", None),
        ("999999999999.99", "0.01", 2147483647),
    ],
)
def test_percent_rounds_half_away_from_zero_and_holds_to_32_bits(
    executor: Conn, amount: str, target: str, percent: int | None
) -> None:
    assert (
        _scalar(executor, "SELECT revenue.percent(%s::numeric, %s::numeric)", (amount, target))
        == percent
    )


@pytest.mark.parametrize(
    ("value", "rounded"), [("0.125", "0.12"), ("0.135", "0.14"), ("142.857", "142.86")]
)
def test_money_figures_round_a_half_cent_to_the_even_cent(
    executor: Conn, value: str, rounded: str
) -> None:
    result = _scalar(executor, "SELECT revenue.round_half_even(%s::numeric, 2)", (value,))
    assert result == Decimal(rounded)


@pytest.mark.parametrize(
    ("text", "code"),
    [
        ("Garage", 1),
        ("Arrest", 2),
        ("No Crew", 3),
        ("NoCrew", 3),
        ("Other", 4),
        ("no crew", None),
        ("garage", None),
        ("No  Crew", None),
        ("", None),
    ],
)
def test_reason_spellings_are_the_labels_with_or_without_their_space(
    executor: Conn, text: str, code: int | None
) -> None:
    assert _scalar(executor, "SELECT revenue.reason_code(%s)", (text,)) == code
    if code is not None:
        label = _scalar(executor, "SELECT revenue.reason_label(%s::smallint)", (code,))
        assert label == ("No Crew" if code == 3 else text)


@pytest.mark.parametrize(
    ("first_day", "start"), [(1, date(2026, 10, 5)), (0, date(2026, 10, 4)), (5, TODAY)]
)
def test_the_week_starts_on_the_organization_first_day(
    executor: Conn, owner_conn: Conn, yard: Yard, first_day: int, start: date
) -> None:
    set_localization(owner_conn, yard.owner.org, first_day_of_week=first_day)
    with _as(executor, yard.owner):
        for day in (start, start + timedelta(days=3), start + timedelta(days=6)):
            assert _scalar(executor, "SELECT revenue.week_start(%s)", (day,)) == start


def test_a_record_snapshot_reads_as_the_dotnet_entity(
    executor: Conn, owner_conn: Conn, yard: Yard
) -> None:
    kda = _vehicle(owner_conn, yard, "KDA 482M")
    record = add_record(
        owner_conn, yard.owner.org, kda, TODAY, None, recorder=yard.owner.id, reason=3
    )
    with _as(executor, yard.owner):
        text = _scalar(executor, "SELECT revenue.record_snapshot(%s)::text", (record,))
        missing = _scalar(executor, "SELECT revenue.record_snapshot(%s)::text", (UUID(int=1),))
    stamp = T0.strftime("%Y-%m-%dT%H:%M:%S.%f+00:00")
    assert text == json.dumps(
        {
            "Id": str(record),
            "VehicleId": str(kda),
            "BusinessDate": TODAY.isoformat(),
            "Amount": None,
            "Reason": "NoCrew",
            "Note": None,
            "CapturedAt": stamp,
            "CapturedBy": str(yard.owner.id),
            "UpdatedAt": stamp,
            "UpdatedBy": str(yard.owner.id),
            "CorrectedAfterDate": False,
            "Version": 1,
        },
        separators=(",", ":"),
    )
    assert missing == "null"


# --- the gap and its band ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("gap", "target", "amber", "band"),
    [
        ("0", "1000", "10", "green"),
        ("0.01", "1000", "10", "green"),
        ("-0.01", "1000", "10", "amber"),
        ("-100", "1000", "10", "amber"),
        ("-100.01", "1000", "10", "red"),
        ("-1", "1000", "0", "red"),
        ("-1000", "1000", "100", "amber"),
        ("-5", "0", "10", None),
        ("5", "0", "10", None),
    ],
)
def test_gap_band(executor: Conn, gap: str, target: str, amber: str, band: str | None) -> None:
    query = "SELECT revenue.gap_band(%s::numeric, %s::numeric, %s::numeric)"
    assert _scalar(executor, query, (gap, target, amber)) == band


def test_the_gap_counts_the_days_so_far(executor: Conn, owner_conn: Conn, yard: Yard) -> None:
    kda = _vehicle(owner_conn, yard, "KDA 482M", joined_on=date(2026, 10, 7), target=7000)
    # 7 and 8 Oct count (missing), today does not until it is recorded.
    week = _week(executor, yard, kda)
    assert (week["gap"], week["gap_band"], week["below_threshold_days"]) == (-2000, "red", 0)
    _record(owner_conn, yard, kda, date(2026, 10, 7), 1950)
    week = _week(executor, yard, kda)
    assert (week["gap"], week["gap_band"]) == (-50, "amber")
    _record(owner_conn, yard, kda, TODAY, 1100)
    week = _week(executor, yard, kda)
    assert (week["gap"], week["gap_band"], week["total_expected"]) == (50, "green", 3000)
    # A finished week counts all seven days.
    old = _vehicle(owner_conn, yard, "KDB 111A", joined_on=date(2026, 9, 1), target=7000)
    _record(owner_conn, yard, old, WEEK - timedelta(days=7), 6000)
    finished = _week(executor, yard, old, WEEK - timedelta(days=7))
    assert (finished["total_expected"], finished["gap"], finished["gap_band"]) == (
        7000,
        -1000,
        "red",
    )
    assert _week(executor, yard, old, WEEK - timedelta(days=7), amber=15)["gap_band"] == "amber"


def test_low_days_are_judged_by_their_amount_against_the_threshold(
    executor: Conn, owner_conn: Conn, yard: Yard
) -> None:
    kda = _vehicle(owner_conn, yard, "KDA 482M", joined_on=date(2026, 10, 1), target=7000)
    org, by = yard.owner.org, yard.owner.id
    _record(owner_conn, yard, kda, WEEK, 3999)
    _record(owner_conn, yard, kda, WEEK + timedelta(days=1), 4000)
    add_record(owner_conn, org, kda, WEEK + timedelta(days=2), None, recorder=by, reason=2)
    add_record(owner_conn, org, kda, WEEK + timedelta(days=3), 100, recorder=by, reason=1)
    assert _week(executor, yard, kda)["below_threshold_days"] == 3
    assert _week(executor, yard, kda, threshold=4001)["below_threshold_days"] == 4
    assert _week(executor, yard, kda, threshold=0)["below_threshold_days"] == 1


def test_the_report_figures_sum_the_day_series_inside_each_vehicle_s_window(
    executor: Conn, owner_conn: Conn, yard: Yard
) -> None:
    rng = random.Random(20261014)  # noqa: S311 - a seeded sample, not a secret
    org = yard.owner.org
    vehicles = []
    for n in range(12):
        joined = date(2026, 8, 1) + timedelta(days=rng.randrange(40))
        left = joined + timedelta(days=rng.randrange(5, 60)) if n % 3 == 0 else None
        vehicle = add_vehicle(
            owner_conn,
            org,
            yard.north,
            f"KD{chr(65 + n)} {200 + n}B",
            joined_on=joined,
            left_on=left,
        )
        effective = joined
        for revision in range(1, rng.randrange(2, 5)):
            add_target(owner_conn, org, vehicle, revision, effective, rng.randrange(700, 9000))
            effective += timedelta(days=rng.choice((0, 3, 11)))
        start = joined + timedelta(days=rng.randrange(1, 10))
        add_away(owner_conn, org, vehicle, start, start + timedelta(days=rng.randrange(1, 6)))
        _record(owner_conn, yard, vehicle, start, 700)
        for offset in rng.sample(range(75), 20):
            day = date(2026, 8, 1) + timedelta(days=offset)
            if day != start:
                if offset % 4 == 0:
                    add_record(
                        owner_conn, org, vehicle, day, None, recorder=yard.owner.id, reason=1
                    )
                else:
                    _record(owner_conn, yard, vehicle, day, rng.randrange(100, 9000))
        vehicles.append(vehicle)
    span = (date(2026, 7, 25), date(2026, 10, 20), TODAY)
    with _as(executor, yard.owner):
        figures = {
            r["vehicle_id"]: (
                r["revenue"],
                r["target"],
                r["captured"],
                r["no_revenue"],
                r["missing"],
                r["missing_days"],
            )
            for r in executor.execute(
                "SELECT * FROM reports.vehicle_figures(%s, %s, %s, %s)", (vehicles, *span)
            ).fetchall()
        }
        summed = {
            r["vehicle_id"]: (
                r["revenue"],
                r["target"],
                r["captured"],
                r["no_revenue"],
                r["missing"],
                r["missing_days"],
            )
            for r in executor.execute(
                "SELECT d.vehicle_id, coalesce(sum(d.amount), 0) AS revenue, "
                "coalesce(sum(d.target) FILTER (WHERE d.counted), 0) AS target, "
                "count(*) FILTER (WHERE d.record_id IS NOT NULL AND d.amount IS NOT NULL) "
                "AS captured, "
                "count(*) FILTER (WHERE d.record_id IS NOT NULL AND d.amount IS NULL) "
                "AS no_revenue, "
                "count(*) FILTER (WHERE d.counted AND d.record_id IS NULL) AS missing, "
                "coalesce(array_agg(d.day ORDER BY d.day) "
                "FILTER (WHERE d.counted AND d.record_id IS NULL), '{}') AS missing_days "
                "FROM revenue.vehicle_days(%s, %s, %s, %s) AS d "
                "WHERE setup.report_window(d.vehicle_id, %s, %s, %s) @> d.day "
                "GROUP BY d.vehicle_id",
                (vehicles, *span, *span),
            ).fetchall()
        }
    assert len(figures) == 12
    assert figures == summed
    assert sum(f[3] for f in figures.values()) > 0
    assert sum(f[4] for f in figures.values()) > 0
