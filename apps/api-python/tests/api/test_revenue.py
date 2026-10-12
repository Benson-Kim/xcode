"""The revenue routes against the real database (``docs/06-http-contract.md`` section 2.8): the
week grid, the dashboard and the day's capture in wire order; what the phones' offline queue
gets for each entry it replays, and so which state it moves the entry to; the web's paging
sequence (the released first request, then the pages the truncated grid still lacks); one
vehicle in a past week; the dashboard cards per permission; the route constraints, the 401,
415 and the statement budget of 2; the low-day rule, the gap, the search, the capture time and
the revenue settings.

The business date is 7 Oct 2026, a Wednesday (the test clock in Nairobi); weeks start on
Monday. History before the first request is seeded as ``xcode_owner``. Each organization's
low-day threshold is set to 100 by the ``owner`` fixture, so the small amounts of the capture
cases are ordinary days; the low-day tests put back the default of 4,000."""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

import pytest

from ..support.client import ApiFactory, AuthApi
from ..support.setup_client import (
    FORBIDDEN,
    INVALID,
    NOT_FOUND,
    Member,
    empty,
    join,
    ok,
    problem,
    statements,
)
from ..support.setup_rows import add_record
from ..support.tenancy import Member as Person
from ..support.tenancy import set_override, set_scope

pytestmark = pytest.mark.asyncio(loop_scope="session")

WEEK_KEYS = [
    "weekStart",
    "weekThrough",
    "currentWeekStart",
    "businessDate",
    "companies",
    "vehicles",
    "totalAmount",
    "totalExpected",
    "percent",
    "pageNumber",
    "pageSize",
    "totalVehicles",
    "truncated",
    "dayTotals",
    "firstGap",
    "lowDayThreshold",
    "gapAmberPercent",
    "gap",
    "gapBand",
    "belowThresholdDays",
    "missingDays",
]
VEHICLE_KEYS = [
    "id",
    "companyId",
    "companyName",
    "registration",
    "joinedOn",
    "leftOn",
    "earliestMissing",
    "days",
    "totalAmount",
    "totalExpected",
    "percent",
    "fleetNumber",
    "gap",
    "gapBand",
    "belowThresholdDays",
]
CELL_KEYS = [
    "date",
    "status",
    "expected",
    "amount",
    "reason",
    "note",
    "canEdit",
    "editedAfterCapture",
    "version",
]
DASHBOARD_KEYS = [
    "period",
    "from",
    "through",
    "businessDate",
    "revenue",
    "expected",
    "percent",
    "capturedToday",
    "vehiclesToday",
    "missingDays",
    "missingVehicles",
    "editedRecords",
]
TODAY = "2026-10-07"
CHANGED = "This day already has a different record."
CHANGED_DETAIL = (
    "This day was changed after you opened it. Check the current record and save again."
)
UNKNOWN = "00000000-0000-4000-8000-000000000000"


@pytest.fixture
async def api(make_api: ApiFactory) -> AuthApi:
    return await make_api()


@pytest.fixture
async def owner(api: AuthApi) -> Member:
    joined = await join(api, email="ann@example.com", phone="0711000111", role="Owner")
    threshold(api, 100)
    return joined


def organization(api: AuthApi) -> UUID:
    row = api.owner.execute("SELECT id FROM tenancy.organizations").fetchone()
    assert row is not None
    return UUID(str(row["id"]))


def threshold(api: AuthApi, amount: int | None) -> None:
    """The organization's low-day threshold, or the default (no row) for ``None``."""
    api.owner.execute("DELETE FROM tenancy.organization_revenue_settings")
    if amount is not None:
        api.owner.execute(
            "INSERT INTO tenancy.organization_revenue_settings (organization_id, "
            "low_day_threshold) VALUES (%s, %s)",
            (organization(api), amount),
        )


def person(api: AuthApi, member: Member) -> Person:
    return Person(member.user_id, organization(api), "", "", "", "", "")


async def member(api: AuthApi, role: str, phone: str) -> Member:
    joined = await join(api, email=f"{phone}@example.com", phone=phone, role=role)
    set_scope(api.owner, joined.user_id, organization(api), all_companies=True)
    return joined


async def company(api: AuthApi, owner: Member, name: str) -> str:
    response = await api.client.post("/setup/companies", json={"name": name}, headers=owner.headers)
    return str(ok(response)["id"])


async def vehicle(
    api: AuthApi, owner: Member, company_id: str, registration: str, target: int = 7000
) -> str:
    body = {
        "companyId": company_id,
        "registration": registration,
        "fleetNumber": registration[-4:],
        "joinedOn": "2026-10-01",
        "dayTargets": [target // 7] * 7,
    }
    response = await api.client.post("/setup/vehicles", json=body, headers=owner.headers)
    return str(ok(response)["id"])


def seed(api: AuthApi, owner: Member, vehicle_id: str, day: str, amount: int) -> None:
    add_record(
        api.owner,
        organization(api),
        UUID(vehicle_id),
        date.fromisoformat(day),
        amount,
        recorder=owner.user_id,
    )


def invalid(response: Any, *fields: str) -> None:
    """A framework validation refusal naming exactly these fields."""
    body = problem(response, 400, INVALID, response.json().get("detail"))
    assert body["detail"]
    assert list(body["errors"]) == list(fields)


def save(api: AuthApi, who: Member, vehicle_id: str, day: str, **body: Any) -> Any:
    entry = {"amount": None, "reason": None, "note": None, "version": None, **body}
    return api.client.put(f"/setup/revenue/{vehicle_id}/{day}", json=entry, headers=who.headers)


# --- capture ----------------------------------------------------------------------------


async def test_a_capture_answers_exactly_id_and_version_in_two_statements(
    api: AuthApi, owner: Member
) -> None:
    kda = await vehicle(api, owner, await company(api, owner, "North Star"), "KDA 482M")
    response, count = await statements(save(api, owner, kda, TODAY, amount=1500.5))
    body = ok(response)
    assert count == 2
    assert list(body) == ["id", "version"]
    assert body["version"] == 1
    assert response.content == f'{{"id":"{body["id"]}","version":1}}'.encode()
    again, count = await statements(save(api, owner, kda, TODAY, amount="1500.50", version=9))
    assert count == 2
    assert ok(again) == body
    changed = ok(await save(api, owner, kda, TODAY, amount=1600, version=1))
    assert changed == {"id": body["id"], "version": 2}


@pytest.mark.parametrize(
    ("entry", "detail"),
    [
        ({"amount": 10.001}, "Amount must be positive with at most two decimal places."),
        ({"reason": "no crew"}, "Choose a valid no-earnings reason."),
        ({"amount": 99.99}, "Choose the reason. Revenue is below KES 100."),
        ({"amount": 100, "reason": "Garage"}, "A reason is kept only for revenue below KES 100."),
        ({"amount": 100, "note": "Late"}, "Only Other may have a no-earnings note."),
        ({}, "Enter revenue or choose a no-earnings reason."),
        ({"amount": 0}, "Amount must be positive with at most two decimal places."),
    ],
)
async def test_an_entry_that_cannot_be_recorded_is_a_400(
    api: AuthApi, owner: Member, entry: dict[str, Any], detail: str
) -> None:
    kda = await vehicle(api, owner, await company(api, owner, "North Star"), "KDA 482M")
    problem(await save(api, owner, kda, TODAY, **entry), 400, INVALID, detail)


@pytest.mark.parametrize(
    "amount", ['"1e999999"', '"-1e999999"', '"79228162514264337593543950336"', "NaN", "Infinity"]
)
async def test_an_amount_no_decimal_can_hold_is_refused_before_the_routine(
    api: AuthApi, owner: Member, amount: str
) -> None:
    kda = await vehicle(api, owner, await company(api, owner, "North Star"), "KDA 482M")
    response = await api.client.put(
        f"/setup/revenue/{kda}/{TODAY}",
        content=f'{{"amount":{amount}}}'.encode(),
        headers={**owner.headers, "content-type": "application/json"},
    )
    invalid(response, "amount")


async def test_an_amount_below_what_a_decimal_holds_reads_as_zero(
    api: AuthApi, owner: Member
) -> None:
    kda = await vehicle(api, owner, await company(api, owner, "North Star"), "KDA 482M")
    response = await save(api, owner, kda, TODAY, amount="1e-999999")
    problem(response, 400, INVALID, "Amount must be positive with at most two decimal places.")


async def test_the_phone_queue_gets_one_answer_per_replayed_entry(
    api: AuthApi, owner: Member
) -> None:
    """Each row is an entry the phone stored offline and replays: ``200`` drops it from the
    queue, ``409`` turns it into a conflict showing ``current``, ``400``/``403``/``404`` mark it
    failed (``apps/mobile/src/revenue/queue.ts``)."""
    north = await company(api, owner, "North Star")
    kda = await vehicle(api, owner, north, "KDA 482M")
    kdb = await vehicle(api, owner, north, "KDB 111A")
    clerk = await member(api, "Revenue clerk", "0722000111")
    seed(api, owner, kda, "2026-10-05", 500)
    seed(api, owner, kdb, "2026-10-05", 520)
    api.owner.execute(
        "UPDATE revenue.records SET version = 2, corrected_after_date = true WHERE vehicle_id = %s",
        (UUID(kdb),),
    )
    first = ok(await save(api, clerk, kda, TODAY, amount=700))
    ok(await save(api, owner, kda, TODAY, amount=750, version=1))

    sent = ok(await save(api, clerk, kdb, "2026-10-06", reason="NoCrew"))
    assert ok(await save(api, clerk, kdb, "2026-10-06", reason="No Crew")) == sent
    # Captured on the phone on 5 Oct, replayed after the day closed: still identical.
    closed = ok(await save(api, clerk, kda, "2026-10-05", amount=500))
    assert closed["version"] == 1
    # The office corrected KDB's 5 Oct while the phone was offline: not the clerk's to change.
    changing = 'Changing revenue already saved needs the permission "Change revenue already saved".'
    refused = problem(
        await save(api, clerk, kdb, "2026-10-05", amount=500), 403, FORBIDDEN, changing
    )
    assert "current" not in refused
    # Today's saved day is closed to the clerk too (v2.30): the phone marks the entry failed.
    refused = problem(
        await save(api, clerk, kda, TODAY, amount=800, version=first["version"]),
        403,
        FORBIDDEN,
        changing,
    )
    assert "current" not in refused
    # A fleet manager's queued change of a day that moved on: a conflict with the stored day.
    manager = await member(api, "Fleet manager", "0744000111")
    conflict = problem(
        await save(api, manager, kda, TODAY, amount=800, version=first["version"]),
        409,
        CHANGED,
        CHANGED_DETAIL,
    )
    assert list(conflict) == [
        "type",
        "title",
        "status",
        "detail",
        "requestId",
        "traceId",
        "current",
    ]
    assert list(conflict["current"]) == CELL_KEYS
    assert conflict["current"] == {
        "date": TODAY,
        "status": "amount",
        "expected": 1000,
        "amount": 750,
        "reason": None,
        "note": None,
        "canEdit": True,
        "editedAfterCapture": False,
        "version": 2,
    }
    problem(
        await save(api, clerk, kda, "2026-10-08", amount=800),
        400,
        INVALID,
        "Revenue cannot be recorded for a future date.",
    )
    problem(await save(api, clerk, UNKNOWN, TODAY, amount=800), 404, NOT_FOUND)
    problem(
        await save(api, clerk, kda, "2026-09-30", amount=800),
        400,
        INVALID,
        "Revenue can only be recorded while the vehicle is active.",
    )


async def test_a_day_another_save_holds_is_a_409_without_current(
    api: AuthApi, owner: Member
) -> None:
    """The phone reads a 409 without ``current`` as a conflict and re-reads the day itself."""
    kda = await vehicle(api, owner, await company(api, owner, "North Star"), "KDA 482M")
    first = ok(await save(api, owner, kda, TODAY, amount=700))
    with api.owner.transaction():
        api.owner.execute(
            "SELECT 1 FROM revenue.records WHERE id = %s FOR UPDATE", (UUID(first["id"]),)
        )
        held = await save(api, owner, kda, TODAY, amount=750, version=first["version"])
    body = problem(
        held,
        409,
        "This day was changed by another save.",
        "Reload the current record and try again.",
    )
    assert "current" not in body and "vehicleId" not in body
    assert ok(await save(api, owner, kda, TODAY, amount=750, version=1))["version"] == 2


async def test_the_route_takes_a_uuid_and_a_date(api: AuthApi, owner: Member) -> None:
    kda = await vehicle(api, owner, await company(api, owner, "North Star"), "KDA 482M")
    empty(await save(api, owner, "KDA-482M", TODAY, amount=500), 404)
    empty(await save(api, owner, "not-a-uuid", "anything", amount=500), 404)
    invalid(await save(api, owner, kda, "2026-13-40", amount=500), "path.date")
    empty(await api.client.put(f"/setup/revenue/{kda}/{TODAY}", json={"amount": 500}), 401)
    text = {**owner.headers, "Content-Type": "text/plain"}
    response = await api.client.put(
        f"/setup/revenue/{kda}/{TODAY}", content=b'{"amount": 500}', headers=text
    )
    empty(response, 415)
    empty(await api.client.post(f"/setup/revenue/{kda}/{TODAY}", headers=owner.headers), 405)


# --- the week grid --------------------------------------------------------------------------


async def test_the_week_in_wire_order_with_its_cells_and_figures(
    api: AuthApi, owner: Member
) -> None:
    north = await company(api, owner, "North Star")
    kda = await vehicle(api, owner, north, "KDA 482M")
    seed(api, owner, kda, "2026-10-05", 1000)
    ok(await save(api, owner, kda, TODAY, reason="Other", note="Engine knock"))
    response, count = await statements(api.client.get("/setup/revenue", headers=owner.headers))
    grid = ok(response)
    assert count == 2
    assert list(grid) == WEEK_KEYS
    assert (grid["weekStart"], grid["weekThrough"], grid["currentWeekStart"]) == (
        "2026-10-05",
        "2026-10-11",
        "2026-10-05",
    )
    assert grid["companies"] == [{"id": north, "name": "North Star"}]
    [row] = grid["vehicles"]
    assert list(row) == VEHICLE_KEYS
    assert [list(cell) for cell in row["days"]] == [CELL_KEYS] * 7
    assert row["days"][0] == {
        "date": "2026-10-05",
        "status": "amount",
        "expected": 1000,
        "amount": 1000,
        "reason": None,
        "note": None,
        "canEdit": True,
        "editedAfterCapture": False,
        "version": 1,
    }
    assert [(c["status"], c["reason"], c["note"]) for c in row["days"][1:4]] == [
        ("missing", None, None),
        ("reason", "Other", "Engine knock"),
        ("future", None, None),
    ]
    assert row["earliestMissing"] == "2026-10-01"
    # Monday and Tuesday are before the business date and Wednesday is recorded: 3 days of 1,000.
    assert (row["totalAmount"], row["totalExpected"], row["percent"]) == (1000, 3000, 33)
    assert (row["fleetNumber"], row["gap"], row["gapBand"], row["belowThresholdDays"]) == (
        "482M",
        -2000,
        "red",
        1,
    )
    assert (grid["lowDayThreshold"], grid["gapAmberPercent"], grid["gap"], grid["gapBand"]) == (
        100,
        10,
        -2000,
        "red",
    )
    assert (grid["belowThresholdDays"], grid["missingDays"]) == (1, 1)
    assert [list(total) for total in grid["dayTotals"]] == [["date", "amount", "expected"]] * 7
    assert grid["firstGap"] == {"vehicleId": kda, "date": "2026-10-01"}
    assert (grid["pageNumber"], grid["pageSize"], grid["totalVehicles"], grid["truncated"]) == (
        1,
        500,
        1,
        False,
    )


async def test_the_web_reads_the_first_500_then_the_pages_the_truncated_grid_lacks(
    api: AuthApi, owner: Member
) -> None:
    north = await company(api, owner, "North Star")
    api.owner.execute(
        "INSERT INTO setup.fleet_vehicles (organization_id, company_id, registration, joined_on) "
        "SELECT %s, %s, 'KZZ ' || lpad(n::text, 3, '0') || 'A', '2026-10-01' "
        "FROM generate_series(1, 640) AS n",
        (organization(api), UUID(north)),
    )
    first = ok(await api.client.get("/setup/revenue?weekStart=2026-10-05", headers=owner.headers))
    assert (len(first["vehicles"]), first["totalVehicles"], first["truncated"]) == (500, 640, True)
    listed = [v["registration"] for v in first["vehicles"]]
    for page in (6, 7):
        response, count = await statements(
            api.client.get(
                f"/setup/revenue?weekStart=2026-10-05&page={page}&pageSize=100",
                headers=owner.headers,
            )
        )
        rest = ok(response)
        assert count == 2
        assert (rest["pageNumber"], rest["pageSize"], rest["truncated"]) == (page, 100, False)
        assert (rest["totalAmount"], rest["dayTotals"], rest["firstGap"]) == (
            first["totalAmount"],
            first["dayTotals"],
            first["firstGap"],
        )
        listed += [v["registration"] for v in rest["vehicles"]]
    assert listed == [f"KZZ {n:03d}A" for n in range(1, 641)]


async def test_one_vehicle_in_a_past_week(api: AuthApi, owner: Member) -> None:
    north = await company(api, owner, "North Star")
    kda = await vehicle(api, owner, north, "KDA 482M")
    await vehicle(api, owner, north, "KDB 111A")
    seed(api, owner, kda, "2026-10-02", 900)
    grid = ok(
        await api.client.get(
            f"/setup/revenue?weekStart=2026-09-30&vehicleId={kda}&page=3", headers=owner.headers
        )
    )
    assert grid["weekStart"] == "2026-09-28"
    [row] = grid["vehicles"]
    assert row["id"] == kda
    assert [c["status"] for c in row["days"]] == ["none"] * 3 + ["missing", "amount"] + [
        "missing"
    ] * 2
    assert (grid["pageNumber"], grid["pageSize"]) == (1, 500)
    problem(
        await api.client.get(f"/setup/revenue?vehicleId={UNKNOWN}", headers=owner.headers),
        404,
        NOT_FOUND,
    )
    problem(
        await api.client.get("/setup/revenue?weekStart=2026-10-12", headers=owner.headers),
        400,
        INVALID,
        "Choose a week from the last ten years through the current week.",
    )
    problem(
        await api.client.get("/setup/revenue?page=0", headers=owner.headers),
        400,
        INVALID,
        "Page must be 1\u2013100000 and page size 1\u2013100.",
    )
    invalid(
        await api.client.get("/setup/revenue?page=2147483648", headers=owner.headers), "query.page"
    )


# --- the dashboard --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("role", "phone", "grant", "shown"),
    [
        ("Owner", None, None, {"revenue", "capture", "gaps", "edits"}),
        ("Owner", None, "-dash.net", {"capture", "gaps"}),
        ("Revenue clerk", "0722000111", None, {"capture", "gaps"}),
        ("Office admin", "0733000111", None, {"revenue", "capture", "gaps", "edits"}),
        ("Office admin", "0733000111", "-dash.gaps", {"revenue", "edits"}),
    ],
)
async def test_the_dashboard_shows_each_card_to_its_own_permission(
    api: AuthApi,
    owner: Member,
    role: str,
    phone: str | None,
    grant: str | None,
    shown: set[str],
) -> None:
    kda = await vehicle(api, owner, await company(api, owner, "North Star"), "KDA 482M")
    seed(api, owner, kda, "2026-10-05", 1000)
    ok(await save(api, owner, kda, TODAY, amount=1200))
    viewer = owner if phone is None else await member(api, role, phone)
    if grant is not None:
        set_override(api.owner, person(api, viewer), grant.lstrip("-"), not grant.startswith("-"))
    response, count = await statements(
        api.client.get("/setup/revenue/dashboard?period=week", headers=viewer.headers)
    )
    cards = ok(response)
    assert count == 2
    assert list(cards) == DASHBOARD_KEYS
    assert (cards["period"], cards["from"], cards["through"], cards["businessDate"]) == (
        "week",
        "2026-10-05",
        TODAY,
        TODAY,
    )
    figures = {
        "revenue": {"revenue": 2200, "expected": 3000, "percent": 73},
        "capture": {"capturedToday": 1, "vehiclesToday": 1},
        "gaps": {"missingDays": 1, "missingVehicles": 1},
        "edits": {"editedRecords": 0},
    }
    for card, values in figures.items():
        for key, value in values.items():
            assert cards[key] == (value if card in shown else None), key


async def test_the_dashboard_periods_and_refusals(api: AuthApi, owner: Member) -> None:
    north = await company(api, owner, "North Star")
    south = await company(api, owner, "South Line")
    kda = await vehicle(api, owner, north, "KDA 482M")
    seed(api, owner, kda, "2026-10-01", 600)
    for period, start, revenue in (
        ("today", TODAY, 0),
        ("week", "2026-10-05", 0),
        ("month", "2026-10-01", 600),
    ):
        cards = ok(
            await api.client.get(f"/setup/revenue/dashboard?period={period}", headers=owner.headers)
        )
        assert (cards["from"], cards["revenue"]) == (start, revenue)
    assert (
        ok(await api.client.get("/setup/revenue/dashboard", headers=owner.headers))["period"]
        == "week"
    )
    narrowed = ok(
        await api.client.get(
            f"/setup/revenue/dashboard?period=month&companyId={south}", headers=owner.headers
        )
    )
    assert (narrowed["revenue"], narrowed["missingDays"]) == (0, 0)
    problem(
        await api.client.get("/setup/revenue/dashboard?period=year", headers=owner.headers),
        400,
        INVALID,
        "Period must be today, week or month.",
    )
    clerk = await member(api, "Revenue clerk", "0722000111")
    set_override(api.owner, person(api, clerk), "dash.gaps", False)
    problem(
        await api.client.get("/setup/revenue/dashboard?period=year", headers=clerk.headers),
        403,
        FORBIDDEN,
    )
    empty(await api.client.get("/setup/revenue/dashboard"), 401)


# --- low days, the gap, the search, the capture time and the settings ----------------------


async def test_a_low_day_is_saved_with_its_reason(api: AuthApi, owner: Member) -> None:
    kda = await vehicle(api, owner, await company(api, owner, "North Star"), "KDA 482M")
    threshold(api, None)
    problem(
        await save(api, owner, kda, TODAY, amount=3999.99),
        400,
        INVALID,
        "Choose the reason. Revenue is below KES 4,000.",
    )
    saved = ok(await save(api, owner, kda, TODAY, amount=3999.99, reason="Garage"))
    grid = ok(await api.client.get("/setup/revenue", headers=owner.headers))
    cell = grid["vehicles"][0]["days"][2]
    assert (cell["status"], cell["amount"], cell["reason"], cell["version"]) == (
        "amount",
        3999.99,
        "Garage",
        saved["version"],
    )
    assert grid["lowDayThreshold"] == 4000
    # The note on Other is optional now.
    ok(await save(api, owner, kda, "2026-10-06", reason="Other"))


async def test_the_week_carries_the_gap_and_the_day_targets(api: AuthApi, owner: Member) -> None:
    north = await company(api, owner, "North Star")
    body = {
        "companyId": north,
        "registration": "KDA 482M",
        "fleetNumber": "14",
        "joinedOn": "2026-10-01",
        "dayTargets": [1000, 1000, 1500, 1000, 1000, 2000, 2500],
    }
    kda = str(ok(await api.client.post("/setup/vehicles", json=body, headers=owner.headers))["id"])
    seed(api, owner, kda, "2026-10-05", 1200)
    seed(api, owner, kda, "2026-10-06", 900)
    grid = ok(await api.client.get("/setup/revenue", headers=owner.headers))
    [row] = grid["vehicles"]
    assert [c["expected"] for c in row["days"]] == [1000, 1000, 1500, 1000, 1000, 2000, 2500]
    # Monday and Tuesday count; Wednesday (today) does not until it is recorded.
    assert (row["totalExpected"], row["gap"], row["gapBand"]) == (2000, 100, "green")
    assert [d["expected"] for d in grid["dayTotals"]] == [1000, 1000, 0, 0, 0, 0, 0]
    ok(await save(api, owner, kda, TODAY, amount=1300))
    row = ok(await api.client.get("/setup/revenue", headers=owner.headers))["vehicles"][0]
    assert (row["totalExpected"], row["gap"], row["gapBand"]) == (3500, -100, "amber")


async def test_the_week_search_matches_registration_or_fleet_number(
    api: AuthApi, owner: Member
) -> None:
    north = await company(api, owner, "North Star")
    kda = await vehicle(api, owner, north, "KDA 482M")
    await vehicle(api, owner, north, "KDB 111A")
    seed(api, owner, kda, "2026-10-05", 700)
    for q, shown in (("kdb", ["KDB 111A"]), ("482", ["KDA 482M"]), ("111a", ["KDB 111A"])):
        grid = ok(await api.client.get(f"/setup/revenue?q={q}", headers=owner.headers))
        assert [v["registration"] for v in grid["vehicles"]] == shown
        assert grid["totalVehicles"] == 1
    matched = ok(await api.client.get("/setup/revenue?q=KDB&pageSize=10", headers=owner.headers))
    assert (matched["totalAmount"], matched["totalVehicles"]) == (0, 1)
    problem(
        await api.client.get(f"/setup/revenue?q={'x' * 41}", headers=owner.headers),
        400,
        INVALID,
        "Search for 40 characters or fewer.",
    )
    unstorable = await api.client.get("/setup/revenue?q=KD%00", headers=owner.headers)
    assert unstorable.status_code == 400
    assert unstorable.json()["errors"] == {
        "query.q": ["Text cannot contain U+0000 or an unpaired surrogate."]
    }


async def test_a_capture_time_moves_the_back_limit_within_72_hours(
    api: AuthApi, owner: Member
) -> None:
    kda = await vehicle(api, owner, await company(api, owner, "North Star"), "KDA 482M")
    clerk = await member(api, "Revenue clerk", "0722000111")
    api.owner.execute(
        "UPDATE tenancy.memberships SET back_limit_mode = 'days', back_limit_count = 0 "
        "WHERE user_id = %s",
        (clerk.user_id,),
    )
    problem(
        await save(api, clerk, kda, "2026-10-06", amount=700),
        400,
        INVALID,
        "You can only add or change records dated 2026-10-07 or later.",
    )
    captured = "2026-10-06T18:30:00+03:00"
    ok(await save(api, clerk, kda, "2026-10-06", amount=700, capturedAt=captured))
    invalid(
        await save(api, clerk, kda, "2026-10-05", amount=700, capturedAt="2026-10-05T18:30:00"),
        "capturedAt",
    )


async def test_the_revenue_settings_are_read_and_saved_by_the_owner(
    api: AuthApi, owner: Member
) -> None:
    threshold(api, None)
    settings = ok(await api.client.get("/setup/organization/settings", headers=owner.headers))
    assert list(settings)[-1] == "revenue"
    assert list(settings["revenue"]) == ["organizationId", "lowDayThreshold", "gapAmberPercent"]
    assert (settings["revenue"]["lowDayThreshold"], settings["revenue"]["gapAmberPercent"]) == (
        4000,
        10,
    )
    url = "/setup/organization/settings/revenue"
    saved = await api.client.put(
        url,
        json={"value": {"lowDayThreshold": 3500.5, "gapAmberPercent": 15}},
        headers=owner.headers,
    )
    assert ok(saved) == {"section": "revenue"}
    settings = ok(await api.client.get("/setup/organization/settings", headers=owner.headers))
    assert (settings["revenue"]["lowDayThreshold"], settings["revenue"]["gapAmberPercent"]) == (
        3500.5,
        15,
    )
    row = api.owner.execute(
        "SELECT section, reason FROM tenancy.change_log ORDER BY version DESC LIMIT 1"
    ).fetchone()
    assert row == {
        "section": "organization",
        "reason": "Changed the low-day threshold to KES 3,500.50 and the amber band to 15 per cent",
    }
    for value in ({"lowDayThreshold": -1}, {"gapAmberPercent": 100.5}, {"lowDayThreshold": 1.005}):
        problem(
            await api.client.put(url, json={"value": value}, headers=owner.headers),
            400,
            INVALID,
            "The low-day threshold must be 0 or more and the amber band 0 to 100 per cent.",
        )
    clerk = await member(api, "Revenue clerk", "0722000111")
    problem(
        await api.client.put(url, json={"value": {"lowDayThreshold": 1}}, headers=clerk.headers),
        403,
        FORBIDDEN,
    )


@pytest.mark.parametrize("number", ["Infinity", "-Infinity", "NaN", "1e999"])
@pytest.mark.parametrize(
    ("section", "key"), [("revenue", "lowDayThreshold"), ("securityPolicy", "pinLength")]
)
async def test_a_settings_number_no_json_holds_is_refused_before_the_routine(
    api: AuthApi, owner: Member, number: str, section: str, key: str
) -> None:
    response = await api.client.put(
        f"/setup/organization/settings/{section}",
        content=f'{{"value":{{"{key}":{number}}}}}'.encode(),
        headers={**owner.headers, "content-type": "application/json"},
    )
    invalid(response, "value")
