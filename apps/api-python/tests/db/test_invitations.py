"""Invitations (migration 0015): the link and code made by ``identity.invite``, the link step
``api.auth_invite_redeem``, the invitation code as a first-setup code, ``api.people_invite``,
revocation on block, removal and a new email, the people status, and the delivery routines
(``api.invite_delivery_start``, ``api.invite_delivery_result``, ``api.invite_claim_undelivered``).

Routines are called as ``xcode_app`` with an injected clock; rows are read back as
``xcode_owner``. Every digest is derived at test time.
"""

from __future__ import annotations

import base64
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg.rows import dict_row

from xcode_api.db.types import auth_outcome
from xcode_api.domain.identity import AuthOutcomeKind, CodePurpose, SignInRefusal

from ..support.rows import OrganizationRows, seed_organization
from ..support.scenario import (
    NEW_CODE_HASH,
    NEW_PIN_HASH,
    PIN_HASH,
    T0,
    UNTRUSTED,
    WRONG_CODE_HASH,
    Auth,
    Conn,
    attempts,
    call,
    codes,
    digest,
    new_token_hash,
    set_user,
    user_row,
)
from ..support.tenancy import (
    REQUEST,
    Member,
    audit_events,
    change_log,
    create_person,
    provision_member,
    refused,
    update_person,
    write,
)

JANE = "0722000111"
STRANGER = "0799999999"
WEEK = timedelta(days=7)
MINUTE = timedelta(minutes=1)
TICK = timedelta(microseconds=1)
INVITE_CODE = digest("code:246810")
CROWD = 20


def _pin_hash(label: str) -> str:
    def encode(part: str) -> str:
        return base64.b64encode(f"{part}:{label}".encode()).decode()

    return f"{encode('salt')}.{encode('key')}"


@dataclass(frozen=True, slots=True)
class Invited:
    user_id: UUID
    token: str
    code: str


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
def jane(app_conn: Conn, owner: Member) -> Invited:
    return _invite(app_conn, owner)


def _invite(app: Conn, actor: Member, *, now: datetime = T0, **fields: Any) -> Invited:
    token = new_token_hash()
    row = create_person(
        app, actor, invite_token_hash=token, invite_code_hash=INVITE_CODE, now=now, **fields
    )
    return Invited(row["id"], token, INVITE_CODE)


def _person(n: int) -> dict[str, Any]:
    return {"first_name": f"Pat{n}", "email": f"pat{n}@example.com", "phone": f"07220002{n:02d}"}


def _elsewhere(owner: Conn) -> OrganizationRows:
    rows = seed_organization(owner)
    owner.execute("DELETE FROM identity.invitations WHERE organization_id = %s", (rows.org,))
    return rows


def _invitations(owner: Conn, user_id: UUID) -> list[dict[str, Any]]:
    return owner.execute(
        "SELECT * FROM identity.invitations WHERE user_id = %s ORDER BY created_at, id",
        (user_id,),
    ).fetchall()


def _live(owner: Conn, user_id: UUID) -> dict[str, Any] | None:
    rows = [r for r in _invitations(owner, user_id) if not r["accepted_at"] and not r["revoked_at"]]
    assert len(rows) <= 1
    return rows[0] if rows else None


def _only(owner: Conn, user_id: UUID) -> dict[str, Any]:
    rows = _invitations(owner, user_id)
    assert len(rows) == 1
    return rows[0]


def _redeem(
    app: Conn,
    token: str,
    *,
    phone: str = JANE,
    device: str = UNTRUSTED,
    code_hash: str = NEW_CODE_HASH,
    now: datetime = T0,
) -> dict[str, Any]:
    result: dict[str, Any] = call(
        app, "auth_invite_redeem", "req-redeem", token, phone, device, code_hash, now
    )
    return result


def _refusal(result: dict[str, Any]) -> tuple[str, str | None]:
    return result["outcome"], result["refusal"]


def _reinvite(
    app: Conn, actor: Member, user_id: UUID, *, token: str | None = None, now: datetime = T0
) -> dict[str, Any]:
    args = (user_id, token or new_token_hash(), INVITE_CODE, now)
    return write(app, "people_invite", actor.id, actor.org, REQUEST, *args)


def _reinvite_refused(
    app: Conn, actor: Member, user_id: UUID | None, sqlstate: str, code: str
) -> None:
    args = [actor.id, actor.org, REQUEST, user_id, new_token_hash(), INVITE_CODE, T0]
    refused(app, "people_invite", args, sqlstate, code)


def _set_active(
    app: Conn, actor: Member, user_id: UUID, active: bool, version: int, reason: str | None
) -> None:
    args = (user_id, active, version, reason, T0)
    write(app, "people_set_active", actor.id, actor.org, REQUEST, *args)


def _person_doc(app: Conn, who: Member, user_id: UUID, now: datetime = T0) -> dict[str, Any]:
    result: dict[str, Any] = call(app, "people_get", who.id, who.org, REQUEST, user_id, now)
    return result


def _start(app: Conn, token: str, now: datetime = T0) -> dict[str, Any] | None:
    result: dict[str, Any] | None = call(app, "invite_delivery_start", token, now)
    return result


def _result(app: Conn, token: str, sent: bool, now: datetime = T0) -> None:
    app.execute("SELECT api.invite_delivery_result(%s, %s, %s)", (token, sent, now))


def _claim(
    app: Conn, now: datetime, limit: int | None, tokens: list[str], code_hashes: list[str]
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = call(
        app, "invite_claim_undelivered", now, limit, tokens, code_hashes
    )
    return result


def _pairs(n: int) -> tuple[list[str], list[str]]:
    return [new_token_hash() for _ in range(n)], [digest(f"code:{i}{uuid4()}") for i in range(n)]


def _race(url: str, first: Callable[[Conn], Any], late: Callable[[Conn], Any]) -> tuple[Any, Any]:
    """Runs ``late`` on a second connection while ``first`` holds its transaction open."""
    results: list[Any] = []
    with (
        psycopg.connect(url, autocommit=True, row_factory=dict_row) as one,
        psycopg.connect(url, autocommit=True, row_factory=dict_row) as two,
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
            # The late call waits on the account row the first one holds until it commits.
            assert worker.is_alive()
        worker.join(10)
    assert len(results) == 1
    return done, results[0]


def _crowd(url: str, steps: list[Callable[[Conn], Any]]) -> list[Any]:
    """Runs every step on its own connection, all released together by one barrier."""
    gate = threading.Barrier(len(steps), timeout=30)

    def run(step: Callable[[Conn], Any]) -> Any:
        with psycopg.connect(url, autocommit=True, row_factory=dict_row) as conn:
            gate.wait()
            return step(conn)

    with ThreadPoolExecutor(max_workers=len(steps)) as pool:
        return list(pool.map(run, steps))


# --- making an invitation ---


def test_creating_a_person_with_digests_stores_one_pending_invitation_for_seven_days(
    app_conn: Conn, owner_conn: Conn, owner: Member, jane: Invited
) -> None:
    row = _only(owner_conn, jane.user_id)
    assert (row["organization_id"], row["invited_by"]) == (owner.org, owner.id)
    assert (row["token_hash"], row["code_hash"]) == (jane.token, INVITE_CODE)
    assert (row["created_at"], row["expires_at"]) == (T0, T0 + WEEK)
    assert (row["delivery_state"], row["delivery_attempts"], row["failed_attempts"]) == (
        "pending",
        0,
        0,
    )
    assert row["accepted_at"] is row["revoked_at"] is row["sent_at"] is None
    assert user_row(owner_conn, jane.user_id)["pin_hash"] is None


def test_creating_a_person_without_digests_invites_nobody(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    row = create_person(app_conn, owner)
    assert _invitations(owner_conn, row["id"]) == []


def test_the_partial_index_allows_one_live_invitation_per_person(
    app_conn: Conn, owner_conn: Conn, owner: Member, jane: Invited
) -> None:
    insert = (
        "INSERT INTO identity.invitations "
        "(organization_id, user_id, token_hash, code_hash, created_at, expires_at) "
        "VALUES (%s, %s, %s, %s, %s, %s)"
    )
    second = (owner.org, jane.user_id, new_token_hash(), INVITE_CODE, T0, T0 + WEEK)
    with pytest.raises(psycopg.errors.UniqueViolation) as caught:
        owner_conn.execute(insert, second)
    assert caught.value.diag.constraint_name == "uq_invitations_live"

    _reinvite(app_conn, owner, jane.user_id, now=T0 + MINUTE)
    _reinvite(app_conn, owner, jane.user_id, now=T0 + 2 * MINUTE)
    rows = _invitations(owner_conn, jane.user_id)
    assert [r["revoke_reason"] for r in rows] == ["replaced", "replaced", None]
    assert [r["revoked_at"] for r in rows] == [T0 + MINUTE, T0 + 2 * MINUTE, None]

    reused = (owner.org, jane.user_id, jane.token, INVITE_CODE, T0, T0 + WEEK)
    owner_conn.execute(
        "UPDATE identity.invitations SET revoked_at = %s, revoke_reason = 'replaced' "
        "WHERE user_id = %s AND revoked_at IS NULL",
        (T0, jane.user_id),
    )
    with pytest.raises(psycopg.errors.UniqueViolation):
        owner_conn.execute(insert, reused)


def test_the_app_role_reads_no_invitation_and_cannot_look_one_up_by_digest(
    app_conn: Conn, jane: Invited
) -> None:
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        app_conn.execute("SELECT count(*) FROM identity.invitations").fetchone()
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        app_conn.execute("SELECT identity.invitation_org(%s)", (jane.token,)).fetchone()


def test_the_executor_sees_only_the_invitations_of_the_organization_it_entered(
    executor: Conn, owner: Member, jane: Invited
) -> None:
    def count(organization: UUID) -> int:
        executor.execute(
            "SELECT set_config('xcode.organization_id', %s, false)", (str(organization),)
        )
        row = executor.execute("SELECT count(*) AS n FROM identity.invitations").fetchone()
        assert row is not None
        return int(row["n"])

    assert count(uuid4()) == 0
    assert count(owner.org) == 1


# --- the link step ---


def test_the_link_with_the_persons_number_stores_a_first_setup_code_for_the_device(
    app_conn: Conn, owner_conn: Conn, jane: Invited
) -> None:
    result = _redeem(app_conn, jane.token, device="phone-a", code_hash=NEW_CODE_HASH)
    assert result["outcome"] == "verification_required"
    assert (result["purpose"], result["masked_email"]) == ("first_setup", "j***@example.com")
    stored = codes(owner_conn, jane.user_id)
    assert [(c["purpose"], c["device_id"], c["code_hash"]) for c in stored] == [
        ("first_setup", "phone-a", NEW_CODE_HASH)
    ]
    assert str(stored[0]["id"]) == result["code_id"]
    assert stored[0]["expires_at"] == T0 + timedelta(minutes=10)
    last = attempts(owner_conn)[-1]
    assert (last["operation"], last["outcome"], last["user_id"]) == (
        "invite_redeem",
        "verification_required",
        jane.user_id,
    )
    assert _only(owner_conn, jane.user_id)["failed_attempts"] == 0


def test_an_unknown_link_an_unknown_number_and_another_persons_link_refuse_alike(
    app_conn: Conn, owner_conn: Conn, owner: Member, jane: Invited
) -> None:
    kim = _invite(app_conn, owner, **_person(1))
    unknown_link = _redeem(app_conn, new_token_hash())
    unknown_number = _redeem(app_conn, jane.token, phone=STRANGER)
    someone_elses = _redeem(app_conn, kim.token)
    assert unknown_link == unknown_number == someone_elses
    assert _refusal(unknown_link) == ("refused", "invite_invalid")
    assert unknown_link["masked_email"] is unknown_link["code_id"] is None

    rows = [a for a in attempts(owner_conn) if a["operation"] == "invite_redeem"]
    assert [(a["refusal"], a["user_id"]) for a in rows] == [("invite_invalid", None)] * 3
    assert _only(owner_conn, jane.user_id)["failed_attempts"] == 1
    assert _only(owner_conn, kim.user_id)["failed_attempts"] == 1
    assert codes(owner_conn, jane.user_id) == codes(owner_conn, kim.user_id) == []


def test_failed_tries_on_the_link_never_close_it_but_end_the_invitation_code(
    app_conn: Conn, owner_conn: Conn, jane: Invited
) -> None:
    for _ in range(5):
        assert _refusal(_redeem(app_conn, jane.token, phone=STRANGER)) == (
            "refused",
            "invite_invalid",
        )
    assert _only(owner_conn, jane.user_id)["failed_attempts"] == 5
    assert _redeem(app_conn, jane.token)["outcome"] == "verification_required"
    started = Auth(app_conn).start(phone=JANE, now=T0 + 2 * MINUTE)
    assert started.get("invitation") is None
    assert started["code_issued"] is True


def test_the_link_answers_used_revoked_and_expired_only_with_the_right_number(
    app_conn: Conn, owner_conn: Conn, owner: Member, jane: Invited
) -> None:
    assert _refusal(_redeem(app_conn, jane.token, now=T0 + WEEK + TICK)) == (
        "refused",
        "invite_expired",
    )
    assert _refusal(_redeem(app_conn, jane.token, phone=STRANGER, now=T0 + WEEK + TICK)) == (
        "refused",
        "invite_invalid",
    )

    _reinvite(app_conn, owner, jane.user_id)
    assert _refusal(_redeem(app_conn, jane.token)) == ("refused", "invite_revoked")

    newest = _live(owner_conn, jane.user_id)
    assert newest is not None
    set_user(owner_conn, jane.user_id, pin_hash=PIN_HASH)
    assert _refusal(_redeem(app_conn, newest["token_hash"])) == ("refused", "invite_used")
    assert codes(owner_conn, jane.user_id) == []
    refusals = [a["refusal"] for a in attempts(owner_conn) if a["operation"] == "invite_redeem"]
    assert refusals == ["invite_expired", "invite_invalid", "invite_revoked", "invite_used"]


def test_the_link_of_an_inactive_member_answers_revoked(
    app_conn: Conn, owner_conn: Conn, owner: Member, jane: Invited
) -> None:
    owner_conn.execute(
        "UPDATE tenancy.memberships SET active = false WHERE user_id = %s", (jane.user_id,)
    )
    assert _refusal(_redeem(app_conn, jane.token)) == ("refused", "invite_revoked")
    assert codes(owner_conn, jane.user_id) == []


def test_two_link_steps_at_once_leave_one_usable_code(
    app_url: str, owner_conn: Conn, jane: Invited
) -> None:
    first_code, late_code = digest("code:111111"), digest("code:222222")
    first, late = _race(
        app_url,
        lambda c: _redeem(c, jane.token, device="phone-a", code_hash=first_code),
        lambda c: _redeem(c, jane.token, device="phone-b", code_hash=late_code),
    )
    assert first["outcome"] == late["outcome"] == "verification_required"
    live = [c for c in codes(owner_conn, jane.user_id) if not c["consumed"]]
    assert [(c["device_id"], c["code_hash"]) for c in live] == [("phone-b", late_code)]


def test_two_first_pins_with_the_invitation_code_at_once_set_one_pin(
    app_url: str, owner_conn: Conn, jane: Invited
) -> None:
    other_pin = _pin_hash("other")

    def complete(device: str, pin_hash: str) -> Callable[[Conn], Any]:
        return lambda c: Auth(c).complete_pin(
            "first_setup", phone=JANE, device=device, code_hash=INVITE_CODE, pin_hash=pin_hash
        )

    first, late = _race(app_url, complete("phone-a", NEW_PIN_HASH), complete("phone-b", other_pin))
    assert first["outcome"] == "authenticated"
    assert _refusal(late) == ("refused", None)
    assert user_row(owner_conn, jane.user_id)["pin_hash"] == NEW_PIN_HASH
    assert _only(owner_conn, jane.user_id)["accepted_at"] == T0


def test_twenty_link_steps_at_once_leave_one_usable_code(
    app_url: str, owner_conn: Conn, jane: Invited
) -> None:
    hashes = [digest(f"code:{i:06d}") for i in range(CROWD)]

    def redeem(i: int) -> Callable[[Conn], Any]:
        return lambda c: _redeem(c, jane.token, device=f"phone-{i}", code_hash=hashes[i])

    results = _crowd(app_url, [redeem(i) for i in range(CROWD)])
    assert {r["outcome"] for r in results} == {"verification_required"}
    live = [c for c in codes(owner_conn, jane.user_id) if not c["consumed"]]
    assert len(live) == 1
    assert live[0]["code_hash"] == hashes[int(live[0]["device_id"].removeprefix("phone-"))]


def test_twenty_first_pins_with_the_invitation_code_at_once_set_one_pin(
    app_url: str, owner_conn: Conn, jane: Invited
) -> None:
    pins = [_pin_hash(str(i)) for i in range(CROWD)]

    def complete(i: int) -> Callable[[Conn], Any]:
        return lambda c: Auth(c).complete_pin(
            "first_setup",
            phone=JANE,
            device=f"phone-{i}",
            code_hash=INVITE_CODE,
            pin_hash=pins[i],
        )

    results = _crowd(app_url, [complete(i) for i in range(CROWD)])
    winners = [i for i, r in enumerate(results) if r["outcome"] == "authenticated"]
    assert len(winners) == 1
    assert {r["outcome"] for i, r in enumerate(results) if i != winners[0]} == {"refused"}
    assert user_row(owner_conn, jane.user_id)["pin_hash"] == pins[winners[0]]
    assert _only(owner_conn, jane.user_id)["accepted_at"] == T0


def test_the_outcome_adapter_reads_the_invitation_flag_and_defaults_it(
    app_conn: Conn, owner: Member, jane: Invited
) -> None:
    auth = Auth(app_conn)
    invited = auth_outcome(auth.start(phone=JANE))
    assert (invited.outcome, invited.purpose, invited.code_issued, invited.invitation) == (
        AuthOutcomeKind.VERIFICATION_REQUIRED,
        CodePurpose.FIRST_SETUP,
        False,
        True,
    )
    create_person(app_conn, owner, **_person(9))
    mailed = auth_outcome(auth.start(phone=_person(9)["phone"]))
    assert (mailed.code_issued, mailed.invitation) == (True, False)
    link = auth_outcome(_redeem(app_conn, new_token_hash()))
    assert (link.refusal, link.invitation) == (SignInRefusal.INVITE_INVALID, False)


# --- the invitation code as a first-setup code ---


def test_the_number_step_mails_no_code_while_the_invitation_is_usable(
    app_conn: Conn, owner_conn: Conn, owner: Member, jane: Invited
) -> None:
    auth = Auth(app_conn)
    started = auth.start(phone=JANE)
    assert started["outcome"] == "verification_required"
    assert (started["purpose"], started["code_issued"], started["invitation"]) == (
        "first_setup",
        False,
        True,
    )
    assert started["code_id"] is started["email"] is None
    assert codes(owner_conn, jane.user_id) == []

    plain = create_person(app_conn, owner, **_person(2))
    mailed = auth.start(phone=_person(2)["phone"])
    assert mailed["code_issued"] is True
    assert mailed.get("invitation") is None
    assert len(codes(owner_conn, plain["id"])) == 1


def test_the_invitation_code_verifies_and_a_first_pin_accepts_the_invitation(
    app_conn: Conn, owner_conn: Conn, owner: Member, jane: Invited
) -> None:
    auth = Auth(app_conn)
    checked = auth.check_code("first_setup", phone=JANE, device="phone", code_hash=INVITE_CODE)
    assert checked["outcome"] == "code_verified"
    stored = codes(owner_conn, jane.user_id)
    assert [(c["device_id"], c["code_hash"], c["consumed"]) for c in stored] == [
        ("phone", INVITE_CODE, False)
    ]
    assert _live(owner_conn, jane.user_id) is not None

    later = T0 + MINUTE
    completed = auth.complete_pin(
        "first_setup", phone=JANE, device="phone", code_hash=INVITE_CODE, now=later
    )
    assert completed["outcome"] == "authenticated"
    row = _only(owner_conn, jane.user_id)
    assert (row["accepted_at"], row["revoked_at"]) == (later, None)
    assert _refusal(_redeem(app_conn, jane.token)) == ("refused", "invite_used")
    _reinvite_refused(app_conn, owner, jane.user_id, "XC422", "people_invite_not_needed")
    status = _person_doc(app_conn, owner, jane.user_id, later)["status"]
    assert status not in ("invited", "invite_expired", "not_signed_in")


def test_five_wrong_codes_void_the_invitation_code_and_mail_one(
    app_conn: Conn, owner_conn: Conn, jane: Invited
) -> None:
    auth = Auth(app_conn)
    for left in (4, 3, 2, 1):
        wrong = auth.check_code("first_setup", phone=JANE, code_hash=WRONG_CODE_HASH)
        assert (wrong["outcome"], wrong["refusal"], wrong["tries_left"]) == (
            "refused",
            "wrong_code",
            left,
        )
    assert codes(owner_conn, jane.user_id) == []
    fifth = auth.check_code(
        "first_setup", phone=JANE, code_hash=WRONG_CODE_HASH, replacement_hash=NEW_CODE_HASH
    )
    assert (fifth["outcome"], fifth["refusal"], fifth["code_issued"]) == (
        "code_resent",
        "wrong_code",
        True,
    )
    row = _live(owner_conn, jane.user_id)
    assert row is not None
    assert row["failed_attempts"] == 5

    late = auth.check_code("first_setup", phone=JANE, code_hash=INVITE_CODE)
    assert _refusal(late) == ("refused", "wrong_code")
    assert auth.check_code("first_setup", phone=JANE, code_hash=NEW_CODE_HASH)["outcome"] == (
        "code_verified"
    )
    assert _only(owner_conn, jane.user_id)["failed_attempts"] == 5
    assert auth.start(phone=JANE, now=T0 + timedelta(hours=1)).get("invitation") is None


def test_with_a_device_code_the_tries_left_are_the_fewer_of_the_two(
    app_conn: Conn, owner_conn: Conn, jane: Invited
) -> None:
    auth = Auth(app_conn)
    _redeem(app_conn, jane.token, code_hash=NEW_CODE_HASH)
    first = auth.check_code("first_setup", phone=JANE, code_hash=WRONG_CODE_HASH)
    assert (first["refusal"], first["tries_left"]) == ("wrong_code", 2)
    assert _only(owner_conn, jane.user_id)["failed_attempts"] == 1
    assert auth.check_code("first_setup", phone=JANE, code_hash=INVITE_CODE)["outcome"] == (
        "code_verified"
    )


def test_the_invitation_works_until_expires_at_and_not_a_tick_after(
    app_conn: Conn, owner_conn: Conn, owner: Member, jane: Invited
) -> None:
    auth = Auth(app_conn)
    edge, past = T0 + WEEK, T0 + WEEK + TICK

    assert auth.start(phone=JANE, now=edge)["invitation"] is True
    document = _person_doc(app_conn, owner, jane.user_id, edge)
    pane = document["sign_in"]["invitation"]
    assert (document["status"], pane["state"], pane["sent_at"]) == ("invited", "pending", None)
    assert datetime.fromisoformat(pane["expires_at"]) == edge
    assert _start(app_conn, jane.token, edge) is not None

    expired = auth.start(phone=JANE, now=past)
    assert expired.get("invitation") is None
    assert expired["code_issued"] is True
    document = _person_doc(app_conn, owner, jane.user_id, past)
    assert document["status"] == "invite_expired"
    assert document["sign_in"]["invitation"]["state"] == "expired"
    assert _start(app_conn, jane.token, past) is None
    assert _refusal(_redeem(app_conn, jane.token, now=past)) == ("refused", "invite_expired")
    wrong = auth.check_code("first_setup", phone=JANE, code_hash=INVITE_CODE, now=past)
    assert _refusal(wrong) == ("refused", "wrong_code")
    assert _only(owner_conn, jane.user_id)["failed_attempts"] == 0


def test_the_invitation_code_at_expires_at_still_verifies(app_conn: Conn, jane: Invited) -> None:
    checked = Auth(app_conn).check_code(
        "first_setup", phone=JANE, code_hash=INVITE_CODE, now=T0 + WEEK
    )
    assert checked["outcome"] == "code_verified"


def test_people_list_filters_invited_and_expired_people(
    app_conn: Conn, owner: Member, jane: Invited
) -> None:
    def ids(status: str, now: datetime) -> list[str]:
        page = call(app_conn, "people_list", owner.id, owner.org, REQUEST, 1, 50, None, status, now)
        return [item["id"] for item in page["items"]]

    assert ids("invited", T0) == [str(jane.user_id)]
    assert ids("invite_expired", T0) == []
    assert ids("invited", T0 + WEEK + TICK) == []
    assert ids("invite_expired", T0 + WEEK + TICK) == [str(jane.user_id)]
    assert str(jane.user_id) not in ids("not_signed_in", T0)


# --- sending the invitation again ---


def test_sending_again_replaces_the_live_invitation_and_is_logged(
    app_conn: Conn, owner_conn: Conn, owner: Member, jane: Invited
) -> None:
    token = new_token_hash()
    later = T0 + MINUTE
    row = _reinvite(app_conn, owner, jane.user_id, token=token, now=later)
    assert (row["id"], row["version"], row["outcome"]) == (jane.user_id, 1, "updated")
    old, new = _invitations(owner_conn, jane.user_id)
    assert (old["revoked_at"], old["revoke_reason"]) == (later, "replaced")
    assert (new["token_hash"], new["created_at"], new["expires_at"]) == (token, later, later + WEEK)
    assert (new["delivery_state"], new["failed_attempts"]) == ("pending", 0)

    entry = change_log(owner_conn, owner.org)[-1]
    assert (entry["section"], entry["entity_id"], entry["actor_id"], entry["reason"]) == (
        "signIn",
        jane.user_id,
        owner.id,
        "Invitation sent, Jane Njeri",
    )
    assert [e["action"] for e in audit_events(owner_conn, owner.org, "person.invited")] == [
        "person.invited"
    ]
    assert _redeem(app_conn, token, now=later)["outcome"] == "verification_required"


def test_sending_again_gives_a_voided_invitation_fresh_tries(
    app_conn: Conn, owner_conn: Conn, owner: Member, jane: Invited
) -> None:
    owner_conn.execute(
        "UPDATE identity.invitations SET failed_attempts = 5 WHERE user_id = %s", (jane.user_id,)
    )
    assert Auth(app_conn).start(phone=JANE).get("invitation") is None
    _reinvite(app_conn, owner, jane.user_id, now=T0 + MINUTE)
    assert Auth(app_conn).start(phone=JANE, now=T0 + MINUTE)["invitation"] is True


def test_a_person_never_invited_can_be_sent_an_invitation(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    plain = create_person(app_conn, owner)
    _reinvite(app_conn, owner, plain["id"])
    assert _only(owner_conn, plain["id"])["delivery_state"] == "pending"


def test_sending_again_refuses_oneself_unknown_people_and_another_organizations_person(
    app_conn: Conn, owner_conn: Conn, owner: Member, jane: Invited
) -> None:
    elsewhere = _elsewhere(owner_conn)
    owner_conn.execute(
        "UPDATE identity.users SET pin_hash = NULL WHERE id = %s", (elsewhere.user2,)
    )
    _reinvite_refused(app_conn, owner, owner.id, "XC422", "people_self_sign_in")
    _reinvite_refused(app_conn, owner, uuid4(), "XC404", "not_found")
    _reinvite_refused(app_conn, owner, None, "XC404", "not_found")
    _reinvite_refused(app_conn, owner, elsewhere.user2, "XC404", "not_found")
    assert _invitations(owner_conn, elsewhere.user2) == []
    assert len(_invitations(owner_conn, jane.user_id)) == 1


def test_sending_again_refuses_the_owner_to_others_and_people_who_need_none(
    app_conn: Conn, owner_conn: Conn, owner: Member, office: Member, clerk: Member, jane: Invited
) -> None:
    _reinvite_refused(app_conn, office, owner.id, "XC403", "people_owner_edit")
    _reinvite_refused(app_conn, clerk, jane.user_id, "XC403", "permission_missing")

    pinned = create_person(app_conn, owner, **_person(3))
    set_user(owner_conn, pinned["id"], pin_hash=PIN_HASH)
    _reinvite_refused(app_conn, owner, pinned["id"], "XC422", "people_invite_not_needed")

    _set_active(app_conn, owner, jane.user_id, False, 1, "Left")
    _reinvite_refused(app_conn, owner, jane.user_id, "XC422", "people_invite_not_needed")
    assert _invitations(owner_conn, owner.id) == _invitations(owner_conn, pinned["id"]) == []
    assert _live(owner_conn, jane.user_id) is None


# --- revocation ---


def test_blocking_a_person_revokes_the_invitation_and_reactivating_keeps_it_revoked(
    app_conn: Conn, owner_conn: Conn, owner: Member, jane: Invited
) -> None:
    _set_active(app_conn, owner, jane.user_id, False, 1, "Left")
    row = _only(owner_conn, jane.user_id)
    assert (row["revoked_at"], row["revoke_reason"]) == (T0, "blocked")
    assert _refusal(_redeem(app_conn, jane.token)) == ("refused", "invite_revoked")

    _set_active(app_conn, owner, jane.user_id, True, 2, None)
    assert _live(owner_conn, jane.user_id) is None
    started = Auth(app_conn).start(phone=JANE)
    assert started.get("invitation") is None
    assert started["code_issued"] is True


def test_removing_a_user_revokes_the_invitation(
    app_conn: Conn, operator_conn: Conn, owner_conn: Conn, jane: Invited
) -> None:
    call(operator_conn, "ops_remove_user", "test-operator", "req", "jane@example.com", T0)
    row = _only(owner_conn, jane.user_id)
    assert (row["revoked_at"], row["revoke_reason"]) == (T0, "removed")
    assert _refusal(_redeem(app_conn, jane.token)) == ("refused", "invite_revoked")


def test_a_new_email_revokes_the_invitation_and_invites_the_new_address(
    app_conn: Conn, owner_conn: Conn, owner: Member, jane: Invited
) -> None:
    token = new_token_hash()
    later = T0 + MINUTE
    update_person(
        app_conn,
        owner,
        jane.user_id,
        1,
        email="jane.new@example.com",
        invite_token_hash=token,
        invite_code_hash=INVITE_CODE,
        now=later,
    )
    old, new = _invitations(owner_conn, jane.user_id)
    assert (old["revoked_at"], old["revoke_reason"]) == (later, "email_changed")
    assert (new["token_hash"], new["invited_by"], new["expires_at"]) == (
        token,
        owner.id,
        later + WEEK,
    )
    assert _refusal(_redeem(app_conn, jane.token, now=later)) == ("refused", "invite_revoked")
    delivery = _start(app_conn, token, later)
    assert delivery is not None
    assert delivery["email"] == "jane.new@example.com"


def test_a_new_email_without_digests_only_revokes(
    app_conn: Conn, owner_conn: Conn, owner: Member, jane: Invited
) -> None:
    update_person(app_conn, owner, jane.user_id, 1, email="jane.new@example.com")
    row = _only(owner_conn, jane.user_id)
    assert row["revoke_reason"] == "email_changed"


def test_an_edit_that_keeps_the_email_keeps_the_invitation(
    app_conn: Conn, owner_conn: Conn, owner: Member, jane: Invited
) -> None:
    update_person(
        app_conn,
        owner,
        jane.user_id,
        1,
        last_name="Wanjiru",
        invite_token_hash=new_token_hash(),
        invite_code_hash=INVITE_CODE,
    )
    row = _only(owner_conn, jane.user_id)
    assert (row["token_hash"], row["revoked_at"]) == (jane.token, None)


def test_a_new_email_invites_nobody_who_was_never_invited_or_has_accepted(
    app_conn: Conn, owner_conn: Conn, owner: Member, jane: Invited
) -> None:
    plain = create_person(app_conn, owner, **_person(4))
    update_person(
        app_conn,
        owner,
        plain["id"],
        1,
        **{**_person(4), "email": "pat4.new@example.com"},
        invite_token_hash=new_token_hash(),
        invite_code_hash=INVITE_CODE,
    )
    assert _invitations(owner_conn, plain["id"]) == []

    Auth(app_conn).complete_pin("first_setup", phone=JANE, code_hash=INVITE_CODE)
    update_person(
        app_conn,
        owner,
        jane.user_id,
        1,
        email="jane.new@example.com",
        invite_token_hash=new_token_hash(),
        invite_code_hash=INVITE_CODE,
    )
    row = _only(owner_conn, jane.user_id)
    assert (row["accepted_at"], row["revoked_at"]) == (T0, None)


# --- delivery ---


def test_a_send_starts_once_per_pending_live_invitation_with_what_the_email_needs(
    app_conn: Conn, owner_conn: Conn, owner: Member, jane: Invited
) -> None:
    organization = owner_conn.execute(
        "SELECT o.name, b.support_email, coalesce(l.time_zone, 'Africa/Nairobi') AS time_zone "
        "FROM tenancy.organizations AS o "
        "LEFT JOIN tenancy.organization_brandings AS b ON b.organization_id = o.id "
        "LEFT JOIN tenancy.organization_localizations AS l ON l.organization_id = o.id "
        "WHERE o.id = %s",
        (owner.org,),
    ).fetchone()
    assert organization is not None
    later = T0 + MINUTE
    delivery = _start(app_conn, jane.token, later)
    assert delivery is not None
    row = _only(owner_conn, jane.user_id)
    assert datetime.fromisoformat(delivery.pop("expires_at")) == T0 + WEEK
    assert delivery == {
        "invitation_id": str(row["id"]),
        "email": "jane@example.com",
        "first_name": "Jane",
        "organization_name": organization["name"],
        "inviter_name": "Olive Owner",
        "support_email": organization["support_email"],
        "time_zone": organization["time_zone"],
    }
    assert (row["attempted_at"], row["delivery_attempts"], row["delivery_state"]) == (
        later,
        1,
        "pending",
    )
    assert _start(app_conn, new_token_hash(), later) is None


def test_a_sent_invitation_starts_no_second_send(
    app_conn: Conn, owner_conn: Conn, jane: Invited
) -> None:
    _start(app_conn, jane.token)
    _result(app_conn, jane.token, True, T0 + MINUTE)
    row = _only(owner_conn, jane.user_id)
    assert (row["delivery_state"], row["sent_at"]) == ("sent", T0 + MINUTE)
    assert _start(app_conn, jane.token, T0 + 2 * MINUTE) is None
    _result(app_conn, jane.token, False, T0 + 2 * MINUTE)
    assert _only(owner_conn, jane.user_id)["delivery_state"] == "sent"


def test_no_send_starts_for_a_revoked_or_accepted_invitation(
    app_conn: Conn, owner_conn: Conn, owner: Member, jane: Invited
) -> None:
    _reinvite(app_conn, owner, jane.user_id)
    assert _start(app_conn, jane.token) is None
    newest = _live(owner_conn, jane.user_id)
    assert newest is not None
    Auth(app_conn).complete_pin("first_setup", phone=JANE, code_hash=INVITE_CODE)
    assert _start(app_conn, newest["token_hash"]) is None
    assert [r["delivery_attempts"] for r in _invitations(owner_conn, jane.user_id)] == [0, 0]


def test_a_failed_send_stays_pending_until_the_fifth_attempt(
    app_conn: Conn, owner_conn: Conn, jane: Invited
) -> None:
    _start(app_conn, jane.token)
    _result(app_conn, jane.token, False)
    assert _only(owner_conn, jane.user_id)["delivery_state"] == "pending"
    owner_conn.execute(
        "UPDATE identity.invitations SET delivery_attempts = 5 WHERE user_id = %s",
        (jane.user_id,),
    )
    _result(app_conn, jane.token, False)
    assert _only(owner_conn, jane.user_id)["delivery_state"] == "failed"
    _result(app_conn, jane.token, True)
    row = _only(owner_conn, jane.user_id)
    assert (row["delivery_state"], row["sent_at"]) == ("failed", None)
    assert _start(app_conn, jane.token) is None


def test_the_sweep_claims_the_oldest_quiet_invitations_up_to_the_pairs_given(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    people = [_invite(app_conn, owner, now=T0 + i * MINUTE, **_person(10 + i)) for i in range(4)]
    _start(app_conn, people[0].token, T0 + 5 * MINUTE)
    tokens, code_hashes = _pairs(2)

    claimed = _claim(app_conn, T0 + 9 * MINUTE, 10, tokens, code_hashes)

    assert [c["pair_index"] for c in claimed] == [0, 1]
    assert [c["email"] for c in claimed] == ["pat11@example.com", "pat12@example.com"]
    for person, token, code_hash in zip(people[1:3], tokens, code_hashes, strict=True):
        row = _only(owner_conn, person.user_id)
        assert (row["token_hash"], row["code_hash"]) == (token, code_hash)
        assert (row["attempted_at"], row["delivery_attempts"]) == (T0 + 9 * MINUTE, 1)
    untouched = [_only(owner_conn, p.user_id) for p in (people[0], people[3])]
    assert [r["delivery_attempts"] for r in untouched] == [1, 0]
    assert untouched[1]["token_hash"] == people[3].token


def test_the_sweep_skips_sent_and_recent_invitations_and_claims_nothing_without_pairs(
    app_conn: Conn, owner_conn: Conn, owner: Member, jane: Invited
) -> None:
    kim = _invite(app_conn, owner, **_person(5))
    _start(app_conn, kim.token)
    _result(app_conn, kim.token, True)
    tokens, code_hashes = _pairs(2)
    assert _claim(app_conn, T0 + 4 * MINUTE, 10, tokens, code_hashes) == []
    assert _claim(app_conn, T0 + 6 * MINUTE, 0, tokens, code_hashes) == []
    assert _claim(app_conn, T0 + 6 * MINUTE, None, tokens, code_hashes) == []
    assert _claim(app_conn, T0 + 6 * MINUTE, 10, tokens, []) == []
    one = _claim(app_conn, T0 + 6 * MINUTE, 10, tokens, code_hashes[:1])
    assert [c["email"] for c in one] == ["jane@example.com"]
    assert _only(owner_conn, kim.user_id)["token_hash"] == kim.token


def test_the_sweep_gives_up_on_expired_and_spent_invitations_without_a_pair(
    app_conn: Conn, owner_conn: Conn, owner: Member, jane: Invited
) -> None:
    spent = _invite(app_conn, owner, now=T0 + MINUTE, **_person(6))
    fresh = _invite(app_conn, owner, now=T0 + WEEK, **_person(7))
    owner_conn.execute(
        "UPDATE identity.invitations SET delivery_attempts = 5 WHERE user_id = %s",
        (spent.user_id,),
    )
    tokens, code_hashes = _pairs(3)

    claimed = _claim(app_conn, T0 + WEEK + 6 * MINUTE, 10, tokens, code_hashes)

    assert [(c["pair_index"], c["email"]) for c in claimed] == [(0, "pat7@example.com")]
    for person in (jane, spent):
        row = _only(owner_conn, person.user_id)
        assert (row["delivery_state"], row["token_hash"]) == ("failed", person.token)
    assert _only(owner_conn, fresh.user_id)["token_hash"] == tokens[0]


def test_the_sweep_skips_an_invitation_another_sweep_holds(
    app_conn: Conn, owner_url: str, owner_conn: Conn, owner: Member, jane: Invited
) -> None:
    kim = _invite(app_conn, owner, now=T0 + MINUTE, **_person(8))
    app_conn.execute("SET statement_timeout = '5s'")
    tokens, code_hashes = _pairs(2)
    with psycopg.connect(owner_url, autocommit=True, row_factory=dict_row) as holder:
        with holder.transaction():
            holder.execute(
                "SELECT 1 FROM identity.invitations WHERE user_id = %s FOR UPDATE",
                (jane.user_id,),
            )
            claimed = _claim(app_conn, T0 + 7 * MINUTE, 10, tokens, code_hashes)
    assert [(c["pair_index"], c["email"]) for c in claimed] == [(0, "pat8@example.com")]
    assert _only(owner_conn, jane.user_id)["token_hash"] == jane.token
    assert _only(owner_conn, kim.user_id)["token_hash"] == tokens[0]


def test_the_sweep_enters_every_organization_and_numbers_the_pairs_across_them(
    app_conn: Conn, owner_conn: Conn, jane: Invited
) -> None:
    elsewhere = _elsewhere(owner_conn)
    owner_conn.execute(
        "INSERT INTO identity.invitations "
        "(organization_id, user_id, token_hash, code_hash, created_at, expires_at) "
        "VALUES (%s, %s, %s, %s, %s, %s)",
        (elsewhere.org, elsewhere.user2, new_token_hash(), INVITE_CODE, T0, T0 + WEEK),
    )
    tokens, code_hashes = _pairs(3)

    claimed = _claim(app_conn, T0 + 6 * MINUTE, 10, tokens, code_hashes)

    assert sorted(c["pair_index"] for c in claimed) == [0, 1]
    users = set()
    for item in claimed:
        row = owner_conn.execute(
            "SELECT * FROM identity.invitations WHERE id = %s", (item["invitation_id"],)
        ).fetchone()
        assert row is not None
        assert (row["token_hash"], row["code_hash"]) == (
            tokens[item["pair_index"]],
            code_hashes[item["pair_index"]],
        )
        users.add(row["user_id"])
    assert users == {jane.user_id, elsewhere.user2}
    assert "Clara" in {item["first_name"] for item in claimed}


def test_a_late_result_for_a_digest_the_sweep_replaced_changes_nothing(
    app_conn: Conn, owner_conn: Conn, jane: Invited
) -> None:
    _start(app_conn, jane.token)
    tokens, code_hashes = _pairs(1)
    _claim(app_conn, T0 + 6 * MINUTE, 10, tokens, code_hashes)

    _result(app_conn, jane.token, True, T0 + 7 * MINUTE)
    row = _only(owner_conn, jane.user_id)
    assert (row["delivery_state"], row["sent_at"], row["delivery_attempts"]) == ("pending", None, 2)
    assert _refusal(_redeem(app_conn, jane.token)) == ("refused", "invite_invalid")
    auth = Auth(app_conn)
    assert _refusal(auth.check_code("first_setup", phone=JANE, code_hash=INVITE_CODE)) == (
        "refused",
        "wrong_code",
    )

    _result(app_conn, tokens[0], True, T0 + 8 * MINUTE)
    row = _only(owner_conn, jane.user_id)
    assert (row["delivery_state"], row["sent_at"]) == ("sent", T0 + 8 * MINUTE)
    checked = auth.check_code("first_setup", phone=JANE, code_hash=code_hashes[0])
    assert checked["outcome"] == "code_verified"
