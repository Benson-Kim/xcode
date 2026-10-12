"""The setup helpers (``docs/05-routines.md`` sections 2.3 and 6.2), called as
``xcode_api_executor`` under row-level security inside the organization: visibility for the
three scope kinds, the activity and away predicates, the target in force, registrations, the
schedule shape, due days, banker's rounding and the change-log snapshots byte for byte.

Companies, vehicles, targets, away periods and scheduled versions are inserted as
``xcode_owner``: the dated history the helpers read is older than any routine could write."""

from __future__ import annotations

import random
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

import psycopg
import pytest

from ..support.scenario import Conn
from ..support.setup_rows import (
    Version,
    add_away,
    add_category,
    add_investment,
    add_item,
    add_main_category,
    add_schedule,
    add_target,
    add_target_set,
)
from ..support.tenancy import (
    Member,
    add_company,
    add_vehicle,
    provision_member,
    set_override,
    set_scope,
)


@dataclass(frozen=True, slots=True)
class Fleet:
    owner: Member
    north: UUID
    south: UUID
    kda: UUID
    kdb: UUID
    kdc: UUID


@pytest.fixture
def fleet(operator_conn: Conn, owner_conn: Conn) -> Fleet:
    owner = provision_member(operator_conn, 1, "Owner", "Olive", "Owner")
    north = add_company(owner_conn, owner.org, "North Star")
    south = add_company(owner_conn, owner.org, "South Line")
    return Fleet(
        owner=owner,
        north=north,
        south=south,
        kda=add_vehicle(owner_conn, owner.org, north, "KDA 482M", joined_on=date(2026, 1, 1)),
        kdb=add_vehicle(owner_conn, owner.org, north, "KDB 111A", joined_on=date(2026, 1, 1)),
        kdc=add_vehicle(owner_conn, owner.org, south, "KDC 200B", joined_on=date(2026, 1, 1)),
    )


@contextmanager
def _as(conn: Conn, who: Member) -> Iterator[None]:
    with conn.transaction():
        conn.execute(
            "SELECT tenancy.enter_organization(%s, %s, 'req-setup-helpers', NULL)",
            (who.id, who.org),
        )
        yield


def _scalar(conn: Conn, query: str, params: Any = ()) -> Any:
    row = conn.execute(query, params).fetchone()
    assert row is not None
    return next(iter(row.values()))


def _ids(conn: Conn, function: str) -> set[UUID]:
    return {UUID(str(r["id"])) for r in conn.execute(f"SELECT id FROM {function}() AS v (id)")}


# --- visibility ------------------------------------------------------------------------


def test_an_all_companies_scope_sees_every_company_and_vehicle(
    executor: Conn, owner_conn: Conn, operator_conn: Conn, fleet: Fleet
) -> None:
    clerk = provision_member(operator_conn, 2, "Office admin", "Otto", "Office")
    set_scope(owner_conn, clerk, clerk.org, all_companies=True)
    with _as(executor, clerk):
        assert _ids(executor, "setup.visible_companies") == {fleet.north, fleet.south}
        assert _ids(executor, "setup.visible_vehicles") == {fleet.kda, fleet.kdb, fleet.kdc}
        assert _scalar(executor, "SELECT setup.company_visible(%s)", (fleet.south,)) is True
        assert _scalar(executor, "SELECT setup.vehicle_visible(%s)", (fleet.kdc,)) is True


def test_a_company_scope_sees_its_companies_and_their_vehicles(
    executor: Conn, owner_conn: Conn, operator_conn: Conn, fleet: Fleet
) -> None:
    clerk = provision_member(operator_conn, 2, "Office admin", "Otto", "Office")
    set_scope(owner_conn, clerk, clerk.org, companies=[fleet.north])
    with _as(executor, clerk):
        assert _ids(executor, "setup.visible_companies") == {fleet.north}
        assert _ids(executor, "setup.visible_vehicles") == {fleet.kda, fleet.kdb}
        assert _scalar(executor, "SELECT setup.company_visible(%s)", (fleet.south,)) is False
        assert _scalar(executor, "SELECT setup.vehicle_visible(%s)", (fleet.kdc,)) is False
        assert _scalar(executor, "SELECT setup.vehicle_visible(%s)", (fleet.kda,)) is True


def test_a_vehicle_scope_sees_its_vehicles_and_the_companies_that_own_them(
    executor: Conn, owner_conn: Conn, operator_conn: Conn, fleet: Fleet
) -> None:
    clerk = provision_member(operator_conn, 2, "Office admin", "Otto", "Office")
    set_scope(owner_conn, clerk, clerk.org, vehicles=[fleet.kdc])
    with _as(executor, clerk):
        assert _ids(executor, "setup.visible_companies") == {fleet.south}
        assert _ids(executor, "setup.visible_vehicles") == {fleet.kdc}
        assert _scalar(executor, "SELECT setup.company_visible(%s)", (fleet.south,)) is True
        assert _scalar(executor, "SELECT setup.company_visible(%s)", (fleet.north,)) is False
        assert _scalar(executor, "SELECT setup.vehicle_visible(%s)", (fleet.kda,)) is False


def test_an_unknown_id_is_not_visible(executor: Conn, fleet: Fleet) -> None:
    with _as(executor, fleet.owner):
        missing = UUID(int=7)
        assert _scalar(executor, "SELECT setup.company_visible(%s)", (missing,)) is False
        assert _scalar(executor, "SELECT setup.vehicle_visible(%s)", (missing,)) is False


# --- activity, away days and the target in force --------------------------------------


@pytest.mark.parametrize(
    ("archived_on", "day", "active"),
    [
        (None, date(2026, 3, 5), True),
        (date(2026, 3, 6), date(2026, 3, 5), True),
        (date(2026, 3, 5), date(2026, 3, 5), False),
        (date(2026, 3, 1), date(2026, 3, 5), False),
    ],
)
def test_a_company_is_active_until_its_archive_date(
    executor: Conn,
    owner_conn: Conn,
    fleet: Fleet,
    archived_on: date | None,
    day: date,
    active: bool,
) -> None:
    owner_conn.execute(
        "UPDATE setup.psv_companies SET archived_on = %s WHERE id = %s", (archived_on, fleet.south)
    )
    with _as(executor, fleet.owner):
        assert (
            _scalar(executor, "SELECT setup.company_active_on(%s, %s)", (fleet.south, day))
            is active
        )


def test_a_vehicle_is_active_from_joining_until_it_leaves_and_never_while_away(
    executor: Conn, owner_conn: Conn, fleet: Fleet
) -> None:
    owner_conn.execute(
        "UPDATE setup.fleet_vehicles SET left_on = %s WHERE id = %s", (date(2026, 3, 20), fleet.kda)
    )
    add_away(owner_conn, fleet.owner.org, fleet.kda, date(2026, 2, 10), date(2026, 2, 13))
    days = {
        date(2025, 12, 31): (False, False),
        date(2026, 1, 1): (True, False),
        date(2026, 2, 9): (True, False),
        date(2026, 2, 10): (False, True),
        date(2026, 2, 12): (False, True),
        date(2026, 2, 13): (True, False),
        date(2026, 3, 19): (True, False),
        date(2026, 3, 20): (False, False),
    }
    with _as(executor, fleet.owner):
        for day, (active, away) in days.items():
            assert (
                _scalar(executor, "SELECT setup.vehicle_active_on(%s, %s)", (fleet.kda, day))
                is active
            ), day
            assert (
                _scalar(executor, "SELECT setup.vehicle_away_on(%s, %s)", (fleet.kda, day)) is away
            ), day
        assert (
            _scalar(
                executor, "SELECT setup.vehicle_active_on(%s, %s)", (UUID(int=9), date(2026, 2, 1))
            )
            is False
        )


def test_the_target_in_force_is_the_latest_one_with_the_highest_revision_on_a_tie(
    executor: Conn, owner_conn: Conn, fleet: Fleet
) -> None:
    org = fleet.owner.org
    add_target(owner_conn, org, fleet.kda, 1, date(2026, 1, 1), 7000)
    add_target(owner_conn, org, fleet.kda, 2, date(2026, 3, 16), 14000)
    add_target(owner_conn, org, fleet.kda, 3, date(2026, 4, 1), 8000)
    add_target(owner_conn, org, fleet.kda, 4, date(2026, 4, 1), 9000)
    add_target(owner_conn, org, fleet.kda, 5, date(2026, 2, 1), 7500)
    expected = {
        date(2025, 12, 31): Decimal(0),
        date(2026, 1, 1): Decimal(7000),
        date(2026, 1, 31): Decimal(7000),
        date(2026, 2, 1): Decimal(7500),
        date(2026, 3, 15): Decimal(7500),
        date(2026, 3, 16): Decimal(14000),
        date(2026, 4, 1): Decimal(9000),
        date(2026, 9, 1): Decimal(9000),
    }
    with _as(executor, fleet.owner):
        for day, amount in expected.items():
            assert _scalar(executor, "SELECT setup.target_on(%s, %s)", (fleet.kda, day)) == amount


def test_there_is_no_target_on_an_away_day_or_after_leaving(
    executor: Conn, owner_conn: Conn, fleet: Fleet
) -> None:
    org = fleet.owner.org
    add_target(owner_conn, org, fleet.kda, 1, date(2026, 1, 1), 7000)
    add_away(owner_conn, org, fleet.kda, date(2026, 2, 10), date(2026, 2, 13))
    owner_conn.execute(
        "UPDATE setup.fleet_vehicles SET left_on = %s WHERE id = %s", (date(2026, 3, 20), fleet.kda)
    )
    with _as(executor, fleet.owner):
        for day, amount in [
            (date(2026, 2, 9), 7000),
            (date(2026, 2, 10), 0),
            (date(2026, 2, 13), 7000),
            (date(2026, 3, 20), 0),
        ]:
            assert _scalar(executor, "SELECT setup.target_on(%s, %s)", (fleet.kda, day)) == amount


# --- registrations --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("given", "stored"),
    [("kda482m", "KDA 482M"), ("KDA 482M", "KDA 482M"), ("  kDa 48 2m ", "KDA 482M")],
)
def test_a_registration_is_stored_with_one_space(executor: Conn, given: str, stored: str) -> None:
    assert _scalar(executor, "SELECT setup.registration_normalize(%s)", (given,)) == stored


@pytest.mark.parametrize("given", ["KDA-482M", "KD 482M", "ABC 123D", "KDA 48M", "", None])
def test_a_registration_of_the_wrong_shape_is_refused(executor: Conn, given: str | None) -> None:
    with pytest.raises(psycopg.Error) as caught:
        executor.execute("SELECT setup.registration_normalize(%s)", (given,))
    assert caught.value.sqlstate == "XC422"
    assert caught.value.diag.message_primary == "vehicle_registration_format"


# --- schedule shape -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("frequency", "day", "last_day", "month", "valid"),
    [
        (2, 0, False, None, True),
        (2, 6, False, None, True),
        (2, 7, False, None, False),
        (2, None, False, None, False),
        (2, 3, True, None, False),
        (2, 3, False, 3, False),
        (3, 1, False, None, True),
        (3, 28, False, None, True),
        (3, 29, False, None, False),
        (3, None, True, None, True),
        (3, None, False, None, False),
        (3, 10, True, None, False),
        (3, 10, False, 3, False),
        (4, 10, False, 3, True),
        (4, None, True, 2, True),
        (4, 10, False, None, False),
        (4, 10, False, 13, False),
        (4, 29, False, 3, False),
        (1, None, False, None, True),
        (1, 3, False, None, False),
        (1, None, True, None, False),
        (5, 3, False, None, False),
        (None, None, None, None, False),
    ],
)
def test_the_schedule_shape_is_the_check_constraint(
    executor: Conn,
    frequency: int | None,
    day: int | None,
    last_day: bool | None,
    month: int | None,
    valid: bool,
) -> None:
    assert (
        _scalar(
            executor,
            "SELECT setup.schedule_valid(%s::integer, %s::integer, %s::boolean, %s::integer)",
            (frequency, day, last_day, month),
        )
        is valid
    )


# --- due days -------------------------------------------------------------------------

_DUE = (
    "SELECT coalesce(array_agg(d ORDER BY d), '{}') AS days FROM setup.recurring_due_days("
    "(SELECT v FROM setup.recurring_versions AS v WHERE v.id = %s), %s, %s) AS d"
)


def _due(conn: Conn, version: UUID, first: date, last: date) -> list[date]:
    row = conn.execute(_DUE, (version, first, last)).fetchone()
    assert row is not None
    return list(row["days"])


def _schedule(owner_conn: Conn, fleet: Fleet, *versions: Version, **item: Any) -> list[UUID]:
    _, ids = add_schedule(owner_conn, fleet.owner.org, *versions, **item)
    return ids


def _v(fleet: Fleet, effective_from: date, **fields: Any) -> Version:
    return Version(effective_from=effective_from, shares={fleet.kda: 100}, **fields)


def test_a_weekly_version_posts_on_its_weekday(
    executor: Conn, owner_conn: Conn, fleet: Fleet
) -> None:
    (weekly,) = _schedule(
        owner_conn, fleet, _v(fleet, date(2027, 11, 1), frequency=2, day=3, kind=2)
    )
    with _as(executor, fleet.owner):
        assert _due(executor, weekly, date(2027, 11, 1), date(2027, 11, 30)) == [
            date(2027, 11, 3),
            date(2027, 11, 10),
            date(2027, 11, 17),
            date(2027, 11, 24),
        ]


def test_a_monthly_version_posts_on_its_day(executor: Conn, owner_conn: Conn, fleet: Fleet) -> None:
    (monthly,) = _schedule(owner_conn, fleet, _v(fleet, date(2027, 11, 1), frequency=3, day=28))
    with _as(executor, fleet.owner):
        assert _due(executor, monthly, date(2027, 11, 1), date(2028, 3, 31)) == [
            date(2027, 11, 28),
            date(2027, 12, 28),
            date(2028, 1, 28),
            date(2028, 2, 28),
            date(2028, 3, 28),
        ]


def test_the_last_day_follows_february_in_leap_and_common_years(
    executor: Conn, owner_conn: Conn, fleet: Fleet
) -> None:
    (last,) = _schedule(
        owner_conn, fleet, _v(fleet, date(2027, 1, 1), frequency=3, day=None, last_day=True)
    )
    (february,) = _schedule(
        owner_conn,
        fleet,
        _v(fleet, date(2027, 1, 1), frequency=4, day=None, last_day=True, month=2),
    )
    with _as(executor, fleet.owner):
        assert _due(executor, last, date(2028, 1, 15), date(2028, 4, 10)) == [
            date(2028, 1, 31),
            date(2028, 2, 29),
            date(2028, 3, 31),
        ]
        assert _due(executor, last, date(2027, 2, 1), date(2027, 2, 28)) == [date(2027, 2, 28)]
        assert _due(executor, february, date(2028, 2, 29), date(2028, 3, 1)) == [date(2028, 2, 29)]
        assert _due(executor, february, date(2027, 1, 1), date(2029, 12, 31)) == [
            date(2027, 2, 28),
            date(2028, 2, 29),
            date(2029, 2, 28),
        ]


def test_a_yearly_version_posts_on_its_month_and_day(
    executor: Conn, owner_conn: Conn, fleet: Fleet
) -> None:
    (yearly,) = _schedule(
        owner_conn, fleet, _v(fleet, date(2027, 11, 1), frequency=4, day=15, month=3)
    )
    with _as(executor, fleet.owner):
        assert _due(executor, yearly, date(2027, 11, 1), date(2029, 3, 31)) == [
            date(2028, 3, 15),
            date(2029, 3, 15),
        ]
        assert _due(executor, yearly, date(2028, 3, 16), date(2029, 3, 14)) == []


def test_a_version_superseded_mid_range_stops_where_the_next_takes_over(
    executor: Conn, owner_conn: Conn, fleet: Fleet
) -> None:
    first, second = _schedule(
        owner_conn,
        fleet,
        _v(fleet, date(2027, 11, 1), frequency=2, day=3, kind=2),
        _v(fleet, date(2027, 11, 20), frequency=3, day=10, kind=2, start_on=date(2027, 11, 1)),
    )
    with _as(executor, fleet.owner):
        assert _due(executor, first, date(2027, 11, 1), date(2028, 1, 31)) == [
            date(2027, 11, 3),
            date(2027, 11, 10),
            date(2027, 11, 17),
        ]
        assert _due(executor, second, date(2027, 11, 1), date(2028, 1, 31)) == [
            date(2027, 12, 10),
            date(2028, 1, 10),
        ]


def test_start_end_and_the_stop_bound_the_due_days(
    executor: Conn, owner_conn: Conn, fleet: Fleet
) -> None:
    bounded = _v(
        fleet,
        date(2027, 11, 1),
        frequency=2,
        day=3,
        kind=2,
        start_on=date(2027, 11, 10),
        end_on=date(2027, 12, 15),
    )
    (open_ended,) = _schedule(owner_conn, fleet, bounded)
    (stopped,) = _schedule(owner_conn, fleet, bounded, stopped_from=date(2027, 12, 8))
    with _as(executor, fleet.owner):
        assert _due(executor, open_ended, date(2027, 11, 1), date(2028, 1, 31)) == [
            date(2027, 11, 10),
            date(2027, 11, 17),
            date(2027, 11, 24),
            date(2027, 12, 1),
            date(2027, 12, 8),
            date(2027, 12, 15),
        ]
        assert _due(executor, stopped, date(2027, 11, 1), date(2028, 1, 31)) == [
            date(2027, 11, 10),
            date(2027, 11, 17),
            date(2027, 11, 24),
            date(2027, 12, 1),
        ]
        assert _due(executor, open_ended, date(2027, 12, 2), date(2027, 12, 7)) == []


def test_a_legacy_daily_version_posts_every_day_until_its_end(
    executor: Conn, owner_conn: Conn, fleet: Fleet
) -> None:
    (daily,) = _schedule(
        owner_conn,
        fleet,
        _v(fleet, date(2028, 1, 1), frequency=1, day=None, end_on=date(2028, 1, 10)),
    )
    with _as(executor, fleet.owner):
        assert _due(executor, daily, date(2028, 1, 5), date(2028, 1, 20)) == [
            date(2028, 1, d) for d in range(5, 11)
        ]


def test_an_empty_window_posts_nothing(executor: Conn, owner_conn: Conn, fleet: Fleet) -> None:
    (daily,) = _schedule(owner_conn, fleet, _v(fleet, date(2028, 1, 1), frequency=1, day=None))
    with _as(executor, fleet.owner):
        assert _due(executor, daily, date(2028, 1, 10), date(2028, 1, 9)) == []


def _is_due(v: Version, day: date) -> bool:
    """The test oracle: the per-day rule the stepped generator must agree with."""
    if v.frequency == 1:
        return True
    if v.frequency == 2:
        return (day.isoweekday() % 7) == v.day
    last = (day.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    due_day = last.day if v.last_day else v.day
    if v.frequency == 3:
        return day.day == due_day
    return day.month == v.month and day.day == due_day


def _oracle(versions: list[Version], stopped: date | None, first: date, last: date) -> set[Any]:
    posted: set[Any] = set()
    day = first
    while day <= last:
        in_charge = [i for i, v in enumerate(versions) if v.effective_from <= day]
        if in_charge and (stopped is None or day < stopped):
            revision = max(in_charge)
            v = versions[revision]
            start = v.start_on or v.effective_from
            if start <= day and (v.end_on is None or day <= v.end_on) and _is_due(v, day):
                posted.add((revision + 1, day))
        day += timedelta(days=1)
    return posted


def _random_version(rng: random.Random, fleet: Fleet, origin: date) -> Version:
    frequency = rng.choice([1, 2, 3, 3, 4])
    last_day = frequency in (3, 4) and rng.random() < 0.3
    day: int | None = None
    if frequency == 2:
        day = rng.randrange(7)
    elif frequency in (3, 4) and not last_day:
        day = rng.randint(1, 28)
    effective = origin + timedelta(days=rng.randrange(400))
    start = effective - timedelta(days=rng.randrange(40)) if rng.random() < 0.5 else effective
    end = start + timedelta(days=rng.randrange(20, 500)) if rng.random() < 0.3 else None
    return Version(
        effective_from=effective,
        shares={fleet.kda: 100},
        kind=2,
        frequency=frequency,
        day=day,
        last_day=last_day,
        month=rng.randint(1, 12) if frequency == 4 else None,
        start_on=start,
        end_on=end,
    )


def test_random_items_post_on_the_days_the_per_day_rule_names(
    executor: Conn, owner_conn: Conn, fleet: Fleet
) -> None:
    rng = random.Random(20260930)  # noqa: S311 - a seeded sample, not a secret
    origin = date(2027, 11, 1)
    for _ in range(400):
        versions = sorted(
            (_random_version(rng, fleet, origin) for _ in range(rng.randint(1, 3))),
            key=lambda v: v.effective_from,
        )
        if rng.random() < 0.5:
            versions.reverse()
        stopped = origin + timedelta(days=rng.randrange(600)) if rng.random() < 0.3 else None
        item, _ = add_schedule(owner_conn, fleet.owner.org, *versions, stopped_from=stopped)
        first = origin + timedelta(days=rng.randrange(300))
        last = first + timedelta(days=rng.randrange(500))
        with _as(executor, fleet.owner):
            rows = executor.execute(
                "SELECT v.revision, d FROM setup.recurring_versions AS v, "
                "setup.recurring_due_days(v, %s, %s) AS d WHERE v.item_id = %s",
                (first, last, item),
            ).fetchall()
        assert {(r["revision"], r["d"]) for r in rows} == _oracle(versions, stopped, first, last)


# --- versions -------------------------------------------------------------------------


def test_the_current_version_is_the_highest_revision_and_the_one_on_a_day_rules_it(
    executor: Conn, owner_conn: Conn, fleet: Fleet
) -> None:
    item, (first, second) = add_schedule(
        owner_conn,
        fleet.owner.org,
        _v(fleet, date(2026, 3, 1)),
        _v(fleet, date(2026, 2, 1), start_on=date(2026, 3, 1)),
    )
    with _as(executor, fleet.owner):
        current = executor.execute(
            "SELECT (setup.recurring_current_version(%s)).id AS id", (item,)
        ).fetchone()
        assert current is not None and current["id"] == second
        for day, expected in [
            (date(2026, 1, 31), None),
            (date(2026, 2, 1), second),
            (date(2026, 3, 5), second),
        ]:
            on = executor.execute(
                "SELECT (setup.recurring_version_on(%s, %s)).id AS id", (item, day)
            ).fetchone()
            assert on is not None and on["id"] == expected, day
        assert first != second


# --- banker's rounding ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "rounded"),
    [
        ("0.125", "0.12"),
        ("0.135", "0.14"),
        ("2142.857142857", "2142.86"),
        ("-0.125", "-0.12"),
        ("-0.135", "-0.14"),
        ("1000", "1000.00"),
        ("0.1251", "0.13"),
    ],
)
def test_half_even_rounding_takes_the_even_neighbour_of_an_exact_half(
    executor: Conn, value: str, rounded: str
) -> None:
    result = _scalar(executor, "SELECT revenue.round_half_even(%s::numeric, 2)", (value,))
    assert str(result) == rounded


# --- snapshots ------------------------------------------------------------------------


def _text(conn: Conn, query: str, params: Any) -> str:
    return str(_scalar(conn, f"SELECT ({query})::text", params))


def test_the_company_snapshot_is_the_dotnet_json(
    executor: Conn, owner_conn: Conn, fleet: Fleet
) -> None:
    # Active is "no archive date" (CompanyUseCases.Snapshot), so an archive dated after a
    # business date that was moved back still reads as not active.
    owner_conn.execute(
        "UPDATE setup.psv_companies SET archived_on = %s WHERE id = %s",
        (date(2026, 3, 10), fleet.south),
    )
    with _as(executor, fleet.owner):
        assert _text(executor, "setup.company_snapshot(%s)", (fleet.north,)) == (
            f'{{"Id":"{fleet.north}","Name":"North Star","ArchivedOn":null,"Active":true}}'
        )
        assert _text(executor, "setup.company_snapshot(%s)", (fleet.south,)) == (
            f'{{"Id":"{fleet.south}","Name":"South Line","ArchivedOn":"2026-03-10","Active":false}}'
        )
        assert _text(executor, "setup.company_snapshot(%s)", (UUID(int=3),)) == ("null")


def test_the_vehicle_snapshot_is_the_dotnet_json(
    executor: Conn, owner_conn: Conn, fleet: Fleet
) -> None:
    org = fleet.owner.org
    add_target_set(
        owner_conn,
        org,
        fleet.kda,
        date(2026, 3, 16),
        [Decimal("2100.00"), 2000, 2000, 2000, Decimal("2000.50"), 2400, 1500],
    )
    add_target(owner_conn, org, fleet.kda, 1, date(2026, 1, 1), Decimal("7000.00"))
    add_away(owner_conn, org, fleet.kda, date(2026, 2, 10), date(2026, 2, 13))
    add_away(owner_conn, org, fleet.kda, date(2026, 1, 5), date(2026, 1, 7))
    owner_conn.execute(
        "UPDATE setup.fleet_vehicles SET left_on = %s, fleet_number = 'N-07', "
        "initial_investment = 1500000.50 WHERE id = %s",
        (date(2026, 3, 20), fleet.kda),
    )
    with _as(executor, fleet.owner):
        assert _text(executor, "setup.vehicle_snapshot(%s)", (fleet.kda,)) == (
            f'{{"Id":"{fleet.kda}","Registration":"KDA 482M","FleetNumber":"N-07",'
            f'"CompanyId":"{fleet.north}","JoinedOn":"2026-01-01","LeftOn":"2026-03-20",'
            '"InitialInvestment":1500000.5,"TargetSets":['
            '{"StartsOn":"2026-01-01","Monday":1000,"Tuesday":1000,"Wednesday":1000,'
            '"Thursday":1000,"Friday":1000,"Saturday":1000,"Sunday":1000},'
            '{"StartsOn":"2026-03-16","Monday":2100,"Tuesday":2000,"Wednesday":2000,'
            '"Thursday":2000,"Friday":2000.5,"Saturday":2400,"Sunday":1500}],'
            '"Away":[{"LeftOn":"2026-01-05","ReturnedOn":"2026-01-07"},'
            '{"LeftOn":"2026-02-10","ReturnedOn":"2026-02-13"}]}'
        )
        assert _text(executor, "setup.vehicle_snapshot(%s)", (fleet.kdb,)) == (
            f'{{"Id":"{fleet.kdb}","Registration":"KDB 111A","FleetNumber":null,'
            f'"CompanyId":"{fleet.north}","JoinedOn":"2026-01-01","LeftOn":null,'
            '"InitialInvestment":null,"TargetSets":[],"Away":[]}'
        )


def test_the_scheduled_item_snapshot_is_the_dotnet_json(
    executor: Conn, owner_conn: Conn, fleet: Fleet
) -> None:
    org = fleet.owner.org
    category = add_category(owner_conn, org, "Charges", bucket=2)
    parking = add_item(owner_conn, org, category, "Parking")
    low, high = sorted([fleet.kda, fleet.kdb], key=str)
    item, (first, second) = add_schedule(
        owner_conn,
        org,
        Version(
            effective_from=date(2026, 3, 1),
            shares={high: Decimal("700.00"), low: Decimal("300.00")},
            name="Parking",
            frequency=2,
            day=1,
            expense_item_id=parking,
            bucket=2,
            note="Stage fees",
        ),
        Version(
            effective_from=date(2026, 3, 20),
            shares={low: Decimal("1250.50")},
            name="Owner savings",
            kind=2,
            frequency=4,
            day=None,
            last_day=True,
            month=2,
            start_on=date(2026, 3, 1),
            end_on=date(2027, 12, 31),
        ),
        stopped_from=date(2026, 6, 1),
    )
    with _as(executor, fleet.owner):
        assert _text(executor, "setup.recurring_snapshot(%s)", (item,)) == (
            f'{{"Id":"{item}","StoppedFrom":"2026-06-01","Versions":['
            f'{{"Id":"{first}","Revision":1,"EffectiveFrom":"2026-03-01","Name":"Parking",'
            '"Kind":1,"Amount":1000,"Frequency":2,"Day":1,"LastDay":false,"Month":null,'
            f'"Start":"2026-03-01","End":null,"ExpenseItemId":"{parking}","Bucket":2,'
            f'"Note":"Stage fees","Allocations":[{{"VehicleId":"{low}","Amount":300}},'
            f'{{"VehicleId":"{high}","Amount":700}}]}},'
            f'{{"Id":"{second}","Revision":2,"EffectiveFrom":"2026-03-20","Name":"Owner savings",'
            '"Kind":2,"Amount":1250.5,"Frequency":4,"Day":null,"LastDay":true,"Month":2,'
            '"Start":"2026-03-01","End":"2027-12-31","ExpenseItemId":null,"Bucket":null,'
            f'"Note":null,"Allocations":[{{"VehicleId":"{low}","Amount":1250.5}}]}}]}}'
        )


def test_the_catalogue_and_investment_snapshots_are_the_dotnet_json(
    executor: Conn, owner_conn: Conn, fleet: Fleet
) -> None:
    org = fleet.owner.org
    finance = add_main_category(owner_conn, org, "Finance")
    loans = add_category(
        owner_conn, org, "Loans", bucket=3, stopped_on=date(2026, 3, 2), main_category=finance
    )
    fuel = add_category(owner_conn, org, "Fuel", bucket=None)
    repayment = add_item(owner_conn, org, loans, "Loan repayment")
    entry = add_investment(
        owner_conn,
        org,
        fleet.kda,
        date(2026, 2, 3),
        "Deposit on the unit",
        Decimal("500000.00"),
        recorder=fleet.owner.id,
    )
    with _as(executor, fleet.owner):
        assert _text(executor, "setup.expense_category_snapshot(%s)", (loans,)) == (
            f'{{"Id":"{loans}","Name":"Loans","MainCategoryId":"{finance}",'
            '"StoppedOn":"2026-03-02"}'
        )
        assert _text(executor, "setup.expense_category_snapshot(%s)", (fuel,)) == (
            f'{{"Id":"{fuel}","Name":"Fuel","MainCategoryId":null,"StoppedOn":null}}'
        )
        assert _text(executor, "setup.expense_main_category_snapshot(%s)", (finance,)) == (
            f'{{"Id":"{finance}","Name":"Finance"}}'
        )
        assert _text(executor, "setup.expense_item_snapshot(%s)", (repayment,)) == (
            f'{{"Id":"{repayment}","CategoryId":"{loans}",'
            '"Name":"Loan repayment","StoppedOn":null}'
        )
        assert _text(executor, "setup.investment_snapshot(%s)", (entry,)) == (
            f'{{"Id":"{entry}","VehicleId":"{fleet.kda}","Date":"2026-02-03",'
            '"Description":"Deposit on the unit","Amount":500000}'
        )
        for builder in (
            "setup.expense_category_snapshot",
            "setup.expense_main_category_snapshot",
            "setup.expense_item_snapshot",
            "setup.investment_snapshot",
            "setup.recurring_snapshot",
            "setup.vehicle_snapshot",
        ):
            assert _text(executor, f"{builder}(%s)", (UUID(int=5),)) == "null"


# --- target sets ----------------------------------------------------------------------


def test_a_day_target_is_the_weekday_figure_of_the_set_in_force(
    executor: Conn, owner_conn: Conn, fleet: Fleet
) -> None:
    org = fleet.owner.org
    add_target_set(
        owner_conn, org, fleet.kda, date(2026, 1, 5), [100, 200, 300, 400, 500, 600, 700]
    )
    add_target_set(owner_conn, org, fleet.kda, date(2026, 1, 14), [10, 20, 30, 40, 50, 60, 70])
    with _as(executor, fleet.owner):
        for day, amount in [
            (date(2026, 1, 4), 0),
            (date(2026, 1, 5), 100),
            (date(2026, 1, 10), 600),
            (date(2026, 1, 11), 700),
            (date(2026, 1, 13), 200),
            (date(2026, 1, 14), 30),
            (date(2026, 1, 18), 70),
        ]:
            target = _scalar(executor, "SELECT setup.day_target(%s, %s)", (fleet.kda, day))
            assert target == amount, day


def test_there_is_no_day_target_while_away_after_leaving_or_without_a_set(
    executor: Conn, owner_conn: Conn, fleet: Fleet
) -> None:
    org = fleet.owner.org
    add_target_set(owner_conn, org, fleet.kda, date(2026, 1, 5), [100] * 7)
    add_away(owner_conn, org, fleet.kda, date(2026, 2, 10), date(2026, 2, 13))
    owner_conn.execute(
        "UPDATE setup.fleet_vehicles SET left_on = %s WHERE id = %s", (date(2026, 3, 20), fleet.kda)
    )
    with _as(executor, fleet.owner):
        for day, amount in [
            (date(2026, 2, 9), 100),
            (date(2026, 2, 10), 0),
            (date(2026, 2, 12), 0),
            (date(2026, 2, 13), 100),
            (date(2026, 3, 19), 100),
            (date(2026, 3, 20), 0),
        ]:
            target = _scalar(executor, "SELECT setup.day_target(%s, %s)", (fleet.kda, day))
            assert target == amount, day
        no_set = _scalar(executor, "SELECT setup.day_target(%s, %s)", (fleet.kdb, date(2026, 2, 2)))
        assert no_set == 0


def test_the_set_in_force_is_the_latest_started_and_its_week_total_is_the_sum_of_seven(
    executor: Conn, owner_conn: Conn, fleet: Fleet
) -> None:
    org = fleet.owner.org
    first = add_target_set(
        owner_conn, org, fleet.kda, date(2026, 1, 5), [1000, 1000, 1000, 1000, 1000, 1500, "500.25"]
    )
    second = add_target_set(owner_conn, org, fleet.kda, date(2026, 2, 2), [Decimal("0.01")] * 7)
    with _as(executor, fleet.owner):
        for day, expected in [
            (date(2026, 1, 4), None),
            (date(2026, 1, 5), first),
            (date(2026, 2, 1), first),
            (date(2026, 2, 2), second),
            (date(2026, 12, 31), second),
        ]:
            row = executor.execute(
                "SELECT (setup.target_set_on(%s, %s)).id AS id", (fleet.kda, day)
            ).fetchone()
            assert row is not None and row["id"] == expected, day
        week = "SELECT setup.week_total(setup.target_set_on(%s, %s))"
        assert _scalar(executor, week, (fleet.kda, date(2026, 1, 20))) == Decimal("7000.25")
        assert _scalar(executor, week, (fleet.kda, date(2026, 1, 4))) is None
        on = "SELECT setup.target_on(%s, %s)"
        assert _scalar(executor, on, (fleet.kda, date(2026, 1, 20))) == Decimal("7000.25")
        assert _scalar(executor, on, (fleet.kda, date(2026, 2, 2))) == Decimal("0.07")


@pytest.mark.parametrize(
    "days",
    [
        [1, 2, 3, 4, 5, 6, 7],
        [Decimal(d) for d in ("0.01", "999999999999.99", "1.50", "1.5", "100", "100", "100")],
    ],
)
def test_seven_positive_amounts_are_day_targets(executor: Conn, days: list[Any]) -> None:
    checked = _scalar(executor, "SELECT setup.check_day_targets(%s::numeric[])", (days,))
    assert checked == [Decimal(d) for d in days]


@pytest.mark.parametrize(
    ("days", "code"),
    [
        (None, "target_days_required"),
        ([100] * 6, "target_days_required"),
        ([100] * 8, "target_days_required"),
        ([100, 100, None, 100, 100, 100, 100], "target_days_required"),
        ([[100] * 7], "target_days_required"),
        ([100, 100, 100, 0, 100, 100, 100], "money_invalid"),
        ([100, 100, 100, -5, 100, 100, 100], "money_invalid"),
        ([Decimal(100)] * 3 + [Decimal("1.005")] + [Decimal(100)] * 3, "money_invalid"),
        ([Decimal(100)] * 3 + [Decimal("1000000000000")] + [Decimal(100)] * 3, "money_invalid"),
    ],
)
def test_day_targets_that_are_not_seven_positive_amounts_are_refused(
    executor: Conn, days: list[Any] | None, code: str
) -> None:
    with pytest.raises(psycopg.Error) as caught:
        executor.execute("SELECT setup.check_day_targets(%s::numeric[])", (days,))
    assert caught.value.sqlstate == "XC422"
    assert caught.value.diag.message_primary == code


# --- fleet numbers --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("given", "stored"),
    [("A-17", "A-17"), ("  Kb 12 ", "Kb 12"), ("  " + "x" * 20 + "  ", "x" * 20)],
)
def test_a_fleet_number_is_stored_trimmed(executor: Conn, given: str, stored: str) -> None:
    assert _scalar(executor, "SELECT setup.fleet_number(%s)", (given,)) == stored


@pytest.mark.parametrize(
    ("given", "code"),
    [
        (None, "vehicle_fleet_required"),
        ("", "vehicle_fleet_required"),
        ("   ", "vehicle_fleet_required"),
        ("x" * 21, "vehicle_fleet_length"),
    ],
)
def test_an_empty_or_long_fleet_number_is_refused(
    executor: Conn, given: str | None, code: str
) -> None:
    with pytest.raises(psycopg.Error) as caught:
        executor.execute("SELECT setup.fleet_number(%s)", (given,))
    assert caught.value.sqlstate == "XC422"
    assert caught.value.diag.message_primary == code


# --- kinds of scheduled items ---------------------------------------------------------


@pytest.mark.parametrize(
    ("kind", "verb", "right"),
    [
        (1, "view", "scheduled.view"),
        (1, "add", "scheduled.add"),
        (1, "edit", "scheduled.edit"),
        (2, "view", "savings.view"),
        (2, "add", "savings.add"),
        (2, "edit", "savings.edit"),
    ],
)
def test_each_kind_of_scheduled_item_has_its_own_rights(
    executor: Conn, kind: int, verb: str, right: str
) -> None:
    assert _scalar(executor, "SELECT setup.recurring_kind_right(%s, %s)", (kind, verb)) == right


def test_the_automatic_reason_names_the_kind_and_the_item(executor: Conn) -> None:
    reason = "SELECT setup.recurring_change_reason(%s, %s)"
    assert _scalar(executor, reason, (1, "Insurance")) == "Scheduled expense, Insurance"
    assert _scalar(executor, reason, (2, "Owner savings")) == "Saving, Owner savings"


def test_an_item_is_hidden_from_a_member_without_the_view_right_of_its_current_kind(
    executor: Conn, owner_conn: Conn, operator_conn: Conn, fleet: Fleet
) -> None:
    org = fleet.owner.org
    clerk = provision_member(operator_conn, 2, "Office admin", "Otto", "Office")
    set_scope(owner_conn, clerk, clerk.org, all_companies=True)
    cost, _ = add_schedule(owner_conn, org, _v(fleet, date(2026, 3, 1)))
    saving, _ = add_schedule(owner_conn, org, _v(fleet, date(2026, 3, 1), kind=2))
    switched, _ = add_schedule(
        owner_conn, org, _v(fleet, date(2026, 3, 1)), _v(fleet, date(2026, 4, 1), kind=2)
    )

    def visible() -> dict[UUID, bool]:
        with _as(executor, clerk):
            return {
                item: _scalar(executor, "SELECT setup.recurring_visible(%s)", (item,))
                for item in (cost, saving, switched)
            }

    assert visible() == {cost: True, saving: True, switched: True}
    set_override(owner_conn, clerk, "savings.view", False)
    assert visible() == {cost: True, saving: False, switched: False}
    set_override(owner_conn, clerk, "savings.view", True)
    set_override(owner_conn, clerk, "scheduled.view", False)
    assert visible() == {cost: False, saving: True, switched: True}
