"""The common and tenancy helpers, called as ``xcode_api_executor`` under row-level security
(``docs/05-routines.md`` sections 2.1 and 6.1)."""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import psycopg
import pytest

from ..support.database import executor_connection
from ..support.fakes import held_permissions, role_permissions, role_rights
from ..support.rows import seed_organization
from ..support.scenario import Account, Conn, provision

ROLE_ORDER = ("Owner", "Office admin", "Fleet manager", "Revenue clerk")


def _scalar(conn: Conn, query: str, params: Any = ()) -> Any:
    row = conn.execute(query, params).fetchone()
    assert row is not None
    return next(iter(row.values()))


def _refusal(conn: Conn, query: str, params: Any = ()) -> psycopg.Error:
    with pytest.raises(psycopg.Error) as caught, conn.transaction():
        conn.execute(query, params)
    return caught.value


@contextmanager
def _inside(conn: Conn, organization_id: UUID) -> Iterator[None]:
    with conn.transaction():
        conn.execute(
            "SELECT set_config('xcode.organization_id', %s, true)", (str(organization_id),)
        )
        yield


@contextmanager
def _entered(
    conn: Conn, actor_id: UUID, organization_id: UUID, permission: str | None = None
) -> Iterator[None]:
    with conn.transaction():
        conn.execute(
            "SELECT tenancy.enter_organization(%s, %s, %s, %s)",
            (actor_id, organization_id, "req-helpers", permission),
        )
        yield


# --- refuse and the input checks ------------------------------------------------------


def test_refuse_raises_the_sqlstate_code_and_json_detail(executor: Conn) -> None:
    error = _refusal(
        executor, "SELECT tenancy.refuse('vehicle_registration_taken', 'XC409', %s::jsonb)",
        ('{"registration": "KDA 482M"}',),
    )  # fmt: skip
    assert error.sqlstate == "XC409"
    assert error.diag.message_primary == "vehicle_registration_taken"
    assert json.loads(error.diag.message_detail or "") == {"registration": "KDA 482M"}


def test_refuse_defaults_to_xc422_with_an_empty_detail(executor: Conn) -> None:
    error = _refusal(executor, "SELECT tenancy.refuse('money_invalid')")
    assert error.sqlstate == "XC422"
    assert json.loads(error.diag.message_detail or "") == {}


@pytest.mark.parametrize(("page", "size"), [(1, 1), (100000, 100), (7, 25)])
def test_check_page_accepts_the_bounds(executor: Conn, page: int, size: int) -> None:
    executor.execute("SELECT tenancy.check_page(%s, %s)", (page, size))


@pytest.mark.parametrize(
    ("page", "size"), [(0, 1), (100001, 1), (1, 0), (1, 101), (None, 10), (1, None), (-1, 10)]
)
def test_check_page_refuses_outside_the_bounds(
    executor: Conn, page: int | None, size: int | None
) -> None:
    error = _refusal(executor, "SELECT tenancy.check_page(%s, %s)", (page, size))
    assert (error.sqlstate, error.diag.message_primary) == ("XC422", "page_out_of_range")


@pytest.mark.parametrize(
    "amount", [Decimal("0.01"), Decimal("1.5"), Decimal("1.500"), Decimal("999999999999.99")]
)
def test_check_money_returns_a_valid_amount(executor: Conn, amount: Decimal) -> None:
    assert _scalar(executor, "SELECT tenancy.check_money(%s)", (amount,)) == amount


@pytest.mark.parametrize(
    "amount",
    [Decimal(0), Decimal(-1), Decimal("1.005"), Decimal("1000000000000"), None],
)
def test_check_money_refuses_without_rounding(executor: Conn, amount: Decimal | None) -> None:
    error = _refusal(executor, "SELECT tenancy.check_money(%s)", (amount,))
    assert (error.sqlstate, error.diag.message_primary) == ("XC422", "money_invalid")


def test_check_money_raises_the_callers_code(executor: Conn) -> None:
    error = _refusal(executor, "SELECT tenancy.check_money(0, 'pettycash_line_amount')")
    assert error.diag.message_primary == "pettycash_line_amount"


@pytest.mark.parametrize(
    ("typed", "expected"),
    [
        (None, None),
        ("", None),
        ("   ", None),
        ("\u00a0 Moved \u3000", "Moved"),
        ("  Tighten lockout after audit  ", "Tighten lockout after audit"),
        ("x" * 500, "x" * 500),
    ],
)
def test_check_typed_reason_trims_and_treats_blank_as_none(
    executor: Conn, typed: str | None, expected: str | None
) -> None:
    assert _scalar(executor, "SELECT tenancy.check_typed_reason(%s)", (typed,)) == expected


def test_check_typed_reason_refuses_more_than_500_characters(executor: Conn) -> None:
    error = _refusal(executor, "SELECT tenancy.check_typed_reason(%s)", ("x" * 501,))
    assert (error.sqlstate, error.diag.message_primary) == ("XC422", "reason_length")


# --- reasons and formatting -------------------------------------------------------------


@pytest.mark.parametrize(
    ("automatic", "typed", "expected"),
    [
        ("Removed access for Grace Achieng", None, "Removed access for Grace Achieng"),
        ("Removed access for Grace Achieng", "", "Removed access for Grace Achieng"),
        (
            "Removed access for Grace Achieng",
            "Moved to another SACCO",
            "Removed access for Grace Achieng. Reason: Moved to another SACCO.",
        ),
        (
            "Vehicle KDA 482M left the fleet on 2026-10-09",
            "Sold to the SACCO.",
            "Vehicle KDA 482M left the fleet on 2026-10-09. Reason: Sold to the SACCO.",
        ),
        ("Removed the logo", "Is it withdrawn?", "Removed the logo. Reason: Is it withdrawn?"),
        ("Removed the logo", "Withdrawn!", "Removed the logo. Reason: Withdrawn!"),
        (
            "Added company North Star",
            "Signed with the SACCO",
            "Added company North Star. Reason: Signed with the SACCO.",
        ),
    ],
)
def test_compose_reason_follows_the_automatic_text(
    executor: Conn, automatic: str, typed: str | None, expected: str
) -> None:
    assert (
        _scalar(executor, "SELECT tenancy.compose_reason(%s, %s)", (automatic, typed)) == expected
    )


def test_compose_reason_shortens_the_automatic_part_first(executor: Conn) -> None:
    automatic = "a" * 400
    typed = "t" * 300
    result = _scalar(executor, "SELECT tenancy.compose_reason(%s, %s)", (automatic, typed))
    assert len(result) == 500
    assert result.endswith("... Reason: " + typed + ".")
    assert result == "a" * 186 + "..." + ". Reason: " + typed + "."


def test_compose_reason_keeps_100_automatic_characters_then_clips(executor: Conn) -> None:
    automatic = "a" * 300
    typed = "t" * 500
    result = _scalar(executor, "SELECT tenancy.compose_reason(%s, %s)", (automatic, typed))
    assert len(result) == 500
    assert result.startswith("a" * 97 + ".... Reason: ")
    assert result.endswith("...")


def test_compose_reason_with_a_500_character_reason_is_still_500(executor: Conn) -> None:
    result = _scalar(
        executor, "SELECT tenancy.compose_reason(%s, %s)", ("Removed the logo", "r" * 500)
    )
    assert len(result) == 500
    assert result.startswith("Removed the logo. Reason: r")
    assert result.endswith("r...")


@pytest.mark.parametrize("typed", [None, ""])
def test_compose_reason_clips_a_long_automatic_reason_without_a_typed_one(
    executor: Conn, typed: str | None
) -> None:
    automatic = "a" * 520
    result = _scalar(executor, "SELECT tenancy.compose_reason(%s, %s)", (automatic, typed))
    assert result == "a" * 497 + "..."
    exact = _scalar(executor, "SELECT tenancy.compose_reason(%s, %s)", ("b" * 500, typed))
    assert exact == "b" * 500


@pytest.mark.parametrize(
    ("parts", "expected"),
    [
        (["amount"], "amount"),
        (["amount", "vehicles"], "amount and vehicles"),
        (["type", "amount", "vehicles"], "type, amount and vehicles"),
        (["name", "bucket", "amount", "note"], "name, bucket, amount and note"),
        (["a", None, "b"], "a and b"),
        ([], None),
        (None, None),
    ],
)
def test_join_words(executor: Conn, parts: list[str | None] | None, expected: str | None) -> None:
    assert _scalar(executor, "SELECT tenancy.join_words(%s::text[])", (parts,)) == expected


@pytest.mark.parametrize(
    ("amount", "expected"),
    [
        (Decimal(21000), "21,000"),
        (Decimal("1500.5"), "1,500.50"),
        (Decimal("0.5"), "0.50"),
        (Decimal("999999999999.99"), "999,999,999,999.99"),
        (Decimal("15000.00"), "15,000"),
        (Decimal(5), "5"),
    ],
)
def test_fmt_money(executor: Conn, amount: Decimal, expected: str) -> None:
    assert _scalar(executor, "SELECT tenancy.fmt_money(%s)", (amount,)) == expected


def test_fmt_day_and_fmt_iso(executor: Conn) -> None:
    assert _scalar(executor, "SELECT tenancy.fmt_day(%s)", (date(2026, 10, 8),)) == "8 Oct 2026"
    assert _scalar(executor, "SELECT tenancy.fmt_day(%s)", (date(2026, 1, 31),)) == "31 Jan 2026"
    assert _scalar(executor, "SELECT tenancy.fmt_iso(%s)", (date(2026, 10, 8),)) == "2026-10-08"


@pytest.mark.parametrize(
    ("key", "word"),
    [
        ("name", "the organization name"),
        ("hour12", "the 12-hour clock"),
        ("useGrouping", "digit grouping"),
        ("use_grouping", "digit grouping"),
        ("firstDayOfWeek", "the first day of the week"),
        ("lockoutThreshold", "the wrong PIN tries before a pause"),
        ("allowHour12Override", "personal clock formats"),
        ("allow_hour12_override", "personal clock formats"),
        ("primary", "the primary colour"),
        ("timeZone", "the time zone"),
        ("time_zone", "the time zone"),
        ("legalName", "the legal name"),
        ("displayName", "the display name"),
        ("organizationId", None),
        ("organization_id", None),
    ],
)
def test_setting_word(executor: Conn, key: str, word: str | None) -> None:
    assert _scalar(executor, "SELECT tenancy.setting_word(%s)", (key,)) == word


@pytest.mark.parametrize(
    ("key", "value", "text"),
    [
        ("useGrouping", "false", "off"),
        ("hour12", "true", "on"),
        ("domain", "null", "none"),
        ("firstDayOfWeek", "0", "Sunday"),
        ("first_day_of_week", "6", "Saturday"),
        ("currency", '"USD"', "USD"),
        ("lockoutThreshold", "3", "3"),
    ],
)
def test_setting_value(executor: Conn, key: str, value: str, text: str) -> None:
    assert _scalar(executor, "SELECT tenancy.setting_value(%s, %s::jsonb)", (key, value)) == text


# --- entering an organization -------------------------------------------------------------


def test_enter_organization_settings_are_transaction_local(
    executor: Conn, account: Account
) -> None:
    with _entered(executor, account.user_id, account.organization_id):
        inside = _scalar(executor, "SELECT tenancy.current_organization()")
        actor = _scalar(executor, "SELECT tenancy.current_actor()")
        request = _scalar(executor, "SELECT tenancy.current_request()")
    assert (inside, actor, request) == (account.organization_id, account.user_id, "req-helpers")
    assert _scalar(executor, "SELECT tenancy.current_organization()") is None
    assert _scalar(executor, "SELECT tenancy.current_actor()") is None
    assert _scalar(executor, "SELECT tenancy.current_request()") is None


def test_enter_organization_refuses_a_member_of_another_organization(
    executor: Conn, owner_conn: Conn
) -> None:
    first = seed_organization(owner_conn)
    second = seed_organization(owner_conn)
    error = _refusal(
        executor,
        "SELECT tenancy.enter_organization(%s, %s, 'req', NULL)",
        (second.user, first.org),
    )
    assert (error.sqlstate, error.diag.message_primary) == ("XC403", "not_member")


def test_enter_organization_refuses_an_inactive_membership(
    executor: Conn, owner_conn: Conn, account: Account
) -> None:
    owner_conn.execute(
        "UPDATE tenancy.memberships SET active = false WHERE user_id = %s", (account.user_id,)
    )
    error = _refusal(
        executor,
        "SELECT tenancy.enter_organization(%s, %s, 'req', NULL)",
        (account.user_id, account.organization_id),
    )
    assert (error.sqlstate, error.diag.message_primary) == ("XC403", "not_member")


def test_enter_organization_refuses_a_missing_permission(
    executor: Conn, operator_conn: Conn
) -> None:
    clerk = provision(operator_conn, email="clerk@example.com", role="Revenue clerk")
    error = _refusal(
        executor,
        "SELECT tenancy.enter_organization(%s, %s, 'req', 'people.manage')",
        (clerk["user_id"], clerk["organization_id"]),
    )
    assert (error.sqlstate, error.diag.message_primary) == ("XC403", "permission_missing")
    with _entered(executor, clerk["user_id"], clerk["organization_id"], "revenue.capture"):
        pass


def test_require_permission_has_permission_and_require_any(
    executor: Conn, operator_conn: Conn
) -> None:
    clerk = provision(operator_conn, email="clerk@example.com", role="Revenue clerk")
    with _entered(executor, clerk["user_id"], clerk["organization_id"]):
        assert _scalar(executor, "SELECT tenancy.has_permission('revenue.capture')") is True
        assert _scalar(executor, "SELECT tenancy.has_permission('people.view')") is False
        executor.execute("SELECT tenancy.require_permission('revenue.view')")
        executor.execute(
            "SELECT tenancy.require_any_permission('{people.view,revenue.capture}'::text[])"
        )
    for query in (
        "SELECT tenancy.require_permission('people.view')",
        "SELECT tenancy.require_any_permission('{people.view,vehicles.manage}'::text[])",
    ):
        with (
            pytest.raises(psycopg.Error) as caught,
            _entered(executor, clerk["user_id"], clerk["organization_id"]),
        ):
            executor.execute(query)
        assert (caught.value.sqlstate, caught.value.diag.message_primary) == (
            "XC403",
            "permission_missing",
        )


# --- the permission resolver ------------------------------------------------------------


def _catalogue(owner: Conn) -> list[str]:
    rows = owner.execute(
        "SELECT key FROM tenancy.permissions ORDER BY group_order, item_order"
    ).fetchall()
    return [str(r["key"]) for r in rows]


def _resolve(executor: Conn, organization_id: Any, user_id: Any) -> list[str]:
    with _inside(executor, organization_id):
        value = _scalar(
            executor,
            "SELECT tenancy.effective_permissions(%s, %s)",
            (organization_id, user_id),
        )
    return list(value)


def _override(owner: Conn, person: dict[str, Any], permission: str, granted: bool) -> None:
    owner.execute(
        "INSERT INTO tenancy.permission_overrides (organization_id, user_id, permission, granted) "
        "VALUES (%s, %s, %s, %s)",
        (person["organization_id"], person["user_id"], permission, granted),
    )


@pytest.mark.parametrize("role", ROLE_ORDER)
def test_resolver_expands_each_roles_defaults(
    executor: Conn, operator_conn: Conn, owner_conn: Conn, role: str
) -> None:
    person = provision(operator_conn, email="person@example.com", role=role)
    resolved = _resolve(executor, person["organization_id"], person["user_id"])
    catalogue = _catalogue(owner_conn)
    assert resolved == [key for key in catalogue if key in resolved], "catalogue order"
    assert resolved == list(role_permissions(role))
    assert len(resolved) == {"Owner": 77, "Office admin": 53, "Fleet manager": 18}.get(role, 5)


def test_legacy_keys_are_derived_never_granted(
    executor: Conn, operator_conn: Conn, owner_conn: Conn
) -> None:
    clerk = provision(operator_conn, email="clerk@example.com", role="Revenue clerk")
    org, user = clerk["organization_id"], clerk["user_id"]
    assert _resolve(executor, org, user) == [
        "dash.gaps",
        "revenue.view",
        "revenue.capture",
        "dash.capture",
        "revenue.no_earnings",
    ]
    stored = owner_conn.execute(
        "SELECT count(*) AS n FROM tenancy.permission_overrides o "
        "JOIN tenancy.permissions p ON p.key = o.permission WHERE NOT p.catalogue"
    ).fetchone()
    assert stored == {"n": 0}
    _override(owner_conn, clerk, "dash.gaps", False)
    assert _resolve(executor, org, user) == [
        "revenue.view",
        "revenue.capture",
        "revenue.no_earnings",
    ]


def test_a_retired_key_needs_only_one_of_its_sources(
    executor: Conn, operator_conn: Conn, owner_conn: Conn
) -> None:
    clerk = provision(operator_conn, email="clerk@example.com", role="Revenue clerk")
    _override(owner_conn, clerk, "revenue.capture", False)
    resolved = _resolve(executor, clerk["organization_id"], clerk["user_id"])
    assert "revenue.no_earnings" not in resolved
    _override(owner_conn, clerk, "revenue.correct", True)
    resolved = _resolve(executor, clerk["organization_id"], clerk["user_id"])
    assert "revenue.no_earnings" in resolved


def test_resolver_adds_a_grant_with_its_dependencies(
    executor: Conn, operator_conn: Conn, owner_conn: Conn
) -> None:
    clerk = provision(operator_conn, email="clerk@example.com", role="Revenue clerk")
    _override(owner_conn, clerk, "people.edit", True)
    resolved = _resolve(executor, clerk["organization_id"], clerk["user_id"])
    rights = [*role_rights("Revenue clerk"), "people.view", "people.edit"]
    assert resolved == list(held_permissions(rights, "Revenue clerk"))
    assert {"access.manage", "people.manage"} <= set(resolved)


def test_resolver_deny_prunes_every_dependant(
    executor: Conn, operator_conn: Conn, owner_conn: Conn
) -> None:
    owner = provision(operator_conn, email="owner@example.com", role="Owner")
    _override(owner_conn, owner, "revenue.view", False)
    resolved = _resolve(executor, owner["organization_id"], owner["user_id"])
    removed = {"revenue.view", "revenue.capture", "revenue.correct", "revenue.export"}
    removed |= {"dash.net", "dash.gaps"}
    kept = [key for key in role_rights("Owner") if key not in removed]
    assert resolved == list(held_permissions(kept, "Owner"))
    assert not {"dash.capture", "dash.revenue", "revenue.no_earnings"} & set(resolved)
    assert "organization.manage" in resolved


def test_resolver_deny_of_a_dependency_prunes_a_grant(
    executor: Conn, operator_conn: Conn, owner_conn: Conn
) -> None:
    clerk = provision(operator_conn, email="clerk@example.com", role="Revenue clerk")
    _override(owner_conn, clerk, "people.edit", True)
    _override(owner_conn, clerk, "people.view", False)
    resolved = _resolve(executor, clerk["organization_id"], clerk["user_id"])
    assert resolved == list(role_permissions("Revenue clerk"))


def test_only_owners_hold_the_hidden_organization_key(executor: Conn, operator_conn: Conn) -> None:
    holders = []
    for slot, role in enumerate(ROLE_ORDER):
        person = provision(
            operator_conn, email=f"person{slot}@example.com", phone=f"072200000{slot}", role=role
        )
        if "organization.manage" in _resolve(
            executor, person["organization_id"], person["user_id"]
        ):
            holders.append(role)
    assert holders == ["Owner"]


def test_resolver_gives_nothing_to_an_inactive_membership(
    executor: Conn, operator_conn: Conn, owner_conn: Conn
) -> None:
    owner = provision(operator_conn, email="owner@example.com", role="Owner")
    owner_conn.execute(
        "UPDATE tenancy.memberships SET active = false WHERE user_id = %s", (owner["user_id"],)
    )
    assert _resolve(executor, owner["organization_id"], owner["user_id"]) == []


def test_resolver_sees_nothing_outside_the_entered_organization(
    executor: Conn, owner_conn: Conn
) -> None:
    first = seed_organization(owner_conn)
    second = seed_organization(owner_conn)
    with _inside(executor, second.org):
        value = _scalar(
            executor, "SELECT tenancy.effective_permissions(%s, %s)", (first.org, first.user)
        )
    assert value == []


# --- scope ------------------------------------------------------------------------------


def test_actor_scope_and_scope_mode(executor: Conn, owner_conn: Conn) -> None:
    org = seed_organization(owner_conn)
    with _entered(executor, org.user, org.org):
        scope = _scalar(executor, "SELECT row_to_json(tenancy.actor_scope())")
        owner_mode = _scalar(executor, "SELECT tenancy.scope_mode(%s, %s)", (org.org, org.user))
        clerk_mode = _scalar(executor, "SELECT tenancy.scope_mode(%s, %s)", (org.org, org.user2))
    assert scope == {"all_companies": True, "company_ids": [], "vehicle_ids": []}
    assert (owner_mode, clerk_mode) == ("all", "companies")

    owner_conn.execute("DELETE FROM tenancy.data_scope_companies WHERE user_id = %s", (org.user2,))
    with _inside(executor, org.org):
        assert (
            _scalar(executor, "SELECT tenancy.scope_mode(%s, %s)", (org.org, org.user2))
            == "vehicles"
        )


def test_people_visible_follows_the_viewers_reach(executor: Conn, owner_conn: Conn) -> None:
    org = seed_organization(owner_conn)
    with _inside(executor, org.org):
        by_owner = {
            r["v"]
            for r in executor.execute(
                "SELECT tenancy.people_visible(%s) AS v", (org.user,)
            ).fetchall()
        }
        by_clerk = {
            r["v"]
            for r in executor.execute(
                "SELECT tenancy.people_visible(%s) AS v", (org.user2,)
            ).fetchall()
        }
    assert by_owner == {org.user, org.user2}
    # The clerk's company scope reaches nobody else's scope: the owner has the all-companies row.
    assert by_clerk == {org.user2}


# --- dates and zones ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("zone", "now", "expected"),
    [
        ("Africa/Nairobi", datetime(2026, 10, 8, 20, 59, 59, tzinfo=UTC), date(2026, 10, 8)),
        ("Africa/Nairobi", datetime(2026, 10, 8, 21, 0, 0, tzinfo=UTC), date(2026, 10, 9)),
        ("America/New_York", datetime(2026, 10, 9, 3, 59, 59, tzinfo=UTC), date(2026, 10, 8)),
        ("America/New_York", datetime(2026, 10, 9, 4, 0, 0, tzinfo=UTC), date(2026, 10, 9)),
    ],
)
def test_business_date_without_a_held_date_follows_the_zone_midnight(
    executor: Conn, owner_conn: Conn, account: Account, zone: str, now: datetime, expected: date
) -> None:
    owner_conn.execute(
        "UPDATE tenancy.organization_localizations SET time_zone = %s WHERE organization_id = %s",
        (zone, account.organization_id),
    )
    with _inside(executor, account.organization_id):
        business = _scalar(
            executor, "SELECT tenancy.business_date(%s, %s)", (account.organization_id, now)
        )
        calendar = _scalar(
            executor, "SELECT tenancy.calendar_date(%s, %s)", (account.organization_id, now)
        )
    assert business == expected
    assert calendar == expected


def test_business_date_prefers_the_held_date(
    executor: Conn, owner_conn: Conn, account: Account
) -> None:
    owner_conn.execute(
        "UPDATE tenancy.organizations SET business_date = DATE '2026-10-01' WHERE id = %s",
        (account.organization_id,),
    )
    now = datetime(2026, 10, 9, 12, 0, tzinfo=UTC)
    with _inside(executor, account.organization_id):
        business = _scalar(
            executor, "SELECT tenancy.business_date(%s, %s)", (account.organization_id, now)
        )
        calendar = _scalar(
            executor, "SELECT tenancy.calendar_date(%s, %s)", (account.organization_id, now)
        )
    assert (business, calendar) == (date(2026, 10, 1), date(2026, 10, 9))


def test_a_stored_unknown_zone_is_refused_on_read(
    executor: Conn, owner_conn: Conn, account: Account
) -> None:
    owner_conn.execute(
        "UPDATE tenancy.organization_localizations SET time_zone = 'Mars/Olympus' "
        "WHERE organization_id = %s",
        (account.organization_id,),
    )
    with pytest.raises(psycopg.Error) as caught, _inside(executor, account.organization_id):
        executor.execute(
            "SELECT tenancy.business_date(%s, %s)",
            (account.organization_id, datetime(2026, 10, 9, tzinfo=UTC)),
        )
    assert (caught.value.sqlstate, caught.value.diag.message_primary) == (
        "XC422",
        "time_zone_invalid",
    )
    assert json.loads(caught.value.diag.message_detail or "") == {"value": "Mars/Olympus"}


@pytest.mark.parametrize("name", ["Africa/Nairobi", "UTC", "America/New_York"])
def test_check_time_zone_accepts_iana_names(executor: Conn, name: str) -> None:
    assert _scalar(executor, "SELECT tenancy.check_time_zone(%s)", (name,)) == name


@pytest.mark.parametrize("name", ["Nairobi", "africa/nairobi", "EAT", "UTC+3", "", None])
def test_check_time_zone_refuses_anything_else(executor: Conn, name: str | None) -> None:
    error = _refusal(executor, "SELECT tenancy.check_time_zone(%s)", (name,))
    assert (error.sqlstate, error.diag.message_primary) == ("XC422", "time_zone_invalid")
    assert json.loads(error.diag.message_detail or "") == {"value": name}


# --- the change log -----------------------------------------------------------------------


def _record(conn: Conn, section: str, entity: UUID, reason: str) -> int:
    return int(
        _scalar(
            conn,
            "SELECT tenancy.record_change(%s, %s, NULL, 'null'::json, %s::json, %s, "
            "'setup.companies', %s, NULL, %s::jsonb, %s)",
            (
                section,
                entity,
                '{"Name": "North"}',
                reason,
                f"company:{entity}",
                '{"Name": "North"}',
                datetime(2026, 10, 9, 8, 0, tzinfo=UTC),
            ),
        )
    )


def test_record_change_returns_consecutive_versions_and_writes_both_rows(
    executor: Conn, owner_conn: Conn, account: Account
) -> None:
    start = _scalar(
        owner_conn,
        "SELECT settings_version FROM tenancy.organizations WHERE id = %s",
        (account.organization_id,),
    )
    entity = account.user_id
    with _entered(executor, account.user_id, account.organization_id):
        first = _record(executor, "companies", entity, "Added company North")
        second = _record(executor, "companies", entity, "Renamed company North to North Star")
    assert (first, second) == (start + 1, start + 2)
    log = owner_conn.execute(
        "SELECT version, section, actor_id, reason, before, after, request_id "
        "FROM tenancy.change_log WHERE organization_id = %s ORDER BY version",
        (account.organization_id,),
    ).fetchall()
    assert [r["version"] for r in log] == [first, second]
    assert log[0]["before"] == "null"
    assert log[0]["after"] == '{"Name": "North"}'
    assert {r["request_id"] for r in log} == {"req-helpers"}
    assert {r["actor_id"] for r in log} == {account.user_id}
    audit = owner_conn.execute(
        "SELECT action, actor_id, request_id FROM tenancy.audit_events WHERE organization_id = %s",
        (account.organization_id,),
    ).fetchall()
    assert len(audit) == 2
    assert {(r["action"], r["actor_id"], r["request_id"]) for r in audit} == {
        ("setup.companies", account.user_id, "req-helpers")
    }


def test_record_change_refuses_without_an_actor(executor: Conn, account: Account) -> None:
    with pytest.raises(psycopg.Error) as caught, executor.transaction():
        executor.execute(
            "SELECT tenancy.enter_organization_as_operator(%s)", (account.organization_id,)
        )
        _record(executor, "companies", account.user_id, "Added company North")
    assert (caught.value.sqlstate, caught.value.diag.message_primary) == ("XC403", "not_member")


def test_two_concurrent_writers_get_distinct_versions(
    owner_url: str, owner_conn: Conn, account: Account
) -> None:
    start = _scalar(
        owner_conn,
        "SELECT settings_version FROM tenancy.organizations WHERE id = %s",
        (account.organization_id,),
    )
    results: dict[str, int] = {}
    second_started = threading.Event()
    with executor_connection(owner_url) as first, executor_connection(owner_url) as second:

        def second_writer() -> None:
            with second.transaction():
                second.execute(
                    "SELECT tenancy.enter_organization(%s, %s, 'req-second', NULL)",
                    (account.user_id, account.organization_id),
                )
                second_started.set()
                results["second"] = _record(second, "companies", account.user_id, "Second")

        with first.transaction():
            first.execute(
                "SELECT tenancy.enter_organization(%s, %s, 'req-first', NULL)",
                (account.user_id, account.organization_id),
            )
            results["first"] = _record(first, "companies", account.user_id, "First")
            worker = threading.Thread(target=second_writer)
            worker.start()
            assert second_started.wait(10)
            # The second writer now queues on the organization row until this one commits.
            worker.join(0.5)
            assert worker.is_alive()
        worker.join(10)
    assert results == {"first": start + 1, "second": start + 2}


def test_seed_roles_inserts_the_four_catalog_roles_once(
    executor: Conn, owner_conn: Conn, account: Account
) -> None:
    with _inside(executor, account.organization_id):
        executor.execute("SELECT tenancy.seed_roles(%s)", (account.organization_id,))
        executor.execute("SELECT tenancy.seed_roles(%s)", (account.organization_id,))
    names = owner_conn.execute(
        "SELECT name FROM tenancy.roles WHERE organization_id = %s ORDER BY created_at, name",
        (account.organization_id,),
    ).fetchall()
    assert sorted(r["name"] for r in names) == sorted(ROLE_ORDER)


def test_a_denied_legacy_key_stays_off_though_its_source_is_held(
    executor: Conn, operator_conn: Conn, owner_conn: Conn
) -> None:
    clerk = provision(operator_conn, email="clerk@example.com", role="Revenue clerk")
    _override(owner_conn, clerk, "revenue.no_earnings", False)
    resolved = _resolve(executor, clerk["organization_id"], clerk["user_id"])
    assert resolved == ["dash.gaps", "revenue.view", "revenue.capture", "dash.capture"]
