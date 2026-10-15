"""The petty-cash routines (``api.pettycash_*``), called as ``xcode_app``: each routine's steps
in order (the first failing step answers), the fifteen line checks, the holder rules, the
replays, the float guard, the version conflicts with ``current``, the reviewer rule, the
decisions and their reason sentences, snapshots, change-log and audit rows, the figures and
float rows, the list filters, the options and dashboard cards, the approved expenses in the
vehicle report and the change-log visibility for scoped viewers.

The business date is 9 Oct 2026 (a Friday; weeks start on Monday). Wanjiru Kamau keeps a float
(Fleet manager, scoped to Petty Fleet), Peter Otieno reviews (Office admin with the reviewing
rights, every company, approval limit 5000) and Antony Maina owns the organization (every
right). The rules are those of ``docs/inventory/inventory-petty-cash.md`` as the design
notes (``docs/15-design-v2-3.md``) change them."""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ..support.rows import seed_organization
from ..support.scenario import T0, Conn
from ..support.setup_rows import add_category, add_item, change_rows, read, refuses
from ..support.tenancy import (
    REQUEST,
    Member,
    add_company,
    add_vehicle,
    audit_events,
    provision_member,
    set_localization,
    set_override,
    set_scope,
)

TODAY = date(2026, 10, 9)
NONE = UUID(int=0)
REVIEWER = (
    "pettycash.view",
    "pettycash.view_all",
    "pettycash.approve_item",
    "pettycash.approve_day",
    "pettycash.send_back",
    "pettycash.reject",
    "pettycash.reopen",
    "dash.pettycash",
)


def at(minutes: int) -> datetime:
    return T0 + timedelta(minutes=minutes)


def day(offset: int) -> date:
    return TODAY + timedelta(days=offset)


def num(value: Any) -> Decimal:
    return Decimal(str(value))


@dataclass(frozen=True, slots=True)
class Yard:
    owner: Member
    clerk: Member
    admin: Member
    petty: UUID
    other: UUID
    kaa: UUID
    kab: UUID
    repairs: UUID
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
    kaa = add_vehicle(owner_conn, org, petty, "KAA 501A", joined_on=day(-30))
    kab = add_vehicle(owner_conn, org, other, "KAB 502B", joined_on=day(-30))
    set_scope(owner_conn, owner, org, all_companies=True)
    set_scope(owner_conn, clerk, org, companies=[petty])
    set_scope(owner_conn, admin, org, all_companies=True)
    for permission in REVIEWER:
        set_override(owner_conn, admin, permission)
    set_limit(owner_conn, admin, 5000)
    repairs = add_category(owner_conn, org, "Repairs", bucket=1)
    tyres = add_item(owner_conn, org, repairs, "Tyres")
    return Yard(owner, clerk, admin, petty, other, kaa, kab, repairs, tyres)


def set_limit(owner_conn: Conn, member: Member, limit: int | None) -> None:
    owner_conn.execute(
        "UPDATE tenancy.memberships SET approval_limit = %s "
        "WHERE organization_id = %s AND user_id = %s",
        (limit, member.org, member.id),
    )


def set_back_limit(owner_conn: Conn, member: Member, days: int) -> None:
    owner_conn.execute(
        "UPDATE tenancy.memberships SET back_limit_mode = 'days', back_limit_count = %s "
        "WHERE organization_id = %s AND user_id = %s",
        (days, member.org, member.id),
    )


def money(value: Any) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def line(
    kind: str | None,
    on: date | None,
    amount: Any,
    *,
    holder: UUID | None = None,
    vehicle: UUID | None = None,
    item: UUID | None = None,
    units: Any = None,
    payee: str | None = None,
    note: str | None = None,
    reimbursable: bool | None = False,
) -> list[Any]:
    return [kind, on, money(amount), holder, vehicle, item, money(units), payee, note, reimbursable]


def create(
    app: Conn, who: Member, *fields: Any, entry_id: UUID | None = None, now: datetime = T0
) -> Any:
    return read(app, "pettycash_entry_create", who, entry_id, *fields, None, now=now)


def create_refused(
    app: Conn,
    who: Member,
    fields: list[Any],
    sqlstate: str,
    code: str,
    *,
    entry_id: UUID | None = None,
) -> dict[str, Any]:
    return detail(
        refuses(app, "pettycash_entry_create", who, [entry_id, *fields, None], sqlstate, code)
    )


def expense(
    app: Conn,
    yard: Yard,
    amount: Any,
    *,
    who: Member | None = None,
    on: date = TODAY,
    units: Any = None,
    note: str | None = None,
    holder: UUID | None = None,
    vehicle: UUID | None = None,
    entry_id: UUID | None = None,
    now: datetime = T0,
) -> Any:
    fields = line(
        "expense",
        on,
        amount,
        holder=holder,
        vehicle=vehicle or yard.kaa,
        item=yard.tyres,
        units=units,
        note=note,
    )
    return create(app, who or yard.clerk, *fields, entry_id=entry_id, now=now)


def cash(
    app: Conn,
    yard: Yard,
    amount: Any,
    *,
    holder: UUID | None = None,
    on: date = TODAY,
    who: Member | None = None,
    now: datetime = T0,
) -> Any:
    fields = line("cash", on, amount, holder=holder or yard.clerk.id)
    return create(app, who or yard.owner, *fields, now=now)


def credit(
    app: Conn,
    yard: Yard,
    amount: Any,
    *,
    holder: UUID | None = None,
    on: date = TODAY,
    payee: str | None = None,
    note: str | None = "Paid back",
    now: datetime = T0,
) -> Any:
    fields = line("credit", on, amount, holder=holder or yard.clerk.id, payee=payee, note=note)
    return create(app, yard.owner, *fields, now=now)


def update(
    app: Conn,
    who: Member,
    saved: Any,
    fields: list[Any],
    version: int | None,
    *,
    now: datetime = T0,
) -> Any:
    return read(app, "pettycash_entry_update", who, UUID(saved["id"]), *fields, version, now=now)


def decide(
    app: Conn,
    routine: str,
    who: Member,
    saved: Any,
    *rest: Any,
    version: Any = "current",
    now: datetime = T0,
) -> Any:
    current = saved["version"] if version == "current" else version
    return read(app, f"pettycash_entry_{routine}", who, UUID(saved["id"]), current, *rest, now=now)


def decide_refused(
    app: Conn,
    routine: str,
    who: Member,
    entry_id: UUID,
    version: int | None,
    rest: list[Any],
    sqlstate: str,
    code: str,
) -> dict[str, Any]:
    return detail(
        refuses(app, f"pettycash_entry_{routine}", who, [entry_id, version, *rest], sqlstate, code)
    )


def overview(
    app: Conn,
    who: Member,
    *,
    on: date | None = None,
    period: str | None = None,
    holder: UUID | None = None,
    start: date | None = None,
    end: date | None = None,
) -> Any:
    return read(app, "pettycash_overview_get", who, on, period, holder, start, end)


def entries(
    app: Conn,
    who: Member,
    *,
    start: date | None = None,
    end: date | None = None,
    holder: UUID | None = None,
    kinds: list[str] | None = None,
    statuses: list[str] | None = None,
    q: str | None = None,
    page: int = 1,
    size: int = 100,
) -> Any:
    return read(
        app, "pettycash_entry_list", who, start, end, holder, kinds, statuses, q, page, size
    )


def detail(error: psycopg.Error) -> dict[str, Any]:
    text = error.diag.message_detail
    return json.loads(text) if text else {}


def stored(owner_conn: Conn, saved: Any) -> dict[str, Any]:
    row = owner_conn.execute(
        "SELECT * FROM pettycash.entries WHERE id = %s", (UUID(saved["id"]),)
    ).fetchone()
    assert row is not None
    return row


def reasons(owner_conn: Conn, yard: Yard) -> list[str]:
    return [str(row["reason"]) for row in change_rows(owner_conn, yard.org, "pettycash")]


def row_of(listing: Any, saved: Any) -> dict[str, Any]:
    [found] = [item for item in listing["items"] if item["id"] == saved["id"]]
    return dict(found)


# --- record an entry ---


def test_recording_spending_waits_for_approval_and_shows_on_the_float(
    app_conn: Conn, yard: Yard
) -> None:
    given = cash(app_conn, yard, 10000)
    assert (given["status"], num(given["balance"]), given["version"], given["outcome"]) == (
        None,
        10000,
        1,
        "created",
    )
    spent = expense(app_conn, yard, 1500, units=2, note="Two tyres")
    assert (spent["status"], num(spent["balance"])) == ("waiting", 7000)

    seen = overview(app_conn, yard.clerk)
    assert (seen["period"], seen["day"], seen["from_date"], seen["to_date"]) == (
        "day",
        "2026-10-09",
        "2026-10-09",
        "2026-10-09",
    )
    figures = seen["figures"]
    assert [
        num(figures[k])
        for k in (
            "opening_balance",
            "cash_received",
            "expenses",
            "credit_notes",
            "money_out",
            "closing_balance",
            "waiting",
            "waiting_count",
        )
    ] == [0, 10000, 3000, 0, 3000, 7000, 3000, 1]
    [row] = seen["floats"]
    assert (row["holder_id"], num(row["cash_received"]), num(row["expenses"])) == (
        str(yard.clerk.id),
        10000,
        3000,
    )
    assert (
        num(row["waiting"]),
        row["waiting_count"],
        num(row["balance"]),
        row["last_cash_on"],
    ) == (
        3000,
        1,
        7000,
        "2026-10-09",
    )
    permissions = seen["permissions"]
    assert (permissions["holder_id"], permissions["can_spend"], permissions["can_issue"]) == (
        str(yard.clerk.id),
        True,
        False,
    )
    assert permissions["can_approve_item"] is False

    before = overview(app_conn, yard.owner, on=day(-1), holder=yard.clerk.id)
    assert (
        num(before["figures"]["opening_balance"]),
        num(before["figures"]["closing_balance"]),
    ) == (0, 0)
    assert num(before["floats"][0]["balance"]) == 7000

    listing = entries(app_conn, yard.owner, start=TODAY, end=TODAY)
    assert listing["total"] == 2
    item = row_of(listing, spent)
    assert (item["registration"], item["expense_item_name"], item["bucket"]) == (
        "KAA 501A",
        "Tyres",
        1,
    )
    assert (num(item["units"]), num(item["unit_amount"]), num(item["total"])) == (2, 1500, 3000)
    assert (item["status"], item["note"], item["holder_name"], item["recorded_by_name"]) == (
        "waiting",
        "Two tyres",
        "Wanjiru Kamau",
        "Wanjiru Kamau",
    )
    assert item["version"] == 1


def test_a_float_may_go_below_zero_but_cash_taken_back_below_zero_needs_its_right(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    """Expenses and credit notes always may; cash below zero needs pettycash.issue_negative,
    and the refusal carries the balance after."""
    spent = expense(app_conn, yard, 3000)
    assert (spent["status"], num(spent["balance"])) == ("waiting", -3000)
    assert num(credit(app_conn, yard, 500)["balance"]) == -3500
    figures = overview(app_conn, yard.clerk)["figures"]
    assert (
        num(figures["opening_balance"]),
        num(figures["money_out"]),
        num(figures["closing_balance"]),
    ) == (
        0,
        3500,
        -3500,
    )
    changed = update(
        app_conn,
        yard.clerk,
        spent,
        line("expense", TODAY, 4000, vehicle=yard.kaa, item=yard.tyres),
        1,
    )
    assert num(changed["balance"]) == -4500
    assert num(expense(app_conn, yard, -200)["balance"]) == -4300
    assert num(cash(app_conn, yard, -500)["balance"]) == -4800
    set_override(owner_conn, yard.owner, "pettycash.issue_negative", False)
    refusal = create_refused(
        app_conn,
        yard.owner,
        line("cash", TODAY, -100, holder=yard.clerk.id),
        "XC422",
        "pettycash_below_zero",
    )
    assert num(refusal["balance_after"]) == -4900
    assert num(cash(app_conn, yard, 1000)["balance"]) == -3800


@pytest.mark.parametrize(
    ("units", "amount", "total"),
    [
        ("11.875", "182.40", "2166.00"),
        ("4.5", "1250.50", "5627.25"),
        ("0.125", "0.1", "0.01"),
        ("1.005", "1", "1.01"),
        ("1001", "10", "10010"),
    ],
)
def test_the_total_is_units_times_amount_rounded_half_away_from_zero(
    app_conn: Conn, owner_conn: Conn, yard: Yard, units: str, amount: str, total: str
) -> None:
    """The stored total is generated from units and amount, never written."""
    saved = expense(app_conn, yard, amount, units=units)
    row = stored(owner_conn, saved)
    assert (row["units"], row["unit_amount"], row["total"]) == (
        Decimal(units),
        Decimal(amount),
        Decimal(total),
    )
    negative = expense(app_conn, yard, "-" + amount, units=units)
    assert stored(owner_conn, negative)["total"] == -Decimal(total)


_LONG = "x" * 81


@pytest.mark.parametrize(
    ("fields", "code"),
    [
        (line("refund", None, 0), "pettycash_kind_invalid"),
        (line(None, None, 0), "pettycash_kind_invalid"),
        (line("expense", None, 0), "pettycash_line_date_required"),
        (line("expense", date(1, 1, 1), 0), "pettycash_line_date_required"),
        (line("expense", TODAY, 0, units=0), "pettycash_line_amount_zero"),
        (line("expense", TODAY, None, units=0), "pettycash_line_amount_zero"),
        (line("expense", TODAY, "10.005", units=0), "pettycash_line_amount_decimals"),
        (line("expense", TODAY, "1000000000000", units=0), "pettycash_line_amount_decimals"),
        (line("expense", TODAY, 10, units=0, note=_LONG), "pettycash_line_units"),
        (line("expense", TODAY, 10, units=-2, note=_LONG), "pettycash_line_units"),
        (line("expense", TODAY, 10, units="1.2345", note=_LONG), "pettycash_line_units"),
        (line("expense", TODAY, 10, units="1000000000", note=_LONG), "pettycash_line_units"),
        (line("cash", TODAY, 10, units=2, payee="p"), "pettycash_line_units_only_expense"),
        (line("expense", TODAY, "0.01", units="0.001", note=_LONG), "pettycash_line_total_zero"),
        (
            line("expense", TODAY, 10000, units="999999999.999", note=_LONG),
            "pettycash_line_total_large",
        ),
        (line("expense", TODAY, 10, note=_LONG), "pettycash_line_note_length"),
        (line("expense", TODAY, 10), "pettycash_line_vehicle_required"),
        (line("expense", TODAY, 10, vehicle=NONE), "pettycash_line_vehicle_required"),
        (line("expense", TODAY, 10, vehicle=uuid4(), payee="p"), "pettycash_line_item_required"),
        (
            line("expense", TODAY, 10, vehicle=uuid4(), item=uuid4(), payee="p"),
            "pettycash_line_expense_payee",
        ),
        (
            line("expense", TODAY, 10, vehicle=uuid4(), item=uuid4(), reimbursable=True),
            "pettycash_line_expense_payee",
        ),
        (line("credit", TODAY, 10, vehicle=uuid4(), payee=_LONG), "pettycash_line_credit_vehicle"),
        (line("credit", TODAY, 10, item=uuid4()), "pettycash_line_credit_vehicle"),
        (line("credit", TODAY, 10, payee=_LONG), "pettycash_line_payee_length"),
        (line("cash", TODAY, 10, payee="p"), "pettycash_line_cash_shape"),
        (line("cash", TODAY, 10, vehicle=uuid4()), "pettycash_line_cash_shape"),
        (line("cash", TODAY, 10, reimbursable=True), "pettycash_line_cash_shape"),
    ],
)
def test_the_line_checks_run_in_their_order(
    app_conn: Conn, yard: Yard, fields: list[Any], code: str
) -> None:
    """Each line fails its check and later ones; the earlier check answers. They run before
    the holder, so the owner meets them all."""
    create_refused(app_conn, yard.owner, fields, "XC422", code)


def test_texts_are_trimmed_and_a_credit_note_needs_no_payee_or_note(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    """Blank is null; the note limit counts the trimmed text."""
    noted = expense(app_conn, yard, 10, note="  " + "n" * 80 + "  ")
    assert stored(owner_conn, noted)["note"] == "n" * 80
    bare = credit(app_conn, yard, 500, payee=" ", note=" ")
    row = stored(owner_conn, bare)
    assert (row["payee"], row["note"], row["status"], row["vehicle_id"]) == (None, None, None, None)
    paid = credit(app_conn, yard, 300, payee="Grace Wambui", note=None)
    assert (bare["status"], paid["status"], num(paid["balance"])) == (None, None, -810)


def test_the_holder_rules_answer_after_the_line_and_before_the_date(
    app_conn: Conn, owner_conn: Conn, operator_conn: Conn, yard: Yard
) -> None:
    clerk, admin, owner = yard.clerk, yard.admin, yard.owner
    tomorrow = day(1)
    create_refused(
        app_conn,
        clerk,
        line("expense", tomorrow, 10, holder=owner.id, vehicle=yard.kaa, item=yard.tyres),
        "XC422",
        "pettycash_own_float_only",
    )
    set_override(owner_conn, admin, "pettycash.credit")
    create_refused(
        app_conn,
        admin,
        line("expense", tomorrow, 10, holder=clerk.id, vehicle=yard.kaa, item=yard.tyres),
        "XC403",
        "pettycash_spend_permission",
    )
    create_refused(
        app_conn, admin, line("credit", tomorrow, 10), "XC422", "pettycash_holder_not_holder"
    )
    create_refused(
        app_conn, clerk, line("credit", tomorrow, 10), "XC403", "pettycash_credit_permission"
    )
    create_refused(
        app_conn,
        clerk,
        line("cash", tomorrow, 10, holder=clerk.id),
        "XC403",
        "pettycash_cash_permission",
    )
    create_refused(
        app_conn, owner, line("cash", tomorrow, 10), "XC422", "pettycash_holder_required"
    )
    create_refused(
        app_conn,
        owner,
        line("cash", tomorrow, 10, holder=admin.id),
        "XC422",
        "pettycash_holder_not_holder",
    )
    set_override(owner_conn, admin, "pettycash.spend_other")
    create_refused(
        app_conn,
        admin,
        line("expense", tomorrow, 10, vehicle=yard.kaa, item=yard.tyres),
        "XC403",
        "pettycash_spend_permission",
    )
    create_refused(
        app_conn,
        admin,
        line("expense", tomorrow, 10, holder=admin.id, vehicle=yard.kaa, item=yard.tyres),
        "XC403",
        "pettycash_spend_permission",
    )
    create_refused(
        app_conn,
        admin,
        line("expense", TODAY, 10, holder=uuid4(), vehicle=yard.kaa, item=yard.tyres),
        "XC422",
        "pettycash_holder_not_holder",
    )
    clerk_float = create(
        app_conn,
        admin,
        *line("expense", TODAY, 10, holder=clerk.id, vehicle=yard.kaa, item=yard.tyres),
    )
    row = stored(owner_conn, clerk_float)
    assert (row["holder_id"], row["recorded_by"], row["status"]) == (clerk.id, admin.id, 1)
    own = create(app_conn, admin, *line("credit", TODAY, 20, holder=clerk.id))
    assert num(own["balance"]) == -30
    create_refused(
        app_conn, clerk, line("expense", TODAY, 10), "XC422", "pettycash_line_vehicle_required"
    )
    nobody = provision_member(operator_conn, 4, "Revenue clerk", "Rita", "Clerk")
    refuses(
        app_conn,
        "pettycash_entry_create",
        nobody,
        [None, *line("cash", TODAY, 10), None],
        "XC403",
        "permission_missing",
    )


def test_the_date_window_and_the_back_dating_limit_follow_the_holder(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    """The ten-year window first, then the person's earliest date."""

    def at_day(on: date, **kw: Any) -> list[Any]:
        return line("expense", on, 10, vehicle=yard.kaa, item=yard.tyres, **kw)

    create_refused(app_conn, yard.clerk, at_day(day(1)), "XC422", "pettycash_future_date")
    create_refused(app_conn, yard.clerk, at_day(day(-3651)), "XC422", "pettycash_too_old")
    set_back_limit(owner_conn, yard.clerk, 3)
    assert create_refused(app_conn, yard.clerk, at_day(day(-4)), "XC422", "record_too_old") == {
        "earliest": "2026-10-06"
    }
    create_refused(app_conn, yard.clerk, at_day(day(-3651)), "XC422", "pettycash_too_old")
    assert expense(app_conn, yard, 10, on=day(-3))["status"] == "waiting"
    set_back_limit(owner_conn, yard.owner, 0)
    assert create_refused(
        app_conn,
        yard.owner,
        line("cash", day(-1), 10, holder=yard.clerk.id),
        "XC422",
        "record_too_old",
    ) == {"earliest": "2026-10-09"}


def test_an_expense_is_checked_against_the_vehicle_and_the_item_vehicle_first(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    stopped = add_item(owner_conn, yard.org, yard.repairs, "Old tyres", stopped_on=day(-5))
    create_refused(
        app_conn,
        yard.clerk,
        line("expense", TODAY, 10, vehicle=yard.kab, item=stopped),
        "XC422",
        "pettycash_vehicle_scope",
    )
    create_refused(
        app_conn,
        yard.clerk,
        line("expense", day(-40), 10, vehicle=yard.kaa, item=stopped),
        "XC422",
        "pettycash_vehicle_inactive",
    )
    create_refused(
        app_conn,
        yard.clerk,
        line("expense", TODAY, 10, vehicle=yard.kaa, item=stopped),
        "XC422",
        "pettycash_item_inactive",
    )
    create_refused(
        app_conn,
        yard.clerk,
        line("expense", TODAY, 10, vehicle=yard.kaa, item=uuid4()),
        "XC422",
        "pettycash_item_inactive",
    )
    assert expense(app_conn, yard, 10, on=day(-6))["status"] == "waiting"


def test_a_retried_create_answers_with_the_entry_it_made_whatever_the_body(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    """The client's id; another actor's id is a conflict with no current entry."""
    cash(app_conn, yard, 10000)
    entry_id = uuid4()
    first = expense(app_conn, yard, 1200, entry_id=entry_id)
    again = create(
        app_conn,
        yard.clerk,
        *line("expense", day(-2), 999, vehicle=yard.kab, item=uuid4()),
        entry_id=entry_id,
    )
    assert again == {**first, "outcome": "replayed"}
    assert (first["id"], num(first["balance"])) == (str(entry_id), 8800)
    assert entries(app_conn, yard.clerk, kinds=["expense"])["total"] == 1
    refusal = create_refused(
        app_conn,
        yard.owner,
        line("cash", TODAY, 10, holder=yard.clerk.id),
        "XC409",
        "pettycash_already_saved",
        entry_id=entry_id,
    )
    assert refusal == {"current": None}
    fresh = create(
        app_conn,
        yard.clerk,
        *line("expense", TODAY, 5, vehicle=yard.kaa, item=yard.tyres),
        entry_id=NONE,
    )
    assert fresh["id"] != str(NONE)
    assert len(change_rows(owner_conn, yard.org, "pettycash")) == 3


def test_a_retried_create_after_a_change_or_a_removal_answers_the_entry_as_it_is(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    set_override(owner_conn, yard.clerk, "pettycash.delete_own")
    entry_id = uuid4()
    first = expense(app_conn, yard, 100, entry_id=entry_id)
    update(
        app_conn,
        yard.clerk,
        first,
        line("expense", TODAY, 150, vehicle=yard.kaa, item=yard.tyres),
        1,
    )
    changed = expense(app_conn, yard, 100, entry_id=entry_id)
    assert (changed["version"], changed["status"], num(changed["balance"]), changed["outcome"]) == (
        2,
        "waiting",
        -150,
        "replayed",
    )
    decide(app_conn, "remove", yard.clerk, changed, None)
    removed = expense(app_conn, yard, 100, entry_id=entry_id)
    assert (removed["version"], num(removed["balance"]), removed["outcome"]) == (3, 0, "replayed")


def test_an_id_another_organization_uses_is_a_new_entry_here(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    """Entries are keyed by organization and id: another organization's entry under the same
    id is neither a replay nor a conflict here, and stays as it was."""
    other = seed_organization(owner_conn)
    theirs = "SELECT * FROM pettycash.entries WHERE organization_id = %s AND id = %s"
    before = owner_conn.execute(theirs, (other.org, other.entry)).fetchone()
    cash(app_conn, yard, 1000)
    mine = expense(app_conn, yard, 300, entry_id=other.entry)
    assert (mine["id"], mine["outcome"], mine["version"], num(mine["balance"])) == (
        str(other.entry),
        "created",
        1,
        700,
    )
    assert owner_conn.execute(theirs, (other.org, other.entry)).fetchone() == before
    owners = owner_conn.execute(
        "SELECT organization_id FROM pettycash.entries WHERE id = %s", (other.entry,)
    ).fetchall()
    assert sorted(str(row["organization_id"]) for row in owners) == sorted(
        [str(other.org), str(yard.org)]
    )


@pytest.mark.parametrize("same_actor", [True, False])
def test_two_creates_under_one_new_id_race_to_one_entry(
    app_url: str, owner_conn: Conn, yard: Yard, same_actor: bool
) -> None:
    """The loser waits on the float, meets the winner's row at the insert and answers as a
    retry: replayed for the same actor, a conflict for another."""
    entry_id = uuid4()
    fields = line("credit", TODAY, 50, holder=yard.clerk.id)
    second_actor = yard.owner if same_actor else yard.admin
    set_override(owner_conn, yard.admin, "pettycash.credit")
    sql = "SELECT api.pettycash_entry_create(" + ", ".join(["%s"] * 16) + ") AS r"
    with (
        psycopg.connect(app_url, autocommit=True, row_factory=dict_row) as first,
        psycopg.connect(app_url, autocommit=True, row_factory=dict_row) as second,
    ):
        outcome: list[Any] = []

        def late() -> None:
            args = (second_actor.id, yard.org, REQUEST, entry_id, *fields, None, at(1))
            try:
                outcome.append(second.execute(sql, args).fetchone())
            except psycopg.Error as error:
                outcome.append(error)

        with first.transaction():
            made = first.execute(
                sql, (yard.owner.id, yard.org, REQUEST, entry_id, *fields, None, at(0))
            ).fetchone()
            worker = threading.Thread(target=late)
            worker.start()
            assert blocked_on(owner_conn, second.info.backend_pid, first.info.backend_pid)
        worker.join(10)
    assert made is not None and made["r"]["outcome"] == "created"
    [answer] = outcome
    if same_actor:
        assert answer["r"] == {**made["r"], "outcome": "replayed"}
    else:
        assert isinstance(answer, psycopg.Error)
        assert (answer.sqlstate, answer.diag.message_primary) == (
            "XC409",
            "pettycash_already_saved",
        )
        assert detail(answer) == {"current": None}
    assert len(change_rows(owner_conn, yard.org, "pettycash")) == 1


def blocked_on(owner_conn: Conn, waiting: int, holder: int) -> bool:
    for _ in range(200):
        row = owner_conn.execute("SELECT pg_blocking_pids(%s) AS pids", (waiting,)).fetchone()
        if row is not None and holder in row["pids"]:
            return True
        threading.Event().wait(0.05)
    return False


def test_two_saves_on_one_float_run_one_after_the_other(
    app_url: str, owner_conn: Conn, yard: Yard
) -> None:
    """The second cash taken back waits for the first and sees its balance, so the float guard
    cannot be raced below zero."""
    cash_line = line("cash", TODAY, -600, holder=yard.clerk.id)
    set_override(owner_conn, yard.owner, "pettycash.issue_negative", False)
    with psycopg.connect(app_url, autocommit=True, row_factory=dict_row) as setup:
        setup.execute(
            "SELECT api.pettycash_entry_create(" + ", ".join(["%s"] * 16) + ")",
            (
                yard.owner.id,
                yard.org,
                REQUEST,
                None,
                *line("cash", TODAY, 1000, holder=yard.clerk.id),
                None,
                at(0),
            ),
        )
    sql = "SELECT api.pettycash_entry_create(" + ", ".join(["%s"] * 16) + ") AS r"
    with (
        psycopg.connect(app_url, autocommit=True, row_factory=dict_row) as first,
        psycopg.connect(app_url, autocommit=True, row_factory=dict_row) as second,
    ):
        outcome: list[Any] = []

        def late() -> None:
            try:
                outcome.append(
                    second.execute(
                        sql, (yard.owner.id, yard.org, REQUEST, None, *cash_line, None, at(2))
                    ).fetchone()
                )
            except psycopg.Error as error:
                outcome.append(error)

        with first.transaction():
            made = first.execute(
                sql, (yard.owner.id, yard.org, REQUEST, None, *cash_line, None, at(1))
            ).fetchone()
            worker = threading.Thread(target=late)
            worker.start()
            assert blocked_on(owner_conn, second.info.backend_pid, first.info.backend_pid)
        worker.join(10)
    assert made is not None and num(made["r"]["balance"]) == 400
    [answer] = outcome
    assert isinstance(answer, psycopg.Error)
    assert (answer.diag.message_primary, num(detail(answer)["balance_after"])) == (
        "pettycash_below_zero",
        -200,
    )


def test_an_entry_held_outside_the_float_lock_is_refused_at_once(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    """Every save takes the float first, so a row another transaction holds without it is a
    concurrent save, answered at once instead of waited for."""
    cash(app_conn, yard, 1000)
    saved = expense(app_conn, yard, 300)
    with owner_conn.transaction():
        owner_conn.execute(
            "SELECT 1 FROM pettycash.entries WHERE id = %s FOR UPDATE", (UUID(saved["id"]),)
        )
        decide_refused(
            app_conn,
            "approve",
            yard.admin,
            UUID(saved["id"]),
            1,
            [],
            "XC409",
            "pettycash_concurrent_save",
        )
    approved = decide(app_conn, "approve", yard.admin, saved)
    assert (approved["status"], approved["version"]) == ("approved", 2)


@pytest.mark.parametrize("change", ["retire the vehicle", "stop the item", "stop the category"])
def test_an_expense_waits_for_a_change_of_its_vehicle_or_item_and_then_reads_it(
    app_url: str, owner_conn: Conn, yard: Yard, change: str
) -> None:
    """A retirement or a stop in flight holds its row: the expense waits for it and then meets
    the vehicle or item as the change left it, never saving on a day it no longer has."""
    first_sql, target, code = {
        "retire the vehicle": (
            "SELECT api.setup_vehicle_retire(%s, %s, %s, %s, %s, NULL, %s)",
            [yard.kaa, TODAY],
            "pettycash_vehicle_inactive",
        ),
        "stop the item": (
            "SELECT api.setup_expense_item_set_stopped(%s, %s, %s, %s, true, %s)",
            [yard.tyres],
            "pettycash_item_inactive",
        ),
        "stop the category": (
            "SELECT api.setup_expense_category_set_stopped(%s, %s, %s, %s, true, %s)",
            [yard.repairs],
            "pettycash_item_inactive",
        ),
    }[change]
    fields = line("expense", TODAY, 300, vehicle=yard.kaa, item=yard.tyres)
    sql = "SELECT api.pettycash_entry_create(" + ", ".join(["%s"] * 16) + ") AS r"
    with (
        psycopg.connect(app_url, autocommit=True, row_factory=dict_row) as first,
        psycopg.connect(app_url, autocommit=True, row_factory=dict_row) as second,
    ):
        outcome: list[Any] = []

        def late() -> None:
            try:
                outcome.append(
                    second.execute(
                        sql, (yard.clerk.id, yard.org, REQUEST, None, *fields, None, at(2))
                    ).fetchone()
                )
            except psycopg.Error as error:
                outcome.append(error)

        with first.transaction():
            first.execute(first_sql, (yard.owner.id, yard.org, REQUEST, *target, at(1)))
            worker = threading.Thread(target=late)
            worker.start()
            assert blocked_on(owner_conn, second.info.backend_pid, first.info.backend_pid)
        worker.join(10)
    [answer] = outcome
    assert isinstance(answer, psycopg.Error), answer
    assert (answer.sqlstate, answer.diag.message_primary) == ("XC422", code)
    count = owner_conn.execute(
        "SELECT count(*) AS n FROM pettycash.entries WHERE organization_id = %s", (yard.org,)
    ).fetchone()
    assert count == {"n": 0}


def test_a_create_a_change_and_a_vehicle_write_on_one_float_never_deadlock(
    app_conn: Conn, app_url: str, owner_conn: Conn, yard: Yard
) -> None:
    """Every petty-cash write takes the float before the vehicle and item rows it checks, so
    a vehicle write queued behind a create cannot close a lock cycle with a change on the
    same float. With the float held, a change waits on it and a create queues behind the
    change, a retirement of their vehicle arrives, and when the float is released the three
    finish one after another, none torn down as a deadlock."""
    spent = expense(app_conn, yard, 100, on=day(-2))
    create_sql = "SELECT api.pettycash_entry_create(" + ", ".join(["%s"] * 16) + ") AS r"
    update_sql = "SELECT api.pettycash_entry_update(" + ", ".join(["%s"] * 16) + ") AS r"
    retire_sql = "SELECT api.setup_vehicle_retire(%s, %s, %s, %s, %s, NULL, %s) AS r"
    changed = line("expense", day(-3), 130, vehicle=yard.kaa, item=yard.tyres)
    added = line("expense", day(-1), 300, vehicle=yard.kaa, item=yard.tyres)
    outcomes: dict[str, Any] = {}

    def run(name: str, conn: psycopg.Connection[Any], sql: str, args: tuple[Any, ...]) -> None:
        try:
            outcomes[name] = conn.execute(sql, args).fetchone()
        except psycopg.Error as error:
            outcomes[name] = error

    workers: list[threading.Thread] = []
    with (
        psycopg.connect(app_url, autocommit=True, row_factory=dict_row) as changing,
        psycopg.connect(app_url, autocommit=True, row_factory=dict_row) as creating,
        psycopg.connect(app_url, autocommit=True, row_factory=dict_row) as retiring,
    ):
        with owner_conn.transaction():
            owner_conn.execute(
                "SELECT 1 FROM tenancy.memberships WHERE organization_id = %s AND user_id = %s "
                "FOR NO KEY UPDATE",
                (yard.org, yard.clerk.id),
            )
            held = owner_conn.info.backend_pid
            change_args = (yard.clerk.id, yard.org, REQUEST, UUID(spent["id"]), *changed, 1, at(1))
            create_args = (yard.clerk.id, yard.org, REQUEST, None, *added, None, at(2))
            for name, conn, sql, args, ahead in (
                ("change", changing, update_sql, change_args, held),
                ("create", creating, create_sql, create_args, changing.info.backend_pid),
            ):
                worker = threading.Thread(target=run, args=(name, conn, sql, args))
                worker.start()
                workers.append(worker)
                assert blocked_on(owner_conn, conn.info.backend_pid, ahead), name
            retire_args = (yard.owner.id, yard.org, REQUEST, yard.kaa, TODAY, at(3))
            worker = threading.Thread(
                target=run, args=("retire", retiring, retire_sql, retire_args)
            )
            worker.start()
            workers.append(worker)
            assert settled(owner_conn, worker, retiring.info.backend_pid, creating.info.backend_pid)
        for worker in workers:
            worker.join(15)
    assert not any(worker.is_alive() for worker in workers)
    failed = {
        name: (error.sqlstate, error.diag.message_primary)
        for name, error in outcomes.items()
        if isinstance(error, psycopg.Error)
    }
    assert failed == {}
    assert outcomes["create"]["r"]["outcome"] == "created"
    assert (outcomes["change"]["r"]["version"], outcomes["change"]["r"]["outcome"]) == (2, "saved")
    assert stored(owner_conn, spent)["entry_date"] == day(-3)
    assert owner_conn.execute(
        "SELECT left_on FROM setup.fleet_vehicles WHERE id = %s", (yard.kaa,)
    ).fetchone() == {"left_on": TODAY}


def settled(owner_conn: Conn, worker: threading.Thread, waiting: int, holder: int) -> bool:
    """True once the worker has finished, or waits on the holder."""
    for _ in range(200):
        if not worker.is_alive():
            return True
        row = owner_conn.execute("SELECT pg_blocking_pids(%s) AS pids", (waiting,)).fetchone()
        if row is not None and holder in row["pids"]:
            return True
        threading.Event().wait(0.05)
    return False


def test_recording_logs_the_snapshot_the_reason_the_vehicle_and_an_audit_row(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    """One audit row per write, its action named after the write."""
    given = cash(app_conn, yard, 10000)
    spent = expense(app_conn, yard, 1500, units=2, note="Two tyres")
    taken = cash(app_conn, yard, -500, now=at(1))
    noted = credit(app_conn, yard, 40, payee=None, note="Loader")
    paid = credit(app_conn, yard, 30, payee="Grace Wambui")
    assert reasons(owner_conn, yard) == [
        "Recorded petty cash given to Wanjiru Kamau",
        "Recorded Wanjiru Kamau's petty cash spending on KAA 501A for 9 Oct 2026",
        "Recorded petty cash taken back from Wanjiru Kamau",
        "Recorded Wanjiru Kamau's petty cash credit note, Loader",
        "Recorded Wanjiru Kamau's petty cash credit note paying Grace Wambui",
    ]
    rows = change_rows(owner_conn, yard.org, "pettycash")
    assert [row["vehicle_id"] for row in rows] == [None, yard.kaa, None, None, None]
    assert [row["entity_id"] for row in rows] == [
        UUID(s["id"]) for s in (given, spent, taken, noted, paid)
    ]
    assert rows[1]["before"] in (None, "null")
    after = json.loads(rows[1]["after"])
    assert list(after) == [
        "Id",
        "HolderId",
        "Kind",
        "Date",
        "VehicleId",
        "ExpenseItemId",
        "Units",
        "UnitAmount",
        "Total",
        "Payee",
        "Note",
        "Reimbursable",
        "Status",
        "SentBackNote",
        "RejectReason",
        "ReopenReason",
        "ReviewedBy",
        "ReviewedAt",
        "RecordedBy",
        "RecordedAt",
        "UpdatedBy",
        "UpdatedAt",
        "RemovedBy",
        "RemovedAt",
        "RemovalReason",
        "Version",
    ]
    assert (after["Kind"], after["Status"], after["Total"], after["Units"], after["Date"]) == (
        "Expense",
        "Waiting",
        3000,
        2,
        "2026-10-09",
    )
    assert (
        json.loads(rows[0]["after"])["Kind"] == "Cash"
        and json.loads(rows[0]["after"])["Status"] is None
    )
    audits = audit_events(owner_conn, yard.org, "pettycash.created")
    assert [a["entity"] for a in audits] == [s["id"] for s in (given, spent, taken, noted, paid)]


# --- change an expense ---


def test_the_change_steps_answer_in_their_order(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    spent = expense(app_conn, yard, 100)
    given = cash(app_conn, yard, 1000)
    good = line("expense", TODAY, 120, vehicle=yard.kaa, item=yard.tyres)
    refuses(
        app_conn,
        "pettycash_entry_update",
        yard.clerk,
        [uuid4(), *line("expense", TODAY, 0), 1],
        "XC422",
        "pettycash_line_amount_zero",
    )
    refuses(
        app_conn, "pettycash_entry_update", yard.clerk, [uuid4(), *good, 1], "XC404", "not_found"
    )
    hidden = expense(app_conn, yard, 100, who=yard.owner)
    refuses(
        app_conn,
        "pettycash_entry_update",
        yard.clerk,
        [UUID(hidden["id"]), *good, 1],
        "XC404",
        "not_found",
    )
    refuses(
        app_conn,
        "pettycash_entry_update",
        yard.clerk,
        [UUID(spent["id"]), *line("credit", TODAY, 120), 1],
        "XC422",
        "pettycash_kind_change",
    )
    moved = line("expense", TODAY, 120, holder=yard.owner.id, vehicle=yard.kaa, item=yard.tyres)
    refuses(
        app_conn,
        "pettycash_entry_update",
        yard.clerk,
        [UUID(spent["id"]), *moved, 1],
        "XC422",
        "pettycash_holder_change",
    )
    refuses(
        app_conn,
        "pettycash_entry_update",
        yard.owner,
        [UUID(given["id"]), *line("cash", TODAY, 900, holder=yard.clerk.id), 1],
        "XC422",
        "pettycash_change_cash",
    )
    set_override(owner_conn, yard.clerk, "pettycash.view_all")
    refuses(
        app_conn,
        "pettycash_entry_update",
        yard.clerk,
        [UUID(hidden["id"]), *line("expense", TODAY, 1, vehicle=yard.kaa, item=yard.tyres), 1],
        "XC403",
        "pettycash_change_other_permission",
    )
    refuses(
        app_conn,
        "pettycash_entry_update",
        yard.clerk,
        [UUID(spent["id"]), *line("expense", day(1), 120, vehicle=yard.kaa, item=yard.tyres), 1],
        "XC422",
        "pettycash_future_date",
    )
    stale = detail(
        refuses(
            app_conn,
            "pettycash_entry_update",
            yard.clerk,
            [UUID(spent["id"]), *good, 7],
            "XC409",
            "pettycash_entry_changed",
        )
    )
    assert (
        stale["current"]["id"],
        stale["current"]["version"],
        num(stale["current"]["unit_amount"]),
    ) == (
        spent["id"],
        1,
        100,
    )
    assert stale["current"]["can_edit"] is True
    missing = detail(
        refuses(
            app_conn,
            "pettycash_entry_update",
            yard.clerk,
            [UUID(spent["id"]), *good, None],
            "XC409",
            "pettycash_entry_changed",
        )
    )
    assert missing["current"]["version"] == 1
    saved = update(app_conn, yard.clerk, spent, good, 1)
    assert (saved["version"], saved["status"], num(saved["balance"]), saved["outcome"]) == (
        2,
        "waiting",
        880,
        "saved",
    )


def test_an_unchanged_line_is_a_replay_before_the_rights_and_the_version(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    """An unchanged save answers the entry as it is, even approved or stale."""
    spent = expense(app_conn, yard, 100, units="1.5", note="Tube")
    same = line(
        "expense", TODAY, 100, vehicle=yard.kaa, item=yard.tyres, units="1.500", note=" Tube "
    )
    replay = update(app_conn, yard.clerk, spent, same, 99)
    assert (replay["version"], replay["outcome"]) == (1, "replayed")
    approved = decide(app_conn, "approve", yard.admin, spent)
    replay = update(app_conn, yard.clerk, approved, same, None)
    assert (replay["version"], replay["status"], replay["outcome"]) == (2, "approved", "replayed")
    refuses(
        app_conn,
        "pettycash_entry_update",
        yard.clerk,
        [UUID(spent["id"]), *line("expense", TODAY, 101, vehicle=yard.kaa, item=yard.tyres), 2],
        "XC422",
        "pettycash_change_decided",
    )
    assert len(change_rows(owner_conn, yard.org, "pettycash")) == 2


def test_saving_a_sent_back_expense_unchanged_sends_it_for_approval_again(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    """An unchanged save of a sent-back entry is a resubmit, not a replay."""
    spent = expense(app_conn, yard, 100)
    sent = decide(app_conn, "send_back", yard.admin, spent, "Attach the receipt")
    assert sent["status"] == "sentBack"
    item = row_of(entries(app_conn, yard.clerk), spent)
    assert (item["status"], item["sent_back_note"], item["can_edit"]) == (
        "sentBack",
        "Attach the receipt",
        True,
    )
    again = update(
        app_conn,
        yard.clerk,
        sent,
        line("expense", TODAY, 100, vehicle=yard.kaa, item=yard.tyres),
        2,
    )
    assert (again["status"], again["version"], again["outcome"]) == ("waiting", 3, "saved")
    row = stored(owner_conn, spent)
    assert (row["sent_back_note"], row["reviewed_by"], row["reviewed_at"]) == (None, None, None)


def test_a_change_checks_the_back_dating_limit_on_the_stored_and_the_new_date(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    old = expense(app_conn, yard, 100, on=day(-5))
    recent = expense(app_conn, yard, 100)
    set_back_limit(owner_conn, yard.clerk, 3)
    refuses(
        app_conn,
        "pettycash_entry_update",
        yard.clerk,
        [UUID(old["id"]), *line("expense", day(-5), 150, vehicle=yard.kaa, item=yard.tyres), 1],
        "XC422",
        "record_too_old",
    )
    refuses(
        app_conn,
        "pettycash_entry_update",
        yard.clerk,
        [UUID(old["id"]), *line("expense", TODAY, 150, vehicle=yard.kaa, item=yard.tyres), 1],
        "XC422",
        "record_too_old",
    )
    refuses(
        app_conn,
        "pettycash_entry_update",
        yard.clerk,
        [UUID(recent["id"]), *line("expense", day(-4), 100, vehicle=yard.kaa, item=yard.tyres), 1],
        "XC422",
        "record_too_old",
    )
    item = row_of(entries(app_conn, yard.clerk), old)
    assert (item["can_edit"], item["can_remove"]) == (False, False)
    moved = update(
        app_conn,
        yard.clerk,
        recent,
        line("expense", day(-3), 100, vehicle=yard.kaa, item=yard.tyres),
        1,
    )
    assert moved["version"] == 2


def test_a_change_checks_only_the_vehicle_and_item_that_changed_a_new_date_both(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    spent = expense(app_conn, yard, 100, on=day(-2))
    owner_conn.execute(
        "UPDATE setup.expense_items SET stopped_on = %s WHERE id = %s", (day(-2), yard.tyres)
    )
    kept = update(
        app_conn,
        yard.clerk,
        spent,
        line("expense", day(-2), 130, vehicle=yard.kaa, item=yard.tyres),
        1,
    )
    assert kept["version"] == 2
    refuses(
        app_conn,
        "pettycash_entry_update",
        yard.clerk,
        [UUID(spent["id"]), *line("expense", day(-1), 130, vehicle=yard.kaa, item=yard.tyres), 2],
        "XC422",
        "pettycash_item_inactive",
    )
    refuses(
        app_conn,
        "pettycash_entry_update",
        yard.clerk,
        [UUID(spent["id"]), *line("expense", day(-2), 130, vehicle=yard.kab, item=yard.tyres), 2],
        "XC422",
        "pettycash_vehicle_scope",
    )


def test_a_change_is_logged_with_the_subject_read_after_it(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    kac = add_vehicle(owner_conn, yard.org, yard.petty, "KAC 503C", joined_on=day(-30))
    spent = expense(app_conn, yard, 100)
    update(
        app_conn, yard.clerk, spent, line("expense", day(-1), 100, vehicle=kac, item=yard.tyres), 1
    )
    rows = change_rows(owner_conn, yard.org, "pettycash")
    assert (
        rows[-1]["reason"]
        == "Changed Wanjiru Kamau's petty cash spending on KAC 503C for 8 Oct 2026"
    )
    assert rows[-1]["vehicle_id"] == kac
    assert json.loads(rows[-1]["before"])["VehicleId"] == str(yard.kaa)
    assert [a["entity"] for a in audit_events(owner_conn, yard.org, "pettycash.changed")] == [
        spent["id"]
    ]


# --- approve, send back, reject, reopen ---


def test_the_approve_steps_answer_in_their_order(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:

    def refused(
        entry: Any, version: int | None, sqlstate: str, code: str, who: Member = yard.admin
    ) -> dict[str, Any]:
        return decide_refused(
            app_conn, "approve", who, UUID(entry["id"]), version, [], sqlstate, code
        )

    decide_refused(app_conn, "approve", yard.admin, uuid4(), 1, [], "XC404", "not_found")
    refused(cash(app_conn, yard, 100), 1, "XC422", "pettycash_cash_not_reviewed")
    refused(credit(app_conn, yard, 100), 1, "XC422", "pettycash_credit_not_reviewed")
    refused(
        expense(app_conn, yard, 100, who=yard.owner, vehicle=yard.kab),
        1,
        "XC403",
        "pettycash_own_float_review",
        yard.owner,
    )
    for_clerk = expense(app_conn, yard, 100, who=yard.owner, holder=yard.clerk.id)
    refused(for_clerk, 1, "XC403", "pettycash_own_entry_review", yard.owner)
    large = expense(app_conn, yard, 6000)
    item = row_of(entries(app_conn, yard.admin), large)
    assert (item["above_limit"], item["can_review"]) == (True, False)
    refused(large, 1, "XC403", "pettycash_above_limit")
    current = refused(large, 9, "XC409", "pettycash_entry_changed", yard.owner)["current"]
    assert (current["id"], current["version"], current["can_review"]) == (large["id"], 1, True)
    approved = decide(app_conn, "approve", yard.owner, large)
    assert (approved["status"], approved["version"], approved["outcome"]) == (
        "approved",
        2,
        "saved",
    )
    rejected = decide(app_conn, "reject", yard.admin, for_clerk, "Not ours")
    refused(rejected, 2, "XC422", "pettycash_not_waiting")
    sent = decide(app_conn, "send_back", yard.admin, expense(app_conn, yard, 50), "Receipt")
    refused(sent, 2, "XC422", "pettycash_sent_back")


def test_approving_twice_answers_the_approval_and_a_row_shows_who_reviewed(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    spent = expense(app_conn, yard, 1200)
    approved = decide(app_conn, "approve", yard.admin, spent)
    again = decide(app_conn, "approve", yard.admin, spent, version=None)
    assert again == {**approved, "outcome": "replayed"}
    item = row_of(entries(app_conn, yard.clerk), spent)
    assert (item["status"], item["reviewed_by_name"], item["can_edit"], item["can_remove"]) == (
        "approved",
        "Peter Otieno",
        False,
        False,
    )
    assert (
        reasons(owner_conn, yard)[-1]
        == "Approved Wanjiru Kamau's petty cash spending on KAA 501A for 9 Oct 2026"
    )
    assert [a["entity"] for a in audit_events(owner_conn, yard.org, "pettycash.approved")] == [
        spent["id"]
    ]
    decide_refused(
        app_conn, "approve", yard.owner, UUID(spent["id"]), 2, [], "XC422", "pettycash_not_waiting"
    )


def test_the_send_back_steps_answer_in_their_order(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    spent = expense(app_conn, yard, 100)
    entry = UUID(spent["id"])
    decide_refused(app_conn, "send_back", yard.admin, uuid4(), 1, ["x"], "XC404", "not_found")
    decide_refused(
        app_conn,
        "send_back",
        yard.admin,
        UUID(cash(app_conn, yard, 10)["id"]),
        1,
        ["x"],
        "XC422",
        "pettycash_cash_not_reviewed",
    )
    decide_refused(
        app_conn, "send_back", yard.admin, entry, 4, ["x"], "XC409", "pettycash_entry_changed"
    )
    decide_refused(
        app_conn, "send_back", yard.admin, entry, 1, [" "], "XC422", "pettycash_comment_required"
    )
    decide_refused(
        app_conn, "send_back", yard.admin, entry, 1, [None], "XC422", "pettycash_comment_required"
    )
    decide_refused(
        app_conn,
        "send_back",
        yard.admin,
        entry,
        1,
        ["c" * 201],
        "XC422",
        "pettycash_comment_length",
    )
    sent = decide(app_conn, "send_back", yard.admin, spent, "  Attach the receipt ")
    assert (sent["status"], sent["version"]) == ("sentBack", 2)
    again = decide(app_conn, "send_back", yard.admin, spent, "Attach the receipt", version=1)
    assert again == {**sent, "outcome": "replayed"}
    decide_refused(
        app_conn,
        "send_back",
        yard.admin,
        entry,
        2,
        ["Other"],
        "XC422",
        "pettycash_already_sent_back",
    )
    assert reasons(owner_conn, yard)[-1] == (
        "Sent back Wanjiru Kamau's petty cash spending on KAA 501A for 9 Oct 2026."
        " Reason: Attach the receipt."
    )
    assert audit_events(owner_conn, yard.org, "pettycash.sent_back")[0]["entity"] == spent["id"]
    approved = decide(app_conn, "approve", yard.owner, expense(app_conn, yard, 10))
    decide_refused(
        app_conn,
        "send_back",
        yard.admin,
        UUID(approved["id"]),
        2,
        ["x"],
        "XC422",
        "pettycash_not_waiting",
    )


def test_a_rejected_expense_leaves_the_balance_the_figures_and_the_report_until_reopened(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    cash(app_conn, yard, 1000)
    spent = expense(app_conn, yard, 300)
    sent = decide(app_conn, "send_back", yard.admin, spent, "Receipt")
    decide_refused(
        app_conn,
        "reject",
        yard.admin,
        UUID(spent["id"]),
        2,
        [" "],
        "XC422",
        "pettycash_reject_reason_required",
    )
    decide_refused(
        app_conn,
        "reject",
        yard.admin,
        UUID(spent["id"]),
        2,
        ["r" * 201],
        "XC422",
        "pettycash_decision_reason_length",
    )
    rejected = decide(app_conn, "reject", yard.admin, sent, " Not a company cost ")
    assert (rejected["status"], num(rejected["balance"]), rejected["version"]) == (
        "rejected",
        1000,
        3,
    )
    again = decide(app_conn, "reject", yard.admin, spent, "Not a company cost", version=1)
    assert again == {**rejected, "outcome": "replayed"}
    row = stored(owner_conn, spent)
    assert (row["status"], row["reject_reason"], row["sent_back_note"], row["reviewed_by"]) == (
        4,
        "Not a company cost",
        None,
        yard.admin.id,
    )
    seen = overview(app_conn, yard.clerk)
    assert (num(seen["figures"]["expenses"]), num(seen["figures"]["closing_balance"])) == (0, 1000)
    [row_float] = seen["floats"]
    assert (num(row_float["expenses"]), num(row_float["rejected"]), num(row_float["balance"])) == (
        0,
        300,
        1000,
    )
    assert reasons(owner_conn, yard)[-1] == (
        "Rejected Wanjiru Kamau's petty cash spending on KAA 501A for 9 Oct 2026."
        " Reason: Not a company cost."
    )
    decide_refused(
        app_conn, "approve", yard.owner, UUID(spent["id"]), 3, [], "XC422", "pettycash_not_waiting"
    )
    decide_refused(
        app_conn,
        "remove",
        yard.owner,
        UUID(spent["id"]),
        3,
        ["x"],
        "XC422",
        "pettycash_delete_rejected",
    )
    reopened = decide(app_conn, "reopen", yard.admin, rejected, "Receipt found")
    assert (reopened["status"], num(reopened["balance"]), reopened["version"]) == (
        "waiting",
        700,
        4,
    )
    row = stored(owner_conn, spent)
    assert (row["status"], row["reject_reason"], row["reopen_reason"], row["reviewed_by"]) == (
        1,
        None,
        "Receipt found",
        None,
    )
    assert audit_events(owner_conn, yard.org, "pettycash.reopened")[0]["entity"] == spent["id"]


def test_the_reopen_steps_answer_in_their_order(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    """The back-dating limit before the version."""
    old = decide(app_conn, "approve", yard.admin, expense(app_conn, yard, 100, on=day(-5)))
    waiting = expense(app_conn, yard, 100)
    given = cash(app_conn, yard, 100)
    decide_refused(app_conn, "reopen", yard.admin, uuid4(), 1, ["x"], "XC404", "not_found")
    set_back_limit(owner_conn, yard.admin, 3)
    decide_refused(
        app_conn, "reopen", yard.admin, UUID(old["id"]), 9, ["x"], "XC422", "record_too_old"
    )
    decide_refused(
        app_conn,
        "reopen",
        yard.admin,
        UUID(waiting["id"]),
        9,
        ["x"],
        "XC409",
        "pettycash_entry_changed",
    )
    decide_refused(
        app_conn,
        "reopen",
        yard.admin,
        UUID(waiting["id"]),
        1,
        ["x"],
        "XC422",
        "pettycash_not_decided",
    )
    decide_refused(
        app_conn,
        "reopen",
        yard.admin,
        UUID(given["id"]),
        1,
        ["x"],
        "XC422",
        "pettycash_not_decided",
    )
    approved = decide(app_conn, "approve", yard.admin, waiting)
    decide_refused(
        app_conn,
        "reopen",
        yard.admin,
        UUID(waiting["id"]),
        2,
        [None],
        "XC422",
        "pettycash_reopen_reason_required",
    )
    decide_refused(
        app_conn,
        "reopen",
        yard.admin,
        UUID(waiting["id"]),
        2,
        ["r" * 201],
        "XC422",
        "pettycash_decision_reason_length",
    )
    reopened = decide(app_conn, "reopen", yard.admin, approved, "Wrong vehicle")
    assert (reopened["status"], reopened["version"]) == ("waiting", 3)
    assert reasons(owner_conn, yard)[-1] == (
        "Reopened Wanjiru Kamau's petty cash spending on KAA 501A for 9 Oct 2026."
        " Reason: Wrong vehicle."
    )


# --- remove ---


def test_the_remove_steps_answer_in_their_order(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    set_override(owner_conn, yard.clerk, "pettycash.delete_own")
    set_override(owner_conn, yard.clerk, "pettycash.view_all")
    given = cash(app_conn, yard, 1000)
    mine = expense(app_conn, yard, 100)
    theirs = expense(app_conn, yard, 100, who=yard.owner)
    approved = decide(app_conn, "approve", yard.admin, expense(app_conn, yard, 50))

    def refused(
        entry: UUID,
        version: int,
        reason: str | None,
        sqlstate: str,
        code: str,
        who: Member = yard.clerk,
    ) -> dict[str, Any]:
        return decide_refused(app_conn, "remove", who, entry, version, [reason], sqlstate, code)

    refused(uuid4(), 1, "r" * 501, "XC422", "reason_length")
    refused(uuid4(), 1, "r" * 500, "XC404", "not_found")
    refused(UUID(given["id"]), 1, "Wrong", "XC403", "pettycash_delete_cash_permission")
    refused(UUID(approved["id"]), 2, "Wrong", "XC403", "pettycash_delete_approved_permission")
    refused(UUID(theirs["id"]), 1, None, "XC403", "pettycash_delete_other_permission")
    refused(UUID(given["id"]), 1, None, "XC422", "reason_length", yard.owner)
    refused(UUID(given["id"]), 1, " ", "XC422", "reason_length", yard.owner)
    refused(UUID(approved["id"]), 2, None, "XC422", "reason_length", yard.owner)
    refused(UUID(mine["id"]), 3, None, "XC409", "pettycash_entry_changed")
    set_override(owner_conn, yard.clerk, "pettycash.delete_own", False)
    set_override(owner_conn, yard.clerk, "pettycash.delete_approved")
    refused(UUID(mine["id"]), 1, None, "XC403", "pettycash_delete_own_permission")
    set_override(owner_conn, yard.clerk, "pettycash.delete_own")
    set_back_limit(owner_conn, yard.clerk, 0)
    old = expense(app_conn, yard, 10, who=yard.owner, holder=yard.clerk.id, on=day(-1))
    refused(UUID(old["id"]), 1, None, "XC422", "record_too_old")


def test_removing_takes_the_entry_out_of_every_total_and_logs_the_reason(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    """The reason sentences byte for byte; without a typed reason nothing is appended."""
    set_override(owner_conn, yard.clerk, "pettycash.delete_own")
    cash(app_conn, yard, 10000)
    twice = expense(app_conn, yard, 1200)
    quiet = expense(app_conn, yard, 300)
    removed = decide(app_conn, "remove", yard.clerk, twice, " Recorded twice ")
    assert (removed["status"], removed["version"], num(removed["balance"])) == ("waiting", 2, 9700)
    decide_refused(
        app_conn, "remove", yard.clerk, UUID(twice["id"]), 2, ["x"], "XC404", "not_found"
    )
    assert decide(app_conn, "remove", yard.clerk, quiet, None)["outcome"] == "saved"
    assert entries(app_conn, yard.clerk, kinds=["expense"])["total"] == 0
    assert num(overview(app_conn, yard.clerk)["floats"][0]["balance"]) == 10000
    assert reasons(owner_conn, yard)[-2:] == [
        "Removed Wanjiru Kamau's petty cash spending on KAA 501A for 9 Oct 2026."
        " Reason: Recorded twice.",
        "Removed Wanjiru Kamau's petty cash spending on KAA 501A for 9 Oct 2026",
    ]
    row = stored(owner_conn, twice)
    assert (row["removed_by"], row["removal_reason"], row["status"]) == (
        yard.clerk.id,
        "Recorded twice",
        1,
    )
    assert len(audit_events(owner_conn, yard.org, "pettycash.removed")) == 2


def test_removing_cash_given_is_guarded_like_cash_taken_back(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    """The delta is minus the entry's effect."""
    given = cash(app_conn, yard, 10000)
    expense(app_conn, yard, 100)
    taken = cash(app_conn, yard, -50)
    set_override(owner_conn, yard.owner, "pettycash.issue_negative", False)
    refusal = decide_refused(
        app_conn,
        "remove",
        yard.owner,
        UUID(given["id"]),
        1,
        ["Wrong"],
        "XC422",
        "pettycash_below_zero",
    )
    assert num(refusal["balance_after"]) == -150
    assert num(decide(app_conn, "remove", yard.owner, taken, "Wrong")["balance"]) == 9900
    set_override(owner_conn, yard.owner, "pettycash.issue_negative")
    assert num(decide(app_conn, "remove", yard.owner, given, "Wrong")["balance"]) == -100


# --- ticked entries, a day or a period ---


def test_ticked_entries_are_all_approved_or_none(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    small = expense(app_conn, yard, 1000)
    large = expense(app_conn, yard, 6000)
    edited = expense(app_conn, yard, 300)
    sent = decide(app_conn, "send_back", yard.admin, expense(app_conn, yard, 20), "Receipt")
    edited = update(
        app_conn,
        yard.clerk,
        edited,
        line("expense", TODAY, 350, vehicle=yard.kaa, item=yard.tyres),
        1,
    )

    def ticked(*pairs: tuple[Any, Any]) -> Jsonb:
        return Jsonb([{"id": saved["id"], "version": version} for saved, version in pairs])

    def tick_refused(body: Any, sqlstate: str, code: str, who: Member = yard.admin) -> None:
        refuses(app_conn, "pettycash_entries_approve", who, [body], sqlstate, code)

    tick_refused(ticked((small, 1), (large, 1)), "XC403", "pettycash_above_limit")
    tick_refused(ticked((small, 1), (edited, 1)), "XC409", "pettycash_entry_changed")
    tick_refused(ticked((small, 1), (sent, 2)), "XC422", "pettycash_sent_back")
    tick_refused(
        ticked((small, 1), (cash(app_conn, yard, 10), 1)), "XC422", "pettycash_cash_not_reviewed"
    )
    tick_refused(Jsonb([]), "XC422", "pettycash_approve_none")
    tick_refused(None, "XC422", "pettycash_approve_none")
    tick_refused(
        Jsonb([{"id": str(uuid4()), "version": 1} for _ in range(101)]),
        "XC422",
        "pettycash_approve_many",
    )
    tick_refused(ticked((small, 1), ({"id": str(uuid4())}, 1)), "XC404", "not_found")
    tick_refused(ticked((small, 1)), "XC403", "permission_missing", yard.clerk)
    assert stored(owner_conn, small)["status"] == 1
    done = read(
        app_conn,
        "pettycash_entries_approve",
        yard.admin,
        ticked((small, 1), (edited, 2), (small, 1)),
    )
    assert (done["approved"], num(done["total"]), done["skipped"]) == (2, 1350, 0)
    again = read(app_conn, "pettycash_entries_approve", yard.admin, ticked((small, 1)))
    assert (again["approved"], num(again["total"]), again["skipped"]) == (0, 0, 1)
    assert len(audit_events(owner_conn, yard.org, "pettycash.approved")) == 2
    duplicates = ticked(*[(large, 1)] * 101)
    refuses(
        app_conn,
        "pettycash_entries_approve",
        yard.admin,
        [duplicates],
        "XC403",
        "pettycash_above_limit",
    )


def test_approving_a_day_approves_what_the_person_may_and_skips_the_rest(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    """No version check; sent-back entries are neither approved nor skipped."""
    first = expense(app_conn, yard, 1000)
    by_owner = expense(app_conn, yard, 400, who=yard.owner, holder=yard.clerk.id)
    large = expense(app_conn, yard, 6000)
    sent = decide(app_conn, "send_back", yard.admin, expense(app_conn, yard, 5), "Receipt")
    yesterday = expense(app_conn, yard, 700, on=day(-1))
    own = read(app_conn, "pettycash_day_approve", yard.owner, TODAY, None, None)
    assert (own["approved"], own["skipped"]) == (2, 1)
    owner_conn.execute(
        "UPDATE pettycash.entries SET status = 1, reviewed_by = NULL, reviewed_at = NULL "
        "WHERE status = 2"
    )
    done = read(app_conn, "pettycash_day_approve", yard.admin, TODAY, None, None)
    assert (done["approved"], num(done["total"]), done["skipped"]) == (2, 1400, 1)
    statuses = {
        s["id"]: stored(owner_conn, s)["status"] for s in (first, by_owner, large, sent, yesterday)
    }
    assert [statuses[s["id"]] for s in (first, by_owner, large, sent, yesterday)] == [2, 2, 1, 1, 1]
    refuses(
        app_conn,
        "pettycash_day_approve",
        yard.clerk,
        [TODAY, None, None],
        "XC403",
        "permission_missing",
    )
    refuses(
        app_conn, "pettycash_day_approve", yard.admin, [TODAY, None, uuid4()], "XC404", "not_found"
    )
    refuses(
        app_conn,
        "pettycash_day_approve",
        yard.admin,
        [None, None, None],
        "XC422",
        "pettycash_too_old",
    )
    refuses(
        app_conn,
        "pettycash_day_approve",
        yard.admin,
        [day(1), None, None],
        "XC422",
        "pettycash_future_date",
    )


def test_approving_a_period_approves_every_day_in_it(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    """With a last day; one change-log row per approved entry."""
    expense(app_conn, yard, 700, on=day(-3))
    expense(app_conn, yard, 1000, on=day(-1))
    expense(app_conn, yard, 6000, on=day(-1))
    expense(app_conn, yard, 300)
    figures = overview(app_conn, yard.admin, start=day(-3), end=day(-1))["figures"]
    assert (num(figures["waiting"]), figures["waiting_count"]) == (7700, 3)
    before = len(change_rows(owner_conn, yard.org, "pettycash"))
    done = read(app_conn, "pettycash_day_approve", yard.admin, day(-3), day(-1), yard.clerk.id)
    assert (done["approved"], num(done["total"]), done["skipped"]) == (2, 1700, 1)
    assert len(change_rows(owner_conn, yard.org, "pettycash")) == before + 2
    refuses(
        app_conn,
        "pettycash_day_approve",
        yard.admin,
        [day(-1), day(-3), None],
        "XC422",
        "history_dates_order",
    )
    refuses(
        app_conn,
        "pettycash_day_approve",
        yard.admin,
        [None, day(-3), None],
        "XC422",
        "pettycash_range_both",
    )


# --- overview ---


def test_a_week_starts_on_the_organizations_first_day(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    """The week bounds for every first day of the week."""
    monday = day(-4)
    cash(app_conn, yard, 10000, on=monday - timedelta(days=2))
    expense(app_conn, yard, 1000, on=monday)
    cash(app_conn, yard, 2000, on=monday + timedelta(days=2))
    expense(app_conn, yard, 500)
    seen = overview(app_conn, yard.clerk, period="week")
    assert (seen["period"], seen["day"], seen["from_date"], seen["to_date"]) == (
        "week",
        "2026-10-09",
        "2026-10-05",
        "2026-10-11",
    )
    assert [
        num(seen["figures"][k])
        for k in (
            "opening_balance",
            "cash_received",
            "expenses",
            "credit_notes",
            "money_out",
            "closing_balance",
            "waiting",
            "waiting_count",
        )
    ] == [10000, 2000, 1500, 0, 1500, 10500, 1500, 2]
    assert (
        overview(app_conn, yard.clerk, on=monday + timedelta(days=1), period=" week ")["from_date"]
        == "2026-10-05"
    )
    for first_day in range(7):
        set_localization(owner_conn, yard.org, first_day_of_week=first_day)
        seen = overview(app_conn, yard.clerk, period="week")
        start = date.fromisoformat(seen["from_date"])
        assert (start.isoweekday() % 7, date.fromisoformat(seen["to_date"]) - start) == (
            first_day,
            timedelta(days=6),
        )
        assert day(-6) <= start <= TODAY
    set_localization(owner_conn, yard.org, first_day_of_week=6)
    seen = overview(app_conn, yard.clerk, period="week")
    assert (seen["from_date"], seen["to_date"]) == ("2026-10-03", "2026-10-09")
    assert (
        num(seen["figures"]["opening_balance"]) == 0
        and num(seen["figures"]["cash_received"]) == 12000
    )
    refuses(
        app_conn,
        "pettycash_overview_get",
        yard.clerk,
        [None, "month", None, None, None],
        "XC422",
        "pettycash_period_invalid",
    )
    refuses(
        app_conn,
        "pettycash_overview_get",
        yard.clerk,
        [day(1), "month", None, None, None],
        "XC422",
        "pettycash_future_date",
    )


def test_any_period_shows_its_figures_from_the_first_day_to_the_last(
    app_conn: Conn, yard: Yard
) -> None:
    cash(app_conn, yard, 10000, on=day(-10))
    expense(app_conn, yard, 1000, on=day(-6))
    cash(app_conn, yard, 2000, on=day(-5))
    expense(app_conn, yard, 700, on=day(-4))
    credit(app_conn, yard, 300)
    seen = overview(app_conn, yard.clerk, start=day(-6), end=day(-4))
    assert (seen["period"], seen["day"], seen["from_date"], seen["to_date"]) == (
        "range",
        "2026-10-05",
        "2026-10-03",
        "2026-10-05",
    )
    assert [
        num(seen["figures"][k])
        for k in (
            "opening_balance",
            "cash_received",
            "expenses",
            "credit_notes",
            "money_out",
            "closing_balance",
            "waiting",
            "waiting_count",
        )
    ] == [10000, 2000, 1700, 0, 1700, 10300, 1700, 2]
    assert num(seen["floats"][0]["balance"]) == 10000
    later = overview(app_conn, yard.clerk, period="week", start=day(-1), end=day(5))
    assert (
        later["period"],
        num(later["figures"]["opening_balance"]),
        num(later["figures"]["credit_notes"]),
    ) == ("range", 10300, 300)
    assert num(later["figures"]["closing_balance"]) == 10000
    assert overview(app_conn, yard.clerk, start=TODAY, end=TODAY)["period"] == "day"

    def refused(start: date | None, end: date | None, code: str) -> None:
        refuses(
            app_conn,
            "pettycash_overview_get",
            yard.clerk,
            [None, None, None, start, end],
            "XC422",
            code,
        )

    refused(day(-1), None, "pettycash_range_both")
    refused(None, day(-1), "pettycash_range_both")
    refused(day(-1), day(-2), "history_dates_order")
    refused(day(-400), TODAY, "pettycash_range_length")
    refused(day(1), day(2), "pettycash_range_start")
    refused(day(-3651), day(-3600), "pettycash_too_old")
    assert overview(app_conn, yard.clerk, start=day(-366), end=TODAY)["period"] == "range"


def test_a_holder_sees_only_their_own_float_and_a_scoped_viewer_only_what_they_may(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    """Over visible entries only."""
    cash(app_conn, yard, 1000)
    cash(app_conn, yard, 500, holder=yard.owner.id)
    expense(app_conn, yard, 100, who=yard.owner, vehicle=yard.kab)
    seen = overview(app_conn, yard.clerk)
    assert [h["id"] for h in seen["holders"]] == [str(yard.clerk.id)]
    assert [f["holder_id"] for f in seen["floats"]] == [str(yard.clerk.id)]
    refuses(
        app_conn,
        "pettycash_overview_get",
        yard.clerk,
        [None, None, yard.owner.id, None, None],
        "XC404",
        "not_found",
    )
    refuses(
        app_conn,
        "pettycash_entry_list",
        yard.clerk,
        [None, None, yard.owner.id, None, None, None, 1, 100],
        "XC404",
        "not_found",
    )
    assert {i["holder_id"] for i in entries(app_conn, yard.clerk)["items"]} == {str(yard.clerk.id)}
    owner_view = overview(app_conn, yard.owner)
    assert [h["name"] for h in owner_view["holders"]] == ["Antony Maina", "Wanjiru Kamau"]
    assert num(owner_view["floats"][0]["balance"]) == 400
    set_scope(owner_conn, yard.admin, yard.org)
    assert [i["kind"] for i in entries(app_conn, yard.admin)["items"]] == ["cash", "cash"]
    rows = {f["holder_id"]: f for f in overview(app_conn, yard.admin)["floats"]}
    owner_row = rows[str(yard.owner.id)]
    assert (num(owner_row["expenses"]), num(owner_row["balance"])) == (0, 500)
    set_override(owner_conn, yard.clerk, "pettycash.spend", False)
    names = {h["name"]: h["active"] for h in overview(app_conn, yard.owner)["holders"]}
    assert names == {"Antony Maina": True, "Wanjiru Kamau": False}
    refuses(
        app_conn,
        "pettycash_entry_create",
        yard.owner,
        [None, *line("cash", TODAY, 10, holder=yard.clerk.id), None],
        "XC422",
        "pettycash_holder_not_holder",
    )


def test_the_overview_lists_the_actors_rights_and_earliest_date(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    set_back_limit(owner_conn, yard.admin, 3)
    permissions = overview(app_conn, yard.admin)["permissions"]
    assert permissions["holder_id"] is None
    assert (
        num(permissions["approval_limit"]) == 5000 and permissions["earliest_date"] == "2026-10-06"
    )
    granted = {k for k, v in permissions.items() if v is True}
    assert granted == {
        "can_view",
        "can_view_all",
        "can_approve_item",
        "can_approve_day",
        "can_send_back",
        "can_reject",
        "can_reopen",
    }
    owner = overview(app_conn, yard.owner)["permissions"]
    assert all(v is True for k, v in owner.items() if k.startswith("can_"))
    assert (owner["approval_limit"], owner["earliest_date"]) == (None, None)


# --- entries ---


def test_the_list_checks_its_filters_in_order(app_conn: Conn, yard: Yard) -> None:
    def refused(args: list[Any], sqlstate: str, code: str) -> None:
        refuses(app_conn, "pettycash_entry_list", yard.clerk, args, sqlstate, code)

    refused([None, None, None, ["x"], ["x"], "q" * 201, 0, 100], "XC422", "page_out_of_range")
    refused([None, None, None, None, None, None, 1, 101], "XC422", "page_out_of_range")
    refused([TODAY, day(-1), None, ["x"], ["x"], "q" * 201, 1, 100], "XC422", "history_dates_order")
    refused([None, None, None, ["x"], ["x"], "q" * 201, 1, 100], "XC422", "history_text_length")
    refused(
        [None, None, None, ["cash", "refund"], ["x"], " " + "q" * 200 + " ", 1, 100],
        "XC422",
        "pettycash_kind_invalid",
    )
    refused(
        [None, None, None, ["cash"], ["pending"], None, 1, 100], "XC422", "pettycash_status_invalid"
    )
    refused(
        [None, None, None, ["cash"], ["sentback"], None, 1, 100],
        "XC422",
        "pettycash_status_invalid",
    )
    refused([None, None, uuid4(), ["cash"], ["waiting"], None, 1, 100], "XC404", "not_found")


def test_the_list_filters_by_kind_status_text_and_days_and_pages_in_order(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    given = cash(app_conn, yard, 1000, on=day(-2))
    percent = expense(app_conn, yard, 10, note="50% off")
    underscore = expense(app_conn, yard, 20, note="a_b", on=day(-1))
    plain = expense(app_conn, yard, 30, note="ab")
    paid = credit(app_conn, yard, 40, payee="Grace Wambui", note="Loader")
    approved = decide(app_conn, "approve", yard.admin, plain)
    sent = decide(app_conn, "send_back", yard.admin, underscore, "Receipt")
    rejected = decide(app_conn, "reject", yard.admin, expense(app_conn, yard, 50), "No")

    def ids(**kw: Any) -> list[str]:
        return [i["id"] for i in entries(app_conn, yard.owner, **kw)["items"]]

    assert ids(q="%") == [percent["id"]]
    assert ids(q="_") == [underscore["id"]]
    assert ids(q="GRACE") == [paid["id"]] and ids(q="loader") == [paid["id"]]
    assert set(ids(q="kaa 501")) == {percent["id"], underscore["id"], plain["id"], rejected["id"]}
    assert len(ids(q="tyre")) == 4 and len(ids(q="wanjiru")) == 6
    assert ids(kinds=["cash"]) == [given["id"]]
    assert ids(statuses=["approved"]) == [approved["id"]]
    assert ids(statuses=["sentBack"]) == [sent["id"]]
    assert ids(statuses=["rejected"]) == [rejected["id"]]
    assert set(ids(statuses=["waiting"])) == {percent["id"]}
    assert set(ids(kinds=["cash", "credit"])) == {given["id"], paid["id"]}
    assert ids(start=day(-1), end=day(-1)) == [underscore["id"]]
    every = entries(app_conn, yard.owner)["items"]
    keys = [
        (i["entry_date"], ["cash", "expense", "credit"].index(i["kind"]), i["id"]) for i in every
    ]
    assert keys == sorted(keys)
    page = entries(app_conn, yard.owner, page=2, size=4)
    assert (page["total"], [i["id"] for i in page["items"]]) == (6, [i["id"] for i in every[4:]])
    assert entries(app_conn, yard.owner, page=3, size=4)["items"] == []


def test_each_row_carries_the_actors_flags(app_conn: Conn, owner_conn: Conn, yard: Yard) -> None:
    small = expense(app_conn, yard, 100)
    large = expense(app_conn, yard, 6000)
    given = cash(app_conn, yard, 10)
    admin = {i["id"]: i for i in entries(app_conn, yard.admin)["items"]}
    flags = (
        "can_edit",
        "can_remove",
        "can_review",
        "above_limit",
        "can_send_back",
        "can_reject",
        "can_reopen",
    )
    assert [admin[small["id"]][f] for f in flags] == [False, False, True, False, True, True, False]
    assert [admin[large["id"]][f] for f in flags] == [
        False,
        False,
        False,
        True,
        False,
        False,
        False,
    ]
    assert [admin[given["id"]][f] for f in flags] == [False] * 7
    clerk = {i["id"]: i for i in entries(app_conn, yard.clerk)["items"]}
    assert [clerk[small["id"]][f] for f in flags] == [
        True,
        False,
        False,
        False,
        False,
        False,
        False,
    ]
    owner = {i["id"]: i for i in entries(app_conn, yard.owner)["items"]}
    assert [owner[given["id"]][f] for f in flags] == [
        False,
        True,
        False,
        False,
        False,
        False,
        False,
    ]
    assert [owner[large["id"]][f] for f in flags] == [True, True, True, False, True, True, False]


# --- options and dashboard ---


def test_the_options_follow_the_rights_and_the_date(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    add_vehicle(owner_conn, yard.org, yard.petty, "KAD 504D", joined_on=TODAY)
    add_item(owner_conn, yard.org, yard.repairs, "Brakes", stopped_on=TODAY)
    clerk = read(app_conn, "pettycash_options_get", yard.clerk, None)
    assert [v["registration"] for v in clerk["vehicles"]] == ["KAA 501A", "KAD 504D"]
    assert [(i["name"], i["category_name"], i["bucket"]) for i in clerk["items"]] == [
        ("Tyres", "Repairs", 1)
    ]
    assert clerk["holders"] == []
    earlier = read(app_conn, "pettycash_options_get", yard.clerk, day(-1))
    assert [v["registration"] for v in earlier["vehicles"]] == ["KAA 501A"]
    assert [i["name"] for i in earlier["items"]] == ["Brakes", "Tyres"]
    owner = read(app_conn, "pettycash_options_get", yard.owner, None)
    assert [v["registration"] for v in owner["vehicles"]] == ["KAA 501A", "KAB 502B", "KAD 504D"]
    assert [h["name"] for h in owner["holders"]] == ["Antony Maina", "Wanjiru Kamau"]
    refuses(app_conn, "pettycash_options_get", yard.admin, [None], "XC403", "permission_missing")
    set_override(owner_conn, yard.admin, "pettycash.issue")
    issuer = read(app_conn, "pettycash_options_get", yard.admin, None)
    assert (issuer["vehicles"], issuer["items"], len(issuer["holders"])) == ([], [], 2)
    refuses(
        app_conn, "pettycash_options_get", yard.clerk, [day(1)], "XC422", "pettycash_future_date"
    )


def test_the_dashboard_cards_follow_what_the_person_can_act_on(
    app_conn: Conn, owner_conn: Conn, operator_conn: Conn, yard: Yard
) -> None:
    cash(app_conn, yard, 10000)
    expense(app_conn, yard, 1200)
    expense(app_conn, yard, 6000)
    decide(app_conn, "send_back", yard.admin, expense(app_conn, yard, 300), "Receipt")
    decide(app_conn, "approve", yard.admin, expense(app_conn, yard, 400, on=date(2026, 10, 1)))
    decide(app_conn, "approve", yard.admin, expense(app_conn, yard, 50, on=date(2026, 9, 30)))
    clerk = read(app_conn, "pettycash_dashboard_get", yard.clerk)
    assert clerk["approvals"] is None
    card = clerk["float_card"]
    assert (num(card["balance"]), card["waiting_count"], num(card["waiting_total"])) == (
        2050,
        2,
        7200,
    )
    assert (card["sent_back_count"], num(card["approved_this_month"])) == (1, 400)
    admin = read(app_conn, "pettycash_dashboard_get", yard.admin)
    assert admin["float_card"] is None
    approvals = admin["approvals"]
    assert (
        approvals["count"],
        num(approvals["total"]),
        num(approvals["approval_limit"]),
        approvals["above_limit"],
    ) == (
        2,
        7200,
        5000,
        1,
    )
    assert approvals["holders"] == [
        {
            "holder_id": str(yard.clerk.id),
            "name": "Wanjiru Kamau",
            "count": 2,
            "total": 7200.00,
            "oldest": "2026-10-09",
        }
    ]
    set_override(owner_conn, yard.clerk, "dash.pettycash", False)
    refuses(app_conn, "pettycash_dashboard_get", yard.clerk, [], "XC403", "permission_missing")


# --- vehicle report and change-log visibility ---


def _report(app: Conn, who: Member, vehicle: UUID) -> Any:
    return read(app, "setup_vehicle_report", who, vehicle, "month", None, None)


def test_approved_spending_reaches_the_vehicle_report_and_credit_notes_never(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    """Only approved, non-removed expenses post, with the item's bucket."""
    cash(app_conn, yard, 5000)
    spent = expense(app_conn, yard, 1200)
    credit(app_conn, yard, 800)
    before = _report(app_conn, yard.owner, yard.kaa)
    assert [p for p in before["postings"] if p["source"] == "pettycash"] == []
    decide(app_conn, "approve", yard.admin, spent)
    after = _report(app_conn, yard.owner, yard.kaa)
    [posting] = [p for p in after["postings"] if p["source"] == "pettycash"]
    assert posting == {
        "item_id": spent["id"],
        "version_id": spent["id"],
        "day": "2026-10-09",
        "name": "Tyres",
        "kind": 1,
        "amount": 1200.00,
        "bucket": 1,
        "source": "pettycash",
    }
    assert num(after["money_out"]) - num(before["money_out"]) == 1200
    assert num(after["repairs"]) - num(before["repairs"]) == 1200
    assert num(before["net"]) - num(after["net"]) == 1200
    reopened = decide(app_conn, "reopen", yard.admin, {**spent, "version": 2}, "Check")
    assert [p for p in _report(app_conn, yard.owner, yard.kaa)["postings"] if p["source"]] == []
    decide(app_conn, "reject", yard.admin, reopened, "No")
    assert [p for p in _report(app_conn, yard.owner, yard.kaa)["postings"] if p["source"]] == []


def test_a_removed_approved_expense_leaves_the_report(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    spent = decide(app_conn, "approve", yard.admin, expense(app_conn, yard, 900))
    assert len([p for p in _report(app_conn, yard.owner, yard.kaa)["postings"] if p["source"]]) == 1
    decide(app_conn, "remove", yard.owner, spent, "Duplicate")
    assert [p for p in _report(app_conn, yard.owner, yard.kaa)["postings"] if p["source"]] == []


def test_an_approved_expense_whose_category_has_no_bucket_posts_as_a_charge(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    """Categories made under main categories carry no bucket; their costs count as charges, as a
    scheduled cost without one does, so the report's buckets still add up to its money out."""
    owner_conn.execute(
        "UPDATE setup.expense_categories SET bucket = NULL WHERE id = %s", (yard.repairs,)
    )
    before = _report(app_conn, yard.owner, yard.kaa)
    spent = decide(app_conn, "approve", yard.admin, expense(app_conn, yard, 900))
    after = _report(app_conn, yard.owner, yard.kaa)
    [posting] = [p for p in after["postings"] if p["source"] == "pettycash"]
    assert (posting["item_id"], posting["bucket"]) == (spent["id"], 2)
    assert num(after["charges"]) - num(before["charges"]) == 900
    assert num(after["money_out"]) - num(before["money_out"]) == 900
    assert num(before["net"]) - num(after["net"]) == 900


def test_a_scoped_viewer_sees_petty_cash_history_only_for_their_vehicles(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    expense(app_conn, yard, 100)
    expense(app_conn, yard, 100, who=yard.owner, vehicle=yard.kab)
    cash(app_conn, yard, 100)

    def seen(who: Member) -> list[str]:
        page = read(
            app_conn, "history_list", who, 1, 100, "pettycash", None, None, None, None, True
        )
        return [str(item["reason"]) for item in page["items"]]

    assert len(seen(yard.owner)) == 3
    set_scope(owner_conn, yard.admin, yard.org, companies=[yard.petty])
    assert seen(yard.admin) == [
        "Recorded Wanjiru Kamau's petty cash spending on KAA 501A for 9 Oct 2026"
    ]


def shared(
    app: Conn,
    yard: Yard,
    units: Any,
    amount: Any,
    parts: list[tuple[UUID, Any]],
    *,
    entry_id: UUID | None = None,
    kind: str = "expense",
    who: Member | None = None,
) -> Any:
    fields = line(kind, TODAY, amount, item=yard.tyres if kind == "expense" else None, units=units)
    allocations = Jsonb([{"vehicle_id": str(v), "amount": str(a)} for v, a in parts])
    return read(app, "pettycash_entry_create", who or yard.owner, entry_id, *fields, allocations)


def test_a_shared_purchase_is_one_entry_per_vehicle_and_recounts(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    """One waiting entry per vehicle with the purchase as bought, the first under the purchase
    id; a retry answers it; the size counts the parts not removed and not rejected; a new
    item, units or amount takes a part out while a rejected part keeps its group; a part
    cannot move onto a vehicle its purchase already has."""
    kac = add_vehicle(owner_conn, yard.org, yard.petty, "KAC 503C", joined_on=day(-30))
    purchase = uuid4()
    made = shared(
        app_conn, yard, 3, 50, [(yard.kaa, 50), (yard.kab, 50), (kac, 50)], entry_id=purchase
    )
    assert (made["id"], made["outcome"], made["status"], num(made["balance"])) == (
        str(purchase),
        "created",
        "waiting",
        -150,
    )
    rows = owner_conn.execute(
        "SELECT * FROM pettycash.entries WHERE group_id = %s ORDER BY vehicle_id = %s DESC",
        (purchase, yard.kaa),
    ).fetchall()
    assert len(rows) == 3
    assert {(r["units"], r["unit_amount"], r["status"]) for r in rows} == {(1, 50, 1)}
    assert {(r["group_total"], r["group_units"], r["group_unit_amount"]) for r in rows} == {
        (150, 3, 50)
    }
    assert rows[0]["id"] == purchase
    assert len(change_rows(owner_conn, yard.org, "pettycash")) == 3
    again = shared(app_conn, yard, 1, 9, [(yard.kaa, 9)], entry_id=purchase)
    assert (again["id"], again["outcome"]) == (str(purchase), "replayed")

    def groups() -> dict[str, Any]:
        listing = entries(app_conn, yard.owner)
        return {item["id"]: item["group"] for item in listing["items"] if item["group"]}

    seen = groups()
    assert len(seen) == 3
    assert {(g["id"], g["size"], num(g["total"]), num(g["units"])) for g in seen.values()} == {
        (str(purchase), 3, 150, 3)
    }
    by_vehicle = {r["vehicle_id"]: r for r in rows}
    second = {"id": str(by_vehicle[yard.kab]["id"]), "version": 1}
    third = {"id": str(by_vehicle[kac]["id"]), "version": 1}
    decide(app_conn, "reject", yard.admin, second, "Not ours")
    assert {g["size"] for g in groups().values()} == {2}
    decide(app_conn, "remove", yard.owner, third, "Bought twice")
    assert {g["size"] for g in groups().values()} == {1}
    moved = line("expense", TODAY, 50, vehicle=yard.kab, item=yard.tyres)
    error = refuses(
        app_conn,
        "pettycash_entry_update",
        yard.owner,
        [purchase, *moved, 1],
        "XC422",
        "expense_purchase_has_vehicle",
    )
    assert detail(error) == {"registration": "KAB 502B"}
    update(
        app_conn, yard.owner, made, line("expense", TODAY, 60, vehicle=yard.kaa, item=yard.tyres), 1
    )
    alone = stored(owner_conn, made)
    assert (alone["group_id"], alone["group_total"], alone["units"]) == (None, None, 1)
    left = groups()
    assert list(left) == [second["id"]]
    assert (left[second["id"]]["id"], left[second["id"]]["size"]) == (str(purchase), 0)


def test_a_shared_purchase_follows_the_purchase_rules_and_only_an_expense_takes_one(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    sum_wrong = refuses(
        app_conn,
        "pettycash_entry_create",
        yard.owner,
        [
            None,
            *line("expense", TODAY, 100, item=yard.tyres),
            Jsonb(
                [
                    {"vehicle_id": str(yard.kaa), "amount": "60"},
                    {"vehicle_id": str(yard.kab), "amount": "50"},
                ]
            ),
        ],
        "XC422",
        "expense_allocation_sum",
    )
    assert detail(sum_wrong) == {}
    refuses(
        app_conn,
        "pettycash_entry_create",
        yard.owner,
        [
            None,
            *line("expense", TODAY, 100, item=yard.tyres),
            Jsonb(
                [
                    {"vehicle_id": str(yard.kaa), "amount": "50"},
                    {"vehicle_id": str(yard.kaa), "amount": "50"},
                ]
            ),
        ],
        "XC422",
        "expense_vehicles_invalid",
    )
    one_part = Jsonb([{"vehicle_id": str(yard.kaa), "amount": "100"}])
    for kind, code in (
        ("cash", "pettycash_line_cash_shape"),
        ("credit", "pettycash_line_credit_vehicle"),
    ):
        refuses(
            app_conn,
            "pettycash_entry_create",
            yard.owner,
            [None, *line(kind, TODAY, 100, holder=yard.clerk.id), one_part],
            "XC422",
            code,
        )
    plain = read(
        app_conn,
        "pettycash_entry_create",
        yard.owner,
        None,
        *line("expense", TODAY, 100, item=yard.tyres),
        one_part,
    )
    row = stored(owner_conn, plain)
    assert (row["vehicle_id"], row["group_id"], row["total"]) == (yard.kaa, None, 100)
    hidden = refuses(
        app_conn,
        "pettycash_entry_create",
        yard.clerk,
        [
            None,
            *line("expense", TODAY, 100, item=yard.tyres),
            Jsonb(
                [
                    {"vehicle_id": str(yard.kaa), "amount": "50"},
                    {"vehicle_id": str(yard.kab), "amount": "50"},
                ]
            ),
        ],
        "XC422",
        "pettycash_vehicle_scope",
    )
    assert detail(hidden) == {}
