"""The contract the released clients were built against (the .NET ``Phase1ContractTests``):
every check reads the raw JSON, so a renamed, re-cased, removed or retyped property or a
changed status fails here while new properties are allowed. The auth, appearance, catalogue,
fleet (companies, vehicles, scheduled items, the vehicle report), people, organization settings,
preferences and revenue (the v2.11 phone's capture queue and week) rows are in place."""

from __future__ import annotations

import base64
import json
from collections.abc import Mapping
from datetime import date
from typing import Any
from urllib.parse import quote
from uuid import UUID

import httpx
import pytest

from ..support.client import DEVICE, PHONE, PIN, ApiFactory, AuthApi, code_of, envelope
from ..support.setup_client import Member, join, ok
from ..support.tenancy import add_company, add_vehicle, set_scope

pytestmark = pytest.mark.asyncio(loop_scope="session")

PNG = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)
_KINDS: dict[str, type | tuple[type, ...]] = {
    "str": str,
    "num": (int, float),
    "null": type(None),
    "arr": list,
    "obj": dict,
}


def has(parent: Mapping[str, Any], name: str, *kinds: str) -> Any:
    """``Phase1.Has``: the property exists under exactly this name with one of the JSON kinds
    ``str``, ``num``, ``bool``, ``null``, ``arr``, ``obj``."""
    assert name in parent, f"{name!r} missing from {sorted(parent)}"
    value = parent[name]
    if isinstance(value, bool):
        assert "bool" in kinds, (name, value)
    else:
        assert any(isinstance(value, _KINDS[kind]) for kind in kinds if kind != "bool"), (
            name,
            value,
        )
    return value


def problem(response: httpx.Response) -> dict[str, Any]:
    """``Phase1.Problem``: a problem body with a string ``title`` and, when present, a
    ``detail`` that is a string or null."""
    assert response.headers["content-type"] == "application/problem+json"
    body: dict[str, Any] = json.loads(response.content)
    has(body, "title", "str")
    if "detail" in body:
        has(body, "detail", "str", "null")
    return body


def jwt_payload(token: str) -> dict[str, Any]:
    parts = token.split(".")
    assert len(parts) == 3
    padded = parts[1] + "=" * (-len(parts[1]) % 4)
    payload: dict[str, Any] = json.loads(base64.urlsafe_b64decode(padded))
    return payload


@pytest.fixture
async def api(make_api: ApiFactory) -> AuthApi:
    return await make_api()


@pytest.fixture
async def owner(api: AuthApi) -> Member:
    return await join(api, email="ann@example.com", phone="0711000111", role="Owner")


@pytest.fixture
async def clerk(api: AuthApi, owner: Member) -> Member:
    return await join(api, email="clerk@example.com", phone="0722000111", role="Revenue clerk")


# --- Phase1AuthContractTests ---------------------------------------------------------------


async def test_sign_in_and_unlock_on_a_trusted_phone(api: AuthApi) -> None:
    await api.onboard()
    for path in ("/auth/sign-in", "/auth/unlock"):
        data = envelope(
            await api.post(path, phoneNumber=PHONE, pin=PIN, deviceId=DEVICE), 200, "authenticated"
        )
        has(jwt_payload(has(data, "accessToken", "str")), "exp", "num")
        has(data, "refreshToken", "str")
        envelope(
            await api.post(path, phoneNumber=PHONE, pin="9998", deviceId=DEVICE),
            401,
            "authentication_failed",
        )


async def test_an_incomplete_request_is_invalid(api: AuthApi) -> None:
    envelope(
        await api.post("/auth/sign-in", phoneNumber=PHONE, pin=PIN, deviceId=""),
        400,
        "invalid_request",
    )


async def test_a_locked_account_shows_the_paused_screen_on_its_trusted_phone(api: AuthApi) -> None:
    await api.onboard()
    for _ in range(4):
        envelope(await api.sign_in(pin="9998"), 401, "authentication_failed")
    paused = envelope(await api.sign_in(pin="9998"), 423, "paused")
    assert has(paused, "retryAfterSeconds", "num") > 0
    for path in ("/auth/sign-in", "/auth/unlock"):
        again = envelope(
            await api.post(path, phoneNumber=PHONE, pin=PIN, deviceId=DEVICE), 423, "paused"
        )
        assert has(again, "retryAfterSeconds", "num") > 0


async def test_a_v211_phone_trusted_by_device_id_signs_in_with_the_pin(api: AuthApi) -> None:
    user_id, _ = await api.onboard()
    for path in ("/auth/sign-in", "/auth/unlock"):
        data = envelope(
            await api.post(path, phoneNumber=PHONE, pin=PIN, deviceId=DEVICE), 200, "authenticated"
        )
        has(data, "accessToken", "str")
    row = api.owner.execute(
        "SELECT token_hash, remembered FROM identity.trusted_devices "
        "WHERE user_id = %s AND device_id = %s",
        (user_id, DEVICE),
    ).fetchone()
    assert row is not None and (row["token_hash"], row["remembered"]) == (None, True)


async def test_a_six_digit_pin_still_signs_in_from_a_v211_phone(api: AuthApi) -> None:
    user_id, _ = await api.onboard()
    longer = "582694"
    api.owner.execute(
        "UPDATE identity.users SET pin_hash = %s WHERE id = %s",
        (await api.container.pin_hasher.hash(longer), user_id),
    )
    envelope(await api.sign_in(pin=longer), 200, "authenticated")


async def test_a_new_pin_of_six_digits_is_refused_with_minimum_four(api: AuthApi) -> None:
    user_id = api.provision()
    api.owner.execute(
        "UPDATE tenancy.organization_security_policies SET pin_length = 6 "
        "WHERE organization_id = (SELECT organization_id FROM tenancy.memberships "
        "WHERE user_id = %s)",
        (user_id,),
    )
    envelope(
        await api.post("/auth/setup-pin/request", phoneNumber=PHONE, deviceId=DEVICE),
        202,
        "check_email",
    )
    await api.delivered(1)
    code = code_of(api.mail.sent[-1].text)
    refused = envelope(
        await api.post(
            "/auth/setup-pin/complete", phoneNumber=PHONE, pin="582694", code=code, deviceId=DEVICE
        ),
        400,
        "invalid_pin",
    )
    assert has(refused, "minimumPinLength", "num") == 4


async def test_the_third_wrong_code_brings_a_new_code_the_phone_can_use(api: AuthApi) -> None:
    await api.onboard()
    envelope(await api.sign_in(device="new-phone"), 202, "verification_required")
    first = code_of(api.mail.sent[-1].text)
    sent = len(api.mail.sent)
    wrong = "111111" if first != "111111" else "222222"
    for _ in range(3):
        envelope(
            await api.post(
                "/auth/verify-device", phoneNumber=PHONE, code=wrong, deviceId="new-phone"
            ),
            401,
            "authentication_failed",
        )
    await api.delivered(sent + 1)
    replacement = code_of(api.mail.sent[-1].text)
    envelope(
        await api.post("/auth/verify-device", phoneNumber=PHONE, code=first, deviceId="new-phone"),
        401,
        "authentication_failed",
    )
    envelope(
        await api.post(
            "/auth/verify-device", phoneNumber=PHONE, code=replacement, deviceId="new-phone"
        ),
        200,
        "authenticated",
    )


async def test_refresh_is_refused_while_the_pin_is_locked_on_every_device(api: AuthApi) -> None:
    _, first = await api.onboard()
    for _ in range(5):
        await api.sign_in(pin="9998")
    envelope(
        await api.post("/auth/refresh", refreshToken=first["refreshToken"], deviceId=DEVICE),
        401,
        "authentication_failed",
    )


async def test_a_new_phone_verifies_with_an_email_code(api: AuthApi) -> None:
    await api.onboard()
    data = envelope(await api.sign_in(device="new-phone"), 202, "verification_required")
    assert "@example.com" in has(data, "maskedEmail", "str")
    has(data, "developmentCode", "str", "null")
    code = code_of(api.mail.sent[-1].text)
    if code != "000000":
        envelope(
            await api.post(
                "/auth/verify-device", phoneNumber=PHONE, code="000000", deviceId="new-phone"
            ),
            401,
            "authentication_failed",
        )
    verified = envelope(
        await api.post("/auth/verify-device", phoneNumber=PHONE, code=code, deviceId="new-phone"),
        200,
        "authenticated",
    )
    has(verified, "accessToken", "str")


async def test_a_first_pin_is_set_with_an_email_code(api: AuthApi) -> None:
    user_id = api.provision()
    envelope(
        await api.post("/auth/setup-pin/request", phoneNumber=PHONE, deviceId=DEVICE),
        202,
        "check_email",
    )
    await api.delivered(1)
    code = code_of(api.mail.sent[-1].text)
    wrong = "111111" if code != "111111" else "222222"
    envelope(
        await api.post("/auth/setup-pin/verify", phoneNumber=PHONE, code=wrong, deviceId=DEVICE),
        401,
        "authentication_failed",
    )
    envelope(
        await api.post("/auth/setup-pin/verify", phoneNumber=PHONE, code=code, deviceId=DEVICE),
        200,
        "code_verified",
    )
    short = envelope(
        await api.post(
            "/auth/setup-pin/complete", phoneNumber=PHONE, pin="1111", code=code, deviceId=DEVICE
        ),
        400,
        "invalid_pin",
    )
    assert has(short, "minimumPinLength", "num") == 4
    api.owner.execute(
        "UPDATE tenancy.organization_security_policies SET pin_length = 6 "
        "WHERE organization_id = (SELECT organization_id FROM tenancy.memberships "
        "WHERE user_id = %s)",
        (user_id,),
    )
    # Changed on purpose (v2.33): every new PIN is four digits whatever the organization's
    # PIN length, and the phone is told the floor of four it already shows.
    longer = envelope(
        await api.post(
            "/auth/setup-pin/complete", phoneNumber=PHONE, pin="582694", code=code, deviceId=DEVICE
        ),
        400,
        "invalid_pin",
    )
    assert has(longer, "minimumPinLength", "num") == 4
    envelope(
        await api.post(
            "/auth/setup-pin/complete", phoneNumber=PHONE, pin="5826", code=wrong, deviceId=DEVICE
        ),
        401,
        "authentication_failed",
    )
    envelope(
        await api.post(
            "/auth/setup-pin/complete", phoneNumber=PHONE, pin="5826", code=code, deviceId=DEVICE
        ),
        200,
        "authenticated",
    )


async def test_a_forgotten_pin_is_reset_with_an_email_code(api: AuthApi) -> None:
    await api.onboard()
    before = len(api.mail.sent)
    envelope(
        await api.post("/auth/pin-reset/request", phoneNumber=PHONE, deviceId=DEVICE),
        202,
        "check_email",
    )
    await api.delivered(before + 1)
    code = code_of(api.mail.sent[-1].text)
    wrong = "111111" if code != "111111" else "222222"
    envelope(
        await api.post("/auth/pin-reset/verify", phoneNumber=PHONE, code=wrong, deviceId=DEVICE),
        401,
        "authentication_failed",
    )
    envelope(
        await api.post("/auth/pin-reset/verify", phoneNumber=PHONE, code=code, deviceId=DEVICE),
        200,
        "code_verified",
    )
    envelope(
        await api.post(
            "/auth/pin-reset/complete", phoneNumber=PHONE, pin="8642", code=wrong, deviceId=DEVICE
        ),
        401,
        "authentication_failed",
    )
    envelope(
        await api.post(
            "/auth/pin-reset/complete", phoneNumber=PHONE, pin="8642", code=code, deviceId=DEVICE
        ),
        200,
        "authenticated",
    )


async def test_refresh_rotates_and_sign_out_ends_the_session(api: AuthApi) -> None:
    _, first = await api.onboard()
    rotated = envelope(
        await api.post("/auth/refresh", refreshToken=first["refreshToken"], deviceId=DEVICE),
        200,
        "authenticated",
    )
    assert has(rotated, "refreshToken", "str") != first["refreshToken"]
    envelope(
        await api.post("/auth/refresh", refreshToken=first["refreshToken"], deviceId=DEVICE),
        401,
        "authentication_failed",
    )
    envelope(
        await api.post("/auth/sign-out", refreshToken=rotated["refreshToken"], deviceId=DEVICE),
        200,
        "signed_out",
    )
    envelope(
        await api.post("/auth/refresh", refreshToken=rotated["refreshToken"], deviceId=DEVICE),
        401,
        "authentication_failed",
    )


async def test_switch_user_revokes_this_phone(api: AuthApi) -> None:
    device = "phone one"
    _, first = await api.onboard(device=device)
    path = f"/auth/devices/{quote(device)}/revoke"
    anonymous = await api.client.post(path)
    assert (anonymous.status_code, anonymous.content) == (401, b"")
    bearer = {"Authorization": f"Bearer {first['accessToken']}"}
    envelope(await api.client.post(path, headers=bearer), 200, "device_revoked")
    assert (await api.client.get("/auth/session", headers=bearer)).status_code == 401
    envelope(
        await api.post("/auth/refresh", refreshToken=first["refreshToken"], deviceId=device),
        401,
        "authentication_failed",
    )


async def test_the_session_names_the_person_and_their_permissions(
    api: AuthApi, owner: Member
) -> None:
    clerk = await join(api, email="clerk@example.com", phone="0722000111", role="Revenue clerk")
    body = ok(await api.client.get("/auth/session", headers=clerk.headers))
    UUID(has(body, "userId", "str"))
    has(body, "firstName", "str")
    has(body, "lastName", "str")
    assert has(body, "role", "str") == "Revenue clerk"
    permissions = has(body, "permissions", "arr")
    assert permissions and all(isinstance(key, str) for key in permissions)
    assert (await api.client.get("/auth/session")).status_code == 401
    anonymous = await api.client.get(
        "/auth/session", headers={"Authorization": "Bearer not-a-token"}
    )
    assert anonymous.status_code == 401


# --- Phase1AppearanceAndCatalogContractTests ---------------------------------------------


async def test_appearance_keeps_every_field_the_clients_read(api: AuthApi, clerk: Member) -> None:
    body = ok(await api.client.get("/setup/appearance", headers=clerk.headers))
    has(body, "organizationName", "str")
    has(body, "settingsVersion", "num")
    branding = has(body, "branding", "obj")
    for name in ("displayName", "logoAlt", "primary", "secondary", "accent"):
        has(branding, name, "str")
    has(branding, "logo", "str", "null")
    formats = has(body, "formats", "obj")
    for name in ("locale", "timeZone", "datePattern", "currency", "weekNumbering", "direction"):
        has(formats, name, "str")
    for name in ("hour12", "useGrouping", "useGroupping"):
        has(formats, name, "bool")
    for name in ("numberDecimals", "firstDayOfWeek"):
        has(formats, name, "num")
    has(body, "themeMode", "str")
    has(body, "reducedMotion", "bool")
    has(body, "fontScale", "num")
    assert (await api.client.get("/setup/appearance")).status_code == 401


async def test_the_catalogue_keeps_its_shape_and_the_names_the_phone_looks_for(
    api: AuthApi, clerk: Member
) -> None:
    groups = ok(await api.client.get("/setup/access/catalog", headers=clerk.headers))
    assert isinstance(groups, list) and groups
    keys: list[str] = []
    for group in groups:
        has(group, "name", "str")
        for item in has(group, "items", "arr"):
            keys.append(has(item, "key", "str"))
            has(item, "label", "str")
            has(item, "needs", "arr")
    names = {group["name"] for group in groups}
    assert {"Revenue", "Petty cash"} <= names
    expected = {
        "revenue.view",
        "revenue.capture",
        "pettycash.spend",
        "pettycash.approve_item",
        "pettycash.view_all",
        "dash.net",
        "dash.gaps",
        "people.view",
        "audit.view",
    }
    assert expected <= set(keys)
    assert (await api.client.get("/setup/access/catalog")).status_code == 401


# The catalogue lists the 59 rights the phone only displays ("Your access"); the keys its tabs,
# cards and buttons are gated on reach it through the token and the session, legacy ones too.
# Deliberately gone: bills.* (no source; office bills were never served) and, for a Fleet
# manager added after the change, commitments.view (dash.net no longer needs it).
_PHONE_GATES = {
    "Revenue clerk": {"dash.capture", "dash.gaps", "revenue.view", "revenue.capture",
                      "revenue.no_earnings"},
    "Fleet manager": {"dash.float", "dash.revenue", "dash.costs", "dash.gaps", "revenue.view",
                      "revenue.capture", "revenue.no_earnings", "revenue.correct",
                      "pettycash.spend", "expenses.view", "reports.view"},
    "Office admin": {"dash.revenue", "dash.costs", "dash.gaps", "dash.commitments", "dash.edits",
                     "revenue.view", "revenue.correct", "expenses.view", "expenses.capture",
                     "expenses.correct", "expenses.setup", "commitments.view",
                     "commitments.manage", "reports.view", "reports.export", "invest.view",
                     "invest.manage", "companies.manage", "vehicles.manage", "people.view",
                     "people.manage", "audit.view"},
}  # fmt: skip


@pytest.mark.parametrize("role", sorted(_PHONE_GATES))
async def test_the_session_keeps_the_keys_a_v211_phone_gates_on(api: AuthApi, role: str) -> None:
    member = await join(api, email="person@example.com", phone="0722000333", role=role)
    body = ok(await api.client.get("/auth/session", headers=member.headers))
    assert _PHONE_GATES[role] <= set(has(body, "permissions", "arr"))


# --- Phase1WebSettingsContractTests (the rows the implemented features cover) ------------


def _person(**changes: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "firstName": "Jane",
        "lastName": "Njeri",
        "email": "jane.njeri@example.com",
        "phoneNumber": "0722000999",
        "role": "Revenue clerk",
        "scopeMode": "all",
        "companyIds": [],
        "vehicleIds": [],
        "permissions": ["revenue.view", "revenue.capture"],
        "approvalLimit": None,
    }
    body.update(changes)
    return body


def _organization_of(api: AuthApi, member: Member) -> UUID:
    row = api.owner.execute(
        "SELECT organization_id FROM tenancy.memberships WHERE user_id = %s", (member.user_id,)
    ).fetchone()
    assert row is not None
    return UUID(str(row["organization_id"]))


async def _fleet(api: AuthApi, owner: Member) -> tuple[str, str]:
    """A company as the develop web creates it, with a vehicle in the v2.3 body (the develop
    web can no longer add one: the fleet number is required, as pinned below) and a
    category as the develop web sends it (its ``bucket`` is accepted and ignored); the vehicle
    and an expense item in use."""
    company = ok(
        await api.client.post(
            "/setup/companies",
            json={"name": "Contract Fleet", "reason": "Added PSV company Contract Fleet"},
            headers=owner.headers,
        )
    )
    company_id = has(company, "id", "str")
    vehicle = ok(
        await api.client.post(
            "/setup/vehicles",
            json={
                "companyId": company_id,
                "registration": "KDA 123A",
                "fleetNumber": "CF-1",
                "joinedOn": "2026-10-01",
                "dayTargets": [3000] * 7,
            },
            headers=owner.headers,
        )
    )
    category = ok(
        await api.client.post(
            "/setup/expense-categories",
            json={"name": "Insurance", "bucket": 2},
            headers=owner.headers,
        )
    )
    item = ok(
        await api.client.post(
            f"/setup/expense-categories/{category['id']}/items",
            json={"name": "Comprehensive cover"},
            headers=owner.headers,
        )
    )
    return has(vehicle, "id", "str"), has(item, "id", "str")


def _scheduled(vehicle_id: str, **changes: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "name": "Insurance",
        "kind": 1,
        "category": 1,
        "amount": 1500,
        "frequency": 2,
        "day": 1,
        "lastDay": False,
        "start": "2026-10-01",
        "end": None,
        "allocations": [{"vehicleId": vehicle_id, "amount": 1500}],
    }
    body.update(changes)
    return body


def _vehicle_row(vehicle: Mapping[str, Any]) -> None:
    for name in ("id", "companyId", "companyName", "registration", "joinedOn"):
        has(vehicle, name, "str")
    for name in ("weeklyTarget", "recurringItems"):
        has(vehicle, name, "num")
    for target in has(vehicle, "targets", "arr"):
        has(target, "effectiveFrom", "str")
        has(target, "weeklyAmount", "num")
        has(target, "revision", "num")


def _recurring_row(row: Mapping[str, Any]) -> None:
    for name in ("id", "name", "start"):
        has(row, name, "str")
    for name in ("kind", "amount", "frequency"):
        has(row, name, "num")
    has(row, "bucket", "num", "null")
    has(row, "day", "num", "null")
    has(row, "lastDay", "bool")
    has(row, "end", "str", "null")
    has(row, "stoppedFrom", "str", "null")
    has(row, "partial", "bool")
    for allocation in has(row, "allocations", "arr"):
        has(allocation, "vehicleId", "str")
        has(allocation, "amount", "num")
        has(allocation, "registration", "str")


def _report(report: Mapping[str, Any]) -> None:
    for name in ("vehicleId", "from", "through"):
        has(report, name, "str")
    for name in ("costs", "savings"):
        has(report, name, "num")
    postings = has(report, "postings", "arr")
    assert postings
    for posting in postings:
        for name in ("itemId", "versionId", "date", "name"):
            has(posting, name, "str")
        for name in ("kind", "amount"):
            has(posting, name, "num")
        has(posting, "bucket", "num", "null")


def _history_page(page: Mapping[str, Any]) -> None:
    entries = has(page, "items", "arr")
    assert entries
    for entry in entries:
        has(entry, "version", "num")
        for name in ("section", "entityId", "reason", "occurredAt", "actorId", "actorName"):
            has(entry, name, "str")


async def test_fleet_screens_read_and_write_as_the_develop_web_does(
    api: AuthApi, owner: Member
) -> None:
    vehicle_id, item_id = await _fleet(api, owner)
    companies = ok(
        await api.client.get("/setup/companies?page=1&pageSize=25", headers=owner.headers)
    )
    (company,) = has(companies, "items", "arr")
    for name in ("id", "name"):
        has(company, name, "str")
    has(company, "vehicleCount", "num")
    response = await api.client.put(
        f"/setup/companies/{company['id']}",
        json={"name": "Contract Fleet Ltd"},
        headers=owner.headers,
    )
    assert has(ok(response), "id", "str") == company["id"]
    vehicles = ok(await api.client.get("/setup/vehicles?page=1&pageSize=25", headers=owner.headers))
    (vehicle,) = has(vehicles, "items", "arr")
    _vehicle_row(vehicle)
    options = ok(await api.client.get("/setup/recurring/vehicle-options", headers=owner.headers))
    assert options
    for option in options:
        for name in ("id", "companyId", "companyName", "registration"):
            has(option, name, "str")
    created = ok(
        await api.client.post(
            "/setup/recurring",
            json=_scheduled(vehicle_id, expenseItemId=item_id),
            headers=owner.headers,
        )
    )
    item = has(created, "id", "str")
    revised = await api.client.put(
        f"/setup/recurring/{item}",
        json=_scheduled(
            vehicle_id,
            expenseItemId=item_id,
            amount=1800,
            allocations=[{"vehicleId": vehicle_id, "amount": 1800}],
        ),
        headers=owner.headers,
    )
    assert has(ok(revised), "id", "str") == item
    recurring = ok(
        await api.client.get("/setup/recurring?page=1&pageSize=25", headers=owner.headers)
    )
    (row,) = has(recurring, "items", "arr")
    _recurring_row(row)
    stopped = await api.client.post(
        f"/setup/recurring/{item}/stop",
        json={"confirmed": True, "reason": "Moved to another insurer"},
        headers=owner.headers,
    )
    assert has(ok(stopped), "id", "str") == item
    for period in ("month", "week"):
        path = f"/setup/vehicles/{vehicle_id}/report?period={period}"
        _report(ok(await api.client.get(path, headers=owner.headers)))
    for query in ("page=1&pageSize=25", "pageSize=3"):
        _history_page(ok(await api.client.get(f"/setup/history?{query}", headers=owner.headers)))


async def test_a_vehicle_save_from_the_develop_web_is_refused_until_it_sends_a_fleet_number(
    api: AuthApi, owner: Member
) -> None:
    """A deliberate change of the setup design: the develop web sends ``weeklyTarget`` and no
    fleet number, so both vehicle saves answer a 400 it can show, and nothing changes."""
    vehicle_id, _ = await _fleet(api, owner)
    vehicles = ok(await api.client.get("/setup/vehicles?page=1&pageSize=25", headers=owner.headers))
    (vehicle,) = has(vehicles, "items", "arr")
    body = {
        "companyId": vehicle["companyId"],
        "registration": "KDB 456B",
        "joinedOn": "2026-10-01",
        "weeklyTarget": 22000,
    }
    for response in (
        await api.client.post("/setup/vehicles", json=body, headers=owner.headers),
        await api.client.put(
            f"/setup/vehicles/{vehicle_id}",
            json={**body, "registration": "KDA 123A"},
            headers=owner.headers,
        ),
    ):
        assert response.status_code == 400
        assert problem(response)["detail"] == "Enter the fleet number."
    after = ok(await api.client.get("/setup/vehicles?page=1&pageSize=25", headers=owner.headers))
    assert [(v["registration"], v["weeklyTarget"]) for v in after["items"]] == [("KDA 123A", 21000)]


async def test_a_recurring_cost_from_the_develop_web_is_refused_with_a_reason(
    api: AuthApi, owner: Member
) -> None:
    vehicle_id, _ = await _fleet(api, owner)
    response = await api.client.post(
        "/setup/recurring", json=_scheduled(vehicle_id), headers=owner.headers
    )
    assert response.status_code == 400
    problem(response)


async def test_a_daily_item_from_the_develop_web_is_refused_with_a_reason(
    api: AuthApi, owner: Member
) -> None:
    """A daily cost; since the saving model (B18) a saving may run daily."""
    vehicle_id, item_id = await _fleet(api, owner)
    body = _scheduled(vehicle_id, name="Crew lunch", frequency=1, day=None, expenseItemId=item_id)
    del body["category"]
    response = await api.client.post("/setup/recurring", json=body, headers=owner.headers)
    assert response.status_code == 400
    assert problem(response)["detail"] == (
        "Daily schedules are no longer offered. Choose weekly, monthly or yearly."
    )


async def test_people_and_access_read_as_the_develop_web_does(api: AuthApi, owner: Member) -> None:
    organization = _organization_of(api, owner)
    company = add_company(api.owner, organization, "Contract Fleet")
    add_vehicle(api.owner, organization, company, "KDA 123A")
    roles = ok(await api.client.get("/setup/access/roles", headers=owner.headers))
    for role in roles:
        has(role, "id", "str")
        has(role, "name", "str")
        has(role, "permissions", "arr")
    options = ok(await api.client.get("/setup/access/scope-options", headers=owner.headers))
    for entry in has(options, "companies", "arr"):
        has(entry, "id", "str")
        has(entry, "name", "str")
    vehicles = has(options, "vehicles", "arr")
    assert vehicles
    for entry in vehicles:
        has(entry, "id", "str")
        has(entry, "registration", "str")
        has(entry, "companyId", "str")
    created = ok(await api.client.post("/setup/people", json=_person(), headers=owner.headers))
    person_id = has(created, "id", "str")
    page = ok(await api.client.get("/setup/people?page=1&pageSize=25", headers=owner.headers))
    for name in ("pageNumber", "pageSize", "total"):
        has(page, name, "num")
    items = has(page, "items", "arr")
    assert person_id in {item["id"] for item in items}
    for item in items:
        for name in ("id", "firstName", "lastName", "email", "phoneNumber", "role", "scopeMode"):
            has(item, name, "str")
        for name in ("active", "hasPin"):
            has(item, name, "bool")
        for name in ("companyIds", "vehicleIds", "permissions"):
            assert all(isinstance(v, str) for v in has(item, name, "arr"))
        has(item, "approvalLimit", "num", "null")
    signed_out = await api.client.post(f"/setup/people/{person_id}/sign-out", headers=owner.headers)
    assert signed_out.status_code == 200


async def test_editing_a_person_from_the_develop_web_asks_for_a_reload(
    api: AuthApi, owner: Member
) -> None:
    created = ok(await api.client.post("/setup/people", json=_person(), headers=owner.headers))
    response = await api.client.put(
        f"/setup/people/{created['id']}", json=_person(), headers=owner.headers
    )
    assert response.status_code == 400
    problem(response)


async def test_removing_access_from_the_develop_web_asks_for_a_reload(
    api: AuthApi, owner: Member
) -> None:
    created = ok(await api.client.post("/setup/people", json=_person(), headers=owner.headers))
    for action in ("deactivate", "activate"):
        response = await api.client.post(
            f"/setup/people/{created['id']}/{action}", headers=owner.headers
        )
        assert response.status_code == 200 or (
            400 <= response.status_code < 500 and response.status_code != 415
        )
        if response.status_code != 200:
            problem(response)


async def test_organization_settings_and_preferences_read_and_save_as_the_develop_web_does(
    api: AuthApi, owner: Member
) -> None:
    settings = ok(await api.client.get("/setup/organization/settings", headers=owner.headers))
    organization = has(settings, "organization", "obj")
    has(organization, "name", "str")
    has(organization, "slug", "str")
    localization = has(settings, "localization", "obj")
    for name in ("locale", "timeZone", "currency", "datePattern", "weekNumbering"):
        has(localization, name, "str")
    for name in (
        "hour12",
        "useGrouping",
        "allowLocaleOverride",
        "allowTimeZoneOverride",
        "allowHour12Override",
        "allowThemeOverride",
    ):
        has(localization, name, "bool")
    for name in ("firstDayOfWeek", "numberDecimals"):
        has(localization, name, "num")
    branding = has(settings, "branding", "obj")
    for name in ("displayName", "legalName", "logoAlt", "primary", "secondary", "accent"):
        has(branding, name, "str")
    for name in ("supportEmail", "domain"):
        has(branding, name, "str", "null")
    policy = has(settings, "securityPolicy", "obj")
    for name in (
        "passwordMinLength",
        "passwordHistory",
        "pinLength",
        "lockoutThreshold",
        "lockoutMinutes",
        "accessTokenMinutes",
        "refreshTokenDays",
        "idleUnlockSeconds",
    ):
        has(policy, name, "num")
    for name in ("passwordComplexity", "allowPinSignIn"):
        has(policy, name, "bool")
    for section, value in (
        ("organization", {"name": organization["name"], "slug": organization["slug"]}),
        ("localization", localization),
        ("branding", branding),
        ("securityPolicy", policy),
    ):
        response = await api.client.put(
            f"/setup/organization/settings/{section}",
            json={"value": value, "reason": "Saved from the web"},
            headers=owner.headers,
        )
        assert response.status_code == 200, (section, response.content)
    uploaded = await api.client.put(
        "/setup/organization/logo", json={"dataUrl": PNG}, headers=owner.headers
    )
    assert uploaded.status_code == 200
    deleted = await api.client.delete("/setup/organization/logo", headers=owner.headers)
    assert deleted.status_code == 200
    preferences = ok(await api.client.get("/setup/preferences", headers=owner.headers))
    for name in ("locale", "timeZone", "hour12", "themeMode"):
        assert name in preferences
    has(preferences, "reducedMotion", "bool")
    has(preferences, "fontScale", "num")
    for name in (
        "allowLocaleOverride",
        "allowTimeZoneOverride",
        "allowHour12Override",
        "allowThemeOverride",
    ):
        has(preferences, name, "bool")
    defaults = has(preferences, "organization", "obj")
    has(defaults, "locale", "str")
    has(defaults, "timeZone", "str")
    has(defaults, "hour12", "bool")
    saved = await api.client.put("/setup/preferences", json=preferences, headers=owner.headers)
    assert saved.status_code == 200, saved.content


async def test_refusals_keep_their_status_and_a_problem_the_web_can_show(
    api: AuthApi, owner: Member, clerk: Member
) -> None:
    unnamed = await api.client.post("/setup/companies", json={"name": ""}, headers=owner.headers)
    assert unnamed.status_code == 400
    problem(unnamed)
    response = await api.client.get("/setup/organization/settings", headers=clerk.headers)
    assert response.status_code == 403
    problem(response)
    unknown = await api.client.get(
        f"/setup/vehicles/{UUID(int=1)}/report?period=month", headers=owner.headers
    )
    assert unknown.status_code == 404
    problem(unknown)
    anonymous = await api.client.get("/setup/companies?page=1&pageSize=25")
    assert anonymous.status_code == 401


# --- revenue: the v2.11 phone's capture queue and week -------------------------------------


def _phone_vehicle(api: AuthApi, member: Member) -> str:
    org = _organization_of(api, member)
    company = add_company(api.owner, org, "Phone Fleet")
    return str(add_vehicle(api.owner, org, company, "KDP 482M", joined_on=date(2026, 10, 1)))


_CELL = (
    ("date", "str"),
    ("status", "str"),
    ("expected", "num"),
    ("amount", "num", "null"),
    ("reason", "str", "null"),
    ("note", "str", "null"),
    ("canEdit", "bool"),
    ("editedAfterCapture", "bool"),
    ("version", "num", "null"),
)


def _sees_every_company(api: AuthApi, member: Member) -> None:
    set_scope(api.owner, member.user_id, _organization_of(api, member), all_companies=True)


def _low_day_threshold(api: AuthApi, member: Member, amount: int) -> None:
    api.owner.execute(
        "INSERT INTO tenancy.organization_revenue_settings (organization_id, low_day_threshold) "
        "VALUES (%s, %s) ON CONFLICT (organization_id) DO UPDATE "
        "SET low_day_threshold = EXCLUDED.low_day_threshold",
        (_organization_of(api, member), amount),
    )


def _entry(**changes: Any) -> dict[str, Any]:
    """The body ``apps/mobile/src/revenue/queue.ts`` sends: all four fields, nulls included,
    and no ``capturedAt``."""
    return {"amount": None, "reason": None, "note": None, "version": None, **changes}


async def test_a_v211_phone_captures_and_replays_its_queue(api: AuthApi, clerk: Member) -> None:
    vehicle = _phone_vehicle(api, clerk)
    _sees_every_company(api, clerk)
    url = f"/setup/revenue/{vehicle}"
    for day, body in (
        ("2026-10-05", _entry(amount=5000)),
        ("2026-10-06", _entry(reason="NoCrew")),
        ("2026-10-07", _entry(reason="Other", note="Engine knock")),
    ):
        saved = await api.client.put(f"{url}/{day}", json=body, headers=clerk.headers)
        assert saved.status_code == 200, saved.text
        first = json.loads(saved.content)
        assert list(first) == ["id", "version"]
        has(first, "id", "str")
        has(first, "version", "num")
        # Drained again later (queue retry): the same answer, nothing written.
        again = await api.client.put(f"{url}/{day}", json=body, headers=clerk.headers)
        assert (again.status_code, json.loads(again.content)) == (200, first)


async def test_a_v211_phone_retrying_an_entry_saved_under_another_threshold_gets_its_answer(
    api: AuthApi, clerk: Member
) -> None:
    """A queue retry of an entry the server already holds is answered as the first save was,
    whatever the threshold says now: 700 saved while it was 500, retried after it went back to
    4,000 (an entry saved before the low-day rule is the same case)."""
    vehicle = _phone_vehicle(api, clerk)
    _sees_every_company(api, clerk)
    url = f"/setup/revenue/{vehicle}/2026-10-05"
    _low_day_threshold(api, clerk, 500)
    saved = await api.client.put(url, json=_entry(amount=700), headers=clerk.headers)
    assert saved.status_code == 200, saved.text
    _low_day_threshold(api, clerk, 4000)
    again = await api.client.put(url, json=_entry(amount=700), headers=clerk.headers)
    assert (again.status_code, json.loads(again.content)) == (200, json.loads(saved.content))


async def test_a_v211_phone_reads_the_week_with_a_low_day_on_it(
    api: AuthApi, owner: Member, clerk: Member
) -> None:
    vehicle = _phone_vehicle(api, owner)
    _sees_every_company(api, clerk)
    saved = await api.client.put(
        f"/setup/revenue/{vehicle}/2026-10-05",
        json={**_entry(amount=2500, reason="Garage"), "capturedAt": None},
        headers=owner.headers,
    )
    assert saved.status_code == 200, saved.text
    response = await api.client.get("/setup/revenue?weekStart=2026-10-05", headers=clerk.headers)
    assert response.status_code == 200
    grid = json.loads(response.content)
    for name, *kinds in (
        ("weekStart", "str"),
        ("businessDate", "str"),
        ("vehicles", "arr"),
        ("totalAmount", "num"),
        ("totalExpected", "num"),
        ("percent", "num", "null"),
    ):
        has(grid, name, *kinds)
    [row] = grid["vehicles"]
    for name, *kinds in (("id", "str"), ("registration", "str"), ("days", "arr")):
        has(row, name, *kinds)
    for cell in row["days"]:
        for name, *kinds in _CELL:
            has(cell, name, *kinds)
    low = row["days"][0]
    # What the phone keeps as the saved value: an amount and a reason together are accepted.
    assert (low["status"], low["amount"], low["reason"]) == ("amount", 2500, "Garage")


async def test_what_a_v211_phone_can_no_longer_save_answers_with_a_sentence(
    api: AuthApi, clerk: Member
) -> None:
    """Deliberate changes (``docs/15-design-v2-3.md`` section 4): an amount below the low-day
    threshold needs a reason the v2.11 form cannot send, and a saved day, today's included,
    needs "Change revenue already saved". The phone shows ``detail`` and keeps the entry."""
    vehicle = _phone_vehicle(api, clerk)
    _sees_every_company(api, clerk)
    url = f"/setup/revenue/{vehicle}"
    low = await api.client.put(f"{url}/2026-10-05", json=_entry(amount=700), headers=clerk.headers)
    assert low.status_code == 400
    assert problem(low)["detail"] == "Choose the reason. Revenue is below KES 4,000."
    saved = await api.client.put(
        f"{url}/2026-10-07", json=_entry(amount=4500), headers=clerk.headers
    )
    version = json.loads(saved.content)["version"]
    changed = await api.client.put(
        f"{url}/2026-10-07", json=_entry(amount=4600, version=version), headers=clerk.headers
    )
    assert changed.status_code == 403
    assert problem(changed)["detail"] == (
        'Changing revenue already saved needs the permission "Change revenue already saved".'
    )


async def test_the_day_and_the_scheduled_summary_read_as_the_v23_web_does(
    api: AuthApi, owner: Member
) -> None:
    """``packages/shared/src/revenue.ts`` (``RevenueDay``) and the web's scheduled-item page
    (``apps/web/components/setup/shared.tsx``): the names and JSON kinds they read."""
    vehicle_id, _ = await _fleet(api, owner)
    day = ok(await api.client.get("/setup/revenue/day", headers=owner.headers))
    for name, *kinds in (
        ("date", "str"),
        ("businessDate", "str"),
        ("vehicles", "arr"),
        ("truncated", "bool"),
    ):
        has(day, name, *kinds)
    [row] = day["vehicles"]
    assert has(row, "id", "str") == vehicle_id
    for name in ("companyId", "registration"):
        has(row, name, "str")
    has(row, "lastWeek", "obj", "null")
    for name, *kinds in _CELL:
        has(has(row, "day", "obj"), name, *kinds)
    summary = ok(await api.client.get("/setup/recurring/summary", headers=owner.headers))
    for name in ("from", "to"):
        has(summary, name, "str")
    for name in ("costsDue", "saved", "savingsBalance"):
        has(summary, name, "num")
    for name in ("runningCosts", "pausedCosts", "runningSavings", "pausedSavings"):
        has(summary, name, "num", "null")
    created = ok(
        await api.client.post(
            "/setup/recurring",
            json={
                "name": "Owner savings",
                "kind": 2,
                "amount": 500,
                "frequency": 3,
                "day": 1,
                "allocations": [{"vehicleId": vehicle_id, "amount": 500}],
                "condition": {"min": 5000, "days": 7},
                "opening": {
                    "date": "2026-10-01",
                    "amounts": [{"vehicleId": vehicle_id, "amount": 900}],
                },
            },
            headers=owner.headers,
        )
    )
    page = ok(await api.client.get("/setup/recurring?page=1&pageSize=25", headers=owner.headers))
    [item] = [i for i in has(page, "items", "arr") if i["id"] == created["id"]]
    for name, *kinds in (
        ("pausedFrom", "str", "null"),
        ("lastRun", "str", "null"),
        ("lastRunVehicles", "num"),
        ("balance", "num", "null"),
        ("nextRun", "str", "null"),
    ):
        has(item, name, *kinds)
    for name in ("saved", "skipped", "held"):
        has(has(item, "lastRunStates", "obj"), name, "num")
    for name in ("min", "days"):
        has(has(item, "condition", "obj"), name, "num")
    opening = has(item, "opening", "obj")
    has(opening, "date", "str")
    has(opening, "total", "num")


# --- central expenses (packages/shared/src/expenses.ts) --------------------------------------

_LEDGER_ROW = (
    ("id", ("str",)),
    ("source", ("str",)),
    ("date", ("str",)),
    ("vehicleId", ("str",)),
    ("registration", ("str",)),
    ("expenseItemId", ("str", "null")),
    ("itemName", ("str",)),
    ("categoryName", ("str", "null")),
    ("bucket", ("num",)),
    ("units", ("num",)),
    ("unitAmount", ("num",)),
    ("total", ("num",)),
    ("note", ("str", "null")),
    ("recordedByName", ("str", "null")),
    ("holderName", ("str", "null")),
    ("scheduleId", ("str", "null")),
    ("group", ("obj", "null")),
    ("version", ("num", "null")),
    ("canEdit", ("bool",)),
    ("canRemove", ("bool",)),
)


async def test_the_expense_ledger_and_options_read_as_the_web_does(
    api: AuthApi, owner: Member
) -> None:
    vehicle_id, item_id = await _fleet(api, owner)
    recorded = ok(
        await api.client.post(
            "/setup/expenses/entries",
            json={
                "date": "2026-10-07",
                "expenseItemId": item_id,
                "units": 1,
                "unitAmount": 4000,
                "allocations": [{"vehicleId": vehicle_id, "amount": 4000}],
            },
            headers=owner.headers,
        )
    )
    assert [type(i) for i in has(recorded, "ids", "arr")] == [str]
    has(recorded, "total", "num")
    ledger = ok(
        await api.client.get(
            "/setup/expenses/ledger?from=2026-10-01&to=2026-10-07&page=1&pageSize=100",
            headers=owner.headers,
        )
    )
    names = ["businessDate", "from", "to", "permissions", "figures", "items", "pageNumber"]
    assert list(ledger)[: len(names) + 3] == [*names, "pageSize", "total", "amount"]
    for name in ("businessDate", "from", "to"):
        has(ledger, name, "str")
    for name in ("canRecord", "canCorrect"):
        has(has(ledger, "permissions", "obj"), name, "bool")
    figures = has(ledger, "figures", "obj")
    for name in ("total", "central", "pettyCash", "scheduled"):
        has(figures, name, "num")
    for name in ("pageNumber", "pageSize", "total", "amount"):
        has(ledger, name, "num")
    (row,) = has(ledger, "items", "arr")
    assert list(row)[: len(_LEDGER_ROW)] == [name for name, _ in _LEDGER_ROW]
    for name, kinds in _LEDGER_ROW:
        has(row, name, *kinds)
    assert (row["source"], row["bucket"], row["total"]) == ("central", 2, 4000)
    saved = ok(
        await api.client.put(
            f"/setup/expenses/entries/{row['id']}",
            json={
                "date": row["date"],
                "vehicleId": row["vehicleId"],
                "expenseItemId": row["expenseItemId"],
                "units": 1,
                "unitAmount": 4500,
                "note": None,
                "version": row["version"],
            },
            headers=owner.headers,
        )
    )
    assert (has(saved, "id", "str"), has(saved, "version", "num")) == (row["id"], 2)
    options = ok(
        await api.client.get("/setup/expenses/options?date=2026-10-07", headers=owner.headers)
    )
    (vehicle,) = has(options, "vehicles", "arr")
    for name in ("id", "companyId", "companyName", "registration"):
        has(vehicle, name, "str")
    has(vehicle, "active", "bool")
    (item,) = has(options, "items", "arr")
    for name in ("id", "name", "categoryId", "categoryName"):
        has(item, name, "str")
    has(item, "bucket", "num")


# --- Phase1ReportContractTests (the catalogue, Net by vehicle, the cash book) -------------

_TABLE = (
    ("group", "str"),
    ("report", "str"),
    ("title", "str"),
    ("from", "str", "null"),
    ("to", "str", "null"),
    ("businessDate", "str"),
    ("headline", "obj"),
    ("figures", "arr"),
    ("columns", "arr"),
    ("rows", "arr"),
    ("pageNumber", "num"),
    ("pageSize", "num"),
    ("total", "num"),
    ("totals", "arr"),
)


def _table(response: httpx.Response) -> dict[str, Any]:
    assert response.status_code == 200, response.text
    table: dict[str, Any] = json.loads(response.content)
    for name, *kinds in _TABLE:
        has(table, name, *kinds)
    for figure in (table["headline"], *table["figures"]):
        has(figure, "label", "str")
        has(figure, "value", "num")
        has(figure, "kind", "str")
    for column in table["columns"]:
        has(column, "key", "str")
        has(column, "label", "str")
        has(column, "kind", "str")
        has(column, "sum", "bool")
    for row in table["rows"]:
        assert isinstance(row, list) and len(row) == len(table["columns"])
        assert all(cell is None or isinstance(cell, str | int | float) for cell in row)
    assert len(table["totals"]) == len(table["columns"])
    return table


async def test_the_report_catalogue_keeps_the_keys_the_web_reads(
    api: AuthApi, owner: Member
) -> None:
    _phone_vehicle(api, owner)
    _sees_every_company(api, owner)
    response = await api.client.get("/setup/reports", headers=owner.headers)
    assert response.status_code == 200, response.text
    access = json.loads(response.content)
    has(access, "businessDate", "str")
    has(access, "firstDayOfWeek", "num")
    assert "net" in has(access, "fleet", "arr")
    assert "cashBook" in has(access, "pettyCash", "arr")
    for holder in has(access, "holders", "arr"):
        for name, *kinds in (("id", "str"), ("name", "str"), ("active", "bool")):
            has(holder, name, *kinds)
    has(access, "canExport", "bool")


async def test_net_by_vehicle_and_the_cash_book_read_as_the_web_does(
    api: AuthApi, owner: Member
) -> None:
    _phone_vehicle(api, owner)
    _sees_every_company(api, owner)
    period = "from=2026-10-01&to=2026-10-07"
    net = _table(await api.client.get(f"/setup/reports/fleet/net?{period}", headers=owner.headers))
    assert (net["group"], net["report"]) == ("fleet", "net")
    assert [c["key"] for c in net["columns"]][:3] == ["vehicle", "company", "revenue"]
    assert [c["key"] for c in net["columns"]][-3:] == ["moneyOut", "net", "saved"]
    [row] = net["rows"]
    assert row[0] == "KDP 482M"
    book = _table(
        await api.client.get(f"/setup/reports/pettycash/cashBook?{period}", headers=owner.headers)
    )
    assert (book["group"], book["report"]) == ("pettycash", "cashBook")
    assert [c["key"] for c in book["columns"]] == [
        "date",
        "opening",
        "cash",
        "expenses",
        "credits",
        "closing",
        "waiting",
    ]
    refused = await api.client.get(f"/setup/reports/fleet/nothing?{period}", headers=owner.headers)
    assert refused.status_code == 404
    problem(refused)
