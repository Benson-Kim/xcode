"""The custom role routines (``api.access_role_create``, ``api.access_role_update``,
``api.access_role_delete``, and ``api.access_role_list`` for what they answer), called as
``xcode_app``.

Each refusal leaves the role as it was. A saved role stores its permissions with their
dependencies expanded, logs one roles change and one audit event, and a change of name or
permissions ends the sessions of everyone holding it. A custom role given to a person decides
what that person may do. Two writers at once never both win, and never surface a foreign key
error. The structure test holds the grants and the row-level security the routines rely on."""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any
from uuid import UUID

import psycopg
import pytest
from psycopg.rows import dict_row

from ..support.rows import seed_organization
from ..support.scenario import T0, Conn, call, user_row
from ..support.tenancy import (
    REQUEST,
    Member,
    audit_events,
    change_log,
    create_person,
    create_refused,
    membership,
    provision_member,
    refused,
    settings_version,
    update_refused,
    write,
)

_SUPPORT = Path(__file__).resolve().parent.parent / "support"
_CATALOGUE = json.loads((_SUPPORT / "permission_catalogue.json").read_text(encoding="utf-8"))
_ITEMS = [item for group in _CATALOGUE["groups"] for item in group["items"]]
_ORDER = [item["key"] for item in _ITEMS]
_NEEDS = {item["key"]: item["needs"] for item in _ITEMS}

BUILT_IN = ["Fleet manager", "Office admin", "Owner", "Revenue clerk"]
# The Office admin holds the expense rights but not revenue.capture.
CASHIER = ["expenses.capture"]
DRIVER = ["revenue.capture"]
UNKNOWN = UUID("00000000-0000-4000-8000-000000000000")


def _expand(keys: list[str]) -> list[str]:
    seen: set[str] = set()
    pending = list(keys)
    while pending:
        key = pending.pop()
        if key not in seen:
            seen.add(key)
            pending.extend(_NEEDS[key])
    return [key for key in _ORDER if key in seen]


def _json(value: Any) -> Any:
    return json.loads(value) if isinstance(value, str) else value


def _create(conn: Conn, actor: Member, name: str | None, permissions: Any) -> dict[str, Any]:
    document: dict[str, Any] = call(
        conn, "access_role_create", actor.id, actor.org, REQUEST, name, permissions, T0
    )
    return document


def _create_refused(
    conn: Conn, actor: Member, name: str | None, permissions: Any, sqlstate: str, code: str
) -> psycopg.Error:
    args = [actor.id, actor.org, REQUEST, name, permissions, T0]
    return refused(conn, "access_role_create", args, sqlstate, code)


def _update(
    conn: Conn,
    actor: Member,
    role: Any,
    name: str | None,
    permissions: Any,
    version: int | None,
) -> dict[str, Any]:
    document: dict[str, Any] = call(
        conn,
        "access_role_update",
        actor.id,
        actor.org,
        REQUEST,
        role,
        name,
        permissions,
        version,
        T0,
    )
    return document


def _update_refused(
    conn: Conn,
    actor: Member,
    role: Any,
    name: str | None,
    permissions: Any,
    version: int | None,
    sqlstate: str,
    code: str,
) -> psycopg.Error:
    args = [actor.id, actor.org, REQUEST, role, name, permissions, version, T0]
    return refused(conn, "access_role_update", args, sqlstate, code)


def _delete(conn: Conn, actor: Member, role: Any) -> dict[str, Any]:
    return write(conn, "access_role_delete", actor.id, actor.org, REQUEST, role, T0)


def _delete_refused(
    conn: Conn, actor: Member, role: Any, sqlstate: str, code: str
) -> psycopg.Error:
    return refused(
        conn, "access_role_delete", [actor.id, actor.org, REQUEST, role, T0], sqlstate, code
    )


def _list(conn: Conn, actor: Member) -> list[dict[str, Any]]:
    roles: list[dict[str, Any]] = call(conn, "access_role_list", actor.id, actor.org, REQUEST, T0)
    return roles


def _role_id(document: dict[str, Any]) -> UUID:
    return UUID(document["id"])


def _built_in_id(conn: Conn, actor: Member, name: str) -> UUID:
    return next(_role_id(r) for r in _list(conn, actor) if r["name"] == name)


def _role_row(owner_conn: Conn, role: UUID) -> dict[str, Any] | None:
    row: dict[str, Any] | None = owner_conn.execute(
        "SELECT * FROM tenancy.roles WHERE id = %s", (role,)
    ).fetchone()
    return row


def _grants(owner_conn: Conn, role: UUID) -> set[str]:
    rows = owner_conn.execute(
        "SELECT permission FROM tenancy.role_grants WHERE role_id = %s", (role,)
    ).fetchall()
    return {str(r["permission"]) for r in rows}


def _roles_log(owner_conn: Conn, org: UUID) -> list[dict[str, Any]]:
    return [r for r in change_log(owner_conn, org) if r["section"] == "roles"]


def _security(owner_conn: Conn, user: UUID) -> int:
    return int(user_row(owner_conn, user)["security_version"])


def _give(conn: Conn, actor: Member, role: str, keys: list[str], slot: int = 0) -> UUID:
    person = create_person(
        conn,
        actor,
        first_name=("Amani", "Baraka", "Chege", "Dalia")[slot],
        email=f"person{slot}@example.com",
        phone=f"0722{slot:06d}",
        role=role,
        permissions=keys,
    )
    return UUID(str(person["id"]))


def _role_of(conn: Conn, actor: Member, user: UUID) -> str:
    return str(call(conn, "people_get", actor.id, actor.org, REQUEST, user, T0)["role"])


def _held(executor: Conn, org: UUID, user: UUID) -> tuple[list[str], list[str]]:
    with executor.transaction():
        executor.execute("SELECT set_config('xcode.organization_id', %s, true)", (str(org),))
        row = executor.execute(
            "SELECT tenancy.assigned_permissions(%s, %s) AS assigned, "
            "tenancy.effective_permissions(%s, %s) AS effective",
            (org, user, org, user),
        ).fetchone()
    assert row is not None
    return list(row["assigned"]), list(row["effective"])


def _race(
    app_url: str, first: Callable[[Conn], Any], late: Callable[[Conn], Any]
) -> tuple[Any, Any]:
    """Runs ``late`` on a second connection while ``first`` holds its transaction open."""
    results: list[Any] = []
    with (
        psycopg.connect(app_url, autocommit=True, row_factory=dict_row) as one,
        psycopg.connect(app_url, autocommit=True, row_factory=dict_row) as two,
    ):

        def run_late() -> None:
            try:
                results.append(late(two))
            except psycopg.Error as error:
                results.append((error.sqlstate, error.diag.message_primary))

        with one.transaction():
            done = first(one)
            worker = threading.Thread(target=run_late)
            worker.start()
            worker.join(0.5)
            # The late call waits on a lock the first one holds until it commits.
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
    return provision_member(operator_conn, 4, "Revenue clerk", "Cleo", "Clerk")


# --- create ------------------------------------------------------------------------------


def test_a_created_role_stores_its_expanded_permissions_at_version_one(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    start = settings_version(owner_conn, owner.org)
    document = _create(app_conn, owner, "  Driver  ", DRIVER)
    role = _role_id(document)
    assert document == {
        "id": str(role),
        "name": "Driver",
        "permissions": _expand(DRIVER),
        "built_in": False,
        "version": 1,
    }
    assert _grants(owner_conn, role) == set(_expand(DRIVER))
    row = _role_row(owner_conn, role)
    assert row is not None
    assert (row["built_in"], row["version"]) == (False, 1)
    assert settings_version(owner_conn, owner.org) == start + 1


def test_a_created_role_is_logged_and_audited(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    role = _role_id(_create(app_conn, owner, "Driver", DRIVER))
    after = {"Name": "Driver", "Permissions": _expand(DRIVER)}
    [entry] = _roles_log(owner_conn, owner.org)
    assert (entry["entity_id"], entry["reason"]) == (role, "Added role Driver")
    assert _json(entry["before"]) is None
    assert _json(entry["after"]) == after
    [event] = audit_events(owner_conn, owner.org, "role.created")
    assert (event["entity"], event["actor_id"]) == (str(role), owner.id)
    assert (event["before"], event["after"]) == (None, after)


def test_a_name_of_one_hundred_characters_is_kept(app_conn: Conn, owner: Member) -> None:
    assert _create(app_conn, owner, "x" * 100, DRIVER)["name"] == "x" * 100


@pytest.mark.parametrize("name", [None, "", "   ", "x" * 101])
def test_a_missing_blank_or_long_name_is_invalid(
    app_conn: Conn, owner_conn: Conn, owner: Member, name: str | None
) -> None:
    _create_refused(app_conn, owner, name, DRIVER, "XC422", "role_name_invalid")
    assert _roles_log(owner_conn, owner.org) == []


@pytest.mark.parametrize(
    "permissions",
    [None, [], [None], ["revenue.view", None], ["revenue.view", "revenue.view"]],
    ids=["null", "empty", "null-element", "null-among-keys", "duplicate"],
)
def test_missing_empty_null_or_repeated_permissions_are_invalid(
    app_conn: Conn, owner: Member, permissions: Any
) -> None:
    _create_refused(app_conn, owner, "Driver", permissions, "XC422", "role_permissions_invalid")


@pytest.mark.parametrize("key", ["organization.manage", "people.manage", "access.manage", "nope"])
def test_a_key_outside_the_catalogue_is_unknown(app_conn: Conn, owner: Member, key: str) -> None:
    _create_refused(
        app_conn, owner, "Driver", ["revenue.view", key], "XC422", "role_permission_unknown"
    )


@pytest.mark.parametrize("name", ["Owner", "owner", "OFFICE ADMIN", " Revenue clerk "])
def test_the_name_of_a_built_in_role_is_taken(app_conn: Conn, owner: Member, name: str) -> None:
    _create_refused(app_conn, owner, name, DRIVER, "XC422", "role_name_taken")


def test_the_name_of_another_role_is_taken_ignoring_case(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    _create(app_conn, owner, "Driver", DRIVER)
    _create_refused(app_conn, owner, "DRIVER", CASHIER, "XC422", "role_name_taken")
    assert len(_roles_log(owner_conn, owner.org)) == 1


def test_another_organizations_role_name_is_free(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    other = seed_organization(owner_conn)
    owner_conn.execute(
        "INSERT INTO tenancy.roles (organization_id, name) VALUES (%s, 'Driver')", (other.org,)
    )
    assert _create(app_conn, owner, "Driver", DRIVER)["name"] == "Driver"


def test_an_office_admin_cannot_create_a_role_with_a_permission_they_lack(
    app_conn: Conn, owner_conn: Conn, office: Member
) -> None:
    _create_refused(app_conn, office, "Driver", DRIVER, "XC422", "role_permission_not_held")
    _create_refused(
        app_conn, office, "Mixed", [*CASHIER, *DRIVER], "XC422", "role_permission_not_held"
    )
    assert _roles_log(owner_conn, office.org) == []


def test_an_office_admin_creates_a_role_within_what_they_hold(
    app_conn: Conn, office: Member
) -> None:
    assert _create(app_conn, office, "Cashier", CASHIER)["permissions"] == _expand(CASHIER)


@pytest.mark.parametrize(
    ("name", "permissions", "code"),
    [
        ("   ", [], "role_name_invalid"),
        ("Owner", [], "role_permissions_invalid"),
        ("Owner", ["organization.manage"], "role_permission_unknown"),
    ],
)
def test_create_refusals_come_in_the_contract_order(
    app_conn: Conn, office: Member, name: str, permissions: list[str], code: str
) -> None:
    _create_refused(app_conn, office, name, permissions, "XC422", code)


def test_a_taken_name_is_refused_before_permissions_not_held(
    app_conn: Conn, office: Member
) -> None:
    _create_refused(app_conn, office, "Owner", DRIVER, "XC422", "role_name_taken")


# --- update ------------------------------------------------------------------------------


def test_a_change_of_name_and_permissions_bumps_the_version_and_replaces_the_grants(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    role = _role_id(_create(app_conn, owner, "Driver", DRIVER))
    keys = [*DRIVER, "revenue.correct"]
    document = _update(app_conn, owner, role, "Courier", keys, 1)
    assert document == {
        "id": str(role),
        "name": "Courier",
        "permissions": _expand(keys),
        "built_in": False,
        "version": 2,
    }
    assert _grants(owner_conn, role) == set(_expand(keys))
    entry = _roles_log(owner_conn, owner.org)[-1]
    assert (entry["entity_id"], entry["reason"]) == (
        role,
        "Changed name and permissions of role Courier",
    )
    before = {"Name": "Driver", "Permissions": _expand(DRIVER)}
    after = {"Name": "Courier", "Permissions": _expand(keys)}
    assert (_json(entry["before"]), _json(entry["after"])) == (before, after)
    [event] = audit_events(owner_conn, owner.org, "role.updated")
    assert (event["entity"], event["before"], event["after"]) == (str(role), before, after)


def test_a_change_of_permissions_alone_is_logged_as_such(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    role = _role_id(_create(app_conn, owner, "Driver", DRIVER))
    _update(app_conn, owner, role, "Driver", [*DRIVER, "revenue.correct"], 1)
    assert _roles_log(owner_conn, owner.org)[-1]["reason"] == "Changed permissions of role Driver"


def test_a_role_may_be_renamed_to_itself_in_another_case(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    role = _role_id(_create(app_conn, owner, "Driver", DRIVER))
    document = _update(app_conn, owner, role, "DRIVER", DRIVER, 1)
    assert (document["name"], document["version"]) == ("DRIVER", 2)
    assert _roles_log(owner_conn, owner.org)[-1]["reason"] == "Changed name of role DRIVER"


def test_the_same_name_and_permissions_answer_the_role_unchanged(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    created = _create(app_conn, owner, "Driver", DRIVER)
    role = _role_id(created)
    holder = _give(app_conn, owner, "Driver", _expand(DRIVER))
    security = _security(owner_conn, holder)
    logged = len(change_log(owner_conn, owner.org))
    assert _update(app_conn, owner, role, " Driver ", _expand(DRIVER), 1) == created
    assert len(change_log(owner_conn, owner.org)) == logged
    assert _security(owner_conn, holder) == security
    assert audit_events(owner_conn, owner.org, "role.updated") == []


def test_a_change_ends_the_sessions_of_holders_only(
    app_conn: Conn, owner_conn: Conn, owner: Member, office: Member
) -> None:
    role = _role_id(_create(app_conn, owner, "Driver", DRIVER))
    first = _give(app_conn, owner, "Driver", _expand(DRIVER), 1)
    second = _give(app_conn, owner, "driver", _expand(DRIVER), 2)
    other = _give(app_conn, owner, "Revenue clerk", ["dash.gaps", *_expand(DRIVER)], 3)
    before = {u: _security(owner_conn, u) for u in (first, second, other, office.id, owner.id)}
    _update(app_conn, owner, role, "Driver", [*DRIVER, "revenue.correct"], 1)
    after = {u: _security(owner_conn, u) for u in before}
    assert {u: after[u] - before[u] for u in before} == {
        first: 1,
        second: 1,
        other: 0,
        office.id: 0,
        owner.id: 0,
    }


def test_a_change_moves_holders_memberships_so_a_person_edit_opened_before_it_conflicts(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    role = _role_id(_create(app_conn, owner, "Driver", DRIVER))
    holder = _give(app_conn, owner, "Driver", _expand(DRIVER), 1)
    other = _give(app_conn, owner, "Revenue clerk", ["dash.gaps", *_expand(DRIVER)], 2)
    seen = int(membership(owner_conn, owner.org, holder)["version"])
    untouched = int(membership(owner_conn, owner.org, other)["version"])
    _update(app_conn, owner, role, "Driver", [*DRIVER, "revenue.correct"], 1)
    assert membership(owner_conn, owner.org, holder)["version"] == seen + 1
    assert membership(owner_conn, owner.org, other)["version"] == untouched
    update_refused(
        app_conn,
        owner,
        holder,
        seen,
        "XC409",
        "version_conflict",
        first_name="Baraka",
        email="person1@example.com",
        phone="0722000001",
        role="Driver",
        permissions=_expand(DRIVER),
    )


@pytest.mark.parametrize("which", ["unknown", "null", "other-organization"])
def test_a_role_this_organization_lacks_is_not_found(
    app_conn: Conn, owner_conn: Conn, owner: Member, which: str
) -> None:
    other = seed_organization(owner_conn)
    foreign = owner_conn.execute(
        "INSERT INTO tenancy.roles (organization_id, name) VALUES (%s, 'Driver') RETURNING id",
        (other.org,),
    ).fetchone()
    assert foreign is not None
    role = {"unknown": UNKNOWN, "null": None, "other-organization": foreign["id"]}[which]
    _update_refused(app_conn, owner, role, "Driver", DRIVER, 1, "XC404", "not_found")
    _delete_refused(app_conn, owner, role, "XC404", "not_found")
    row = _role_row(owner_conn, foreign["id"])
    assert row is not None
    assert (row["name"], row["version"]) == ("Driver", 1)


@pytest.mark.parametrize("name", BUILT_IN)
def test_a_built_in_role_is_neither_changed_nor_deleted(
    app_conn: Conn, owner_conn: Conn, owner: Member, name: str
) -> None:
    role = _built_in_id(app_conn, owner, name)
    _update_refused(app_conn, owner, role, "Renamed", DRIVER, 1, "XC422", "role_built_in")
    _delete_refused(app_conn, owner, role, "XC422", "role_built_in")
    row = _role_row(owner_conn, role)
    assert row is not None
    assert (row["name"], row["version"]) == (name, 1)


@pytest.mark.parametrize("version", [None, 2, 0])
def test_a_missing_or_stale_version_conflicts(
    app_conn: Conn, owner_conn: Conn, owner: Member, version: int | None
) -> None:
    role = _role_id(_create(app_conn, owner, "Driver", DRIVER))
    _update_refused(app_conn, owner, role, "Courier", DRIVER, version, "XC409", "version_conflict")
    row = _role_row(owner_conn, role)
    assert row is not None
    assert (row["name"], row["version"]) == ("Driver", 1)


def test_an_edit_at_the_old_version_after_a_change_conflicts(app_conn: Conn, owner: Member) -> None:
    role = _role_id(_create(app_conn, owner, "Driver", DRIVER))
    _update(app_conn, owner, role, "Courier", DRIVER, 1)
    _update_refused(app_conn, owner, role, "Rider", DRIVER, 1, "XC409", "version_conflict")


def test_an_office_admin_cannot_change_a_role_holding_a_permission_they_lack(
    app_conn: Conn, owner_conn: Conn, owner: Member, office: Member
) -> None:
    role = _role_id(_create(app_conn, owner, "Driver", DRIVER))
    _update_refused(app_conn, office, role, "Driver", CASHIER, 1, "XC422", "role_not_held")
    assert _grants(owner_conn, role) == set(_expand(DRIVER))


def test_an_office_admin_cannot_add_a_permission_they_lack(
    app_conn: Conn, owner_conn: Conn, office: Member
) -> None:
    role = _role_id(_create(app_conn, office, "Cashier", CASHIER))
    _update_refused(
        app_conn,
        office,
        role,
        "Cashier",
        [*CASHIER, *DRIVER],
        1,
        "XC422",
        "role_permission_not_held",
    )
    assert _grants(owner_conn, role) == set(_expand(CASHIER))


def test_renaming_to_another_roles_name_is_taken(app_conn: Conn, owner: Member) -> None:
    _create(app_conn, owner, "Driver", DRIVER)
    role = _role_id(_create(app_conn, owner, "Cashier", CASHIER))
    _update_refused(app_conn, owner, role, "driver", CASHIER, 1, "XC422", "role_name_taken")
    _update_refused(app_conn, owner, role, "Owner", CASHIER, 1, "XC422", "role_name_taken")


@pytest.mark.parametrize(
    ("name", "permissions", "version", "sqlstate", "code"),
    [
        ("", DRIVER, 9, "XC422", "role_name_invalid"),
        ("Courier", ["nope"], 9, "XC422", "role_permission_unknown"),
        ("Owner", [], 9, "XC422", "role_permissions_invalid"),
        ("Owner", DRIVER, 9, "XC409", "version_conflict"),
    ],
)
def test_update_refusals_come_in_the_contract_order(
    app_conn: Conn,
    owner: Member,
    name: str,
    permissions: list[str],
    version: int,
    sqlstate: str,
    code: str,
) -> None:
    role = _role_id(_create(app_conn, owner, "Driver", DRIVER))
    _update_refused(app_conn, owner, role, name, permissions, version, sqlstate, code)


# --- a custom role decides what its holders may do -----------------------------------------


def test_a_custom_role_gives_its_holder_its_permissions_and_the_retired_keys_they_source(
    app_conn: Conn, owner_conn: Conn, executor: Conn, owner: Member
) -> None:
    role = _role_id(_create(app_conn, owner, "Driver", DRIVER))
    holder = _give(app_conn, owner, "driver", _expand(DRIVER))
    retired = ["revenue.no_earnings"]
    assert _held(executor, owner.org, holder) == (_expand(DRIVER), [*_expand(DRIVER), *retired])
    keys = [*DRIVER, "revenue.correct"]
    _update(app_conn, owner, role, "Driver", keys, 1)
    assert _held(executor, owner.org, holder) == (_expand(keys), [*_expand(keys), *retired])


def test_a_non_owner_gives_a_custom_role_only_when_holding_all_of_it(
    app_conn: Conn, owner: Member, office: Member
) -> None:
    _create(app_conn, owner, "Driver", DRIVER)
    _create(app_conn, office, "Cashier", CASHIER)
    create_refused(
        app_conn,
        office,
        "XC403",
        "people_role_not_held",
        role="Driver",
        permissions=_expand(DRIVER),
    )
    holder = _give(app_conn, office, "Cashier", _expand(CASHIER))
    assert _role_of(app_conn, owner, holder) == "Cashier"


def test_a_deleted_role_cannot_be_given(app_conn: Conn, owner: Member) -> None:
    role = _role_id(_create(app_conn, owner, "Driver", DRIVER))
    _delete(app_conn, owner, role)
    create_refused(
        app_conn, owner, "XC422", "people_role_unknown", role="Driver", permissions=_expand(DRIVER)
    )


# --- delete ------------------------------------------------------------------------------


def test_a_role_nobody_holds_is_deleted_with_its_grants_and_logged(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    role = _role_id(_create(app_conn, owner, "Driver", DRIVER))
    start = settings_version(owner_conn, owner.org)
    result = _delete(app_conn, owner, role)
    assert (result["id"], result["outcome"]) == (role, "updated")
    assert _role_row(owner_conn, role) is None
    assert _grants(owner_conn, role) == set()
    before = {"Name": "Driver", "Permissions": _expand(DRIVER)}
    entry = _roles_log(owner_conn, owner.org)[-1]
    assert (entry["entity_id"], entry["reason"]) == (role, "Deleted role Driver")
    assert (_json(entry["before"]), _json(entry["after"])) == (before, None)
    [event] = audit_events(owner_conn, owner.org, "role.deleted")
    assert (event["entity"], event["before"], event["after"]) == (str(role), before, None)
    assert settings_version(owner_conn, owner.org) == start + 1
    assert [r["name"] for r in _list(app_conn, owner)] == BUILT_IN


@pytest.mark.parametrize(("holders", "people"), [(1, "1 person"), (3, "3 people")])
def test_a_held_role_is_in_use_and_stays(
    app_conn: Conn, owner_conn: Conn, owner: Member, holders: int, people: str
) -> None:
    role = _role_id(_create(app_conn, owner, "Driver", DRIVER))
    for slot in range(holders):
        _give(app_conn, owner, "Driver", _expand(DRIVER), slot)
    logged = len(change_log(owner_conn, owner.org))
    error = _delete_refused(app_conn, owner, role, "XC409", "in_use")
    assert json.loads(error.diag.message_detail or "{}") == {
        "name": "Driver",
        "use": "role_people",
        "people": people,
    }
    assert _role_row(owner_conn, role) is not None
    assert _grants(owner_conn, role) == set(_expand(DRIVER))
    assert len(change_log(owner_conn, owner.org)) == logged


def test_a_blocked_holder_still_holds_the_role(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    role = _role_id(_create(app_conn, owner, "Driver", DRIVER))
    holder = _give(app_conn, owner, "Driver", _expand(DRIVER))
    write(app_conn, "people_set_active", owner.id, owner.org, REQUEST, holder, False, 1, "Left", T0)
    error = _delete_refused(app_conn, owner, role, "XC409", "in_use")
    assert json.loads(error.diag.message_detail or "{}")["people"] == "1 person"
    assert _role_row(owner_conn, role) is not None


def test_an_office_admin_cannot_delete_a_role_holding_a_permission_they_lack(
    app_conn: Conn, owner_conn: Conn, owner: Member, office: Member
) -> None:
    role = _role_id(_create(app_conn, owner, "Driver", DRIVER))
    _delete_refused(app_conn, office, role, "XC422", "role_not_held")
    assert _role_row(owner_conn, role) is not None


def test_an_office_admin_deletes_a_role_within_what_they_hold(
    app_conn: Conn, owner_conn: Conn, office: Member
) -> None:
    role = _role_id(_create(app_conn, office, "Cashier", CASHIER))
    _delete(app_conn, office, role)
    assert _role_row(owner_conn, role) is None


# --- who may call ------------------------------------------------------------------------


def test_without_access_manage_every_role_write_is_refused(
    app_conn: Conn, owner_conn: Conn, owner: Member, clerk: Member
) -> None:
    role = _role_id(_create(app_conn, owner, "Driver", DRIVER))
    _create_refused(app_conn, clerk, "Rider", DRIVER, "XC403", "permission_missing")
    _update_refused(app_conn, clerk, role, "Rider", DRIVER, 1, "XC403", "permission_missing")
    _delete_refused(app_conn, clerk, role, "XC403", "permission_missing")
    assert len(_roles_log(owner_conn, owner.org)) == 1


def test_someone_outside_the_organization_is_not_a_member(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    role = _role_id(_create(app_conn, owner, "Driver", DRIVER))
    other = seed_organization(owner_conn)
    stranger = Member(other.user, owner.org, "x@example.com", "0700000000", "Owen", "Out", "Owner")
    _create_refused(app_conn, stranger, "Rider", DRIVER, "XC403", "not_member")
    _update_refused(app_conn, stranger, role, "Rider", DRIVER, 1, "XC403", "not_member")
    _delete_refused(app_conn, stranger, role, "XC403", "not_member")
    refused(
        app_conn, "access_role_list", [other.user, owner.org, REQUEST, T0], "XC403", "not_member"
    )


# --- the list ----------------------------------------------------------------------------


def test_the_list_answers_built_in_roles_first_then_custom_roles_by_name(
    app_conn: Conn, owner: Member, office: Member
) -> None:
    driver = _create(app_conn, owner, "driver", DRIVER)
    cashier = _create(app_conn, owner, "Cashier", CASHIER)
    roles = _list(app_conn, office)
    assert [r["name"] for r in roles] == [*BUILT_IN, "Cashier", "driver"]
    assert [r["built_in"] for r in roles] == [True] * 4 + [False] * 2
    assert roles[-2:] == [cashier, driver]
    assert {r["version"] for r in roles} == {1}


# --- two writers at once ------------------------------------------------------------------


def test_two_changes_at_the_same_version_let_one_win(
    app_conn: Conn, app_url: str, owner_conn: Conn, owner: Member
) -> None:
    role = _role_id(_create(app_conn, owner, "Driver", DRIVER))
    first, late = _race(
        app_url,
        lambda one: _update(one, owner, role, "Courier", DRIVER, 1),
        lambda two: _update(two, owner, role, "Rider", DRIVER, 1),
    )
    assert (first["name"], first["version"]) == ("Courier", 2)
    assert late == ("XC409", "version_conflict")
    row = _role_row(owner_conn, role)
    assert row is not None
    assert (row["name"], row["version"]) == ("Courier", 2)


def test_two_creates_of_one_name_let_one_win(
    app_conn: Conn, app_url: str, owner_conn: Conn, owner: Member
) -> None:
    first, late = _race(
        app_url,
        lambda one: _create(one, owner, "Driver", DRIVER),
        lambda two: _create(two, owner, "DRIVER", CASHIER),
    )
    assert first["name"] == "Driver"
    assert late == ("XC422", "role_name_taken")
    assert [r["name"] for r in _list(app_conn, owner)] == [*BUILT_IN, "Driver"]


def test_a_delete_waits_for_a_person_save_giving_the_role_and_is_in_use(
    app_conn: Conn, app_url: str, owner_conn: Conn, owner: Member
) -> None:
    role = _role_id(_create(app_conn, owner, "Driver", DRIVER))
    _, late = _race(
        app_url,
        lambda one: _give(one, owner, "Driver", _expand(DRIVER)),
        lambda two: _delete(two, owner, role),
    )
    assert late == ("XC409", "in_use")
    assert _role_row(owner_conn, role) is not None


def test_a_person_save_waits_for_a_delete_of_the_role_and_finds_no_role(
    app_conn: Conn, app_url: str, owner_conn: Conn, owner: Member
) -> None:
    role = _role_id(_create(app_conn, owner, "Driver", DRIVER))
    _, late = _race(
        app_url,
        lambda one: _delete(one, owner, role),
        lambda two: _give(two, owner, "Driver", _expand(DRIVER)),
    )
    assert late == ("XC422", "people_role_unknown")
    assert _role_row(owner_conn, role) is None


# --- structure ---------------------------------------------------------------------------


def test_the_executor_rights_generated_flag_and_row_level_security_hold(
    owner_conn: Conn,
) -> None:
    rights = {
        (table, right): owner_conn.execute(
            "SELECT has_table_privilege('xcode_api_executor', %s, %s) AS ok", (table, right)
        ).fetchone()
        for table in ("tenancy.roles", "tenancy.role_grants")
        for right in ("SELECT", "INSERT", "UPDATE", "DELETE")
    }
    assert {k for k, v in rights.items() if v == {"ok": True}} >= {
        ("tenancy.roles", "UPDATE"),
        ("tenancy.roles", "DELETE"),
        ("tenancy.role_grants", "SELECT"),
        ("tenancy.role_grants", "INSERT"),
        ("tenancy.role_grants", "DELETE"),
    }
    assert rights[("tenancy.role_grants", "UPDATE")] == {"ok": False}
    generated = owner_conn.execute(
        "SELECT attgenerated FROM pg_catalog.pg_attribute "
        "WHERE attrelid = 'tenancy.roles'::regclass AND attname = 'built_in'"
    ).fetchone()
    assert generated == {"attgenerated": "s"}
    security = owner_conn.execute(
        "SELECT relrowsecurity FROM pg_catalog.pg_class WHERE oid = 'tenancy.role_grants'::regclass"
    ).fetchone()
    assert security == {"relrowsecurity": True}
    policies = owner_conn.execute(
        "SELECT policyname, roles::text[] AS roles FROM pg_catalog.pg_policies "
        "WHERE schemaname = 'tenancy' AND tablename = 'role_grants'"
    ).fetchall()
    assert policies == [{"policyname": "tenant_isolation", "roles": ["xcode_api_executor"]}]
