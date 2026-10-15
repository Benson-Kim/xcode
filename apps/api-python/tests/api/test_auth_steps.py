"""The number-first sign-in routes against the real database (``docs/06-http-contract.md``
2.12.1, ``docs/07-auth.md`` section 12): the step envelope, the number step, the simulated
account of an unknown number byte for byte, the PIN throttle, device tokens, the first sign-in
and the forced reset, change PIN, the own-devices list and removal, and statement budgets."""

from __future__ import annotations

import json
from collections.abc import Awaitable
from typing import Any
from uuid import UUID

import httpx
import pytest

from xcode_api.db.pool import current_statement_count

from ..support.client import (
    DEVICE,
    ENVELOPE_KEYS,
    JSON_UTF8,
    PHONE,
    PIN,
    ApiFactory,
    AuthApi,
    code_of,
    envelope,
)
from ..support.scenario import device_row, set_user, user_row

pytestmark = pytest.mark.asyncio(loop_scope="session")

STEP_KEYS = [*ENVELOPE_KEYS, "purpose", "triesLeft", "pinProblem", "deviceToken"]
SEEN_EXCLUDED = frozenset({"date", "content-length", "x-request-id"})
UNKNOWN_PHONE = "0799999999"
PHONE_2 = "phone-2"
NEW_PHONE = "0722000123"


def step(response: httpx.Response, status_code: int, status: str) -> dict[str, Any]:
    """Assert the status, the content type, the request id and the eleven step-envelope
    properties in order; return the body."""
    assert response.status_code == status_code, response.content
    assert response.headers["content-type"] == JSON_UTF8
    assert response.headers["x-request-id"]
    data: dict[str, Any] = json.loads(response.content)
    assert list(data) == STEP_KEYS
    assert data["status"] == status
    return data


def seen(response: httpx.Response) -> tuple[int, list[tuple[str, str]], bytes]:
    headers = sorted(
        (name.lower(), value)
        for name, value in response.headers.multi_items()
        if name.lower() not in SEEN_EXCLUDED
    )
    return response.status_code, headers, response.content


async def post(
    api: AuthApi, path: str, headers: dict[str, str] | None = None, **body: Any
) -> httpx.Response:
    return await api.client.post(path, json=body, headers=headers)


def bearer(tokens: dict[str, Any]) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['accessToken']}"}


@pytest.fixture
async def api(make_api: ApiFactory) -> AuthApi:
    return await make_api()


async def _trust_with_token(
    api: AuthApi, device: str = PHONE_2, name: str = "Jane phone"
) -> dict[str, Any]:
    """The new-device flow of the new routes: a right PIN, the mailed code, a remembered device."""
    asked = step(
        await post(api, "/auth/pin", phoneNumber=PHONE, deviceId=device, pin=PIN),
        202,
        "verification_required",
    )
    assert (asked["purpose"], asked["maskedEmail"]) == ("new_device", "j***@example.com")
    code = code_of(api.mail.sent[-1].text)
    trusted = step(
        await post(
            api,
            "/auth/code",
            phoneNumber=PHONE,
            deviceId=device,
            deviceName=name,
            purpose="new_device",
            code=code,
        ),
        200,
        "authenticated",
    )
    assert trusted["accessToken"] and trusted["refreshToken"]
    api.clock.advance(61)
    return trusted


async def test_the_number_step_routes_by_account_state(api: AuthApi) -> None:
    jane, _ = await api.onboard()
    answers = [
        step(
            await post(api, "/auth/start", phoneNumber=UNKNOWN_PHONE, deviceId=DEVICE),
            200,
            "pin_required",
        ),
        step(
            await post(api, "/auth/start", phoneNumber=PHONE, deviceId=PHONE_2), 200, "pin_required"
        ),
    ]
    newcomer = api.provision(email="new@example.com", phone=NEW_PHONE)
    before = len(api.mail.sent)
    first = step(
        await post(api, "/auth/start", phoneNumber=NEW_PHONE, deviceId=PHONE_2, deviceName="Spare"),
        202,
        "verification_required",
    )
    assert (first["purpose"], first["maskedEmail"]) == ("first_setup", "n***@example.com")
    await api.delivered(before + 1)
    assert api.mail.sent[-1].text.endswith("\nFor: First sign in\nDevice: Spare")
    set_user(api.owner, jane, pin_reset_required=True)
    reset = step(
        await post(api, "/auth/start", phoneNumber=PHONE, deviceId=PHONE_2),
        202,
        "verification_required",
    )
    assert reset["purpose"] == "pin_reset"
    set_user(api.owner, jane, pin_reset_required=False, failed_attempts=5)
    locked = step(
        await post(api, "/auth/start", phoneNumber=PHONE, deviceId=DEVICE), 423, "pin_locked"
    )
    set_user(api.owner, newcomer, status="removed")
    blocked = step(
        await post(api, "/auth/start", phoneNumber=NEW_PHONE, deviceId=PHONE_2), 403, "blocked"
    )
    for answer in (*answers, first, reset, locked, blocked):
        assert (answer["accessToken"], answer["refreshToken"], answer["deviceToken"]) == (None,) * 3


async def test_the_number_step_answers_an_unknown_number_like_an_account_with_a_pin(
    api: AuthApi,
) -> None:
    await api.onboard()
    unknown = seen(await post(api, "/auth/start", phoneNumber=UNKNOWN_PHONE, deviceId=PHONE_2))
    known = seen(await post(api, "/auth/start", phoneNumber=PHONE, deviceId=PHONE_2))
    assert unknown == known
    assert unknown[0] == 200


async def test_an_unknown_number_counts_down_and_locks_like_a_real_one(api: AuthApi) -> None:
    await api.onboard()

    async def both(path: str, **body: Any) -> tuple[httpx.Response, httpx.Response]:
        real = await post(api, path, phoneNumber=PHONE, deviceId=PHONE_2, **body)
        fake = await post(api, path, phoneNumber=UNKNOWN_PHONE, deviceId=PHONE_2, **body)
        assert seen(real) == seen(fake), path
        return real, fake

    for left in (4, 3, 2, 1):
        real, _ = await both("/auth/pin", pin="0000")
        assert step(real, 401, "authentication_failed")["triesLeft"] == left
        assert real.headers["www-authenticate"] == "Bearer"
    real, _ = await both("/auth/pin", pin="0000")
    step(real, 423, "pin_locked")
    real, _ = await both("/auth/pin", pin=PIN)
    step(real, 423, "pin_locked")
    real, _ = await both("/auth/start")
    step(real, 423, "pin_locked")
    real, _ = await both("/auth/pin/forgot")
    forgot = step(real, 202, "verification_required")
    assert (forgot["purpose"], forgot["maskedEmail"]) == ("pin_reset", None)
    for left in (2, 1):
        real, _ = await both("/auth/code", purpose="pin_reset", code="000000")
        assert step(real, 401, "authentication_failed")["triesLeft"] == left
    real, _ = await both("/auth/code", purpose="pin_reset", code="000000")
    assert step(real, 202, "code_resent")["purpose"] == "pin_reset"
    real, _ = await both("/auth/code/resend", purpose="pin_reset")
    assert step(real, 202, "verification_required")["maskedEmail"] is None


async def test_pin_checks_are_throttled_per_address_and_per_device(make_api: ApiFactory) -> None:
    api = await make_api(rate_limit_pin_per_address=20, rate_limit_pin_per_device=10)

    async def pin(device: str, address: str, path: str = "/auth/pin") -> httpx.Response:
        body = {"phoneNumber": UNKNOWN_PHONE, "deviceId": device, "pin": "0000"}
        if path != "/auth/pin":
            body = {
                name: body.get(name, "")
                for name in ("email", "phoneNumber", "pin", "deviceId", "code", "refreshToken")
            }
        return await api.client.post(path, json=body, headers={"X-Forwarded-For": address})

    for attempt in range(10):
        path = "/auth/sign-in" if attempt % 2 else "/auth/pin"
        assert (await pin("one-device", "203.0.113.1", path)).status_code != 429
    refused = await pin("one-device", "203.0.113.9")
    assert (refused.status_code, refused.content) == (429, b"")
    assert int(refused.headers["retry-after"]) > 0
    for attempt in range(10):
        assert (await pin(f"device-{attempt}", "203.0.113.1")).status_code != 429
    assert (await pin("device-x", "203.0.113.1")).status_code == 429
    assert (await pin("device-y", "203.0.113.2")).status_code != 429


async def test_a_trusted_device_starts_at_the_pin_step_and_names_no_one(api: AuthApi) -> None:
    await api.onboard()
    before = len(api.mail.sent)
    trusted = await _trust_with_token(api)
    assert len(api.mail.sent) == before + 1, "the new-device code is mailed before the reply"
    token = trusted["deviceToken"]
    assert isinstance(token, str) and len(token) == 43
    start = step(
        await post(api, "/auth/start", phoneNumber=PHONE, deviceId=PHONE_2, deviceToken=token),
        200,
        "pin_required",
    )
    assert all(start[k] is None for k in STEP_KEYS[1:])
    signed_in = step(
        await post(
            api, "/auth/pin", phoneNumber=PHONE, deviceId=PHONE_2, deviceToken=token, pin=PIN
        ),
        200,
        "authenticated",
    )
    assert signed_in["deviceToken"] is None
    no_token = step(
        await post(api, "/auth/pin", phoneNumber=PHONE, deviceId=PHONE_2, pin=PIN),
        202,
        "verification_required",
    )
    assert no_token["purpose"] == "new_device"
    # A device trusted with a token is never trusted by its id on the released routes.
    envelope(await api.sign_in(device=PHONE_2), 202, "verification_required")


async def test_an_untrusted_sign_in_gives_a_session_but_not_a_remembered_device(
    api: AuthApi,
) -> None:
    user_id, _ = await api.onboard()
    step(
        await post(api, "/auth/pin", phoneNumber=PHONE, deviceId="borrowed", pin=PIN),
        202,
        "verification_required",
    )
    code = code_of(api.mail.sent[-1].text)
    session = step(
        await post(
            api,
            "/auth/code",
            phoneNumber=PHONE,
            deviceId="borrowed",
            purpose="new_device",
            code=code,
            trustDevice=False,
        ),
        200,
        "authenticated",
    )
    assert session["deviceToken"] is None
    assert (await api.client.get("/auth/session", headers=bearer(session))).status_code == 200
    api.clock.advance(61)
    step(
        await post(api, "/auth/pin", phoneNumber=PHONE, deviceId="borrowed", pin=PIN),
        202,
        "verification_required",
    )
    envelope(
        await api.post("/auth/sign-out", refreshToken=session["refreshToken"], deviceId="borrowed"),
        200,
        "signed_out",
    )
    row = device_row(api.owner, user_id, "borrowed")
    assert row is not None and (row["remembered"], row["revoked"]) == (False, True)


async def test_a_first_sign_in_and_a_forced_reset_through_the_new_steps(api: AuthApi) -> None:
    user_id = api.provision(phone=NEW_PHONE, email="new@example.com")
    step(
        await post(api, "/auth/start", phoneNumber=NEW_PHONE, deviceId=PHONE_2),
        202,
        "verification_required",
    )
    await api.delivered(1)
    code = code_of(api.mail.sent[-1].text)
    verified = step(
        await post(
            api,
            "/auth/code",
            phoneNumber=NEW_PHONE,
            deviceId=PHONE_2,
            purpose="first_setup",
            code=code,
        ),
        200,
        "code_verified",
    )
    assert verified["purpose"] is None
    for pin, problem in (("12345", "length"), ("1234", "weak"), ("0123", "weak"), ("7777", "weak")):
        refused = step(
            await post(
                api,
                "/auth/pin/new",
                phoneNumber=NEW_PHONE,
                deviceId=PHONE_2,
                purpose="first_setup",
                code=code,
                pin=pin,
            ),
            400,
            "invalid_pin",
        )
        assert (refused["pinProblem"], refused["minimumPinLength"]) == (problem, 4)
    own_last_four = step(
        await post(
            api,
            "/auth/pin/new",
            phoneNumber=NEW_PHONE,
            deviceId=PHONE_2,
            purpose="first_setup",
            code=code,
            pin=NEW_PHONE[-4:],
        ),
        400,
        "invalid_pin",
    )
    assert own_last_four["pinProblem"] == "weak"
    done = step(
        await post(
            api,
            "/auth/pin/new",
            phoneNumber=NEW_PHONE,
            deviceId=PHONE_2,
            deviceName="Work phone",
            purpose="first_setup",
            code=code,
            pin=PIN,
        ),
        200,
        "authenticated",
    )
    assert done["accessToken"] and len(done["deviceToken"]) == 43
    api.clock.advance(61)
    set_user(api.owner, user_id, pin_reset_required=True)
    forced = step(
        await post(api, "/auth/start", phoneNumber=NEW_PHONE, deviceId=PHONE_2),
        202,
        "verification_required",
    )
    assert forced["purpose"] == "pin_reset"
    await api.delivered(2)
    reset_code = code_of(api.mail.sent[-1].text)
    step(
        await post(
            api,
            "/auth/code",
            phoneNumber=NEW_PHONE,
            deviceId=PHONE_2,
            purpose="pin_reset",
            code=reset_code,
        ),
        200,
        "code_verified",
    )
    same = step(
        await post(
            api,
            "/auth/pin/new",
            phoneNumber=NEW_PHONE,
            deviceId=PHONE_2,
            purpose="pin_reset",
            code=reset_code,
            pin=PIN,
        ),
        400,
        "invalid_pin",
    )
    assert same["pinProblem"] == "unchanged"
    renewed = step(
        await post(
            api,
            "/auth/pin/new",
            phoneNumber=NEW_PHONE,
            deviceId=PHONE_2,
            purpose="pin_reset",
            code=reset_code,
            pin="2580",
            trustDevice=False,
        ),
        200,
        "authenticated",
    )
    assert renewed["deviceToken"] is None
    row = user_row(api.owner, user_id)
    assert (row["pin_reset_required"], row["failed_attempts"]) == (False, 0)
    stale = step(
        await post(
            api,
            "/auth/pin",
            phoneNumber=NEW_PHONE,
            deviceId=PHONE_2,
            deviceToken=done["deviceToken"],
            pin="2580",
        ),
        202,
        "verification_required",
    )
    assert stale["purpose"] == "new_device"


async def test_change_pin(api: AuthApi) -> None:
    user_id, first = await api.onboard()
    headers = bearer(first)
    empty = await post(api, "/auth/pin/change", currentPin=PIN, newPin="2580")
    assert (empty.status_code, empty.content) == (401, b"")
    for new_pin, problem in (("1111", "weak"), ("12345", "length"), (PIN, "unchanged")):
        refused = step(
            await post(api, "/auth/pin/change", headers, currentPin=PIN, newPin=new_pin),
            400,
            "invalid_pin",
        )
        assert refused["pinProblem"] == problem
    wrong = step(
        await post(api, "/auth/pin/change", headers, currentPin="0000", newPin="2580"),
        401,
        "authentication_failed",
    )
    assert wrong["triesLeft"] == 4
    assert wrong["accessToken"] is None
    changed = step(
        await post(api, "/auth/pin/change", headers, currentPin=PIN, newPin="2580"),
        200,
        "pin_changed",
    )
    assert all(changed[k] is None for k in STEP_KEYS[1:])
    assert (await api.client.get("/auth/session", headers=headers)).status_code == 200
    envelope(await api.sign_in(pin="2580"), 200, "authenticated")
    assert user_row(api.owner, user_id)["failed_attempts"] == 0
    for _ in range(4):
        step(
            await post(api, "/auth/pin/change", headers, currentPin="0000", newPin="1357"),
            401,
            "authentication_failed",
        )
    step(
        await post(api, "/auth/pin/change", headers, currentPin="0000", newPin="1357"),
        423,
        "pin_locked",
    )
    step(
        await post(api, "/auth/pin/change", headers, currentPin="2580", newPin="1357"),
        423,
        "pin_locked",
    )


async def test_own_devices_are_listed_and_removed(api: AuthApi) -> None:
    _, first = await api.onboard()
    phone = await _trust_with_token(api)
    listed = await api.client.get("/auth/trusted-devices", headers=bearer(phone))
    assert listed.status_code == 200
    assert listed.headers["content-type"] == JSON_UTF8
    devices = json.loads(listed.content)
    assert [list(d) for d in devices] == [
        ["id", "name", "trustedAt", "lastUsedAt", "thisDevice"]
    ] * 2
    assert [(d["name"], d["thisDevice"]) for d in devices] == [("Jane phone", True), (None, False)]
    other = next(d for d in devices if not d["thisDevice"])
    missing = await post(api, f"/auth/trusted-devices/{UUID(int=7)}/remove", bearer(phone))
    assert (missing.status_code, missing.content) == (404, b"")
    not_uuid = await post(api, "/auth/trusted-devices/not-a-uuid/remove", bearer(phone))
    assert (not_uuid.status_code, not_uuid.content) == (404, b"")
    removed = step(
        await post(api, f"/auth/trusted-devices/{other['id']}/remove", bearer(phone)),
        200,
        "device_revoked",
    )
    assert removed["accessToken"] is None
    assert (await api.client.get("/auth/session", headers=bearer(first))).status_code == 401
    mine = next(d for d in devices if d["thisDevice"])
    step(
        await post(api, f"/auth/trusted-devices/{mine['id']}/remove", bearer(phone)),
        200,
        "device_revoked",
    )
    assert (await api.client.get("/auth/session", headers=bearer(phone))).status_code == 401


@pytest.mark.parametrize(
    ("path", "body"),
    [
        ("/auth/start", {"phoneNumber": PHONE, "deviceId": DEVICE, "deviceToken": "a+b"}),
        ("/auth/start", {"phoneNumber": PHONE, "deviceId": DEVICE, "deviceToken": "x" * 65}),
        ("/auth/start", {"phoneNumber": PHONE, "deviceId": DEVICE, "deviceName": "(phone)"}),
        ("/auth/start", {"phoneNumber": PHONE, "deviceId": DEVICE, "deviceName": "x" * 61}),
        ("/auth/start", {"phoneNumber": PHONE, "deviceId": ""}),
        ("/auth/start", {"phoneNumber": PHONE, "deviceId": DEVICE, "deviceName": None}),
        ("/auth/pin", {"phoneNumber": PHONE, "deviceId": DEVICE, "pin": "123456789"}),
        ("/auth/code", {"phoneNumber": PHONE, "deviceId": DEVICE, "purpose": "other", "code": "1"}),
        (
            "/auth/code",
            {
                "phoneNumber": PHONE,
                "deviceId": DEVICE,
                "purpose": "new_device",
                "code": "1",
                "trustDevice": "yes",
            },
        ),
        ("/auth/code/resend", {"phoneNumber": PHONE, "deviceId": DEVICE, "purpose": ""}),
        (
            "/auth/pin/new",
            {
                "phoneNumber": PHONE,
                "deviceId": DEVICE,
                "purpose": "new_device",
                "code": "1",
                "pin": "2580",
            },
        ),
    ],
)
async def test_the_step_routes_pre_validate_before_any_lookup(
    api: AuthApi, path: str, body: dict[str, Any]
) -> None:
    response = await api.client.post(path, json=body)
    data = step(response, 400, "invalid_request")
    assert all(data[k] is None for k in STEP_KEYS[1:])


async def test_a_body_that_does_not_parse_is_the_step_invalid_request(api: AuthApi) -> None:
    for raw in (b'{"deviceId":', b'["x"]', b'{"deviceId": 7}'):
        response = await api.client.post(
            "/auth/pin", content=raw, headers={"content-type": "application/json"}
        )
        step(response, 400, "invalid_request")


async def test_each_step_route_stays_within_its_statement_budget(api: AuthApi) -> None:
    _, first = await api.onboard()
    phone = await _trust_with_token(api)

    async def budget(response: Awaitable[httpx.Response]) -> int:
        await response
        return current_statement_count()

    assert await budget(post(api, "/auth/start", phoneNumber=PHONE, deviceId=PHONE_2)) == 1
    assert (
        await budget(post(api, "/auth/pin", phoneNumber=PHONE, deviceId=PHONE_2, pin="0000")) == 2
    )
    assert (
        await budget(
            post(
                api,
                "/auth/code",
                phoneNumber=PHONE,
                deviceId=PHONE_2,
                purpose="new_device",
                code="1",
            )
        )
        == 1
    )
    assert (
        await budget(
            post(api, "/auth/code/resend", phoneNumber=PHONE, deviceId=PHONE_2, purpose="pin_reset")
        )
        == 1
    )
    assert await budget(post(api, "/auth/pin/forgot", phoneNumber=PHONE, deviceId=PHONE_2)) == 1
    assert (
        await budget(
            post(
                api,
                "/auth/pin/new",
                phoneNumber=PHONE,
                deviceId=PHONE_2,
                purpose="first_setup",
                code="1",
                pin="2580",
            )
        )
        == 1
    )
    assert (
        await budget(
            post(
                api,
                "/auth/pin/new",
                phoneNumber=PHONE,
                deviceId=PHONE_2,
                purpose="pin_reset",
                code="1",
                pin="2580",
            )
        )
        == 2
    )
    assert (
        await budget(post(api, "/auth/pin/change", bearer(phone), currentPin="0000", newPin="2580"))
        == 3
    )
    assert await budget(api.client.get("/auth/trusted-devices", headers=bearer(phone))) == 2
    devices = (await api.client.get("/auth/trusted-devices", headers=bearer(phone))).json()
    other = next(d["id"] for d in devices if not d["thisDevice"])
    assert await budget(post(api, f"/auth/trusted-devices/{other}/remove", bearer(phone))) == 2
    assert first["accessToken"]
