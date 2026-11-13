"""The sign-in notice outbox (``tenancy.sign_in_notices``, ``api.sign_in_notice_claim``,
``api.sign_in_notice_result``): for an account with a PIN set, a new sign-in email writes a
pending notice to the old and to the new address, a new mobile number alone one to the current
address, and any other change none. An account without a PIN has never signed in, so it gets none.
Right after the change the API claims that person's unsent notices; the sweep claims what is
still pending 5 minutes after its last send. A send records sent; five failed sends end it
failed. Sent, failed or dropped, the address is gone. A 'new' or 'current' notice whose address
is no longer the account's email is dropped, and an erasure drops the person's pending ones."""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest

from ..support.rows import seed_organization
from ..support.scenario import PIN_HASH, T0, Conn, call, set_user
from ..support.tenancy import (
    REQUEST,
    Member,
    create_person,
    provision_member,
    update_person,
    write,
)

ROWS = (
    "SELECT id, user_id, actor_id, kind, address, state, attempts, attempted_at, sent_at "
    "FROM tenancy.sign_in_notices WHERE organization_id = %s ORDER BY created_at, kind"
)


@pytest.fixture
def owner(operator_conn: Conn) -> Member:
    return provision_member(operator_conn, 1, "Owner", "Olive", "Owner")


@pytest.fixture
def clerk(operator_conn: Conn, owner: Member) -> Member:
    return provision_member(operator_conn, 4, "Revenue clerk", "Cleo", "Clerk")


def _rows(owner_conn: Conn, org: UUID) -> list[dict[str, Any]]:
    return owner_conn.execute(ROWS, (org,)).fetchall()


def _sent_to(owner_conn: Conn, org: UUID) -> list[tuple[str, str | None]]:
    return [(r["kind"], r["address"]) for r in _rows(owner_conn, org)]


def _claim(
    app: Conn, now: Any, actor: Member | None = None, user: UUID | None = None
) -> list[dict[str, Any]]:
    tenant = (actor.id, actor.org, REQUEST) if actor is not None else (None, None, None)
    claimed: list[dict[str, Any]] = call(app, "sign_in_notice_claim", now, 100, *tenant, user)
    return claimed


def _claim_refused(
    app: Conn, tenant: tuple[UUID | None, UUID | None, str | None], user: UUID, code: str
) -> None:
    with pytest.raises(psycopg.Error) as caught:
        call(app, "sign_in_notice_claim", T0, 100, *tenant, user)
    assert caught.value.sqlstate == "XC403"
    assert caught.value.diag.message_primary == code


def _swept(app: Conn, now: Any, org: UUID) -> list[dict[str, Any]]:
    return [n for n in _claim(app, now) if n["organization_id"] == str(org)]


def _org_name(owner_conn: Conn, org: UUID) -> str:
    row = owner_conn.execute("SELECT name FROM tenancy.organizations WHERE id = %s", (org,))
    found = row.fetchone()
    assert found is not None
    return str(found["name"])


def _with_pin(owner_conn: Conn, user_id: UUID) -> UUID:
    set_user(owner_conn, user_id, pin_hash=PIN_HASH)
    return user_id


def _jane(app_conn: Conn, owner_conn: Conn, owner: Member) -> UUID:
    return _with_pin(owner_conn, create_person(app_conn, owner)["id"])


def test_a_new_email_writes_a_notice_to_the_old_and_to_the_new_address(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    jane = _jane(app_conn, owner_conn, owner)
    update_person(app_conn, owner, jane, 1, email="janet@example.com")
    rows = _rows(owner_conn, owner.org)
    assert sorted((r["kind"], r["address"]) for r in rows) == [
        ("new", "janet@example.com"),
        ("old", "jane@example.com"),
    ]
    for row in rows:
        assert (row["user_id"], row["actor_id"]) == (jane, owner.id)
        assert (row["state"], row["attempts"], row["attempted_at"]) == ("pending", 0, None)


def test_a_new_email_and_number_together_write_only_the_email_notices(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    jane = _jane(app_conn, owner_conn, owner)
    update_person(app_conn, owner, jane, 1, email="janet@example.com", phone="0722000222")
    assert sorted(_sent_to(owner_conn, owner.org)) == [
        ("new", "janet@example.com"),
        ("old", "jane@example.com"),
    ]


def test_a_new_number_alone_writes_one_notice_to_the_current_address(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    jane = _jane(app_conn, owner_conn, owner)
    update_person(app_conn, owner, jane, 1, phone="0722000222")
    assert _sent_to(owner_conn, owner.org) == [("current", "jane@example.com")]


@pytest.mark.parametrize(
    "fields",
    [{"last_name": "Wanjiru"}, {}],
    ids=["name", "unchanged"],
)
def test_a_change_that_keeps_the_sign_in_details_writes_no_notice(
    app_conn: Conn, owner_conn: Conn, owner: Member, fields: dict[str, Any]
) -> None:
    jane = _jane(app_conn, owner_conn, owner)
    update_person(app_conn, owner, jane, 1, **fields)
    assert _rows(owner_conn, owner.org) == []


@pytest.mark.parametrize(
    "fields",
    [
        {"email": "paula@example.com"},
        {"phone": "0722000444"},
        {"email": "paula@example.com", "phone": "0722000444"},
    ],
    ids=["email", "number", "both"],
)
def test_a_person_without_a_pin_gets_no_notice_and_one_with_a_pin_still_does(
    app_conn: Conn, owner_conn: Conn, owner: Member, fields: dict[str, Any]
) -> None:
    jane = _jane(app_conn, owner_conn, owner)
    paul = create_person(
        app_conn, owner, first_name="Paul", email="paul@example.com", phone="0722000333"
    )["id"]
    jane_fields = {k: {"email": "janet@example.com", "phone": "0722000222"}[k] for k in fields}
    paul_fields = {"email": "paul@example.com", "phone": "0722000333", **fields}
    assert update_person(app_conn, owner, paul, 1, first_name="Paul", **paul_fields)["outcome"] == (
        "updated"
    )
    update_person(app_conn, owner, jane, 1, **jane_fields)
    rows = _rows(owner_conn, owner.org)
    assert {r["user_id"] for r in rows} == {jane}
    assert {r["kind"] for r in rows} == (
        {"current"} if list(fields) == ["phone"] else {"old", "new"}
    )


def test_a_new_person_gets_no_notice(app_conn: Conn, owner_conn: Conn, owner: Member) -> None:
    _jane(app_conn, owner_conn, owner)
    assert _rows(owner_conn, owner.org) == []


def test_the_claim_after_the_change_takes_that_persons_unsent_notices_once(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    jane = _jane(app_conn, owner_conn, owner)
    paul = _with_pin(
        owner_conn,
        create_person(
            app_conn, owner, first_name="Paul", email="paul@example.com", phone="0722000333"
        )["id"],
    )
    update_person(app_conn, owner, jane, 1, email="janet@example.com")
    update_person(
        app_conn, owner, paul, 1, first_name="Paul", email="paul@example.com", phone="0722000444"
    )

    claimed = _claim(app_conn, T0, owner, jane)
    common = {
        "organization_id": str(owner.org),
        "first_name": "Jane",
        "actor_name": "Olive Owner",
        "organization_name": _org_name(owner_conn, owner.org),
    }
    assert sorted(
        ({k: v for k, v in n.items() if k != "notice_id"} for n in claimed),
        key=lambda n: n["kind"],
    ) == [
        {**common, "address": "janet@example.com", "kind": "new", "new_address_hint": None},
        {
            **common,
            "address": "jane@example.com",
            "kind": "old",
            "new_address_hint": "j***@example.com",
        },
    ]
    assert _claim(app_conn, T0, owner, jane) == []
    by_user = {(r["user_id"], r["kind"]): r for r in _rows(owner_conn, owner.org)}
    assert {
        (by_user[jane, k]["attempts"], by_user[jane, k]["attempted_at"]) for k in ("old", "new")
    } == {(1, T0)}
    assert by_user[paul, "current"]["attempts"] == 0


def test_the_claim_after_a_change_needs_people_edit_in_the_organization_it_names(
    app_conn: Conn, owner_conn: Conn, owner: Member, clerk: Member
) -> None:
    jane = _jane(app_conn, owner_conn, owner)
    update_person(app_conn, owner, jane, 1, email="janet@example.com")
    other = seed_organization(owner_conn)
    _claim_refused(app_conn, (owner.id, other.org, REQUEST), jane, "not_member")
    _claim_refused(app_conn, (clerk.id, clerk.org, REQUEST), jane, "permission_missing")
    _claim_refused(app_conn, (None, None, None), jane, "not_member")
    assert {r["attempts"] for r in _rows(owner_conn, owner.org)} == {0}


def test_a_claim_in_the_organization_without_a_person_takes_nothing(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    jane = _jane(app_conn, owner_conn, owner)
    update_person(app_conn, owner, jane, 1, phone="0722000222")
    assert _claim(app_conn, T0 + timedelta(hours=1), owner) == []
    assert _rows(owner_conn, owner.org)[0]["attempts"] == 0


def test_the_sweep_sends_what_is_still_pending_five_minutes_after_its_last_send(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    jane = _jane(app_conn, owner_conn, owner)
    update_person(app_conn, owner, jane, 1, phone="0722000222")
    assert _swept(app_conn, T0 + timedelta(minutes=4), owner.org) == []
    (first,) = _swept(app_conn, T0 + timedelta(minutes=6), owner.org)
    assert (first["kind"], first["address"]) == ("current", "jane@example.com")
    assert _swept(app_conn, T0 + timedelta(minutes=10), owner.org) == []
    (again,) = _swept(app_conn, T0 + timedelta(minutes=12), owner.org)
    assert again["notice_id"] == first["notice_id"]
    assert _rows(owner_conn, owner.org)[0]["attempts"] == 2


def test_a_sent_notice_keeps_no_address_and_is_not_sent_again(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    jane = _jane(app_conn, owner_conn, owner)
    update_person(app_conn, owner, jane, 1, phone="0722000222")
    (notice,) = _claim(app_conn, T0, owner, jane)
    sent_at = T0 + timedelta(seconds=3)
    call(app_conn, "sign_in_notice_result", notice["notice_id"], True, sent_at)
    (row,) = _rows(owner_conn, owner.org)
    assert (row["state"], row["address"], row["sent_at"]) == ("sent", None, sent_at)
    assert _swept(app_conn, T0 + timedelta(hours=1), owner.org) == []
    call(app_conn, "sign_in_notice_result", notice["notice_id"], False, sent_at)
    assert _rows(owner_conn, owner.org)[0]["state"] == "sent"


def test_a_notice_never_sent_fails_after_five_sends_and_keeps_no_address(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    jane = _jane(app_conn, owner_conn, owner)
    update_person(app_conn, owner, jane, 1, phone="0722000222")
    (notice,) = _claim(app_conn, T0, owner, jane)
    call(app_conn, "sign_in_notice_result", notice["notice_id"], False, T0)
    now = T0
    for _ in range(4):
        assert _rows(owner_conn, owner.org)[0]["state"] == "pending"
        now += timedelta(minutes=6)
        (again,) = _swept(app_conn, now, owner.org)
        call(app_conn, "sign_in_notice_result", again["notice_id"], False, now)
    (row,) = _rows(owner_conn, owner.org)
    assert (row["state"], row["attempts"], row["address"]) == ("failed", 5, None)
    assert _swept(app_conn, now + timedelta(hours=1), owner.org) == []


def test_a_notice_whose_sends_ran_out_unrecorded_ends_failed_at_the_next_claim(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    jane = _jane(app_conn, owner_conn, owner)
    update_person(app_conn, owner, jane, 1, phone="0722000222")
    owner_conn.execute(
        "UPDATE tenancy.sign_in_notices SET attempts = 5, attempted_at = %s "
        "WHERE organization_id = %s",
        (T0, owner.org),
    )
    assert _swept(app_conn, T0 + timedelta(minutes=6), owner.org) == []
    (row,) = _rows(owner_conn, owner.org)
    assert (row["state"], row["address"]) == ("failed", None)


def test_a_new_address_replaced_before_its_send_is_dropped(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    jane = _jane(app_conn, owner_conn, owner)
    update_person(app_conn, owner, jane, 1, email="janet@example.com")
    update_person(app_conn, owner, jane, 2, email="june@example.com")
    claimed = _claim(app_conn, T0, owner, jane)
    assert sorted((n["kind"], n["address"], n["new_address_hint"]) for n in claimed) == [
        ("new", "june@example.com", None),
        ("old", "jane@example.com", "j***@example.com"),
        ("old", "janet@example.com", "j***@example.com"),
    ]
    dropped = [r for r in _rows(owner_conn, owner.org) if r["state"] == "dropped"]
    assert [(r["kind"], r["address"], r["attempts"]) for r in dropped] == [("new", None, 0)]


def test_a_notice_whose_actor_is_gone_names_no_one(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    jane = _jane(app_conn, owner_conn, owner)
    update_person(app_conn, owner, jane, 1, phone="0722000222")
    owner_conn.execute(
        "UPDATE tenancy.sign_in_notices SET actor_id = NULL WHERE organization_id = %s",
        (owner.org,),
    )
    (notice,) = _claim(app_conn, T0, owner, jane)
    assert (notice["kind"], notice["actor_name"]) == ("current", None)


def test_an_erasure_drops_the_persons_pending_notices_and_their_addresses(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    jane = _jane(app_conn, owner_conn, owner)
    update_person(app_conn, owner, jane, 1, email="janet@example.com")
    write(
        app_conn,
        "people_set_active",
        owner.id,
        owner.org,
        REQUEST,
        jane,
        False,
        2,
        "Asked to leave",
        T0,
    )
    write(app_conn, "people_erase", owner.id, owner.org, REQUEST, jane, 3, "Asked to go", T0)
    rows = _rows(owner_conn, owner.org)
    assert {(r["state"], r["address"]) for r in rows} == {("dropped", None)}
    assert len(rows) == 2
    assert _claim(app_conn, T0, owner, jane) == []


def test_recording_an_unknown_notice_changes_nothing(app_conn: Conn) -> None:
    call(app_conn, "sign_in_notice_result", uuid4(), True, T0)
