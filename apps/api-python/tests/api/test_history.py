"""The change-log route against the real database (``docs/06-http-contract.md`` section 2.5):
the page and entry properties in wire order, instants with six digits and ``+00:00``, both
paging forms, the skipped count, the refusals with their sentences, the permission, the
statement budget of 2."""

from __future__ import annotations

import re

import pytest

from ..support.client import ApiFactory, AuthApi
from ..support.setup_client import FORBIDDEN, INVALID, Member, empty, join, ok, problem, statements

pytestmark = pytest.mark.asyncio(loop_scope="session")

ENTRY_KEYS = [
    "version",
    "section",
    "entityId",
    "reason",
    "occurredAt",
    "actorId",
    "actorName",
    "before",
    "after",
]


@pytest.fixture
async def api(make_api: ApiFactory) -> AuthApi:
    return await make_api()


@pytest.fixture
async def owner(api: AuthApi) -> Member:
    member = await join(api, email="ann@example.com", phone="0711000111", role="Owner")
    for minutes in (20, 25, 30, 35, 40):
        response = await api.client.put(
            "/setup/organization/settings/securityPolicy",
            json={"value": {"lockoutMinutes": minutes}},
            headers=member.headers,
        )
        ok(response)
    return member


async def test_a_page_of_history_in_the_wire_shape(api: AuthApi, owner: Member) -> None:
    response, count = await statements(
        api.client.get("/setup/history?page=1&pageSize=2", headers=owner.headers)
    )
    page = ok(response)
    assert count == 2
    assert list(page) == ["items", "pageNumber", "pageSize", "total", "hasMore", "nextBefore"]
    # Five policy saves after the Owner's first sign-in, which the sign-in history section logs.
    assert (page["pageNumber"], page["pageSize"], page["total"], page["hasMore"]) == (1, 2, 6, True)
    assert [item["version"] for item in page["items"]] == [7, 6]
    assert page["nextBefore"] == 6
    entry = page["items"][0]
    assert list(entry) == ENTRY_KEYS
    assert entry["section"] == "securityPolicy"
    assert entry["reason"] == "Changed the pause in minutes to 40"
    assert entry["actorName"] == "Jane Doe"
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}\+00:00", entry["occurredAt"])
    assert '"lockoutMinutes":40' in entry["after"]


async def test_seeking_below_a_version_returns_what_the_next_page_does(
    api: AuthApi, owner: Member
) -> None:
    second = ok(await api.client.get("/setup/history?page=2&pageSize=2", headers=owner.headers))
    seek = ok(await api.client.get("/setup/history?pageSize=2&before=6", headers=owner.headers))
    assert [i["version"] for i in seek["items"]] == [i["version"] for i in second["items"]]
    assert seek["nextBefore"] == second["nextBefore"] == 4
    last = ok(
        await api.client.get(
            "/setup/history?pageSize=2&before=4&includeTotal=false", headers=owner.headers
        )
    )
    assert (last["total"], last["hasMore"], last["nextBefore"]) == (None, False, None)
    assert [i["version"] for i in last["items"]] == [3, 2]


async def test_filters_narrow_the_log(api: AuthApi, owner: Member) -> None:
    section = ok(await api.client.get("/setup/history?section=branding", headers=owner.headers))
    assert section["total"] == 0
    text = ok(await api.client.get("/setup/history?text=MINUTES%20TO%2030", headers=owner.headers))
    assert [i["reason"] for i in text["items"]] == ["Changed the pause in minutes to 30"]
    literal = ok(await api.client.get("/setup/history?text=%25", headers=owner.headers))
    assert literal["total"] == 0
    today = ok(
        await api.client.get("/setup/history?from=2000-01-01&to=2100-01-01", headers=owner.headers)
    )
    assert today["total"] == 6
    sign_in = ok(await api.client.get("/setup/history?section=signIn", headers=owner.headers))
    assert [(i["section"], i["reason"], i["entityId"]) for i in sign_in["items"]] == [
        ("signIn", "PIN set at first sign in; Device trusted", str(owner.user_id))
    ]
    assert sign_in["items"][0]["after"] == '{"Status":"Active","Devices":[null]}'


async def test_refusals_carry_their_sentences(api: AuthApi, owner: Member) -> None:
    problem(
        await api.client.get("/setup/history?from=2026-10-09&to=2026-10-08", headers=owner.headers),
        400,
        INVALID,
        "The first date cannot be after the last date.",
    )
    problem(
        await api.client.get(f"/setup/history?text={'x' * 201}", headers=owner.headers),
        400,
        INVALID,
        "Search for 200 characters or fewer.",
    )
    problem(
        await api.client.get("/setup/history?before=0", headers=owner.headers),
        400,
        INVALID,
        "Before must be a change log version.",
    )
    unparsable = await api.client.get("/setup/history?from=yesterday", headers=owner.headers)
    assert unparsable.status_code == 400


async def test_the_log_needs_audit_view(api: AuthApi, owner: Member) -> None:
    clerk = await join(api, email="clerk@example.com", phone="0722000111", role="Revenue clerk")
    problem(await api.client.get("/setup/history", headers=clerk.headers), 403, FORBIDDEN)
    empty(await api.client.get("/setup/history"), 401)
