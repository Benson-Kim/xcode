"""The organization settings, logo, appearance and preferences routines, called as ``xcode_app``.

Stored rows are changed or read as ``xcode_owner`` where a test needs state no routine writes
(a stored value the validation would refuse today, a section with no row, a preference stored
before an override was switched off). Snapshots are compared as literal compact JSON text.
"""

from __future__ import annotations

import base64
import json
import threading
from collections.abc import Callable
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ..support.rows import PNG_BYTES, seed_organization
from ..support.scenario import T0, Conn, call
from ..support.tenancy import (
    REQUEST,
    Member,
    audit_events,
    change_log,
    provision_member,
    refused,
    set_localization,
    set_organization,
    settings_version,
    write,
)

JPEG_BYTES = bytes.fromhex("ffd8ffe000104a464946") + b"\x00" * 6
WEBP_BYTES = b"RIFF" + b"\x0c\x00\x00\x00" + b"WEBP" + b"VP8 "

LOCALIZATION_FULL = {
    "locale": "en-US",
    "time_zone": "Africa/Kampala",
    "date_pattern": "long",
    "hour12": True,
    "first_day_of_week": 0,
    "week_numbering": "local",
    "currency": "USD",
    "use_grouping": False,
    "number_decimals": 0,
    "allow_locale_override": False,
    "allow_time_zone_override": True,
    "allow_hour12_override": False,
    "allow_theme_override": False,
}
BRANDING_FULL = {
    "display_name": "North Star",
    "legal_name": "North Star Fleet Ltd",
    "logo_light": "https://cdn.example.com/light.png",
    "logo_dark": "https://cdn.example.com/dark.png",
    "logo_alt": "North Star logo",
    "favicon": "https://cdn.example.com/favicon.ico",
    "primary": "#0B5FA5",
    "secondary": "#14213D",
    "accent": "#1E6B3A",
    "domain": "northstar.example.com",
    "support_email": "help@northstar.example.com",
    "terms_url": "https://northstar.example.com/terms",
    "privacy_url": "https://northstar.example.com/privacy",
}
POLICY_FULL = {
    "password_min_length": 14,
    "password_complexity": False,
    "password_history": 3,
    "pin_length": 6,
    "lockout_threshold": 3,
    "lockout_minutes": 30,
    "access_token_minutes": 5,
    "refresh_token_days": 60,
    "idle_unlock_seconds": 120,
    "allow_pin_sign_in": True,
}
DOCUMENT_KEY = {
    "localization": "localization",
    "branding": "branding",
    "securityPolicy": "security_policy",
}

LOCALIZATION_TEXT = (
    '{"organizationId":"ORG","locale":"en-GB","timeZone":"Africa/Nairobi",'
    '"datePattern":"medium","hour12":false,"firstDayOfWeek":1,"weekNumbering":"iso8601",'
    '"currency":"KES","useGrouping":true,"numberDecimals":2,"allowLocaleOverride":true,'
    '"allowTimeZoneOverride":false,"allowHour12Override":true,"allowThemeOverride":true}'
)
BRANDING_TEXT = (
    '{"organizationId":"ORG","displayName":"XCODE","legalName":"XCODE","logoLight":null,'
    '"logoDark":null,"logoAlt":"XCODE","favicon":null,"primary":"#1D5FD6",'
    '"secondary":"#14213D","accent":"#1E6B3A","domain":null,"supportEmail":null,'
    '"termsUrl":null,"privacyUrl":null}'
)
POLICY_TEXT = (
    '{"organizationId":"ORG","passwordMinLength":12,"passwordComplexity":true,'
    '"passwordHistory":5,"pinLength":4,"lockoutThreshold":5,"lockoutMinutes":15,'
    '"accessTokenMinutes":10,"refreshTokenDays":30,"idleUnlockSeconds":900,'
    '"allowPinSignIn":true}'
)


def _text(template: str, org: UUID, *swaps: tuple[str, str]) -> str:
    text = template.replace("ORG", str(org))
    for old, new in swaps:
        assert old in text
        text = text.replace(old, new)
    return text


def _png(size: int) -> bytes:
    return PNG_BYTES[:8] + b"\x00" * (size - 8)


def _save(
    app: Conn,
    who: Member,
    section: str | None,
    value: Any,
    reason: str | None = None,
    expected: int | None = None,
    now: datetime = T0,
) -> dict[str, Any]:
    payload = value if value is None else Jsonb(value)
    return write(
        app,
        "organization_settings_set",
        who.id,
        who.org,
        REQUEST,
        section,
        payload,
        reason,
        expected,
        now,
    )


def _save_refused(
    app: Conn,
    who: Member,
    section: str | None,
    value: Any,
    sqlstate: str,
    code: str,
    reason: str | None = None,
    expected: int | None = None,
    now: datetime = T0,
) -> psycopg.Error:
    payload = value if value is None else Jsonb(value)
    args = [who.id, who.org, REQUEST, section, payload, reason, expected, now]
    return refused(app, "organization_settings_set", args, sqlstate, code)


def _get(app: Conn, who: Member, now: datetime = T0) -> dict[str, Any]:
    result: dict[str, Any] = call(app, "organization_settings_get", who.id, who.org, REQUEST, now)
    return result


def _appearance(app: Conn, who: Member) -> dict[str, Any]:
    result: dict[str, Any] = call(app, "organization_appearance_get", who.id, who.org, REQUEST, T0)
    return result


def _preferences(app: Conn, who: Member) -> dict[str, Any]:
    result: dict[str, Any] = call(app, "preferences_get", who.id, who.org, REQUEST, T0)
    return result


def _set_preferences(
    app: Conn,
    who: Member,
    locale: str | None = None,
    time_zone: str | None = None,
    hour12: bool | None = None,
    theme_mode: str | None = None,
    reduced_motion: bool | None = False,
    font_scale: float | None = 1.0,
) -> dict[str, Any]:
    result: dict[str, Any] = call(
        app,
        "preferences_set",
        who.id,
        who.org,
        REQUEST,
        locale,
        time_zone,
        hour12,
        theme_mode,
        reduced_motion,
        font_scale,
        T0,
    )
    return result


def _set_preferences_refused(
    app: Conn, who: Member, code: str, sqlstate: str = "XC422", **values: Any
) -> psycopg.Error:
    fields: dict[str, Any] = {
        "locale": None,
        "time_zone": None,
        "hour12": None,
        "theme_mode": None,
        "reduced_motion": False,
        "font_scale": 1.0,
        **values,
    }
    args = [
        who.id,
        who.org,
        REQUEST,
        fields["locale"],
        fields["time_zone"],
        fields["hour12"],
        fields["theme_mode"],
        fields["reduced_motion"],
        fields["font_scale"],
        T0,
    ]
    return refused(app, "preferences_set", args, sqlstate, code)


def _store_preferences(owner_conn: Conn, who: Member, **values: Any) -> None:
    columns = ", ".join(values)
    placeholders = ", ".join(["%s"] * len(values))
    assignments = ", ".join(f"{name} = EXCLUDED.{name}" for name in values)
    owner_conn.execute(
        f"INSERT INTO tenancy.user_preferences (organization_id, user_id, {columns}) "
        f"VALUES (%s, %s, {placeholders}) ON CONFLICT (organization_id, user_id) "
        f"DO UPDATE SET {assignments}",
        (who.org, who.id, *values.values()),
    )


def _upload(
    app: Conn,
    who: Member,
    data: bytes,
    content_type: str = "image/png",
    reason: str | None = None,
) -> dict[str, Any]:
    return write(
        app, "organization_logo_set", who.id, who.org, REQUEST, content_type, data, reason, T0
    )


def _upload_refused(
    app: Conn, who: Member, data: bytes | None, content_type: str | None, code: str
) -> None:
    args = [who.id, who.org, REQUEST, content_type, data, None, T0]
    refused(app, "organization_logo_set", args, "XC422", code)


def _remove_logo(app: Conn, who: Member, reason: str | None = None) -> dict[str, Any]:
    return write(app, "organization_logo_delete", who.id, who.org, REQUEST, reason, T0)


def _last(owner_conn: Conn, org: UUID) -> dict[str, Any]:
    return change_log(owner_conn, org)[-1]


def _race(
    app_url: str, first: Callable[[Conn], Any], late: Callable[[Conn], Any]
) -> tuple[Any, Any]:
    """Runs ``late`` on a second connection while ``first`` holds its transaction open."""
    results: list[Any] = []
    with (
        psycopg.connect(app_url, autocommit=True, row_factory=dict_row) as one,
        psycopg.connect(app_url, autocommit=True, row_factory=dict_row) as two,
    ):
        started = threading.Event()

        def run_late() -> None:
            started.set()
            try:
                results.append(late(two))
            except psycopg.Error as error:
                results.append((error.sqlstate, error.diag.message_primary))

        with one.transaction():
            done = first(one)
            worker = threading.Thread(target=run_late)
            worker.start()
            assert started.wait(10)
            worker.join(0.5)
            # The late call waits on the row lock the first one holds until it commits.
            assert worker.is_alive()
        worker.join(10)
    assert len(results) == 1
    return done, results[0]


@pytest.fixture
def owner(operator_conn: Conn) -> Member:
    return provision_member(operator_conn, 1, "Owner", "Olive", "Owner")


@pytest.fixture
def office(operator_conn: Conn, owner: Member) -> Member:
    return provision_member(operator_conn, 2, "Office admin", "Otto", "Office")


@pytest.fixture
def clerk(operator_conn: Conn, owner: Member) -> Member:
    return provision_member(operator_conn, 3, "Revenue clerk", "Cleo", "Clerk")


# --- defaults ---


@pytest.mark.parametrize(
    ("section", "table", "renames"),
    [
        ("localization", "organization_localizations", {}),
        (
            "branding",
            "organization_brandings",
            {
                "primary_color": "primary",
                "secondary_color": "secondary",
                "accent_color": "accent",
                "logo_light_url": "logo_light",
                "logo_dark_url": "logo_dark",
                "favicon_url": "favicon",
            },
        ),
        ("securityPolicy", "organization_security_policies", {}),
    ],
)
def test_the_settings_defaults_equal_the_column_defaults(
    owner_conn: Conn, section: str, table: str, renames: dict[str, str]
) -> None:
    fresh = owner_conn.execute(
        "INSERT INTO tenancy.organizations (slug, name) VALUES ('fresh', 'Fresh') RETURNING id"
    ).fetchone()
    assert fresh is not None
    owner_conn.execute(f"INSERT INTO tenancy.{table} (organization_id) VALUES (%s)", (fresh["id"],))
    row = owner_conn.execute(
        f"SELECT * FROM tenancy.{table} WHERE organization_id = %s", (fresh["id"],)
    ).fetchone()
    assert row is not None
    skipped = ("organization_id", "created_at", "updated_at")
    stored = {renames.get(k, k): v for k, v in row.items() if k not in skipped}
    defaults = owner_conn.execute(
        "SELECT tenancy.settings_defaults(%s) AS d", (section,)
    ).fetchone()
    assert defaults is not None
    assert defaults["d"] == stored


def test_settings_defaults_of_another_section_are_null(owner_conn: Conn) -> None:
    for section in ("organization", "businessDate", "logo", "bogus"):
        row = owner_conn.execute("SELECT tenancy.settings_defaults(%s) AS d", (section,)).fetchone()
        assert row == {"d": None}


# --- reading the settings ---


def test_settings_get_returns_the_stored_sections_and_the_effective_values(
    app_conn: Conn, owner: Member
) -> None:
    settings = _get(app_conn, owner)
    assert settings["organization"] == {
        "id": str(owner.org),
        "slug": "my-fleet",
        "name": "My fleet",
        "business_date": None,
        "settings_version": 1,
    }
    assert settings["localization"]["organization_id"] == str(owner.org)
    assert settings["localization"]["time_zone"] == "Africa/Nairobi"
    assert settings["branding"]["primary"] == "#1D5FD6"
    assert settings["security_policy"]["lockout_threshold"] == 5
    assert settings["calendar_date"] == "2026-10-09"
    assert settings["effective_business_date"] == "2026-10-09"
    assert set(settings["effective"]) == {
        "formats",
        "branding",
        "security_policy",
        "theme_mode",
        "reduced_motion",
        "font_scale",
    }
    assert settings["effective"]["formats"]["currency"] == "KES"
    assert settings["effective"]["security_policy"]["lockout_minutes"] == 15


def test_a_held_business_date_is_the_effective_one_and_the_calendar_date_stays_today(
    app_conn: Conn, owner: Member
) -> None:
    _save(app_conn, owner, "businessDate", "2026-10-02")
    settings = _get(app_conn, owner)
    assert settings["organization"]["business_date"] == "2026-10-02"
    assert settings["effective_business_date"] == "2026-10-02"
    assert settings["calendar_date"] == "2026-10-09"


def test_the_calendar_date_follows_the_organization_time_zone(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    late = datetime(2026, 10, 9, 22, 30, tzinfo=UTC)
    assert _get(app_conn, owner, late)["calendar_date"] == "2026-10-10"
    set_localization(owner_conn, owner.org, time_zone="UTC")
    assert _get(app_conn, owner, late)["calendar_date"] == "2026-10-09"


def test_a_section_without_a_row_is_served_as_its_defaults(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    owner_conn.execute(
        "DELETE FROM tenancy.organization_security_policies WHERE organization_id = %s",
        (owner.org,),
    )
    policy = _get(app_conn, owner)["security_policy"]
    assert policy["organization_id"] == str(owner.org)
    assert (policy["lockout_threshold"], policy["pin_length"]) == (5, 4)


def test_settings_get_needs_organization_manage(
    app_conn: Conn, office: Member, clerk: Member
) -> None:
    for who in (office, clerk):
        args = [who.id, who.org, REQUEST, T0]
        refused(app_conn, "organization_settings_get", args, "XC403", "permission_missing")


def test_settings_get_refuses_a_stored_time_zone_postgresql_does_not_know(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    set_localization(owner_conn, owner.org, time_zone="Mars/Olympus")
    args = [owner.id, owner.org, REQUEST, T0]
    error = refused(app_conn, "organization_settings_get", args, "XC422", "time_zone_invalid")
    assert json.loads(error.diag.message_detail or "") == {"value": "Mars/Olympus"}


# --- saving a section ---


@pytest.mark.parametrize(
    ("section", "value"),
    [
        ("localization", LOCALIZATION_FULL),
        ("branding", BRANDING_FULL),
        ("securityPolicy", POLICY_FULL),
    ],
)
def test_a_full_payload_replaces_every_field_of_the_section(
    app_conn: Conn, owner: Member, section: str, value: dict[str, Any]
) -> None:
    row = _save(app_conn, owner, section, value)
    assert (row["id"], row["outcome"]) == (owner.org, "updated")
    stored = _get(app_conn, owner)[DOCUMENT_KEY[section]]
    assert stored == {"organization_id": str(owner.org), **value}


@pytest.mark.parametrize(
    ("section", "partial"),
    [
        ("localization", {"currency": "USD", "hour12": True}),
        ("branding", {"display_name": "North Star"}),
        ("securityPolicy", {"pin_length": 6}),
    ],
)
def test_a_partial_payload_keeps_the_omitted_fields(
    app_conn: Conn, owner: Member, section: str, partial: dict[str, Any]
) -> None:
    before = _get(app_conn, owner)[DOCUMENT_KEY[section]]
    assert _save(app_conn, owner, section, partial)["outcome"] == "updated"
    after = _get(app_conn, owner)[DOCUMENT_KEY[section]]
    assert after == {**before, **partial}
    assert after != before


def test_a_nullable_branding_field_can_be_cleared(app_conn: Conn, owner: Member) -> None:
    _save(app_conn, owner, "branding", {"logo_light": "https://cdn.example.com/light.png"})
    assert _get(app_conn, owner)["branding"]["logo_light"] == "https://cdn.example.com/light.png"
    _save(app_conn, owner, "branding", {"logo_light": None})
    assert _get(app_conn, owner)["branding"]["logo_light"] is None


def test_the_organization_section_saves_a_trimmed_lower_case_slug(
    app_conn: Conn, owner: Member
) -> None:
    row = _save(
        app_conn, owner, "organization", {"name": "  North Star Fleet ", "slug": " North-Star "}
    )
    assert row["outcome"] == "updated"
    organization = _get(app_conn, owner)["organization"]
    assert (organization["name"], organization["slug"]) == ("North Star Fleet", "north-star")


def test_the_organization_name_and_slug_accept_their_maximum_lengths(
    app_conn: Conn, owner: Member
) -> None:
    row = _save(app_conn, owner, "organization", {"name": "n" * 200, "slug": "s" * 100})
    assert row["outcome"] == "updated"


def test_unknown_keys_and_an_organization_id_in_the_payload_are_ignored(
    app_conn: Conn, owner: Member
) -> None:
    before = _get(app_conn, owner)["localization"]
    other = str(uuid4())
    row = _save(
        app_conn, owner, "localization", {"currency": "USD", "organization_id": other, "bogus": 1}
    )
    assert row["outcome"] == "updated"
    after = _get(app_conn, owner)["localization"]
    assert after == {**before, "currency": "USD"}
    assert "bogus" not in after


def test_a_payload_of_only_unknown_keys_changes_nothing(app_conn: Conn, owner: Member) -> None:
    row = _save(app_conn, owner, "localization", {"bogus": 1, "organization_id": str(uuid4())})
    assert row["outcome"] == "unchanged"


def test_the_legacy_grouping_key_is_accepted(app_conn: Conn, owner: Member) -> None:
    assert _save(app_conn, owner, "localization", {"use_groupping": False})["outcome"] == "updated"
    localization = _get(app_conn, owner)["localization"]
    assert localization["use_grouping"] is False
    assert "use_groupping" not in localization


def test_the_current_grouping_key_wins_over_the_legacy_one(app_conn: Conn, owner: Member) -> None:
    _save(app_conn, owner, "localization", {"use_grouping": False})
    row = _save(app_conn, owner, "localization", {"use_grouping": True, "use_groupping": False})
    assert row["outcome"] == "updated"
    assert _get(app_conn, owner)["localization"]["use_grouping"] is True


def test_a_section_without_a_row_is_created_from_the_defaults_and_the_payload(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    owner_conn.execute(
        "DELETE FROM tenancy.organization_security_policies WHERE organization_id = %s",
        (owner.org,),
    )
    row = _save(app_conn, owner, "securityPolicy", {})
    assert row["outcome"] == "updated"
    entry = _last(owner_conn, owner.org)
    assert entry["before"] == "null"
    assert entry["after"] == _text(POLICY_TEXT, owner.org)


# --- wrong shapes and wrong types ---


@pytest.mark.parametrize(
    ("section", "value"),
    [
        ("securityPolicy", {"lockout_threshold": "three"}),
        ("securityPolicy", {"lockout_threshold": 3.5}),
        ("securityPolicy", {"lockout_threshold": None}),
        ("securityPolicy", {"lockout_threshold": True}),
        ("securityPolicy", {"lockout_threshold": 99999999999}),
        ("securityPolicy", {"password_complexity": "yes"}),
        ("securityPolicy", {"allow_pin_sign_in": 1}),
        ("localization", {"hour12": "true"}),
        ("localization", {"locale": 5}),
        ("localization", {"number_decimals": "2"}),
        ("localization", {"time_zone": None}),
        ("branding", {"display_name": 5}),
        ("branding", {"display_name": None}),
        ("branding", {"logo_light": 5}),
        ("branding", {"primary": ["#1D5FD6"]}),
        ("organization", {"name": 5, "slug": "ok"}),
        ("organization", {"name": "Fleet", "slug": {"a": 1}}),
    ],
)
def test_a_wrongly_typed_value_is_refused(
    app_conn: Conn, owner: Member, section: str, value: Any
) -> None:
    _save_refused(app_conn, owner, section, value, "XC422", "settings_wrong_type")


@pytest.mark.parametrize("section", ["organization", "localization", "branding", "securityPolicy"])
@pytest.mark.parametrize("value", [[], "text", 5, True, None, [1, 2]])
def test_a_value_that_is_not_an_object_is_refused(
    app_conn: Conn, owner: Member, section: str, value: Any
) -> None:
    _save_refused(app_conn, owner, section, value, "XC422", "settings_not_object")


def test_a_json_null_is_not_an_object_either(app_conn: Conn, owner: Member) -> None:
    args = [owner.id, owner.org, REQUEST, "localization", Jsonb(None), None, None, T0]
    refused(app_conn, "organization_settings_set", args, "XC422", "settings_not_object")


@pytest.mark.parametrize("section", ["bogus", "Localization", "security_policy", "", None])
def test_an_unknown_section_is_not_found(
    app_conn: Conn, owner: Member, section: str | None
) -> None:
    _save_refused(app_conn, owner, section, {"currency": "USD"}, "XC404", "not_found")


def test_the_reason_length_is_checked_before_the_section_is_known(
    app_conn: Conn, owner: Member
) -> None:
    _save_refused(app_conn, owner, "bogus", {}, "XC422", "reason_length", reason="x" * 501)


@pytest.mark.parametrize("section", ["localization", "businessDate"])
def test_a_typed_reason_over_five_hundred_characters_is_refused(
    app_conn: Conn, owner: Member, section: str
) -> None:
    value: Any = {"currency": "USD"} if section == "localization" else "2026-10-01"
    _save_refused(app_conn, owner, section, value, "XC422", "reason_length", reason="x" * 501)


def test_saving_needs_organization_manage(app_conn: Conn, office: Member, clerk: Member) -> None:
    for who in (office, clerk):
        _save_refused(app_conn, who, "localization", {}, "XC403", "permission_missing")


def test_a_stale_expected_version_conflicts_and_the_current_one_saves(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    current = settings_version(owner_conn, owner.org)
    for section, value in (
        ("localization", {"currency": "USD"}),
        ("branding", {"display_name": "North Star"}),
        ("securityPolicy", {"pin_length": 6}),
        ("organization", {"name": "North Star", "slug": "north-star"}),
        ("businessDate", "2026-10-01"),
    ):
        _save_refused(
            app_conn, owner, section, value, "XC409", "version_conflict", expected=current + 7
        )
    assert settings_version(owner_conn, owner.org) == current
    row = _save(app_conn, owner, "localization", {"currency": "USD"}, expected=current)
    assert row["outcome"] == "updated"


def test_two_saves_of_one_section_at_once_keep_both_changes(
    app_conn: Conn, app_url: str, owner_conn: Conn, owner: Member
) -> None:
    current = settings_version(owner_conn, owner.org)
    first, late = _race(
        app_url,
        lambda one: _save(one, owner, "localization", {"currency": "USD"}),
        lambda two: _save(two, owner, "localization", {"hour12": True}),
    )
    assert (first["version"], late["version"]) == (current + 1, current + 2)
    stored = _get(app_conn, owner)[DOCUMENT_KEY["localization"]]
    assert (stored["currency"], stored["hour12"]) == ("USD", True)
    earlier, later = change_log(owner_conn, owner.org)[-2:]
    assert later["before"] == earlier["after"]


# --- the validation codes ---


NAME_SLUG_VALUES = [
    {"name": "", "slug": "ok"},
    {"name": "   ", "slug": "ok"},
    {"name": "Fleet", "slug": ""},
    {"name": "Fleet", "slug": "Bad Slug"},
    {"name": "Fleet", "slug": "-bad"},
    {"name": "Fleet", "slug": "bad-"},
    {"name": "Fleet", "slug": "a--b"},
    {"name": "Fleet", "slug": "a_b"},
    {"name": "n" * 201, "slug": "ok"},
    {"name": "Fleet", "slug": "s" * 101},
    {"name": "Fleet"},
    {"slug": "ok"},
    {},
]


def test_the_organization_name_and_slug_must_be_valid(app_conn: Conn, owner: Member) -> None:
    for value in NAME_SLUG_VALUES:
        _save_refused(app_conn, owner, "organization", value, "XC422", "organization_name_slug")


def test_a_slug_used_by_another_organization_conflicts(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    seed_organization(owner_conn, slug="taken")
    _save_refused(
        app_conn,
        owner,
        "organization",
        {"name": "Fleet", "slug": "Taken"},
        "XC409",
        "organization_slug_taken",
    )
    assert settings_version(owner_conn, owner.org) == 1


@pytest.mark.parametrize("locale", ["not a locale", "e", "en_GB", "", "english-gb-"])
def test_the_locale_must_be_a_bcp_47_tag(app_conn: Conn, owner: Member, locale: str) -> None:
    _save_refused(app_conn, owner, "localization", {"locale": locale}, "XC422", "locale_invalid")


@pytest.mark.parametrize("zone", ["Mars/Olympus", "africa/nairobi", "", "Nowhere"])
def test_the_time_zone_must_be_one_postgresql_knows(
    app_conn: Conn, owner: Member, zone: str
) -> None:
    error = _save_refused(
        app_conn, owner, "localization", {"time_zone": zone}, "XC422", "time_zone_invalid"
    )
    assert json.loads(error.diag.message_detail or "") == {"value": zone}


@pytest.mark.parametrize(
    "value",
    [
        {"date_pattern": "tiny"},
        {"first_day_of_week": 7},
        {"first_day_of_week": -1},
        {"week_numbering": "us"},
        {"currency": "usd"},
        {"currency": "US"},
        {"currency": "USDX"},
        {"number_decimals": 3},
        {"number_decimals": -1},
    ],
)
def test_the_format_settings_must_be_valid(
    app_conn: Conn, owner: Member, value: dict[str, Any]
) -> None:
    _save_refused(app_conn, owner, "localization", value, "XC422", "format_settings_invalid")


def test_the_format_settings_accept_their_bounds(app_conn: Conn, owner: Member) -> None:
    for value in ({"first_day_of_week": 6}, {"number_decimals": 0}, {"date_pattern": "short"}):
        assert _save(app_conn, owner, "localization", value)["outcome"] == "updated"


@pytest.mark.parametrize(
    "value",
    [
        {"display_name": ""},
        {"display_name": "   "},
        {"display_name": "x" * 101},
        {"legal_name": ""},
        {"legal_name": "x" * 201},
        {"logo_alt": ""},
        {"logo_alt": "x" * 201},
    ],
)
def test_the_brand_names_are_required_and_bounded(
    app_conn: Conn, owner: Member, value: dict[str, Any]
) -> None:
    _save_refused(app_conn, owner, "branding", value, "XC422", "brand_names_required")


@pytest.mark.parametrize("key", ["primary", "secondary", "accent"])
@pytest.mark.parametrize("colour", ["red", "#12345", "#GGGGGG", "1D5FD6", "#1D5FD6A"])
def test_a_brand_colour_must_be_a_six_digit_hex_colour(
    app_conn: Conn, owner: Member, key: str, colour: str
) -> None:
    _save_refused(app_conn, owner, "branding", {key: colour}, "XC422", "brand_colour_format")


@pytest.mark.parametrize("key", ["primary", "secondary", "accent"])
@pytest.mark.parametrize("colour", ["#078A22", "#FFFF00", "#FFFFFF", "#CCCCCC"])
def test_a_brand_colour_needs_contrast_against_white_and_the_paper_colour(
    app_conn: Conn, owner: Member, key: str, colour: str
) -> None:
    _save_refused(app_conn, owner, "branding", {key: colour}, "XC422", "brand_contrast")


@pytest.mark.parametrize("key", ["logo_light", "logo_dark", "favicon", "terms_url", "privacy_url"])
@pytest.mark.parametrize(
    "url",
    [
        "http://cdn.example.com/a.png",
        "ftp://cdn.example.com/a.png",
        "//cdn.example.com/a.png",
        "https://",
        "https://a b.example.com",
        "https://cdn.example.com/" + "a" * 2050,
    ],
)
def test_a_brand_url_must_be_https_and_bounded(
    app_conn: Conn, owner: Member, key: str, url: str
) -> None:
    _save_refused(app_conn, owner, "branding", {key: url}, "XC422", "brand_url_https")


@pytest.mark.parametrize(
    "domain",
    [
        "-bad.example.com",
        "exa mple.com",
        "bad..example.com",
        ".example.com",
        "example.com..",
        "a/b.example.com",
        ".".join(["a" * 63, "b" * 63, "c" * 63, "d" * 62]),
    ],
)
def test_a_brand_domain_must_be_a_dns_host_name(app_conn: Conn, owner: Member, domain: str) -> None:
    _save_refused(app_conn, owner, "branding", {"domain": domain}, "XC422", "brand_domain_invalid")


@pytest.mark.parametrize(
    "domain",
    [
        "Example.com",
        "localhost",
        "example.com.",
        "a_b.example.com",
        "b\u00fccher.de",
        ".".join(["a" * 63, "b" * 63, "c" * 63, "d" * 61]),
    ],
)
def test_a_brand_domain_accepts_the_host_names_dotnet_accepts_as_typed(
    app_conn: Conn, owner_conn: Conn, owner: Member, domain: str
) -> None:
    assert _save(app_conn, owner, "branding", {"domain": domain})["outcome"] == "updated"
    stored = owner_conn.execute(
        "SELECT domain FROM tenancy.organization_brandings WHERE organization_id = %s",
        (owner.org,),
    ).fetchone()
    assert stored == {"domain": domain}


@pytest.mark.parametrize("key", ["logo_light", "terms_url"])
@pytest.mark.parametrize("url", ["HTTPS://cdn.example.com/a.png", "Https://Example.com/terms"])
def test_a_brand_url_scheme_is_matched_ignoring_case(
    app_conn: Conn, owner: Member, key: str, url: str
) -> None:
    assert _save(app_conn, owner, "branding", {key: url})["outcome"] == "updated"


@pytest.mark.parametrize("email", ["no-at", "a b@example.com", "@example.com", "a@", "a@@b.com"])
def test_a_brand_support_email_must_be_an_address(
    app_conn: Conn, owner: Member, email: str
) -> None:
    _save_refused(
        app_conn,
        owner,
        "branding",
        {"support_email": email},
        "XC422",
        "brand_support_email_invalid",
    )


def test_brand_domain_and_support_email_may_be_cleared(app_conn: Conn, owner: Member) -> None:
    _save(app_conn, owner, "branding", {"domain": "a.example.com", "support_email": "a@b.com"})
    row = _save(app_conn, owner, "branding", {"domain": None, "support_email": None})
    assert row["outcome"] == "updated"


def test_the_brand_checks_run_in_order(app_conn: Conn, owner: Member) -> None:
    _save_refused(
        app_conn,
        owner,
        "branding",
        {"display_name": "", "primary": "red", "domain": "-bad.example.com"},
        "XC422",
        "brand_names_required",
    )
    _save_refused(
        app_conn,
        owner,
        "branding",
        {"primary": "red", "logo_light": "http://x.example"},
        "XC422",
        "brand_colour_format",
    )
    _save_refused(
        app_conn,
        owner,
        "branding",
        {"logo_light": "http://x.example", "domain": "-bad.example.com"},
        "XC422",
        "brand_url_https",
    )


def test_pin_sign_in_cannot_be_switched_off(app_conn: Conn, owner: Member) -> None:
    _save_refused(
        app_conn,
        owner,
        "securityPolicy",
        {"allow_pin_sign_in": False},
        "XC422",
        "security_policy_pin_sign_in",
    )
    _save_refused(
        app_conn,
        owner,
        "securityPolicy",
        {"allow_pin_sign_in": False, "pin_length": 99},
        "XC422",
        "security_policy_pin_sign_in",
    )


@pytest.mark.parametrize(
    "value",
    [
        {"password_min_length": 11},
        {"password_min_length": 129},
        {"password_history": -1},
        {"password_history": 25},
        {"pin_length": 3},
        {"pin_length": 9},
        {"lockout_threshold": 2},
        {"lockout_threshold": 11},
        {"lockout_minutes": 0},
        {"lockout_minutes": 61},
        {"access_token_minutes": 0},
        {"access_token_minutes": 16},
        {"refresh_token_days": 0},
        {"refresh_token_days": 91},
        {"idle_unlock_seconds": 29},
        {"idle_unlock_seconds": 3601},
    ],
)
def test_the_security_policy_numbers_must_lie_within_their_bounds(
    app_conn: Conn, owner: Member, value: dict[str, Any]
) -> None:
    _save_refused(app_conn, owner, "securityPolicy", value, "XC422", "security_policy_invalid")


def test_the_security_policy_accepts_its_bounds(app_conn: Conn, owner: Member) -> None:
    low = {
        "password_min_length": 12,
        "password_history": 0,
        "pin_length": 4,
        "lockout_threshold": 3,
        "lockout_minutes": 1,
        "access_token_minutes": 1,
        "refresh_token_days": 1,
        "idle_unlock_seconds": 30,
    }
    high = {
        "password_min_length": 128,
        "password_history": 24,
        "pin_length": 8,
        "lockout_threshold": 10,
        "lockout_minutes": 60,
        "access_token_minutes": 15,
        "refresh_token_days": 90,
        "idle_unlock_seconds": 3600,
    }
    assert _save(app_conn, owner, "securityPolicy", low)["outcome"] == "updated"
    assert _save(app_conn, owner, "securityPolicy", high)["outcome"] == "updated"


@pytest.mark.parametrize(
    "value",
    [
        5,
        True,
        "tomorrow",
        "2026-02-30",
        "0001-01-01",
        "2026-1-5",
        " 2026-10-08",
        "2026-10-08 ",
        ["x"],
    ],
)
def test_the_business_date_must_be_a_calendar_date_or_null(
    app_conn: Conn, owner: Member, value: Any
) -> None:
    _save_refused(app_conn, owner, "businessDate", value, "XC422", "business_date_invalid")


@pytest.mark.parametrize("value", ["2026-10-10", "2999-12-31"])
def test_the_business_date_cannot_be_after_today_in_the_organization_zone(
    app_conn: Conn, owner: Member, value: str
) -> None:
    _save_refused(app_conn, owner, "businessDate", value, "XC422", "business_date_future")


def test_today_in_the_organization_zone_is_not_in_the_future(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    late = datetime(2026, 10, 9, 22, 30, tzinfo=UTC)
    _save_refused(
        app_conn, owner, "businessDate", "2026-10-10", "XC422", "business_date_future", now=T0
    )
    assert _save(app_conn, owner, "businessDate", "2026-10-10", now=late)["outcome"] == "updated"


def test_changing_the_zone_cannot_put_a_held_business_date_in_the_future(
    app_conn: Conn, owner: Member
) -> None:
    _save(app_conn, owner, "localization", {"time_zone": "Pacific/Kiritimati"})
    _save(app_conn, owner, "businessDate", "2026-10-09")
    _save_refused(
        app_conn,
        owner,
        "localization",
        {"time_zone": "Pacific/Pago_Pago"},
        "XC422",
        "settings_business_date_future_zone",
    )


def test_changing_the_zone_is_fine_when_the_held_date_stays_valid(
    app_conn: Conn, owner: Member
) -> None:
    _save(app_conn, owner, "localization", {"time_zone": "Pacific/Pago_Pago"})
    _save(app_conn, owner, "businessDate", "2026-10-07")
    row = _save(app_conn, owner, "localization", {"time_zone": "Pacific/Kiritimati"})
    assert row["outcome"] == "updated"


def test_the_zone_check_does_not_apply_to_a_save_that_changes_nothing(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    set_organization(owner_conn, owner.org, business_date=date(2026, 10, 12))
    assert _save(app_conn, owner, "localization", {})["outcome"] == "unchanged"


def test_wrong_types_are_refused_before_values_are_validated(app_conn: Conn, owner: Member) -> None:
    _save_refused(
        app_conn,
        owner,
        "localization",
        {"currency": 5, "locale": "not a locale"},
        "XC422",
        "settings_wrong_type",
    )


# --- the business date ---


def test_a_business_date_can_be_held_and_returned_to_the_calendar(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    row = _save(app_conn, owner, "businessDate", "2026-10-08")
    assert row["outcome"] == "updated"
    entry = _last(owner_conn, owner.org)
    assert entry["reason"] == "Set the business date to 2026-10-08"
    assert (entry["before"], entry["after"]) == ("null", '"2026-10-08"')
    assert _get(app_conn, owner)["organization"]["business_date"] == "2026-10-08"
    _save(app_conn, owner, "businessDate", None)
    entry = _last(owner_conn, owner.org)
    assert entry["reason"] == "Returned the business date to the calendar"
    assert (entry["before"], entry["after"]) == ('"2026-10-08"', "null")
    assert _get(app_conn, owner)["organization"]["business_date"] is None


def test_a_json_null_returns_the_business_date_to_the_calendar_too(
    app_conn: Conn, owner: Member
) -> None:
    _save(app_conn, owner, "businessDate", "2026-10-08")
    row = write(
        app_conn,
        "organization_settings_set",
        owner.id,
        owner.org,
        REQUEST,
        "businessDate",
        Jsonb(None),
        None,
        None,
        T0,
    )
    assert row["outcome"] == "updated"
    assert _get(app_conn, owner)["organization"]["business_date"] is None


def test_todays_date_and_an_earlier_date_are_accepted(app_conn: Conn, owner: Member) -> None:
    assert _save(app_conn, owner, "businessDate", "2026-10-09")["outcome"] == "updated"
    assert _save(app_conn, owner, "businessDate", "2020-01-01")["outcome"] == "updated"


def test_holding_the_same_date_or_none_again_is_unchanged(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    assert _save(app_conn, owner, "businessDate", None)["outcome"] == "unchanged"
    _save(app_conn, owner, "businessDate", "2026-10-08")
    version = settings_version(owner_conn, owner.org)
    row = _save(app_conn, owner, "businessDate", "2026-10-08")
    assert (row["outcome"], row["version"]) == ("unchanged", version)
    assert settings_version(owner_conn, owner.org) == version


def test_a_typed_reason_follows_the_business_date_reason(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    _save(app_conn, owner, "businessDate", "2026-10-08", reason="  Month end close ")
    assert (
        _last(owner_conn, owner.org)["reason"]
        == "Set the business date to 2026-10-08. Reason: Month end close."
    )


# --- automatic reasons ---


def test_the_reason_names_each_changed_setting_with_its_value(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    _save(app_conn, owner, "localization", {"first_day_of_week": 0, "currency": "USD"})
    assert (
        _last(owner_conn, owner.org)["reason"]
        == "Changed the first day of the week to Sunday and the currency to USD"
    )


def test_the_organization_reason_names_the_name(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    _save(app_conn, owner, "organization", {"name": "North Star Fleet", "slug": "my-fleet"})
    assert (
        _last(owner_conn, owner.org)["reason"]
        == "Changed the organization name to North Star Fleet"
    )


def test_the_organization_reason_names_the_slug_too(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    _save(app_conn, owner, "organization", {"name": "North Star Fleet", "slug": "north-star"})
    assert _last(owner_conn, owner.org)["reason"] == (
        "Changed the organization name to North Star Fleet and the slug to north-star"
    )


def test_the_security_policy_reason_names_the_wrong_pin_tries(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    _save(app_conn, owner, "securityPolicy", {"lockout_threshold": 3})
    assert (
        _last(owner_conn, owner.org)["reason"] == "Changed the wrong PIN tries before a pause to 3"
    )


def test_the_branding_reason_names_the_display_name(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    _save(app_conn, owner, "branding", {"display_name": "North Star"})
    assert _last(owner_conn, owner.org)["reason"] == "Changed the display name to North Star"


def test_the_grouping_reason_reads_on_and_off(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    _save(app_conn, owner, "localization", {"use_grouping": False})
    assert _last(owner_conn, owner.org)["reason"] == "Changed digit grouping to off"
    _save(app_conn, owner, "localization", {"use_grouping": True})
    assert _last(owner_conn, owner.org)["reason"] == "Changed digit grouping to on"


def test_three_changed_settings_are_joined_with_commas_and_and(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    _save(
        app_conn, owner, "localization", {"hour12": True, "currency": "USD", "number_decimals": 0}
    )
    assert _last(owner_conn, owner.org)["reason"] == (
        "Changed the 12-hour clock to on, the currency to USD and the decimal places to 0"
    )


def test_a_cleared_value_reads_none(app_conn: Conn, owner_conn: Conn, owner: Member) -> None:
    _save(app_conn, owner, "branding", {"domain": "a.example.com"})
    _save(app_conn, owner, "branding", {"domain": None})
    assert _last(owner_conn, owner.org)["reason"] == "Changed the domain to none"


def test_a_typed_reason_is_appended(app_conn: Conn, owner_conn: Conn, owner: Member) -> None:
    _save(app_conn, owner, "localization", {"use_grouping": False}, reason="Rebrand")
    assert (
        _last(owner_conn, owner.org)["reason"] == "Changed digit grouping to off. Reason: Rebrand."
    )


def test_a_blank_typed_reason_adds_nothing(app_conn: Conn, owner_conn: Conn, owner: Member) -> None:
    _save(app_conn, owner, "localization", {"use_grouping": False}, reason="   ")
    assert _last(owner_conn, owner.org)["reason"] == "Changed digit grouping to off"


def test_the_reason_helper_names_the_section_when_only_the_organization_id_differs(
    owner_conn: Conn,
) -> None:
    row = owner_conn.execute(
        "SELECT tenancy.settings_reason('branding', %s::json, %s::json) AS r",
        ('{"organizationId":"a","displayName":"X"}', '{"organizationId":"b","displayName":"X"}'),
    ).fetchone()
    assert row == {"r": "Changed the branding settings"}


def test_the_reason_helper_lists_every_key_when_there_is_no_earlier_snapshot(
    owner_conn: Conn,
) -> None:
    row = owner_conn.execute(
        "SELECT tenancy.settings_reason('localization', 'null'::json, %s::json) AS r",
        ('{"organizationId":"a","currency":"KES","hour12":false}',),
    ).fetchone()
    assert row == {"r": "Changed the currency to KES and the 12-hour clock to off"}


# --- versions, snapshots and audit ---


def test_one_logged_save_moves_the_settings_version_once(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    start = settings_version(owner_conn, owner.org)
    row = _save(app_conn, owner, "localization", {"currency": "USD"})
    assert (row["id"], row["version"], row["outcome"]) == (owner.org, start + 1, "updated")
    assert settings_version(owner_conn, owner.org) == start + 1
    row = _save(app_conn, owner, "securityPolicy", {"pin_length": 6})
    assert row["version"] == start + 2
    assert [e["version"] for e in change_log(owner_conn, owner.org)] == [start + 1, start + 2]


@pytest.mark.parametrize(
    ("section", "value"),
    [
        ("localization", {"currency": "USD"}),
        ("branding", {"display_name": "North Star"}),
        ("securityPolicy", {"pin_length": 6}),
        ("organization", {"name": "North Star", "slug": "north-star"}),
        ("businessDate", "2026-10-08"),
    ],
)
def test_the_same_payload_twice_is_unchanged_the_second_time_and_logs_once(
    app_conn: Conn, owner_conn: Conn, owner: Member, section: str, value: Any
) -> None:
    first = _save(app_conn, owner, section, value)
    second = _save(app_conn, owner, section, value)
    assert (first["outcome"], second["outcome"]) == ("updated", "unchanged")
    assert second["version"] == first["version"]
    assert settings_version(owner_conn, owner.org) == first["version"]
    assert len(change_log(owner_conn, owner.org)) == 1
    assert len(audit_events(owner_conn, owner.org, "organization.settings.updated")) == 1


def test_an_empty_object_changes_nothing(app_conn: Conn, owner_conn: Conn, owner: Member) -> None:
    for section in ("localization", "branding", "securityPolicy"):
        assert _save(app_conn, owner, section, {})["outcome"] == "unchanged"
    assert change_log(owner_conn, owner.org) == []


def test_a_localization_save_logs_literal_camel_case_snapshots(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    row = _save(app_conn, owner, "localization", {"first_day_of_week": 0, "currency": "USD"})
    entry = _last(owner_conn, owner.org)
    assert (entry["section"], entry["entity_id"], entry["version"]) == (
        "localization",
        owner.org,
        row["version"],
    )
    assert entry["actor_id"] == owner.id
    assert entry["vehicle_id"] is None
    assert entry["before"] == _text(LOCALIZATION_TEXT, owner.org)
    assert entry["after"] == _text(
        LOCALIZATION_TEXT,
        owner.org,
        ('"firstDayOfWeek":1', '"firstDayOfWeek":0'),
        ('"currency":"KES"', '"currency":"USD"'),
    )


def test_a_security_policy_save_logs_literal_camel_case_snapshots(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    _save(app_conn, owner, "securityPolicy", {"lockout_threshold": 3})
    entry = _last(owner_conn, owner.org)
    assert entry["section"] == "securityPolicy"
    assert entry["before"] == _text(POLICY_TEXT, owner.org)
    assert entry["after"] == _text(
        POLICY_TEXT, owner.org, ('"lockoutThreshold":5', '"lockoutThreshold":3')
    )


def test_a_branding_save_logs_literal_camel_case_snapshots(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    _save(
        app_conn,
        owner,
        "branding",
        {"display_name": "North Star", "logo_light": "https://a.example/l.png"},
    )
    entry = _last(owner_conn, owner.org)
    assert entry["before"] == _text(BRANDING_TEXT, owner.org)
    assert entry["after"] == _text(
        BRANDING_TEXT,
        owner.org,
        ('"displayName":"XCODE"', '"displayName":"North Star"'),
        ('"logoLight":null', '"logoLight":"https://a.example/l.png"'),
    )


def test_an_organization_save_logs_the_name_and_slug(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    _save(app_conn, owner, "organization", {"name": "North Star Fleet", "slug": "north-star"})
    entry = _last(owner_conn, owner.org)
    assert (entry["section"], entry["entity_id"]) == ("organization", owner.org)
    assert entry["before"] == '{"name":"My fleet","slug":"my-fleet"}'
    assert entry["after"] == '{"name":"North Star Fleet","slug":"north-star"}'


def test_a_save_writes_an_audit_event_with_the_value_and_the_reason(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    _save(app_conn, owner, "localization", {"use_grouping": False}, reason="Rebrand")
    event = audit_events(owner_conn, owner.org, "organization.settings.updated")[-1]
    entry = _last(owner_conn, owner.org)
    assert event["entity"] == "localization"
    assert event["actor_id"] == owner.id
    assert event["before"] == json.loads(entry["before"])
    assert event["after"] == {
        "value": json.loads(entry["after"]),
        "reason": "Changed digit grouping to off. Reason: Rebrand.",
    }


def test_a_business_date_audit_event_carries_the_date_string(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    _save(app_conn, owner, "businessDate", "2026-10-08")
    event = audit_events(owner_conn, owner.org, "organization.settings.updated")[-1]
    assert event["entity"] == "businessDate"
    assert event["after"] == {
        "value": "2026-10-08",
        "reason": "Set the business date to 2026-10-08",
    }


# --- the logo ---


@pytest.mark.parametrize(
    ("content_type", "data"),
    [("image/png", PNG_BYTES), ("image/jpeg", JPEG_BYTES), ("image/webp", WEBP_BYTES)],
)
def test_png_jpeg_and_webp_logos_are_accepted(
    app_conn: Conn, owner_conn: Conn, owner: Member, content_type: str, data: bytes
) -> None:
    row = _upload(app_conn, owner, data, content_type)
    assert (row["id"], row["outcome"]) == (owner.org, "updated")
    stored = owner_conn.execute(
        "SELECT content_type, data FROM tenancy.organization_logos WHERE organization_id = %s",
        (owner.org,),
    ).fetchone()
    assert stored is not None
    assert (stored["content_type"], bytes(stored["data"])) == (content_type, data)


@pytest.mark.parametrize("content_type", ["image/svg+xml", "image/gif", "text/plain", "", None])
def test_other_content_types_are_not_a_logo(
    app_conn: Conn, owner: Member, content_type: str | None
) -> None:
    _upload_refused(app_conn, owner, PNG_BYTES, content_type, "logo_type")


def test_a_png_that_claims_to_be_a_jpeg_is_refused(app_conn: Conn, owner: Member) -> None:
    _upload_refused(app_conn, owner, PNG_BYTES, "image/jpeg", "logo_signature")
    _upload_refused(app_conn, owner, JPEG_BYTES, "image/png", "logo_signature")
    _upload_refused(app_conn, owner, b"RIFF" + b"\x00" * 12, "image/webp", "logo_signature")


def test_a_logo_over_256_kib_is_too_large(app_conn: Conn, owner: Member) -> None:
    _upload_refused(app_conn, owner, _png(262145), "image/png", "logo_too_large")


def test_an_empty_or_missing_logo_is_too_large_a_range_error(app_conn: Conn, owner: Member) -> None:
    _upload_refused(app_conn, owner, b"", "image/png", "logo_too_large")
    _upload_refused(app_conn, owner, None, "image/png", "logo_too_large")


def test_a_logo_of_exactly_256_kib_is_accepted(app_conn: Conn, owner: Member) -> None:
    assert _upload(app_conn, owner, _png(262144))["outcome"] == "updated"


def test_the_logo_checks_run_type_then_size_then_signature(app_conn: Conn, owner: Member) -> None:
    _upload_refused(app_conn, owner, b"x" * 262145, "image/svg+xml", "logo_type")
    _upload_refused(app_conn, owner, b"x" * 262145, "image/png", "logo_too_large")


def test_a_logo_reason_over_five_hundred_characters_is_refused(
    app_conn: Conn, owner: Member
) -> None:
    args = [owner.id, owner.org, REQUEST, "image/svg+xml", PNG_BYTES, "x" * 501, T0]
    refused(app_conn, "organization_logo_set", args, "XC422", "reason_length")


def test_a_logo_upload_logs_its_shape_and_never_the_image(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    start = settings_version(owner_conn, owner.org)
    row = _upload(app_conn, owner, PNG_BYTES)
    assert row["version"] == start + 1
    entry = _last(owner_conn, owner.org)
    assert (entry["section"], entry["entity_id"], entry["version"]) == (
        "logo",
        owner.org,
        start + 1,
    )
    assert entry["reason"] == "Uploaded a new logo"
    assert entry["before"] == "null"
    assert entry["after"] == (
        '{"contentType":"image/png","bytes":16,"updatedAt":"2026-10-09T07:00:00.000000+00:00"}'
    )
    event = audit_events(owner_conn, owner.org, "organization.settings.updated")[-1]
    assert event["entity"] == "logo"
    assert event["after"] == {
        "value": {
            "contentType": "image/png",
            "bytes": 16,
            "updatedAt": "2026-10-09T07:00:00.000000+00:00",
        },
        "reason": "Uploaded a new logo",
    }


def test_a_second_upload_replaces_the_first_and_logs_the_old_shape(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    _upload(app_conn, owner, PNG_BYTES)
    _upload(app_conn, owner, JPEG_BYTES, "image/jpeg", reason="New brand")
    entry = _last(owner_conn, owner.org)
    assert entry["reason"] == "Uploaded a new logo. Reason: New brand."
    assert entry["before"].startswith('{"contentType":"image/png","bytes":16,')
    assert entry["after"].startswith('{"contentType":"image/jpeg","bytes":16,')


def test_deleting_the_logo_logs_the_old_shape_and_a_null_after(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    _upload(app_conn, owner, PNG_BYTES)
    row = _remove_logo(app_conn, owner)
    assert (row["id"], row["outcome"]) == (owner.org, "updated")
    entry = _last(owner_conn, owner.org)
    assert entry["reason"] == "Removed the logo"
    assert entry["before"] == (
        '{"contentType":"image/png","bytes":16,"updatedAt":"2026-10-09T07:00:00.000000+00:00"}'
    )
    assert entry["after"] == "null"
    gone = owner_conn.execute("SELECT count(*) AS n FROM tenancy.organization_logos").fetchone()
    assert gone == {"n": 0}
    event = audit_events(owner_conn, owner.org, "organization.settings.updated")[-1]
    assert event["after"] == {"value": None, "reason": "Removed the logo"}


def test_deleting_with_a_typed_reason_appends_it(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    _upload(app_conn, owner, PNG_BYTES)
    _remove_logo(app_conn, owner, "Wrong file")
    assert _last(owner_conn, owner.org)["reason"] == "Removed the logo. Reason: Wrong file."


def test_deleting_without_a_logo_is_unchanged_and_logs_nothing(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    version = settings_version(owner_conn, owner.org)
    row = _remove_logo(app_conn, owner)
    assert (row["id"], row["version"], row["outcome"]) == (owner.org, version, "unchanged")
    assert change_log(owner_conn, owner.org) == []
    assert settings_version(owner_conn, owner.org) == version


def test_a_logo_upload_racing_another_logs_the_first_as_its_before(
    app_url: str, owner_conn: Conn, owner: Member
) -> None:
    first, late = _race(
        app_url,
        lambda one: _upload(one, owner, PNG_BYTES),
        lambda two: _upload(two, owner, JPEG_BYTES, "image/jpeg"),
    )
    assert (first["outcome"], late["outcome"]) == ("updated", "updated")
    assert late["version"] == first["version"] + 1
    upload, replacement = change_log(owner_conn, owner.org)
    assert upload["before"] == "null"
    assert replacement["before"] == upload["after"]
    assert replacement["after"].startswith('{"contentType":"image/jpeg","bytes":16,')


def test_two_logo_removals_at_once_remove_it_once(
    app_conn: Conn, app_url: str, owner_conn: Conn, owner: Member
) -> None:
    _upload(app_conn, owner, PNG_BYTES)
    version = settings_version(owner_conn, owner.org)
    first, late = _race(
        app_url, lambda one: _remove_logo(one, owner), lambda two: _remove_logo(two, owner)
    )
    assert (first["version"], first["outcome"]) == (version + 1, "updated")
    assert (late["version"], late["outcome"]) == (version + 1, "unchanged")
    assert len(change_log(owner_conn, owner.org)) == 2


def test_a_logo_delete_reason_over_five_hundred_characters_is_refused(
    app_conn: Conn, owner: Member
) -> None:
    args = [owner.id, owner.org, REQUEST, "x" * 501, T0]
    refused(app_conn, "organization_logo_delete", args, "XC422", "reason_length")


def test_the_logo_routines_need_organization_manage(
    app_conn: Conn, office: Member, clerk: Member
) -> None:
    for who in (office, clerk):
        upload_args = [who.id, who.org, REQUEST, "image/png", PNG_BYTES, None, T0]
        refused(app_conn, "organization_logo_set", upload_args, "XC403", "permission_missing")
        delete_args = [who.id, who.org, REQUEST, None, T0]
        refused(app_conn, "organization_logo_delete", delete_args, "XC403", "permission_missing")


# --- appearance ---


def test_appearance_of_a_fresh_organization(app_conn: Conn, clerk: Member) -> None:
    assert _appearance(app_conn, clerk) == {
        "organization_name": "My fleet",
        "settings_version": 1,
        "business_date": "2026-10-09",
        "branding": {
            "display_name": "XCODE",
            "logo_alt": "XCODE",
            "primary": "#1D5FD6",
            "secondary": "#14213D",
            "accent": "#1E6B3A",
            "logo": None,
        },
        "formats": {
            "locale": "en-GB",
            "time_zone": "Africa/Nairobi",
            "date_pattern": "medium",
            "hour12": False,
            "first_day_of_week": 1,
            "week_numbering": "iso8601",
            "currency": "KES",
            "use_grouping": True,
            "number_decimals": 2,
            "direction": "ltr",
        },
        "theme_mode": "system",
        "reduced_motion": False,
        "font_scale": 1,
        "lockout_threshold": 5,
        "lockout_minutes": 15,
        "idle_unlock_seconds": 900,
    }


def test_appearance_follows_the_saved_settings(
    app_conn: Conn, owner: Member, clerk: Member
) -> None:
    _save(app_conn, owner, "organization", {"name": "North Star", "slug": "north-star"})
    _save(app_conn, owner, "branding", {"display_name": "North Star", "primary": "#0B5FA5"})
    _save(app_conn, owner, "securityPolicy", {"lockout_threshold": 3, "lockout_minutes": 30})
    _save(app_conn, owner, "businessDate", "2026-10-02")
    appearance = _appearance(app_conn, clerk)
    assert appearance["organization_name"] == "North Star"
    assert appearance["settings_version"] == 5
    assert appearance["business_date"] == "2026-10-02"
    assert appearance["branding"]["display_name"] == "North Star"
    assert appearance["branding"]["primary"] == "#0B5FA5"
    # Five wrong PINs lock whatever the policy says (docs/07-auth.md 12.5); the minutes follow it.
    assert (appearance["lockout_threshold"], appearance["lockout_minutes"]) == (5, 30)


def test_appearance_business_date_is_the_calendar_date_when_none_is_held(
    app_conn: Conn, owner_conn: Conn, clerk: Member
) -> None:
    set_localization(owner_conn, clerk.org, time_zone="Pacific/Kiritimati")
    assert _appearance(app_conn, clerk)["business_date"] == "2026-10-09"
    set_localization(owner_conn, clerk.org, time_zone="Pacific/Pago_Pago")
    assert _appearance(app_conn, clerk)["business_date"] == "2026-10-08"


@pytest.mark.parametrize(
    ("flag", "column", "stored", "when_allowed", "when_not_allowed", "read"),
    [
        ("allow_locale_override", "locale", "sw-KE", "sw-KE", "en-GB", ("formats", "locale")),
        (
            "allow_time_zone_override",
            "time_zone",
            "Africa/Kampala",
            "Africa/Kampala",
            "Africa/Nairobi",
            ("formats", "time_zone"),
        ),
        ("allow_hour12_override", "hour12", True, True, False, ("formats", "hour12")),
        ("allow_theme_override", "theme_mode", "dark", "dark", "light", ("theme_mode",)),
    ],
)
@pytest.mark.parametrize("allowed", [True, False])
def test_a_personal_override_counts_only_when_the_organization_allows_it(
    app_conn: Conn,
    owner_conn: Conn,
    clerk: Member,
    flag: str,
    column: str,
    stored: Any,
    when_allowed: Any,
    when_not_allowed: Any,
    read: tuple[str, ...],
    allowed: bool,
) -> None:
    set_localization(owner_conn, clerk.org, **{flag: allowed})
    _store_preferences(owner_conn, clerk, **{column: stored})
    value: Any = _appearance(app_conn, clerk)
    for key in read:
        value = value[key]
    assert value == (when_allowed if allowed else when_not_allowed)


def test_an_allowed_theme_without_a_personal_choice_follows_the_system(
    app_conn: Conn, owner_conn: Conn, clerk: Member
) -> None:
    assert _appearance(app_conn, clerk)["theme_mode"] == "system"
    set_localization(owner_conn, clerk.org, allow_theme_override=False)
    assert _appearance(app_conn, clerk)["theme_mode"] == "light"


def test_reduced_motion_and_font_scale_are_the_persons_own(
    app_conn: Conn, owner_conn: Conn, clerk: Member
) -> None:
    _store_preferences(owner_conn, clerk, reduced_motion=True, font_scale=2.0)
    appearance = _appearance(app_conn, clerk)
    assert (appearance["reduced_motion"], appearance["font_scale"]) == (True, 2.0)


@pytest.mark.parametrize(
    ("locale", "direction"),
    [
        ("ar-EG", "rtl"),
        ("AR", "rtl"),
        ("he-IL", "rtl"),
        ("fa-IR", "rtl"),
        ("ur-PK", "rtl"),
        ("en-GB", "ltr"),
        ("sw-KE", "ltr"),
    ],
)
def test_the_direction_follows_the_locale(
    app_conn: Conn, owner: Member, clerk: Member, locale: str, direction: str
) -> None:
    _save(app_conn, owner, "localization", {"locale": locale})
    assert _appearance(app_conn, clerk)["formats"]["direction"] == direction


def test_a_personal_locale_sets_the_direction(
    app_conn: Conn, owner_conn: Conn, clerk: Member
) -> None:
    _store_preferences(owner_conn, clerk, locale="ar-EG")
    formats = _appearance(app_conn, clerk)["formats"]
    assert (formats["locale"], formats["direction"]) == ("ar-EG", "rtl")


def test_the_logo_is_served_as_a_data_url(app_conn: Conn, owner: Member, clerk: Member) -> None:
    _upload(app_conn, owner, PNG_BYTES)
    expected = "data:image/png;base64," + base64.b64encode(PNG_BYTES).decode()
    assert _appearance(app_conn, clerk)["branding"]["logo"] == expected
    _remove_logo(app_conn, owner)
    assert _appearance(app_conn, clerk)["branding"]["logo"] is None


def test_a_large_logo_data_url_has_no_line_breaks(app_conn: Conn, owner: Member) -> None:
    _upload(app_conn, owner, _png(5000))
    logo = _appearance(app_conn, owner)["branding"]["logo"]
    assert "\n" not in logo
    assert base64.b64decode(logo.split(",", 1)[1]) == _png(5000)


def test_appearance_refuses_a_stored_time_zone_postgresql_does_not_know(
    app_conn: Conn, owner_conn: Conn, clerk: Member
) -> None:
    set_localization(owner_conn, clerk.org, time_zone="Mars/Olympus")
    args = [clerk.id, clerk.org, REQUEST, T0]
    error = refused(app_conn, "organization_appearance_get", args, "XC422", "time_zone_invalid")
    assert json.loads(error.diag.message_detail or "") == {"value": "Mars/Olympus"}


def test_appearance_refuses_a_personal_time_zone_postgresql_does_not_know(
    app_conn: Conn, owner_conn: Conn, clerk: Member
) -> None:
    _store_preferences(owner_conn, clerk, time_zone="Mars/Olympus")
    args = [clerk.id, clerk.org, REQUEST, T0]
    refused(app_conn, "organization_appearance_get", args, "XC422", "time_zone_invalid")


def test_appearance_refuses_a_stored_locale_that_no_longer_validates(
    app_conn: Conn, owner_conn: Conn, clerk: Member
) -> None:
    owner_conn.execute(
        "ALTER TABLE tenancy.organization_localizations DROP CONSTRAINT ck_localizations_locale"
    )
    set_localization(owner_conn, clerk.org, locale="not a locale")
    args = [clerk.id, clerk.org, REQUEST, T0]
    refused(app_conn, "organization_appearance_get", args, "XC422", "locale_invalid")


# --- preferences ---


def test_preferences_default_to_nothing_chosen(app_conn: Conn, clerk: Member) -> None:
    assert _preferences(app_conn, clerk) == {
        "organization_id": str(clerk.org),
        "user_id": str(clerk.id),
        "locale": None,
        "time_zone": None,
        "hour12": None,
        "theme_mode": None,
        "reduced_motion": False,
        "font_scale": 1,
        "allow_locale_override": True,
        "allow_time_zone_override": False,
        "allow_hour12_override": True,
        "allow_theme_override": True,
        "organization": {"locale": "en-GB", "time_zone": "Africa/Nairobi", "hour12": False},
    }


def test_preferences_serve_a_stored_value_only_while_its_override_is_allowed(
    app_conn: Conn, owner_conn: Conn, clerk: Member
) -> None:
    _store_preferences(
        owner_conn,
        clerk,
        locale="sw-KE",
        time_zone="Africa/Kampala",
        hour12=True,
        theme_mode="dark",
        reduced_motion=True,
        font_scale=2.0,
    )
    shown = _preferences(app_conn, clerk)
    assert (shown["locale"], shown["time_zone"], shown["hour12"], shown["theme_mode"]) == (
        "sw-KE",
        None,
        True,
        "dark",
    )
    set_localization(
        owner_conn,
        clerk.org,
        allow_locale_override=False,
        allow_time_zone_override=False,
        allow_hour12_override=False,
        allow_theme_override=False,
    )
    hidden = _preferences(app_conn, clerk)
    assert (hidden["locale"], hidden["time_zone"], hidden["hour12"], hidden["theme_mode"]) == (
        None,
        None,
        None,
        None,
    )
    assert (hidden["reduced_motion"], hidden["font_scale"]) == (True, 2.0)
    assert hidden["allow_locale_override"] is False
    assert hidden["organization"]["locale"] == "en-GB"


def test_preferences_show_the_organization_defaults(
    app_conn: Conn, owner: Member, clerk: Member
) -> None:
    _save(app_conn, owner, "localization", {"locale": "sw-KE", "time_zone": "UTC", "hour12": True})
    assert _preferences(app_conn, clerk)["organization"] == {
        "locale": "sw-KE",
        "time_zone": "UTC",
        "hour12": True,
    }


def test_saving_preferences_returns_the_saved_row(
    app_conn: Conn, owner_conn: Conn, clerk: Member
) -> None:
    set_localization(owner_conn, clerk.org, allow_time_zone_override=True)
    saved = _set_preferences(
        app_conn,
        clerk,
        locale="sw-KE",
        time_zone="Africa/Kampala",
        hour12=True,
        theme_mode="dark",
        reduced_motion=True,
        font_scale=1.5,
    )
    assert saved == {
        "organization_id": str(clerk.org),
        "user_id": str(clerk.id),
        "locale": "sw-KE",
        "time_zone": "Africa/Kampala",
        "hour12": True,
        "theme_mode": "dark",
        "reduced_motion": True,
        "font_scale": 1.5,
    }
    shown = _preferences(app_conn, clerk)
    assert (shown["locale"], shown["time_zone"], shown["font_scale"]) == (
        "sw-KE",
        "Africa/Kampala",
        1.5,
    )


def test_saving_null_overrides_clears_them(app_conn: Conn, owner_conn: Conn, clerk: Member) -> None:
    _set_preferences(app_conn, clerk, locale="sw-KE", hour12=True, theme_mode="dark")
    saved = _set_preferences(app_conn, clerk, reduced_motion=None)
    assert saved["locale"] is None
    assert saved["hour12"] is None
    assert saved["theme_mode"] is None
    assert saved["reduced_motion"] is False
    assert saved["font_scale"] == 1


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("locale", "sw-KE", "preferences_locale_not_allowed"),
        ("time_zone", "Africa/Kampala", "preferences_time_zone_not_allowed"),
        ("hour12", True, "preferences_hour12_not_allowed"),
        ("theme_mode", "dark", "preferences_theme_not_allowed"),
    ],
)
def test_an_override_the_organization_does_not_allow_is_refused(
    app_conn: Conn, owner_conn: Conn, clerk: Member, field: str, value: Any, code: str
) -> None:
    set_localization(
        owner_conn,
        clerk.org,
        allow_locale_override=False,
        allow_time_zone_override=False,
        allow_hour12_override=False,
        allow_theme_override=False,
    )
    _set_preferences_refused(app_conn, clerk, code, **{field: value})


def test_a_refused_save_leaves_the_stored_preferences_alone(
    app_conn: Conn, owner_conn: Conn, clerk: Member
) -> None:
    _set_preferences(app_conn, clerk, locale="sw-KE")
    _set_preferences_refused(
        app_conn, clerk, "preferences_time_zone_not_allowed", time_zone="Africa/Kampala"
    )
    assert _preferences(app_conn, clerk)["locale"] == "sw-KE"


@pytest.mark.parametrize("scale", [0.0, 0.99, 3.01, 3.5, float("nan"), float("inf"), None])
def test_the_font_scale_must_lie_between_one_and_three(
    app_conn: Conn, clerk: Member, scale: float | None
) -> None:
    _set_preferences_refused(app_conn, clerk, "preferences_accessibility", font_scale=scale)


@pytest.mark.parametrize("scale", [1.0, 2.25, 3.0])
def test_the_font_scale_accepts_its_bounds(app_conn: Conn, clerk: Member, scale: float) -> None:
    assert _set_preferences(app_conn, clerk, font_scale=scale)["font_scale"] == scale


@pytest.mark.parametrize("theme", ["blue", "", "Dark"])
def test_the_theme_must_be_light_dark_or_system(app_conn: Conn, clerk: Member, theme: str) -> None:
    _set_preferences_refused(app_conn, clerk, "preferences_accessibility", theme_mode=theme)


@pytest.mark.parametrize("theme", ["light", "dark", "system"])
def test_the_three_themes_are_accepted(app_conn: Conn, clerk: Member, theme: str) -> None:
    assert _set_preferences(app_conn, clerk, theme_mode=theme)["theme_mode"] == theme


@pytest.mark.parametrize("locale", ["english", "e", "en_GB", ""])
def test_a_personal_locale_must_be_a_bcp_47_tag(app_conn: Conn, clerk: Member, locale: str) -> None:
    _set_preferences_refused(app_conn, clerk, "locale_invalid", locale=locale)


def test_a_personal_time_zone_must_be_one_postgresql_knows(
    app_conn: Conn, owner_conn: Conn, clerk: Member
) -> None:
    set_localization(owner_conn, clerk.org, allow_time_zone_override=True)
    error = _set_preferences_refused(app_conn, clerk, "time_zone_invalid", time_zone="Mars/Olympus")
    assert json.loads(error.diag.message_detail or "") == {"value": "Mars/Olympus"}


def test_preference_checks_run_in_order(app_conn: Conn, owner_conn: Conn, clerk: Member) -> None:
    set_localization(
        owner_conn, clerk.org, allow_time_zone_override=False, allow_theme_override=False
    )
    _set_preferences_refused(
        app_conn, clerk, "locale_invalid", locale="english", time_zone="Mars/Olympus"
    )
    _set_preferences_refused(
        app_conn, clerk, "time_zone_invalid", time_zone="Mars/Olympus", theme_mode="blue"
    )
    _set_preferences_refused(
        app_conn,
        clerk,
        "preferences_accessibility",
        theme_mode="blue",
        time_zone="Africa/Kampala",
    )
    _set_preferences_refused(
        app_conn,
        clerk,
        "preferences_time_zone_not_allowed",
        time_zone="Africa/Kampala",
        theme_mode="dark",
    )


def test_saving_preferences_writes_no_change_log_and_leaves_the_version_alone(
    app_conn: Conn, owner_conn: Conn, clerk: Member
) -> None:
    version = settings_version(owner_conn, clerk.org)
    _set_preferences(app_conn, clerk, locale="sw-KE", hour12=True, theme_mode="dark")
    _set_preferences(app_conn, clerk, locale="en-US", font_scale=2.0)
    assert change_log(owner_conn, clerk.org) == []
    assert audit_events(owner_conn, clerk.org) == []
    assert settings_version(owner_conn, clerk.org) == version


def test_every_member_keeps_their_own_preferences(
    app_conn: Conn, owner: Member, clerk: Member
) -> None:
    _set_preferences(app_conn, clerk, locale="sw-KE")
    assert _preferences(app_conn, owner)["locale"] is None
    assert _preferences(app_conn, clerk)["locale"] == "sw-KE"


# --- tenant isolation ---


@pytest.mark.parametrize(
    ("routine", "extra"),
    [
        ("organization_settings_get", []),
        ("organization_settings_set", ["localization", Jsonb({}), None, None]),
        ("organization_logo_set", ["image/png", PNG_BYTES, None]),
        ("organization_logo_delete", [None]),
        ("organization_appearance_get", []),
        ("preferences_get", []),
        ("preferences_set", [None, None, None, None, False, 1.0]),
    ],
)
def test_an_actor_of_another_organization_is_not_a_member(
    app_conn: Conn, owner_conn: Conn, owner: Member, routine: str, extra: list[Any]
) -> None:
    other = seed_organization(owner_conn)
    refused(app_conn, routine, [other.user, owner.org, REQUEST, *extra, T0], "XC403", "not_member")
