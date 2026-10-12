"""How far back a person may change records (``docs/05-routines.md`` section 10.2):
``tenancy.earliest_writable``, ``tenancy.check_writable`` and ``tenancy.back_limit_words``,
called as ``xcode_api_executor`` under row-level security."""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

import psycopg
import pytest

from ..support.scenario import Conn, provision
from ..support.tenancy import set_localization, set_organization

REQUEST = "req-back-limit"


@pytest.fixture
def person(operator_conn: Conn) -> dict[str, Any]:
    return provision(operator_conn, email="clerk@example.com", role="Revenue clerk")


def _limit(
    owner: Conn, person: dict[str, Any], mode: str, count: int | None, since: date | None
) -> None:
    owner.execute(
        "UPDATE tenancy.memberships SET back_limit_mode = %s, back_limit_count = %s, "
        "back_limit_from = %s WHERE organization_id = %s AND user_id = %s",
        (mode, count, since, person["organization_id"], person["user_id"]),
    )


@contextmanager
def _entered(executor: Conn, person: dict[str, Any]) -> Iterator[None]:
    with executor.transaction():
        executor.execute(
            "SELECT tenancy.enter_organization(%s, %s, %s, NULL)",
            (person["user_id"], person["organization_id"], REQUEST),
        )
        yield


def _earliest(executor: Conn, person: dict[str, Any], today: date) -> date | None:
    with _entered(executor, person):
        row = executor.execute(
            "SELECT tenancy.earliest_writable(%s, %s, %s) AS d",
            (person["organization_id"], person["user_id"], today),
        ).fetchone()
    assert row is not None
    value: date | None = row["d"]
    return value


def _writable(executor: Conn, person: dict[str, Any], day: date, as_of: datetime) -> str | None:
    """``None`` when the write may go ahead, else the earliest date the refusal names."""
    try:
        with _entered(executor, person):
            executor.execute("SELECT tenancy.check_writable(%s, %s)", (day, as_of))
    except psycopg.Error as error:
        assert error.sqlstate == "XC422"
        assert error.diag.message_primary == "record_too_old"
        earliest: str = json.loads(error.diag.message_detail or "")["earliest"]
        return earliest
    return None


@pytest.mark.parametrize(
    ("mode", "count", "since", "today", "expected"),
    [
        ("none", None, None, date(2026, 10, 9), None),
        ("days", 0, None, date(2026, 10, 9), date(2026, 10, 9)),
        ("days", 7, None, date(2026, 10, 9), date(2026, 10, 2)),
        ("days", 1, None, date(2026, 3, 1), date(2026, 2, 28)),
        ("days", 1, None, date(2024, 3, 1), date(2024, 2, 29)),
        ("days", 3650, None, date(2026, 10, 9), date(2016, 10, 11)),
        ("months", 0, None, date(2026, 10, 9), date(2026, 10, 9)),
        ("months", 1, None, date(2026, 3, 31), date(2026, 2, 28)),
        ("months", 1, None, date(2024, 3, 31), date(2024, 2, 29)),
        ("months", 1, None, date(2026, 5, 31), date(2026, 4, 30)),
        ("months", 1, None, date(2026, 1, 31), date(2025, 12, 31)),
        ("months", 1, None, date(2026, 6, 30), date(2026, 5, 30)),
        ("months", 12, None, date(2024, 2, 29), date(2023, 2, 28)),
        ("months", 120, None, date(2026, 10, 9), date(2016, 10, 9)),
        ("none", None, date(2026, 9, 1), date(2026, 10, 9), date(2026, 9, 1)),
        ("days", 7, date(2026, 10, 5), date(2026, 10, 9), date(2026, 10, 5)),
        ("days", 7, date(2026, 9, 1), date(2026, 10, 9), date(2026, 10, 2)),
        ("months", 1, date(2026, 3, 1), date(2026, 3, 31), date(2026, 3, 1)),
        ("days", 0, date(2026, 10, 9), date(2026, 10, 9), date(2026, 10, 9)),
    ],
)
def test_earliest_writable(
    executor: Conn,
    owner_conn: Conn,
    person: dict[str, Any],
    mode: str,
    count: int | None,
    since: date | None,
    today: date,
    expected: date | None,
) -> None:
    _limit(owner_conn, person, mode, count, since)
    assert _earliest(executor, person, today) == expected


def test_earliest_writable_of_someone_outside_the_organization_is_null(
    executor: Conn, owner_conn: Conn, person: dict[str, Any], operator_conn: Conn
) -> None:
    _limit(owner_conn, person, "days", 0, None)
    with _entered(executor, person):
        row = executor.execute(
            "SELECT tenancy.earliest_writable(%s, %s, %s) AS d",
            (person["organization_id"], UUID(int=1), date(2026, 10, 9)),
        ).fetchone()
    assert row == {"d": None}


def test_the_limit_turns_at_midnight_in_the_organization_zone(
    executor: Conn, owner_conn: Conn, person: dict[str, Any]
) -> None:
    _limit(owner_conn, person, "days", 0, None)
    last_second = datetime(2026, 10, 9, 20, 59, 59, tzinfo=UTC)
    midnight = datetime(2026, 10, 9, 21, 0, 0, tzinfo=UTC)
    assert _writable(executor, person, date(2026, 10, 9), last_second) is None
    assert _writable(executor, person, date(2026, 10, 8), last_second) == "2026-10-09"
    assert _writable(executor, person, date(2026, 10, 9), midnight) == "2026-10-10"
    assert _writable(executor, person, date(2026, 10, 10), midnight) is None
    set_localization(owner_conn, person["organization_id"], time_zone="America/New_York")
    assert _writable(executor, person, date(2026, 10, 9), midnight) is None


def test_a_month_back_from_a_month_end_is_the_last_day_of_the_shorter_month(
    executor: Conn, owner_conn: Conn, person: dict[str, Any]
) -> None:
    _limit(owner_conn, person, "months", 1, None)
    as_of = datetime(2026, 3, 31, 9, 0, tzinfo=UTC)
    assert _writable(executor, person, date(2026, 2, 28), as_of) is None
    assert _writable(executor, person, date(2026, 2, 27), as_of) == "2026-02-28"


def test_a_fixed_date_later_than_the_rolling_limit_wins(
    executor: Conn, owner_conn: Conn, person: dict[str, Any]
) -> None:
    _limit(owner_conn, person, "days", 30, date(2026, 10, 1))
    as_of = datetime(2026, 10, 9, 9, 0, tzinfo=UTC)
    assert _writable(executor, person, date(2026, 9, 30), as_of) == "2026-10-01"
    assert _writable(executor, person, date(2026, 10, 1), as_of) is None


def test_a_held_business_date_moves_the_limit(
    executor: Conn, owner_conn: Conn, person: dict[str, Any]
) -> None:
    _limit(owner_conn, person, "days", 7, None)
    set_organization(owner_conn, person["organization_id"], business_date=date(2026, 9, 1))
    as_of = datetime(2026, 10, 9, 9, 0, tzinfo=UTC)
    assert _writable(executor, person, date(2026, 8, 24), as_of) == "2026-08-25"
    assert _writable(executor, person, date(2026, 8, 25), as_of) is None


def test_no_limit_writes_any_date(executor: Conn, owner_conn: Conn, person: dict[str, Any]) -> None:
    _limit(owner_conn, person, "none", None, None)
    as_of = datetime(2026, 10, 9, 9, 0, tzinfo=UTC)
    assert _writable(executor, person, date(1990, 1, 1), as_of) is None


@pytest.mark.parametrize(
    ("mode", "count", "since", "words"),
    [
        ("none", None, None, "Any date"),
        ("days", 0, None, "Today only"),
        ("months", 0, None, "Today only"),
        ("days", 1, None, "1 day back"),
        ("days", 7, None, "7 days back"),
        ("months", 1, None, "1 month back"),
        ("months", 3, None, "3 months back"),
        ("days", 7, date(2026, 9, 1), "7 days back, not before 1 September 2026"),
        ("days", 0, date(2026, 10, 9), "Today only, not before 9 October 2026"),
        ("none", None, date(2026, 1, 5), "Not before 5 January 2026"),
    ],
)
def test_can_change_words(
    executor: Conn, mode: str, count: int | None, since: date | None, words: str
) -> None:
    row = executor.execute(
        "SELECT tenancy.back_limit_words(%s, %s, %s) AS w", (mode, count, since)
    ).fetchone()
    assert row == {"w": words}


@pytest.mark.parametrize(
    ("mode", "count", "since", "today", "expected"),
    [
        ("none", None, None, date(2026, 10, 9), None),
        ("days", 3, None, date(2026, 10, 9), date(2026, 10, 6)),
        ("months", 1, None, date(2026, 3, 31), date(2026, 2, 28)),
        ("days", 3, date(2026, 10, 8), date(2026, 10, 9), date(2026, 10, 8)),
        ("none", None, date(2026, 9, 1), date(2026, 10, 9), date(2026, 9, 1)),
    ],
)
def test_back_limit_earliest_is_the_rule_of_the_membership_helper(
    executor: Conn,
    mode: str,
    count: int | None,
    since: date | None,
    today: date,
    expected: date | None,
) -> None:
    row = executor.execute(
        "SELECT tenancy.back_limit_earliest(%s, %s, %s, %s) AS d", (mode, count, since, today)
    ).fetchone()
    assert row == {"d": expected}
