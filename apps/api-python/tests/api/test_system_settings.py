"""The system settings routes against the real database (``docs/06-http-contract.md``): the
on/off settings read in wire order, a switch for the whole organization served and logged once,
the unknown-key and missing-state refusals, and the ``settings.edit`` gate on both the read and
the switch."""

from __future__ import annotations

import pytest

from ..support.client import ApiFactory, AuthApi
from ..support.setup_client import (
    FORBIDDEN,
    INVALID,
    NOT_FOUND,
    Member,
    join,
    ok,
    problem,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")

ON = {"settings": [{"key": "targets", "label": "Targets", "on": True}]}
OFF = {"settings": [{"key": "targets", "label": "Targets", "on": False}]}


@pytest.fixture
async def api(make_api: ApiFactory) -> AuthApi:
    return await make_api()


@pytest.fixture
async def owner(api: AuthApi) -> Member:
    return await join(api, email="ann@example.com", phone="0711000111", role="Owner")


async def test_targets_is_on_and_served_in_wire_order(api: AuthApi, owner: Member) -> None:
    settings = ok(await api.client.get("/setup/settings", headers=owner.headers))
    assert settings == ON
    assert list(settings["settings"][0]) == ["key", "label", "on"]


async def test_a_switch_is_saved_served_and_logged(api: AuthApi, owner: Member) -> None:
    saved = ok(
        await api.client.put("/setup/settings/targets", json={"on": False}, headers=owner.headers)
    )
    assert saved == OFF
    assert ok(await api.client.get("/setup/settings", headers=owner.headers)) == OFF
    row = api.owner.execute(
        "SELECT section, reason FROM tenancy.change_log ORDER BY version DESC LIMIT 1"
    ).fetchone()
    assert row == {"section": "organization", "reason": "Setting, Targets, On to Off"}
    back = ok(
        await api.client.put("/setup/settings/targets", json={"on": True}, headers=owner.headers)
    )
    assert back == ON


async def test_switching_to_the_state_held_logs_nothing(api: AuthApi, owner: Member) -> None:
    before = api.owner.execute("SELECT count(*) AS n FROM tenancy.change_log").fetchone()["n"]
    saved = ok(
        await api.client.put("/setup/settings/targets", json={"on": True}, headers=owner.headers)
    )
    assert saved == ON
    after = api.owner.execute("SELECT count(*) AS n FROM tenancy.change_log").fetchone()["n"]
    assert after == before


async def test_an_unknown_key_is_not_found_and_a_missing_state_is_refused(
    api: AuthApi, owner: Member
) -> None:
    problem(
        await api.client.put("/setup/settings/budget", json={"on": True}, headers=owner.headers),
        404,
        NOT_FOUND,
    )
    problem(
        await api.client.put("/setup/settings/targets", json={"on": None}, headers=owner.headers),
        400,
        INVALID,
        "Choose whether the setting is on or off.",
    )


async def test_only_a_holder_of_settings_edit_may_read_and_switch(
    api: AuthApi, owner: Member
) -> None:
    clerk = await join(api, email="cleo@example.com", phone="0722000111", role="Revenue clerk")
    problem(await api.client.get("/setup/settings", headers=clerk.headers), 403, FORBIDDEN)
    problem(
        await api.client.put("/setup/settings/targets", json={"on": False}, headers=clerk.headers),
        403,
        FORBIDDEN,
    )
