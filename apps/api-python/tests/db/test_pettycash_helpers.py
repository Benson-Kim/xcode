"""The petty-cash helpers (``docs/05-routines.md`` section 4.9), called as
``xcode_api_executor`` under row-level security inside the organization: kind and status words,
the effect and the balance, who keeps a float and whose floats a person sees, the visibility of
an entry for the three kinds of data scope, the line, date and period checks, the float guard,
the change, remove and review rules as truth tables, the per-row flags, the tallies, the
subjects and the snapshot, and the vehicle postings.

Entries are inserted as ``xcode_owner``: the helpers read states no single routine call
could set up in one step (removed, rejected, recorded by someone else on old dates)."""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

import psycopg
import pytest

from ..support.rows import seed_organization
from ..support.scenario import T0, Conn
from ..support.setup_rows import add_category, add_item
from ..support.tenancy import (
    Member,
    add_company,
    add_vehicle,
    provision_member,
    set_override,
    set_scope,
)

TODAY = date(2026, 10, 9)
EVERY = (
    "pettycash.edit_own",
    "pettycash.edit",
    "pettycash.delete_own",
    "pettycash.delete",
    "pettycash.delete_approved",
    "pettycash.delete_cash",
    "pettycash.approve_item",
    "pettycash.send_back",
    "pettycash.reject",
    "pettycash.reopen",
)
CASH, EXPENSE, CREDIT = 1, 2, 3
WAITING, APPROVED, REJECTED = 1, 2, 4


@dataclass(frozen=True, slots=True)
class Yard:
    owner: Member
    clerk: Member
    admin: Member
    petty: UUID
    other: UUID
    kaa: UUID
    kab: UUID
    tyres: UUID

    @property
    def org(self) -> UUID:
        return self.owner.org


@pytest.fixture
def yard(operator_conn: Conn, owner_conn: Conn) -> Yard:
    owner = provision_member(operator_conn, 1, "Owner", "Antony", "Maina")
    clerk = provision_member(operator_conn, 2, "Fleet manager", "Wanjiru", "Kamau")
    admin = provision_member(operator_conn, 3, "Office admin", "Peter", "Otieno")
    org = owner.org
    petty = add_company(owner_conn, org, "Petty Fleet")
    other = add_company(owner_conn, org, "Other Fleet")
    kaa = add_vehicle(owner_conn, org, petty, "KAA 501A", joined_on=date(2026, 9, 1))
    kab = add_vehicle(owner_conn, org, other, "KAB 502B", joined_on=date(2026, 9, 1))
    set_scope(owner_conn, owner, org, all_companies=True)
    set_scope(owner_conn, clerk, org, companies=[petty])
    repairs = add_category(owner_conn, org, "Repairs", bucket=3)
    tyres = add_item(owner_conn, org, repairs, "Tyres")
    return Yard(owner, clerk, admin, petty, other, kaa, kab, tyres)


@contextmanager
def inside(conn: Conn, who: Member) -> Iterator[None]:
    with conn.transaction():
        conn.execute(
            "SELECT tenancy.enter_organization(%s, %s, 'req-pettycash-helpers', NULL)",
            (who.id, who.org),
        )
        yield


def scalar(conn: Conn, query: str, params: Any = ()) -> Any:
    row = conn.execute(query, params).fetchone()
    assert row is not None
    return next(iter(row.values()))


def refusal(conn: Conn, query: str, params: Any) -> tuple[str | None, str | None, dict[str, Any]]:
    with pytest.raises(psycopg.Error) as caught, conn.transaction():
        conn.execute(query, params)
    text = caught.value.diag.message_detail
    return (
        caught.value.sqlstate,
        caught.value.diag.message_primary,
        json.loads(text) if text else {},
    )


def add_entry(
    owner_conn: Conn,
    yard: Yard,
    kind: int,
    holder: Member,
    amount: Any,
    *,
    status: int | None = None,
    on: date = TODAY,
    vehicle: UUID | None = None,
    units: Any = 1,
    recorded_by: Member | None = None,
    sent_back: str | None = None,
    reviewed_by: Member | None = None,
    reject_reason: str | None = None,
    removed: bool = False,
    payee: str | None = None,
    note: str | None = None,
) -> UUID:
    expense = kind == EXPENSE
    if expense and status is None:
        status = WAITING
    if (status in (APPROVED, REJECTED) or sent_back) and reviewed_by is None:
        reviewed_by = yard.owner
    if status == REJECTED and reject_reason is None:
        reject_reason = "No"
    recorder = recorded_by or holder
    row = owner_conn.execute(
        "INSERT INTO pettycash.entries (organization_id, holder_id, kind, entry_date, vehicle_id, "
        "expense_item_id, units, unit_amount, payee, note, status, sent_back_note, reject_reason, "
        "reviewed_by, reviewed_at, recorded_by, recorded_at, updated_by, updated_at, removed_by, "
        "removed_at, removal_reason) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, "
        "%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
        (
            yard.org,
            holder.id,
            kind,
            on,
            (vehicle or yard.kaa) if expense else None,
            yard.tyres if expense else None,
            Decimal(str(units)),
            Decimal(str(amount)),
            payee,
            note,
            status,
            sent_back,
            reject_reason,
            reviewed_by.id if reviewed_by else None,
            T0 if reviewed_by else None,
            recorder.id,
            T0,
            recorder.id,
            T0,
            yard.owner.id if removed else None,
            T0 if removed else None,
            "Gone" if removed else None,
        ),
    ).fetchone()
    assert row is not None
    return UUID(str(row["id"]))


ENTRY = "(SELECT e FROM pettycash.entries AS e WHERE e.id = %s)"


def test_kind_and_status_words(executor: Conn, yard: Yard) -> None:
    """Sent back is a waiting expense with a note; cash and credit notes have no status."""
    with inside(executor, yard.owner):
        assert [
            scalar(executor, "SELECT pettycash.kind_code(%s)", (w,))
            for w in (
                "cash",
                " expense ",
                "credit",
                "Cash",
                "refund",
                None,
            )
        ] == [1, 2, 3, None, None, None]
        words = [
            scalar(executor, "SELECT pettycash.status_word(%s::smallint, %s)", (status, note))
            for status, note in ((None, None), (1, None), (1, "Fix"), (2, None), (4, None))
        ]
        assert words == [None, "waiting", "sentBack", "approved", "rejected"]


@pytest.mark.parametrize(
    ("kind", "status", "total", "effect"),
    [
        (CASH, None, "100.50", "100.50"),
        (CASH, None, "-40", "-40"),
        (CREDIT, None, "30", "-30"),
        (CREDIT, None, "-30", "30"),
        (EXPENSE, WAITING, "25", "-25"),
        (EXPENSE, APPROVED, "25", "-25"),
        (EXPENSE, REJECTED, "25", "0"),
        (EXPENSE, WAITING, "-25", "25"),
    ],
)
def test_the_effect_of_an_entry_on_its_float(
    executor: Conn, yard: Yard, kind: int, status: int | None, total: str, effect: str
) -> None:
    """Signed amounts: refunds and cash taken back."""
    with inside(executor, yard.owner):
        assert scalar(
            executor,
            "SELECT pettycash.effect(%s::smallint, %s::smallint, %s::numeric)",
            (kind, status, Decimal(total)),
        ) == Decimal(effect)


def test_the_balance_counts_every_entry_not_removed_visible_or_not(
    executor: Conn, owner_conn: Conn, yard: Yard
) -> None:
    add_entry(owner_conn, yard, CASH, yard.clerk, 1000, recorded_by=yard.owner)
    add_entry(owner_conn, yard, EXPENSE, yard.clerk, 100)
    add_entry(owner_conn, yard, EXPENSE, yard.clerk, 200, status=APPROVED, vehicle=yard.kab)
    add_entry(owner_conn, yard, EXPENSE, yard.clerk, 300, status=REJECTED)
    add_entry(owner_conn, yard, EXPENSE, yard.clerk, 400, sent_back="Fix")
    add_entry(owner_conn, yard, CREDIT, yard.clerk, 50, recorded_by=yard.owner)
    add_entry(owner_conn, yard, CASH, yard.clerk, 9999, recorded_by=yard.owner, removed=True)
    add_entry(owner_conn, yard, CASH, yard.owner, 777)
    for who in (yard.clerk, yard.owner):
        with inside(executor, who):
            assert scalar(executor, "SELECT pettycash.balance(%s)", (yard.clerk.id,)) == 250


def test_holders_are_the_people_with_the_spend_right_and_anyone_with_an_entry(
    executor: Conn, owner_conn: Conn, operator_conn: Conn, yard: Yard
) -> None:
    """Sorted by name ignoring case, then id."""
    zed = provision_member(operator_conn, 4, "Fleet manager", "Zed", "Mwangi")
    provision_member(operator_conn, 6, "Fleet manager", "adam", "Zulu")
    gone = provision_member(operator_conn, 5, "Revenue clerk", "Ann", "Old")
    add_entry(owner_conn, yard, CASH, gone, 10, recorded_by=yard.owner)
    add_entry(owner_conn, yard, CASH, yard.admin, 10, recorded_by=yard.owner, removed=True)
    owner_conn.execute(
        "UPDATE tenancy.memberships SET active = false WHERE organization_id = %s AND user_id = %s",
        (yard.org, zed.id),
    )
    with inside(executor, yard.owner):
        holders = executor.execute("SELECT * FROM pettycash.holders()").fetchall()
        assert [(h["name"], h["active"]) for h in holders] == [
            ("adam Zulu", True),
            ("Ann Old", False),
            ("Antony Maina", True),
            ("Wanjiru Kamau", True),
        ]
        assert [
            scalar(executor, "SELECT pettycash.is_holder(%s)", (m.id,))
            for m in (
                yard.owner,
                yard.clerk,
                yard.admin,
                gone,
                zed,
            )
        ] == [True, True, False, False, False]
        assert [
            h["name"]
            for h in executor.execute("SELECT * FROM pettycash.visible_holders(true)").fetchall()
        ] == ["adam Zulu", "Ann Old", "Antony Maina", "Wanjiru Kamau"]
    with inside(executor, yard.clerk):
        assert [
            h["user_id"]
            for h in executor.execute("SELECT * FROM pettycash.visible_holders(false)").fetchall()
        ] == [yard.clerk.id]
    with inside(executor, yard.admin):
        assert executor.execute("SELECT * FROM pettycash.visible_holders(false)").fetchall() == []


@pytest.mark.parametrize("scope", ["all", "companies", "vehicles", "none"])
def test_an_entry_is_visible_by_float_and_by_the_scope_of_its_vehicle(
    executor: Conn, owner_conn: Conn, yard: Yard, scope: str
) -> None:
    """For the three kinds of data scope (and none): one's own float whatever the vehicle;
    others' with view_all when the vehicle is in scope or there is none."""
    own_far = add_entry(owner_conn, yard, EXPENSE, yard.admin, 10, vehicle=yard.kab)
    near = add_entry(owner_conn, yard, EXPENSE, yard.clerk, 10)
    far = add_entry(owner_conn, yard, EXPENSE, yard.clerk, 10, vehicle=yard.kab)
    given = add_entry(owner_conn, yard, CASH, yard.clerk, 10, recorded_by=yard.owner)
    removed = add_entry(
        owner_conn, yard, CASH, yard.admin, 10, recorded_by=yard.owner, removed=True
    )
    if scope == "all":
        set_scope(owner_conn, yard.admin, yard.org, all_companies=True)
    elif scope == "companies":
        set_scope(owner_conn, yard.admin, yard.org, companies=[yard.petty])
    elif scope == "vehicles":
        set_scope(owner_conn, yard.admin, yard.org, vehicles=[yard.kaa])
    else:
        set_scope(owner_conn, yard.admin, yard.org)
    expected = {
        "all": {own_far, near, far, given},
        "companies": {own_far, near, given},
        "vehicles": {own_far, near, given},
        "none": {own_far, given},
    }[scope]
    with inside(executor, yard.admin):
        rows = executor.execute(
            "SELECT e.id, "
            "pettycash.entry_visible(e, true, ARRAY(SELECT setup.visible_vehicles())) AS seen, "
            "pettycash.entry_visible(e, false, ARRAY(SELECT setup.visible_vehicles())) AS own "
            "FROM pettycash.entries AS e"
        ).fetchall()
    seen = {r["id"] for r in rows if r["seen"]}
    assert seen == expected
    assert {r["id"] for r in rows if r["own"]} == {own_far}
    assert removed not in seen


def test_the_date_and_period_checks(executor: Conn, yard: Yard) -> None:
    """The window is ten years back to the business date; a period may end after it but holds
    at most 367 days."""
    with inside(executor, yard.owner):

        def check(query: str, *args: Any) -> str | None:
            try:
                with executor.transaction():
                    executor.execute(query, args)
            except psycopg.Error as error:
                return error.diag.message_primary
            return None

        date_check = "SELECT pettycash.check_date(%s, %s)"
        assert check(date_check, TODAY, TODAY) is None
        assert check(date_check, TODAY + timedelta(days=1), TODAY) == "pettycash_future_date"
        assert check(date_check, TODAY - timedelta(days=3650), TODAY) is None
        assert check(date_check, TODAY - timedelta(days=3651), TODAY) == "pettycash_too_old"
        period = "SELECT pettycash.check_period(%s, %s, %s)"
        assert check(period, TODAY - timedelta(days=366), TODAY, TODAY) is None
        assert check(period, TODAY, TODAY + timedelta(days=366), TODAY) is None
        assert check(period, TODAY - timedelta(days=367), TODAY, TODAY) == "pettycash_range_length"
        assert check(period, None, TODAY, TODAY) == "pettycash_range_both"
        assert check(period, TODAY, TODAY - timedelta(days=1), TODAY) == "history_dates_order"
        assert (
            check(period, TODAY + timedelta(days=1), TODAY + timedelta(days=2), TODAY)
            == "pettycash_range_start"
        )
        assert (
            check(period, TODAY - timedelta(days=3651), TODAY - timedelta(days=3600), TODAY)
            == "pettycash_too_old"
        )


def test_the_float_guard_stops_only_cash_going_below_zero_without_its_right(
    executor: Conn, owner_conn: Conn, yard: Yard
) -> None:
    add_entry(owner_conn, yard, CASH, yard.clerk, 100, recorded_by=yard.owner)
    guard = "SELECT pettycash.guard_float(%s, %s::smallint, %s::numeric)"
    set_override(owner_conn, yard.owner, "pettycash.issue_negative", False)
    with inside(executor, yard.owner):
        executor.execute(guard, (yard.clerk.id, CASH, Decimal(-100)))
        executor.execute(guard, (yard.clerk.id, EXPENSE, Decimal(-500)))
        executor.execute(guard, (yard.clerk.id, CREDIT, Decimal(-500)))
        executor.execute(guard, (yard.clerk.id, CASH, Decimal(5)))
    with inside(executor, yard.owner):
        assert refusal(executor, guard, (yard.clerk.id, CASH, Decimal("-100.01"))) == (
            "XC422",
            "pettycash_below_zero",
            {"balance_after": -0.01},
        )
    set_override(owner_conn, yard.owner, "pettycash.issue_negative")
    with inside(executor, yard.owner):
        executor.execute(guard, (yard.clerk.id, CASH, Decimal(-5000)))


CHANGE_TABLE = [
    (EXPENSE, WAITING, "own", ("pettycash.edit_own",), None),
    (EXPENSE, WAITING, "own", ("pettycash.edit",), None),
    (EXPENSE, WAITING, "own", ("pettycash.delete_own",), "pettycash_change_own_permission"),
    (EXPENSE, WAITING, "other", ("pettycash.edit",), None),
    (EXPENSE, WAITING, "other", ("pettycash.edit_own",), "pettycash_change_other_permission"),
    (EXPENSE, APPROVED, "own", ("pettycash.edit",), "pettycash_change_decided"),
    (EXPENSE, REJECTED, "other", ("pettycash.edit",), "pettycash_change_decided"),
    (CASH, None, "other", ("pettycash.edit",), "pettycash_change_decided"),
]


@pytest.mark.parametrize(("kind", "status", "whose", "rights", "code"), CHANGE_TABLE)
def test_who_may_change_an_entry(
    executor: Conn,
    owner_conn: Conn,
    yard: Yard,
    kind: int,
    status: int | None,
    whose: str,
    rights: tuple[str, ...],
    code: str | None,
) -> None:
    """Only a waiting expense; own float with edit_own, any float with edit."""
    holder = yard.clerk if whose == "own" else yard.owner
    entry = add_entry(owner_conn, yard, kind, holder, 10, status=status, recorded_by=yard.owner)
    with inside(executor, yard.clerk):
        query = f"SELECT pettycash.authorize_change({ENTRY}, %s::text[])"
        if code is None:
            executor.execute(query, (entry, list(rights)))
        else:
            sqlstate = "XC422" if code == "pettycash_change_decided" else "XC403"
            assert refusal(executor, query, (entry, list(rights)))[:2] == (sqlstate, code)


REMOVE_TABLE = [
    (CASH, None, "own", ("pettycash.delete",), "x", "pettycash_delete_cash_permission"),
    (CREDIT, None, "other", ("pettycash.delete_cash",), None, "reason_length"),
    (CREDIT, None, "other", ("pettycash.delete_cash",), "x", None),
    (EXPENSE, REJECTED, "own", EVERY, "x", "pettycash_delete_rejected"),
    (EXPENSE, APPROVED, "own", ("pettycash.delete",), "x", "pettycash_delete_approved_permission"),
    (EXPENSE, APPROVED, "other", ("pettycash.delete_approved",), None, "reason_length"),
    (EXPENSE, APPROVED, "other", ("pettycash.delete_approved",), "x", None),
    (
        EXPENSE,
        WAITING,
        "own",
        ("pettycash.delete_approved",),
        None,
        "pettycash_delete_own_permission",
    ),
    (EXPENSE, WAITING, "own", ("pettycash.delete_own",), None, None),
    (EXPENSE, WAITING, "own", ("pettycash.delete",), None, None),
    (
        EXPENSE,
        WAITING,
        "other",
        ("pettycash.delete_own",),
        None,
        "pettycash_delete_other_permission",
    ),
    (EXPENSE, WAITING, "other", ("pettycash.delete",), None, None),
]


@pytest.mark.parametrize(("kind", "status", "whose", "rights", "reason", "code"), REMOVE_TABLE)
def test_who_may_remove_an_entry(
    executor: Conn,
    owner_conn: Conn,
    yard: Yard,
    kind: int,
    status: int | None,
    whose: str,
    rights: tuple[str, ...],
    reason: str | None,
    code: str | None,
) -> None:
    """Never a rejected expense; a reason for cash, credit notes and approved expenses only."""
    holder = yard.clerk if whose == "own" else yard.owner
    entry = add_entry(owner_conn, yard, kind, holder, 10, status=status, recorded_by=yard.owner)
    with inside(executor, yard.clerk):
        query = f"SELECT pettycash.authorize_remove({ENTRY}, %s::text[], %s)"
        if code is None:
            executor.execute(query, (entry, list(rights), reason))
        else:
            sqlstate = "XC403" if code.endswith("_permission") else "XC422"
            assert refusal(executor, query, (entry, list(rights), reason))[:2] == (sqlstate, code)


REVIEW_TABLE = [
    (CASH, "clerk", "owner", 10, None, "pettycash_cash_not_reviewed"),
    (CREDIT, "clerk", "owner", 10, None, "pettycash_credit_not_reviewed"),
    (EXPENSE, "admin", "clerk", 10, None, "pettycash_own_float_review"),
    (EXPENSE, "clerk", "admin", 10, None, "pettycash_own_entry_review"),
    (EXPENSE, "clerk", "clerk", 5000.01, 5000, "pettycash_above_limit"),
    (EXPENSE, "clerk", "clerk", -5000.01, 5000, "pettycash_above_limit"),
    (EXPENSE, "clerk", "clerk", 5000, 5000, None),
    (EXPENSE, "clerk", "clerk", 10, 0, "pettycash_above_limit"),
    (EXPENSE, "clerk", "clerk", 99999, None, None),
]


@pytest.mark.parametrize(("kind", "holder", "recorder", "amount", "limit", "code"), REVIEW_TABLE)
def test_who_may_review_an_entry(
    executor: Conn,
    owner_conn: Conn,
    yard: Yard,
    kind: int,
    holder: str,
    recorder: str,
    amount: Any,
    limit: int | None,
    code: str | None,
) -> None:
    """The cash and credit refusals first, then the own float, the own entry and the limit on
    the absolute total."""
    people = {"clerk": yard.clerk, "admin": yard.admin, "owner": yard.owner}
    entry = add_entry(owner_conn, yard, kind, people[holder], amount, recorded_by=people[recorder])
    with inside(executor, yard.admin):
        query = f"SELECT pettycash.authorize_review({ENTRY}, %s::numeric)"
        if code is None:
            executor.execute(query, (entry, limit))
        else:
            sqlstate = "XC422" if code.endswith("_reviewed") else "XC403"
            assert refusal(executor, query, (entry, limit))[:2] == (sqlstate, code)


FLAG_NAMES = (
    "can_edit",
    "can_remove",
    "can_review",
    "above_limit",
    "can_send_back",
    "can_reject",
    "can_reopen",
)


@pytest.mark.parametrize(
    ("case", "rights", "limit", "earliest", "expected"),
    [
        ("waiting", EVERY, None, None, (True, True, True, False, True, True, False)),
        ("waiting", EVERY, 5, None, (True, True, False, True, False, False, False)),
        (
            "waiting",
            EVERY,
            None,
            TODAY + timedelta(days=1),
            (False, False, True, False, True, True, False),
        ),
        ("sent_back", EVERY, None, None, (True, True, False, False, False, True, False)),
        ("approved", EVERY, None, None, (False, True, False, False, False, False, True)),
        ("rejected", EVERY, None, None, (False, False, False, False, False, False, True)),
        ("own_waiting", EVERY, None, None, (True, True, False, False, False, False, False)),
        (
            "own_waiting",
            ("pettycash.edit_own", "pettycash.delete_own"),
            None,
            None,
            (True, True, False, False, False, False, False),
        ),
        (
            "waiting",
            ("pettycash.edit_own", "pettycash.delete_own"),
            None,
            None,
            (False, False, False, False, False, False, False),
        ),
        ("recorded", EVERY, None, None, (True, True, False, False, False, False, False)),
        (
            "cash",
            (*EVERY, "pettycash.delete_cash"),
            None,
            None,
            (False, True, False, False, False, False, False),
        ),
        ("credit", EVERY, None, None, (False, True, False, False, False, False, False)),
        (
            "approved",
            EVERY,
            None,
            TODAY + timedelta(days=1),
            (False, False, False, False, False, False, False),
        ),
    ],
)
def test_the_row_flags(
    executor: Conn,
    owner_conn: Conn,
    yard: Yard,
    case: str,
    rights: tuple[str, ...],
    limit: int | None,
    earliest: date | None,
    expected: tuple[bool, ...],
) -> None:
    """The flags agree with authorize_change, authorize_remove, authorize_review and the
    back-dating limit; can_review means "may approve now"."""
    clerk, admin = yard.clerk, yard.admin
    entry = {
        "waiting": lambda: add_entry(owner_conn, yard, EXPENSE, clerk, 10),
        "sent_back": lambda: add_entry(owner_conn, yard, EXPENSE, clerk, 10, sent_back="Fix"),
        "approved": lambda: add_entry(owner_conn, yard, EXPENSE, clerk, 10, status=APPROVED),
        "rejected": lambda: add_entry(owner_conn, yard, EXPENSE, clerk, 10, status=REJECTED),
        "own_waiting": lambda: add_entry(owner_conn, yard, EXPENSE, admin, 10),
        "recorded": lambda: add_entry(owner_conn, yard, EXPENSE, clerk, 10, recorded_by=admin),
        "cash": lambda: add_entry(owner_conn, yard, CASH, clerk, 10, recorded_by=yard.owner),
        "credit": lambda: add_entry(owner_conn, yard, CREDIT, clerk, 10, recorded_by=yard.owner),
    }[case]()
    with inside(executor, admin):
        flags = scalar(
            executor,
            f"SELECT pettycash.flags({ENTRY}, %s::text[], %s::numeric, %s::date)",
            (entry, list(rights), limit, earliest),
        )
    assert tuple(flags[name] for name in FLAG_NAMES) == expected


def test_the_tallies_group_the_visible_entries_by_window(
    executor: Conn, owner_conn: Conn, yard: Yard
) -> None:
    """Over visible entries only."""
    add_entry(
        owner_conn,
        yard,
        CASH,
        yard.clerk,
        1000,
        recorded_by=yard.owner,
        on=TODAY - timedelta(days=5),
    )
    add_entry(owner_conn, yard, EXPENSE, yard.clerk, 100, on=TODAY - timedelta(days=2))
    add_entry(owner_conn, yard, EXPENSE, yard.clerk, 50, on=TODAY - timedelta(days=2))
    add_entry(
        owner_conn, yard, EXPENSE, yard.clerk, 70, sent_back="Fix", on=TODAY - timedelta(days=1)
    )
    add_entry(owner_conn, yard, EXPENSE, yard.clerk, 30, vehicle=yard.kab)
    add_entry(owner_conn, yard, EXPENSE, yard.clerk, 999, removed=True)
    with inside(executor, yard.owner):
        rows = executor.execute(
            "SELECT kind, status, sent_back, window_position, total, entries, latest "
            "FROM pettycash.tallies(%s, %s, %s, true, ARRAY[%s]::uuid[]) ORDER BY 1, 2, 3, 4",
            (
                [yard.clerk.id],
                TODAY - timedelta(days=2),
                TODAY - timedelta(days=1),
                yard.kaa,
            ),
        ).fetchall()
    assert [tuple(r.values()) for r in rows] == [
        (1, None, False, 0, Decimal("1000.00"), 1, TODAY - timedelta(days=5)),
        (2, 1, False, 1, Decimal("150.00"), 2, TODAY - timedelta(days=2)),
        (2, 1, True, 1, Decimal("70.00"), 1, TODAY - timedelta(days=1)),
    ]


def test_the_subjects_and_the_snapshot(executor: Conn, owner_conn: Conn, yard: Yard) -> None:
    """The change-log subjects, and the snapshot keys with the reject and reopen reasons."""
    spent = add_entry(owner_conn, yard, EXPENSE, yard.clerk, "1500", units="2.5", note="Tyres")
    given = add_entry(owner_conn, yard, CASH, yard.clerk, 10, recorded_by=yard.owner)
    taken = add_entry(owner_conn, yard, CASH, yard.clerk, -10, recorded_by=yard.owner)
    paid = add_entry(
        owner_conn,
        yard,
        CREDIT,
        yard.clerk,
        10,
        recorded_by=yard.owner,
        payee="Grace",
        note="Loader",
    )
    noted = add_entry(
        owner_conn, yard, CREDIT, yard.clerk, 10, recorded_by=yard.owner, note="Loader"
    )
    bare = add_entry(owner_conn, yard, CREDIT, yard.clerk, 10, recorded_by=yard.owner)
    with inside(executor, yard.owner):
        subjects = [
            scalar(executor, f"SELECT pettycash.describe({ENTRY})", (e,))
            for e in (
                spent,
                given,
                taken,
                paid,
                noted,
                bare,
            )
        ]
        snapshot = json.loads(
            scalar(executor, f"SELECT pettycash.entry_snapshot({ENTRY})::text", (spent,))
        )
    assert subjects == [
        "Wanjiru Kamau's petty cash spending on KAA 501A for 9 Oct 2026",
        "petty cash given to Wanjiru Kamau",
        "petty cash taken back from Wanjiru Kamau",
        "Wanjiru Kamau's petty cash credit note paying Grace",
        "Wanjiru Kamau's petty cash credit note, Loader",
        "Wanjiru Kamau's petty cash credit note",
    ]
    assert snapshot == {
        "Id": str(spent),
        "HolderId": str(yard.clerk.id),
        "Kind": "Expense",
        "Date": "2026-10-09",
        "VehicleId": str(yard.kaa),
        "ExpenseItemId": str(yard.tyres),
        "Units": 2.5,
        "UnitAmount": 1500,
        "Total": 3750,
        "Payee": None,
        "Note": "Tyres",
        "Reimbursable": False,
        "Status": "Waiting",
        "SentBackNote": None,
        "RejectReason": None,
        "ReopenReason": None,
        "ReviewedBy": None,
        "ReviewedAt": None,
        "RecordedBy": str(yard.clerk.id),
        "RecordedAt": snapshot["RecordedAt"],
        "UpdatedBy": str(yard.clerk.id),
        "UpdatedAt": snapshot["UpdatedAt"],
        "RemovedBy": None,
        "RemovedAt": None,
        "RemovalReason": None,
        "Version": 1,
    }
    assert snapshot["RecordedAt"].startswith("2026-10-09T07:00:00")


def test_the_fleet_postings_hold_the_approved_expenses_in_the_window(
    executor: Conn, owner_conn: Conn, yard: Yard
) -> None:
    """One cost per approved, non-removed expense, the bucket of the item's category."""
    approved = add_entry(owner_conn, yard, EXPENSE, yard.clerk, 120, status=APPROVED)
    add_entry(
        owner_conn, yard, EXPENSE, yard.clerk, 1, status=APPROVED, on=TODAY - timedelta(days=9)
    )
    add_entry(owner_conn, yard, EXPENSE, yard.clerk, 2)
    add_entry(owner_conn, yard, EXPENSE, yard.clerk, 3, status=REJECTED)
    add_entry(owner_conn, yard, EXPENSE, yard.clerk, 4, status=APPROVED, removed=True)
    add_entry(owner_conn, yard, EXPENSE, yard.clerk, 5, status=APPROVED, vehicle=yard.kab)
    with inside(executor, yard.owner):
        rows = executor.execute(
            "SELECT id, version_id, day, name, kind, amount, bucket, holder_id"
            " FROM setup.fleet_postings(ARRAY[%s]::uuid[], %s, %s, %s) WHERE source = 2",
            (yard.kaa, TODAY - timedelta(days=3), TODAY, TODAY),
        ).fetchall()
    assert [tuple(r.values()) for r in rows] == [
        (approved, approved, TODAY, "Tyres", 1, Decimal("120.00"), 3, yard.clerk.id)
    ]


def test_an_entry_of_another_organization_is_never_read(
    executor: Conn, owner_conn: Conn, yard: Yard
) -> None:
    """Row-level security and the organization filter: a helper inside one organization does
    not see another's entry even by id, nor count it in a balance or a float list."""
    entry = add_entry(owner_conn, yard, CASH, yard.clerk, 10, recorded_by=yard.owner)
    other = seed_organization(owner_conn)
    stranger = Member(other.user, other.org, "", "", "", "", "Owner")
    with inside(executor, stranger):
        assert (
            scalar(executor, "SELECT count(*) FROM pettycash.entries WHERE id = %s", (entry,)) == 0
        )
        assert scalar(executor, "SELECT pettycash.balance(%s)", (yard.clerk.id,)) == 0
        assert (
            scalar(
                executor,
                "SELECT count(*) FROM pettycash.holders() WHERE user_id = %s",
                (yard.clerk.id,),
            )
            == 0
        )
        sqlstate, code, _ = refusal(
            executor, "SELECT pettycash.visible_entry(%s, true, '{}'::uuid[], false)", (entry,)
        )
        assert (sqlstate, code) == ("XC404", "not_found")


def test_the_report_entries_are_the_set_form_of_entry_visible_and_member_name(
    executor: Conn, owner_conn: Conn, yard: Yard
) -> None:
    """``reports.pettycash_entries`` joins what ``pettycash.entry_visible`` and
    ``pettycash.member_name`` answer one row at a time: the same entries for every float,
    scope and right, with the same names."""
    add_entry(owner_conn, yard, EXPENSE, yard.clerk, 120, status=APPROVED, reviewed_by=yard.admin)
    add_entry(owner_conn, yard, EXPENSE, yard.clerk, 60, vehicle=yard.kab, recorded_by=yard.admin)
    add_entry(owner_conn, yard, EXPENSE, yard.admin, 30, vehicle=yard.kab)
    add_entry(owner_conn, yard, EXPENSE, yard.admin, 20, removed=True)
    add_entry(owner_conn, yard, CASH, yard.clerk, 500, recorded_by=yard.owner)
    add_entry(owner_conn, yard, CREDIT, yard.admin, 40)
    holders = [yard.clerk.id, yard.admin.id, yard.owner.id]
    names = (
        "coalesce(pettycash.member_name(e.holder_id), '') AS holder, "
        "coalesce(pettycash.member_name(e.recorded_by), '') AS recorder, "
        "pettycash.member_name(e.reviewed_by) AS reviewer"
    )
    for who in (yard.owner, yard.clerk, yard.admin):
        with inside(executor, who):
            for view_all, vehicles in (
                (True, "ARRAY(SELECT setup.visible_vehicles())"),
                (False, "ARRAY(SELECT setup.visible_vehicles())"),
                (True, f"ARRAY['{yard.kaa}']::uuid[]"),
            ):
                one_by_one = executor.execute(
                    f"SELECT e.id, {names} FROM pettycash.entries AS e "
                    "WHERE e.holder_id = ANY (%s) "
                    f"AND pettycash.entry_visible(e, %s, {vehicles}) ORDER BY e.id",
                    (holders, view_all),
                ).fetchall()
                as_set = executor.execute(
                    "SELECT id, holder_name, recorded_by_name, reviewed_by_name "
                    f"FROM reports.pettycash_entries(%s, %s, {vehicles}) ORDER BY id",
                    (holders, view_all),
                ).fetchall()
                assert [tuple(r.values()) for r in as_set] == [
                    tuple(r.values()) for r in one_by_one
                ]
                assert one_by_one or not view_all
