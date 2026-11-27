"""The system settings routines (``api.setup_settings_get`` and ``api.setup_settings_set``),
called as ``xcode_app``: the settings with their state, a switch for the whole organization
logged once as "Setting, Targets, On to Off", a switch to the state already held changing
nothing, the refusals, ``settings.edit`` alone opening both, and a setting of another
organization never read. What Targets off does to vehicles, revenue and reports is tested with
those routines."""

from __future__ import annotations

import json
from datetime import timedelta
from typing import Any

import pytest

from ..support.rows import seed_organization
from ..support.scenario import T0, Conn, call
from ..support.tenancy import (
    REQUEST,
    Member,
    audit_events,
    change_log,
    provision_member,
    refused,
    set_override,
    set_system_setting,
    settings_version,
)

ON = {"settings": [{"key": "targets", "label": "Targets", "on": True}]}
OFF = {"settings": [{"key": "targets", "label": "Targets", "on": False}]}


@pytest.fixture
def owner(operator_conn: Conn) -> Member:
    return provision_member(operator_conn, 1, "Owner", "Olive", "Owner")


@pytest.fixture
def clerk(operator_conn: Conn, owner: Member) -> Member:
    return provision_member(operator_conn, 2, "Revenue clerk", "Cleo", "Clerk")


def _get(app: Conn, who: Member) -> dict[str, Any]:
    result: dict[str, Any] = call(app, "setup_settings_get", who.id, who.org, REQUEST)
    return result


def _set(app: Conn, who: Member, key: Any, on: Any, *, now: Any = T0) -> dict[str, Any]:
    result: dict[str, Any] = call(app, "setup_settings_set", who.id, who.org, REQUEST, key, on, now)
    return result


def _appearance(app: Conn, who: Member) -> dict[str, Any]:
    result: dict[str, Any] = call(app, "organization_appearance_get", who.id, who.org, REQUEST, T0)
    return result


def test_targets_is_on_until_switched_off(app_conn: Conn, owner: Member) -> None:
    assert _get(app_conn, owner) == ON
    assert _appearance(app_conn, owner)["targets"] is True


def test_a_switch_is_stored_logged_and_served(
    app_conn: Conn, owner_conn: Conn, owner: Member, clerk: Member
) -> None:
    before = settings_version(owner_conn, owner.org)
    assert _set(app_conn, owner, "targets", False) == OFF
    assert _get(app_conn, owner) == OFF
    assert _appearance(app_conn, clerk)["targets"] is False
    (log,) = change_log(owner_conn, owner.org)
    assert (log["section"], log["entity_id"], log["reason"]) == (
        "organization",
        owner.org,
        "Setting, Targets, On to Off",
    )
    assert (json.loads(log["before"]), json.loads(log["after"])) == (
        {"Targets": "On"},
        {"Targets": "Off"},
    )
    assert settings_version(owner_conn, owner.org) == before + 1
    (audit,) = audit_events(owner_conn, owner.org, "organization.settings.updated")
    assert (audit["entity"], audit["before"], audit["after"]) == (
        "system_settings",
        {"key": "targets", "on": True},
        {"key": "targets", "on": False},
    )

    assert _set(app_conn, owner, "targets", True, now=T0 + timedelta(minutes=1)) == ON
    assert [r["reason"] for r in change_log(owner_conn, owner.org)] == [
        "Setting, Targets, On to Off",
        "Setting, Targets, Off to On",
    ]
    stored = owner_conn.execute(
        "SELECT enabled, created_at, updated_at FROM tenancy.organization_system_settings "
        "WHERE organization_id = %s",
        (owner.org,),
    ).fetchall()
    assert stored == [{"enabled": True, "created_at": T0, "updated_at": T0 + timedelta(minutes=1)}]


def test_switching_to_the_state_held_changes_and_logs_nothing(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    before = settings_version(owner_conn, owner.org)
    assert _set(app_conn, owner, "targets", True) == ON
    assert change_log(owner_conn, owner.org) == []
    assert settings_version(owner_conn, owner.org) == before
    assert owner_conn.execute(
        "SELECT count(*) AS n FROM tenancy.organization_system_settings WHERE organization_id = %s",
        (owner.org,),
    ).fetchone() == {"n": 0}


def test_an_unknown_setting_is_not_found_and_a_missing_state_is_refused(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    base = [owner.id, owner.org, REQUEST]
    refused(app_conn, "setup_settings_set", [*base, "budget", True, T0], "XC404", "not_found")
    refused(app_conn, "setup_settings_set", [*base, None, True, T0], "XC404", "not_found")
    refused(
        app_conn,
        "setup_settings_set",
        [*base, "targets", None, T0],
        "XC422",
        "setting_state_required",
    )
    assert change_log(owner_conn, owner.org) == []


def test_settings_edit_alone_opens_the_settings(
    app_conn: Conn, owner_conn: Conn, operator_conn: Conn, clerk: Member
) -> None:
    get_args = [clerk.id, clerk.org, REQUEST]
    set_args = [*get_args, "targets", False, T0]
    refused(app_conn, "setup_settings_get", get_args, "XC403", "permission_missing")
    refused(app_conn, "setup_settings_set", set_args, "XC403", "permission_missing")
    office = provision_member(operator_conn, 3, "Office admin", "Otto", "Office")
    set_override(owner_conn, office, "organization.manage")
    refused(
        app_conn,
        "setup_settings_set",
        [office.id, office.org, REQUEST, "targets", False, T0],
        "XC403",
        "permission_missing",
    )
    set_override(owner_conn, clerk, "settings.edit")
    assert _get(app_conn, clerk) == ON
    assert _set(app_conn, clerk, "targets", False) == OFF


def test_an_actor_of_another_organization_is_not_a_member(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    other = seed_organization(owner_conn)
    refused(app_conn, "setup_settings_get", [other.user, owner.org, REQUEST], "XC403", "not_member")
    refused(
        app_conn,
        "setup_settings_set",
        [other.user, owner.org, REQUEST, "targets", False, T0],
        "XC403",
        "not_member",
    )


def test_another_organization_switching_off_leaves_this_one_on(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    other = seed_organization(owner_conn)
    set_system_setting(owner_conn, other.org, "targets", on=False)
    assert _get(app_conn, owner) == ON
    assert _appearance(app_conn, owner)["targets"] is True
