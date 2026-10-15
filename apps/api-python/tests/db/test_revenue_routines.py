"""The revenue routines (``api.revenue_capture``, ``api.revenue_week_get``,
``api.revenue_dashboard_get``), called as ``xcode_app``: the capture's steps in order, one
case each (the first failing step answers), identical replays whatever the version and the
date, the writes with their change-log and audit rows, two saves racing on two connections,
the week grid's figures, range and paging, and the dashboard cards per permission and period;
the low-day rule, the gap to target, the search and the back-dating limit.

The business date is 9 Oct 2026 (a Friday; weeks start on Monday), the date of ``T0`` in
Nairobi. Calls that write in sequence advance the clock a minute each, as requests do.
Vehicles, targets, away periods and the history a test needs before its first call are
inserted as ``xcode_owner``. The yard's low-day threshold is 100, so the small amounts of the
step cases are ordinary days; the low-day tests set the default of 4,000."""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

import psycopg
import pytest
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ..support.rows import seed_organization
from ..support.scenario import T0, Conn
from ..support.setup_rows import add_away, add_record, add_target, change_rows, read, refuses, run
from ..support.tenancy import (
    REQUEST,
    Member,
    add_company,
    add_vehicle,
    audit_events,
    provision_member,
    refused,
    set_localization,
    set_override,
    set_scope,
    settings_version,
)

TODAY = date(2026, 10, 9)
WEEK = date(2026, 10, 5)
OCT1 = date(2026, 10, 1)


def at(minutes: int) -> datetime:
    return T0 + timedelta(minutes=minutes)


@dataclass(frozen=True, slots=True)
class Yard:
    owner: Member
    clerk: Member
    admin: Member
    north: UUID
    south: UUID
    kda: UUID
    kdb: UUID
    kdc: UUID


@pytest.fixture
def yard(operator_conn: Conn, owner_conn: Conn) -> Yard:
    """KDA 482M and KDB 111A of North Star, KDC 200B of South Line; KDA and KDC joined on
    1 Oct at 7000 a week, KDB on 7 Oct at 3500, and KDC left on 8 Oct."""
    owner = provision_member(operator_conn, 1, "Owner", "Antony", "Maina")
    clerk = provision_member(operator_conn, 2, "Revenue clerk", "Cleo", "Clerk")
    admin = provision_member(operator_conn, 3, "Office admin", "Ada", "Admin")
    org = owner.org
    for member in (clerk, admin):
        set_scope(owner_conn, member, org, all_companies=True)
    north = add_company(owner_conn, org, "North Star")
    south = add_company(owner_conn, org, "South Line")
    set_threshold(owner_conn, org, 100)

    def vehicle(company: UUID, registration: str, joined: date, target: int, **kw: Any) -> UUID:
        vehicle_id = add_vehicle(owner_conn, org, company, registration, joined_on=joined, **kw)
        add_target(owner_conn, org, vehicle_id, 1, joined, target)
        return vehicle_id

    return Yard(
        owner=owner,
        clerk=clerk,
        admin=admin,
        north=north,
        south=south,
        kda=vehicle(north, "KDA 482M", OCT1, 7000),
        kdb=vehicle(north, "KDB 111A", date(2026, 10, 7), 3500),
        kdc=vehicle(south, "KDC 200B", OCT1, 7000, left_on=date(2026, 10, 8)),
    )


def set_threshold(
    owner: Conn, org: UUID, threshold: Decimal | int, amber: Decimal | int = 10
) -> None:
    owner.execute(
        "INSERT INTO tenancy.organization_revenue_settings (organization_id, low_day_threshold, "
        "gap_amber_percent) VALUES (%s, %s, %s) ON CONFLICT (organization_id) DO UPDATE SET "
        "low_day_threshold = EXCLUDED.low_day_threshold, "
        "gap_amber_percent = EXCLUDED.gap_amber_percent",
        (org, threshold, amber),
    )


def set_limit(
    owner: Conn, who: Member, mode: str, count: int | None = None, since: date | None = None
) -> None:
    owner.execute(
        "UPDATE tenancy.memberships SET back_limit_mode = %s, back_limit_count = %s, "
        "back_limit_from = %s WHERE organization_id = %s AND user_id = %s",
        (mode, count, since, who.org, who.id),
    )


def capture(
    app: Conn,
    who: Member,
    vehicle: UUID,
    day: date | None,
    amount: Decimal | int | str | None = None,
    reason: str | None = None,
    note: str | None = None,
    version: int | None = None,
    *,
    captured_at: datetime | None = None,
    now: datetime = T0,
) -> dict[str, Any]:
    return run(
        app, "revenue_capture", who, vehicle, day, amount, reason, note, version, captured_at,
        now=now,
    )  # fmt: skip


def capture_refused(
    app: Conn,
    who: Member,
    vehicle: UUID,
    day: date | None,
    amount: Decimal | int | str | None,
    reason: str | None,
    note: str | None,
    version: int | None,
    sqlstate: str,
    code: str,
    *,
    captured_at: datetime | None = None,
    now: datetime = T0,
) -> psycopg.Error:
    return refuses(
        app,
        "revenue_capture",
        who,
        [vehicle, day, amount, reason, note, version, captured_at],
        sqlstate,
        code,
        now=now,
    )


def detail(error: psycopg.Error) -> dict[str, Any]:
    text = error.diag.message_detail
    return json.loads(text) if text else {}


def record_row(owner_conn: Conn, vehicle: UUID, day: date) -> dict[str, Any] | None:
    return owner_conn.execute(
        "SELECT * FROM revenue.records WHERE vehicle_id = %s AND business_date = %s",
        (vehicle, day),
    ).fetchone()


def week(
    app: Conn,
    who: Member,
    week_start: date | None = None,
    company: UUID | None = None,
    vehicle: UUID | None = None,
    page: int | None = None,
    size: int | None = None,
    q: str | None = None,
) -> dict[str, Any]:
    return read(app, "revenue_week_get", who, week_start, company, vehicle, page, size, q)


def dashboard(
    app: Conn, who: Member, period: str | None = None, company: UUID | None = None
) -> dict[str, Any]:
    return read(app, "revenue_dashboard_get", who, period, company)


# --- capture: the steps in order ----------------------------------------------------------


def test_an_actor_of_another_organization_is_not_a_member(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    other = seed_organization(owner_conn)
    stranger = Member(other.user, yard.owner.org, "", "", "Sam", "Stranger", "Owner")
    capture_refused(
        app_conn, stranger, yard.kda, TODAY, 500, None, None, None, "XC403", "not_member"
    )
    own = Member(other.user, other.org, "", "", "Sam", "Stranger", "Owner")
    capture_refused(app_conn, own, yard.kda, TODAY, 500, None, None, None, "XC404", "not_found")
    assert record_row(owner_conn, yard.kda, TODAY) is None
    refuses(
        app_conn,
        "revenue_week_get",
        own,
        [None, None, yard.kda, None, None, None],
        "XC404",
        "not_found",
    )
    assert yard.kda not in {UUID(v["id"]) for v in week(app_conn, own)["vehicles"]}


def test_a_member_with_neither_capture_nor_correct_is_refused_before_the_entry_is_read(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    set_override(owner_conn, yard.clerk, "revenue.capture", False)
    capture_refused(
        app_conn, yard.clerk, UUID(int=1), TODAY, None, "Lunch", None, None,
        "XC403", "permission_missing",
    )  # fmt: skip


@pytest.mark.parametrize(
    ("amount", "reason", "note", "code"),
    [
        (None, "Lunch", None, "revenue_reason_invalid"),
        (None, "no crew", None, "revenue_reason_invalid"),
        ("10.001", "Garage", None, "money_invalid"),
        (-5, None, None, "money_invalid"),
        (-5, "Garage", None, "money_invalid"),
        ("1000000000000.00", None, None, "money_invalid"),
        (0, None, None, "money_invalid"),
        (0, None, "Late", "money_invalid"),
        (None, None, None, "revenue_entry_required"),
        (None, "  ", "Late", "revenue_entry_required"),
        (500, None, "Late", "revenue_note_without_other"),
        ("99.99", "Garage", "Late", "revenue_note_without_other"),
        (None, "Other", "x" * 81, "revenue_note_length"),
        (None, "Garage", "x" * 81, "revenue_note_length"),
        (None, "Garage", "Late", "revenue_note_without_other"),
    ],
)
def test_the_entry_shape_is_checked_before_the_vehicle(
    app_conn: Conn,
    yard: Yard,
    amount: int | str | None,
    reason: str | None,
    note: str | None,
    code: str,
) -> None:
    capture_refused(
        app_conn, yard.owner, UUID(int=1), TODAY, amount, reason, note, None, "XC422", code
    )


@pytest.mark.parametrize(
    ("amount", "reason", "code"),
    [
        ("99.99", None, "revenue_low_needs_reason"),
        (100, "Garage", "revenue_amount_with_reason"),
        (500, "Garage", "revenue_amount_with_reason"),
    ],
)
def test_the_threshold_is_checked_after_the_vehicle_and_before_the_date(
    app_conn: Conn, yard: Yard, amount: int | str, reason: str | None, code: str
) -> None:
    capture_refused(
        app_conn, yard.owner, UUID(int=1), TODAY, amount, reason, None, None, "XC404", "not_found"
    )
    capture_refused(
        app_conn, yard.owner, yard.kda, TODAY + timedelta(days=1), amount, reason, None, None,
        "XC422", code,
    )  # fmt: skip


def test_an_unknown_or_unseen_vehicle_is_not_found_before_the_date_is_read(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    tomorrow = TODAY + timedelta(days=1)
    capture_refused(
        app_conn, yard.owner, UUID(int=1), tomorrow, 500, None, None, None, "XC404", "not_found"
    )
    set_scope(owner_conn, yard.clerk, yard.owner.org, companies=[yard.south])
    capture_refused(
        app_conn, yard.clerk, yard.kda, tomorrow, 500, None, None, None, "XC404", "not_found"
    )
    assert capture(app_conn, yard.clerk, yard.kdc, OCT1, 500)["outcome"] == "created"


def test_the_business_date_is_the_organizations_own_calendar_day(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    set_localization(owner_conn, yard.owner.org, time_zone="America/New_York")
    evening = datetime(2026, 10, 9, 2, 0, tzinfo=T0.tzinfo)
    capture_refused(
        app_conn,
        yard.owner,
        yard.kda,
        TODAY,
        500,
        None,
        None,
        None,
        "XC422",
        "revenue_future_date",
        now=evening,
    )
    grid = read(
        app_conn, "revenue_week_get", yard.owner, None, None, None, None, None, None, now=evening
    )
    assert grid["business_date"] == "2026-10-08"
    day = capture(app_conn, yard.owner, yard.kda, TODAY - timedelta(days=1), 500, now=evening)
    assert day["outcome"] == "created"
    assert record_row(owner_conn, yard.kda, TODAY) is None


@pytest.mark.parametrize("day", [TODAY + timedelta(days=1), date(1, 1, 1)])
def test_a_day_after_the_business_date_or_the_default_date_is_refused(
    app_conn: Conn, yard: Yard, day: date
) -> None:
    capture_refused(
        app_conn, yard.owner, yard.kda, day, 500, None, None, None, "XC422", "revenue_future_date"
    )


def test_a_day_out_of_the_fleet_is_refused_as_away_or_inactive(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    add_away(owner_conn, yard.owner.org, yard.kda, date(2026, 10, 3), date(2026, 10, 5))
    for day, code in (
        (date(2026, 10, 3), "revenue_vehicle_away"),
        (date(2026, 10, 4), "revenue_vehicle_away"),
        (date(2026, 9, 30), "revenue_vehicle_inactive"),
    ):
        capture_refused(app_conn, yard.owner, yard.kda, day, 500, None, None, None, "XC422", code)
    capture_refused(
        app_conn, yard.owner, yard.kdc, date(2026, 10, 8), 500, None, None, None,
        "XC422", "revenue_vehicle_inactive",
    )  # fmt: skip
    assert capture(app_conn, yard.owner, yard.kda, date(2026, 10, 5), 500)["outcome"] == "created"


def test_a_reason_needs_only_the_right_of_its_path(app_conn: Conn, yard: Yard) -> None:
    # The admin may change saved days but not fill an empty one, whatever the entry holds.
    capture_refused(
        app_conn, yard.admin, yard.kda, TODAY, None, "Garage", None, None,
        "XC403", "revenue_capture_permission",
    )  # fmt: skip
    assert capture(app_conn, yard.clerk, yard.kda, TODAY, None, "Garage")["outcome"] == "created"
    assert capture(app_conn, yard.clerk, yard.kdb, TODAY, 50, "Arrest")["outcome"] == "created"
    changed = capture(app_conn, yard.admin, yard.kdb, TODAY, None, "Other", version=1, now=at(1))
    assert changed["outcome"] == "updated"


def test_a_day_with_no_record_needs_the_capture_permission(app_conn: Conn, yard: Yard) -> None:
    capture_refused(
        app_conn, yard.admin, yard.kda, TODAY, 500, None, None, None,
        "XC403", "revenue_capture_permission",
    )  # fmt: skip


def test_changing_an_earlier_day_needs_the_correct_permission_and_shows_nothing_stored(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    yesterday = TODAY - timedelta(days=1)
    stored = capture(app_conn, yard.owner, yard.kda, yesterday, 500)
    error = capture_refused(
        app_conn, yard.clerk, yard.kda, yesterday, 600, None, None, None,
        "XC403", "revenue_correct_permission",
    )  # fmt: skip
    assert "current" not in detail(error)
    # A record of the business date is closed to the clerk too; the admin changes either.
    today = capture(app_conn, yard.clerk, yard.kda, TODAY, 500, now=at(1))
    capture_refused(
        app_conn, yard.clerk, yard.kda, TODAY, 550, None, None, 1,
        "XC403", "revenue_correct_permission", now=at(2),
    )  # fmt: skip
    assert capture(app_conn, yard.admin, yard.kda, TODAY, 550, version=1, now=at(2)) == {
        "id": today["id"],
        "version": 2,
        "outcome": "updated",
    }
    corrected = capture(app_conn, yard.admin, yard.kda, yesterday, 600, version=1, now=at(3))
    assert (corrected["id"], corrected["version"]) == (stored["id"], 2)


def test_a_stale_version_is_a_conflict_carrying_the_stored_cell(app_conn: Conn, yard: Yard) -> None:
    yesterday = TODAY - timedelta(days=1)
    capture(app_conn, yard.owner, yard.kda, yesterday, None, "Other", " Engine knock ")
    for version in (None, 2):
        error = capture_refused(
            app_conn, yard.owner, yard.kda, yesterday, None, "Other", "Puncture", version,
            "XC409", "revenue_version_conflict",
        )  # fmt: skip
        assert detail(error)["current"]["version"] == 1
    error = capture_refused(
        app_conn, yard.admin, yard.kda, yesterday, 700, None, None, None,
        "XC409", "revenue_version_conflict",
    )  # fmt: skip
    assert detail(error) == {
        "current": {
            "day": "2026-10-08",
            "status": "reason",
            "expected": 1000.0,
            "amount": None,
            "reason": "Other",
            "note": "Engine knock",
            "can_edit": True,
            "edited_after_capture": False,
            "version": 1,
        }
    }


def test_the_clerk_gets_the_conflict_only_once_they_may_change_a_saved_day(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    capture(app_conn, yard.owner, yard.kda, TODAY, 500)
    error = capture_refused(
        app_conn, yard.clerk, yard.kda, TODAY, 600, None, None, None,
        "XC403", "revenue_correct_permission",
    )  # fmt: skip
    assert detail(error) == {}
    set_override(owner_conn, yard.clerk, "revenue.correct")
    error = capture_refused(
        app_conn, yard.clerk, yard.kda, TODAY, 600, None, None, None,
        "XC409", "revenue_version_conflict",
    )  # fmt: skip
    assert detail(error)["current"]["can_edit"] is True
    assert detail(error)["current"]["amount"] == 500


# --- capture: writes, the change log and the audit trail ----------------------------------


def test_a_first_capture_creates_version_1_and_logs_it(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    org = yard.owner.org
    before = settings_version(owner_conn, org)
    result = capture(app_conn, yard.clerk, yard.kda, date(2026, 10, 8), "1500.50")
    assert (result["outcome"], result["version"]) == ("created", 1)
    row = record_row(owner_conn, yard.kda, date(2026, 10, 8))
    assert row is not None
    assert (row["id"], row["amount"], row["reason"], row["note"]) == (
        result["id"],
        Decimal("1500.50"),
        None,
        None,
    )
    assert (row["captured_at"], row["captured_by"], row["updated_by"]) == (
        T0,
        yard.clerk.id,
        yard.clerk.id,
    )
    assert row["corrected_after_date"] is False
    [log] = change_rows(owner_conn, org, "revenue")
    assert log["version"] == before + 1 == settings_version(owner_conn, org)
    assert (log["entity_id"], log["vehicle_id"], log["actor_id"], log["request_id"]) == (
        result["id"],
        yard.kda,
        yard.clerk.id,
        REQUEST,
    )
    assert log["reason"] == "Recorded revenue for KDA 482M on 8 Oct 2026"
    assert log["before"] == "null"
    after = json.loads(log["after"])
    assert list(after) == [
        "Id",
        "VehicleId",
        "BusinessDate",
        "Amount",
        "Reason",
        "Note",
        "CapturedAt",
        "CapturedBy",
        "UpdatedAt",
        "UpdatedBy",
        "CorrectedAfterDate",
        "Version",
    ]
    assert (after["Amount"], after["BusinessDate"], after["Version"]) == (1500.5, "2026-10-08", 1)
    [event] = audit_events(owner_conn, org, "revenue.recorded")
    assert (event["entity"], event["before"], event["after"]) == (
        str(result["id"]),
        None,
        after,
    )


@pytest.mark.parametrize(
    ("reason", "note", "words", "label", "snapshot"),
    [
        ("NoCrew", None, "No Crew", None, "NoCrew"),
        (" No Crew ", None, "No Crew", None, "NoCrew"),
        ("Garage", None, "Garage", None, "Garage"),
        ("Other", "  Engine knock ", "Other", "Engine knock", "Other"),
    ],
)
def test_a_no_earnings_day_logs_its_reason_label(
    app_conn: Conn,
    owner_conn: Conn,
    yard: Yard,
    reason: str,
    note: str | None,
    words: str,
    label: str | None,
    snapshot: str,
) -> None:
    result = capture(app_conn, yard.owner, yard.kda, OCT1, None, reason, note)
    row = record_row(owner_conn, yard.kda, OCT1)
    assert row is not None and row["note"] == label
    [log] = change_rows(owner_conn, yard.owner.org, "revenue")
    assert log["reason"] == f"Recorded no revenue for KDA 482M on 1 Oct 2026: {words}"
    after = json.loads(log["after"])
    assert (after["Reason"], after["Note"], after["Amount"]) == (snapshot, label, None)
    assert result["version"] == 1


def test_changing_today_updates_and_changing_an_earlier_day_corrects(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    yesterday = TODAY - timedelta(days=1)
    first = capture(app_conn, yard.owner, yard.kda, TODAY, 500, now=at(0))
    past = capture(app_conn, yard.owner, yard.kda, yesterday, 500, now=at(1))
    updated = capture(app_conn, yard.owner, yard.kda, TODAY, None, "Arrest", version=1, now=at(2))
    corrected = capture(app_conn, yard.owner, yard.kda, yesterday, 450, version=1, now=at(3))
    assert updated == {"id": first["id"], "version": 2, "outcome": "updated"}
    assert corrected == {"id": past["id"], "version": 2, "outcome": "updated"}
    today_row = record_row(owner_conn, yard.kda, TODAY)
    past_row = record_row(owner_conn, yard.kda, yesterday)
    assert today_row is not None and past_row is not None
    assert (today_row["amount"], today_row["reason"], today_row["corrected_after_date"]) == (
        None,
        2,
        False,
    )
    assert (past_row["amount"], past_row["corrected_after_date"]) == (450, True)
    assert (past_row["captured_at"], past_row["updated_at"]) == (at(1), at(3))
    logs = change_rows(owner_conn, yard.owner.org, "revenue")
    assert [log["reason"] for log in logs] == [
        "Recorded revenue for KDA 482M on 9 Oct 2026",
        "Recorded revenue for KDA 482M on 8 Oct 2026",
        "Updated revenue for KDA 482M on 9 Oct 2026",
        "Corrected revenue for KDA 482M on 8 Oct 2026",
    ]
    assert all(log["vehicle_id"] == yard.kda for log in logs)
    before, after = json.loads(logs[3]["before"]), json.loads(logs[3]["after"])
    assert (before["Amount"], before["Version"], before["CorrectedAfterDate"]) == (500, 1, False)
    assert (after["Amount"], after["Version"], after["CorrectedAfterDate"]) == (450, 2, True)
    assert after["UpdatedAt"] == "2026-10-09T07:03:00.000000+00:00"


def test_changing_a_day_after_it_closed_marks_it_corrected(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    capture(app_conn, yard.owner, yard.kda, TODAY, 500, now=at(0))
    tomorrow = T0 + timedelta(days=1)
    capture(app_conn, yard.owner, yard.kda, TODAY, 450, version=1, now=tomorrow)
    row = record_row(owner_conn, yard.kda, TODAY)
    assert row is not None and row["corrected_after_date"] is True
    logs = change_rows(owner_conn, yard.owner.org, "revenue")
    assert logs[-1]["reason"] == "Corrected revenue for KDA 482M on 9 Oct 2026"


# --- capture: identical replays -----------------------------------------------------------


def test_an_identical_entry_replays_whatever_version_is_sent_and_writes_nothing(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    org = yard.owner.org
    stored = capture(app_conn, yard.clerk, yard.kda, TODAY, 500)
    version = settings_version(owner_conn, org)
    for sent, amount in ((None, "500.00"), (1, 500), (99, "500")):
        replay = capture(app_conn, yard.clerk, yard.kda, TODAY, amount, version=sent, now=at(5))
        assert replay == {"id": stored["id"], "version": 1, "outcome": "replayed"}
    reasons = capture(app_conn, yard.owner, yard.kdb, TODAY, None, "Other", "Engine knock")
    replay = capture(app_conn, yard.owner, yard.kdb, TODAY, None, " Other", " Engine knock  ")
    assert replay == {**reasons, "outcome": "replayed"}
    no_crew = capture(app_conn, yard.owner, yard.kda, OCT1, None, "No Crew")
    assert capture(app_conn, yard.owner, yard.kda, OCT1, None, "NoCrew")["outcome"] == "replayed"
    assert no_crew["outcome"] == "created"
    assert settings_version(owner_conn, org) == version + 2
    assert len(change_rows(owner_conn, org, "revenue")) == 3
    row = record_row(owner_conn, yard.kda, TODAY)
    assert row is not None and (row["version"], row["updated_at"]) == (1, T0)


def test_a_phone_replaying_after_the_day_closed_succeeds_without_any_permission_check(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    stored = capture(app_conn, yard.clerk, yard.kdc, date(2026, 10, 7), 500)
    # Days later: the clerk cannot change a saved day, KDC has since left the fleet, and the
    # clerk may now write today only.
    later = T0 + timedelta(days=3)
    set_limit(owner_conn, yard.clerk, "days", 0)
    for version in (None, 1, 7):
        replay = capture(
            app_conn, yard.clerk, yard.kdc, date(2026, 10, 7), 500, version=version, now=later
        )
        assert replay == {"id": stored["id"], "version": 1, "outcome": "replayed"}


def test_a_replay_that_is_no_longer_identical_is_refused_for_permission_without_current(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    clerk_saved = capture(app_conn, yard.clerk, yard.kda, TODAY, 500)
    later = T0 + timedelta(days=1)
    capture(app_conn, yard.owner, yard.kda, TODAY, 520, version=1, now=later)
    for version in (None, clerk_saved["version"]):
        error = capture_refused(
            app_conn, yard.clerk, yard.kda, TODAY, 500, None, None, version,
            "XC403", "revenue_correct_permission", now=later + timedelta(minutes=1),
        )  # fmt: skip
        assert detail(error) == {}


# --- capture: two saves at once ------------------------------------------------------------


def _blocked_on(owner_conn: Conn, waiting: int, holder: int) -> bool:
    for _ in range(200):
        row = owner_conn.execute("SELECT pg_blocking_pids(%s) AS pids", (waiting,)).fetchone()
        if row is not None and holder in row["pids"]:
            return True
        threading.Event().wait(0.05)
    return False


def _capture_args(
    who: Member, vehicle: UUID, day: date, amount: int, now: datetime
) -> tuple[Any, ...]:
    return (who.id, who.org, REQUEST, vehicle, day, amount, None, None, None, None, now)


_CAPTURE = "SELECT * FROM api.revenue_capture(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"


def test_two_first_captures_of_a_day_race_to_one_record_and_a_unique_conflict(
    app_url: str, owner_conn: Conn, yard: Yard
) -> None:
    with (
        psycopg.connect(app_url, autocommit=True, row_factory=dict_row) as first,
        psycopg.connect(app_url, autocommit=True, row_factory=dict_row) as second,
    ):
        outcome: list[BaseException | dict[str, Any] | None] = []

        def second_capture() -> None:
            try:
                outcome.append(
                    second.execute(
                        _CAPTURE, _capture_args(yard.clerk, yard.kda, TODAY, 600, at(1))
                    ).fetchone()
                )
            except psycopg.Error as error:
                outcome.append(error)

        with first.transaction():
            created = first.execute(
                _CAPTURE, _capture_args(yard.owner, yard.kda, TODAY, 500, at(0))
            ).fetchone()
            worker = threading.Thread(target=second_capture)
            worker.start()
            assert _blocked_on(owner_conn, second.info.backend_pid, first.info.backend_pid)
        worker.join(10)
    assert created is not None and created["outcome"] == "created"
    [error] = outcome
    assert isinstance(error, psycopg.Error)
    assert (error.sqlstate, error.diag.message_primary) == ("XC409", "unique_conflict")
    row = record_row(owner_conn, yard.kda, TODAY)
    assert row is not None and (row["amount"], row["version"]) == (500, 1)
    assert len(change_rows(owner_conn, yard.owner.org, "revenue")) == 1


def test_a_save_of_a_day_another_save_holds_is_refused_at_once(
    app_url: str, app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    capture(app_conn, yard.owner, yard.kda, TODAY, 500)
    with (
        psycopg.connect(app_url, autocommit=True, row_factory=dict_row) as first,
        psycopg.connect(app_url, autocommit=True, row_factory=dict_row) as second,
    ):
        with first.transaction():
            args = list(_capture_args(yard.owner, yard.kda, TODAY, 550, at(1)))
            args[8] = 1
            updated = first.execute(_CAPTURE, args).fetchone()
            args = list(_capture_args(yard.clerk, yard.kda, TODAY, 600, at(1)))
            args[8] = 1
            with pytest.raises(psycopg.Error) as caught:
                second.execute(_CAPTURE, args).fetchone()
    assert updated is not None and (updated["outcome"], updated["version"]) == ("updated", 2)
    assert (caught.value.sqlstate, caught.value.diag.message_primary) == (
        "XC409",
        "revenue_concurrent_save",
    )
    assert detail(caught.value) == {}
    row = record_row(owner_conn, yard.kda, TODAY)
    assert row is not None and (row["amount"], row["version"]) == (550, 2)


_RETIRE = "SELECT * FROM api.setup_vehicle_retire(%s, %s, %s, %s, %s, %s, %s)"
_UPDATE = "SELECT * FROM api.setup_vehicle_update(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"


@pytest.mark.parametrize("change", ["retire", "join later"])
def test_a_capture_waits_for_a_fleet_change_of_its_vehicle_and_then_reads_it(
    app_url: str, owner_conn: Conn, yard: Yard, change: str
) -> None:
    """The vehicle writers lock the vehicle and then look for revenue the change would strand;
    a capture that read the vehicle before such a change commits must not add that revenue."""
    owner = yard.owner
    if change == "retire":
        vehicle, day = yard.kda, TODAY
        sql = _RETIRE
        args: tuple[Any, ...] = (owner.id, owner.org, REQUEST, vehicle, TODAY, None, at(0))
    else:
        vehicle, day = yard.kdb, date(2026, 10, 8)
        sql = _UPDATE
        args = (
            owner.id,
            owner.org,
            REQUEST,
            vehicle,
            yard.north,
            "KDB 111A",
            "111A",
            TODAY,
            None,
            None,
            at(0),
        )
    with (
        psycopg.connect(app_url, autocommit=True, row_factory=dict_row) as first,
        psycopg.connect(app_url, autocommit=True, row_factory=dict_row) as second,
    ):
        outcome: list[BaseException | dict[str, Any] | None] = []

        def late_capture() -> None:
            try:
                outcome.append(
                    second.execute(
                        _CAPTURE, _capture_args(yard.clerk, vehicle, day, 600, at(1))
                    ).fetchone()
                )
            except psycopg.Error as error:
                outcome.append(error)

        with first.transaction():
            changed = first.execute(sql, args).fetchone()
            worker = threading.Thread(target=late_capture)
            worker.start()
            assert _blocked_on(owner_conn, second.info.backend_pid, first.info.backend_pid)
        worker.join(10)
    assert changed is not None and changed["outcome"] == "updated"
    [error] = outcome
    assert isinstance(error, psycopg.Error)
    assert (error.sqlstate, error.diag.message_primary) == ("XC422", "revenue_vehicle_inactive")
    assert record_row(owner_conn, vehicle, day) is None


def test_a_retirement_waits_for_a_capture_of_its_vehicle_and_then_sees_the_record(
    app_url: str, owner_conn: Conn, yard: Yard
) -> None:
    owner = yard.owner
    retire = (owner.id, owner.org, REQUEST, yard.kda, TODAY, None, at(1))
    with (
        psycopg.connect(app_url, autocommit=True, row_factory=dict_row) as first,
        psycopg.connect(app_url, autocommit=True, row_factory=dict_row) as second,
    ):
        outcome: list[BaseException | dict[str, Any] | None] = []

        def late_retire() -> None:
            try:
                outcome.append(second.execute(_RETIRE, retire).fetchone())
            except psycopg.Error as error:
                outcome.append(error)

        with first.transaction():
            created = first.execute(
                _CAPTURE, _capture_args(yard.clerk, yard.kda, TODAY, 600, at(0))
            ).fetchone()
            worker = threading.Thread(target=late_retire)
            worker.start()
            assert _blocked_on(owner_conn, second.info.backend_pid, first.info.backend_pid)
        worker.join(10)
    assert created is not None and created["outcome"] == "created"
    [error] = outcome
    assert isinstance(error, psycopg.Error)
    assert (error.sqlstate, error.diag.message_primary) == ("XC422", "vehicle_leave_before_revenue")
    row = owner_conn.execute("SELECT left_on FROM setup.fleet_vehicles WHERE id = %s", (yard.kda,))
    assert row.fetchone() == {"left_on": None}


# --- the week grid ----------------------------------------------------------------------


def _history(owner_conn: Conn, yard: Yard) -> None:
    """The fleet's records: KDA on 1, 2, 5, 6 (Garage), 8 (corrected) and 9 Oct; KDB on 7 Oct;
    KDC on 5 Oct."""
    org, by = yard.owner.org, yard.owner.id
    for day, amount in ((1, 1200), (2, 800), (5, 1000), (8, 900), (9, 1100)):
        add_record(owner_conn, org, yard.kda, date(2026, 10, day), amount, recorder=by)
    add_record(owner_conn, org, yard.kda, date(2026, 10, 6), None, recorder=by, reason=1)
    owner_conn.execute(
        "UPDATE revenue.records SET corrected_after_date = true, version = 2 "
        "WHERE vehicle_id = %s AND business_date = %s",
        (yard.kda, date(2026, 10, 8)),
    )
    add_record(owner_conn, org, yard.kdb, date(2026, 10, 7), 500, recorder=by)
    add_record(owner_conn, org, yard.kdc, date(2026, 10, 5), 700, recorder=by)


def _figures(grid: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "total_amount",
        "total_expected",
        "percent",
        "total_vehicles",
        "day_totals",
        "first_gap",
        "gap",
        "gap_band",
        "below_threshold_days",
        "missing_days",
    )
    return {key: grid[key] for key in keys}


def test_the_week_lists_the_fleet_by_registration_with_cells_and_whole_grid_figures(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    _history(owner_conn, yard)
    grid = week(app_conn, yard.owner)
    assert set(grid) == {
        "week_start",
        "week_through",
        "current_week_start",
        "business_date",
        "companies",
        "vehicles",
        "total_amount",
        "total_expected",
        "percent",
        "page_number",
        "page_size",
        "total_vehicles",
        "truncated",
        "day_totals",
        "first_gap",
        "low_day_threshold",
        "gap_amber_percent",
        "gap",
        "gap_band",
        "below_threshold_days",
        "missing_days",
    }
    assert (grid["week_start"], grid["week_through"], grid["current_week_start"]) == (
        "2026-10-05",
        "2026-10-11",
        "2026-10-05",
    )
    assert grid["business_date"] == "2026-10-09"
    assert grid["companies"] == [
        {"id": str(yard.north), "name": "North Star"},
        {"id": str(yard.south), "name": "South Line"},
    ]
    kda, kdb, kdc = grid["vehicles"]
    assert [v["registration"] for v in grid["vehicles"]] == ["KDA 482M", "KDB 111A", "KDC 200B"]
    assert set(kda) == {
        "id",
        "company_id",
        "company_name",
        "registration",
        "joined_on",
        "left_on",
        "earliest_missing",
        "fleet_number",
        "days",
        "total_amount",
        "total_expected",
        "percent",
        "gap",
        "gap_band",
        "below_threshold_days",
    }
    assert (kda["company_name"], kda["joined_on"], kda["left_on"]) == (
        "North Star",
        "2026-10-01",
        None,
    )
    assert [(c["status"], c["amount"], c["reason"]) for c in kda["days"]] == [
        ("amount", 1000, None),
        ("reason", None, "Garage"),
        ("missing", None, None),
        ("amount", 900, None),
        ("amount", 1100, None),
        ("future", None, None),
        ("future", None, None),
    ]
    assert [c["edited_after_capture"] for c in kda["days"]] == [False, False, False, True] + [
        False
    ] * 3
    assert [c["version"] for c in kda["days"]] == [1, 1, None, 2, 1, None, None]
    assert [c["can_edit"] for c in kda["days"]] == [True] * 5 + [False] * 2
    assert (kda["total_amount"], kda["total_expected"], kda["percent"]) == (3000, 5000, 60)
    assert [c["status"] for c in kdb["days"]] == [
        "none",
        "none",
        "amount",
        "missing",
        "missing",
        "future",
        "future",
    ]
    assert (kdb["total_expected"], kdb["percent"]) == (1000, 50)
    assert [c["status"] for c in kdc["days"]] == ["amount", "missing", "missing"] + ["none"] * 4
    assert (kdc["left_on"], kdc["total_expected"], kdc["percent"]) == ("2026-10-08", 3000, 23)
    assert [v["earliest_missing"] for v in grid["vehicles"]] == [
        "2026-10-03",
        "2026-10-08",
        "2026-10-01",
    ]
    assert _figures(grid) == {
        "total_amount": 4200,
        "total_expected": 9000,
        "percent": 47,
        "total_vehicles": 3,
        "day_totals": [
            {"day": "2026-10-05", "amount": 1700, "expected": 2000},
            {"day": "2026-10-06", "amount": 0, "expected": 2000},
            {"day": "2026-10-07", "amount": 500, "expected": 2500},
            {"day": "2026-10-08", "amount": 900, "expected": 1500},
            {"day": "2026-10-09", "amount": 1100, "expected": 1000},
            {"day": "2026-10-10", "amount": 0, "expected": 0},
            {"day": "2026-10-11", "amount": 0, "expected": 0},
        ],
        "first_gap": {"vehicle_id": str(yard.kdc), "day": "2026-10-01"},
        "gap": -4800,
        "gap_band": "red",
        "below_threshold_days": 1,
        "missing_days": 4,
    }
    assert (grid["page_number"], grid["page_size"], grid["truncated"]) == (1, 500, False)


def test_the_cells_open_by_the_viewers_permissions(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    _history(owner_conn, yard)
    clerk = week(app_conn, yard.clerk)["vehicles"][0]["days"]
    admin = week(app_conn, yard.admin)["vehicles"][0]["days"]
    assert [c["can_edit"] for c in clerk] == [False, False, True, False, False, False, False]
    assert [c["can_edit"] for c in admin] == [True, True, False, True, True, False, False]


def test_pages_list_a_slice_and_keep_the_whole_grid_figures(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    _history(owner_conn, yard)
    whole = week(app_conn, yard.owner)
    pages = [week(app_conn, yard.owner, page=n, size=1) for n in (1, 2, 3, 4)]
    assert [[v["registration"] for v in p["vehicles"]] for p in pages] == [
        ["KDA 482M"],
        ["KDB 111A"],
        ["KDC 200B"],
        [],
    ]
    for n, page in enumerate(pages, start=1):
        assert (page["page_number"], page["page_size"], page["truncated"]) == (n, 1, False)
        assert _figures(page) == _figures(whole)
    either = week(app_conn, yard.owner, page=2)
    assert (either["page_number"], either["page_size"], len(either["vehicles"])) == (2, 100, 0)
    sized = week(app_conn, yard.owner, size=2)
    assert (sized["page_number"], sized["page_size"], len(sized["vehicles"])) == (1, 2, 2)


def test_a_grid_of_more_than_500_lists_500_and_says_truncated_until_paged(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    owner_conn.execute(
        "INSERT INTO setup.fleet_vehicles (organization_id, company_id, registration, joined_on) "
        "SELECT %s, %s, 'KZZ ' || lpad(n::text, 3, '0') || 'A', %s FROM generate_series(1, 498) "
        "AS n",
        (yard.owner.org, yard.north, OCT1),
    )
    legacy = week(app_conn, yard.owner)
    assert (len(legacy["vehicles"]), legacy["total_vehicles"], legacy["truncated"]) == (
        500,
        501,
        True,
    )
    assert legacy["vehicles"][-1]["registration"] == "KZZ 497A"
    rest = week(app_conn, yard.owner, page=6, size=100)
    assert [v["registration"] for v in rest["vehicles"]] == ["KZZ 498A"]
    assert (rest["truncated"], rest["total_vehicles"]) == (False, 501)
    assert _figures(rest) == _figures(legacy)


@pytest.mark.parametrize(("page", "size"), [(0, None), (None, 0), (None, 101), (100_001, 10)])
def test_a_page_out_of_range_is_refused_before_the_week_is_read(
    app_conn: Conn, yard: Yard, page: int | None, size: int | None
) -> None:
    refuses(
        app_conn,
        "revenue_week_get",
        yard.owner,
        [WEEK + timedelta(days=7), None, None, page, size, None],
        "XC422",
        "page_out_of_range",
    )


def test_the_week_range_runs_from_ten_years_back_through_the_current_week(
    app_conn: Conn, yard: Yard
) -> None:
    lower = WEEK - timedelta(days=3650)
    earliest = lower + timedelta(days=(7 - lower.weekday()) % 7)
    for allowed in (TODAY + timedelta(days=2), WEEK, earliest, earliest + timedelta(days=6)):
        start = week(app_conn, yard.owner, allowed)["week_start"]
        assert start == (WEEK if allowed >= WEEK else earliest).isoformat()
    for refused_day in (WEEK + timedelta(days=7), earliest - timedelta(days=1)):
        refuses(
            app_conn,
            "revenue_week_get",
            yard.owner,
            [refused_day, None, UUID(int=1), None, None, None],
            "XC422",
            "revenue_week_range",
        )


def test_one_vehicle_is_listed_for_any_week_and_never_paged(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    _history(owner_conn, yard)
    past = week(app_conn, yard.owner, date(2026, 9, 28), vehicle=yard.kdc, page=0, size=0)
    [kdc] = past["vehicles"]
    assert kdc["registration"] == "KDC 200B"
    assert [c["status"] for c in kdc["days"]] == ["none"] * 3 + ["missing"] * 4
    assert (past["page_number"], past["page_size"], past["truncated"]) == (1, 500, False)
    assert past["first_gap"] == {"vehicle_id": str(yard.kdc), "day": "2026-10-01"}
    later = week(app_conn, yard.owner, vehicle=yard.kdc)
    assert [v["registration"] for v in later["vehicles"]] == ["KDC 200B"]
    other_company = week(app_conn, yard.owner, company=yard.north, vehicle=yard.kdc)
    assert (other_company["vehicles"], other_company["total_vehicles"]) == ([], 0)


def test_an_unknown_or_unseen_vehicle_is_not_found(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    set_scope(owner_conn, yard.clerk, yard.owner.org, companies=[yard.south])
    for who, vehicle in ((yard.owner, UUID(int=1)), (yard.clerk, yard.kda)):
        refuses(
            app_conn,
            "revenue_week_get",
            who,
            [None, None, vehicle, None, None, None],
            "XC404",
            "not_found",
        )
    seen = week(app_conn, yard.clerk)
    assert [v["registration"] for v in seen["vehicles"]] == ["KDC 200B"]
    assert seen["companies"] == [{"id": str(yard.south), "name": "South Line"}]


@pytest.mark.parametrize("scope", ["companies", "vehicles"])
def test_a_scoped_viewer_counts_only_the_vehicles_they_may_see(
    app_conn: Conn, owner_conn: Conn, yard: Yard, scope: str
) -> None:
    _history(owner_conn, yard)
    if scope == "companies":
        set_scope(owner_conn, yard.clerk, yard.owner.org, companies=[yard.south])
    else:
        set_scope(owner_conn, yard.clerk, yard.owner.org, vehicles=[yard.kdc])
    seen = week(app_conn, yard.clerk)
    assert [v["registration"] for v in seen["vehicles"]] == ["KDC 200B"]
    assert _figures(seen) == _figures(week(app_conn, yard.owner, company=yard.south))
    assert _figures(seen) != _figures(week(app_conn, yard.owner))
    shown = ("captured_today", "vehicles_today", "missing_days", "missing_vehicles")
    for period in ("today", "week", "month"):
        cards = dashboard(app_conn, yard.clerk, period)
        south = dashboard(app_conn, yard.owner, period, yard.south)
        assert {key: cards[key] for key in shown} == {key: south[key] for key in shown}
    assert (
        dashboard(app_conn, yard.clerk, "week")["missing_days"]
        != (dashboard(app_conn, yard.owner, "week")["missing_days"])
    )


def test_a_company_filter_narrows_the_grid_and_its_figures(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    _history(owner_conn, yard)
    south = week(app_conn, yard.owner, company=yard.south)
    assert [v["registration"] for v in south["vehicles"]] == ["KDC 200B"]
    assert (south["total_amount"], south["total_expected"], south["percent"]) == (700, 3000, 23)
    assert south["first_gap"] == {"vehicle_id": str(yard.kdc), "day": "2026-10-01"}


def test_an_archived_company_is_offered_only_while_a_vehicle_of_it_runs_that_week(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    owner_conn.execute(
        "UPDATE setup.psv_companies SET archived_on = %s WHERE id = %s",
        (date(2026, 10, 8), yard.south),
    )
    names = [c["name"] for c in week(app_conn, yard.owner)["companies"]]
    assert names == ["North Star", "South Line"]
    owner_conn.execute(
        "UPDATE setup.fleet_vehicles SET left_on = %s WHERE id = %s",
        (OCT1 + timedelta(days=2), yard.kdc),
    )
    names = [c["name"] for c in week(app_conn, yard.owner)["companies"]]
    assert names == ["North Star"]


def test_viewing_the_week_needs_revenue_view(app_conn: Conn, owner_conn: Conn, yard: Yard) -> None:
    set_override(owner_conn, yard.clerk, "revenue.view", False)
    refuses(
        app_conn,
        "revenue_week_get",
        yard.clerk,
        [None, None, None, 0, None, None],
        "XC403",
        "permission_missing",
    )


# --- the dashboard -------------------------------------------------------------------------


_CARDS = {
    "week": {
        "revenue": 4200,
        "expected": 9000,
        "percent": 47,
        "captured_today": 1,
        "vehicles_today": 2,
        "missing_days": 4,
        "missing_vehicles": 3,
        "edited_records": 1,
    },
    "month": {
        "revenue": 6200,
        "expected": 17000,
        "percent": 36,
        "captured_today": 1,
        "vehicles_today": 2,
        "missing_days": 10,
        "missing_vehicles": 3,
        "edited_records": 1,
    },
    "today": {
        "revenue": 1100,
        "expected": 1000,
        "percent": 110,
        "captured_today": 1,
        "vehicles_today": 2,
        "missing_days": 0,
        "missing_vehicles": 0,
        "edited_records": 0,
    },
}


@pytest.mark.parametrize(
    ("period", "start"), [("today", TODAY), ("week", WEEK), ("month", OCT1), (None, WEEK)]
)
def test_the_dashboard_sums_the_period_through_the_business_date(
    app_conn: Conn, owner_conn: Conn, yard: Yard, period: str | None, start: date
) -> None:
    _history(owner_conn, yard)
    cards = dashboard(app_conn, yard.owner, period)
    assert set(cards) == {
        "period",
        "from_date",
        "through",
        "business_date",
        "revenue",
        "expected",
        "percent",
        "captured_today",
        "vehicles_today",
        "missing_days",
        "missing_vehicles",
        "edited_records",
    }
    assert (cards["period"], cards["from_date"], cards["through"], cards["business_date"]) == (
        period or "week",
        start.isoformat(),
        "2026-10-09",
        "2026-10-09",
    )
    assert {key: cards[key] for key in _CARDS["week"]} == _CARDS[period or "week"]


@pytest.mark.parametrize(
    ("member", "shown"),
    [
        ("owner", {"revenue", "capture", "gaps", "edits"}),
        ("clerk", {"capture", "gaps"}),
        ("admin", {"revenue", "capture", "gaps", "edits"}),
    ],
)
def test_each_card_needs_its_own_permission(
    app_conn: Conn, owner_conn: Conn, yard: Yard, member: str, shown: set[str]
) -> None:
    _history(owner_conn, yard)
    cards = dashboard(app_conn, getattr(yard, member), "month")
    groups = {
        "revenue": ("revenue", "expected", "percent"),
        "capture": ("captured_today", "vehicles_today"),
        "gaps": ("missing_days", "missing_vehicles"),
        "edits": ("edited_records",),
    }
    for group, keys in groups.items():
        for key in keys:
            expected = _CARDS["month"][key] if group in shown else None
            assert cards[key] == expected, key
    assert cards["from_date"] == OCT1.isoformat()


def test_the_company_filter_narrows_the_cards(app_conn: Conn, owner_conn: Conn, yard: Yard) -> None:
    _history(owner_conn, yard)
    cards = dashboard(app_conn, yard.owner, "week", yard.south)
    assert {key: cards[key] for key in _CARDS["week"]} == {
        "revenue": 700,
        "expected": 3000,
        "percent": 23,
        "captured_today": 0,
        "vehicles_today": 0,
        "missing_days": 2,
        "missing_vehicles": 1,
        "edited_records": 0,
    }
    assert dashboard(app_conn, yard.owner, "today", yard.south)["expected"] == 0


def test_the_dashboard_is_refused_without_a_card_and_before_the_period_is_read(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    set_override(owner_conn, yard.clerk, "dash.gaps", False)
    refuses(
        app_conn,
        "revenue_dashboard_get",
        yard.clerk,
        ["year", None],
        "XC403",
        "permission_missing",
    )
    for period in ("year", "", "Week"):
        refuses(
            app_conn,
            "revenue_dashboard_get",
            yard.owner,
            [period, None],
            "XC422",
            "dashboard_period_invalid",
        )
    stranger = seed_organization(owner_conn)
    refused(
        app_conn,
        "revenue_dashboard_get",
        [stranger.user, yard.owner.org, REQUEST, "week", None, T0],
        "XC403",
        "not_member",
    )


# --- low days, the gap, the search and the back-dating limit -----------------------------


def test_a_low_day_needs_a_reason(app_conn: Conn, owner_conn: Conn, yard: Yard) -> None:
    org = yard.owner.org
    owner_conn.execute(
        "DELETE FROM tenancy.organization_revenue_settings WHERE organization_id = %s", (org,)
    )
    error = capture_refused(
        app_conn, yard.owner, yard.kda, TODAY, "3999.99", None, None, None,
        "XC422", "revenue_low_needs_reason",
    )  # fmt: skip
    assert detail(error) == {"currency": "KES", "threshold": "4,000"}
    error = capture_refused(
        app_conn, yard.owner, yard.kda, TODAY, 4000, "Garage", None, None,
        "XC422", "revenue_amount_with_reason",
    )  # fmt: skip
    assert detail(error) == {"currency": "KES", "threshold": "4,000"}
    low = capture(app_conn, yard.owner, yard.kda, TODAY, "3999.99", "Garage")
    assert capture(app_conn, yard.owner, yard.kda, OCT1, 4000)["outcome"] == "created"
    alone = capture(app_conn, yard.owner, yard.kdb, TODAY, 0, "No Crew")
    other = capture(app_conn, yard.owner, yard.kda, date(2026, 10, 2), None, "Other", "  ")
    assert {low["outcome"], alone["outcome"], other["outcome"]} == {"created"}
    rows = [
        record_row(owner_conn, vehicle, day)
        for vehicle, day in ((yard.kda, TODAY), (yard.kdb, TODAY), (yard.kda, date(2026, 10, 2)))
    ]
    assert [(r["amount"], r["reason"], r["note"]) for r in rows if r is not None] == [
        (Decimal("3999.99"), 1, None),
        (None, 3, None),
        (None, 4, None),
    ]
    logs = [log["reason"] for log in change_rows(owner_conn, org, "revenue")]
    assert logs[0] == "Recorded revenue for KDA 482M on 9 Oct 2026: Garage"
    assert logs[2] == "Recorded no revenue for KDB 111A on 9 Oct 2026: No Crew"
    set_threshold(owner_conn, org, 3000)
    assert capture(app_conn, yard.owner, yard.kdb, TODAY - timedelta(days=1), 3500)["outcome"] == (
        "created"
    )
    capture_refused(
        app_conn, yard.owner, yard.kda, date(2026, 10, 3), 2999, None, None, None,
        "XC422", "revenue_low_needs_reason",
    )  # fmt: skip


def _low_week(owner_conn: Conn, yard: Yard) -> None:
    """KDA: 5,000 on 5 Oct, Garage alone on 6, 3,500 without a reason (saved before the rule)
    on 7, 3,500 with Garage on 8, nothing yet today; KDB: 4,000 on 7 Oct, nothing on 8."""
    org, by = yard.owner.org, yard.owner.id
    add_record(owner_conn, org, yard.kda, date(2026, 10, 5), 5000, recorder=by)
    add_record(owner_conn, org, yard.kda, date(2026, 10, 6), None, recorder=by, reason=1)
    add_record(owner_conn, org, yard.kda, date(2026, 10, 7), 3500, recorder=by)
    add_record(owner_conn, org, yard.kda, date(2026, 10, 8), 3500, recorder=by, reason=1)
    add_record(owner_conn, org, yard.kdb, date(2026, 10, 7), 4000, recorder=by)


def test_below_threshold_days_count_low_and_no_revenue_days(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    set_threshold(owner_conn, yard.owner.org, 4000)
    _low_week(owner_conn, yard)
    grid = week(app_conn, yard.owner)
    kda, kdb, kdc = grid["vehicles"]
    assert [(v["below_threshold_days"], v["total_amount"]) for v in (kda, kdb, kdc)] == [
        (3, 12000),
        (0, 4000),
        (0, 0),
    ]
    assert [c["status"] for c in kda["days"][:4]] == ["amount", "reason", "amount", "amount"]
    assert (kda["days"][3]["amount"], kda["days"][3]["reason"]) == (3500, "Garage")
    assert (grid["below_threshold_days"], grid["missing_days"]) == (3, 4)
    assert (grid["low_day_threshold"], grid["gap_amber_percent"]) == (4000, 10)
    set_threshold(owner_conn, yard.owner.org, 3000)
    assert week(app_conn, yard.owner)["below_threshold_days"] == 1


def test_capture_fills_and_correct_changes(app_conn: Conn, owner_conn: Conn, yard: Yard) -> None:
    yesterday = TODAY - timedelta(days=1)
    capture(app_conn, yard.clerk, yard.kda, TODAY, 500)
    capture_refused(
        app_conn, yard.clerk, yard.kda, TODAY, 600, None, None, 1,
        "XC403", "revenue_correct_permission", now=at(1),
    )  # fmt: skip
    capture_refused(
        app_conn, yard.admin, yard.kda, yesterday, 600, None, None, None,
        "XC403", "revenue_capture_permission",
    )  # fmt: skip
    assert capture(app_conn, yard.admin, yard.kda, TODAY, 600, version=1, now=at(2))["version"] == 2
    set_limit(owner_conn, yard.clerk, "days", 1)
    set_limit(owner_conn, yard.admin, "days", 1)
    clerk = week(app_conn, yard.clerk)["vehicles"][0]["days"]
    admin = week(app_conn, yard.admin)["vehicles"][0]["days"]
    # 5 to 7 Oct are before the limit; 8 Oct is missing, today is saved.
    assert [c["can_edit"] for c in clerk] == [False, False, False, True, False, False, False]
    assert [c["can_edit"] for c in admin] == [False, False, False, False, True, False, False]


def test_capture_and_change_respect_the_back_limit(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    set_limit(owner_conn, yard.clerk, "days", 2)
    error = capture_refused(
        app_conn, yard.clerk, yard.kda, date(2026, 10, 6), 500, None, None, None,
        "XC422", "record_too_old",
    )  # fmt: skip
    assert detail(error) == {"earliest": "2026-10-07"}
    assert record_row(owner_conn, yard.kda, date(2026, 10, 6)) is None
    assert capture(app_conn, yard.clerk, yard.kda, date(2026, 10, 7), 500)["outcome"] == "created"
    # The permission answers before the limit, and the limit before the version.
    set_limit(owner_conn, yard.admin, "days", 0)
    capture_refused(
        app_conn, yard.admin, yard.kda, OCT1, 500, None, None, None,
        "XC403", "revenue_capture_permission",
    )  # fmt: skip
    error = capture_refused(
        app_conn, yard.admin, yard.kda, date(2026, 10, 7), 600, None, None, 99,
        "XC422", "record_too_old",
    )  # fmt: skip
    assert detail(error) == {"earliest": "2026-10-09"}
    set_limit(owner_conn, yard.admin, "none", None, date(2026, 10, 8))
    capture_refused(
        app_conn, yard.admin, yard.kda, date(2026, 10, 7), 600, None, None, 1,
        "XC422", "record_too_old",
    )  # fmt: skip
    set_limit(owner_conn, yard.admin, "none")
    assert (
        capture(app_conn, yard.admin, yard.kda, date(2026, 10, 7), 600, version=1)["version"] == 2
    )


def test_an_offline_replay_is_checked_at_its_capture_time_within_72_hours(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    set_limit(owner_conn, yard.clerk, "days", 0)
    later = T0 + timedelta(days=2)
    error = capture_refused(
        app_conn, yard.clerk, yard.kda, TODAY, 500, None, None, None,
        "XC422", "record_too_old", now=later,
    )  # fmt: skip
    assert detail(error) == {"earliest": "2026-10-11"}
    saved = capture(app_conn, yard.clerk, yard.kda, TODAY, 500, captured_at=T0, now=later)
    assert saved["outcome"] == "created"
    # A claimed time older than 72 hours counts as 72 hours before the request (8 Oct).
    error = capture_refused(
        app_conn, yard.clerk, yard.kda, date(2026, 10, 7), 500, None, None, None,
        "XC422", "record_too_old", captured_at=T0 - timedelta(days=5), now=later,
    )  # fmt: skip
    assert detail(error) == {"earliest": "2026-10-08"}
    old = capture(
        app_conn, yard.clerk, yard.kda, date(2026, 10, 8), 500,
        captured_at=T0 - timedelta(days=5), now=later,
    )  # fmt: skip
    assert old["outcome"] == "created"
    # A time after the request counts as the request's.
    error = capture_refused(
        app_conn, yard.clerk, yard.kda, date(2026, 10, 10), 500, None, None, None,
        "XC422", "record_too_old", captured_at=later + timedelta(days=5), now=later,
    )  # fmt: skip
    assert detail(error) == {"earliest": "2026-10-11"}


def test_the_capture_time_is_read_on_the_organizations_calendar(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    """00:30 on 10 Oct in Nairobi is 21:30 UTC on 9 Oct: a today-only clerk is on 10 Oct, and an
    entry the phone captured at 23:59 Nairobi time still belongs to 9 Oct."""
    set_limit(owner_conn, yard.clerk, "days", 0)
    after_midnight = datetime(2026, 10, 9, 21, 30, tzinfo=T0.tzinfo)
    before_midnight = datetime(2026, 10, 9, 20, 59, tzinfo=T0.tzinfo)
    error = capture_refused(
        app_conn, yard.clerk, yard.kda, TODAY, 500, None, None, None,
        "XC422", "record_too_old", now=after_midnight,
    )  # fmt: skip
    assert detail(error) == {"earliest": "2026-10-10"}
    saved = capture(
        app_conn, yard.clerk, yard.kda, TODAY, 500, captured_at=before_midnight, now=after_midnight
    )
    assert saved["outcome"] == "created"
    set_localization(owner_conn, yard.owner.org, time_zone="America/New_York")
    # The same instants are 17:30 and 16:59 on 9 Oct in New York: both today.
    assert capture(app_conn, yard.clerk, yard.kdb, TODAY, 500, now=after_midnight)["outcome"] == (
        "created"
    )


def test_an_identical_replay_is_answered_whatever_the_limit(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    stored = capture(app_conn, yard.clerk, yard.kda, OCT1, None, "Garage", now=at(0))
    set_limit(owner_conn, yard.clerk, "days", 0)
    replay = capture(app_conn, yard.clerk, yard.kda, OCT1, None, "Garage", version=5, now=at(1))
    assert replay == {**stored, "outcome": "replayed"}
    capture_refused(
        app_conn, yard.clerk, yard.kda, OCT1, None, "Arrest", None, 1,
        "XC403", "revenue_correct_permission", now=at(2),
    )  # fmt: skip


def test_an_identical_replay_is_answered_whatever_the_threshold(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    org = yard.owner.org
    low = capture(app_conn, yard.clerk, yard.kda, OCT1, 3000)
    garage = capture(app_conn, yard.clerk, yard.kda, date(2026, 10, 2), 50, "Garage")
    set_threshold(owner_conn, org, 4000)
    replay = capture(app_conn, yard.clerk, yard.kda, OCT1, 3000, version=7)
    assert replay == {**low, "outcome": "replayed"}
    capture_refused(
        app_conn, yard.owner, yard.kda, OCT1, 2999, None, None, 1,
        "XC422", "revenue_low_needs_reason",
    )  # fmt: skip
    set_threshold(owner_conn, org, 40)
    replay = capture(app_conn, yard.clerk, yard.kda, date(2026, 10, 2), 50, "Garage")
    assert replay == {**garage, "outcome": "replayed"}
    capture_refused(
        app_conn, yard.owner, yard.kda, date(2026, 10, 2), 51, "Garage", None, 1,
        "XC422", "revenue_amount_with_reason",
    )  # fmt: skip
    assert len(change_rows(owner_conn, org, "revenue")) == 2


def test_the_week_search_matches_registration_or_fleet_number(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    _history(owner_conn, yard)
    for vehicle, fleet in ((yard.kda, "14"), (yard.kdb, "A_7%")):
        owner_conn.execute(
            "UPDATE setup.fleet_vehicles SET fleet_number = %s WHERE id = %s", (fleet, vehicle)
        )
    for q, shown in (
        ("kda", ["KDA 482M"]),
        ("  2", ["KDA 482M", "KDC 200B"]),
        ("14", ["KDA 482M"]),
        ("_", ["KDB 111A"]),
        ("%", ["KDB 111A"]),
        ("a_7", ["KDB 111A"]),
        ("x", []),
        ("", ["KDA 482M", "KDB 111A", "KDC 200B"]),
    ):
        grid = week(app_conn, yard.owner, q=q)
        assert [v["registration"] for v in grid["vehicles"]] == shown, q
        assert grid["total_vehicles"] == len(shown)
    found = week(app_conn, yard.owner, q="KDB", page=1, size=1)
    assert [v["fleet_number"] for v in found["vehicles"]] == ["A_7%"]
    assert (found["total_amount"], found["total_expected"]) == (500, 1000)
    refuses(
        app_conn,
        "revenue_week_get",
        yard.owner,
        [None, None, None, None, None, "x" * 41],
        "XC422",
        "revenue_search_length",
    )
    assert week(app_conn, yard.owner, q="x" * 40)["vehicles"] == []


def test_the_search_finds_only_vehicles_the_viewer_may_see(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    """A scoped clerk finds no hidden vehicle by its registration or fleet number, and another
    organization's search finds and counts only its own vehicles."""
    _history(owner_conn, yard)
    owner_conn.execute(
        "UPDATE setup.fleet_vehicles SET fleet_number = '14' WHERE id = %s", (yard.kda,)
    )
    set_scope(owner_conn, yard.clerk, yard.owner.org, companies=[yard.south])
    for q in ("KDA", "14", "482"):
        hidden = week(app_conn, yard.clerk, q=q)
        assert hidden["vehicles"] == [], q
        assert [hidden[key] for key in ("total_vehicles", "total_amount", "gap")] == [0, 0, 0], q
        assert (hidden["below_threshold_days"], hidden["missing_days"]) == (0, 0), q
    shown = week(app_conn, yard.clerk, q="KD")
    assert [v["registration"] for v in shown["vehicles"]] == ["KDC 200B"]
    assert _figures(shown) == _figures(week(app_conn, yard.owner, company=yard.south))
    other = seed_organization(owner_conn)
    stranger = Member(other.user, other.org, "", "", "Sam", "Stranger", "Owner")
    found = week(app_conn, stranger, q="KDA 482M")
    assert [UUID(v["id"]) for v in found["vehicles"]] == [other.vehicle]
    assert found["total_vehicles"] == 1
    assert week(app_conn, stranger, q="KDC")["total_vehicles"] == 0


def test_the_week_carries_the_gap_and_its_band(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    _history(owner_conn, yard)
    grid = week(app_conn, yard.owner)
    kda, kdb, kdc = grid["vehicles"]
    # Today counts for KDA (recorded) and not for KDB (not yet); KDC left on 8 Oct.
    assert [(v["gap"], v["gap_band"]) for v in (kda, kdb, kdc)] == [
        (-2000, "red"),
        (-500, "red"),
        (-2300, "red"),
    ]
    assert (grid["gap"], grid["gap_band"]) == (-4800, "red")
    assert [c["expected"] for c in kdb["days"]] == [0, 0, 500, 500, 500, 500, 500]
    set_threshold(owner_conn, yard.owner.org, 100, 50)
    add_record(owner_conn, yard.owner.org, yard.kdb, date(2026, 10, 8), 600, recorder=yard.owner.id)
    grid = week(app_conn, yard.owner)
    kda, kdb, kdc = grid["vehicles"]
    assert [(v["gap"], v["gap_band"]) for v in (kda, kdb, kdc)] == [
        (-2000, "amber"),
        (100, "green"),
        (-2300, "red"),
    ]
    assert grid["gap_amber_percent"] == 50


# --- the revenue settings -------------------------------------------------------------------


def _save_settings(
    app: Conn, who: Member, value: Any, *, now: datetime = T0, version: int | None = None
) -> dict[str, Any]:
    return run(
        app, "organization_settings_set", who, "revenue", Jsonb(value), None, version, now=now
    )


def test_the_revenue_settings_default_save_and_log_in_the_organization_section(
    app_conn: Conn, owner_conn: Conn, yard: Yard
) -> None:
    org = yard.owner.org
    owner_conn.execute(
        "DELETE FROM tenancy.organization_revenue_settings WHERE organization_id = %s", (org,)
    )
    read_back = read(app_conn, "organization_settings_get", yard.owner)["revenue"]
    assert read_back == {
        "organization_id": str(org),
        "low_day_threshold": 4000,
        "gap_amber_percent": 10,
    }
    saved = _save_settings(app_conn, yard.owner, {"low_day_threshold": 3500.5}, now=at(1))
    assert saved["outcome"] == "updated"
    read_back = read(app_conn, "organization_settings_get", yard.owner)["revenue"]
    assert (read_back["low_day_threshold"], read_back["gap_amber_percent"]) == (3500.5, 10)
    [log] = change_rows(owner_conn, org, "organization")
    assert log["reason"] == (
        "Changed the low-day threshold to KES 3,500.50 and the amber band to 10 per cent"
    )
    assert (log["vehicle_id"], json.loads(log["before"])) == (None, None)
    assert json.loads(log["after"]) == {
        "organizationId": str(org),
        "lowDayThreshold": 3500.5,
        "gapAmberPercent": 10,
    }
    same = _save_settings(app_conn, yard.owner, {"low_day_threshold": 3500.50}, now=at(2))
    assert same["outcome"] == "unchanged"
    moved = _save_settings(app_conn, yard.owner, {"gap_amber_percent": 12.5}, now=at(3))
    assert moved["outcome"] == "updated"
    assert change_rows(owner_conn, org, "organization")[-1]["reason"] == (
        "Changed the amber band to 12.5 per cent"
    )
    assert change_rows(owner_conn, org, "revenue") == []


@pytest.mark.parametrize(
    ("value", "code"),
    [
        ({"low_day_threshold": -1}, "revenue_settings_invalid"),
        ({"low_day_threshold": 1000000000000}, "revenue_settings_invalid"),
        ({"low_day_threshold": 10.005}, "revenue_settings_invalid"),
        ({"gap_amber_percent": 100.01}, "revenue_settings_invalid"),
        ({"gap_amber_percent": -0.5}, "revenue_settings_invalid"),
        ({"low_day_threshold": "4000"}, "settings_wrong_type"),
        ({"gap_amber_percent": True}, "settings_wrong_type"),
        ({"low_day_threshold": None}, "settings_wrong_type"),
        ([4000], "settings_not_object"),
    ],
)
def test_revenue_settings_out_of_range_or_of_the_wrong_kind_are_refused(
    app_conn: Conn, owner_conn: Conn, yard: Yard, value: Any, code: str
) -> None:
    refuses(
        app_conn,
        "organization_settings_set",
        yard.owner,
        ["revenue", Jsonb(value), None, None],
        "XC422",
        code,
    )
    assert owner_conn.execute(
        "SELECT low_day_threshold FROM tenancy.organization_revenue_settings "
        "WHERE organization_id = %s",
        (yard.owner.org,),
    ).fetchone() == {"low_day_threshold": 100}


def test_only_owners_change_the_revenue_settings(app_conn: Conn, yard: Yard) -> None:
    for who in (yard.clerk, yard.admin):
        refuses(
            app_conn,
            "organization_settings_set",
            who,
            ["revenue", Jsonb({"low_day_threshold": 1}), None, None],
            "XC403",
            "permission_missing",
        )
