"""The change-log read (``api.history_list``), called as ``xcode_app``.

Rows of sections no routine writes yet (companies, vehicles, investment, revenue, recurring,
expenses) are seeded as owner directly into ``tenancy.change_log``, each with the next
``settings_version``; people rows come from the people routines.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest

from ..support.scenario import T0, Conn, call
from ..support.tenancy import (
    REQUEST,
    Member,
    add_company,
    add_recurring,
    add_vehicle,
    change_log,
    create_person,
    provision_member,
    refused,
    seed_change,
    set_localization,
    set_override,
    set_scope,
    update_person,
)


def _history(
    app: Conn,
    who: Member,
    *,
    page: int = 1,
    size: int = 25,
    section: str | None = None,
    day_from: date | None = None,
    day_to: date | None = None,
    text: str | None = None,
    before: int | None = None,
    total: bool | None = True,
) -> dict[str, Any]:
    result: dict[str, Any] = call(
        app,
        "history_list",
        who.id,
        who.org,
        REQUEST,
        page,
        size,
        section,
        day_from,
        day_to,
        text,
        before,
        total,
        T0,
    )
    return result


def _history_refused(app: Conn, who: Member, sqlstate: str, code: str, **filters: Any) -> None:
    defaults: dict[str, Any] = {
        "page": 1,
        "size": 25,
        "section": None,
        "day_from": None,
        "day_to": None,
        "text": None,
        "before": None,
        "total": True,
    }
    f = {**defaults, **filters}
    args = [
        who.id,
        who.org,
        REQUEST,
        f["page"],
        f["size"],
        f["section"],
        f["day_from"],
        f["day_to"],
        f["text"],
        f["before"],
        f["total"],
        T0,
    ]
    refused(app, "history_list", args, sqlstate, code)


def _reasons(page: dict[str, Any]) -> list[str]:
    return [item["reason"] for item in page["items"]]


def _versions(page: dict[str, Any]) -> list[int]:
    return [item["version"] for item in page["items"]]


def _utc(day: int, hour: int, minute: int = 0, second: int = 0, month: int = 10) -> datetime:
    return datetime(2026, month, day, hour, minute, second, tzinfo=UTC)


@pytest.fixture
def owner(operator_conn: Conn) -> Member:
    return provision_member(operator_conn, 1, "Owner", "Olive", "Owner")


@pytest.fixture
def office(operator_conn: Conn, owner: Member) -> Member:
    return provision_member(operator_conn, 2, "Office admin", "Otto", "Office")


@pytest.fixture
def clerk(operator_conn: Conn, owner: Member) -> Member:
    return provision_member(operator_conn, 3, "Revenue clerk", "Cleo", "Clerk")


def _expenses(owner_conn: Conn, who: Member, reason: str, **kwargs: Any) -> int:
    return seed_change(owner_conn, who.org, who.id, "expenses", uuid4(), reason, **kwargs)


# --- permission and validation ---


def test_history_needs_audit_view(app_conn: Conn, clerk: Member) -> None:
    _history_refused(app_conn, clerk, "XC403", "permission_missing")


def test_history_refuses_a_stranger(app_conn: Conn, owner: Member) -> None:
    stranger = Member(uuid4(), owner.org, "x@example.com", "0700000000", "X", "Y", "Owner")
    _history_refused(app_conn, stranger, "XC403", "not_member")


def test_the_first_date_cannot_be_after_the_last(app_conn: Conn, owner: Member) -> None:
    _history_refused(
        app_conn,
        owner,
        "XC422",
        "history_dates_order",
        day_from=date(2026, 10, 9),
        day_to=date(2026, 10, 8),
    )


def test_one_day_may_be_both_the_first_and_the_last_date(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    _expenses(owner_conn, owner, "Turned off expense category Fuel", occurred_at=_utc(9, 8))
    page = _history(app_conn, owner, day_from=date(2026, 10, 9), day_to=date(2026, 10, 9))
    assert _reasons(page) == ["Turned off expense category Fuel"]


def test_search_text_of_two_hundred_and_one_characters_after_trimming_is_refused(
    app_conn: Conn, owner: Member
) -> None:
    _history_refused(app_conn, owner, "XC422", "history_text_length", text="x" * 201)
    _history_refused(app_conn, owner, "XC422", "history_text_length", text=" " + "x" * 201 + " ")


def test_search_text_of_two_hundred_characters_after_trimming_is_accepted(
    app_conn: Conn, owner: Member
) -> None:
    page = _history(app_conn, owner, text="  " + "x" * 200 + "  ")
    assert page["items"] == []


@pytest.mark.parametrize("before", [0, -1])
def test_before_must_be_a_change_log_version(app_conn: Conn, owner: Member, before: int) -> None:
    _history_refused(app_conn, owner, "XC422", "history_before_invalid", before=before)


@pytest.mark.parametrize(("page", "size"), [(0, 10), (1, 0), (1, 101), (100001, 10), (-1, 10)])
def test_history_refuses_a_page_outside_the_bounds(
    app_conn: Conn, owner: Member, page: int, size: int
) -> None:
    _history_refused(app_conn, owner, "XC422", "page_out_of_range", page=page, size=size)


# --- the shape of an entry ---


def test_an_entry_carries_the_version_section_entity_reason_actor_and_snapshots(
    app_conn: Conn, owner_conn: Conn, owner: Member, office: Member
) -> None:
    entity = uuid4()
    version = seed_change(
        owner_conn,
        office.org,
        office.id,
        "expenses",
        entity,
        "Renamed expense category Fuel to Diesel",
        occurred_at=_utc(9, 8),
        before='{"Name":"Fuel"}',
        after='{"Name":"Diesel"}',
    )
    item = _history(app_conn, owner)["items"][0]
    assert set(item) == {
        "version",
        "section",
        "entity_id",
        "reason",
        "occurred_at",
        "actor_id",
        "actor_name",
        "before",
        "after",
    }
    assert item["version"] == version
    assert item["section"] == "expenses"
    assert item["entity_id"] == str(entity)
    assert item["reason"] == "Renamed expense category Fuel to Diesel"
    assert item["actor_id"] == str(office.id)
    assert item["actor_name"] == "Otto Office"
    assert (item["before"], item["after"]) == ('{"Name":"Fuel"}', '{"Name":"Diesel"}')
    assert datetime.fromisoformat(item["occurred_at"]) == _utc(9, 8)


def test_a_creation_keeps_its_null_text_and_a_removal_its_null_value(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    _expenses(owner_conn, owner, "Created", before="null", after='{"Name":"Fuel"}')
    _expenses(owner_conn, owner, "Removed", before='{"Name":"Fuel"}', after=None)
    first, second = _history(app_conn, owner)["items"]
    assert (second["before"], second["after"]) == ("null", '{"Name":"Fuel"}')
    assert (first["before"], first["after"]) == ('{"Name":"Fuel"}', None)


def test_entries_come_newest_version_first(app_conn: Conn, owner_conn: Conn, owner: Member) -> None:
    versions = [_expenses(owner_conn, owner, f"Change {n}") for n in range(4)]
    page = _history(app_conn, owner)
    assert _versions(page) == sorted(versions, reverse=True)
    assert _reasons(page) == ["Change 3", "Change 2", "Change 1", "Change 0"]


def test_the_actor_name_comes_from_the_membership(
    app_conn: Conn, owner_conn: Conn, owner: Member, office: Member
) -> None:
    _expenses(owner_conn, owner, "By the owner")
    _expenses(owner_conn, office, "By the office")
    page = _history(app_conn, owner)
    assert [(i["reason"], i["actor_name"]) for i in page["items"]] == [
        ("By the office", "Otto Office"),
        ("By the owner", "Olive Owner"),
    ]


# --- filters ---


def test_the_section_filter_matches_one_section_exactly(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    company = add_company(owner_conn, owner.org, "Alpha Sacco")
    seed_change(owner_conn, owner.org, owner.id, "companies", company, "Added company Alpha Sacco")
    _expenses(owner_conn, owner, "Turned off expense category Fuel")
    seed_change(owner_conn, owner.org, owner.id, "logo", owner.org, "Uploaded a new logo")
    assert _reasons(_history(app_conn, owner, section="companies")) == ["Added company Alpha Sacco"]
    assert _reasons(_history(app_conn, owner, section="logo")) == ["Uploaded a new logo"]
    assert _history(app_conn, owner, section="people")["items"] == []
    assert _history(app_conn, owner, section="Companies")["items"] == []


def test_a_blank_section_means_every_section(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    _expenses(owner_conn, owner, "One")
    seed_change(owner_conn, owner.org, owner.id, "logo", owner.org, "Two")
    for blank in (None, "", "   "):
        assert len(_history(app_conn, owner, section=blank)["items"]) == 2


def test_the_text_filter_matches_the_reason_ignoring_case(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    _expenses(owner_conn, owner, "Renamed expense category Fuel to Diesel")
    _expenses(owner_conn, owner, "Turned off expense category Tyres")
    assert _reasons(_history(app_conn, owner, text="RENAMED")) == [
        "Renamed expense category Fuel to Diesel"
    ]
    assert len(_history(app_conn, owner, text="expense category")["items"]) == 2


def test_the_text_filter_is_trimmed_and_blank_means_no_filter(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    _expenses(owner_conn, owner, "Renamed expense category Fuel to Diesel")
    _expenses(owner_conn, owner, "Turned off expense category Tyres")
    assert len(_history(app_conn, owner, text="  Tyres  ")["items"]) == 1
    for blank in (None, "", "   "):
        assert len(_history(app_conn, owner, text=blank)["items"]) == 2


def test_the_text_filter_matches_the_actors_first_and_last_name(
    app_conn: Conn, owner_conn: Conn, owner: Member, office: Member
) -> None:
    _expenses(owner_conn, owner, "By the owner")
    _expenses(owner_conn, office, "By the office")
    assert _reasons(_history(app_conn, owner, text="otto office")) == ["By the office"]
    assert _reasons(_history(app_conn, owner, text="ve ow")) == ["By the owner"]
    assert _history(app_conn, owner, text="Office Otto")["items"] == []


def test_a_percent_sign_in_the_text_is_taken_literally(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    _expenses(owner_conn, owner, "Added a 100% discount")
    _expenses(owner_conn, owner, "Added 1000 discounts")
    assert _reasons(_history(app_conn, owner, text="100%")) == ["Added a 100% discount"]
    assert _reasons(_history(app_conn, owner, text="%")) == ["Added a 100% discount"]


def test_an_underscore_in_the_text_is_taken_literally(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    _expenses(owner_conn, owner, "Renamed to Mary_Jane")
    _expenses(owner_conn, owner, "Renamed to MaryXJane")
    assert _reasons(_history(app_conn, owner, text="y_J")) == ["Renamed to Mary_Jane"]
    assert _reasons(_history(app_conn, owner, text="_")) == ["Renamed to Mary_Jane"]


def test_a_backslash_in_the_text_is_taken_literally(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    backslash = chr(92)
    _expenses(owner_conn, owner, f"Moved a{backslash}b")
    _expenses(owner_conn, owner, "Moved ab")
    assert _reasons(_history(app_conn, owner, text=f"a{backslash}b")) == [f"Moved a{backslash}b"]


@pytest.fixture
def instants(owner_conn: Conn, owner: Member) -> list[int]:
    """Rows around the Nairobi midnight of 2026-10-09 (21:00 UTC on the 8th)."""
    moments = [
        _utc(8, 20, 59, 59),
        _utc(8, 21, 0, 0),
        _utc(8, 22, 30),
        _utc(9, 20, 59, 59),
        _utc(9, 21, 0, 0),
    ]
    return [
        _expenses(owner_conn, owner, f"Moment {n}", occurred_at=at) for n, at in enumerate(moments)
    ]


def test_days_are_bounded_in_the_organization_time_zone_nairobi(
    app_conn: Conn, owner: Member, instants: list[int]
) -> None:
    page = _history(app_conn, owner, day_from=date(2026, 10, 9), day_to=date(2026, 10, 9))
    assert _reasons(page) == ["Moment 3", "Moment 2", "Moment 1"]
    page = _history(app_conn, owner, day_from=date(2026, 10, 8), day_to=date(2026, 10, 8))
    assert _reasons(page) == ["Moment 0"]
    page = _history(app_conn, owner, day_from=date(2026, 10, 10), day_to=date(2026, 10, 10))
    assert _reasons(page) == ["Moment 4"]


def test_days_are_bounded_in_the_organization_time_zone_utc(
    app_conn: Conn, owner_conn: Conn, owner: Member, instants: list[int]
) -> None:
    set_localization(owner_conn, owner.org, time_zone="UTC")
    page = _history(app_conn, owner, day_from=date(2026, 10, 8), day_to=date(2026, 10, 8))
    assert _reasons(page) == ["Moment 2", "Moment 1", "Moment 0"]
    page = _history(app_conn, owner, day_from=date(2026, 10, 9), day_to=date(2026, 10, 9))
    assert _reasons(page) == ["Moment 4", "Moment 3"]


def test_a_row_at_22_30_utc_falls_on_the_next_day_in_nairobi_only(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    _expenses(owner_conn, owner, "Late", occurred_at=_utc(8, 22, 30))
    day = date(2026, 10, 8)
    next_day = date(2026, 10, 9)
    set_localization(owner_conn, owner.org, time_zone="UTC")
    assert len(_history(app_conn, owner, day_from=day, day_to=day)["items"]) == 1
    assert _history(app_conn, owner, day_from=next_day, day_to=next_day)["items"] == []
    set_localization(owner_conn, owner.org, time_zone="Africa/Nairobi")
    assert _history(app_conn, owner, day_from=day, day_to=day)["items"] == []
    assert len(_history(app_conn, owner, day_from=next_day, day_to=next_day)["items"]) == 1


def test_the_first_date_alone_and_the_last_date_alone_are_open_ended(
    app_conn: Conn, owner: Member, instants: list[int]
) -> None:
    only_from = _history(app_conn, owner, day_from=date(2026, 10, 10))
    assert _reasons(only_from) == ["Moment 4"]
    only_to = _history(app_conn, owner, day_to=date(2026, 10, 8))
    assert _reasons(only_to) == ["Moment 0"]


def test_every_filter_together_narrows_the_page(
    app_conn: Conn, owner_conn: Conn, owner: Member, office: Member
) -> None:
    company = add_company(owner_conn, owner.org, "Alpha Sacco")
    seed_change(
        owner_conn,
        owner.org,
        owner.id,
        "companies",
        company,
        "Archived company Alpha Sacco",
        occurred_at=_utc(9, 8),
    )
    seed_change(
        owner_conn,
        owner.org,
        office.id,
        "companies",
        company,
        "Archived company Beta Sacco",
        occurred_at=_utc(9, 9),
    )
    seed_change(
        owner_conn,
        owner.org,
        office.id,
        "companies",
        company,
        "Archived company Gamma Sacco",
        occurred_at=_utc(2, 9),
    )
    _expenses(owner_conn, office, "Archived expense category Fuel", occurred_at=_utc(9, 10))
    page = _history(
        app_conn,
        owner,
        section="companies",
        day_from=date(2026, 10, 9),
        day_to=date(2026, 10, 9),
        text="archived company",
    )
    assert _reasons(page) == ["Archived company Beta Sacco", "Archived company Alpha Sacco"]
    page = _history(
        app_conn,
        owner,
        section="companies",
        day_from=date(2026, 10, 9),
        day_to=date(2026, 10, 9),
        text="otto",
    )
    assert _reasons(page) == ["Archived company Beta Sacco"]
    assert page["total"] == 1


# --- paging ---


@pytest.fixture
def seven(owner_conn: Conn, owner: Member) -> list[int]:
    return [_expenses(owner_conn, owner, f"Change {n}") for n in range(7)]


def test_offset_paging_cuts_the_newest_first_list(
    app_conn: Conn, owner: Member, seven: list[int]
) -> None:
    newest_first = sorted(seven, reverse=True)
    assert _versions(_history(app_conn, owner, page=1, size=3)) == newest_first[:3]
    assert _versions(_history(app_conn, owner, page=2, size=3)) == newest_first[3:6]
    assert _versions(_history(app_conn, owner, page=3, size=3)) == newest_first[6:]


def test_has_more_and_next_before_describe_the_rest_of_the_list(
    app_conn: Conn, owner: Member, seven: list[int]
) -> None:
    newest_first = sorted(seven, reverse=True)
    first = _history(app_conn, owner, page=1, size=3)
    assert (first["has_more"], first["next_before"]) == (True, newest_first[2])
    last = _history(app_conn, owner, page=3, size=3)
    assert (last["has_more"], last["next_before"]) == (False, None)


def test_a_page_that_ends_exactly_at_the_last_entry_has_no_more(
    app_conn: Conn, owner: Member, seven: list[int]
) -> None:
    page = _history(app_conn, owner, page=1, size=7)
    assert (len(page["items"]), page["has_more"], page["next_before"]) == (7, False, None)
    page = _history(app_conn, owner, page=1, size=6)
    assert (len(page["items"]), page["has_more"]) == (6, True)


def test_seek_paging_returns_the_entries_below_the_given_version(
    app_conn: Conn, owner: Member, seven: list[int]
) -> None:
    newest_first = sorted(seven, reverse=True)
    page = _history(app_conn, owner, size=3, before=newest_first[2])
    assert _versions(page) == newest_first[3:6]
    assert (page["has_more"], page["next_before"]) == (True, newest_first[5])
    last = _history(app_conn, owner, size=3, before=newest_first[5])
    assert _versions(last) == newest_first[6:]
    assert (last["has_more"], last["next_before"]) == (False, None)


def test_seek_paging_ignores_the_page_offset(
    app_conn: Conn, owner: Member, seven: list[int]
) -> None:
    newest_first = sorted(seven, reverse=True)
    page = _history(app_conn, owner, page=5, size=2, before=newest_first[1])
    assert _versions(page) == newest_first[2:4]


def test_seek_paging_and_offset_paging_return_the_same_versions_for_the_same_filter(
    app_conn: Conn, owner_conn: Conn, owner: Member, office: Member, seven: list[int]
) -> None:
    for n in range(4):
        seed_change(owner_conn, owner.org, office.id, "logo", owner.org, f"Logo {n}")
    by_offset: list[int] = []
    page_number = 1
    while True:
        page = _history(app_conn, owner, page=page_number, size=2, text="change")
        by_offset += _versions(page)
        if not page["has_more"]:
            break
        page_number += 1
    by_seek: list[int] = []
    before: int | None = None
    while True:
        page = _history(app_conn, owner, size=2, text="change", before=before)
        by_seek += _versions(page)
        if not page["has_more"]:
            break
        before = page["next_before"]
    assert by_offset == by_seek == sorted(seven, reverse=True)


def test_total_is_absent_when_not_asked_for_and_counts_otherwise(
    app_conn: Conn, owner: Member, seven: list[int]
) -> None:
    assert _history(app_conn, owner, total=False)["total"] is None
    assert _history(app_conn, owner, total=True)["total"] == 7
    assert _history(app_conn, owner, total=None)["total"] == 7


def test_total_ignores_the_seek_position_and_the_page_size(
    app_conn: Conn, owner: Member, seven: list[int]
) -> None:
    page = _history(app_conn, owner, size=2, before=sorted(seven)[2])
    assert _versions(page) == [sorted(seven)[1], sorted(seven)[0]]
    assert page["total"] == 7


def test_total_counts_only_the_filtered_entries(
    app_conn: Conn, owner_conn: Conn, owner: Member, seven: list[int]
) -> None:
    seed_change(owner_conn, owner.org, owner.id, "logo", owner.org, "Uploaded a new logo")
    assert _history(app_conn, owner, section="expenses", size=2)["total"] == 7
    assert _history(app_conn, owner, section="logo")["total"] == 1
    assert _history(app_conn, owner)["total"] == 8


def test_an_empty_log_gives_an_empty_page(app_conn: Conn, owner: Member) -> None:
    page = _history(app_conn, owner)
    assert page == {"items": [], "total": 0, "has_more": False, "next_before": None}


# --- visibility ---


@dataclass(frozen=True, slots=True)
class Ledger:
    alpha: UUID
    beta: UUID
    a1: UUID
    a2: UUID
    b1: UUID
    company_viewer: Member
    vehicle_viewer: Member


EVERYTHING = [
    "company alpha",
    "company beta",
    "vehicle a1",
    "vehicle b1",
    "investment a1",
    "investment b1",
    "revenue a1",
    "revenue b1",
    "recurring a1+a2",
    "recurring a1",
    "recurring a1+b1",
    "recurring second revision adds b1",
    "recurring second revision drops b1",
    "expenses",
    "settings organization",
    "settings businessDate",
    "settings localization",
    "settings branding",
    "settings securityPolicy",
    "settings logo",
]


@pytest.fixture
def ledger(owner_conn: Conn, operator_conn: Conn, owner: Member, office: Member) -> Ledger:
    org = owner.org
    alpha = add_company(owner_conn, org, "Alpha Sacco")
    beta = add_company(owner_conn, org, "Beta Sacco")
    a1 = add_vehicle(owner_conn, org, alpha, "KDA 482M")
    a2 = add_vehicle(owner_conn, org, alpha, "KDB 100A")
    b1 = add_vehicle(owner_conn, org, beta, "KDC 200B")
    money = Decimal(100)

    def log(section: str, reason: str, entity: UUID, vehicle: UUID | None = None) -> None:
        seed_change(owner_conn, org, owner.id, section, entity, reason, vehicle=vehicle)

    log("companies", "company alpha", alpha)
    log("companies", "company beta", beta)
    log("vehicles", "vehicle a1", a1, a1)
    log("vehicles", "vehicle b1", b1, b1)
    log("investment", "investment a1", a1, a1)
    log("investment", "investment b1", b1, b1)
    log("revenue", "revenue a1", uuid4(), a1)
    log("revenue", "revenue b1", uuid4(), b1)
    log("recurring", "recurring a1+a2", add_recurring(owner_conn, org, [{a1: money, a2: money}]))
    log("recurring", "recurring a1", add_recurring(owner_conn, org, [{a1: money}]))
    log("recurring", "recurring a1+b1", add_recurring(owner_conn, org, [{a1: money, b1: money}]))
    log(
        "recurring",
        "recurring second revision adds b1",
        add_recurring(owner_conn, org, [{a1: money}, {a1: money, b1: money}]),
    )
    log(
        "recurring",
        "recurring second revision drops b1",
        add_recurring(owner_conn, org, [{a1: money, b1: money}, {a1: money}]),
    )
    log("expenses", "expenses", uuid4())
    for section in ("organization", "businessDate", "localization", "branding", "securityPolicy"):
        log(section, f"settings {section}", org)
    log("logo", "settings logo", org)
    company_viewer = provision_member(operator_conn, 5, "Office admin", "Cam", "Viewer")
    set_scope(owner_conn, company_viewer, org, companies=[alpha])
    vehicle_viewer = provision_member(operator_conn, 6, "Office admin", "Vic", "Viewer")
    set_scope(owner_conn, vehicle_viewer, org, vehicles=[a1])
    return Ledger(alpha, beta, a1, a2, b1, company_viewer, vehicle_viewer)


def test_an_all_companies_viewer_sees_every_section(
    app_conn: Conn, office: Member, ledger: Ledger
) -> None:
    page = _history(app_conn, office, size=100)
    assert sorted(_reasons(page)) == sorted(EVERYTHING)
    assert page["total"] == len(EVERYTHING)


def test_a_company_scoped_viewer_sees_the_rows_of_their_companies_and_vehicles(
    app_conn: Conn, ledger: Ledger
) -> None:
    page = _history(app_conn, ledger.company_viewer, size=100)
    assert sorted(_reasons(page)) == sorted(
        [
            "company alpha",
            "vehicle a1",
            "investment a1",
            "revenue a1",
            "recurring a1+a2",
            "recurring a1",
            "recurring second revision drops b1",
            "expenses",
        ]
    )
    assert page["total"] == 8


def test_a_vehicle_scoped_viewer_sees_the_rows_of_their_vehicles_and_those_companies(
    app_conn: Conn, ledger: Ledger
) -> None:
    page = _history(app_conn, ledger.vehicle_viewer, size=100)
    assert sorted(_reasons(page)) == sorted(
        [
            "company alpha",
            "vehicle a1",
            "investment a1",
            "revenue a1",
            "recurring a1",
            "recurring second revision drops b1",
            "expenses",
        ]
    )
    assert page["total"] == 7


def test_a_recurring_item_is_decided_by_its_highest_revision(
    app_conn: Conn, ledger: Ledger
) -> None:
    page = _history(app_conn, ledger.company_viewer, size=100, section="recurring")
    assert "recurring second revision adds b1" not in _reasons(page)
    assert "recurring second revision drops b1" in _reasons(page)


@pytest.mark.parametrize(
    "section",
    ["organization", "businessDate", "localization", "branding", "securityPolicy", "logo"],
)
def test_settings_sections_are_never_shown_to_a_scoped_viewer(
    app_conn: Conn, ledger: Ledger, section: str
) -> None:
    for viewer in (ledger.company_viewer, ledger.vehicle_viewer):
        assert _history(app_conn, viewer, section=section)["items"] == []


def test_expenses_rows_are_always_shown_to_a_scoped_viewer(app_conn: Conn, ledger: Ledger) -> None:
    for viewer in (ledger.company_viewer, ledger.vehicle_viewer):
        assert _reasons(_history(app_conn, viewer, section="expenses")) == ["expenses"]


def test_a_scoped_viewers_paging_runs_over_the_visible_rows_only(
    app_conn: Conn, ledger: Ledger
) -> None:
    seen: list[str] = []
    before: int | None = None
    while True:
        page = _history(app_conn, ledger.company_viewer, size=3, before=before)
        seen += _reasons(page)
        if not page["has_more"]:
            break
        before = page["next_before"]
    assert len(seen) == 8
    assert not any(reason.startswith("settings") for reason in seen)


@pytest.fixture
def people(
    app_conn: Conn, owner_conn: Conn, owner: Member, ledger: Ledger
) -> dict[str, dict[str, Any]]:
    hana = create_person(
        app_conn,
        owner,
        first_name="Hana",
        scope_mode="companies",
        company_ids=[ledger.alpha, ledger.beta],
        email="hana@example.com",
        phone="0722000333",
    )
    vic = create_person(
        app_conn,
        owner,
        first_name="Victor",
        scope_mode="vehicles",
        vehicle_ids=[ledger.a1, ledger.b1],
        email="victor@example.com",
        phone="0722000444",
    )
    bea = create_person(
        app_conn,
        owner,
        first_name="Bea",
        scope_mode="companies",
        company_ids=[ledger.beta],
        email="bea@example.com",
        phone="0722000555",
    )
    update_person(
        app_conn,
        owner,
        hana["id"],
        1,
        first_name="Hana",
        last_name="Mwangi",
        scope_mode="companies",
        company_ids=[ledger.alpha, ledger.beta],
        email="hana@example.com",
        phone="0722000333",
    )
    return {"hana": hana, "vic": vic, "bea": bea}


def _people_entries(app: Conn, who: Member) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = _history(app, who, section="people", size=100)["items"]
    return items


def _stored(owner_conn: Conn, org: UUID) -> dict[int, dict[str, Any]]:
    return {row["version"]: row for row in change_log(owner_conn, org)}


def _json_ids(*ids: UUID) -> str:
    return "[" + ",".join(f'"{i}"' for i in sorted(ids, key=str)) + "]"


def test_an_all_companies_viewer_reads_people_snapshots_as_stored(
    app_conn: Conn,
    owner_conn: Conn,
    office: Member,
    people: dict[str, dict[str, Any]],
) -> None:
    stored = _stored(owner_conn, office.org)
    entries = _people_entries(app_conn, office)
    assert len(entries) == 4
    for entry in entries:
        assert entry["before"] == stored[entry["version"]]["before"]
        assert entry["after"] == stored[entry["version"]]["after"]


def test_a_company_scoped_viewer_sees_only_visible_people_with_redacted_snapshots(
    app_conn: Conn,
    owner_conn: Conn,
    ledger: Ledger,
    people: dict[str, dict[str, Any]],
) -> None:
    viewer = ledger.company_viewer
    stored = _stored(owner_conn, viewer.org)
    entries = _people_entries(app_conn, viewer)
    visible = {str(people["hana"]["id"]), str(people["vic"]["id"])}
    assert {e["entity_id"] for e in entries} == visible
    assert len(entries) == 3
    both = _json_ids(ledger.alpha, ledger.beta)
    only_alpha = _json_ids(ledger.alpha)
    vehicles = _json_ids(ledger.a1, ledger.b1)
    only_a1 = _json_ids(ledger.a1)
    for entry in entries:
        raw_after = stored[entry["version"]]["after"]
        assert entry["after"] == raw_after.replace(
            f'"CompanyIds":{both}', f'"CompanyIds":{only_alpha}'
        ).replace(f'"VehicleIds":{vehicles}', f'"VehicleIds":{only_a1}')
        raw_before = stored[entry["version"]]["before"]
        if raw_before == "null":
            assert entry["before"] == "null"
        else:
            assert entry["before"] == raw_before.replace(
                f'"CompanyIds":{both}', f'"CompanyIds":{only_alpha}'
            )


def test_a_vehicle_scoped_viewer_sees_people_with_company_and_vehicle_ids_cut_to_their_reach(
    app_conn: Conn,
    owner_conn: Conn,
    ledger: Ledger,
    people: dict[str, dict[str, Any]],
) -> None:
    viewer = ledger.vehicle_viewer
    stored = _stored(owner_conn, viewer.org)
    entries = _people_entries(app_conn, viewer)
    assert {e["entity_id"] for e in entries} == {
        str(people["hana"]["id"]),
        str(people["vic"]["id"]),
    }
    both = _json_ids(ledger.alpha, ledger.beta)
    vehicles = _json_ids(ledger.a1, ledger.b1)
    for entry in entries:
        raw = stored[entry["version"]]["after"]
        assert entry["after"] == raw.replace(f'"CompanyIds":{both}', '"CompanyIds":[]').replace(
            f'"VehicleIds":{vehicles}', f'"VehicleIds":{_json_ids(ledger.a1)}'
        )


def test_redaction_leaves_every_other_key_and_the_compact_form_alone(
    app_conn: Conn,
    owner_conn: Conn,
    ledger: Ledger,
    people: dict[str, dict[str, Any]],
) -> None:
    viewer = ledger.company_viewer
    # The oldest of Hana's entries: her creation, before the fixture renames her.
    entry = [
        e for e in _people_entries(app_conn, viewer) if e["entity_id"] == str(people["hana"]["id"])
    ][-1]
    after = entry["after"]
    assert after.startswith('{"FirstName":"Hana","LastName":"')
    scope = f'"ScopeMode":"companies","CompanyIds":["{ledger.alpha}"],"VehicleIds":[],'
    assert scope in after
    assert after.endswith(
        '"ApprovalLimit":null,"BackLimitMode":"days","BackLimitCount":7,"BackLimitFrom":null,'
        '"Name":"Hana Njeri"}'
    )
    assert ": " not in after
    assert ", " not in after


def test_a_company_scoped_viewer_does_not_see_people_outside_their_view(
    app_conn: Conn, ledger: Ledger, people: dict[str, dict[str, Any]]
) -> None:
    for viewer in (ledger.company_viewer, ledger.vehicle_viewer):
        ids = {e["entity_id"] for e in _people_entries(app_conn, viewer)}
        assert str(people["bea"]["id"]) not in ids


def test_a_viewer_with_audit_view_but_not_people_view_sees_no_people_rows(
    app_conn: Conn,
    owner_conn: Conn,
    clerk: Member,
    ledger: Ledger,
    people: dict[str, dict[str, Any]],
) -> None:
    set_override(owner_conn, clerk, "audit.view")
    set_scope(owner_conn, clerk, clerk.org, all_companies=True)
    page = _history(app_conn, clerk, size=100)
    assert _history(app_conn, clerk, section="people")["items"] == []
    assert sorted(_reasons(page)) == sorted(EVERYTHING)


def test_a_scoped_viewer_with_audit_view_but_not_people_view_sees_no_people_rows(
    app_conn: Conn,
    owner_conn: Conn,
    clerk: Member,
    ledger: Ledger,
    people: dict[str, dict[str, Any]],
) -> None:
    set_override(owner_conn, clerk, "audit.view")
    set_scope(owner_conn, clerk, clerk.org, companies=[ledger.alpha])
    assert _history(app_conn, clerk, section="people")["items"] == []
    assert "company alpha" in _reasons(_history(app_conn, clerk, size=100))


def test_total_counts_only_what_the_viewer_may_see(
    app_conn: Conn, ledger: Ledger, people: dict[str, dict[str, Any]]
) -> None:
    page = _history(app_conn, ledger.company_viewer, size=1)
    assert page["total"] == 8 + 3
    assert len(page["items"]) == 1
