"""Pause, resume, runs and summary of scheduled items over HTTP (``docs/06-http-contract.md``
2.13.4, S53 to S56), the four ``RecurringPauseTests`` scenarios with the Python rules: a saving's
last run, balance, runs and the month summary; a pause skips runs until resumed; resuming the
day it was paused skips nothing; only a caller with the kind's pause right who sees every
vehicle may pause, and a stopped item cannot be paused. Also the DTO key orders, the saving's
rule and opening on S26/S27 (an absent opening keeps it), 401/403/404 and the statement budget
of 2. The business date is Wednesday 7 October 2026 (the API tests' clock in Nairobi)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest

from ..support.client import ApiFactory, AuthApi
from ..support.rows import seed_organization
from ..support.setup_client import (
    FORBIDDEN,
    INVALID,
    NOT_FOUND,
    Member,
    join,
    ok,
    problem,
    statements,
)
from ..support.setup_rows import add_record
from ..support.tenancy import Member as Person
from ..support.tenancy import set_override, set_scope

pytestmark = pytest.mark.asyncio(loop_scope="session")

TODAY = date(2026, 10, 7)
SUMMARY_KEYS = [
    "from",
    "to",
    "costsDue",
    "saved",
    "savingsBalance",
    "runningCosts",
    "pausedCosts",
    "runningSavings",
    "pausedSavings",
]
RUNS_KEYS = ["id", "name", "kind", "start", "total", "runCount", "runs"]
RUN_KEYS = ["date", "amount", "shares"]
SHARE_KEYS = ["vehicleId", "registration", "amount", "state", "revenue"]


@dataclass(frozen=True, slots=True)
class Fleet:
    north: str
    south: str
    kda: str
    kdb: str
    kdc: str
    parking: str


@pytest.fixture
async def api(make_api: ApiFactory) -> AuthApi:
    return await make_api()


@pytest.fixture
async def owner(api: AuthApi) -> Member:
    return await join(api, email="ann@example.com", phone="0711000111", role="Owner")


async def post_id(api: AuthApi, member: Member, path: str, body: dict[str, Any]) -> str:
    return str(ok(await api.client.post(path, json=body, headers=member.headers))["id"])


@pytest.fixture
async def fleet(api: AuthApi, owner: Member) -> Fleet:
    north = await post_id(api, owner, "/setup/companies", {"name": "North Star"})
    south = await post_id(api, owner, "/setup/companies", {"name": "South Line"})

    async def vehicle(company: str, registration: str) -> str:
        body = {
            "companyId": company,
            "registration": registration,
            "fleetNumber": registration.replace(" ", "")[-4:],
            "joinedOn": "2026-09-01",
            "dayTargets": [1000] * 7,
        }
        return await post_id(api, owner, "/setup/vehicles", body)

    charges = await post_id(api, owner, "/setup/expense-categories", {"name": "Charges"})
    parking = await post_id(
        api, owner, f"/setup/expense-categories/{charges}/items", {"name": "Parking"}
    )
    return Fleet(
        north=north,
        south=south,
        kda=await vehicle(north, "KDA 482M"),
        kdb=await vehicle(north, "KDB 111A"),
        kdc=await vehicle(south, "KDC 200B"),
        parking=parking,
    )


def _org(api: AuthApi) -> UUID:
    row = api.owner.execute("SELECT id FROM tenancy.organizations").fetchone()
    assert row is not None
    return UUID(str(row["id"]))


def _daily(api: AuthApi, fleet: Fleet, *, kind: int, since: int, shares: dict[str, int]) -> str:
    """A daily item seeded as the owner, started ``since`` days ago (a save starts today)."""
    org = _org(api)
    start = TODAY - timedelta(days=since)
    with api.owner.transaction():
        item = api.owner.execute(
            "INSERT INTO setup.recurring_items (organization_id) VALUES (%s) RETURNING id", (org,)
        ).fetchone()
        assert item is not None
        version = api.owner.execute(
            "INSERT INTO setup.recurring_versions (organization_id, item_id, revision, "
            "effective_from, name, kind, amount, frequency, day, last_day, start_on, "
            "expense_item_id, bucket) "
            "VALUES (%s, %s, 1, %s, %s, %s, %s, 1, NULL, false, %s, %s, %s) RETURNING id",
            (
                org,
                item["id"],
                start,
                "Owner savings" if kind == 2 else "Parking",
                kind,
                sum(shares.values()),
                start,
                UUID(fleet.parking) if kind == 1 else None,
                2 if kind == 1 else None,
            ),
        ).fetchone()
        assert version is not None
        for vehicle, amount in shares.items():
            api.owner.execute(
                "INSERT INTO setup.recurring_allocations (organization_id, version_id, "
                "vehicle_id, amount) VALUES (%s, %s, %s, %s)",
                (org, version["id"], UUID(vehicle), amount),
            )
    return str(item["id"])


async def _call(api: AuthApi, member: Member, method: str, path: str, **kw: Any) -> Any:
    return await getattr(api.client, method)(path, headers=member.headers, **kw)


async def _row(api: AuthApi, member: Member, item: str) -> dict[str, Any]:
    page = ok(await _call(api, member, "get", "/setup/recurring?pageSize=100"))
    (found,) = [r for r in page["items"] if r["id"] == item]
    return found


async def scoped(api: AuthApi, fleet: Fleet, *grants: str) -> Member:
    member = await join(api, email="sam@example.com", phone="0733000111", role="Fleet manager")
    org = _org(api)
    for grant in grants:
        set_override(api.owner, Person(member.user_id, org, "", "", "", "", ""), grant)
    set_scope(api.owner, member.user_id, org, companies=[UUID(fleet.north)])
    return member


# --- RecurringPauseTests -----------------------------------------------------------------


async def test_a_savings_last_run_balance_runs_and_the_summary(
    api: AuthApi, owner: Member, fleet: Fleet
) -> None:
    saving = _daily(api, fleet, kind=2, since=2, shares={fleet.kda: 300, fleet.kdb: 200})
    _daily(api, fleet, kind=1, since=8, shares={fleet.kda: 100})
    listed = await _row(api, owner, saving)
    assert (listed["pausedFrom"], listed["lastRun"], listed["lastRunVehicles"]) == (
        None,
        "2026-10-07",
        2,
    )
    assert (listed["balance"], listed["lastRunStates"]) == (
        1500,
        {"saved": 2, "skipped": 0, "held": 0},
    )
    assert (listed["condition"], listed["opening"], listed["nextRun"]) == (None, None, "2026-10-08")
    response, count = await statements(_call(api, owner, "get", f"/setup/recurring/{saving}/runs"))
    runs = ok(response)
    assert count == 2
    assert list(runs) == RUNS_KEYS
    assert (runs["name"], runs["kind"], runs["start"], runs["total"], runs["runCount"]) == (
        "Owner savings",
        2,
        "2026-10-05",
        1500,
        3,
    )
    assert [r["date"] for r in runs["runs"]] == ["2026-10-07", "2026-10-06", "2026-10-05"]
    assert list(runs["runs"][0]) == RUN_KEYS
    assert runs["runs"][0]["shares"] == [
        {
            "vehicleId": fleet.kda,
            "registration": "KDA 482M",
            "amount": 300,
            "state": "saved",
            "revenue": None,
        },
        {
            "vehicleId": fleet.kdb,
            "registration": "KDB 111A",
            "amount": 200,
            "state": "saved",
            "revenue": None,
        },
    ]
    assert [list(s) for s in runs["runs"][0]["shares"]] == [SHARE_KEYS] * 2
    response, count = await statements(_call(api, owner, "get", "/setup/recurring/summary"))
    summary = ok(response)
    assert count == 2
    assert list(summary) == SUMMARY_KEYS
    assert summary == {
        "from": "2026-10-01",
        "to": "2026-10-31",
        "costsDue": 100 * 31,
        "saved": 1500,
        "savingsBalance": 1500,
        "runningCosts": 1,
        "pausedCosts": 0,
        "runningSavings": 1,
        "pausedSavings": 0,
    }


async def test_a_pause_skips_runs_until_it_is_resumed(
    api: AuthApi, owner: Member, fleet: Fleet
) -> None:
    item = _daily(api, fleet, kind=1, since=5, shares={fleet.kda: 100})
    org = _org(api)
    api.owner.execute(
        "UPDATE tenancy.organizations SET business_date = %s WHERE id = %s",
        (TODAY - timedelta(days=3), org),
    )
    response, count = await statements(_call(api, owner, "post", f"/setup/recurring/{item}/pause"))
    assert (ok(response), count) == ({"id": item}, 2)
    assert (await _row(api, owner, item))["pausedFrom"] == "2026-10-04"
    api.owner.execute(
        "UPDATE tenancy.organizations SET business_date = %s WHERE id = %s", (TODAY, org)
    )
    response, count = await statements(_call(api, owner, "post", f"/setup/recurring/{item}/resume"))
    assert (ok(response), count) == ({"id": item}, 2)
    runs = ok(await _call(api, owner, "get", f"/setup/recurring/{item}/runs"))
    assert [r["date"] for r in runs["runs"]] == ["2026-10-07", "2026-10-03", "2026-10-02"]
    history = ok(await _call(api, owner, "get", "/setup/history?section=recurring&pageSize=10"))
    assert [e["reason"] for e in history["items"]] == [
        "Scheduled expense, Parking",
        "Scheduled expense, Parking",
    ]


async def test_resuming_on_the_day_of_the_pause_skips_nothing(
    api: AuthApi, owner: Member, fleet: Fleet
) -> None:
    item = _daily(api, fleet, kind=2, since=1, shares={fleet.kda: 300})
    ok(await _call(api, owner, "post", f"/setup/recurring/{item}/pause"))
    ok(await _call(api, owner, "post", f"/setup/recurring/{item}/resume"))
    runs = ok(await _call(api, owner, "get", f"/setup/recurring/{item}/runs"))
    assert [r["date"] for r in runs["runs"]] == ["2026-10-07", "2026-10-06"]
    assert (await _row(api, owner, item))["pausedFrom"] is None


async def test_only_the_kinds_pause_right_over_every_vehicle_may_pause_and_a_stopped_item_never(
    api: AuthApi, owner: Member, fleet: Fleet
) -> None:
    both = _daily(api, fleet, kind=1, since=1, shares={fleet.kda: 100, fleet.kdc: 100})
    north = _daily(api, fleet, kind=1, since=1, shares={fleet.kda: 100})
    saving = _daily(api, fleet, kind=2, since=1, shares={fleet.kda: 100})
    viewer = await scoped(api, fleet, "scheduled.view", "savings.view")
    problem(await _call(api, viewer, "post", f"/setup/recurring/{north}/pause"), 403, FORBIDDEN)
    manager = await join(api, email="pat@example.com", phone="0744000111", role="Fleet manager")
    org = _org(api)
    for grant in ("scheduled.view", "scheduled.pause", "savings.view"):
        set_override(api.owner, Person(manager.user_id, org, "", "", "", "", ""), grant)
    set_scope(api.owner, manager.user_id, org, companies=[UUID(fleet.north)])
    problem(await _call(api, manager, "post", f"/setup/recurring/{both}/pause"), 403, FORBIDDEN)
    problem(await _call(api, manager, "post", f"/setup/recurring/{saving}/pause"), 403, FORBIDDEN)
    assert ok(await _call(api, manager, "post", f"/setup/recurring/{north}/pause")) == {"id": north}
    api.owner.execute(
        "UPDATE setup.recurring_items SET stopped_from = %s WHERE id = %s", (TODAY, UUID(saving))
    )
    problem(
        await _call(api, owner, "post", f"/setup/recurring/{saving}/pause"),
        400,
        INVALID,
        "The item is already stopped.",
    )
    unknown = "00000000-0000-4000-8000-000000000000"
    problem(await _call(api, owner, "post", f"/setup/recurring/{unknown}/pause"), 404, NOT_FOUND)
    assert (await api.client.post(f"/setup/recurring/{north}/resume")).status_code == 401


# --- the saving's rule and opening on the save routes ----------------------------------------


async def test_a_saving_saves_its_rule_and_opening_and_an_absent_opening_keeps_it(
    api: AuthApi, owner: Member, fleet: Fleet
) -> None:
    body = {
        "name": "Owner savings",
        "kind": 2,
        "amount": 500,
        "frequency": 3,
        "day": 1,
        "start": "2026-01-01",
        "allocations": [{"vehicleId": fleet.kda, "amount": 500}],
        "condition": {"min": 5000, "days": 7},
        "opening": {"date": "2026-10-01", "amounts": [{"vehicleId": fleet.kda, "amount": 2500}]},
    }
    item = str(ok(await _call(api, owner, "post", "/setup/recurring", json=body))["id"])
    listed = await _row(api, owner, item)
    assert (listed["start"], listed["condition"], listed["opening"]) == (
        "2026-10-07",
        {"min": 5000, "days": 7},
        {"date": "2026-10-01", "total": 2500},
    )
    assert (listed["balance"], listed["nextRun"]) == (2500, "2026-11-01")
    kept = {k: v for k, v in body.items() if k != "opening"} | {"note": "Kept"}
    ok(await _call(api, owner, "put", f"/setup/recurring/{item}", json=kept))
    assert (await _row(api, owner, item))["opening"] == {"date": "2026-10-01", "total": 2500}
    ok(await _call(api, owner, "put", f"/setup/recurring/{item}", json=kept | {"opening": None}))
    assert (await _row(api, owner, item))["opening"] is None
    problem(
        await _call(
            api, owner, "put", f"/setup/recurring/{item}", json=kept | {"end": "2026-12-31"}
        ),
        400,
        INVALID,
        "A saving has no end date.",
    )
    problem(
        await _call(
            api,
            owner,
            "post",
            "/setup/recurring",
            json=body | {"condition": {"min": 5000, "days": 3}},
        ),
        400,
        INVALID,
        "Measure the revenue over 1, 7 or 30 days.",
    )


# --- stored columns and other organizations ------------------------------------------------


async def test_unknown_properties_never_reach_a_stored_item(
    api: AuthApi, owner: Member, fleet: Fleet
) -> None:
    """A body naming stored or computed columns is read for its own fields only."""
    stored = {
        "id": str(uuid4()),
        "versionId": str(uuid4()),
        "revision": 9,
        "stoppedFrom": "2026-10-01",
        "pausedFrom": "2026-10-01",
        "balance": 99999,
        "lastRun": "2026-10-01",
        "activeAmount": 1,
        "organizationId": str(uuid4()),
    }
    body = {
        "name": "Owner savings",
        "kind": 2,
        "amount": 500,
        "frequency": 3,
        "day": 1,
        "allocations": [{"vehicleId": fleet.kda, "amount": 500}],
    }
    item = str(
        ok(await _call(api, owner, "post", "/setup/recurring", json={**body, **stored}))["id"]
    )
    assert item != stored["id"]
    row = await _row(api, owner, item)
    assert (row["revision"], row["stoppedFrom"], row["pausedFrom"], row["balance"]) == (
        1,
        None,
        None,
        0,
    )
    assert (row["lastRun"], row["activeAmount"]) == (None, 500)


async def test_another_organizations_items_are_not_found_and_stay_as_they_were(
    api: AuthApi, owner: Member, fleet: Fleet
) -> None:
    other = seed_organization(api.owner)
    count = "SELECT count(*) AS n FROM setup.recurring_pauses WHERE organization_id = %s"
    before = api.owner.execute(count, (other.org,)).fetchone()
    for item in (other.recurring, other.saving):
        for verb in ("pause", "resume"):
            path = f"/setup/recurring/{item}/{verb}"
            problem(await _call(api, owner, "post", path), 404, NOT_FOUND)
        problem(await _call(api, owner, "get", f"/setup/recurring/{item}/runs"), 404, NOT_FOUND)
    assert api.owner.execute(count, (other.org,)).fetchone() == before
    assert fleet


# --- vehicle writes decide held runs ------------------------------------------------------


def _rule(api: AuthApi, item: str, minimum: int, days: int) -> None:
    api.owner.execute(
        "UPDATE setup.recurring_versions SET condition_min = %s, condition_days = %s "
        "WHERE item_id = %s",
        (minimum, days, UUID(item)),
    )


async def _states(api: AuthApi, member: Member, item: str) -> dict[str, list[str]]:
    runs = ok(await _call(api, member, "get", f"/setup/recurring/{item}/runs"))
    return {r["date"]: [s["state"] for s in r["shares"]] for r in runs["runs"]}


def _decided(api: AuthApi, item: str) -> list[tuple[str, int]]:
    rows = api.owner.execute(
        "SELECT run_on, state FROM setup.saving_runs WHERE item_id = %s ORDER BY run_on",
        (UUID(item),),
    ).fetchall()
    return [(str(r["run_on"]), r["state"]) for r in rows]


async def test_a_later_join_date_decides_the_held_runs_whose_window_it_completes(
    api: AuthApi, owner: Member, fleet: Fleet
) -> None:
    saving = _daily(api, fleet, kind=2, since=2, shares={fleet.kda: 500})
    _rule(api, saving, 5000, 7)
    for day in range(1, 7):
        add_record(
            api.owner,
            _org(api),
            UUID(fleet.kda),
            date(2026, 10, day),
            1000,
            recorder=owner.user_id,
        )
    held = {"2026-10-07": ["held"], "2026-10-06": ["held"], "2026-10-05": ["held"]}
    assert await _states(api, owner, saving) == held
    body = {
        "companyId": fleet.north,
        "registration": "KDA 482M",
        "fleetNumber": "482M",
        "joinedOn": "2026-10-01",
    }
    ok(await _call(api, owner, "put", f"/setup/vehicles/{fleet.kda}", json=body))
    assert _decided(api, saving) == [("2026-10-05", 1), ("2026-10-06", 1)]
    assert await _states(api, owner, saving) == held | {
        "2026-10-06": ["saved"],
        "2026-10-05": ["saved"],
    }


async def test_a_restore_decides_the_held_runs_of_the_days_away(
    api: AuthApi, owner: Member, fleet: Fleet
) -> None:
    saving = _daily(api, fleet, kind=2, since=2, shares={fleet.kdb: 500})
    _rule(api, saving, 1000, 1)
    path = f"/setup/vehicles/{fleet.kdb}"
    ok(await _call(api, owner, "post", f"{path}/retire", json={"leftOn": "2026-10-05"}))
    assert await _states(api, owner, saving) == {}
    ok(await _call(api, owner, "post", f"{path}/restore", json={"returnedOn": "2026-10-07"}))
    assert _decided(api, saving) == [("2026-10-05", 2), ("2026-10-06", 2)]
    assert await _states(api, owner, saving) == {
        "2026-10-07": ["held"],
        "2026-10-06": ["skipped"],
        "2026-10-05": ["skipped"],
    }
