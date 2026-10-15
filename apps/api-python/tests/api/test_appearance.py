"""``GET /setup/appearance`` against the real database (``docs/06-http-contract.md`` section
2.9): every property the clients read, in wire order, for any member; branding, formats, the
wrong-PIN pause and the idle unlock the Owner saved; the version after a save; the statement
budget of 2."""

from __future__ import annotations

import pytest

from ..support.client import ApiFactory, AuthApi
from ..support.setup_client import Member, empty, join, ok, statements

pytestmark = pytest.mark.asyncio(loop_scope="session")


@pytest.fixture
async def api(make_api: ApiFactory) -> AuthApi:
    return await make_api()


@pytest.fixture
async def owner(api: AuthApi) -> Member:
    return await join(api, email="ann@example.com", phone="0711000111", role="Owner")


@pytest.fixture
async def clerk(api: AuthApi, owner: Member) -> Member:
    return await join(api, email="clerk@example.com", phone="0722000111", role="Revenue clerk")


async def test_every_member_reads_the_appearance_in_wire_order(api: AuthApi, clerk: Member) -> None:
    response, count = await statements(api.client.get("/setup/appearance", headers=clerk.headers))
    body = ok(response)
    assert count == 2
    assert list(body) == [
        "organizationName",
        "settingsVersion",
        "businessDate",
        "branding",
        "formats",
        "themeMode",
        "reducedMotion",
        "fontScale",
        "lockoutThreshold",
        "lockoutMinutes",
        "idleUnlockSeconds",
    ]
    assert list(body["branding"]) == [
        "displayName",
        "logoAlt",
        "primary",
        "secondary",
        "accent",
        "logo",
    ]
    assert list(body["formats"]) == [
        "locale",
        "timeZone",
        "datePattern",
        "hour12",
        "firstDayOfWeek",
        "weekNumbering",
        "currency",
        "useGrouping",
        "numberDecimals",
        "direction",
        "useGroupping",
    ]
    assert body["branding"]["logo"] is None
    assert (body["formats"]["currency"], body["formats"]["direction"]) == ("KES", "ltr")
    assert (body["themeMode"], body["reducedMotion"], body["fontScale"]) == ("system", False, 1)
    assert (body["lockoutThreshold"], body["lockoutMinutes"]) == (5, 15)


async def test_appearance_serves_the_idle_unlock_seconds(api: AuthApi, clerk: Member) -> None:
    body = ok(await api.client.get("/setup/appearance", headers=clerk.headers))
    assert (body["idleUnlockSeconds"], body["lockoutThreshold"]) == (900, 5)


async def test_members_see_what_the_owner_saved(api: AuthApi, owner: Member, clerk: Member) -> None:
    before = ok(await api.client.get("/setup/appearance", headers=clerk.headers))["settingsVersion"]
    for section, value in (
        ("branding", {"displayName": "North Star", "primary": "#1647A6"}),
        ("securityPolicy", {"lockoutThreshold": 3, "lockoutMinutes": 60, "idleUnlockSeconds": 600}),
    ):
        response = await api.client.put(
            f"/setup/organization/settings/{section}", json={"value": value}, headers=owner.headers
        )
        ok(response)
    body = ok(await api.client.get("/setup/appearance", headers=clerk.headers))
    assert body["settingsVersion"] == before + 2
    assert (body["branding"]["displayName"], body["branding"]["primary"]) == (
        "North Star",
        "#1647A6",
    )
    # The wrong-PIN lock is five whatever the stored threshold (v2.33); the minutes still set the
    # released phone's paused timer.
    assert (body["lockoutThreshold"], body["lockoutMinutes"], body["idleUnlockSeconds"]) == (
        5,
        60,
        600,
    )


async def test_appearance_needs_a_session(api: AuthApi) -> None:
    response = await api.client.get("/setup/appearance")
    empty(response, 401)
    assert response.headers["www-authenticate"] == "Bearer"
