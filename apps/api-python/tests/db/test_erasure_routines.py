"""The erasure routine (``api.people_erase``) and its 0018 helpers: a blocked person who belongs
to this organization only loses their email, mobile number, PIN and name, their devices,
sessions, open codes and App Review sign-in code go, and this organization's people and sign-in
history of them is redacted, while money and history rows keep the id. Another person's rows
and another organization's rows are untouched; every refusal erases nothing; a repeat answers
unchanged. ``tenancy.belongs_elsewhere`` answers only for a member of the current organization,
and only the executor may run the owner-owned helpers (``docs/05-routines.md``;
``docs/06-http-contract.md`` section 2.2)."""

from __future__ import annotations

import json
import secrets
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest

from ..support.rows import seed_organization
from ..support.scenario import (
    T0,
    TRUSTED,
    Conn,
    call,
    codes,
    device_row,
    set_user,
    store_code,
    store_token,
    tokens,
    trust,
    user_row,
)
from ..support.tenancy import (
    REQUEST,
    Member,
    audit_events,
    change_log,
    membership,
    provision_member,
    refused,
    seed_change,
    write,
)

REASON = "Asked to be deleted"
ERASED = f"Erased the personal details of a former member. Reason: {REASON}."
BLOCKED_VERSION = 2


@pytest.fixture
def owner(operator_conn: Conn) -> Member:
    return provision_member(operator_conn, 1, "Owner", "Olive", "Owner")


@pytest.fixture
def office(operator_conn: Conn, owner: Member) -> Member:
    return provision_member(operator_conn, 2, "Office admin", "Otto", "Office")


@pytest.fixture
def clerk(operator_conn: Conn, owner: Member) -> Member:
    return provision_member(operator_conn, 4, "Revenue clerk", "Cleo", "Clerk")


@pytest.fixture
def cashier(operator_conn: Conn, owner: Member) -> Member:
    return provision_member(operator_conn, 5, "Revenue clerk", "Cara", "Cashier")


@pytest.fixture
def owner2(operator_conn: Conn, owner: Member) -> Member:
    return provision_member(operator_conn, 6, "Owner", "Oscar", "Second")


def _block(app: Conn, actor: Member, member: Member) -> None:
    result = write(
        app,
        "people_set_active",
        actor.id,
        actor.org,
        REQUEST,
        member.id,
        False,
        1,
        "Asked to leave",
        T0,
    )
    assert result["outcome"] == "updated"


def _erase(
    app: Conn, actor: Member, user_id: UUID | None, version: int | None, reason: str | None = REASON
) -> dict[str, Any]:
    return write(app, "people_erase", actor.id, actor.org, REQUEST, user_id, version, reason, T0)


def _erase_refused(
    app: Conn,
    actor: Member,
    user_id: UUID | None,
    version: int | None,
    reason: str | None,
    sqlstate: str,
    code: str,
) -> None:
    refused(
        app,
        "people_erase",
        [actor.id, actor.org, REQUEST, user_id, version, reason, T0],
        sqlstate,
        code,
    )


def _join(owner_conn: Conn, org: UUID, user: UUID, *, active: bool = True) -> None:
    owner_conn.execute(
        "INSERT INTO tenancy.memberships (organization_id, user_id, first_name, last_name, "
        "active) VALUES (%s, %s, 'Cleo', 'Clerk', %s)",
        (org, user, active),
    )


def _review(owner_conn: Conn, user: UUID) -> None:
    owner_conn.execute(
        "INSERT INTO identity.review_accounts (user_id, code_hash, created_at, updated_at) "
        "VALUES (%s, %s, %s, %s)",
        (user, secrets.token_hex(32).upper(), T0, T0),
    )


def _reviews(owner_conn: Conn, user: UUID) -> int:
    row = owner_conn.execute(
        "SELECT count(*) AS n FROM identity.review_accounts WHERE user_id = %s", (user,)
    ).fetchone()
    assert row is not None
    return int(row["n"])


def _rows_of(owner_conn: Conn, org: UUID, entity: UUID) -> list[dict[str, Any]]:
    return [r for r in change_log(owner_conn, org) if r["entity_id"] == entity]


def _intact(owner_conn: Conn, member: Member) -> None:
    row = user_row(owner_conn, member.id)
    assert row["erased_at"] is None
    assert (row["email"], row["phone_number"]) != (None, None)
    names = membership(owner_conn, member.org, member.id)
    assert (names["first_name"], names["last_name"]) == (member.first_name, member.last_name)


def _belongs(executor: Conn, current: UUID | None, org: UUID | None, user: UUID) -> bool:
    with executor.transaction():
        if current is not None:
            executor.execute(
                "SELECT set_config('xcode.organization_id', %s, true)", (str(current),)
            )
        row = executor.execute(
            "SELECT tenancy.belongs_elsewhere(%s, %s) AS b", (org, user)
        ).fetchone()
    assert row is not None
    return bool(row["b"])


# --- the effect -----------------------------------------------------------------------------


def test_a_blocked_person_loses_their_details_devices_codes_and_review_login(
    app_conn: Conn, owner_conn: Conn, owner: Member, office: Member, clerk: Member
) -> None:
    _block(app_conn, owner, clerk)
    before = user_row(owner_conn, clerk.id)
    trust(owner_conn, clerk.id, TRUSTED, name="Cleo phone")
    store_token(owner_conn, clerk.id, TRUSTED)
    store_code(owner_conn, clerk.id, "new_device", TRUSTED)
    _review(owner_conn, clerk.id)
    _review(owner_conn, office.id)

    result = _erase(app_conn, owner, clerk.id, BLOCKED_VERSION)

    assert result == {"id": clerk.id, "version": BLOCKED_VERSION + 1, "outcome": "updated"}
    after = user_row(owner_conn, clerk.id)
    assert after["erased_at"] == T0
    assert (after["email"], after["phone_number"], after["pin_hash"]) == (None, None, None)
    assert after["status"] == "removed" and after["pin_reset_required"] is False
    assert after["security_version"] > before["security_version"]
    names = membership(owner_conn, clerk.org, clerk.id)
    assert (names["first_name"], names["last_name"]) == ("Former", "member")
    assert names["version"] == BLOCKED_VERSION + 1 and names["active"] is False
    device = device_row(owner_conn, clerk.id, TRUSTED)
    assert device is not None and device["revoked"] is True and device["name"] == "Device"
    sessions, open_codes = tokens(owner_conn, clerk.id), codes(owner_conn, clerk.id)
    assert sessions and all(t["revoked"] for t in sessions)
    assert open_codes and all(c["consumed"] for c in open_codes)
    assert _reviews(owner_conn, clerk.id) == 0
    assert _reviews(owner_conn, office.id) == 1
    _intact(owner_conn, office)


def test_the_erasure_is_logged_and_audited_without_personal_details(
    app_conn: Conn, owner_conn: Conn, owner: Member, clerk: Member
) -> None:
    _block(app_conn, owner, clerk)
    _erase(app_conn, owner, clerk.id, BLOCKED_VERSION)

    row = _rows_of(owner_conn, clerk.org, clerk.id)[-1]
    assert (row["section"], row["actor_id"], row["reason"]) == ("people", owner.id, ERASED)
    assert (json.loads(row["before"]), json.loads(row["after"])) == (
        {"Erased": False},
        {"Erased": True},
    )
    events = audit_events(owner_conn, clerk.org, "person.erased")
    assert len(events) == 1
    assert events[0]["entity"] == str(clerk.id) and events[0]["actor_id"] == owner.id
    assert (events[0]["before"], events[0]["after"]) == ({"erased": False}, {"erased": True})


def test_this_organizations_history_of_the_person_is_redacted_and_no_one_elses(
    app_conn: Conn, owner_conn: Conn, owner: Member, office: Member, clerk: Member
) -> None:
    other = seed_organization(owner_conn)
    detail = json.dumps(
        {
            "FirstName": "Cleo",
            "LastName": "Clerk",
            "Email": clerk.email,
            "PhoneNumber": clerk.phone,
            "Role": "Revenue clerk",
        }
    )
    call(app_conn, "me_deletion_request", clerk.id, clerk.org, REQUEST, T0)
    seed_change(
        owner_conn,
        clerk.org,
        owner.id,
        "signIn",
        clerk.id,
        "Signed out Cleo Clerk",
        before=detail,
        after=detail,
    )
    seed_change(
        owner_conn, clerk.org, owner.id, "companies", clerk.id, "Cleo Clerk runs it", after=detail
    )
    seed_change(
        owner_conn, office.org, owner.id, "people", office.id, "Edited Otto Office", after=detail
    )
    seed_change(
        owner_conn, other.org, other.user, "people", clerk.id, "Edited Cleo Clerk", after=detail
    )
    _block(app_conn, owner, clerk)
    office_rows = _rows_of(owner_conn, office.org, office.id)

    _erase(app_conn, owner, clerk.id, BLOCKED_VERSION)

    redacted = {(r["section"], r["reason"]): r for r in _rows_of(owner_conn, clerk.org, clerk.id)}
    assert ("people", "Account deletion requested, Former member") in redacted
    assert ("people", "Removed access for Former member. Reason: Asked to leave.") in redacted
    signed_out = redacted[("signIn", "Signed out Former member")]
    for snapshot in (signed_out["before"], signed_out["after"]):
        assert json.loads(snapshot) == {
            "FirstName": "Former",
            "LastName": "member",
            "Email": None,
            "PhoneNumber": None,
            "Role": "Revenue clerk",
        }
    for row in redacted.values():
        text = json.dumps([row["reason"], row["before"], row["after"]])
        if row["section"] != "companies":
            assert clerk.name not in text
            assert clerk.email not in text and clerk.phone not in text
    assert redacted[("companies", "Cleo Clerk runs it")]["after"] == detail
    assert _rows_of(owner_conn, office.org, office.id) == office_rows
    elsewhere = _rows_of(owner_conn, other.org, clerk.id)
    assert [(r["reason"], r["after"]) for r in elsewhere] == [("Edited Cleo Clerk", detail)]


def test_an_owner_may_erase_another_blocked_owner(
    app_conn: Conn, owner_conn: Conn, owner: Member, owner2: Member
) -> None:
    _block(app_conn, owner, owner2)
    assert _erase(app_conn, owner, owner2.id, BLOCKED_VERSION)["outcome"] == "updated"
    assert user_row(owner_conn, owner2.id)["erased_at"] == T0


def test_a_repeat_answers_unchanged_and_records_nothing(
    app_conn: Conn, owner_conn: Conn, owner: Member, clerk: Member
) -> None:
    _block(app_conn, owner, clerk)
    _erase(app_conn, owner, clerk.id, BLOCKED_VERSION)
    logged = len(change_log(owner_conn, clerk.org))

    for version, reason in ((BLOCKED_VERSION + 1, REASON), (None, None)):
        again = _erase(app_conn, owner, clerk.id, version, reason)
        assert again == {"id": clerk.id, "version": BLOCKED_VERSION + 1, "outcome": "unchanged"}

    assert len(change_log(owner_conn, clerk.org)) == logged
    assert len(audit_events(owner_conn, clerk.org, "person.erased")) == 1


# --- refusals -------------------------------------------------------------------------------


def test_erasing_oneself_or_without_people_block_is_refused(
    app_conn: Conn, owner_conn: Conn, owner: Member, clerk: Member, cashier: Member
) -> None:
    _block(app_conn, owner, clerk)
    _erase_refused(app_conn, owner, owner.id, 1, REASON, "XC422", "people_self_erase")
    _erase_refused(
        app_conn, cashier, clerk.id, BLOCKED_VERSION, REASON, "XC403", "permission_missing"
    )
    _intact(owner_conn, owner)
    _intact(owner_conn, clerk)


def test_an_unknown_or_another_organizations_person_is_not_found(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    other = seed_organization(owner_conn)
    for target in (uuid4(), None, other.user2):
        _erase_refused(app_conn, owner, target, 1, REASON, "XC404", "not_found")
    assert user_row(owner_conn, other.user2)["erased_at"] is None


def test_a_non_owner_cannot_erase_an_owner(
    app_conn: Conn, owner_conn: Conn, owner: Member, office: Member, owner2: Member
) -> None:
    _block(app_conn, owner, owner2)
    _erase_refused(
        app_conn, office, owner2.id, BLOCKED_VERSION, REASON, "XC403", "people_owner_edit"
    )
    assert user_row(owner_conn, owner2.id)["erased_at"] is None


def test_an_active_person_is_refused_before_the_version_is_checked(
    app_conn: Conn, owner_conn: Conn, owner: Member, clerk: Member
) -> None:
    _erase_refused(app_conn, owner, clerk.id, 99, REASON, "XC422", "people_erase_active")
    _intact(owner_conn, clerk)


def test_a_person_who_also_belongs_to_another_organization_is_refused(
    app_conn: Conn, owner_conn: Conn, owner: Member, clerk: Member
) -> None:
    other = seed_organization(owner_conn)
    _block(app_conn, owner, clerk)
    _join(owner_conn, other.org, clerk.id)
    _erase_refused(app_conn, owner, clerk.id, 99, REASON, "XC422", "people_erase_shared")
    row = user_row(owner_conn, clerk.id)
    assert row["erased_at"] is None and row["email"] == clerk.email


@pytest.mark.parametrize(
    ("version", "reason", "sqlstate", "code"),
    [
        (1, REASON, "XC409", "version_conflict"),
        (None, REASON, "XC409", "version_conflict"),
        (BLOCKED_VERSION, None, "XC422", "reason_length"),
        (BLOCKED_VERSION, "   ", "XC422", "reason_length"),
    ],
)
def test_a_stale_version_or_a_missing_reason_erases_nothing(
    app_conn: Conn,
    owner_conn: Conn,
    owner: Member,
    clerk: Member,
    version: int | None,
    reason: str | None,
    sqlstate: str,
    code: str,
) -> None:
    _block(app_conn, owner, clerk)
    _erase_refused(app_conn, owner, clerk.id, version, reason, sqlstate, code)
    assert user_row(owner_conn, clerk.id)["erased_at"] is None
    assert membership(owner_conn, clerk.org, clerk.id)["first_name"] == "Cleo"


# --- the helpers ----------------------------------------------------------------------------


def test_belongs_elsewhere_answers_only_for_a_member_of_the_current_organization(
    executor: Conn, owner_conn: Conn, owner: Member, clerk: Member
) -> None:
    other = seed_organization(owner_conn)
    third = seed_organization(owner_conn)
    assert _belongs(executor, owner.org, owner.org, clerk.id) is False

    _join(owner_conn, other.org, clerk.id, active=False)
    assert _belongs(executor, owner.org, owner.org, clerk.id) is True
    assert _belongs(executor, owner.org, other.org, clerk.id) is False
    assert _belongs(executor, None, owner.org, clerk.id) is False
    assert _belongs(executor, owner.org, None, clerk.id) is False

    _join(owner_conn, third.org, other.user, active=False)
    assert _belongs(executor, owner.org, owner.org, other.user) is False
    assert _belongs(executor, owner.org, other.org, other.user) is False


@pytest.mark.parametrize(
    ("signature", "executor_may"),
    [
        ("tenancy.belongs_elsewhere(uuid, uuid)", True),
        ("tenancy.erase_person_history(uuid, uuid)", True),
        ("identity.erase_review_login(uuid)", True),
        ("tenancy.erased_snapshot(text)", False),
    ],
)
def test_the_erasure_helpers_are_owner_owned_and_run_only_by_the_executor(
    owner_conn: Conn, signature: str, executor_may: bool
) -> None:
    row = owner_conn.execute(
        "SELECT pg_get_userbyid(p.proowner) AS owner, p.proconfig, "
        "(SELECT count(*) FROM aclexplode(p.proacl) AS a WHERE a.grantee = 0) AS public "
        "FROM pg_proc AS p WHERE p.oid = %s::regprocedure",
        (signature,),
    ).fetchone()
    assert row is not None
    assert row["owner"] != "xcode_api_executor"
    assert row["proconfig"] == ["search_path=pg_catalog, pg_temp"]
    assert row["public"] == 0
    for role, allowed in (
        ("xcode_api_executor", executor_may),
        ("xcode_app", False),
        ("xcode_operator", False),
        ("xcode_readonly", False),
    ):
        granted = owner_conn.execute(
            "SELECT has_function_privilege(%s, %s, 'EXECUTE') AS ok", (role, signature)
        ).fetchone()
        assert granted is not None and granted["ok"] is allowed, role


def test_the_definer_helpers_are_security_definer(owner_conn: Conn) -> None:
    rows = owner_conn.execute(
        "SELECT p.oid::regprocedure::text AS signature, p.prosecdef FROM pg_proc AS p "
        "WHERE p.oid IN ('tenancy.belongs_elsewhere(uuid, uuid)'::regprocedure, "
        "'tenancy.erase_person_history(uuid, uuid)'::regprocedure, "
        "'identity.erase_review_login(uuid)'::regprocedure)"
    ).fetchall()
    assert len(rows) == 3 and all(r["prosecdef"] for r in rows)


def test_the_app_role_cannot_call_belongs_elsewhere(
    app_conn: Conn, owner: Member, clerk: Member
) -> None:
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        app_conn.execute(
            "SELECT tenancy.belongs_elsewhere(%s, %s)", (owner.org, clerk.id)
        ).fetchall()


def test_the_review_login_delete_spares_an_account_that_is_not_erased(
    executor: Conn, owner_conn: Conn, clerk: Member
) -> None:
    _review(owner_conn, clerk.id)
    executor.execute("SELECT identity.erase_review_login(%s)", (clerk.id,))
    assert _reviews(owner_conn, clerk.id) == 1


def test_the_history_rewrite_spares_a_live_account_and_another_organization(
    app_conn: Conn, executor: Conn, owner_conn: Conn, owner: Member, clerk: Member
) -> None:
    other = seed_organization(owner_conn)
    seed_change(owner_conn, clerk.org, owner.id, "people", clerk.id, "Edited Cleo Clerk")
    seed_change(owner_conn, other.org, other.user, "people", clerk.id, "Edited Cleo Clerk")
    ours = _rows_of(owner_conn, clerk.org, clerk.id)
    theirs = _rows_of(owner_conn, other.org, clerk.id)
    with executor.transaction():
        executor.execute("SELECT set_config('xcode.organization_id', %s, true)", (str(owner.org),))
        executor.execute("SELECT tenancy.erase_person_history(%s, %s)", (owner.org, clerk.id))
    assert _rows_of(owner_conn, clerk.org, clerk.id) == ours

    _block(app_conn, owner, clerk)
    _erase(app_conn, owner, clerk.id, BLOCKED_VERSION)
    with executor.transaction():
        executor.execute("SELECT set_config('xcode.organization_id', %s, true)", (str(owner.org),))
        executor.execute("SELECT tenancy.erase_person_history(%s, %s)", (other.org, clerk.id))
    assert _rows_of(owner_conn, other.org, clerk.id) == theirs


def test_the_executor_still_cannot_rewrite_history_itself(executor: Conn, owner: Member) -> None:
    with pytest.raises(psycopg.errors.InsufficientPrivilege), executor.transaction():
        executor.execute("SELECT set_config('xcode.organization_id', %s, true)", (str(owner.org),))
        executor.execute("UPDATE tenancy.change_log SET reason = 'x'")


# --- the constraints ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("values", "constraint"),
    [
        ({"email": None}, "ck_users_erased_email"),
        ({"phone_number": None}, "ck_users_erased_phone_number"),
        ({"erased_at": T0}, "ck_users_erased_email"),
        ({"erased_at": T0, "email": None, "phone_number": None}, "ck_users_erased_removed"),
    ],
)
def test_an_account_is_erased_whole_or_not_at_all(
    owner_conn: Conn, clerk: Member, values: dict[str, Any], constraint: str
) -> None:
    with pytest.raises(psycopg.errors.CheckViolation) as caught:
        set_user(owner_conn, clerk.id, **values)
    assert caught.value.diag.constraint_name == constraint
