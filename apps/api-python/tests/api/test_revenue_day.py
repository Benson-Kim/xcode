"""Day capture over HTTP (``docs/06-http-contract.md`` 2.13.3, D01 and D02), the four
``RevenueDayTests`` scenarios with the Python rules: the day lists the active vehicles with last
week; a day saves every row and a replay changes nothing; one refused row saves nothing and its
400 names the vehicle; each row checks rights and scope. Also the 409 with ``vehicleId`` and
``current``, the DTO key orders, the route constraints, 401 and the statement budget of 2. The
mobile single capture keeps its body: ``tests/api/test_revenue.py`` is the evidence.

The business date is 7 Oct 2026 (the test clock in Nairobi); the low-day threshold is 100."""

from __future__ import annotations

from datetime import date
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

TODAY = "2026-10-07"
DAY_KEYS = ["date", "businessDate", "vehicles", "truncated"]
VEHICLE_KEYS = ["id", "companyId", "registration", "day", "lastWeek", "fleetNumber"]
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
UNKNOWN = "00000000-0000-4000-8000-000000000000"


@pytest.fixture
async def api(make_api: ApiFactory) -> AuthApi:
    return await make_api()


@pytest.fixture
async def owner(api: AuthApi) -> Member:
    joined = await join(api, email="ann@example.com", phone="0711000111", role="Owner")
    api.owner.execute(
        "INSERT INTO tenancy.organization_revenue_settings (organization_id, low_day_threshold, "
        "gap_amber_percent) SELECT id, 100, 10 FROM tenancy.organizations"
    )
    return joined


def _org(api: AuthApi) -> UUID:
    row = api.owner.execute("SELECT id FROM tenancy.organizations").fetchone()
    assert row is not None
    return UUID(str(row["id"]))


async def _post_id(api: AuthApi, owner: Member, path: str, body: dict[str, Any]) -> str:
    return str(ok(await api.client.post(path, json=body, headers=owner.headers))["id"])


async def _fleet(api: AuthApi, owner: Member) -> tuple[str, str, str, str]:
    north = await _post_id(api, owner, "/setup/companies", {"name": "North Star"})
    south = await _post_id(api, owner, "/setup/companies", {"name": "South Line"})

    async def vehicle(company: str, registration: str) -> str:
        body = {
            "companyId": company,
            "registration": registration,
            "fleetNumber": registration[-4:],
            "joinedOn": "2026-09-01",
            "dayTargets": [1000] * 7,
        }
        return await _post_id(api, owner, "/setup/vehicles", body)

    return (
        north,
        await vehicle(north, "KDA 482M"),
        await vehicle(north, "KDB 111A"),
        await vehicle(south, "KDC 200B"),
    )


def _row(vehicle: str, amount: Any = None, **more: Any) -> dict[str, Any]:
    return {
        "vehicleId": vehicle,
        "amount": amount,
        "reason": None,
        "note": None,
        "version": None,
        **more,
    }


def _save(api: AuthApi, who: Member, day: str, *rows: dict[str, Any]) -> Any:
    return api.client.put(
        f"/setup/revenue/day/{day}", json={"rows": list(rows)}, headers=who.headers
    )


def _records(api: AuthApi, day: str) -> dict[str, Any]:
    rows = api.owner.execute(
        "SELECT vehicle_id, amount FROM revenue.records WHERE business_date = %s",
        (date.fromisoformat(day),),
    ).fetchall()
    return {str(r["vehicle_id"]): r["amount"] for r in rows}


# --- RevenueDayTests --------------------------------------------------------------------------


async def test_the_day_lists_the_active_vehicles_with_last_week(
    api: AuthApi, owner: Member
) -> None:
    north, kda, _, kdc = await _fleet(api, owner)
    add_record(api.owner, _org(api), UUID(kda), date(2026, 9, 30), 900, recorder=owner.user_id)
    add_record(api.owner, _org(api), UUID(kda), date(2026, 10, 7), 1200, recorder=owner.user_id)
    response, count = await statements(api.client.get("/setup/revenue/day", headers=owner.headers))
    day = ok(response)
    assert count == 2
    assert list(day) == DAY_KEYS
    assert (day["date"], day["businessDate"], day["truncated"]) == (TODAY, TODAY, False)
    assert [v["registration"] for v in day["vehicles"]] == ["KDA 482M", "KDB 111A", "KDC 200B"]
    first = day["vehicles"][0]
    assert list(first) == VEHICLE_KEYS
    assert list(first["day"]) == CELL_KEYS
    assert (first["id"], first["companyId"], first["fleetNumber"]) == (kda, north, "482M")
    assert (first["day"]["status"], first["day"]["amount"], first["day"]["version"]) == (
        "amount",
        1200,
        1,
    )
    assert first["lastWeek"] == {"amount": 900, "reason": None}
    assert day["vehicles"][1]["lastWeek"] is None
    north_only = ok(
        await api.client.get(
            f"/setup/revenue/day?date=2026-10-06&companyId={north}", headers=owner.headers
        )
    )
    assert [v["registration"] for v in north_only["vehicles"]] == ["KDA 482M", "KDB 111A"]
    problem(
        await api.client.get("/setup/revenue/day?date=2026-10-08", headers=owner.headers),
        400,
        INVALID,
        "Choose a day from the last ten years up to today.",
    )
    assert kdc
    assert (await api.client.get("/setup/revenue/day")).status_code == 401


async def test_a_day_saves_every_row_and_a_replay_changes_nothing(
    api: AuthApi, owner: Member
) -> None:
    _, kda, kdb, _ = await _fleet(api, owner)
    response, count = await statements(_save(api, owner, TODAY, _row(kdb, 800), _row(kda, 700)))
    saved = ok(response)
    assert count == 2
    assert list(saved) == ["rows"]
    assert [(r["vehicleId"], r["version"]) for r in saved["rows"]] == [(kdb, 1), (kda, 1)]
    assert [list(r) for r in saved["rows"]] == [["vehicleId", "id", "version"]] * 2
    again = ok(await _save(api, owner, TODAY, _row(kdb, "800.00"), _row(kda, 700)))
    assert again == saved
    history = ok(
        await api.client.get("/setup/history?section=revenue&pageSize=10", headers=owner.headers)
    )
    assert len(history["items"]) == 2


async def test_one_refused_row_saves_nothing_and_its_400_names_the_vehicle(
    api: AuthApi, owner: Member
) -> None:
    _, kda, kdb, _ = await _fleet(api, owner)
    problem(
        await _save(api, owner, TODAY, _row(kda, 700), _row(kdb, 50)),
        400,
        INVALID,
        "KDB 111A: Choose the reason. Revenue is below KES 100.",
    )
    problem(
        await _save(api, owner, "2026-10-08", _row(kda, 700)),
        400,
        INVALID,
        "KDA 482M: Revenue cannot be recorded for a future date.",
    )
    assert _records(api, TODAY) == {}
    for rows, detail in (
        ([], "Enter the revenue or a no-earnings reason for at least one vehicle."),
        ([_row(kda, 700), _row(kda.upper(), 800)], "Each vehicle can be in the day only once."),
    ):
        problem(await _save(api, owner, TODAY, *rows), 400, INVALID, detail)


async def test_each_row_checks_rights_and_scope(api: AuthApi, owner: Member) -> None:
    north, kda, _, kdc = await _fleet(api, owner)
    clerk = await join(api, email="cleo@example.com", phone="0722000111", role="Revenue clerk")
    org = _org(api)
    set_scope(api.owner, clerk.user_id, org, companies=[UUID(north)])
    problem(await _save(api, clerk, TODAY, _row(kda, 700), _row(kdc, 700)), 404, NOT_FOUND)
    problem(await _save(api, clerk, TODAY, _row(UNKNOWN, 700)), 404, NOT_FOUND)
    ok(await _save(api, owner, "2026-10-06", _row(kda, 700)))
    set_override(
        api.owner, Person(clerk.user_id, org, "", "", "", "", ""), "revenue.correct", granted=False
    )
    problem(
        await _save(api, clerk, "2026-10-06", _row(kda, 900, version=1)),
        403,
        FORBIDDEN,
        'Changing revenue already saved needs the permission "Change revenue already saved".',
    )
    assert _records(api, "2026-10-06") == {kda: 700}


async def test_a_stale_row_is_a_409_naming_the_vehicle_with_its_current_record(
    api: AuthApi, owner: Member
) -> None:
    _, kda, kdb, _ = await _fleet(api, owner)
    ok(await _save(api, owner, TODAY, _row(kda, 700)))
    ok(await _save(api, owner, TODAY, _row(kda, 750, version=1)))
    body = problem(
        await _save(api, owner, TODAY, _row(kdb, 300), _row(kda, 800, version=1)),
        409,
        "This day already has a different record.",
        "KDA 482M was changed after you opened the day. Check its current record and save again.",
    )
    assert body["vehicleId"] == kda
    assert (body["current"]["amount"], body["current"]["version"]) == (750, 2)
    assert list(body["current"]) == CELL_KEYS
    assert _records(api, TODAY) == {kda: 750}


async def test_a_date_that_is_not_a_date_is_refused_as_the_single_capture_does(
    api: AuthApi, owner: Member
) -> None:
    response = await api.client.put(
        "/setup/revenue/day/2026-13-40", json={"rows": []}, headers=owner.headers
    )
    body = problem(response, 400, INVALID, response.json().get("detail"))
    assert list(body["errors"]) == ["path.date"]
    empty(await api.client.put(f"/setup/revenue/day/{TODAY}", json={"rows": []}), 401)


async def test_unknown_properties_never_reach_a_saved_day(api: AuthApi, owner: Member) -> None:
    """A row naming stored columns is read for its own fields only."""
    _, kda, _, _ = await _fleet(api, owner)
    stored = {
        "id": str(uuid4()),
        "capturedBy": str(uuid4()),
        "editedAfterCapture": True,
        "status": "reason",
        "organizationId": str(uuid4()),
    }
    saved = ok(await _save(api, owner, TODAY, {**_row(kda, 700), **stored}))
    record = api.owner.execute(
        "SELECT id, captured_by, corrected_after_date, version FROM revenue.records "
        "WHERE vehicle_id = %s",
        (UUID(kda),),
    ).fetchone()
    assert record is not None
    assert (str(record["id"]), record["captured_by"], record["corrected_after_date"]) == (
        saved["rows"][0]["id"],
        owner.user_id,
        False,
    )
    assert record["version"] == 1


async def test_another_organizations_vehicle_is_not_found_and_its_day_stays_empty(
    api: AuthApi, owner: Member
) -> None:
    _, kda, _, _ = await _fleet(api, owner)
    other = seed_organization(api.owner)
    theirs = "SELECT count(*) AS n FROM revenue.records WHERE organization_id = %s"
    before = api.owner.execute(theirs, (other.org,)).fetchone()
    problem(
        await _save(api, owner, TODAY, _row(kda, 700), _row(str(other.vehicle), 700)),
        404,
        NOT_FOUND,
    )
    assert api.owner.execute(theirs, (other.org,)).fetchone() == before
    assert kda not in _records(api, TODAY)
    day = ok(await api.client.get("/setup/revenue/day", headers=owner.headers))
    assert str(other.vehicle) not in [v["id"] for v in day["vehicles"]]
