"""The preferences routes against the real database (``docs/06-http-contract.md`` section
2.9): the read with the organization's allow flags and defaults, saves that the organization
allows, the refusals with their sentences, values the organization later withdraws served as
``null``, and the statement budget of 2."""

from __future__ import annotations

from typing import Any

import pytest

from ..support.client import ApiFactory, AuthApi
from ..support.setup_client import INVALID, Member, empty, join, ok, problem, statements

pytestmark = pytest.mark.asyncio(loop_scope="session")

PREFERENCE_KEYS = [
    "organizationId",
    "userId",
    "locale",
    "timeZone",
    "hour12",
    "themeMode",
    "reducedMotion",
    "fontScale",
]


@pytest.fixture
async def api(make_api: ApiFactory) -> AuthApi:
    return await make_api()


@pytest.fixture
async def owner(api: AuthApi) -> Member:
    return await join(api, email="ann@example.com", phone="0711000111", role="Owner")


@pytest.fixture
async def clerk(api: AuthApi, owner: Member) -> Member:
    return await join(api, email="clerk@example.com", phone="0722000111", role="Revenue clerk")


async def put(api: AuthApi, member: Member, body: dict[str, Any]) -> Any:
    return await api.client.put("/setup/preferences", json=body, headers=member.headers)


async def test_the_read_says_which_overrides_the_organization_allows(
    api: AuthApi, clerk: Member
) -> None:
    response, count = await statements(api.client.get("/setup/preferences", headers=clerk.headers))
    body = ok(response)
    assert count == 2
    assert list(body) == [
        *PREFERENCE_KEYS,
        "allowLocaleOverride",
        "allowTimeZoneOverride",
        "allowHour12Override",
        "allowThemeOverride",
        "organization",
    ]
    assert body["userId"] == str(clerk.user_id)
    assert (body["locale"], body["themeMode"], body["reducedMotion"], body["fontScale"]) == (
        None,
        None,
        False,
        1,
    )
    assert (body["allowLocaleOverride"], body["allowTimeZoneOverride"]) == (True, False)
    assert body["organization"] == {
        "locale": "en-GB",
        "timeZone": "Africa/Nairobi",
        "hour12": False,
    }


async def test_an_allowed_save_returns_the_saved_row(api: AuthApi, clerk: Member) -> None:
    body = {
        "locale": "fr-FR",
        "hour12": True,
        "themeMode": "dark",
        "reducedMotion": True,
        "fontScale": 1.25,
    }
    response, count = await statements(put(api, clerk, body))
    saved = ok(response)
    assert count == 2
    assert list(saved) == PREFERENCE_KEYS
    assert (saved["locale"], saved["hour12"], saved["themeMode"], saved["fontScale"]) == (
        "fr-FR",
        True,
        "dark",
        1.25,
    )
    appearance = ok(await api.client.get("/setup/appearance", headers=clerk.headers))
    assert (appearance["formats"]["locale"], appearance["themeMode"]) == ("fr-FR", "dark")


@pytest.mark.parametrize(
    ("body", "detail"),
    [
        (
            {"timeZone": "UTC", "fontScale": 1},
            "Your organization does not allow a personal time zone.",
        ),
        ({"themeMode": "blue", "fontScale": 1}, "Invalid accessibility preferences"),
        ({"locale": "fr-FR"}, "Invalid accessibility preferences"),
        ({"locale": "french!", "fontScale": 1}, "Use BCP 47 locale."),
    ],
)
async def test_a_refused_save_answers_its_sentence(
    api: AuthApi, clerk: Member, body: dict[str, Any], detail: str
) -> None:
    problem(await put(api, clerk, body), 400, INVALID, detail)


async def test_withdrawn_overrides_are_refused_and_read_as_null(
    api: AuthApi, owner: Member, clerk: Member
) -> None:
    ok(await put(api, clerk, {"locale": "fr-FR", "themeMode": "dark", "fontScale": 1}))
    response = await api.client.put(
        "/setup/organization/settings/localization",
        json={"value": {"allowLocaleOverride": False, "allowThemeOverride": False}},
        headers=owner.headers,
    )
    ok(response)
    read = ok(await api.client.get("/setup/preferences", headers=clerk.headers))
    assert (read["locale"], read["themeMode"]) == (None, None)
    problem(
        await put(api, clerk, {"locale": "fr-FR", "fontScale": 1}),
        400,
        INVALID,
        "Your organization does not allow a personal locale.",
    )
    problem(
        await put(api, clerk, {"themeMode": "dark", "fontScale": 1}),
        400,
        INVALID,
        "Your organization does not allow a personal theme.",
    )
    assert ok(await put(api, clerk, {"fontScale": 1})) is not None


async def test_preferences_need_a_session(api: AuthApi) -> None:
    empty(await api.client.get("/setup/preferences"), 401)
    empty(await api.client.put("/setup/preferences", json={"fontScale": 1}), 401)
