"""``POST /setup/revenue/export/image`` (``docs/06-http-contract.md`` X04) against the real
database: the change-log row of the Revenue Summary image the web drew on the device, its
rights (``revenue.export`` and ``revenue.view``), the checks of its body, the company a scoped
viewer cannot see, 401, fields the contract does not bind, and the statement budget.

The business date is 7 Oct 2026, a Wednesday (the test clock in Nairobi). Antony Maina owns the
organization, Wanjiru Kamau (Fleet manager, granted revenue.export) sees North Star only, Grace
Njeri (Revenue clerk) holds no export right. The week's first day is the organization's setting,
read from the week grid rather than assumed."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any
from uuid import UUID, uuid4

import pytest

from xcode_api.http.messages import MESSAGES

from ..support.client import ApiFactory, AuthApi
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
from ..support.tenancy import Member as Person
from ..support.tenancy import add_company, set_override, set_scope

pytestmark = pytest.mark.asyncio(loop_scope="session")

PATH = "/setup/revenue/export/image"
TODAY = "2026-10-07"


@dataclass(frozen=True)
class World:
    api: AuthApi
    org: UUID
    owner: Member
    clerk: Member
    teller: Member
    north: UUID
    south: UUID


@pytest.fixture
async def api(make_api: ApiFactory) -> AuthApi:
    return await make_api()


@pytest.fixture
async def world(api: AuthApi) -> World:
    owner = await join(api, email="owner@example.com", phone="0711000411", role="Owner")
    row = api.owner.execute("SELECT id FROM tenancy.organizations").fetchone()
    assert row is not None
    org = UUID(str(row["id"]))
    clerk = await join(api, email="clerk@example.com", phone="0733000411", role="Fleet manager")
    teller = await join(api, email="teller@example.com", phone="0744000411", role="Revenue clerk")
    north = add_company(api.owner, org, "North Star")
    south = add_company(api.owner, org, "South Line")
    for member in (owner, teller):
        set_scope(api.owner, member.user_id, org, all_companies=True)
    set_scope(api.owner, clerk.user_id, org, companies=[north])
    set_override(api.owner, Person(clerk.user_id, org, "", "", "", "", ""), "revenue.export")
    return World(api, org, owner, clerk, teller, north, south)


def post(world: World, who: Member | None, body: dict[str, Any]) -> Any:
    headers = None if who is None else who.headers
    return world.api.client.post(PATH, json=body, headers=headers)


def logged(world: World) -> list[dict[str, Any]]:
    return world.api.owner.execute(
        "SELECT reason, after, actor_id FROM tenancy.change_log "
        "WHERE organization_id = %s AND section = 'reports' ORDER BY version",
        (world.org,),
    ).fetchall()


def sentence(code: str) -> str:
    text = MESSAGES[code].sentence({})
    assert text is not None
    return text


def words(day: str) -> str:
    value = date.fromisoformat(day)
    return f"{value.day} {value.strftime('%b')} {value.year}"


async def week_words(world: World) -> str:
    grid = world.api.client.get(f"/setup/revenue?weekStart={TODAY}", headers=world.owner.headers)
    week = ok(await grid)
    return f"{words(week['weekStart'])} to {words(week['weekThrough'])}"


async def test_the_image_is_logged_as_an_export_of_the_week_with_its_company_and_search(
    world: World,
) -> None:
    period = await week_words(world)
    response, count = await statements(post(world, world.owner, {"weekStart": TODAY}))
    assert response.status_code == 204, response.content
    assert response.content == b""
    assert response.headers.get("x-request-id")
    assert count <= 2

    response = await post(
        world, world.clerk, {"weekStart": TODAY, "companyId": str(world.north), "q": " KDA "}
    )
    assert response.status_code == 204, response.content

    rows = logged(world)
    assert [r["reason"] for r in rows] == [
        f"Exported Revenue for {period} to Summary image",
        f'Exported Revenue for {period}, searched for "KDA" to Summary image',
    ]
    assert [r["actor_id"] for r in rows] == [world.owner.user_id, world.clerk.user_id]
    assert '"format":"png"' in rows[1]["after"].replace(" ", "")
    assert str(world.north) in rows[1]["after"]


async def test_without_revenue_export_or_a_token_nothing_is_logged(world: World) -> None:
    problem(await post(world, world.teller, {"weekStart": TODAY}), 403, FORBIDDEN)
    response = await post(world, None, {"weekStart": TODAY})
    assert response.status_code == 401
    assert logged(world) == []


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({}, "weekStart"),
        ({"weekStart": "2026-13-40"}, "weekStart"),
        ({"weekStart": TODAY, "companyId": "north"}, "companyId"),
        ({"weekStart": TODAY, "q": 7}, "q"),
    ],
)
async def test_a_body_the_framework_cannot_read_is_refused(
    world: World, body: dict[str, Any], field: str
) -> None:
    response = await post(world, world.owner, body)
    refused = problem(response, 400, INVALID, response.json().get("detail"))
    assert refused["detail"]
    assert any(field in key for key in refused["errors"]), refused
    assert logged(world) == []


async def test_the_week_and_the_search_are_checked_by_the_routine(world: World) -> None:
    for week in ("2026-10-14", "2016-10-07"):
        problem(
            await post(world, world.owner, {"weekStart": week}),
            400,
            INVALID,
            sentence("revenue_week_range"),
        )
    problem(
        await post(world, world.owner, {"weekStart": TODAY, "q": "x" * 41}),
        400,
        INVALID,
        sentence("revenue_search_length"),
    )
    assert logged(world) == []


async def test_a_company_outside_the_callers_view_is_not_found(world: World) -> None:
    problem(
        await post(world, world.clerk, {"weekStart": TODAY, "companyId": str(world.south)}),
        404,
        NOT_FOUND,
    )
    problem(
        await post(world, world.owner, {"weekStart": TODAY, "companyId": str(uuid4())}),
        404,
        NOT_FOUND,
    )
    assert logged(world) == []


async def test_fields_the_contract_does_not_bind_change_nothing(world: World) -> None:
    period = await week_words(world)
    response = await post(
        world,
        world.clerk,
        {
            "weekStart": TODAY,
            "organizationId": str(uuid4()),
            "actorId": str(world.owner.user_id),
            "format": "xlsx",
            "title": "Payroll",
            "reason": "Nothing happened",
        },
    )
    assert response.status_code == 204, response.content
    [row] = logged(world)
    assert row["reason"] == f"Exported Revenue for {period} to Summary image"
    assert row["actor_id"] == world.clerk.user_id
