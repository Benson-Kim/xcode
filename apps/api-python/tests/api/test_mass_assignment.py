"""Setup bodies carrying fields the contract does not bind: an id, the organization, a
version or revision, an archive or leave date, targets, away periods, who recorded an entry,
a stop date, the weekly target and bucket the v2.3 design ignores, another vehicle for a target
set, counts a list derives. As in .NET, which ignores unknown members, each is ignored: the
write succeeds and the stored row holds the server's values, in the caller's organization. Both
spellings are sent, the camelCase alias and the snake_case field name."""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID, uuid4

import pytest

from ..support.client import ApiFactory, AuthApi
from ..support.setup_client import Member, join, ok
from ..support.tenancy import add_company, add_vehicle

pytestmark = pytest.mark.asyncio(loop_scope="session")

FOREIGN = str(uuid4())
CHOSEN = str(uuid4())


def _both(**fields: Any) -> dict[str, Any]:
    """Each field under its camelCase name and its snake_case name."""
    body: dict[str, Any] = {}
    for name, value in fields.items():
        parts = name.split("_")
        body[parts[0] + "".join(p.title() for p in parts[1:])] = value
        body[name] = value
    return body


@pytest.fixture
async def api(make_api: ApiFactory) -> AuthApi:
    return await make_api()


@pytest.fixture
async def owner(api: AuthApi) -> Member:
    return await join(api, email="ann@example.com", phone="0711000111", role="Owner")


def _organization(api: AuthApi) -> UUID:
    row = api.owner.execute("SELECT id FROM tenancy.organizations").fetchone()
    assert row is not None
    return UUID(str(row["id"]))


def _row(api: AuthApi, table: str, id_: str) -> dict[str, Any]:
    row = api.owner.execute(f"SELECT * FROM setup.{table} WHERE id = %s", (id_,)).fetchone()
    assert row is not None
    return row


async def test_a_company_body_cannot_set_its_id_organization_or_archive_date(
    api: AuthApi, owner: Member
) -> None:
    extra = _both(
        id=CHOSEN,
        organization_id=FOREIGN,
        archived_on="2026-01-01",
        active=False,
        vehicle_count=9,
        version=7,
    )
    body = ok(
        await api.client.post(
            "/setup/companies", json={"name": "North Star", **extra}, headers=owner.headers
        )
    )
    assert body["id"] != CHOSEN
    row = _row(api, "psv_companies", body["id"])
    assert (row["organization_id"], row["name"], row["archived_on"]) == (
        _organization(api),
        "North Star",
        None,
    )


def _sets(api: AuthApi, vehicle: str) -> list[tuple[date, list[Any], Any]]:
    rows = api.owner.execute(
        "SELECT starts_on, ARRAY[monday, tuesday, wednesday, thursday, friday, saturday, "
        "sunday] AS days, created_by FROM setup.vehicle_target_sets WHERE vehicle_id = %s "
        "ORDER BY starts_on",
        (vehicle,),
    ).fetchall()
    return [(r["starts_on"], [int(d) for d in r["days"]], r["created_by"]) for r in rows]


DAYS = [1000, 1000, 1000, 1000, 1000, 1500, 500]


async def test_a_vehicle_body_cannot_set_its_leave_date_targets_or_away_periods(
    api: AuthApi, owner: Member
) -> None:
    north = add_company(api.owner, _organization(api), "North Star")
    extra = _both(
        id=CHOSEN,
        organization_id=FOREIGN,
        left_on="2026-10-02",
        active=False,
        weekly_target=99000,
        targets=[{"effectiveFrom": "2026-01-01", "weeklyAmount": 1, "revision": 9}],
        next_target={"startsOn": "2026-10-20", "dayTargets": [1] * 7, "weeklyTarget": 7},
        normalized_fleet_number="OTHER",
        away=[{"leftOn": "2026-10-02", "returnedOn": "2026-10-03"}],
        recurring_items=4,
    )
    save = {
        "companyId": str(north),
        "registration": "KDA 482M",
        "fleetNumber": "ns-01",
        "joinedOn": "2026-10-01",
        "dayTargets": DAYS,
    }
    body = ok(
        await api.client.post("/setup/vehicles", json={**save, **extra}, headers=owner.headers)
    )
    assert body["id"] != CHOSEN
    row = _row(api, "fleet_vehicles", body["id"])
    assert (row["organization_id"], row["left_on"]) == (_organization(api), None)
    assert (row["fleet_number"], row["normalized_fleet_number"]) == ("ns-01", "NS-01")
    assert _sets(api, body["id"]) == [(date(2026, 10, 1), DAYS, owner.user_id)]
    away = api.owner.execute(
        "SELECT count(*) AS n FROM setup.vehicle_away_periods WHERE vehicle_id = %s",
        (body["id"],),
    ).fetchone()
    assert away == {"n": 0}


async def test_an_investment_body_cannot_set_who_recorded_it_or_move_it_to_another_vehicle(
    api: AuthApi, owner: Member
) -> None:
    org = _organization(api)
    north = add_company(api.owner, org, "North Star")
    kda = add_vehicle(api.owner, org, north, "KDA 482M")
    kdb = add_vehicle(api.owner, org, north, "KDB 111A")
    extra = _both(
        id=CHOSEN,
        vehicle_id=str(kdb),
        recorded_by=FOREIGN,
        recorded_at="2020-01-01T00:00:00+00:00",
        organization_id=FOREIGN,
    )
    body = ok(
        await api.client.post(
            f"/setup/vehicles/{kda}/investment",
            json={"date": "2026-10-01", "description": "Deposit", "amount": 100, **extra},
            headers=owner.headers,
        )
    )
    assert body["id"] != CHOSEN
    row = _row(api, "vehicle_investments", body["id"])
    assert (row["organization_id"], row["vehicle_id"], row["recorded_by"]) == (
        org,
        kda,
        owner.user_id,
    )
    assert row["recorded_at"].year == 2026


async def test_a_target_set_body_cannot_move_it_to_another_vehicle_or_name_its_author(
    api: AuthApi, owner: Member
) -> None:
    org = _organization(api)
    north = add_company(api.owner, org, "North Star")
    kda = str(add_vehicle(api.owner, org, north, "KDA 482M"))
    kdb = str(add_vehicle(api.owner, org, north, "KDB 111A"))
    extra = _both(
        id=CHOSEN,
        vehicle_id=kdb,
        organization_id=FOREIGN,
        created_by=FOREIGN,
        week_total=1,
        in_force=True,
        can_remove=False,
    )
    body = ok(
        await api.client.post(
            f"/setup/vehicles/{kda}/targets",
            json={"startsOn": "2026-10-20", "days": DAYS, **extra},
            headers=owner.headers,
        )
    )
    assert body["id"] != CHOSEN
    assert _sets(api, kda) == [(date(2026, 10, 20), DAYS, owner.user_id)]
    assert _sets(api, kdb) == []


async def test_a_main_category_body_cannot_set_its_id_organization_or_counts(
    api: AuthApi, owner: Member
) -> None:
    extra = _both(
        id=CHOSEN, organization_id=FOREIGN, category_count=9, item_count=9, normalized_name="X"
    )
    body = ok(
        await api.client.post(
            "/setup/expense-main-categories",
            json={"name": "Repairs", **extra},
            headers=owner.headers,
        )
    )
    assert body["id"] != CHOSEN
    row = api.owner.execute(
        "SELECT organization_id, name, normalized_name FROM setup.expense_main_categories "
        "WHERE id = %s",
        (body["id"],),
    ).fetchone()
    assert row == {
        "organization_id": _organization(api),
        "name": "Repairs",
        "normalized_name": "REPAIRS",
    }


async def test_a_category_body_bucket_is_accepted_and_ignored(api: AuthApi, owner: Member) -> None:
    extra = _both(id=CHOSEN, organization_id=FOREIGN, bucket=3, main_category_name="Loans")
    body = ok(
        await api.client.post(
            "/setup/expense-categories",
            json={"name": "Bank loans", "mainCategoryId": None, **extra},
            headers=owner.headers,
        )
    )
    assert body["id"] != CHOSEN
    row = _row(api, "expense_categories", body["id"])
    assert (row["organization_id"], row["bucket"], row["main_category_id"]) == (
        _organization(api),
        None,
        None,
    )


async def test_a_scheduled_item_body_cannot_set_its_stop_revision_or_bucket(
    api: AuthApi, owner: Member
) -> None:
    org = _organization(api)
    north = add_company(api.owner, org, "North Star")
    kda = add_vehicle(api.owner, org, north, "KDA 482M")
    extra = _both(
        id=CHOSEN,
        version_id=CHOSEN,
        revision=9,
        stopped_from="2026-10-02",
        partial=True,
        active_amount=1,
        bucket=3,
        organization_id=FOREIGN,
    )
    saving = {
        "name": "Owner savings",
        "kind": 2,
        "amount": 1000,
        "frequency": 3,
        "day": 15,
        "lastDay": False,
        "start": "2026-10-01",
        "allocations": [{"vehicleId": str(kda), "amount": 1000}],
    }
    body = ok(
        await api.client.post("/setup/recurring", json={**saving, **extra}, headers=owner.headers)
    )
    assert body["id"] != CHOSEN
    item = _row(api, "recurring_items", body["id"])
    assert (item["organization_id"], item["stopped_from"]) == (org, None)
    versions = api.owner.execute(
        "SELECT id, revision, bucket FROM setup.recurring_versions WHERE item_id = %s",
        (body["id"],),
    ).fetchall()
    assert [(v["revision"], v["bucket"]) for v in versions] == [(1, None)]
    assert str(versions[0]["id"]) != CHOSEN
