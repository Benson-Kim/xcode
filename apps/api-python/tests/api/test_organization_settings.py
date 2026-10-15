"""The organization settings and logo routes against the real database
(``docs/06-http-contract.md`` section 2.9): the settings read in wire order with the legacy
name only in the effective formats, section saves with merge, legacy key, reasons, the plain
``{detail}`` answers of the organization section, problems everywhere else, the version moving
once per logged save, logo checks, 415, permissions and the statement budget of 2."""

from __future__ import annotations

import json
from typing import Any

import psycopg
import pytest

from ..support.client import ApiFactory, AuthApi
from ..support.setup_client import (
    FORBIDDEN,
    INVALID,
    JSON_UTF8,
    NOT_FOUND,
    Member,
    empty,
    join,
    ok,
    problem,
    statements,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")

PNG = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)
LOCALIZATION_KEYS = [
    "organizationId",
    "locale",
    "timeZone",
    "datePattern",
    "hour12",
    "firstDayOfWeek",
    "weekNumbering",
    "currency",
    "useGrouping",
    "numberDecimals",
    "allowLocaleOverride",
    "allowTimeZoneOverride",
    "allowHour12Override",
    "allowThemeOverride",
]


@pytest.fixture
async def api(make_api: ApiFactory) -> AuthApi:
    return await make_api()


@pytest.fixture
async def owner(api: AuthApi) -> Member:
    return await join(api, email="ann@example.com", phone="0711000111", role="Owner")


async def save(
    api: AuthApi, member: Member, section: str, value: Any, reason: str | None = None
) -> Any:
    body: dict[str, Any] = {"value": value}
    if reason is not None:
        body["reason"] = reason
    return await api.client.put(
        f"/setup/organization/settings/{section}", json=body, headers=member.headers
    )


async def settings(api: AuthApi, member: Member) -> dict[str, Any]:
    body: dict[str, Any] = ok(
        await api.client.get("/setup/organization/settings", headers=member.headers)
    )
    return body


async def history_reasons(api: AuthApi, member: Member, section: str) -> list[str]:
    page = ok(await api.client.get(f"/setup/history?section={section}", headers=member.headers))
    return [item["reason"] for item in reversed(page["items"])]


async def test_the_settings_read_keeps_the_entity_shapes(api: AuthApi, owner: Member) -> None:
    response, count = await statements(
        api.client.get("/setup/organization/settings", headers=owner.headers)
    )
    body = ok(response)
    assert count == 2
    assert list(body) == [
        "organization",
        "localization",
        "branding",
        "securityPolicy",
        "effectiveBusinessDate",
        "calendarDate",
        "effective",
        "revenue",
    ]
    assert list(body["organization"]) == ["id", "slug", "name", "businessDate", "settingsVersion"]
    assert list(body["revenue"]) == ["organizationId", "lowDayThreshold", "gapAmberPercent"]
    assert list(body["localization"]) == LOCALIZATION_KEYS
    assert "useGroupping" not in body["localization"]
    assert list(body["branding"]) == [
        "organizationId",
        "displayName",
        "legalName",
        "logoLight",
        "logoDark",
        "logoAlt",
        "favicon",
        "primary",
        "secondary",
        "accent",
        "domain",
        "supportEmail",
        "termsUrl",
        "privacyUrl",
    ]
    assert next(iter(body["securityPolicy"])) == "organizationId"
    assert list(body["effective"]) == [
        "formats",
        "branding",
        "securityPolicy",
        "themeMode",
        "reducedMotion",
        "fontScale",
    ]
    formats = body["effective"]["formats"]
    assert list(formats)[-2:] == ["direction", "useGroupping"]
    assert formats["useGrouping"] is formats["useGroupping"] is True


async def test_a_partial_section_keeps_what_it_omits(api: AuthApi, owner: Member) -> None:
    response, count = await statements(
        save(api, owner, "localization", {"currency": "USD", "firstDayOfWeek": 0})
    )
    assert ok(response) == {"section": "localization"}
    assert count == 2
    stored = (await settings(api, owner))["localization"]
    assert (stored["currency"], stored["firstDayOfWeek"], stored["timeZone"]) == (
        "USD",
        0,
        "Africa/Nairobi",
    )
    assert await history_reasons(api, owner, "localization") == [
        "Changed the first day of the week to Sunday and the currency to USD"
    ]


async def test_grouping_under_its_old_name_is_saved_and_both_names_are_served(
    api: AuthApi, owner: Member
) -> None:
    ok(await save(api, owner, "localization", {"useGroupping": False}))
    assert (await settings(api, owner))["localization"]["useGrouping"] is False
    appearance = ok(await api.client.get("/setup/appearance", headers=owner.headers))
    assert appearance["formats"]["useGrouping"] is appearance["formats"]["useGroupping"] is False
    ok(await save(api, owner, "localization", {"useGroupping": False, "useGrouping": True}))
    assert await history_reasons(api, owner, "localization") == [
        "Changed digit grouping to off",
        "Changed digit grouping to on",
    ]


async def test_an_unchanged_save_logs_nothing_and_a_logged_save_moves_the_version_once(
    api: AuthApi, owner: Member
) -> None:
    before = (await settings(api, owner))["organization"]["settingsVersion"]
    ok(await save(api, owner, "securityPolicy", {"lockoutThreshold": 3}, "  Tighten lockout  "))
    ok(await save(api, owner, "securityPolicy", {"lockoutThreshold": 3}))
    after = (await settings(api, owner))["organization"]["settingsVersion"]
    assert after == before + 1
    assert await history_reasons(api, owner, "securityPolicy") == [
        "Changed the wrong PIN tries before a pause to 3. Reason: Tighten lockout."
    ]


async def test_the_organization_section_answers_plain_details(
    api: AuthApi, owner: Member, owner_conn: psycopg.Connection[dict[str, Any]]
) -> None:
    invalid = await save(api, owner, "organization", {"name": "North", "slug": "../invalid"})
    assert invalid.status_code == 400
    assert invalid.headers["content-type"] == JSON_UTF8
    assert json.loads(invalid.content) == {
        "detail": "Enter an organization name and a lowercase slug using letters, numbers, "
        "and hyphens."
    }
    owner_conn.execute("INSERT INTO tenancy.organizations (slug, name) VALUES ('taken', 'Other')")
    taken = await save(api, owner, "organization", {"name": "North", "slug": "Taken"})
    assert taken.status_code == 409
    assert json.loads(taken.content) == {"detail": "This organization slug is already in use."}
    ok(
        await save(
            api, owner, "organization", {"name": "North Star Fleet", "slug": "north-star-fleet"}
        )
    )
    organization = (await settings(api, owner))["organization"]
    assert (organization["name"], organization["slug"]) == ("North Star Fleet", "north-star-fleet")
    assert await history_reasons(api, owner, "organization") == [
        "Changed the organization name to North Star Fleet and the slug to north-star-fleet"
    ]


@pytest.mark.parametrize(
    ("section", "value", "detail"),
    [
        ("securityPolicy", 3, "Send the section's settings as an object."),
        ("securityPolicy", {"lockoutThreshold": "three"}, "A setting has the wrong type of value."),
        ("securityPolicy", {"lockoutThreshold": 99}, "Invalid security policy."),
        ("securityPolicy", {"allowPinSignIn": False}, "PIN sign-in cannot be disabled."),
        ("localization", {"locale": "english!"}, "Use BCP 47 locale."),
        (
            "localization",
            {"timeZone": "Mars/Olympus"},
            "'Mars/Olympus' is an unknown or invalid time zone identifier. (Parameter 'value')",
        ),
        (
            "branding",
            {"primary": "#FFFFFF"},
            "Brand colors must meet WCAG AA (4.5:1) against the fixed surfaces",
        ),
        ("branding", {"termsUrl": "http://example.com"}, "Brand URLs must use HTTPS."),
        ("businessDate", "2999-01-01", "The business date cannot be in the future."),
        ("businessDate", "0001-01-01", "Business date must be a valid calendar date or null."),
    ],
)
async def test_a_refused_section_answers_its_sentence(
    api: AuthApi, owner: Member, section: str, value: Any, detail: str
) -> None:
    problem(await save(api, owner, section, value), 400, INVALID, detail)


async def test_an_unknown_section_is_not_found_after_the_reason_check(
    api: AuthApi, owner: Member
) -> None:
    problem(await save(api, owner, "theme", {}), 404, NOT_FOUND)
    problem(
        await save(api, owner, "theme", {}, "x" * 501),
        400,
        INVALID,
        "A reason of 1\u2013500 characters is required.",
    )


async def test_the_business_date_is_held_and_returned(api: AuthApi, owner: Member) -> None:
    calendar = (await settings(api, owner))["calendarDate"]
    ok(await save(api, owner, "businessDate", calendar, "Reconcile"))
    held = await settings(api, owner)
    assert held["organization"]["businessDate"] == held["effectiveBusinessDate"] == calendar
    ok(await save(api, owner, "businessDate", None))
    assert (await settings(api, owner))["organization"]["businessDate"] is None
    assert await history_reasons(api, owner, "businessDate") == [
        f"Set the business date to {calendar}. Reason: Reconcile.",
        "Returned the business date to the calendar",
    ]


async def test_logos_are_checked_recorded_and_removed(api: AuthApi, owner: Member) -> None:
    response, count = await statements(
        api.client.put("/setup/organization/logo", json={"dataUrl": PNG}, headers=owner.headers)
    )
    assert ok(response) == {"logo": PNG}
    assert count == 2
    appearance = ok(await api.client.get("/setup/appearance", headers=owner.headers))
    assert appearance["branding"]["logo"] == PNG
    for data_url, detail in (
        (
            "data:image/png;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==",
            "The file is not the image type it claims to be.",
        ),
        ("data:image/svg+xml;base64,PHN2Zz48L3N2Zz4=", "Upload a PNG, JPEG or WebP image."),
        ("data:image/png;base64,!!!!", "Upload a PNG, JPEG or WebP image."),
        ("data:image/png;base64,abc", "The image could not be read."),
        ("data:image/png;base64," + "A" * 400_000, "The logo must be at most 256 KB."),
    ):
        refused = await api.client.put(
            "/setup/organization/logo", json={"dataUrl": data_url}, headers=owner.headers
        )
        problem(refused, 400, INVALID, detail)
    deleted = await api.client.delete(
        "/setup/organization/logo?reason=Brand%20withdrawn", headers=owner.headers
    )
    assert ok(deleted) == {"logo": None}
    assert ok(await api.client.delete("/setup/organization/logo", headers=owner.headers)) == {
        "logo": None
    }
    assert await history_reasons(api, owner, "logo") == [
        "Uploaded a new logo",
        "Removed the logo. Reason: Brand withdrawn.",
    ]


async def test_settings_need_organization_manage(api: AuthApi, owner: Member) -> None:
    clerk = await join(api, email="clerk@example.com", phone="0722000111", role="Revenue clerk")
    problem(
        await api.client.get("/setup/organization/settings", headers=clerk.headers), 403, FORBIDDEN
    )
    problem(await save(api, clerk, "branding", {"displayName": "X"}), 403, FORBIDDEN)
    problem(
        await api.client.put(
            "/setup/organization/logo", json={"dataUrl": PNG}, headers=clerk.headers
        ),
        403,
        FORBIDDEN,
    )
    empty(await api.client.get("/setup/organization/settings"), 401)


async def test_a_section_save_without_json_is_415(api: AuthApi, owner: Member) -> None:
    response = await api.client.put(
        "/setup/organization/settings/branding",
        content=b'{"value": {}}',
        headers={**owner.headers, "Content-Type": "text/plain"},
    )
    empty(response, 415)
