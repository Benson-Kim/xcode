"""The setup delete routes against the real database (``docs/06-http-contract.md`` rows S60 to
S64): a main category, category, item, vehicle or company nothing refers to answers ``{id}`` in
two statements and leaves a change-log entry; one in use answers 409 with the sentence that
says what uses it and what to do instead, and stays; another organization's record and a
malformed id are not found; a caller without the right gets 403, and no token 401."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any
from uuid import UUID

import pytest

from xcode_api.http.messages import IN_USE_TITLE

from ..support.client import ApiFactory, AuthApi
from ..support.rows import seed_organization
from ..support.setup_client import (
    FORBIDDEN,
    NOT_FOUND,
    Member,
    empty,
    join,
    ok,
    problem,
    statements,
)
from ..support.setup_rows import add_central_expense, add_record
from ..support.tenancy import set_organization

pytestmark = pytest.mark.asyncio(loop_scope="session")

PATHS = {
    "main_category": "/setup/expense-main-categories",
    "category": "/setup/expense-categories",
    "item": "/setup/expense-items",
    "vehicle": "/setup/vehicles",
    "company": "/setup/companies",
}
TABLES = {
    "main_category": "expense_main_categories",
    "category": "expense_categories",
    "item": "expense_items",
    "vehicle": "fleet_vehicles",
    "company": "psv_companies",
}


@dataclass(frozen=True, slots=True)
class Yard:
    org: UUID
    company: str
    spare: str
    vehicle: str
    main: str
    category: str
    item: str


@pytest.fixture
async def api(make_api: ApiFactory) -> AuthApi:
    return await make_api()


@pytest.fixture
async def owner(api: AuthApi) -> Member:
    return await join(api, email="ann@example.com", phone="0711000111", role="Owner")


async def _post(api: AuthApi, member: Member, path: str, body: dict[str, Any]) -> str:
    return str(ok(await api.client.post(path, json=body, headers=member.headers))["id"])


async def _vehicle(api: AuthApi, owner: Member, company: str, registration: str) -> str:
    body = {
        "companyId": company,
        "registration": registration,
        "fleetNumber": registration[-4:],
        "joinedOn": "2026-03-01",
        "dayTargets": [1000] * 7,
    }
    return await _post(api, owner, "/setup/vehicles", body)


@pytest.fixture
async def yard(api: AuthApi, owner: Member) -> Yard:
    row = api.owner.execute("SELECT id FROM tenancy.organizations").fetchone()
    assert row is not None
    org = UUID(str(row["id"]))
    set_organization(api.owner, org, business_date=date(2026, 3, 31))
    company = await _post(api, owner, "/setup/companies", {"name": "North Star"})
    spare = await _post(api, owner, "/setup/companies", {"name": "Spare Line"})
    vehicle = await _vehicle(api, owner, company, "KDA 482M")
    main = await _post(api, owner, "/setup/expense-main-categories", {"name": "Running"})
    category = await _post(
        api, owner, "/setup/expense-categories", {"name": "Fuel", "mainCategoryId": main}
    )
    item = await _post(
        api, owner, f"/setup/expense-categories/{category}/items", {"name": "Diesel"}
    )
    return Yard(org, company, spare, vehicle, main, category, item)


def _exists(api: AuthApi, record: str, record_id: str) -> bool:
    row = api.owner.execute(
        f"SELECT count(*) AS n FROM setup.{TABLES[record]} WHERE id = %s", (record_id,)
    ).fetchone()
    assert row is not None
    return bool(row["n"])


async def _history(api: AuthApi, member: Member, section: str) -> list[str]:
    page = ok(
        await api.client.get(
            f"/setup/history?section={section}&pageSize=100", headers=member.headers
        )
    )
    return [entry["reason"] for entry in reversed(page["items"])]


async def test_records_nothing_refers_to_are_deleted_and_logged(
    api: AuthApi, owner: Member, yard: Yard
) -> None:
    main = await _post(api, owner, "/setup/expense-main-categories", {"name": "Admin"})
    category = await _post(
        api, owner, "/setup/expense-categories", {"name": "Office", "mainCategoryId": main}
    )
    item = await _post(api, owner, f"/setup/expense-categories/{category}/items", {"name": "Paper"})
    vehicle = await _vehicle(api, owner, yard.spare, "KDC 200B")
    deletes = [
        ("item", item),
        ("category", category),
        ("main_category", main),
        ("vehicle", vehicle),
        ("company", yard.spare),
    ]
    for record, record_id in deletes:
        path = f"{PATHS[record]}/{record_id}"
        response, count = await statements(api.client.delete(path, headers=owner.headers))
        assert ok(response) == {"id": record_id}, record
        assert count == 2, record
        assert not _exists(api, record, record_id), record
        problem(await api.client.delete(path, headers=owner.headers), 404, NOT_FOUND)
    expenses = await _history(api, owner, "expenses")
    assert expenses[-3:] == [
        "Deleted expense item Paper",
        "Deleted expense category Office",
        "Deleted main category Admin",
    ]
    assert (await _history(api, owner, "vehicles"))[-1] == "Deleted vehicle KDC 200B"
    assert (await _history(api, owner, "companies"))[-1] == "Deleted company Spare Line"


async def test_a_record_in_use_answers_409_with_what_uses_it_and_stays(
    api: AuthApi, owner: Member, yard: Yard
) -> None:
    add_central_expense(
        api.owner, yard.org, UUID(yard.vehicle), UUID(yard.item), recorder=owner.user_id
    )
    other = await _vehicle(api, owner, yard.company, "KDB 111A")
    add_record(api.owner, yard.org, UUID(other), date(2026, 3, 2), 1500, recorder=owner.user_id)
    cases = [
        ("main_category", yard.main, "Running has categories: delete or move them first."),
        ("category", yard.category, "Fuel has items: delete them first, or stop it instead."),
        ("item", yard.item, "Diesel is used by expenses: stop it instead."),
        ("vehicle", yard.vehicle, "KDA 482M has expenses: retire it instead."),
        ("vehicle", other, "KDB 111A has revenue entries: retire it instead."),
        (
            "company",
            yard.company,
            "North Star has vehicles: delete or move them first, or archive it instead.",
        ),
    ]
    for record, record_id, detail in cases:
        response, count = await statements(
            api.client.delete(f"{PATHS[record]}/{record_id}", headers=owner.headers)
        )
        body = problem(response, 409, IN_USE_TITLE, detail)
        assert "use" not in body and "name" not in body
        assert count == 1, record  # the gateway counts only the calls that answered
        assert _exists(api, record, record_id), record


async def test_each_delete_needs_its_right(api: AuthApi, owner: Member, yard: Yard) -> None:
    clerk = await join(api, email="clerk@example.com", phone="0744000111", role="Revenue clerk")
    records = {
        "main_category": await _post(
            api, owner, "/setup/expense-main-categories", {"name": "Spare"}
        ),
        "category": await _post(api, owner, "/setup/expense-categories", {"name": "Spare"}),
        "item": await _post(
            api, owner, f"/setup/expense-categories/{yard.category}/items", {"name": "Petrol"}
        ),
        "vehicle": await _vehicle(api, owner, yard.spare, "KDC 200B"),
        "company": yard.spare,
    }
    for record, record_id in records.items():
        problem(
            await api.client.delete(f"{PATHS[record]}/{record_id}", headers=clerk.headers),
            403,
            FORBIDDEN,
        )
        assert _exists(api, record, record_id), record


async def test_another_organizations_records_are_not_found(
    api: AuthApi, owner: Member, yard: Yard
) -> None:
    other = seed_organization(api.owner)
    records = {
        "main_category": other.main_category,
        "category": other.category,
        "item": other.item,
        "vehicle": other.vehicle,
        "company": other.company,
    }
    for record, record_id in records.items():
        problem(
            await api.client.delete(f"{PATHS[record]}/{record_id}", headers=owner.headers),
            404,
            NOT_FOUND,
        )
        assert _exists(api, record, str(record_id)), record


async def test_a_malformed_id_is_an_empty_not_found_and_no_token_is_401(
    api: AuthApi, owner: Member, yard: Yard
) -> None:
    for path in PATHS.values():
        empty(await api.client.delete(f"{path}/not-a-uuid", headers=owner.headers), 404)
    for record, record_id in [("item", yard.item), ("vehicle", yard.vehicle)]:
        empty(await api.client.delete(f"{PATHS[record]}/{record_id}"), 401)
        assert _exists(api, record, record_id)
