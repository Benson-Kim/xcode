"""The self-service account-deletion routine (``api.me_deletion_request``): it records the
member's own "Delete my account" once, names the administrators who can block members
(``people.block``, the right blocking and erasing need) for the after-commit notice (the
requester and members without that right excluded, inactive members and removed accounts left
out), and makes a repeat within 24 hours a no-op so the administrators' inbox cannot be
flooded. The requester's membership is locked first, so two requests at once serialise and only
one is recorded (``docs/05-routines.md``; ``docs/06-http-contract.md`` section 2.2)."""

from __future__ import annotations

import threading
from datetime import timedelta
from typing import Any

import psycopg
import pytest
from psycopg.rows import dict_row

from ..support.rows import seed_organization
from ..support.scenario import T0, Conn, call, set_user
from ..support.tenancy import (
    REQUEST,
    Member,
    audit_events,
    change_log,
    provision_member,
    refused,
    set_override,
)

DAY = timedelta(hours=24)


@pytest.fixture
def owner(operator_conn: Conn) -> Member:
    return provision_member(operator_conn, 1, "Owner", "Olive", "Owner")


@pytest.fixture
def office(operator_conn: Conn, owner: Member) -> Member:
    return provision_member(operator_conn, 2, "Office admin", "Otto", "Office")


@pytest.fixture
def admin2(operator_conn: Conn, owner: Member) -> Member:
    return provision_member(operator_conn, 6, "Office admin", "Amara", "Admin")


@pytest.fixture
def fleet(operator_conn: Conn, owner: Member) -> Member:
    return provision_member(operator_conn, 3, "Fleet manager", "Fiona", "Fleet")


@pytest.fixture
def clerk(operator_conn: Conn, owner: Member) -> Member:
    return provision_member(operator_conn, 4, "Revenue clerk", "Cleo", "Clerk")


def _request(app: Conn, actor: Member, *, now: Any = T0) -> dict[str, Any]:
    return call(app, "me_deletion_request", actor.id, actor.org, REQUEST, now)


def _org_name(owner_conn: Conn, org: Any) -> str:
    row = owner_conn.execute(
        "SELECT name FROM tenancy.organizations WHERE id = %s", (org,)
    ).fetchone()
    assert row is not None
    return str(row["name"])


def _race(app_url: str, first: Any, late: Any) -> tuple[Any, Any]:
    """Runs ``late`` on a second connection while ``first`` holds its transaction open, so the
    late call waits on the membership-row lock the first one takes until it commits."""
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
            assert worker.is_alive()
        worker.join(10)
    assert len(results) == 1
    return done, results[0]


def test_the_first_request_names_only_the_other_admins_who_can_block(
    app_conn: Conn,
    owner_conn: Conn,
    owner: Member,
    office: Member,
    fleet: Member,
    clerk: Member,
) -> None:
    result = _request(app_conn, office)
    assert result["recorded"] is True
    assert result["requester_name"] == "Otto Office"
    assert result["organization_name"] == _org_name(owner_conn, office.org)
    # owner holds people.block; office is the requester; fleet and clerk do not hold it.
    assert result["recipients"] == [{"email": "olive.owner@example.com", "first_name": "Olive"}]


def test_the_recipients_are_every_other_admin_who_can_block_in_name_order(
    app_conn: Conn, owner: Member, office: Member, admin2: Member
) -> None:
    result = _request(app_conn, office)
    assert result["recipients"] == [
        {"email": "amara.admin@example.com", "first_name": "Amara"},
        {"email": "olive.owner@example.com", "first_name": "Olive"},
    ]


def test_the_block_right_not_the_sign_in_right_makes_a_recipient(
    app_conn: Conn,
    owner_conn: Conn,
    owner: Member,
    office: Member,
    admin2: Member,
    fleet: Member,
    clerk: Member,
) -> None:
    # admin2 keeps people.sign_in but loses people.block; fleet gains people.block alone.
    set_override(owner_conn, admin2, "people.block", granted=False)
    set_override(owner_conn, fleet, "people.block")
    result = _request(app_conn, clerk)
    assert [r["email"] for r in result["recipients"]] == [
        "fiona.fleet@example.com",
        "otto.office@example.com",
        "olive.owner@example.com",
    ]


def test_a_member_without_the_block_right_may_request_their_own_deletion(
    app_conn: Conn, owner: Member, office: Member, clerk: Member
) -> None:
    result = _request(app_conn, clerk)
    assert result["recorded"] is True
    assert result["requester_name"] == "Cleo Clerk"
    assert [r["email"] for r in result["recipients"]] == [
        "otto.office@example.com",
        "olive.owner@example.com",
    ]


def test_the_first_request_writes_one_audit_event_and_one_change_log_row(
    app_conn: Conn, owner_conn: Conn, owner: Member, office: Member
) -> None:
    logged_before = len(change_log(owner_conn, office.org))
    _request(app_conn, office)

    events = audit_events(owner_conn, office.org, "person.deletion_requested")
    assert len(events) == 1
    assert events[0]["actor_id"] == office.id
    assert events[0]["entity"] == str(office.id)
    assert events[0]["after"]["user_id"] == str(office.id)
    assert "requested_at" in events[0]["after"]

    rows = change_log(owner_conn, office.org)
    assert len(rows) == logged_before + 1
    row = rows[-1]
    assert row["section"] == "people"
    assert row["entity_id"] == office.id
    assert row["vehicle_id"] is None
    assert row["actor_id"] == office.id
    assert row["reason"] == "Account deletion requested, Otto Office"


@pytest.mark.parametrize("gone", ["membership", "account"])
def test_an_inactive_member_or_removed_account_is_not_notified(
    app_conn: Conn, owner_conn: Conn, owner: Member, office: Member, admin2: Member, gone: str
) -> None:
    if gone == "membership":
        owner_conn.execute(
            "UPDATE tenancy.memberships SET active = false "
            "WHERE organization_id = %s AND user_id = %s",
            (admin2.org, admin2.id),
        )
    else:
        set_user(owner_conn, admin2.id, status="removed")
    result = _request(app_conn, office)
    assert result["recorded"] is True
    assert result["recipients"] == [{"email": "olive.owner@example.com", "first_name": "Olive"}]


def test_a_repeat_within_twenty_four_hours_records_nothing(
    app_conn: Conn, owner_conn: Conn, owner: Member, office: Member
) -> None:
    assert _request(app_conn, office)["recorded"] is True
    audited = len(audit_events(owner_conn, office.org, "person.deletion_requested"))
    logged = len(change_log(owner_conn, office.org))

    for later in (T0 + timedelta(seconds=1), T0 + timedelta(hours=23, minutes=59)):
        repeat = _request(app_conn, office, now=later)
        assert repeat["recorded"] is False
        assert repeat["recipients"] == []
        assert repeat["requester_name"] == "Otto Office"
        assert repeat["organization_name"] == _org_name(owner_conn, office.org)

    assert len(audit_events(owner_conn, office.org, "person.deletion_requested")) == audited
    assert len(change_log(owner_conn, office.org)) == logged


def test_a_request_after_twenty_four_hours_is_recorded_again(
    app_conn: Conn, owner_conn: Conn, owner: Member, office: Member
) -> None:
    assert _request(app_conn, office)["recorded"] is True
    later = _request(app_conn, office, now=T0 + DAY + timedelta(minutes=1))
    assert later["recorded"] is True
    assert len(audit_events(owner_conn, office.org, "person.deletion_requested")) == 2


def test_a_caller_who_is_not_a_member_is_refused(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    other = seed_organization(owner_conn)
    refused(
        app_conn,
        "me_deletion_request",
        [other.user, owner.org, REQUEST, T0],
        "XC403",
        "not_member",
    )


def test_two_requests_at_once_record_the_deletion_only_once(
    app_url: str, owner_conn: Conn, owner: Member, office: Member
) -> None:
    first, late = _race(
        app_url,
        lambda one: call(one, "me_deletion_request", office.id, office.org, REQUEST, T0),
        lambda two: call(
            two, "me_deletion_request", office.id, office.org, REQUEST, T0 + timedelta(seconds=1)
        ),
    )
    assert first["recorded"] is True
    assert late["recorded"] is False
    assert late["recipients"] == []
    assert len(audit_events(owner_conn, office.org, "person.deletion_requested")) == 1
