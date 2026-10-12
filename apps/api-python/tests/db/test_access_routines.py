"""The people and access routines (``api.access_*``, ``api.people_*``), called as ``xcode_app``.

Accounts are provisioned through ``api.ops_provision_user``. Companies, vehicles, data scopes
and permission overrides that no routine writes yet are inserted as ``xcode_owner`` (seeded as
owner: no routine writes companies yet), and every result is read back as ``xcode_owner``.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg.rows import dict_row

from ..support.rows import seed_organization
from ..support.scenario import (
    PIN_HASH,
    T0,
    Conn,
    call,
    device_row,
    live_tokens,
    set_user,
    store_token,
    trust,
    user_row,
)
from ..support.tenancy import (
    CLERK_KEYS,
    REQUEST,
    Member,
    add_company,
    add_vehicle,
    audit_events,
    change_log,
    create_person,
    create_refused,
    membership,
    provision_member,
    refused,
    scope_rows,
    set_organization,
    set_override,
    set_scope,
    settings_version,
    update_person,
    update_refused,
    write,
)

_SUPPORT = Path(__file__).resolve().parent.parent / "support"
_CATALOGUE = json.loads((_SUPPORT / "permission_catalogue.json").read_text(encoding="utf-8"))
_ITEMS = [item for group in _CATALOGUE["groups"] for item in group["items"]]
_ORDER = [item["key"] for item in _ITEMS]
_NEEDS = {item["key"]: item["needs"] for item in _ITEMS}

GROUPS = [
    "Dashboard",
    "Revenue",
    "Central expenses",
    "Petty cash",
    "Scheduled expenses",
    "Savings",
    "Reports",
    "PSV companies",
    "Vehicles",
    "Expense items",
    "People and access",
    "Change log",
]
OFFICE_KEYS = [
    "dash.net",
    "dash.gaps",
    "revenue.view",
    "revenue.correct",
    "revenue.export",
    "expenses.view",
    "expenses.capture",
    "expenses.correct",
    "expenses.export",
    "scheduled.view",
    "scheduled.add",
    "scheduled.edit",
    "scheduled.pause",
    "savings.view",
    "savings.add",
    "savings.edit",
    "savings.pause",
    "reports.view",
    "reports.investment",
    "reports.export",
    "companies.view",
    "companies.add",
    "companies.edit",
    "vehicles.view",
    "vehicles.add",
    "vehicles.edit",
    "vehicles.target",
    "catalog.view",
    "catalog.add",
    "catalog.edit",
    "catalog.stop",
    "people.view",
    "people.add",
    "people.edit",
    "people.block",
    "people.sign_in",
    "audit.view",
]
FLEET_KEYS = [
    "dash.net",
    "dash.gaps",
    "dash.pettycash",
    "revenue.view",
    "revenue.capture",
    "revenue.correct",
    "expenses.view",
    "pettycash.view",
    "pettycash.spend",
    "pettycash.edit_own",
    "reports.view",
]
RETIRED = [item["key"] for item in _CATALOGUE["retired"]]
JANE_AFTER = (
    '{"FirstName":"Jane","LastName":"Njeri","Email":"jane@example.com",'
    '"PhoneNumber":"+254722000111","Role":"Revenue clerk","Active":true,"ScopeMode":"all",'
    '"CompanyIds":[],"VehicleIds":[],"Permissions":["dash.gaps","revenue.capture",'
    '"revenue.view"],"ApprovalLimit":null,"BackLimitMode":"days","BackLimitCount":7,'
    '"BackLimitFrom":null,"Name":"Jane Njeri"}'
)
DEVICE = "device-1"
HOUR = timedelta(hours=1)


def _expand(keys: list[str]) -> list[str]:
    seen: set[str] = set()
    pending = list(keys)
    while pending:
        key = pending.pop()
        if key not in seen:
            seen.add(key)
            pending.extend(_NEEDS[key])
    return [key for key in _ORDER if key in seen]


def _role_defaults(name: str) -> list[str]:
    spec = _CATALOGUE["role_defaults"][name]
    keys = [k for k in _ORDER if k not in spec["all_except"]] if isinstance(spec, dict) else spec
    return _expand(keys)


def _read(app: Conn, routine: str, who: Member, *args: Any) -> Any:
    return call(app, routine, who.id, who.org, REQUEST, *args, T0)


def _sorted_ids(*ids: UUID) -> list[str]:
    return sorted(str(i) for i in ids)


def _uuids(*ids: UUID) -> list[UUID]:
    return [UUID(i) for i in _sorted_ids(*ids)]


def _revoked(owner_conn: Conn, user: UUID, device: str) -> bool:
    row = device_row(owner_conn, user, device)
    assert row is not None
    return bool(row["revoked"])


def _set_active(
    app: Conn,
    actor: Member,
    user: UUID | None,
    active: bool | None,
    version: int | None,
    reason: str | None = None,
) -> dict[str, Any]:
    return write(
        app, "people_set_active", actor.id, actor.org, REQUEST, user, active, version, reason, T0
    )


def _set_active_refused(
    app: Conn,
    actor: Member,
    user: UUID | None,
    active: bool | None,
    version: int | None,
    sqlstate: str,
    code: str,
    reason: str | None = None,
) -> None:
    args = [actor.id, actor.org, REQUEST, user, active, version, reason, T0]
    refused(app, "people_set_active", args, sqlstate, code)


def _sign_out(app: Conn, actor: Member, user: UUID | None) -> dict[str, Any]:
    return write(app, "people_sign_out", actor.id, actor.org, REQUEST, user, T0)


def _sign_out_refused(
    app: Conn, actor: Member, user: UUID | None, sqlstate: str, code: str
) -> None:
    refused(app, "people_sign_out", [actor.id, actor.org, REQUEST, user, T0], sqlstate, code)


def _pin_reset(app: Conn, actor: Member, user: UUID | None) -> dict[str, Any]:
    return write(app, "people_pin_reset", actor.id, actor.org, REQUEST, user, T0)


def _pin_reset_refused(
    app: Conn, actor: Member, user: UUID | None, sqlstate: str, code: str
) -> None:
    refused(app, "people_pin_reset", [actor.id, actor.org, REQUEST, user, T0], sqlstate, code)


def _device_remove(
    app: Conn, actor: Member, user: UUID | None, row_id: UUID | None
) -> dict[str, Any]:
    return write(app, "people_device_remove", actor.id, actor.org, REQUEST, user, row_id, T0)


def _device_remove_refused(
    app: Conn, actor: Member, user: UUID | None, row_id: UUID | None, sqlstate: str, code: str
) -> None:
    args = [actor.id, actor.org, REQUEST, user, row_id, T0]
    refused(app, "people_device_remove", args, sqlstate, code)


def _race(
    app_url: str, first: Callable[[Conn], Any], late: Callable[[Conn], Any]
) -> tuple[Any, Any]:
    """Runs ``late`` on a second connection while ``first`` holds its transaction open."""
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
            # The late call waits on the row lock the first one holds until it commits.
            assert worker.is_alive()
        worker.join(10)
    assert len(results) == 1
    return done, results[0]


@dataclass(frozen=True, slots=True)
class Yard:
    alpha: UUID
    beta: UUID
    a1: UUID
    a2: UUID
    b1: UUID


@pytest.fixture
def owner(operator_conn: Conn) -> Member:
    return provision_member(operator_conn, 1, "Owner", "Olive", "Owner")


@pytest.fixture
def office(operator_conn: Conn, owner: Member) -> Member:
    return provision_member(operator_conn, 2, "Office admin", "Otto", "Office")


@pytest.fixture
def fleet(operator_conn: Conn, owner: Member) -> Member:
    return provision_member(operator_conn, 3, "Fleet manager", "Fiona", "Fleet")


@pytest.fixture
def clerk(operator_conn: Conn, owner: Member) -> Member:
    return provision_member(operator_conn, 4, "Revenue clerk", "Cleo", "Clerk")


@pytest.fixture
def yard(owner_conn: Conn, owner: Member) -> Yard:
    alpha = add_company(owner_conn, owner.org, "Alpha Sacco")
    beta = add_company(owner_conn, owner.org, "Beta Sacco")
    return Yard(
        alpha=alpha,
        beta=beta,
        a1=add_vehicle(owner_conn, owner.org, alpha, "KDA 482M"),
        a2=add_vehicle(owner_conn, owner.org, alpha, "KDB 100A"),
        b1=add_vehicle(owner_conn, owner.org, beta, "KDC 200B"),
    )


@pytest.fixture
def scoped(operator_conn: Conn, owner_conn: Conn, owner: Member, yard: Yard) -> Member:
    """An Office admin who only reaches Alpha Sacco."""
    who = provision_member(operator_conn, 5, "Office admin", "Sam", "Scoped")
    set_scope(owner_conn, who, who.org, companies=[yard.alpha])
    return who


# --- the catalogue and the roles ---


def test_the_catalogue_lists_twelve_modules_in_order(app_conn: Conn, clerk: Member) -> None:
    groups = _read(app_conn, "access_catalog_list", clerk)
    assert [g["name"] for g in groups] == GROUPS


def test_the_catalogue_holds_fifty_nine_rights(app_conn: Conn, clerk: Member) -> None:
    groups = _read(app_conn, "access_catalog_list", clerk)
    assert sum(len(g["items"]) for g in groups) == 59


def test_a_right_needs_the_view_right_of_its_module_or_the_right_it_builds_on(
    app_conn: Conn, clerk: Member
) -> None:
    groups = _read(app_conn, "access_catalog_list", clerk)
    items = {i["key"]: i for g in groups for i in g["items"]}
    assert items["dash.net"]["needs"] == ["revenue.view"]
    assert items["pettycash.approve_day"]["needs"] == ["pettycash.approve_item"]
    assert items["pettycash.issue_negative"]["needs"] == ["pettycash.issue"]
    assert items["revenue.view"]["needs"] == []


def test_the_petty_cash_rights_carry_their_card_section(app_conn: Conn, clerk: Member) -> None:
    groups = _read(app_conn, "access_catalog_list", clerk)
    sections = {i["key"]: i["section"] for g in groups for i in g["items"]}
    assert sections["pettycash.view"] == "View"
    assert sections["pettycash.spend"] == "Expenses"
    assert sections["pettycash.send_back"] == "Approval"
    assert sections["pettycash.issue"] == "Cash"
    assert sections["revenue.view"] is None


def test_the_catalogue_matches_the_inventory_table(app_conn: Conn, clerk: Member) -> None:
    groups = _read(app_conn, "access_catalog_list", clerk)
    assert groups == [
        {
            "name": group["name"],
            "items": [
                {key: value for key, value in item.items() if key != "prototype"}
                for item in group["items"]
            ],
        }
        for group in _CATALOGUE["groups"]
    ]


def test_the_catalogue_leaves_out_the_retired_and_the_hidden_keys(
    app_conn: Conn, clerk: Member
) -> None:
    groups = _read(app_conn, "access_catalog_list", clerk)
    keys = {i["key"] for g in groups for i in g["items"]}
    assert not keys & {*RETIRED, "organization.manage"}


def test_a_revenue_clerk_may_read_the_catalogue(app_conn: Conn, clerk: Member) -> None:
    assert _read(app_conn, "access_catalog_list", clerk)


def test_the_catalogue_refuses_someone_outside_the_organization(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    other = seed_organization(owner_conn)
    refused(
        app_conn, "access_catalog_list", [other.user, owner.org, REQUEST, T0], "XC403", "not_member"
    )


def test_the_roles_are_listed_by_name(app_conn: Conn, office: Member) -> None:
    roles = _read(app_conn, "access_role_list", office)
    assert [r["name"] for r in roles] == [
        "Fleet manager",
        "Office admin",
        "Owner",
        "Revenue clerk",
    ]
    assert all(UUID(r["id"]) for r in roles)


def test_the_revenue_clerk_role_has_exactly_its_three_defaults(
    app_conn: Conn, office: Member
) -> None:
    roles = {r["name"]: r for r in _read(app_conn, "access_role_list", office)}
    assert roles["Revenue clerk"]["permissions"] == ["dash.gaps", "revenue.view", "revenue.capture"]


def test_no_role_offers_a_key_outside_the_catalogue(app_conn: Conn, office: Member) -> None:
    for role in _read(app_conn, "access_role_list", office):
        assert set(role["permissions"]) <= set(_ORDER), role["name"]


def test_the_owner_role_offers_every_right_but_not_the_hidden_key(
    app_conn: Conn, office: Member
) -> None:
    roles = {r["name"]: r for r in _read(app_conn, "access_role_list", office)}
    assert roles["Owner"]["permissions"] == _ORDER
    assert len(roles["Owner"]["permissions"]) == 59


@pytest.mark.parametrize("name", ["Owner", "Office admin", "Fleet manager", "Revenue clerk"])
def test_each_role_matches_the_inventory_defaults_in_catalogue_order(
    app_conn: Conn, office: Member, name: str
) -> None:
    roles = {r["name"]: r for r in _read(app_conn, "access_role_list", office)}
    assert roles[name]["permissions"] == _role_defaults(name)


def test_a_clerk_may_not_list_the_roles(app_conn: Conn, clerk: Member) -> None:
    args = [clerk.id, clerk.org, REQUEST, T0]
    refused(app_conn, "access_role_list", args, "XC403", "permission_missing")


# --- scope options and the actor's own scope ----------------------------------------------


@dataclass(frozen=True, slots=True)
class Estate:
    zulu: UUID
    alpha: UUID
    closed: UUID
    closing: UUID
    kbz: UUID
    kcc: UUID
    kcd: UUID
    kce: UUID
    kcf: UUID
    kcg: UUID
    kda: UUID


@pytest.fixture
def estate(owner_conn: Conn, owner: Member) -> Estate:
    org = owner.org
    zulu = add_company(owner_conn, org, "Zulu Sacco")
    alpha = add_company(owner_conn, org, "Alpha Sacco")
    closed = add_company(owner_conn, org, "Closed Sacco", archived_on=date(2026, 10, 9))
    closing = add_company(owner_conn, org, "Closing Sacco", archived_on=date(2026, 10, 10))
    return Estate(
        zulu=zulu,
        alpha=alpha,
        closed=closed,
        closing=closing,
        kbz=add_vehicle(owner_conn, org, zulu, "KBZ 100A"),
        kcc=add_vehicle(owner_conn, org, alpha, "KCC 300C", left_on=date(2026, 10, 9)),
        kcd=add_vehicle(owner_conn, org, alpha, "KCD 400D", left_on=date(2026, 10, 10)),
        kce=add_vehicle(owner_conn, org, alpha, "KCE 500E", joined_on=date(2026, 10, 10)),
        kcf=add_vehicle(owner_conn, org, closed, "KCF 600F"),
        kcg=add_vehicle(owner_conn, org, closing, "KCG 700G"),
        kda=add_vehicle(owner_conn, org, alpha, "KDA 482M", fleet_number="A-17"),
    )


def test_scope_options_exclude_archived_companies_and_order_them_by_name(
    app_conn: Conn, owner: Member, estate: Estate
) -> None:
    options = _read(app_conn, "access_scope_options", owner)
    assert [c["name"] for c in options["companies"]] == [
        "Alpha Sacco",
        "Closing Sacco",
        "Zulu Sacco",
    ]
    assert options["companies"][0] == {"id": str(estate.alpha), "name": "Alpha Sacco"}


def test_scope_options_exclude_vehicles_that_left_or_wait_to_join_or_have_an_archived_company(
    app_conn: Conn, owner: Member, estate: Estate
) -> None:
    options = _read(app_conn, "access_scope_options", owner)
    assert [v["registration"] for v in options["vehicles"]] == [
        "KBZ 100A",
        "KCD 400D",
        "KCG 700G",
        "KDA 482M",
    ]
    assert options["vehicles"][3] == {
        "id": str(estate.kda),
        "registration": "KDA 482M",
        "fleet_number": "A-17",
        "company_id": str(estate.alpha),
    }


def test_scope_options_follow_the_held_business_date(
    app_conn: Conn, owner_conn: Conn, owner: Member, estate: Estate
) -> None:
    set_organization(owner_conn, owner.org, business_date=date(2026, 9, 1))
    options = _read(app_conn, "access_scope_options", owner)
    assert [c["name"] for c in options["companies"]] == [
        "Alpha Sacco",
        "Closed Sacco",
        "Closing Sacco",
        "Zulu Sacco",
    ]
    assert [v["registration"] for v in options["vehicles"]] == [
        "KBZ 100A",
        "KCC 300C",
        "KCD 400D",
        "KCF 600F",
        "KCG 700G",
        "KDA 482M",
    ]


def test_scope_options_of_a_company_scoped_actor_cover_only_their_companies(
    app_conn: Conn, owner_conn: Conn, office: Member, estate: Estate
) -> None:
    set_scope(owner_conn, office, office.org, companies=[estate.alpha])
    options = _read(app_conn, "access_scope_options", office)
    assert [c["name"] for c in options["companies"]] == ["Alpha Sacco"]
    assert [v["registration"] for v in options["vehicles"]] == ["KCD 400D", "KDA 482M"]


def test_scope_options_of_a_vehicle_scoped_actor_list_their_vehicles_only(
    app_conn: Conn, owner_conn: Conn, office: Member, estate: Estate
) -> None:
    set_scope(owner_conn, office, office.org, vehicles=[estate.kda, estate.kbz, estate.kcf])
    options = _read(app_conn, "access_scope_options", office)
    assert options["companies"] == []
    assert [v["registration"] for v in options["vehicles"]] == ["KBZ 100A", "KDA 482M"]


def test_scope_options_need_adding_or_editing_people(app_conn: Conn, fleet: Member) -> None:
    args = [fleet.id, fleet.org, REQUEST, T0]
    refused(app_conn, "access_scope_options", args, "XC403", "permission_missing")


@pytest.mark.parametrize("right", ["people.add", "people.edit"])
def test_scope_options_open_to_either_right_alone(
    app_conn: Conn, owner_conn: Conn, clerk: Member, right: str
) -> None:
    set_override(owner_conn, clerk, right)
    options = _read(app_conn, "access_scope_options", clerk)
    assert options == {"companies": [], "vehicles": []}


def test_my_scope_of_an_all_companies_member_lists_everything_including_retired_vehicles(
    app_conn: Conn, owner: Member, estate: Estate
) -> None:
    mine = _read(app_conn, "access_my_scope", owner)
    assert mine["all_companies"] is True
    assert [c["name"] for c in mine["companies"]] == [
        "Alpha Sacco",
        "Closed Sacco",
        "Closing Sacco",
        "Zulu Sacco",
    ]
    assert [v["registration"] for v in mine["vehicles"]] == [
        "KBZ 100A",
        "KCC 300C",
        "KCD 400D",
        "KCE 500E",
        "KCF 600F",
        "KCG 700G",
        "KDA 482M",
    ]


def test_my_scope_of_a_vehicle_scoped_member_is_their_vehicle_and_its_company(
    app_conn: Conn, owner_conn: Conn, clerk: Member, estate: Estate
) -> None:
    set_scope(owner_conn, clerk, clerk.org, vehicles=[estate.kda])
    mine = _read(app_conn, "access_my_scope", clerk)
    assert mine["all_companies"] is False
    assert mine["companies"] == [{"id": str(estate.alpha), "name": "Alpha Sacco"}]
    assert mine["vehicles"] == [
        {
            "id": str(estate.kda),
            "registration": "KDA 482M",
            "fleet_number": "A-17",
            "company_id": str(estate.alpha),
        }
    ]


def test_my_scope_of_a_company_scoped_member_includes_retired_vehicles_of_the_company(
    app_conn: Conn, owner_conn: Conn, fleet: Member, estate: Estate
) -> None:
    set_scope(owner_conn, fleet, fleet.org, companies=[estate.alpha])
    mine = _read(app_conn, "access_my_scope", fleet)
    assert [c["name"] for c in mine["companies"]] == ["Alpha Sacco"]
    assert [v["registration"] for v in mine["vehicles"]] == [
        "KCC 300C",
        "KCD 400D",
        "KCE 500E",
        "KDA 482M",
    ]


def test_my_scope_of_a_member_without_scope_rows_is_empty(
    app_conn: Conn, clerk: Member, estate: Estate
) -> None:
    mine = _read(app_conn, "access_my_scope", clerk)
    assert mine == {
        "all_companies": False,
        "companies": [],
        "vehicles": [],
        "can_change": "Any date",
        "earliest": None,
    }


# --- the sixteen steps ---


class Attempt:
    """One person save, as create or as update of an existing person (same base fields)."""

    def __init__(self, conn: Conn, actor: Member, target: dict[str, Any] | None) -> None:
        self.conn = conn
        self.actor = actor
        self.target = target

    def refused(self, sqlstate: str, code: str, **fields: Any) -> None:
        if self.target is None:
            create_refused(self.conn, self.actor, sqlstate, code, **fields)
        else:
            update_refused(
                self.conn,
                self.actor,
                self.target["id"],
                self.target["version"],
                sqlstate,
                code,
                **fields,
            )

    def accepted(self, **fields: Any) -> dict[str, Any]:
        if self.target is None:
            return create_person(self.conn, self.actor, **fields)
        return update_person(
            self.conn, self.actor, self.target["id"], self.target["version"], **fields
        )


@pytest.fixture(params=["create", "update"])
def attempt(request: pytest.FixtureRequest, app_conn: Conn, owner: Member) -> Attempt:
    if request.param == "update":
        return Attempt(app_conn, owner, create_person(app_conn, owner))
    return Attempt(app_conn, owner, None)


@pytest.mark.parametrize(
    "fields",
    [
        {"first_name": ""},
        {"first_name": "   "},
        {"first_name": None},
        {"last_name": ""},
        {"last_name": None},
        {"first_name": "x" * 101},
        {"last_name": "y" * 101},
    ],
)
def test_step_1_names_are_required(attempt: Attempt, fields: dict[str, Any]) -> None:
    attempt.refused("XC422", "people_names_required", **fields)


def test_step_1_names_of_one_hundred_characters_are_accepted(attempt: Attempt) -> None:
    row = attempt.accepted(first_name="x" * 100, last_name=" " + "y" * 100 + " ")
    assert row["outcome"] in ("created", "updated")


@pytest.mark.parametrize(
    "email", ["", None, "no-at-sign", "two@@signs.com", "has space@example.com", "a@" + "b" * 320]
)
def test_step_2_email_must_be_valid(attempt: Attempt, email: str | None) -> None:
    attempt.refused("XC422", "people_email_invalid", email=email)


@pytest.mark.parametrize(
    "phone", ["", None, "12345", "0522000111", "+1 555 123 4567", "07220001", "0722 000"]
)
def test_step_3_phone_must_be_a_kenyan_mobile_number(attempt: Attempt, phone: str | None) -> None:
    attempt.refused("XC422", "people_phone_invalid", phone=phone)


@pytest.mark.parametrize("mode", [None, "", "everything", "ALL", "company"])
def test_step_4_scope_mode_must_be_known(attempt: Attempt, mode: str | None) -> None:
    attempt.refused("XC422", "people_scope_mode", scope_mode=mode)


@pytest.mark.parametrize(
    "fields",
    [
        {"scope_mode": "companies", "company_ids": []},
        {"scope_mode": "companies", "company_ids": None},
        {"scope_mode": "vehicles", "vehicle_ids": []},
        {"scope_mode": "vehicles", "vehicle_ids": None},
        {"scope_mode": "companies", "company_ids": [], "vehicle_ids": [uuid4()]},
        {"scope_mode": "vehicles", "vehicle_ids": [], "company_ids": [uuid4()]},
    ],
)
def test_step_5_a_company_or_vehicle_scope_needs_an_item(
    attempt: Attempt, fields: dict[str, Any]
) -> None:
    attempt.refused("XC422", "people_scope_empty", **fields)


def test_step_5_an_all_companies_scope_ignores_the_id_lists(
    attempt: Attempt, owner_conn: Conn, owner: Member
) -> None:
    row = attempt.accepted(scope_mode="all", company_ids=[uuid4()], vehicle_ids=[uuid4()])
    assert scope_rows(owner_conn, owner.org, row["id"]) == {
        "all_companies": True,
        "companies": [],
        "vehicles": [],
    }


def test_step_6_scope_items_must_be_distinct(attempt: Attempt) -> None:
    same = uuid4()
    attempt.refused(
        "XC422", "people_scope_duplicate", scope_mode="companies", company_ids=[same, same]
    )
    attempt.refused(
        "XC422", "people_scope_duplicate", scope_mode="vehicles", vehicle_ids=[same, same]
    )


def test_step_6_duplicates_in_the_unused_list_are_ignored(attempt: Attempt, yard: Yard) -> None:
    same = uuid4()
    row = attempt.accepted(
        scope_mode="companies", company_ids=[yard.alpha], vehicle_ids=[same, same]
    )
    assert row["outcome"] in ("created", "updated")


@pytest.mark.parametrize(
    "fields",
    [
        {"permissions": []},
        {"permissions": None},
        {"permissions": ["revenue.view", "revenue.view"]},
        {"permissions": ["revenue.view", None]},
        {"approval_limit": Decimal(-1)},
        {"approval_limit": Decimal("1000000000000.00")},
        {"approval_limit": Decimal("1.005")},
    ],
)
def test_step_7_permissions_and_the_approval_limit_must_be_valid(
    attempt: Attempt, fields: dict[str, Any]
) -> None:
    attempt.refused("XC422", "people_permissions_invalid", **fields)


@pytest.mark.parametrize("limit", [Decimal(0), Decimal("0.01"), Decimal("999999999999.99")])
def test_step_7_approval_limits_inside_the_bounds_are_accepted(
    attempt: Attempt, limit: Decimal
) -> None:
    assert attempt.accepted(approval_limit=limit)["outcome"] in ("created", "updated")


@pytest.mark.parametrize("role", [None, "", "Admin", "Owners", "Fleet  manager"])
def test_step_8_the_role_must_be_one_of_the_four(attempt: Attempt, role: str | None) -> None:
    attempt.refused("XC422", "people_role_unknown", role=role)


def test_step_8_the_role_matches_ignoring_case(
    attempt: Attempt, app_conn: Conn, owner: Member
) -> None:
    row = attempt.accepted(role="revenue CLERK")
    document = _read(app_conn, "people_get", owner, row["id"])
    assert document["role"] == "Revenue clerk"


@pytest.mark.parametrize(
    ("fields", "code"),
    [
        ({"first_name": "", "role": "Nobody"}, "people_names_required"),
        ({"email": "bad", "phone": "bad"}, "people_email_invalid"),
        ({"phone": "bad", "scope_mode": "nope"}, "people_phone_invalid"),
        ({"scope_mode": "nope", "permissions": []}, "people_scope_mode"),
        ({"scope_mode": "companies", "company_ids": [], "permissions": []}, "people_scope_empty"),
        ({"permissions": [], "role": "Nobody"}, "people_permissions_invalid"),
        (
            {"role": "Nobody", "scope_mode": "companies", "company_ids": [uuid4()]},
            "people_role_unknown",
        ),
    ],
)
def test_the_first_failing_step_decides_the_refusal(
    attempt: Attempt, fields: dict[str, Any], code: str
) -> None:
    attempt.refused("XC422", code, **fields)


def test_the_duplicate_step_comes_before_the_permission_step(attempt: Attempt) -> None:
    same = uuid4()
    attempt.refused(
        "XC422",
        "people_scope_duplicate",
        scope_mode="companies",
        company_ids=[same, same],
        permissions=[],
    )


def test_step_9_an_unknown_person_is_not_found(app_conn: Conn, owner: Member) -> None:
    update_refused(app_conn, owner, uuid4(), 1, "XC404", "not_found")


def test_step_9_a_missing_person_id_is_not_found(app_conn: Conn, owner: Member) -> None:
    update_refused(app_conn, owner, None, 1, "XC404", "not_found")


def test_step_9_a_person_outside_the_editors_view_is_not_found(
    app_conn: Conn, owner: Member, scoped: Member, yard: Yard
) -> None:
    hidden = create_person(
        app_conn,
        owner,
        scope_mode="companies",
        company_ids=[yard.beta],
        email="beta@example.com",
        phone="0722000222",
    )
    update_refused(app_conn, scoped, hidden["id"], hidden["version"], "XC404", "not_found")


def test_step_9_a_member_of_another_organization_is_not_found(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    other = seed_organization(owner_conn)
    update_refused(app_conn, owner, other.user2, 1, "XC404", "not_found")


def test_step_9_the_version_is_required(app_conn: Conn, owner: Member) -> None:
    jane = create_person(app_conn, owner)
    update_refused(app_conn, owner, jane["id"], None, "XC422", "people_version_required")


def test_step_9_a_stale_version_conflicts(app_conn: Conn, owner: Member) -> None:
    jane = create_person(app_conn, owner)
    update_person(app_conn, owner, jane["id"], 1, last_name="Wanjiru")
    update_refused(app_conn, owner, jane["id"], 1, "XC409", "version_conflict", last_name="Mwangi")


def test_step_9_a_save_racing_another_waits_for_it_then_conflicts(
    app_conn: Conn, app_url: str, owner_conn: Conn, owner: Member
) -> None:
    jane = create_person(app_conn, owner)
    logged = len(change_log(owner_conn, owner.org))
    first, late = _race(
        app_url,
        lambda one: update_person(one, owner, jane["id"], 1, last_name="Wanjiru"),
        lambda two: update_person(two, owner, jane["id"], 1, last_name="Mwangi"),
    )
    assert first["version"] == 2
    assert late == ("XC409", "version_conflict")
    row = membership(owner_conn, owner.org, jane["id"])
    assert (row["last_name"], row["version"]) == ("Wanjiru", 2)
    assert len(change_log(owner_conn, owner.org)) == logged + 1


def test_step_9_a_version_from_the_future_conflicts(app_conn: Conn, owner: Member) -> None:
    jane = create_person(app_conn, owner)
    update_refused(app_conn, owner, jane["id"], 9, "XC409", "version_conflict")


def test_step_9_the_version_check_comes_before_the_grant_rules(
    app_conn: Conn, owner: Member
) -> None:
    jane = create_person(app_conn, owner)
    unknown = {"scope_mode": "companies", "company_ids": [uuid4()]}
    update_refused(app_conn, owner, jane["id"], None, "XC422", "people_version_required", **unknown)
    update_refused(app_conn, owner, jane["id"], 7, "XC409", "version_conflict", **unknown)


def test_step_10_only_an_all_companies_editor_gives_all_companies(
    app_conn: Conn, scoped: Member
) -> None:
    create_refused(app_conn, scoped, "XC403", "people_all_companies_needs_all", scope_mode="all")


def test_step_10_chosen_companies_must_exist(app_conn: Conn, owner: Member) -> None:
    create_refused(
        app_conn,
        owner,
        "XC422",
        "people_companies_unknown",
        scope_mode="companies",
        company_ids=[uuid4()],
    )


def test_step_10_a_company_of_another_organization_is_unknown(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    other = seed_organization(owner_conn)
    create_refused(
        app_conn,
        owner,
        "XC422",
        "people_companies_unknown",
        scope_mode="companies",
        company_ids=[other.company],
    )


def test_step_10_chosen_vehicles_must_exist(app_conn: Conn, owner: Member) -> None:
    create_refused(
        app_conn,
        owner,
        "XC422",
        "people_vehicles_unknown",
        scope_mode="vehicles",
        vehicle_ids=[uuid4()],
    )


def test_step_10_companies_outside_the_editors_scope_are_refused(
    app_conn: Conn, scoped: Member, yard: Yard
) -> None:
    create_refused(
        app_conn,
        scoped,
        "XC403",
        "people_companies_outside_scope",
        scope_mode="companies",
        company_ids=[yard.alpha, yard.beta],
    )


def test_step_10_vehicles_outside_the_editors_scope_are_refused(
    app_conn: Conn, scoped: Member, yard: Yard
) -> None:
    create_refused(
        app_conn,
        scoped,
        "XC403",
        "people_vehicles_outside_scope",
        scope_mode="vehicles",
        vehicle_ids=[yard.b1],
    )


def test_step_10_vehicles_of_the_editors_companies_are_within_scope(
    app_conn: Conn, owner_conn: Conn, scoped: Member, yard: Yard
) -> None:
    row = create_person(
        app_conn,
        scoped,
        role="Office admin",
        permissions=OFFICE_KEYS,
        scope_mode="vehicles",
        vehicle_ids=[yard.a1, yard.a2],
    )
    assert scope_rows(owner_conn, scoped.org, row["id"])["vehicles"] == _uuids(yard.a1, yard.a2)


def test_step_10_a_scoped_editor_cannot_switch_the_kind_of_scope_of_a_person_with_hidden_scope(
    app_conn: Conn, owner: Member, scoped: Member, yard: Yard
) -> None:
    hana = create_person(
        app_conn,
        owner,
        scope_mode="companies",
        company_ids=[yard.alpha, yard.beta],
        email="hana@example.com",
        phone="0722000333",
    )
    update_refused(
        app_conn,
        scoped,
        hana["id"],
        hana["version"],
        "XC403",
        "people_hidden_scope_kind",
        email="hana@example.com",
        phone="0722000333",
        scope_mode="vehicles",
        vehicle_ids=[yard.a1],
    )


def test_step_11_an_editor_cannot_change_themselves(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    version = membership(owner_conn, owner.org, owner.id)["version"]
    update_refused(
        app_conn,
        owner,
        owner.id,
        version,
        "XC422",
        "people_self_edit",
        email=owner.email,
        phone=owner.phone,
        role="Owner",
    )


def test_step_11_comes_after_the_scope_rules(app_conn: Conn, office: Member) -> None:
    update_refused(
        app_conn,
        office,
        office.id,
        1,
        "XC422",
        "people_companies_unknown",
        scope_mode="companies",
        company_ids=[uuid4()],
        role="Office admin",
    )


def test_step_12_only_an_owner_gives_the_owner_role(app_conn: Conn, office: Member) -> None:
    create_refused(app_conn, office, "XC403", "people_owner_grant", role="Owner")


def test_step_12_promoting_someone_to_owner_is_an_owner_grant_too(
    app_conn: Conn, owner: Member, office: Member
) -> None:
    jane = create_person(app_conn, owner)
    update_refused(
        app_conn, office, jane["id"], jane["version"], "XC403", "people_owner_grant", role="Owner"
    )


def test_step_12_only_an_owner_changes_an_owner(
    app_conn: Conn, owner: Member, office: Member
) -> None:
    update_refused(
        app_conn,
        office,
        owner.id,
        1,
        "XC403",
        "people_owner_edit",
        email=owner.email,
        phone=owner.phone,
        role="Owner",
    )


def test_step_12_comes_after_the_self_edit_rule(app_conn: Conn, office: Member) -> None:
    update_refused(app_conn, office, office.id, 1, "XC422", "people_self_edit", role="Owner")


def test_step_13_permission_keys_must_exist(app_conn: Conn, owner: Member) -> None:
    create_refused(
        app_conn,
        owner,
        "XC422",
        "people_permission_unknown",
        permissions=["revenue.view", "no.such_key"],
    )


@pytest.mark.parametrize(
    "key", ["dash.capture", "revenue.no_earnings", "vehicles.manage", "access.manage", "bills.view"]
)
def test_a_legacy_key_cannot_be_granted(app_conn: Conn, owner: Member, key: str) -> None:
    create_refused(
        app_conn, owner, "XC422", "people_permission_unknown", permissions=[*CLERK_KEYS, key]
    )
    jane = create_person(app_conn, owner)
    update_refused(
        app_conn,
        owner,
        jane["id"],
        1,
        "XC422",
        "people_permission_unknown",
        permissions=[*CLERK_KEYS, key],
    )


def test_the_hidden_organization_key_cannot_be_granted_even_by_an_owner(
    app_conn: Conn, owner: Member
) -> None:
    create_refused(
        app_conn,
        owner,
        "XC422",
        "people_permission_unknown",
        role="Office admin",
        permissions=[*OFFICE_KEYS, "organization.manage"],
    )


def test_step_13_comes_after_the_owner_rules(app_conn: Conn, office: Member) -> None:
    create_refused(
        app_conn, office, "XC403", "people_owner_grant", role="Owner", permissions=["no.such_key"]
    )


def test_step_14_a_role_needs_every_default_permission_the_editor_holds(
    app_conn: Conn, office: Member
) -> None:
    create_refused(app_conn, office, "XC403", "people_role_not_held")


def test_step_14_single_permissions_need_people_edit(
    app_conn: Conn, owner_conn: Conn, clerk: Member
) -> None:
    set_override(owner_conn, clerk, "people.add")
    set_scope(owner_conn, clerk, clerk.org, all_companies=True)
    create_refused(
        app_conn,
        clerk,
        "XC403",
        "people_access_manage_needed",
        permissions=[*CLERK_KEYS, "people.view"],
    )
    assert create_person(app_conn, clerk)["outcome"] == "created"


def test_step_14_an_approval_limit_needs_people_edit(
    app_conn: Conn, owner_conn: Conn, clerk: Member
) -> None:
    set_override(owner_conn, clerk, "people.add")
    set_scope(owner_conn, clerk, clerk.org, all_companies=True)
    create_refused(
        app_conn, clerk, "XC403", "people_access_manage_needed", approval_limit=Decimal(5000)
    )


def test_step_14_only_permissions_the_editor_holds_may_be_granted(
    app_conn: Conn, office: Member
) -> None:
    create_refused(
        app_conn,
        office,
        "XC403",
        "people_permission_not_held",
        role="Office admin",
        permissions=[*OFFICE_KEYS, "pettycash.view_all"],
    )


def test_step_14_comes_after_the_unknown_permission_rule(app_conn: Conn, office: Member) -> None:
    create_refused(
        app_conn, office, "XC422", "people_permission_unknown", permissions=["no.such_key"]
    )


def test_step_15_a_scoped_editor_needs_the_whole_scope_to_change_sign_in_details(
    app_conn: Conn, owner: Member, scoped: Member, yard: Yard
) -> None:
    hana = create_person(
        app_conn,
        owner,
        scope_mode="companies",
        company_ids=[yard.alpha, yard.beta],
        email="hana@example.com",
        phone="0722000333",
    )
    update_refused(
        app_conn,
        scoped,
        hana["id"],
        hana["version"],
        "XC403",
        "people_sign_in_scope",
        email="hana.new@example.com",
        phone="0722000333",
        scope_mode="companies",
        company_ids=[yard.alpha],
    )


def test_step_15_a_person_who_also_holds_every_company_is_beyond_a_scoped_editor(
    app_conn: Conn, owner_conn: Conn, owner: Member, scoped: Member, yard: Yard
) -> None:
    gus = create_person(app_conn, owner, email="gus@example.com", phone="0722000444")
    set_scope(owner_conn, gus["id"], owner.org, all_companies=True, companies=[yard.alpha])
    update_refused(
        app_conn,
        scoped,
        gus["id"],
        gus["version"],
        "XC403",
        "people_sign_in_scope",
        email="gus.new@example.com",
        phone="0722000444",
        scope_mode="companies",
        company_ids=[yard.alpha],
    )


def test_step_15_the_editor_must_hold_everything_the_person_holds(
    app_conn: Conn, owner: Member, office: Member
) -> None:
    fiona = create_person(
        app_conn,
        owner,
        role="Fleet manager",
        permissions=FLEET_KEYS,
        email="fiona@example.com",
        phone="0722000555",
    )
    update_refused(
        app_conn,
        office,
        fiona["id"],
        fiona["version"],
        "XC403",
        "people_sign_in_holdings",
        role="Fleet manager",
        permissions=FLEET_KEYS,
        email="fiona.new@example.com",
        phone="0722000555",
    )


def test_step_15_an_editor_with_people_edit_changes_the_sign_in_details_of_a_limited_person(
    app_conn: Conn, owner: Member, office: Member
) -> None:
    ola = create_person(
        app_conn,
        owner,
        role="Office admin",
        permissions=OFFICE_KEYS,
        approval_limit=Decimal(1000),
        email="ola@example.com",
        phone="0722000666",
    )
    row = update_person(
        app_conn,
        office,
        ola["id"],
        ola["version"],
        role="Office admin",
        permissions=OFFICE_KEYS,
        approval_limit=Decimal(1000),
        email="ola.new@example.com",
        phone="0722000666",
    )
    assert row["outcome"] == "updated"


def test_step_15_an_editor_holding_everything_may_change_sign_in_details(
    app_conn: Conn, owner: Member, office: Member
) -> None:
    ola = create_person(
        app_conn,
        owner,
        role="Office admin",
        permissions=OFFICE_KEYS,
        email="ola@example.com",
        phone="0722000666",
    )
    row = update_person(
        app_conn,
        office,
        ola["id"],
        ola["version"],
        role="Office admin",
        permissions=OFFICE_KEYS,
        email="ola.new@example.com",
        phone="0722000666",
    )
    assert row["outcome"] == "updated"


def test_step_15_an_owner_changes_anyones_sign_in_details(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    jane = create_person(app_conn, owner)
    update_person(app_conn, owner, jane["id"], 1, email="new@example.com", phone="0722000999")
    stored = user_row(owner_conn, jane["id"])
    assert (stored["email"], stored["phone_number"]) == ("new@example.com", "+254722000999")


@pytest.mark.parametrize(
    "fields",
    [
        {"email": "olive.owner@example.com"},
        {"email": " OLIVE.Owner@Example.com "},
        {"phone": "0711000001"},
        {"phone": "+254 711 000 001"},
    ],
)
def test_step_16_a_create_cannot_reuse_someone_elses_email_or_number(
    app_conn: Conn, owner: Member, fields: dict[str, Any]
) -> None:
    create_refused(app_conn, owner, "XC422", "people_contact_taken", **fields)


@pytest.mark.parametrize("fields", [{"email": "olive.owner@example.com"}, {"phone": "0711000001"}])
def test_step_16_an_update_cannot_take_someone_elses_email_or_number(
    app_conn: Conn, owner: Member, fields: dict[str, Any]
) -> None:
    jane = create_person(app_conn, owner)
    update_refused(app_conn, owner, jane["id"], 1, "XC422", "people_contact_taken", **fields)


def test_step_16_a_person_keeps_their_own_email_and_number(app_conn: Conn, owner: Member) -> None:
    jane = create_person(app_conn, owner)
    row = update_person(app_conn, owner, jane["id"], 1, last_name="Mwangi")
    assert row["outcome"] == "updated"


def test_step_16_comes_after_the_access_rules(app_conn: Conn, office: Member) -> None:
    create_refused(
        app_conn, office, "XC403", "people_role_not_held", email="olive.owner@example.com"
    )


def test_an_email_is_stored_trimmed_and_lower_case_and_a_number_with_the_country_code(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    row = create_person(app_conn, owner, email="  Jane.NJERI@Example.com ", phone="722 000 111")
    stored = user_row(owner_conn, row["id"])
    assert (stored["email"], stored["phone_number"]) == (
        "jane.njeri@example.com",
        "+254722000111",
    )


# --- allowed escalations ---


def test_an_office_admin_creates_an_office_admin_with_its_defaults(
    app_conn: Conn, owner_conn: Conn, office: Member
) -> None:
    row = create_person(
        app_conn,
        office,
        role="Office admin",
        permissions=OFFICE_KEYS,
        email="ola@example.com",
        phone="0722000666",
    )
    assert row["outcome"] == "created"
    document = _read(app_conn, "people_get", office, row["id"])
    assert document["role"] == "Office admin"
    assert document["permissions"] == _role_defaults("Office admin")
    overrides = owner_conn.execute("SELECT count(*) AS n FROM tenancy.permission_overrides")
    assert overrides.fetchone() == {"n": 0}


def test_an_owner_adds_single_permissions_and_an_approval_limit(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    row = create_person(
        app_conn,
        owner,
        permissions=[*CLERK_KEYS, "reports.view"],
        approval_limit=Decimal("5000.00"),
    )
    document = _read(app_conn, "people_get", owner, row["id"])
    assert document["permissions"] == _expand([*CLERK_KEYS, "reports.view"])
    assert Decimal(str(document["approval_limit"])) == Decimal(5000)
    overrides = owner_conn.execute(
        "SELECT permission, granted FROM tenancy.permission_overrides WHERE user_id = %s",
        (row["id"],),
    ).fetchall()
    assert overrides == [{"permission": "reports.view", "granted": True}]


def test_removing_a_default_permission_stores_denied_overrides(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    row = create_person(app_conn, owner, permissions=["dash.gaps"])
    document = _read(app_conn, "people_get", owner, row["id"])
    assert document["permissions"] == ["dash.gaps", "revenue.view"]
    overrides = owner_conn.execute(
        "SELECT permission, granted FROM tenancy.permission_overrides WHERE user_id = %s "
        "ORDER BY permission",
        (row["id"],),
    ).fetchall()
    assert overrides == [{"permission": "revenue.capture", "granted": False}]


def test_an_office_admin_given_the_missing_rights_creates_a_fleet_manager(
    app_conn: Conn, owner_conn: Conn, office: Member
) -> None:
    fiona = {
        "role": "Fleet manager",
        "permissions": FLEET_KEYS,
        "email": "fiona@example.com",
        "phone": "0722000555",
    }
    create_refused(app_conn, office, "XC403", "people_role_not_held", **fiona)
    for key in ("dash.pettycash", "revenue.capture", "pettycash.spend", "pettycash.edit_own"):
        set_override(owner_conn, office, key)
    assert create_person(app_conn, office, **fiona)["outcome"] == "created"


# --- hidden scope ---


def test_a_company_scoped_editor_keeps_a_company_outside_their_view(
    app_conn: Conn, owner_conn: Conn, owner: Member, scoped: Member, yard: Yard
) -> None:
    hana = create_person(
        app_conn,
        owner,
        scope_mode="companies",
        company_ids=[yard.alpha, yard.beta],
        email="hana@example.com",
        phone="0722000333",
    )
    row = update_person(
        app_conn,
        scoped,
        hana["id"],
        hana["version"],
        last_name="Mwangi",
        scope_mode="companies",
        company_ids=[yard.alpha],
        email="hana@example.com",
        phone="0722000333",
    )
    assert row["outcome"] == "updated"
    assert scope_rows(owner_conn, owner.org, hana["id"])["companies"] == _uuids(
        yard.alpha, yard.beta
    )
    document = _read(app_conn, "people_get", scoped, hana["id"])
    assert document["company_ids"] == [str(yard.alpha)]
    assert document["other_companies"] == 1


def test_a_vehicle_scoped_editor_keeps_a_vehicle_outside_their_view(
    app_conn: Conn, owner_conn: Conn, operator_conn: Conn, owner: Member, yard: Yard
) -> None:
    editor = provision_member(operator_conn, 6, "Office admin", "Eve", "Editor")
    set_scope(owner_conn, editor, editor.org, vehicles=[yard.a1])
    vic = create_person(
        app_conn,
        owner,
        scope_mode="vehicles",
        vehicle_ids=[yard.a1, yard.b1],
        email="vic@example.com",
        phone="0722000888",
    )
    update_person(
        app_conn,
        editor,
        vic["id"],
        vic["version"],
        last_name="Mwangi",
        scope_mode="vehicles",
        vehicle_ids=[yard.a1],
        email="vic@example.com",
        phone="0722000888",
    )
    assert scope_rows(owner_conn, owner.org, vic["id"])["vehicles"] == _uuids(yard.a1, yard.b1)
    document = _read(app_conn, "people_get", editor, vic["id"])
    assert document["vehicle_ids"] == [str(yard.a1)]
    assert document["other_vehicles"] == 1


# --- visibility ---


@dataclass(frozen=True, slots=True)
class Team:
    cora: dict[str, Any]
    victor: dict[str, Any]
    vera: dict[str, Any]
    bea: dict[str, Any]
    gus: dict[str, Any]
    mia: UUID
    company_viewer: Member
    vehicle_viewer: Member


@pytest.fixture
def team(
    app_conn: Conn,
    owner_conn: Conn,
    operator_conn: Conn,
    owner: Member,
    office: Member,
    yard: Yard,
) -> Team:
    def person(first: str, last: str, slot: int, **fields: Any) -> dict[str, Any]:
        return create_person(
            app_conn,
            owner,
            first_name=first,
            last_name=last,
            email=f"{first}.{last}@example.com".lower(),
            phone=f"0722{slot:06d}",
            **fields,
        )

    cora = person("Cora", "Alphaco", 1, scope_mode="companies", company_ids=[yard.alpha])
    victor = person("Victor", "Alphaveh", 2, scope_mode="vehicles", vehicle_ids=[yard.a1])
    vera = person("Vera", "Alphatwo", 3, scope_mode="vehicles", vehicle_ids=[yard.a2])
    bea = person("Bea", "Betaco", 4, scope_mode="companies", company_ids=[yard.beta])
    gus = person("Gus", "Global", 5)
    mia = person("Mia", "Mixed", 6, scope_mode="vehicles", vehicle_ids=[yard.a1])["id"]
    set_scope(owner_conn, mia, owner.org, companies=[yard.beta], vehicles=[yard.a1])
    company_viewer = provision_member(operator_conn, 7, "Office admin", "Cam", "Viewer")
    set_scope(owner_conn, company_viewer, owner.org, companies=[yard.alpha])
    vehicle_viewer = provision_member(operator_conn, 8, "Office admin", "Vic", "Viewer")
    set_scope(owner_conn, vehicle_viewer, owner.org, vehicles=[yard.a1])
    return Team(cora, victor, vera, bea, gus, mia, company_viewer, vehicle_viewer)


def test_an_all_companies_viewer_lists_everyone_in_last_name_order(
    app_conn: Conn, office: Member, team: Team
) -> None:
    page = _read(app_conn, "people_list", office, 1, 50, None, None)
    assert [i["last_name"] for i in page["items"]] == [
        "Alphaco",
        "Alphatwo",
        "Alphaveh",
        "Betaco",
        "Global",
        "Mixed",
        "Office",
        "Owner",
        "Viewer",
        "Viewer",
    ]
    assert page["total"] == 10


def test_people_with_one_last_name_are_ordered_by_first_name_then_user_id(
    app_conn: Conn, owner: Member
) -> None:
    created = {}
    for first, slot in (("Zed", 1), ("Amy", 2), ("Sam", 3), ("Sam", 4)):
        row = create_person(
            app_conn,
            owner,
            first_name=first,
            last_name="Same",
            email=f"p{slot}@example.com",
            phone=f"0722{slot:06d}",
        )
        created[slot] = str(row["id"])
    page = _read(app_conn, "people_list", owner, 1, 50, None, None)
    same = [(i["first_name"], i["id"]) for i in page["items"] if i["last_name"] == "Same"]
    assert same == [
        ("Amy", created[2]),
        *[("Sam", i) for i in sorted([created[3], created[4]])],
        ("Zed", created[1]),
    ]


def test_a_page_is_cut_from_the_ordered_list_and_total_counts_everyone(
    app_conn: Conn, office: Member, team: Team
) -> None:
    first = _read(app_conn, "people_list", office, 1, 3, None, None)
    second = _read(app_conn, "people_list", office, 2, 3, None, None)
    beyond = _read(app_conn, "people_list", office, 99, 3, None, None)
    assert [i["last_name"] for i in first["items"]] == ["Alphaco", "Alphatwo", "Alphaveh"]
    assert [i["last_name"] for i in second["items"]] == ["Betaco", "Global", "Mixed"]
    assert (first["total"], second["total"], beyond["total"]) == (10, 10, 10)
    assert beyond["items"] == []


@pytest.mark.parametrize(("page", "size"), [(0, 10), (1, 0), (1, 101), (100001, 10)])
def test_people_list_refuses_a_page_outside_the_bounds(
    app_conn: Conn, office: Member, page: int, size: int
) -> None:
    args = [office.id, office.org, REQUEST, page, size, None, None, T0]
    refused(app_conn, "people_list", args, "XC422", "page_out_of_range")


def _people(
    app: Conn, who: Member, role: str | None, status: str | None, page: int = 1, size: int = 50
) -> dict[str, Any]:
    result: dict[str, Any] = call(
        app, "people_list", who.id, who.org, REQUEST, page, size, role, status, T0
    )
    return result


def test_people_list_keeps_one_role_by_name_and_one_sign_in_state(
    app_conn: Conn, owner_conn: Conn, owner: Member, office: Member, team: Team
) -> None:
    owner_conn.execute(
        "UPDATE identity.users SET pin_hash = 'c2FsdA==.aGFzaA==' WHERE id = %s",
        (team.cora["id"],),
    )
    version = _read(app_conn, "people_get", office, team.vera["id"])["version"]
    _set_active(app_conn, owner, team.vera["id"], False, version, "Left the company")

    everyone = _people(app_conn, office, None, None)
    by_id = {i["id"]: i for i in everyone["items"]}
    active = _people(app_conn, office, None, "active")
    waiting = _people(app_conn, office, None, "waiting")
    none = _people(app_conn, office, None, "none")
    assert all(i["active"] and i["has_pin"] for i in active["items"])
    assert all(i["active"] and not i["has_pin"] for i in waiting["items"])
    assert [i["id"] for i in none["items"]] == [str(team.vera["id"])]
    assert str(team.cora["id"]) in [i["id"] for i in active["items"]]
    assert str(team.bea["id"]) in [i["id"] for i in waiting["items"]]
    assert active["total"] + waiting["total"] + none["total"] == everyone["total"] == 10
    for blank in ("", "all"):
        assert _people(app_conn, office, blank, blank) == everyone

    clerks = _people(app_conn, office, "Revenue clerk", None)
    assert {i["role"] for i in clerks["items"]} == {"Revenue clerk"}
    assert clerks["total"] == sum(1 for i in by_id.values() if i["role"] == "Revenue clerk")
    assert _people(app_conn, office, "revenue CLERK", None) == clerks
    assert _people(app_conn, office, "Nobody", None) == {"total": 0, "items": []}
    one = _people(app_conn, office, "Revenue clerk", "waiting", 1, 1)
    assert one["total"] == sum(1 for i in waiting["items"] if i["role"] == "Revenue clerk")
    assert len(one["items"]) == 1

    scoped = _people(app_conn, team.company_viewer, "Revenue clerk", "waiting")
    assert [i["last_name"] for i in scoped["items"]] == ["Alphaveh", "Mixed"]
    assert scoped["total"] == 2


@pytest.mark.parametrize("status", ["asleep", "Active", " none"])
def test_people_list_refuses_an_unknown_sign_in_state(
    app_conn: Conn, office: Member, status: str
) -> None:
    args = [office.id, office.org, REQUEST, 1, 10, None, status, T0]
    refused(app_conn, "people_list", args, "XC422", "people_filter_status_invalid")


def test_people_list_checks_permission_and_page_before_the_state(
    app_conn: Conn, clerk: Member, office: Member
) -> None:
    denied = [clerk.id, clerk.org, REQUEST, 1, 10, None, "asleep", T0]
    refused(app_conn, "people_list", denied, "XC403", "permission_missing")
    out_of_range = [office.id, office.org, REQUEST, 0, 10, None, "asleep", T0]
    refused(app_conn, "people_list", out_of_range, "XC422", "page_out_of_range")


def test_people_list_and_get_need_people_view(app_conn: Conn, clerk: Member) -> None:
    list_args = [clerk.id, clerk.org, REQUEST, 1, 10, None, None, T0]
    refused(app_conn, "people_list", list_args, "XC403", "permission_missing")
    get_args = [clerk.id, clerk.org, REQUEST, clerk.id, T0]
    refused(app_conn, "people_get", get_args, "XC403", "permission_missing")


def test_an_all_companies_viewer_sees_every_scope_unfiltered(
    app_conn: Conn, office: Member, team: Team, yard: Yard
) -> None:
    mia = _read(app_conn, "people_get", office, team.mia)
    assert mia["scope_mode"] == "companies"
    assert mia["company_ids"] == [str(yard.beta)]
    assert mia["vehicle_ids"] == [str(yard.a1)]
    assert (mia["other_companies"], mia["other_vehicles"]) == (0, 0)
    gus = _read(app_conn, "people_get", office, team.gus["id"])
    assert (gus["scope_mode"], gus["company_ids"], gus["vehicle_ids"]) == ("all", [], [])


def test_a_company_scoped_viewer_sees_people_meeting_their_companies_and_vehicles(
    app_conn: Conn, team: Team
) -> None:
    page = _read(app_conn, "people_list", team.company_viewer, 1, 50, None, None)
    assert [i["last_name"] for i in page["items"]] == [
        "Alphaco",
        "Alphatwo",
        "Alphaveh",
        "Mixed",
        "Viewer",
        "Viewer",
    ]
    assert page["total"] == 6


def test_a_vehicle_scoped_viewer_sees_people_meeting_their_vehicles_and_those_companies(
    app_conn: Conn, team: Team
) -> None:
    page = _read(app_conn, "people_list", team.vehicle_viewer, 1, 50, None, None)
    assert [i["last_name"] for i in page["items"]] == [
        "Alphaco",
        "Alphaveh",
        "Mixed",
        "Viewer",
        "Viewer",
    ]
    assert page["total"] == 5


def test_a_scoped_viewer_cannot_get_a_person_outside_their_view(app_conn: Conn, team: Team) -> None:
    for viewer in (team.company_viewer, team.vehicle_viewer):
        for hidden in (team.bea["id"], team.gus["id"]):
            args = [viewer.id, viewer.org, REQUEST, hidden, T0]
            refused(app_conn, "people_get", args, "XC404", "not_found")


def test_getting_an_unknown_or_missing_person_is_not_found(app_conn: Conn, office: Member) -> None:
    for missing in (uuid4(), None):
        args = [office.id, office.org, REQUEST, missing, T0]
        refused(app_conn, "people_get", args, "XC404", "not_found")


def test_a_company_scoped_viewer_sees_ids_inside_their_reach_and_counts_the_rest(
    app_conn: Conn, team: Team, yard: Yard
) -> None:
    mia = _read(app_conn, "people_get", team.company_viewer, team.mia)
    assert mia["company_ids"] == []
    assert mia["other_companies"] == 1
    assert mia["vehicle_ids"] == [str(yard.a1)]
    assert mia["other_vehicles"] == 0
    cora = _read(app_conn, "people_get", team.company_viewer, team.cora["id"])
    assert cora["company_ids"] == [str(yard.alpha)]
    assert cora["other_companies"] == 0


def test_a_vehicle_scoped_viewer_sees_no_company_ids_and_counts_them_as_others(
    app_conn: Conn, team: Team, yard: Yard
) -> None:
    cora = _read(app_conn, "people_get", team.vehicle_viewer, team.cora["id"])
    assert cora["company_ids"] == []
    assert cora["other_companies"] == 1
    victor = _read(app_conn, "people_get", team.vehicle_viewer, team.victor["id"])
    assert victor["vehicle_ids"] == [str(yard.a1)]
    assert victor["other_vehicles"] == 0


def test_a_scoped_viewer_sees_themselves(app_conn: Conn, team: Team) -> None:
    me = _read(app_conn, "people_get", team.company_viewer, team.company_viewer.id)
    assert me["id"] == str(team.company_viewer.id)
    assert me["other_companies"] == 0


def test_the_permissions_of_an_inactive_person_are_kept(
    app_conn: Conn, owner: Member, team: Team
) -> None:
    before = _read(app_conn, "people_get", owner, team.cora["id"])
    _set_active(app_conn, owner, team.cora["id"], False, 1, "Left")
    after = _read(app_conn, "people_get", owner, team.cora["id"])
    assert after["active"] is False
    assert after["permissions"] == before["permissions"] == _role_defaults("Revenue clerk")


def test_a_person_document_reports_whether_a_pin_is_set(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    jane = create_person(app_conn, owner)
    assert _read(app_conn, "people_get", owner, jane["id"])["has_pin"] is False
    owner_conn.execute(
        "UPDATE identity.users SET pin_hash = 'c2FsdA==.aGFzaA==' WHERE id = %s", (jane["id"],)
    )
    assert _read(app_conn, "people_get", owner, jane["id"])["has_pin"] is True


def test_a_person_document_carries_every_field(app_conn: Conn, owner: Member) -> None:
    jane = create_person(app_conn, owner, approval_limit=Decimal("250.50"))
    document = _read(app_conn, "people_get", owner, jane["id"])
    assert set(document) == {
        "id",
        "first_name",
        "last_name",
        "email",
        "phone_number",
        "role",
        "active",
        "scope_mode",
        "company_ids",
        "vehicle_ids",
        "permissions",
        "approval_limit",
        "has_pin",
        "version",
        "other_companies",
        "other_vehicles",
        "status",
        "last_signed_in_at",
        "back_limit",
        "can_change",
        "modules",
        "everything",
        "sign_in",
    }
    assert (document["email"], document["phone_number"]) == ("jane@example.com", "+254722000111")
    assert (document["first_name"], document["last_name"]) == ("Jane", "Njeri")
    assert (document["active"], document["version"]) == (True, 1)
    assert Decimal(str(document["approval_limit"])) == Decimal("250.50")


# --- versions ---


def test_creating_a_person_stores_an_active_membership_at_version_one(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    row = create_person(app_conn, owner)
    assert (row["version"], row["outcome"]) == (1, "created")
    stored = membership(owner_conn, owner.org, row["id"])
    assert (stored["active"], stored["version"]) == (True, 1)
    account = user_row(owner_conn, row["id"])
    assert (account["status"], account["pin_hash"], account["security_version"]) == (
        "active",
        None,
        0,
    )


def test_an_update_bumps_the_membership_version_by_one(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    jane = create_person(app_conn, owner)
    second = update_person(app_conn, owner, jane["id"], 1, last_name="Mwangi")
    third = update_person(app_conn, owner, jane["id"], 2, last_name="Wanjiru")
    assert [(second["version"], second["outcome"]), (third["version"], third["outcome"])] == [
        (2, "updated"),
        (3, "updated"),
    ]
    assert membership(owner_conn, owner.org, jane["id"])["version"] == 3


def test_an_update_that_changes_nothing_is_unchanged_and_logs_nothing(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    jane = create_person(app_conn, owner)
    logged = len(change_log(owner_conn, owner.org))
    version = settings_version(owner_conn, owner.org)
    row = update_person(app_conn, owner, jane["id"], 1)
    assert (row["id"], row["version"], row["outcome"]) == (jane["id"], 1, "unchanged")
    assert len(change_log(owner_conn, owner.org)) == logged
    assert settings_version(owner_conn, owner.org) == version
    assert membership(owner_conn, owner.org, jane["id"])["version"] == 1


def test_the_same_values_in_another_notation_are_unchanged(app_conn: Conn, owner: Member) -> None:
    jane = create_person(app_conn, owner, permissions=[*CLERK_KEYS, "reports.view"])
    row = update_person(
        app_conn,
        owner,
        jane["id"],
        1,
        email="  JANE@Example.com ",
        phone="+254 722 000 111",
        first_name=" Jane ",
        role="revenue clerk",
        permissions=["reports.view", *CLERK_KEYS[::-1]],
    )
    assert row["outcome"] == "unchanged"


# --- snapshots and reasons ---


def test_a_created_person_is_logged_with_a_null_before_and_the_compact_snapshot(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    jane = create_person(app_conn, owner)
    entry = change_log(owner_conn, owner.org)[-1]
    assert (entry["section"], entry["entity_id"], entry["actor_id"]) == (
        "people",
        jane["id"],
        owner.id,
    )
    assert entry["before"] == "null"
    assert entry["after"] == JANE_AFTER


def test_an_updated_person_is_logged_with_both_snapshots(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    jane = create_person(app_conn, owner)
    update_person(app_conn, owner, jane["id"], 1, approval_limit=Decimal("5000.00"))
    entry = change_log(owner_conn, owner.org)[-1]
    assert entry["before"] == JANE_AFTER
    assert entry["after"] == JANE_AFTER.replace('"ApprovalLimit":null', '"ApprovalLimit":5000')


def test_a_snapshot_lists_single_permissions_in_ordinal_order(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    create_person(app_conn, owner, permissions=[*CLERK_KEYS, "reports.view"])
    after = change_log(owner_conn, owner.org)[-1]["after"]
    assert '"Permissions":["dash.gaps","reports.view","revenue.capture","revenue.view"]' in after


def test_a_snapshot_lists_scope_ids_sorted(
    app_conn: Conn, owner_conn: Conn, owner: Member, yard: Yard
) -> None:
    create_person(app_conn, owner, scope_mode="companies", company_ids=[yard.beta, yard.alpha])
    after = change_log(owner_conn, owner.org)[-1]["after"]
    ids = ",".join(f'"{i}"' for i in _sorted_ids(yard.alpha, yard.beta))
    assert f'"ScopeMode":"companies","CompanyIds":[{ids}],"VehicleIds":[]' in after


def test_creating_a_person_is_logged_as_added(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    create_person(app_conn, owner)
    assert change_log(owner_conn, owner.org)[-1]["reason"] == "Added Jane Njeri as Revenue clerk"


def test_the_role_is_logged_in_its_catalogue_spelling(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    create_person(app_conn, owner, role="fleet MANAGER", permissions=FLEET_KEYS)
    assert change_log(owner_conn, owner.org)[-1]["reason"] == "Added Jane Njeri as Fleet manager"


def test_changing_the_role_is_logged_as_a_role_change(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    jane = create_person(app_conn, owner)
    update_person(app_conn, owner, jane["id"], 1, role="Fleet manager", permissions=FLEET_KEYS)
    assert change_log(owner_conn, owner.org)[-1]["reason"] == "Changed role for Jane Njeri"


def test_several_changes_are_joined_in_one_reason(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    jane = create_person(app_conn, owner)
    update_person(
        app_conn,
        owner,
        jane["id"],
        1,
        first_name="Janet",
        email="janet@example.com",
        phone="0722000222",
        role="Fleet manager",
        permissions=FLEET_KEYS,
    )
    assert (
        change_log(owner_conn, owner.org)[-1]["reason"]
        == "Changed name, sign-in details and role for Janet Njeri"
    )


def test_all_seven_kinds_of_change_are_joined_with_commas_and_and(
    app_conn: Conn, owner_conn: Conn, owner: Member, yard: Yard
) -> None:
    jane = create_person(app_conn, owner)
    update_person(
        app_conn,
        owner,
        jane["id"],
        1,
        last_name="Mwangi",
        email="jm@example.com",
        phone="0722000222",
        role="Fleet manager",
        permissions=[*FLEET_KEYS, "audit.view"],
        scope_mode="companies",
        company_ids=[yard.alpha],
        approval_limit=Decimal(10),
        back_limit_mode="months",
        back_limit_count=1,
    )
    assert change_log(owner_conn, owner.org)[-1]["reason"] == (
        "Changed name, sign-in details, role, single permissions, data scope, approval limit "
        "and how far back they can change records for Jane Mwangi"
    )


def test_changing_the_data_scope_alone_is_logged_as_a_data_scope_change(
    app_conn: Conn, owner_conn: Conn, owner: Member, yard: Yard
) -> None:
    jane = create_person(app_conn, owner)
    update_person(app_conn, owner, jane["id"], 1, scope_mode="vehicles", vehicle_ids=[yard.a1])
    assert change_log(owner_conn, owner.org)[-1]["reason"] == "Changed data scope for Jane Njeri"


def test_remove_all_is_logged_as_trusted_device_removed(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    jane = _with_session(app_conn, owner_conn, owner)
    trust(owner_conn, jane["id"], "device-2", name="Phone 2", last_used_at=T0 - HOUR)
    row = _sign_out(app_conn, owner, jane["id"])
    assert (row["id"], row["version"], row["outcome"]) == (jane["id"], 1, "updated")
    entry = change_log(owner_conn, owner.org)[-1]
    assert (entry["section"], entry["entity_id"]) == ("signIn", jane["id"])
    assert entry["reason"] == "Trusted device removed, Jane Njeri"
    assert entry["before"] == '{"Status":"Not signed in yet","Devices":["Phone 2",null]}'
    assert entry["after"] == '{"Status":"Not signed in yet","Devices":[]}'


def test_remove_all_with_nothing_left_to_remove_is_unchanged(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    jane = create_person(app_conn, owner)
    logged = len(change_log(owner_conn, owner.org))
    row = _sign_out(app_conn, owner, jane["id"])
    assert (row["version"], row["outcome"]) == (1, "unchanged")
    assert len(change_log(owner_conn, owner.org)) == logged


def test_deactivating_a_person_logs_the_reason(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    jane = create_person(app_conn, owner)
    _set_active(app_conn, owner, jane["id"], False, 1, "Left the organization")
    entry = change_log(owner_conn, owner.org)[-1]
    assert entry["reason"] == "Removed access for Jane Njeri. Reason: Left the organization."
    assert entry["before"] == JANE_AFTER
    assert entry["after"] == JANE_AFTER.replace('"Active":true', '"Active":false')


def test_reactivating_a_person_is_logged_as_restored(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    jane = create_person(app_conn, owner)
    _set_active(app_conn, owner, jane["id"], False, 1, "Left")
    _set_active(app_conn, owner, jane["id"], True, 2)
    assert change_log(owner_conn, owner.org)[-1]["reason"] == "Restored access for Jane Njeri"


def test_two_deactivations_at_once_end_the_person_once(
    app_conn: Conn, app_url: str, owner_conn: Conn, owner: Member
) -> None:
    jane = create_person(app_conn, owner)
    logged = len(change_log(owner_conn, owner.org))
    security = user_row(owner_conn, jane["id"])["security_version"]
    first, late = _race(
        app_url,
        lambda one: _set_active(one, owner, jane["id"], False, 1, "Left"),
        lambda two: _set_active(two, owner, jane["id"], False, 1, "Left"),
    )
    assert (first["version"], first["outcome"]) == (2, "updated")
    assert (late["version"], late["outcome"]) == (2, "unchanged")
    assert len(change_log(owner_conn, owner.org)) == logged + 1
    assert user_row(owner_conn, jane["id"])["security_version"] == security + 1


@pytest.mark.parametrize("write", ["save", "deactivate"])
def test_a_person_write_leaves_the_membership_open_to_the_change_log_key_check(
    app_conn: Conn, app_url: str, owner_conn: Conn, owner: Member, write: str
) -> None:
    jane = create_person(app_conn, owner)
    with psycopg.connect(app_url, autocommit=True, row_factory=dict_row) as one:
        with one.transaction():
            if write == "save":
                update_person(one, owner, jane["id"], 1, last_name="Wanjiru")
            else:
                _set_active(one, owner, jane["id"], False, 1, "Left")
            # A change-log row naming this person as actor takes KEY SHARE on the membership;
            # blocking it would deadlock an edit of an admin with that admin's own logged write.
            row = owner_conn.execute(
                "SELECT 1 AS free FROM tenancy.memberships "
                "WHERE organization_id = %s AND user_id = %s FOR KEY SHARE NOWAIT",
                (owner.org, jane["id"]),
            ).fetchone()
    assert row == {"free": 1}


def test_every_logged_write_moves_the_settings_version_by_exactly_one(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    start = settings_version(owner_conn, owner.org)
    jane = _with_session(app_conn, owner_conn, owner)
    update_person(app_conn, owner, jane["id"], 1, last_name="Mwangi")
    update_person(app_conn, owner, jane["id"], 2, last_name="Mwangi")
    _sign_out(app_conn, owner, jane["id"])
    _set_active(app_conn, owner, jane["id"], False, 2, "Left")
    _set_active(app_conn, owner, jane["id"], False, None, None)
    _set_active(app_conn, owner, jane["id"], True, 3)
    entries = change_log(owner_conn, owner.org)
    assert [e["version"] for e in entries] == [start + n for n in range(1, 6)]
    assert settings_version(owner_conn, owner.org) == start + 5


def test_each_logged_write_has_an_audit_event(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    jane = _with_session(app_conn, owner_conn, owner)
    update_person(app_conn, owner, jane["id"], 1, last_name="Mwangi")
    _sign_out(app_conn, owner, jane["id"])
    _set_active(app_conn, owner, jane["id"], False, 2, "Left")
    _set_active(app_conn, owner, jane["id"], True, 3)
    actions = [e["action"] for e in audit_events(owner_conn, owner.org)]
    assert actions == [
        "person.created",
        "person.updated",
        "person.sessions_revoked",
        "person.deactivated",
        "person.activated",
    ]
    created = audit_events(owner_conn, owner.org, "person.created")[0]
    assert created["before"] is None
    assert created["after"] == json.loads(JANE_AFTER)
    assert created["entity"] == str(jane["id"])


# --- lifecycle ---


@pytest.mark.parametrize("active", [False, True])
def test_nobody_changes_their_own_active_state(app_conn: Conn, owner: Member, active: bool) -> None:
    _set_active_refused(app_conn, owner, owner.id, active, 1, "XC422", "people_self_deactivate")


def test_nobody_signs_themselves_out_here(app_conn: Conn, owner: Member) -> None:
    _sign_out_refused(app_conn, owner, owner.id, "XC422", "people_self_sign_out")


def test_only_an_owner_deactivates_or_activates_an_owner(
    app_conn: Conn, owner: Member, office: Member
) -> None:
    _set_active_refused(app_conn, office, owner.id, False, 1, "XC403", "people_owner_edit", "Gone")
    _set_active_refused(app_conn, office, owner.id, True, 1, "XC403", "people_owner_edit")


def test_only_an_owner_signs_an_owner_out(app_conn: Conn, owner: Member, office: Member) -> None:
    _sign_out_refused(app_conn, office, owner.id, "XC403", "people_owner_edit")


def test_an_owner_may_deactivate_another_owner(
    app_conn: Conn, operator_conn: Conn, owner: Member
) -> None:
    second = provision_member(operator_conn, 9, "Owner", "Olga", "Owner")
    row = _set_active(app_conn, owner, second.id, False, 1, "Left")
    assert row["outcome"] == "updated"


def test_lifecycle_calls_on_unknown_people_are_not_found(app_conn: Conn, owner: Member) -> None:
    _set_active_refused(app_conn, owner, uuid4(), False, 1, "XC404", "not_found", "Gone")
    _set_active_refused(app_conn, owner, None, False, 1, "XC404", "not_found", "Gone")
    _sign_out_refused(app_conn, owner, uuid4(), "XC404", "not_found")
    _sign_out_refused(app_conn, owner, None, "XC404", "not_found")


def test_a_missing_active_flag_is_not_found(app_conn: Conn, owner: Member, clerk: Member) -> None:
    _set_active_refused(app_conn, owner, clerk.id, None, 1, "XC404", "not_found")


def test_a_scoped_editor_cannot_reach_a_person_outside_their_view(
    app_conn: Conn, owner: Member, scoped: Member, yard: Yard
) -> None:
    bea = create_person(
        app_conn,
        owner,
        scope_mode="companies",
        company_ids=[yard.beta],
        email="bea@example.com",
        phone="0722000222",
    )
    _set_active_refused(app_conn, scoped, bea["id"], False, 1, "XC404", "not_found", "Gone")
    _sign_out_refused(app_conn, scoped, bea["id"], "XC404", "not_found")


@pytest.mark.parametrize("active", [True, False])
def test_repeating_a_finished_transition_skips_the_version_check_and_logs_nothing(
    app_conn: Conn, owner_conn: Conn, owner: Member, active: bool
) -> None:
    jane = create_person(app_conn, owner)
    version = 1
    if not active:
        _set_active(app_conn, owner, jane["id"], False, 1, "Left")
        version = 2
    logged = len(change_log(owner_conn, owner.org))
    row = _set_active(app_conn, owner, jane["id"], active, None, None)
    assert (row["id"], row["version"], row["outcome"]) == (jane["id"], version, "unchanged")
    assert len(change_log(owner_conn, owner.org)) == logged
    assert membership(owner_conn, owner.org, jane["id"])["version"] == version


@pytest.mark.parametrize("version", [5, None])
def test_a_transition_with_a_stale_or_missing_version_conflicts(
    app_conn: Conn, owner: Member, version: int | None
) -> None:
    jane = create_person(app_conn, owner)
    _set_active_refused(
        app_conn, owner, jane["id"], False, version, "XC409", "version_conflict", "Left"
    )


@pytest.mark.parametrize("reason", [None, "", "   ", "x" * 501])
def test_deactivating_needs_a_typed_reason_of_one_to_five_hundred_characters(
    app_conn: Conn, owner_conn: Conn, owner: Member, reason: str | None
) -> None:
    jane = create_person(app_conn, owner)
    _set_active_refused(app_conn, owner, jane["id"], False, 1, "XC422", "reason_length", reason)
    assert membership(owner_conn, owner.org, jane["id"])["active"] is True


def test_a_reason_of_five_hundred_characters_is_accepted(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    jane = create_person(app_conn, owner)
    _set_active(app_conn, owner, jane["id"], False, 1, "x" * 500)
    assert len(change_log(owner_conn, owner.org)[-1]["reason"]) == 500


def test_activating_ignores_the_reason(app_conn: Conn, owner_conn: Conn, owner: Member) -> None:
    jane = create_person(app_conn, owner)
    _set_active(app_conn, owner, jane["id"], False, 1, "Left")
    _set_active(app_conn, owner, jane["id"], True, 2, "x" * 900)
    assert change_log(owner_conn, owner.org)[-1]["reason"] == "Restored access for Jane Njeri"


def test_deactivation_flips_the_membership_and_the_account(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    jane = create_person(app_conn, owner)
    row = _set_active(app_conn, owner, jane["id"], False, 1, "Left")
    assert (row["version"], row["outcome"]) == (2, "updated")
    stored = membership(owner_conn, owner.org, jane["id"])
    assert (stored["active"], stored["version"]) == (False, 2)
    assert user_row(owner_conn, jane["id"])["status"] == "removed"


def test_a_deactivated_person_can_no_longer_act(app_conn: Conn, owner: Member) -> None:
    jane = create_person(app_conn, owner)
    _set_active(app_conn, owner, jane["id"], False, 1, "Left")
    args = [jane["id"], owner.org, REQUEST, T0]
    refused(app_conn, "access_my_scope", args, "XC403", "not_member")


# --- sessions, devices and tokens ---


def _with_session(app: Conn, owner_conn: Conn, actor: Member, **fields: Any) -> dict[str, Any]:
    jane = create_person(app, actor, **fields)
    trust(owner_conn, jane["id"], DEVICE)
    store_token(owner_conn, jane["id"], DEVICE)
    return jane


def _resolves(app: Conn, user: UUID, version: int) -> dict[str, Any]:
    result: dict[str, Any] = call(app, "auth_resolve_session", user, DEVICE, version, T0)
    return result


def _session_refused(app: Conn, user: UUID, version: int) -> None:
    refused(app, "auth_resolve_session", [user, DEVICE, version, T0], "XC401", "session_invalid")


def test_a_role_change_bumps_the_security_version_and_keeps_devices_and_tokens(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    jane = _with_session(app_conn, owner_conn, owner)
    assert _resolves(app_conn, jane["id"], 0)["role"] == "Revenue clerk"
    update_person(app_conn, owner, jane["id"], 1, role="Fleet manager", permissions=FLEET_KEYS)
    assert user_row(owner_conn, jane["id"])["security_version"] == 1
    _session_refused(app_conn, jane["id"], 0)
    assert _resolves(app_conn, jane["id"], 1)["role"] == "Fleet manager"
    assert _revoked(owner_conn, jane["id"], DEVICE) is False
    assert live_tokens(owner_conn, jane["id"]) == 1


def test_a_single_permission_change_bumps_the_security_version(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    jane = _with_session(app_conn, owner_conn, owner)
    update_person(app_conn, owner, jane["id"], 1, permissions=[*CLERK_KEYS, "reports.view"])
    assert user_row(owner_conn, jane["id"])["security_version"] == 1
    _session_refused(app_conn, jane["id"], 0)
    _resolves(app_conn, jane["id"], 1)
    assert live_tokens(owner_conn, jane["id"]) == 1


def test_a_name_change_bumps_the_security_version(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    jane = _with_session(app_conn, owner_conn, owner)
    update_person(app_conn, owner, jane["id"], 1, last_name="Mwangi")
    assert user_row(owner_conn, jane["id"])["security_version"] == 1
    _resolves(app_conn, jane["id"], 1)


@pytest.mark.parametrize(
    "fields", [{"email": "janet@example.com"}, {"phone": "0722000222"}], ids=["email", "phone"]
)
def test_new_sign_in_details_bump_the_security_version_and_end_every_device_and_token(
    app_conn: Conn, owner_conn: Conn, owner: Member, fields: dict[str, Any]
) -> None:
    jane = _with_session(app_conn, owner_conn, owner)
    store_token(owner_conn, jane["id"], "device-2")
    trust(owner_conn, jane["id"], "device-2")
    update_person(app_conn, owner, jane["id"], 1, **fields)
    assert user_row(owner_conn, jane["id"])["security_version"] == 1
    assert _revoked(owner_conn, jane["id"], DEVICE) is True
    assert _revoked(owner_conn, jane["id"], "device-2") is True
    assert live_tokens(owner_conn, jane["id"]) == 0
    _session_refused(app_conn, jane["id"], 1)


def test_new_sign_in_details_keep_the_pin(app_conn: Conn, owner_conn: Conn, owner: Member) -> None:
    jane = _with_session(app_conn, owner_conn, owner)
    owner_conn.execute(
        "UPDATE identity.users SET pin_hash = 'c2FsdA==.aGFzaA==' WHERE id = %s", (jane["id"],)
    )
    update_person(app_conn, owner, jane["id"], 1, email="janet@example.com")
    assert user_row(owner_conn, jane["id"])["pin_hash"] == "c2FsdA==.aGFzaA=="


def test_new_sign_in_details_write_an_audit_event(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    jane = create_person(app_conn, owner)
    update_person(app_conn, owner, jane["id"], 1, email="janet@example.com", phone="0722000222")
    events = audit_events(owner_conn, owner.org, "person.sign_in_details_changed")
    assert len(events) == 1
    assert events[0]["entity"] == str(jane["id"])
    assert events[0]["actor_id"] == owner.id
    assert events[0]["before"] == {"email": "jane@example.com", "phone_number": "+254722000111"}
    assert events[0]["after"] == {"email": "janet@example.com", "phone_number": "+254722000222"}


def test_a_scope_only_change_leaves_the_session_alone(
    app_conn: Conn, owner_conn: Conn, owner: Member, yard: Yard
) -> None:
    jane = _with_session(app_conn, owner_conn, owner)
    update_person(app_conn, owner, jane["id"], 1, scope_mode="companies", company_ids=[yard.alpha])
    assert user_row(owner_conn, jane["id"])["security_version"] == 0
    _resolves(app_conn, jane["id"], 0)
    assert _revoked(owner_conn, jane["id"], DEVICE) is False
    assert live_tokens(owner_conn, jane["id"]) == 1
    assert audit_events(owner_conn, owner.org, "person.sign_in_details_changed") == []


def test_an_approval_limit_change_leaves_the_session_alone(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    jane = _with_session(app_conn, owner_conn, owner)
    update_person(app_conn, owner, jane["id"], 1, approval_limit=Decimal(100))
    assert user_row(owner_conn, jane["id"])["security_version"] == 0
    _resolves(app_conn, jane["id"], 0)


def test_deactivating_ends_everything_and_bumps_the_security_version(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    jane = _with_session(app_conn, owner_conn, owner)
    _set_active(app_conn, owner, jane["id"], False, 1, "Left")
    account = user_row(owner_conn, jane["id"])
    assert (account["status"], account["security_version"]) == ("removed", 1)
    assert _revoked(owner_conn, jane["id"], DEVICE) is True
    assert live_tokens(owner_conn, jane["id"]) == 0
    _session_refused(app_conn, jane["id"], 1)


def test_reactivating_restores_the_account_but_not_the_devices(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    jane = _with_session(app_conn, owner_conn, owner)
    _set_active(app_conn, owner, jane["id"], False, 1, "Left")
    _set_active(app_conn, owner, jane["id"], True, 2)
    account = user_row(owner_conn, jane["id"])
    assert (account["status"], account["security_version"]) == ("active", 1)
    assert _revoked(owner_conn, jane["id"], DEVICE) is True
    _session_refused(app_conn, jane["id"], 1)


def test_signing_out_revokes_devices_and_tokens_without_bumping_the_security_version(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    jane = _with_session(app_conn, owner_conn, owner)
    _resolves(app_conn, jane["id"], 0)
    _sign_out(app_conn, owner, jane["id"])
    assert user_row(owner_conn, jane["id"])["security_version"] == 0
    assert _revoked(owner_conn, jane["id"], DEVICE) is True
    assert live_tokens(owner_conn, jane["id"]) == 0
    _session_refused(app_conn, jane["id"], 0)


def test_signing_out_leaves_the_membership_version_alone(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    jane = _with_session(app_conn, owner_conn, owner)
    assert _sign_out(app_conn, owner, jane["id"])["outcome"] == "updated"
    assert membership(owner_conn, owner.org, jane["id"])["version"] == 1


# --- tenant isolation ---


@pytest.mark.parametrize(
    "routine",
    ["access_catalog_list", "access_role_list", "access_scope_options", "access_my_scope"],
)
def test_an_actor_of_another_organization_cannot_read_access_data(
    app_conn: Conn, owner_conn: Conn, owner: Member, routine: str
) -> None:
    other = seed_organization(owner_conn)
    refused(app_conn, routine, [other.user, owner.org, REQUEST, T0], "XC403", "not_member")


def test_an_actor_of_another_organization_cannot_list_or_change_people(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    other = seed_organization(owner_conn)
    stranger = Member(
        other.user, owner.org, "x@example.com", "0700000000", "Owen", "Owner", "Owner"
    )
    list_args = [stranger.id, owner.org, REQUEST, 1, 10, None, None, T0]
    refused(app_conn, "people_list", list_args, "XC403", "not_member")
    create_refused(app_conn, stranger, "XC403", "not_member")
    update_refused(app_conn, stranger, owner.id, 1, "XC403", "not_member")
    _set_active_refused(app_conn, stranger, owner.id, False, 1, "XC403", "not_member", "Gone")
    _sign_out_refused(app_conn, stranger, owner.id, "XC403", "not_member")
    _pin_reset_refused(app_conn, stranger, owner.id, "XC403", "not_member")
    _device_remove_refused(app_conn, stranger, owner.id, uuid4(), "XC403", "not_member")


def test_a_member_does_not_see_the_people_of_another_organization(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    other = seed_organization(owner_conn)
    page = _read(app_conn, "people_list", owner, 1, 50, None, None)
    assert str(other.user) not in [i["id"] for i in page["items"]]
    args = [owner.id, owner.org, REQUEST, other.user, T0]
    refused(app_conn, "people_get", args, "XC404", "not_found")


# --- the sign-in actions: make them reset the PIN, remove one device, remove all ---


def _signed_in(app: Conn, owner_conn: Conn, actor: Member, **fields: Any) -> dict[str, Any]:
    jane = _with_session(app, owner_conn, actor, **fields)
    set_user(owner_conn, jane["id"], pin_hash=PIN_HASH)
    return jane


def test_making_a_person_reset_ends_their_sessions_at_once(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    jane = _signed_in(app_conn, owner_conn, owner)
    _resolves(app_conn, jane["id"], 0)
    row = _pin_reset(app_conn, owner, jane["id"])
    assert (row["id"], row["version"], row["outcome"]) == (jane["id"], 1, "updated")
    account = user_row(owner_conn, jane["id"])
    assert (account["pin_reset_required"], account["security_version"]) == (True, 1)
    assert account["pin_hash"] == PIN_HASH
    assert _revoked(owner_conn, jane["id"], DEVICE) is True
    assert live_tokens(owner_conn, jane["id"]) == 0
    _session_refused(app_conn, jane["id"], 0)
    _session_refused(app_conn, jane["id"], 1)
    entry = change_log(owner_conn, owner.org)[-1]
    assert (entry["section"], entry["entity_id"]) == ("signIn", jane["id"])
    assert entry["reason"] == "PIN reset required, Jane Njeri"
    assert entry["before"] == '{"Status":"Active","Devices":[null]}'
    assert entry["after"] == '{"Status":"PIN reset due","Devices":[]}'
    event = audit_events(owner_conn, owner.org, "person.pin_reset_required")
    assert [e["entity"] for e in event] == [str(jane["id"])]
    assert _read(app_conn, "people_get", owner, jane["id"])["status"] == "pin_reset_due"


def test_a_pin_reset_already_due_or_without_a_pin_is_unchanged(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    jane = _signed_in(app_conn, owner_conn, owner)
    newcomer = create_person(app_conn, owner, email="new@example.com", phone="0722000999")
    _pin_reset(app_conn, owner, jane["id"])
    logged = len(change_log(owner_conn, owner.org))
    assert _pin_reset(app_conn, owner, jane["id"])["outcome"] == "unchanged"
    assert _pin_reset(app_conn, owner, newcomer["id"])["outcome"] == "unchanged"
    assert len(change_log(owner_conn, owner.org)) == logged
    assert user_row(owner_conn, jane["id"])["security_version"] == 1


def test_removing_one_device_leaves_the_others(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    jane = _signed_in(app_conn, owner_conn, owner)
    trust(owner_conn, jane["id"], "device-2", name="Tablet", last_used_at=T0 - HOUR)
    store_token(owner_conn, jane["id"], "device-2")
    row_id = device_row(owner_conn, jane["id"], "device-2")["id"]  # type: ignore[index]
    row = _device_remove(app_conn, owner, jane["id"], row_id)
    assert (row["id"], row["version"], row["outcome"]) == (jane["id"], 1, "updated")
    assert _revoked(owner_conn, jane["id"], "device-2") is True
    assert live_tokens(owner_conn, jane["id"], "device-2") == 0
    assert _revoked(owner_conn, jane["id"], DEVICE) is False
    assert live_tokens(owner_conn, jane["id"], DEVICE) == 1
    _resolves(app_conn, jane["id"], 0)
    assert user_row(owner_conn, jane["id"])["security_version"] == 0
    entry = change_log(owner_conn, owner.org)[-1]
    assert (entry["section"], entry["reason"]) == ("signIn", "Trusted device removed, Jane Njeri")
    assert entry["before"] == '{"Status":"Active","Devices":["Tablet",null]}'
    assert entry["after"] == '{"Status":"Active","Devices":[null]}'
    assert len(audit_events(owner_conn, owner.org, "person.device_removed")) == 1


def test_a_device_row_that_is_gone_or_someone_elses_is_not_found(
    app_conn: Conn, owner_conn: Conn, owner: Member, office: Member
) -> None:
    jane = _signed_in(app_conn, owner_conn, owner)
    trust(owner_conn, office.id, "office-phone")
    theirs = device_row(owner_conn, office.id, "office-phone")["id"]  # type: ignore[index]
    mine = device_row(owner_conn, jane["id"], DEVICE)["id"]  # type: ignore[index]
    for row_id in (theirs, uuid4(), None):
        _device_remove_refused(app_conn, owner, jane["id"], row_id, "XC404", "not_found")
    _device_remove(app_conn, owner, jane["id"], mine)
    _device_remove_refused(app_conn, owner, jane["id"], mine, "XC404", "not_found")
    assert _revoked(owner_conn, office.id, "office-phone") is False


@pytest.mark.parametrize("action", ["reset", "device", "all"])
def test_people_sign_in_cannot_be_used_on_oneself(
    app_conn: Conn, owner_conn: Conn, owner: Member, action: str
) -> None:
    trust(owner_conn, owner.id, DEVICE)
    row_id = device_row(owner_conn, owner.id, DEVICE)["id"]  # type: ignore[index]
    if action == "reset":
        _pin_reset_refused(app_conn, owner, owner.id, "XC422", "people_self_sign_in")
    elif action == "device":
        _device_remove_refused(app_conn, owner, owner.id, row_id, "XC422", "people_self_sign_in")
    else:
        _sign_out_refused(app_conn, owner, owner.id, "XC422", "people_self_sign_out")
    assert _revoked(owner_conn, owner.id, DEVICE) is False


@pytest.mark.parametrize("action", ["reset", "device", "all"])
def test_only_an_owner_resets_an_owner(
    app_conn: Conn,
    operator_conn: Conn,
    owner_conn: Conn,
    owner: Member,
    office: Member,
    action: str,
) -> None:
    trust(owner_conn, owner.id, DEVICE)
    set_user(owner_conn, owner.id, pin_hash=PIN_HASH)
    row_id = device_row(owner_conn, owner.id, DEVICE)["id"]  # type: ignore[index]
    if action == "reset":
        _pin_reset_refused(app_conn, office, owner.id, "XC403", "people_owner_edit")
    elif action == "device":
        _device_remove_refused(app_conn, office, owner.id, row_id, "XC403", "people_owner_edit")
    else:
        _sign_out_refused(app_conn, office, owner.id, "XC403", "people_owner_edit")
    assert _revoked(owner_conn, owner.id, DEVICE) is False
    second = provision_member(operator_conn, 9, "Owner", "Olga", "Owner")
    if action == "reset":
        assert _pin_reset(app_conn, second, owner.id)["outcome"] == "updated"
    elif action == "device":
        assert _device_remove(app_conn, second, owner.id, row_id)["outcome"] == "updated"
    else:
        assert _sign_out(app_conn, second, owner.id)["outcome"] == "updated"


@pytest.mark.parametrize("action", ["reset", "device", "all"])
def test_the_sign_in_actions_need_the_sign_in_right(
    app_conn: Conn, owner_conn: Conn, owner: Member, office: Member, action: str
) -> None:
    jane = _signed_in(app_conn, owner_conn, owner)
    row_id = device_row(owner_conn, jane["id"], DEVICE)["id"]  # type: ignore[index]
    set_override(owner_conn, office, "people.sign_in", granted=False)
    if action == "reset":
        _pin_reset_refused(app_conn, office, jane["id"], "XC403", "permission_missing")
    elif action == "device":
        _device_remove_refused(app_conn, office, jane["id"], row_id, "XC403", "permission_missing")
    else:
        _sign_out_refused(app_conn, office, jane["id"], "XC403", "permission_missing")
    set_override(owner_conn, office, "people.sign_in", granted=True)
    if action == "reset":
        assert _pin_reset(app_conn, office, jane["id"])["outcome"] == "updated"
    elif action == "device":
        assert _device_remove(app_conn, office, jane["id"], row_id)["outcome"] == "updated"
    else:
        assert _sign_out(app_conn, office, jane["id"])["outcome"] == "updated"


@pytest.mark.parametrize("action", ["reset", "device", "all"])
def test_a_scoped_editor_cannot_act_on_a_person_outside_their_view(
    app_conn: Conn, owner_conn: Conn, owner: Member, scoped: Member, yard: Yard, action: str
) -> None:
    jane = _signed_in(app_conn, owner_conn, owner, scope_mode="companies", company_ids=[yard.beta])
    row_id = device_row(owner_conn, jane["id"], DEVICE)["id"]  # type: ignore[index]
    if action == "reset":
        _pin_reset_refused(app_conn, scoped, jane["id"], "XC404", "not_found")
    elif action == "device":
        _device_remove_refused(app_conn, scoped, jane["id"], row_id, "XC404", "not_found")
    else:
        _sign_out_refused(app_conn, scoped, jane["id"], "XC404", "not_found")
    assert _revoked(owner_conn, jane["id"], DEVICE) is False


def test_people_sign_in_cannot_be_granted_without_holding_it(
    app_conn: Conn, owner_conn: Conn, owner: Member, clerk: Member
) -> None:
    set_override(owner_conn, clerk, "people.add")
    set_override(owner_conn, clerk, "people.edit")
    set_scope(owner_conn, clerk, clerk.org, all_companies=True)
    create_refused(
        app_conn,
        clerk,
        "XC403",
        "people_permission_not_held",
        permissions=[*CLERK_KEYS, "people.sign_in"],
    )
    jane = create_person(app_conn, owner)
    update_refused(
        app_conn,
        clerk,
        jane["id"],
        1,
        "XC403",
        "people_permission_not_held",
        permissions=[*CLERK_KEYS, "people.sign_in"],
    )
    set_override(owner_conn, clerk, "people.sign_in")
    row = update_person(app_conn, clerk, jane["id"], 1, permissions=[*CLERK_KEYS, "people.sign_in"])
    assert row["outcome"] == "updated"


def test_a_sign_in_action_waits_for_a_save_of_the_same_person(
    app_conn: Conn, app_url: str, owner_conn: Conn, owner: Member
) -> None:
    jane = _signed_in(app_conn, owner_conn, owner)
    saved, reset = _race(
        app_url,
        lambda one: update_person(one, owner, jane["id"], 1, last_name="Wanjiru"),
        lambda two: _pin_reset(two, owner, jane["id"]),
    )
    assert (saved["outcome"], reset["outcome"], reset["version"]) == ("updated", "updated", 2)
    assert change_log(owner_conn, owner.org)[-1]["reason"] == "PIN reset required, Jane Wanjiru"


def test_two_resets_at_once_reset_once(
    app_conn: Conn, app_url: str, owner_conn: Conn, owner: Member
) -> None:
    jane = _signed_in(app_conn, owner_conn, owner)
    logged = len(change_log(owner_conn, owner.org))
    first, late = _race(
        app_url,
        lambda one: _pin_reset(one, owner, jane["id"]),
        lambda two: _pin_reset(two, owner, jane["id"]),
    )
    assert (first["outcome"], late["outcome"]) == ("updated", "unchanged")
    assert len(change_log(owner_conn, owner.org)) == logged + 1
    assert user_row(owner_conn, jane["id"])["security_version"] == 1


def test_a_device_removal_racing_remove_all_logs_once(
    app_conn: Conn, app_url: str, owner_conn: Conn, owner: Member
) -> None:
    jane = _signed_in(app_conn, owner_conn, owner)
    row_id = device_row(owner_conn, jane["id"], DEVICE)["id"]  # type: ignore[index]
    logged = len(change_log(owner_conn, owner.org))
    first, late = _race(
        app_url,
        lambda one: _sign_out(one, owner, jane["id"]),
        lambda two: _device_remove(two, owner, jane["id"], row_id),
    )
    assert first["outcome"] == "updated"
    assert late == ("XC404", "not_found")
    assert len(change_log(owner_conn, owner.org)) == logged + 1


@pytest.mark.parametrize("action", ["reset", "device", "all"])
def test_a_sign_in_action_leaves_the_membership_open_to_the_change_log_key_check(
    app_conn: Conn, app_url: str, owner_conn: Conn, owner: Member, action: str
) -> None:
    jane = _signed_in(app_conn, owner_conn, owner)
    row_id = device_row(owner_conn, jane["id"], DEVICE)["id"]  # type: ignore[index]
    with psycopg.connect(app_url, autocommit=True, row_factory=dict_row) as one:
        with one.transaction():
            if action == "reset":
                _pin_reset(one, owner, jane["id"])
            elif action == "device":
                _device_remove(one, owner, jane["id"], row_id)
            else:
                _sign_out(one, owner, jane["id"])
            row = owner_conn.execute(
                "SELECT 1 AS free FROM tenancy.memberships "
                "WHERE organization_id = %s AND user_id = %s FOR KEY SHARE NOWAIT",
                (owner.org, jane["id"]),
            ).fetchone()
    assert row == {"free": 1}


# --- the people statuses and the sign-in pane ---


def test_the_people_status_follows_the_sign_in_state(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    jane = create_person(app_conn, owner)

    def status() -> str:
        document = _read(app_conn, "people_get", owner, jane["id"])
        assert document["sign_in"]["status"] == document["status"]
        return str(document["status"])

    def listed(word: str) -> list[str]:
        return [i["id"] for i in _people(app_conn, owner, None, word)["items"]]

    assert status() == "not_signed_in"
    assert str(jane["id"]) in listed("not_signed_in") == listed("waiting")
    set_user(owner_conn, jane["id"], pin_hash=PIN_HASH)
    assert status() == "active"
    set_user(owner_conn, jane["id"], failed_attempts=5)
    assert status() == "locked"
    assert _read(app_conn, "people_get", owner, jane["id"])["sign_in"]["lock"] == "every_device"
    set_user(owner_conn, jane["id"], failed_attempts=0, untrusted_failed_attempts=5)
    assert status() == "locked"
    assert _read(app_conn, "people_get", owner, jane["id"])["sign_in"]["lock"] == "new_devices"
    assert str(jane["id"]) in listed("locked")
    set_user(owner_conn, jane["id"], pin_reset_required=True)
    assert status() == "pin_reset_due"
    assert str(jane["id"]) in listed("pin_reset_due")
    _set_active(app_conn, owner, jane["id"], False, 1, "Left")
    assert status() == "blocked"
    assert str(jane["id"]) in listed("blocked") == listed("none")
    assert str(jane["id"]) not in listed("active")


def test_the_status_filter_accepts_the_new_and_the_legacy_words(
    app_conn: Conn, owner: Member, team: Team
) -> None:
    everyone = _people(app_conn, owner, None, None)["total"]
    counts = {
        word: _people(app_conn, owner, None, word)["total"]
        for word in ("active", "not_signed_in", "pin_reset_due", "locked", "blocked")
    }
    assert sum(counts.values()) == everyone
    assert _people(app_conn, owner, None, "waiting")["total"] == counts["not_signed_in"]
    assert _people(app_conn, owner, None, "none")["total"] == counts["blocked"]


def test_the_sign_in_pane_lists_live_devices_most_recent_first(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    jane = _signed_in(app_conn, owner_conn, owner)
    trust(owner_conn, jane["id"], "old", name="Old phone", last_used_at=T0 - 2 * HOUR)
    trust(owner_conn, jane["id"], "gone", name="Gone", revoked=True)
    trust(owner_conn, jane["id"], "once", name="Once", remembered=False)
    set_user(owner_conn, jane["id"], last_signed_in_at=T0 - HOUR)
    pane = _read(app_conn, "people_get", owner, jane["id"])["sign_in"]
    assert pane["status"] == "active"
    assert pane["lock"] is None
    assert pane["email"] == "jane@example.com"
    assert pane["last_signed_in_at"] is not None
    assert [d["name"] for d in pane["devices"]] == [None, "Old phone"]
    assert set(pane["devices"][0]) == {"id", "name", "trusted_at", "last_used_at"}
    listed = _people(app_conn, owner, None, None)["items"]
    assert all(item["sign_in"] is None for item in listed)


def test_the_people_list_shows_modules_can_change_and_status(
    app_conn: Conn, owner: Member, office: Member
) -> None:
    jane = create_person(app_conn, owner, permissions=[*CLERK_KEYS, "reports.view"])
    item = next(
        i for i in _people(app_conn, owner, None, None)["items"] if i["id"] == str(jane["id"])
    )
    assert item["modules"] == [
        {"name": "Dashboard", "held": 1, "total": 3},
        {"name": "Revenue", "held": 2, "total": 4},
        {"name": "Reports", "held": 1, "total": 3},
    ]
    assert item["everything"] is False
    assert item["can_change"] == "7 days back"
    assert item["back_limit"] == {"mode": "days", "count": 7, "from_date": None}
    assert item["status"] == "not_signed_in"
    assert item["last_signed_in_at"] is None
    me = _read(app_conn, "people_get", office, owner.id)
    assert me["everything"] is True
    assert sum(m["held"] for m in me["modules"]) == 59


# --- the back-dating limit on the person ---


def test_a_new_person_starts_on_seven_days_back(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    jane = create_person(app_conn, owner)
    stored = membership(owner_conn, owner.org, jane["id"])
    assert (stored["back_limit_mode"], stored["back_limit_count"], stored["back_limit_from"]) == (
        "days",
        7,
        None,
    )
    assert _read(app_conn, "people_get", owner, jane["id"])["can_change"] == "7 days back"


def test_an_update_without_a_limit_keeps_the_stored_one(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    jane = create_person(app_conn, owner, back_limit_mode="months", back_limit_count=2)
    row = update_person(app_conn, owner, jane["id"], 1, last_name="Mwangi")
    assert row["outcome"] == "updated"
    stored = membership(owner_conn, owner.org, jane["id"])
    assert (stored["back_limit_mode"], stored["back_limit_count"]) == ("months", 2)


@pytest.mark.parametrize(
    "fields",
    [
        {"back_limit_mode": "weeks", "back_limit_count": 1},
        {"back_limit_mode": "none", "back_limit_count": 3},
        {"back_limit_mode": "days", "back_limit_count": None},
        {"back_limit_mode": "days", "back_limit_count": -1},
        {"back_limit_mode": "days", "back_limit_count": 3651},
        {"back_limit_mode": "months", "back_limit_count": 121},
        {"back_limit_mode": "DAYS", "back_limit_count": 1},
        {"back_limit_count": 3},
        {"back_limit_from": date(2026, 10, 1)},
    ],
)
def test_a_back_limit_needs_a_known_mode_and_a_count_in_range(
    attempt: Attempt, fields: dict[str, Any]
) -> None:
    attempt.refused("XC422", "people_back_limit_invalid", **fields)


@pytest.mark.parametrize(
    "fields",
    [
        {"back_limit_mode": "days", "back_limit_count": 0},
        {"back_limit_mode": "days", "back_limit_count": 3650},
        {"back_limit_mode": "months", "back_limit_count": 120},
        {"back_limit_mode": "none"},
        {"back_limit_mode": "none", "back_limit_from": date(2026, 10, 9)},
    ],
)
def test_a_back_limit_inside_the_bounds_is_accepted(
    attempt: Attempt, fields: dict[str, Any]
) -> None:
    assert attempt.accepted(**fields)["outcome"] in ("created", "updated")


def test_a_fixed_date_after_the_business_date_is_refused(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    create_refused(
        app_conn,
        owner,
        "XC422",
        "people_back_limit_date_future",
        back_limit_mode="days",
        back_limit_count=7,
        back_limit_from=date(2026, 10, 10),
    )
    set_organization(owner_conn, owner.org, business_date=date(2026, 9, 30))
    create_refused(
        app_conn,
        owner,
        "XC422",
        "people_back_limit_date_future",
        back_limit_mode="none",
        back_limit_from=date(2026, 10, 1),
    )
    row = create_person(app_conn, owner, back_limit_mode="none", back_limit_from=date(2026, 9, 30))
    assert row["outcome"] == "created"


def test_the_back_limit_rules_come_after_the_role_and_before_the_person(
    app_conn: Conn, owner: Member
) -> None:
    create_refused(
        app_conn,
        owner,
        "XC422",
        "people_role_unknown",
        role="Nobody",
        back_limit_mode="weeks",
    )
    update_refused(
        app_conn,
        owner,
        uuid4(),
        1,
        "XC422",
        "people_back_limit_invalid",
        back_limit_mode="weeks",
    )


def test_a_back_limit_change_is_logged_with_the_access_change(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    jane = create_person(app_conn, owner)
    update_person(
        app_conn,
        owner,
        jane["id"],
        1,
        back_limit_mode="months",
        back_limit_count=1,
        back_limit_from=date(2026, 9, 1),
    )
    entry = change_log(owner_conn, owner.org)[-1]
    assert entry["section"] == "people"
    assert entry["reason"] == "Changed how far back they can change records for Jane Njeri"
    assert entry["before"] == JANE_AFTER
    assert entry["after"] == JANE_AFTER.replace(
        '"BackLimitMode":"days","BackLimitCount":7,"BackLimitFrom":null',
        '"BackLimitMode":"months","BackLimitCount":1,"BackLimitFrom":"2026-09-01"',
    )
    document = _read(app_conn, "people_get", owner, jane["id"])
    assert document["can_change"] == "1 month back, not before 1 September 2026"
    assert user_row(owner_conn, jane["id"])["security_version"] == 0
    same = update_person(
        app_conn,
        owner,
        jane["id"],
        2,
        back_limit_mode="months",
        back_limit_count=1,
        back_limit_from=date(2026, 9, 1),
    )
    assert same["outcome"] == "unchanged"


def test_my_scope_carries_the_actors_limit_and_earliest_date(
    app_conn: Conn, owner_conn: Conn, owner: Member, office: Member
) -> None:
    owner_conn.execute(
        "UPDATE tenancy.memberships SET back_limit_mode = 'days', back_limit_count = 3 "
        "WHERE organization_id = %s AND user_id = %s",
        (office.org, office.id),
    )
    mine = _read(app_conn, "access_my_scope", office)
    assert (mine["can_change"], mine["earliest"]) == ("3 days back", "2026-10-06")
    set_organization(owner_conn, owner.org, business_date=date(2026, 9, 1))
    assert _read(app_conn, "access_my_scope", office)["earliest"] == "2026-08-29"


# --- the hidden organization key ---


def test_only_owners_manage_organization_settings(
    app_conn: Conn, owner: Member, office: Member
) -> None:
    assert _read(app_conn, "organization_settings_get", owner)
    args = [office.id, office.org, REQUEST, T0]
    refused(app_conn, "organization_settings_get", args, "XC403", "permission_missing")


def test_blocking_needs_the_block_right(
    app_conn: Conn, owner_conn: Conn, owner: Member, office: Member, clerk: Member
) -> None:
    jane = create_person(app_conn, owner)
    set_override(owner_conn, office, "people.block", granted=False)
    _set_active_refused(
        app_conn, office, jane["id"], False, 1, "XC403", "permission_missing", "Left"
    )
    set_override(owner_conn, clerk, "people.block")
    set_scope(owner_conn, clerk, clerk.org, all_companies=True)
    assert _set_active(app_conn, clerk, jane["id"], False, 1, "Left")["outcome"] == "updated"
    assert _set_active(app_conn, clerk, jane["id"], True, 2)["outcome"] == "updated"


def _limit(owner_conn: Conn, who: Member, mode: str, count: int | None) -> None:
    owner_conn.execute(
        "UPDATE tenancy.memberships SET back_limit_mode = %s, back_limit_count = %s "
        "WHERE organization_id = %s AND user_id = %s",
        (mode, count, who.org, who.id),
    )


@pytest.mark.parametrize(
    ("fields", "allowed"),
    [
        ({}, False),
        ({"back_limit_mode": "none"}, False),
        ({"back_limit_mode": "months", "back_limit_count": 1}, False),
        ({"back_limit_mode": "days", "back_limit_count": 4}, False),
        ({"back_limit_mode": "none", "back_limit_from": date(2026, 10, 5)}, False),
        ({"back_limit_mode": "days", "back_limit_count": 3}, True),
        ({"back_limit_mode": "days", "back_limit_count": 0}, True),
        ({"back_limit_mode": "none", "back_limit_from": date(2026, 10, 6)}, True),
        (
            {
                "back_limit_mode": "days",
                "back_limit_count": 30,
                "back_limit_from": date(2026, 10, 8),
            },
            True,
        ),
    ],
)
def test_a_limited_editor_cannot_give_a_looser_limit(
    app_conn: Conn, owner_conn: Conn, office: Member, fields: dict[str, Any], allowed: bool
) -> None:
    _limit(owner_conn, office, "days", 3)
    admin = {"role": "Office admin", "permissions": OFFICE_KEYS, **fields}
    if allowed:
        assert create_person(app_conn, office, **admin)["outcome"] == "created"
    else:
        create_refused(app_conn, office, "XC403", "people_back_limit_not_held", **admin)


def test_a_limited_editor_keeps_a_looser_limit_they_do_not_change(
    app_conn: Conn, owner_conn: Conn, owner: Member, office: Member
) -> None:
    jane = create_person(app_conn, owner, back_limit_mode="none")
    _limit(owner_conn, office, "days", 3)
    assert update_person(app_conn, office, jane["id"], 1, last_name="Mwangi")["outcome"] == (
        "updated"
    )
    same = update_person(
        app_conn, office, jane["id"], 2, last_name="Mwangi", back_limit_mode="none"
    )
    assert same["outcome"] == "unchanged"
    update_refused(
        app_conn,
        office,
        jane["id"],
        2,
        "XC403",
        "people_back_limit_not_held",
        last_name="Mwangi",
        back_limit_mode="days",
        back_limit_count=10,
    )
    row = update_person(
        app_conn,
        office,
        jane["id"],
        2,
        last_name="Mwangi",
        back_limit_mode="days",
        back_limit_count=2,
    )
    assert row["outcome"] == "updated"


def test_an_owner_gives_any_limit_whatever_their_own(
    app_conn: Conn, owner_conn: Conn, owner: Member
) -> None:
    _limit(owner_conn, owner, "days", 0)
    assert create_person(app_conn, owner, back_limit_mode="none")["outcome"] == "created"


def test_the_back_limit_grant_rule_comes_after_the_access_rules_and_before_the_contact(
    app_conn: Conn, owner_conn: Conn, office: Member
) -> None:
    _limit(owner_conn, office, "days", 3)
    create_refused(app_conn, office, "XC403", "people_role_not_held", back_limit_mode="none")
    create_refused(
        app_conn,
        office,
        "XC403",
        "people_back_limit_not_held",
        role="Office admin",
        permissions=OFFICE_KEYS,
        email="olive.owner@example.com",
        back_limit_mode="none",
    )
