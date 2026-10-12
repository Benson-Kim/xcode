"""The target set routes against the real database (``docs/06-http-contract.md`` S47 to S49):
a vehicle's sets newest first in wire order, a set saved from today or later (a body with
``startsOn`` and seven ``days``, Monday first), saving again on the same date, removing a set
that has not started, the refusals with their exact sentences, the change-log entries, the 401,
403 and 404 answers and the statement budget of 2. The business date is 2026-10-07."""

from __future__ import annotations

import json
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
from ..support.tenancy import Member as Person
from ..support.tenancy import set_override, set_scope

pytestmark = pytest.mark.asyncio(loop_scope="session")

SET_KEYS = ["id", "startsOn", "days", "weekTotal", "inForce", "canRemove"]
WEEK = [1000] * 5 + [1500, 500]
LATER = [1200] * 6 + [1300.5]
UNKNOWN = "00000000-0000-4000-8000-000000000000"
STARTED = "A target that has started cannot be changed or removed. Add a new one from today."


@pytest.fixture
async def api(make_api: ApiFactory) -> AuthApi:
    return await make_api()


@pytest.fixture
async def owner(api: AuthApi) -> Member:
    return await join(api, email="ann@example.com", phone="0711000111", role="Owner")


def organization(api: AuthApi) -> UUID:
    row = api.owner.execute("SELECT id FROM tenancy.organizations").fetchone()
    assert row is not None
    return UUID(str(row["id"]))


@pytest.fixture
async def kda(api: AuthApi, owner: Member) -> str:
    north = ok(
        await api.client.post(
            "/setup/companies", json={"name": "North Star"}, headers=owner.headers
        )
    )["id"]
    body = {
        "companyId": north,
        "registration": "KDA 482M",
        "fleetNumber": "N-1",
        "joinedOn": "2026-10-01",
        "dayTargets": WEEK,
    }
    return str(ok(await api.client.post("/setup/vehicles", json=body, headers=owner.headers))["id"])


async def holding(api: AuthApi, slot: int, *rights: str) -> Member:
    member = await join(
        api, email=f"r{slot}@example.com", phone=f"07440001{slot:02d}", role="Revenue clerk"
    )
    who = Person(member.user_id, organization(api), "", "", "", "", "")
    for right in rights:
        set_override(api.owner, who, right)
    set_scope(api.owner, member.user_id, organization(api), all_companies=True)
    return member


async def save(api: AuthApi, member: Member, vehicle: str, body: dict[str, Any]) -> Any:
    return await api.client.post(
        f"/setup/vehicles/{vehicle}/targets", json=body, headers=member.headers
    )


async def sets(api: AuthApi, member: Member, vehicle: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = ok(
        await api.client.get(f"/setup/vehicles/{vehicle}/targets", headers=member.headers)
    )
    return result


async def reasons(api: AuthApi, member: Member) -> list[str]:
    page = ok(
        await api.client.get("/setup/history?section=vehicles&pageSize=100", headers=member.headers)
    )
    return [entry["reason"] for entry in reversed(page["items"])]


async def test_the_sets_list_newest_first_in_wire_order(
    api: AuthApi, owner: Member, kda: str
) -> None:
    created = ok(await save(api, owner, kda, {"startsOn": "2026-10-20", "days": LATER}))
    assert list(created) == ["id"]
    response, count = await statements(
        api.client.get(f"/setup/vehicles/{kda}/targets", headers=owner.headers)
    )
    listed = ok(response)
    assert count == 2
    assert [list(s) for s in listed] == [SET_KEYS, SET_KEYS]
    assert listed[0] == {
        "id": created["id"],
        "startsOn": "2026-10-20",
        "days": LATER,
        "weekTotal": 8500.5,
        "inForce": False,
        "canRemove": True,
    }
    assert (listed[1]["startsOn"], listed[1]["weekTotal"], listed[1]["inForce"]) == (
        "2026-10-01",
        7000,
        True,
    )
    assert listed[1]["canRemove"] is False


async def test_a_set_saved_again_on_its_date_replaces_it_and_both_are_logged(
    api: AuthApi, owner: Member, kda: str
) -> None:
    first = ok(await save(api, owner, kda, {"startsOn": "2026-10-20", "days": LATER}))
    response, count = await statements(
        save(api, owner, kda, {"startsOn": "2026-10-20", "days": WEEK[::-1]})
    )
    assert ok(response) == first
    assert count == 2
    assert [s["days"] for s in await sets(api, owner, kda)] == [WEEK[::-1], WEEK]
    assert (await reasons(api, owner))[1:] == ["Target set, KDA 482M"] * 2


async def test_a_set_that_has_not_started_is_removed(api: AuthApi, owner: Member, kda: str) -> None:
    later = ok(await save(api, owner, kda, {"startsOn": "2026-10-20", "days": LATER}))["id"]
    response, count = await statements(
        api.client.post(f"/setup/vehicle-targets/{later}/remove", headers=owner.headers)
    )
    assert ok(response) == {"id": later}
    assert count == 2
    assert [s["startsOn"] for s in await sets(api, owner, kda)] == ["2026-10-01"]
    assert (await reasons(api, owner))[-1] == "Target removed before it started, KDA 482M"
    problem(
        await api.client.post(f"/setup/vehicle-targets/{later}/remove", headers=owner.headers),
        404,
        NOT_FOUND,
    )


async def test_a_set_from_today_can_be_replaced_today_but_not_removed(
    api: AuthApi, owner: Member, kda: str
) -> None:
    today = ok(await save(api, owner, kda, {"startsOn": "2026-10-07", "days": LATER}))["id"]
    ok(await save(api, owner, kda, {"startsOn": "2026-10-07", "days": WEEK[::-1]}))
    problem(
        await api.client.post(f"/setup/vehicle-targets/{today}/remove", headers=owner.headers),
        400,
        INVALID,
        STARTED,
    )
    (row,) = ok(await api.client.get("/setup/vehicles", headers=owner.headers))["items"]
    assert row["dayTargets"] == WEEK[::-1]


@pytest.mark.parametrize(
    ("body", "detail"),
    [
        ({"days": LATER}, "Enter the start date."),
        ({"startsOn": None, "days": LATER}, "Enter the start date."),
        ({"startsOn": "2026-10-20"}, "Enter the target for every day."),
        ({"startsOn": "2026-10-20", "days": LATER[:6]}, "Enter the target for every day."),
        ({"startsOn": "2026-10-20", "days": [*LATER[:6], None]}, "Enter the target for every day."),
        (
            {"startsOn": "2026-10-20", "days": [0, *LATER[1:]]},
            "Amount must be positive with at most two decimal places.",
        ),
        ({"startsOn": "2026-10-06", "days": LATER}, "A target cannot start before today."),
        (
            {"startsOn": "2026-10-07", "days": WEEK},
            "This is the target already set for 2026-10-07.",
        ),
    ],
)
async def test_a_bad_set_is_refused_with_its_sentence(
    api: AuthApi, owner: Member, kda: str, body: dict[str, Any], detail: str
) -> None:
    problem(await save(api, owner, kda, body), 400, INVALID, detail)
    assert len(await sets(api, owner, kda)) == 1


async def test_a_start_date_that_does_not_parse_is_a_400(
    api: AuthApi, owner: Member, kda: str
) -> None:
    for starts_on in ("20 October", "2026-02-30"):
        response = await save(api, owner, kda, {"startsOn": starts_on, "days": LATER})
        assert response.status_code == 400


async def test_a_retired_vehicle_takes_no_new_set(api: AuthApi, owner: Member, kda: str) -> None:
    ok(
        await api.client.post(
            f"/setup/vehicles/{kda}/retire", json={"leftOn": "2026-10-07"}, headers=owner.headers
        )
    )
    problem(
        await save(api, owner, kda, {"startsOn": "2026-10-20", "days": LATER}),
        400,
        INVALID,
        "Retired vehicles must be restored before they can be edited.",
    )


async def test_unknown_or_malformed_ids_are_not_found(
    api: AuthApi, owner: Member, kda: str
) -> None:
    problem(
        await api.client.get(f"/setup/vehicles/{UNKNOWN}/targets", headers=owner.headers),
        404,
        NOT_FOUND,
    )
    problem(
        await save(api, owner, UNKNOWN, {"startsOn": "2026-10-20", "days": LATER}), 404, NOT_FOUND
    )
    problem(
        await api.client.post(f"/setup/vehicle-targets/{UNKNOWN}/remove", headers=owner.headers),
        404,
        NOT_FOUND,
    )
    empty(await api.client.get("/setup/vehicles/kda/targets", headers=owner.headers), 404)
    empty(await api.client.post("/setup/vehicle-targets/kda/remove", headers=owner.headers), 404)
    assert kda


async def test_reading_needs_vehicles_view_and_writing_vehicles_target(
    api: AuthApi, owner: Member, kda: str
) -> None:
    later = ok(await save(api, owner, kda, {"startsOn": "2026-10-20", "days": LATER}))["id"]
    clerk = await join(api, email="clerk@example.com", phone="0722000111", role="Revenue clerk")
    problem(
        await api.client.get(f"/setup/vehicles/{kda}/targets", headers=clerk.headers),
        403,
        FORBIDDEN,
    )
    editor = await holding(api, 3, "vehicles.view", "vehicles.add", "vehicles.edit")
    viewed = await sets(api, editor, kda)
    assert [s["canRemove"] for s in viewed] == [False, False]
    for member in (clerk, editor):
        problem(
            await save(api, member, kda, {"startsOn": "2026-10-21", "days": LATER}),
            403,
            FORBIDDEN,
        )
        problem(
            await api.client.post(f"/setup/vehicle-targets/{later}/remove", headers=member.headers),
            403,
            FORBIDDEN,
        )
    setter = await holding(api, 4, "vehicles.target")
    assert [s["canRemove"] for s in await sets(api, setter, kda)] == [True, False]
    ok(await save(api, setter, kda, {"startsOn": "2026-10-21", "days": WEEK[::-1]}))
    ok(await api.client.post(f"/setup/vehicle-targets/{later}/remove", headers=setter.headers))


async def test_the_routes_need_a_token_and_a_json_body(
    api: AuthApi, owner: Member, kda: str
) -> None:
    empty(await api.client.get(f"/setup/vehicles/{kda}/targets"), 401)
    empty(
        await api.client.post(
            f"/setup/vehicles/{kda}/targets", json={"startsOn": "2026-10-20", "days": LATER}
        ),
        401,
    )
    empty(await api.client.post(f"/setup/vehicle-targets/{UNKNOWN}/remove"), 401)
    payload = json.dumps({"startsOn": "2026-10-20", "days": LATER}).encode()
    text = {**owner.headers, "Content-Type": "text/plain"}
    empty(
        await api.client.post(f"/setup/vehicles/{kda}/targets", content=payload, headers=text), 415
    )
