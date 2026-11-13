"""``api.people_delete`` (0022), called as ``xcode_app``: a person nothing refers to leaves
this organization with their role, overrides, scope, preferences, pending invitation and
notices, and their account goes too unless they belong to another organization, which keeps
it with its devices and sessions. The change log keeps a snapshot without their email and
mobile number, and their earlier history in this organization loses both too, names kept;
another organization's history is untouched. Anything else that refers to them refuses with
``XC409 in_use`` and keeps every row. The refusals come in order: a caller without
``people.manage``, oneself, a person outside the caller's view (another organization's, out
of scope, unknown), a non-Owner on an Owner, then use, so no refusal tells a caller more than
the first rule they broke."""

from __future__ import annotations

import json
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest

from ..support.rows import seed_organization
from ..support.scenario import T0, TRUSTED, Conn, store_code, store_token, trust
from ..support.setup_rows import (
    add_category,
    add_central_expense,
    add_investment,
    add_item,
    add_main_category,
    add_pettycash_spend,
    add_record,
    add_target_set,
)
from ..support.tenancy import (
    REQUEST,
    Member,
    add_company,
    add_vehicle,
    audit_events,
    change_log,
    provision_member,
    refused,
    seed_change,
    set_override,
    set_scope,
    write,
)

IN_USE = {"name": "Cleo Clerk", "use": "person_records"}
SNAPSHOT_KEYS = [
    "FirstName",
    "LastName",
    "Email",
    "PhoneNumber",
    "Role",
    "Active",
    "ScopeMode",
    "CompanyIds",
    "VehicleIds",
    "Permissions",
    "ApprovalLimit",
    "BackLimitMode",
    "BackLimitCount",
    "BackLimitFrom",
    "Name",
]
MEMBERSHIP_ROWS = (
    ("tenancy.memberships", "user_id"),
    ("tenancy.person_roles", "user_id"),
    ("tenancy.permission_overrides", "user_id"),
    ("tenancy.data_scopes", "user_id"),
    ("tenancy.data_scope_companies", "user_id"),
    ("tenancy.data_scope_vehicles", "user_id"),
    ("tenancy.user_preferences", "user_id"),
    ("identity.invitations", "user_id"),
    ("tenancy.sign_in_notices", "user_id"),
    ("tenancy.deletion_notices", "recipient_id"),
)
ACCOUNT_ROWS = (
    ("identity.users", "id"),
    ("identity.verification_codes", "user_id"),
    ("identity.trusted_devices", "user_id"),
    ("identity.refresh_tokens", "user_id"),
    ("identity.review_accounts", "user_id"),
)


@dataclass(frozen=True, slots=True)
class Yard:
    company: UUID
    spare: UUID
    vehicle: UUID
    item: UUID


@pytest.fixture
def owner(operator_conn: Conn) -> Member:
    return provision_member(operator_conn, 1, "Owner", "Olive", "Owner")


@pytest.fixture
def office(operator_conn: Conn, owner: Member) -> Member:
    return provision_member(operator_conn, 2, "Office admin", "Otto", "Office")


@pytest.fixture
def clerk(operator_conn: Conn, owner: Member) -> Member:
    return provision_member(operator_conn, 3, "Revenue clerk", "Cleo", "Clerk")


@pytest.fixture
def owner2(operator_conn: Conn, owner: Member) -> Member:
    return provision_member(operator_conn, 4, "Owner", "Oscar", "Second")


@pytest.fixture
def yard(owner_conn: Conn, owner: Member) -> Yard:
    company = add_company(owner_conn, owner.org, "North Star")
    spare = add_company(owner_conn, owner.org, "Spare Line")
    vehicle = add_vehicle(owner_conn, owner.org, company, "KDA 482M")
    main = add_main_category(owner_conn, owner.org, "Running")
    category = add_category(owner_conn, owner.org, "Fuel", main_category=main)
    item = add_item(owner_conn, owner.org, category, "Diesel")
    return Yard(company, spare, vehicle, item)


def _delete(app: Conn, actor: Member, user_id: UUID) -> dict[str, Any]:
    return write(app, "people_delete", actor.id, actor.org, REQUEST, user_id, T0)


def _refused(app: Conn, actor: Member, user_id: UUID, sqlstate: str, code: str) -> psycopg.Error:
    return refused(
        app, "people_delete", [actor.id, actor.org, REQUEST, user_id, T0], sqlstate, code
    )


def _count(owner_conn: Conn, sql: str, params: tuple[Any, ...]) -> int:
    row = owner_conn.execute(sql, params).fetchone()
    assert row is not None
    return int(row["n"])


def _membership_rows(owner_conn: Conn, org: UUID, user: UUID) -> dict[str, int]:
    return {
        table: _count(
            owner_conn,
            f"SELECT count(*) AS n FROM {table} WHERE organization_id = %s AND {column} = %s",
            (org, user),
        )
        for table, column in MEMBERSHIP_ROWS
    }


def _account_rows(owner_conn: Conn, user: UUID) -> dict[str, int]:
    return {
        table: _count(owner_conn, f"SELECT count(*) AS n FROM {table} WHERE {column} = %s", (user,))
        for table, column in ACCOUNT_ROWS
    }


def _hex() -> str:
    return secrets.token_hex(32).upper()


def _preferences(owner_conn: Conn, org: UUID, user: UUID) -> None:
    owner_conn.execute(
        "INSERT INTO tenancy.user_preferences (organization_id, user_id, theme_mode) "
        "VALUES (%s, %s, 'dark')",
        (org, user),
    )


def _dependents(owner_conn: Conn, actor: Member, member: Member, yard: Yard) -> None:
    """One row in every table that hangs on the membership: override, scope, preferences, a
    pending invitation, a sign-in notice and a deletion notice addressed to them."""
    org = member.org
    set_override(owner_conn, member, "dash.capture")
    set_scope(
        owner_conn,
        member,
        org,
        all_companies=True,
        companies=[yard.company],
        vehicles=[yard.vehicle],
    )
    _preferences(owner_conn, org, member.id)
    owner_conn.execute(
        "INSERT INTO identity.invitations (organization_id, user_id, invited_by, token_hash, "
        "code_hash, created_at, expires_at) VALUES (%s, %s, %s, %s, %s, %s, %s)",
        (org, member.id, actor.id, _hex(), _hex(), T0, T0 + timedelta(days=7)),
    )
    owner_conn.execute(
        "INSERT INTO tenancy.sign_in_notices (organization_id, user_id, actor_id, kind, address, "
        "created_at) VALUES (%s, %s, %s, 'current', 'notice@example.com', %s)",
        (org, member.id, actor.id, T0),
    )
    owner_conn.execute(
        "INSERT INTO tenancy.deletion_notices (organization_id, requester_id, recipient_id, "
        "created_at) VALUES (%s, %s, %s, %s)",
        (org, actor.id, member.id, T0),
    )


def _devices(owner_conn: Conn, user: UUID) -> None:
    trust(owner_conn, user, TRUSTED, name="Work phone")
    store_token(owner_conn, user, TRUSTED)
    store_code(owner_conn, user, "new_device", TRUSTED)
    owner_conn.execute(
        "INSERT INTO identity.review_accounts (user_id, code_hash, created_at, updated_at) "
        "VALUES (%s, %s, %s, %s)",
        (user, _hex(), T0, T0),
    )


def _attempt(owner_conn: Conn, member: Member, _yard: Yard) -> None:
    owner_conn.execute(
        "INSERT INTO identity.sign_in_attempts (occurred_at, operation, outcome, user_id, "
        "phone_digest, device_id, request_id) VALUES (%s, 'sign_in', 'authenticated', %s, "
        "repeat('a', 64), %s, 'req-sign-in')",
        (T0, member.id, TRUSTED),
    )


def _attempts(owner_conn: Conn, user: UUID) -> int:
    return _count(
        owner_conn,
        "SELECT count(*) AS n FROM identity.sign_in_attempts WHERE user_id = %s",
        (user,),
    )


def _audit(owner_conn: Conn, member: Member, yard: Yard) -> None:
    owner_conn.execute(
        "INSERT INTO tenancy.audit_events (organization_id, actor_id, action, entity, "
        "occurred_at, request_id) VALUES (%s, %s, 'company.updated', %s, %s, 'req-audit')",
        (member.org, member.id, str(yard.company), T0),
    )


def _join(owner_conn: Conn, org: UUID, user: UUID) -> None:
    owner_conn.execute(
        "INSERT INTO tenancy.memberships (organization_id, user_id, first_name, last_name, "
        "active) VALUES (%s, %s, 'Cleo', 'Clerk', false)",
        (org, user),
    )


def _contact_snapshot(member: Member) -> str:
    return json.dumps(
        {
            "FirstName": member.first_name,
            "LastName": member.last_name,
            "Email": member.email,
            "PhoneNumber": member.phone,
            "Role": member.role,
        }
    )


def _person_event(owner_conn: Conn, org: UUID, actor: UUID, member: Member) -> None:
    snapshot = _contact_snapshot(member)
    owner_conn.execute(
        "INSERT INTO tenancy.audit_events (organization_id, actor_id, action, entity, before, "
        "after, occurred_at, request_id) "
        "VALUES (%s, %s, 'person.updated', %s, %s, %s, %s, 'req-audit')",
        (org, actor, str(member.id), snapshot, snapshot, T0),
    )


def _forget(executor: Conn, current: UUID | None, org: UUID, user: UUID) -> None:
    with executor.transaction():
        if current is not None:
            executor.execute(
                "SELECT set_config('xcode.organization_id', %s, true)", (str(current),)
            )
        executor.execute("SELECT tenancy.forget_contact_history(%s, %s)", (org, user))


def _history(owner_conn: Conn, org: UUID, user: UUID) -> list[tuple[Any, Any]]:
    changes = [
        (json.loads(r["before"]), json.loads(r["after"]))
        for r in change_log(owner_conn, org)
        if r["entity_id"] == user
    ]
    events = [
        (e["before"], e["after"]) for e in audit_events(owner_conn, org) if e["entity"] == str(user)
    ]
    return changes + events


USES: dict[str, Callable[[Conn, Member, Yard], object]] = {
    "change_log_actor": lambda conn, m, y: seed_change(
        conn, m.org, m.id, "companies", y.company, "Edited company North Star"
    ),
    "audit_actor": _audit,
    "revenue_captured": lambda conn, m, y: add_record(
        conn, m.org, y.vehicle, date(2026, 3, 2), 1500, recorder=m.id
    ),
    "petty_cash_holder": lambda conn, m, y: add_pettycash_spend(
        conn, m.org, y.vehicle, y.item, holder=m.id
    ),
    "expense_recorded": lambda conn, m, y: add_central_expense(
        conn, m.org, y.vehicle, y.item, recorder=m.id
    ),
    "investment_recorded": lambda conn, m, y: add_investment(
        conn, m.org, y.vehicle, date(2026, 3, 1), "Tyres", 5000, recorder=m.id
    ),
    "target_set_created": lambda conn, m, y: add_target_set(
        conn, m.org, y.vehicle, date(2026, 3, 1), [1000] * 7, created_by=m.id
    ),
    "sign_in_attempt": _attempt,
}


# --- the effect -----------------------------------------------------------------------------


def test_a_person_nothing_refers_to_goes_with_everything_that_hangs_on_them(
    app_conn: Conn, owner_conn: Conn, owner: Member, office: Member, clerk: Member, yard: Yard
) -> None:
    _dependents(owner_conn, owner, clerk, yard)
    _devices(owner_conn, clerk.id)
    _devices(owner_conn, office.id)
    assert all(_membership_rows(owner_conn, clerk.org, clerk.id).values())
    assert all(_account_rows(owner_conn, clerk.id).values())
    office_rows = _membership_rows(owner_conn, office.org, office.id)
    office_account = _account_rows(owner_conn, office.id)

    result = _delete(app_conn, owner, clerk.id)

    assert (result["id"], result["outcome"]) == (clerk.id, "updated")
    assert not any(_membership_rows(owner_conn, clerk.org, clerk.id).values())
    assert not any(_account_rows(owner_conn, clerk.id).values())
    assert _membership_rows(owner_conn, office.org, office.id) == office_rows
    assert _account_rows(owner_conn, office.id) == office_account
    _refused(app_conn, owner, clerk.id, "XC404", "not_found")


def test_an_account_that_belongs_to_another_organization_stays_with_its_devices(
    app_conn: Conn, owner_conn: Conn, owner: Member, clerk: Member, yard: Yard
) -> None:
    other = seed_organization(owner_conn)
    _join(owner_conn, other.org, clerk.id)
    _preferences(owner_conn, other.org, clerk.id)
    _dependents(owner_conn, owner, clerk, yard)
    _devices(owner_conn, clerk.id)
    _attempt(owner_conn, clerk, yard)
    elsewhere = _membership_rows(owner_conn, other.org, clerk.id)
    account = _account_rows(owner_conn, clerk.id)

    _delete(app_conn, owner, clerk.id)

    assert not any(_membership_rows(owner_conn, clerk.org, clerk.id).values())
    assert _membership_rows(owner_conn, other.org, clerk.id) == elsewhere
    assert elsewhere["tenancy.memberships"] == 1 and elsewhere["tenancy.user_preferences"] == 1
    assert _account_rows(owner_conn, clerk.id) == account
    assert _attempts(owner_conn, clerk.id) == 1


def test_the_history_keeps_a_snapshot_without_email_or_mobile_number(
    app_conn: Conn, owner_conn: Conn, owner: Member, clerk: Member
) -> None:
    _delete(app_conn, owner, clerk.id)

    rows = [r for r in change_log(owner_conn, clerk.org) if r["entity_id"] == clerk.id]
    assert len(rows) == 1
    row = rows[0]
    assert (row["section"], row["actor_id"], row["reason"]) == (
        "people",
        owner.id,
        "Deleted Cleo Clerk",
    )
    assert row["after"] == "null"
    before = json.loads(row["before"])
    assert list(before) == SNAPSHOT_KEYS
    assert (before["Email"], before["PhoneNumber"]) == (None, None)
    assert (before["FirstName"], before["LastName"], before["Name"]) == (
        "Cleo",
        "Clerk",
        "Cleo Clerk",
    )
    assert (before["Role"], before["Active"]) == ("Revenue clerk", True)
    events = audit_events(owner_conn, clerk.org, "person.deleted")
    assert len(events) == 1
    assert (events[0]["entity"], events[0]["actor_id"]) == (str(clerk.id), owner.id)
    for text in (row["before"], json.dumps([events[0]["before"], events[0]["after"]])):
        assert clerk.email not in text and clerk.phone[1:] not in text


def test_earlier_history_here_loses_their_email_and_mobile_but_keeps_names_and_key_order(
    app_conn: Conn, owner_conn: Conn, owner: Member, office: Member, clerk: Member
) -> None:
    other = seed_organization(owner_conn)
    _join(owner_conn, other.org, clerk.id)
    snapshot = _contact_snapshot(clerk)
    for section, reason in (
        ("people", "Added Cleo Clerk as Revenue clerk"),
        ("signIn", "Invitation sent, Cleo Clerk"),
    ):
        seed_change(
            owner_conn,
            clerk.org,
            owner.id,
            section,
            clerk.id,
            reason,
            before=snapshot,
            after=snapshot,
        )
    office_snapshot = _contact_snapshot(office)
    seed_change(
        owner_conn,
        office.org,
        owner.id,
        "people",
        office.id,
        "Added Otto Office as Office admin",
        before=office_snapshot,
        after=office_snapshot,
    )
    seed_change(
        owner_conn,
        other.org,
        other.user,
        "people",
        clerk.id,
        "Added Cleo Clerk as Revenue clerk",
        before=snapshot,
        after=snapshot,
    )
    _person_event(owner_conn, clerk.org, owner.id, clerk)
    _person_event(owner_conn, other.org, other.user, clerk)

    _delete(app_conn, owner, clerk.id)

    forgotten = {**json.loads(snapshot), "Email": None, "PhoneNumber": None}
    earlier = [
        r
        for r in change_log(owner_conn, clerk.org)
        if r["entity_id"] == clerk.id and r["reason"] != "Deleted Cleo Clerk"
    ]
    assert sorted(r["section"] for r in earlier) == ["people", "signIn"]
    for row in earlier:
        for text in (row["before"], row["after"]):
            assert list(json.loads(text)) == list(forgotten)
            assert json.loads(text) == forgotten
    events = [
        e
        for e in audit_events(owner_conn, clerk.org, "person.updated")
        if e["entity"] == str(clerk.id)
    ]
    assert [(e["before"], e["after"]) for e in events] == [(forgotten, forgotten)]
    office_rows = [r for r in change_log(owner_conn, office.org) if r["entity_id"] == office.id]
    assert [(r["before"], r["after"]) for r in office_rows] == [(office_snapshot, office_snapshot)]
    elsewhere = [r for r in change_log(owner_conn, other.org) if r["entity_id"] == clerk.id]
    assert [(r["before"], r["after"]) for r in elsewhere] == [(snapshot, snapshot)]
    kept = audit_events(owner_conn, other.org, "person.updated")
    assert [(e["before"], e["after"]) for e in kept] == [(json.loads(snapshot),) * 2]


def test_forgetting_contact_history_spares_a_member_and_another_organization(
    executor: Conn, owner_conn: Conn, owner: Member, clerk: Member
) -> None:
    other = seed_organization(owner_conn)
    snapshot = _contact_snapshot(clerk)
    for org, actor in ((clerk.org, owner.id), (other.org, other.user)):
        seed_change(
            owner_conn,
            org,
            actor,
            "people",
            clerk.id,
            "Edited Cleo Clerk",
            before=snapshot,
            after=snapshot,
        )
        _person_event(owner_conn, org, actor, clerk)
    ours = _history(owner_conn, clerk.org, clerk.id)
    theirs = _history(owner_conn, other.org, clerk.id)
    assert len(ours) == len(theirs) == 2

    _forget(executor, clerk.org, clerk.org, clerk.id)
    _forget(executor, clerk.org, other.org, clerk.id)
    _forget(executor, None, other.org, clerk.id)

    assert _history(owner_conn, clerk.org, clerk.id) == ours
    assert _history(owner_conn, other.org, clerk.id) == theirs

    _forget(executor, other.org, other.org, clerk.id)

    forgotten = {**json.loads(snapshot), "Email": None, "PhoneNumber": None}
    assert _history(owner_conn, other.org, clerk.id) == [(forgotten, forgotten)] * 2
    assert _history(owner_conn, clerk.org, clerk.id) == ours


def test_an_owner_may_delete_another_owner_and_an_office_admin_a_clerk(
    app_conn: Conn, owner_conn: Conn, owner: Member, office: Member, clerk: Member, owner2: Member
) -> None:
    assert _delete(app_conn, owner, owner2.id)["outcome"] == "updated"
    assert _delete(app_conn, office, clerk.id)["outcome"] == "updated"
    for user in (owner2.id, clerk.id):
        assert _account_rows(owner_conn, user)["identity.users"] == 0


# --- in use ---------------------------------------------------------------------------------


@pytest.mark.parametrize("use", sorted(USES))
def test_a_person_anything_refers_to_is_in_use_and_keeps_every_row(
    app_conn: Conn, owner_conn: Conn, owner: Member, clerk: Member, yard: Yard, use: str
) -> None:
    _dependents(owner_conn, owner, clerk, yard)
    _devices(owner_conn, clerk.id)
    USES[use](owner_conn, clerk, yard)
    rows = _membership_rows(owner_conn, clerk.org, clerk.id)
    account = _account_rows(owner_conn, clerk.id)
    logged = len(change_log(owner_conn, clerk.org))

    error = _refused(app_conn, owner, clerk.id, "XC409", "in_use")

    assert json.loads(error.diag.message_detail or "{}") == IN_USE
    assert _membership_rows(owner_conn, clerk.org, clerk.id) == rows
    assert _account_rows(owner_conn, clerk.id) == account
    assert len(change_log(owner_conn, clerk.org)) == logged
    assert audit_events(owner_conn, clerk.org, "person.deleted") == []


# --- refusals -------------------------------------------------------------------------------


def test_deleting_oneself_is_refused(app_conn: Conn, owner_conn: Conn, owner: Member) -> None:
    _refused(app_conn, owner, owner.id, "XC403", "people_self_delete")
    assert _membership_rows(owner_conn, owner.org, owner.id)["tenancy.memberships"] == 1


def test_a_non_owner_cannot_delete_an_owner(
    app_conn: Conn, owner_conn: Conn, owner: Member, office: Member, owner2: Member
) -> None:
    rows = _membership_rows(owner_conn, owner2.org, owner2.id)
    _refused(app_conn, office, owner2.id, "XC403", "people_owner_edit")
    assert _membership_rows(owner_conn, owner2.org, owner2.id) == rows
    assert _account_rows(owner_conn, owner2.id)["identity.users"] == 1


@pytest.mark.parametrize("role", ["Revenue clerk", "Fleet manager"])
def test_a_caller_without_people_manage_is_refused(
    app_conn: Conn,
    operator_conn: Conn,
    owner_conn: Conn,
    owner: Member,
    clerk: Member,
    yard: Yard,
    role: str,
) -> None:
    caller = provision_member(operator_conn, 7, role, "Carl", "Caller")
    _dependents(owner_conn, owner, clerk, yard)
    rows = _membership_rows(owner_conn, clerk.org, clerk.id)
    _refused(app_conn, caller, clerk.id, "XC403", "permission_missing")
    assert _membership_rows(owner_conn, clerk.org, clerk.id) == rows


def test_another_organizations_person_or_an_unknown_id_is_not_found(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    other = seed_organization(owner_conn)
    for target in (other.user2, other.user, uuid4()):
        _refused(app_conn, owner, target, "XC404", "not_found")
    for user in (other.user, other.user2):
        assert _membership_rows(owner_conn, other.org, user)["tenancy.memberships"] == 1
        assert _account_rows(owner_conn, user)["identity.users"] == 1


def test_a_person_outside_the_callers_scope_is_not_found(
    app_conn: Conn, owner_conn: Conn, office: Member, clerk: Member, yard: Yard
) -> None:
    set_scope(owner_conn, office, office.org, companies=[yard.spare])
    set_scope(owner_conn, clerk, clerk.org, companies=[yard.company])
    _refused(app_conn, office, clerk.id, "XC404", "not_found")
    assert _membership_rows(owner_conn, clerk.org, clerk.id)["tenancy.memberships"] == 1


def test_each_refusal_tells_no_more_than_the_first_rule_broken(
    app_conn: Conn,
    operator_conn: Conn,
    owner_conn: Conn,
    office: Member,
    owner2: Member,
    yard: Yard,
) -> None:
    caller = provision_member(operator_conn, 7, "Revenue clerk", "Carl", "Caller")
    other = seed_organization(owner_conn)
    USES["change_log_actor"](owner_conn, owner2, yard)
    for target in (caller.id, other.user2, uuid4(), owner2.id):
        _refused(app_conn, caller, target, "XC403", "permission_missing")
    _refused(app_conn, office, office.id, "XC403", "people_self_delete")
    _refused(app_conn, office, other.user2, "XC404", "not_found")
    _refused(app_conn, office, owner2.id, "XC403", "people_owner_edit")
