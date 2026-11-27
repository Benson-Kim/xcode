"""``api.revenue_image_log``, called as ``xcode_app``: the change-log row of the Revenue Summary
image the device drew, in the organization week holding the date sent, with the company filter
and the search; the rights every revenue export needs, and each input refused in its order.

The business date is 9 Oct 2026 (a Friday). Antony Maina owns the organization, Wanjiru Kamau
(Fleet manager, granted revenue.export) sees North Star only, Grace Njeri (Revenue clerk) holds
no export right. The
week's first day comes from the organization's settings, so the expected week is read from
``api.revenue_week_get`` rather than assumed."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, timedelta
from uuid import UUID, uuid4

import pytest

from ..support.scenario import Conn
from ..support.setup_rows import change_rows, read, refuses
from ..support.tenancy import (
    Member,
    add_company,
    audit_events,
    provision_member,
    set_override,
    set_scope,
)

WEDNESDAY = date(2026, 10, 7)


@dataclass(frozen=True, slots=True)
class World:
    owner: Member
    clerk: Member
    teller: Member
    north: UUID
    south: UUID
    start: date


def words(day: date) -> str:
    return f"{day.day} {day.strftime('%b')} {day.year}"


@pytest.fixture
def world(operator_conn: Conn, owner_conn: Conn, app_conn: Conn) -> World:
    owner = provision_member(operator_conn, 1, "Owner", "Antony", "Maina")
    clerk = provision_member(operator_conn, 3, "Fleet manager", "Wanjiru", "Kamau")
    teller = provision_member(operator_conn, 4, "Revenue clerk", "Grace", "Njeri")
    north = add_company(owner_conn, owner.org, "North Star")
    south = add_company(owner_conn, owner.org, "South Line")
    set_scope(owner_conn, owner, owner.org, all_companies=True)
    set_scope(owner_conn, teller, owner.org, all_companies=True)
    set_scope(owner_conn, clerk, owner.org, companies=[north])
    set_override(owner_conn, clerk, "revenue.export")
    week = read(app_conn, "revenue_week_get", owner, WEDNESDAY, None, None, None, None, None)
    start = date.fromisoformat(week["week_start"])
    return World(owner, clerk, teller, north, south, start)


def test_one_change_log_row_names_the_week_the_company_and_the_search(
    world: World, app_conn: Conn, owner_conn: Conn
) -> None:
    org = world.owner.org
    read(app_conn, "revenue_image_log", world.owner, WEDNESDAY, None, None)
    read(app_conn, "revenue_image_log", world.owner, WEDNESDAY, world.north, "  KDA  ")

    rows = change_rows(owner_conn, org, "reports")
    through = world.start + timedelta(days=6)
    period = f"{words(world.start)} to {words(through)}"
    assert [r["reason"] for r in rows] == [
        f"Exported Revenue for {period} to Summary image",
        f'Exported Revenue for {period}, searched for "KDA" to Summary image',
    ]
    assert json.loads(rows[1]["after"]) == {
        "q": "KDA",
        "screen": "revenue",
        "format": "png",
        "companyId": str(world.north),
        "weekStart": world.start.isoformat(),
    }
    assert all(r["vehicle_id"] is None and r["actor_id"] == world.owner.id for r in rows)
    events = audit_events(owner_conn, org, "reports.exported")
    assert [e["after"]["filters"] for e in events] == ["All companies", "North Star"]


def test_a_scoped_viewer_logs_their_own_company(
    world: World, app_conn: Conn, owner_conn: Conn
) -> None:
    read(app_conn, "revenue_image_log", world.clerk, WEDNESDAY, world.north, None)

    [row] = change_rows(owner_conn, world.owner.org, "reports")
    assert row["actor_id"] == world.clerk.id


def test_refusals_come_in_order_and_write_nothing(
    world: World, app_conn: Conn, owner_conn: Conn
) -> None:
    next_week = world.start + timedelta(days=7)
    long_ago = world.start - timedelta(days=3660)
    refuses(
        app_conn,
        "revenue_image_log",
        world.teller,
        [WEDNESDAY, None, None],
        "XC403",
        "permission_missing",
    )
    refuses(
        app_conn,
        "revenue_image_log",
        world.owner,
        [None, None, "x" * 41],
        "XC422",
        "revenue_search_length",
    )
    for week in (None, next_week, long_ago):
        refuses(
            app_conn,
            "revenue_image_log",
            world.owner,
            [week, None, "x" * 40],
            "XC422",
            "revenue_week_range",
        )
    refuses(
        app_conn,
        "revenue_image_log",
        world.clerk,
        [WEDNESDAY, world.south, None],
        "XC404",
        "not_found",
    )
    refuses(
        app_conn,
        "revenue_image_log",
        world.owner,
        [WEDNESDAY, uuid4(), None],
        "XC404",
        "not_found",
    )
    assert change_rows(owner_conn, world.owner.org, "reports") == []
