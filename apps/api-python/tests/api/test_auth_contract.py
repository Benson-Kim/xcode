"""The thirteen ``/auth`` routes against the real database (``docs/06-http-contract.md``
sections 1.6 A and 2.1, ``docs/07-auth.md``): happy paths, refusals, pre-validation, the
seven-property envelope, the byte-for-byte refusal rule, lockout and the untrusted cap on a
manual clock, token rotation and revocation, mail timing, development codes, rate limiting
and statement budgets. Accounts are provisioned by the operator routine and get their PIN
through the real setup flow; nothing is minted by hand."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable
from typing import Any

import httpx
import pytest

from xcode_api.db.pool import current_statement_count
from xcode_api.security.pins import Pbkdf2PinHasher
from xcode_api.settings import PIN_ITERATIONS_TESTING

from ..support.client import (
    DEVICE,
    EMAIL,
    ENVELOPE_KEYS,
    FIELDS,
    JSON_UTF8,
    PHONE,
    PIN,
    ApiFactory,
    AuthApi,
    auth_body,
    code_of,
    envelope,
)
from ..support.fakes import PinHasherSpy
from ..support.pins import HasherAtCapacity
from ..support.scenario import call, codes, set_user, user_row

# The app's mail queue task is started by the lifespan inside the fixtures; the tests must run
# on the same loop for queued mail to be delivered while a test waits for it.
pytestmark = pytest.mark.asyncio(loop_scope="session")

NEW_PIN = "8642"
OTHER_DEVICE = "tablet-9"
UNKNOWN_PHONE = "0799999999"
SEEN_EXCLUDED = frozenset({"date", "content-length", "x-request-id"})

BODY_ROUTES = (
    "/auth/sign-in",
    "/auth/unlock",
    "/auth/verify-device",
    "/auth/setup-pin/request",
    "/auth/setup-pin/verify",
    "/auth/setup-pin/complete",
    "/auth/pin-reset/request",
    "/auth/pin-reset/verify",
    "/auth/pin-reset/complete",
    "/auth/refresh",
    "/auth/sign-out",
)


def seen(response: httpx.Response) -> tuple[int, list[tuple[str, str]], bytes]:
    """Status, every header but ``Date``, ``Content-Length`` and ``X-Request-ID``, and the
    body bytes: two refusals are the same answer only if all three match."""
    headers = sorted(
        (name.lower(), value)
        for name, value in response.headers.multi_items()
        if name.lower() not in SEEN_EXCLUDED
    )
    return response.status_code, headers, response.content


def refused(response: httpx.Response) -> None:
    data = envelope(response, 401, "authentication_failed")
    assert all(data[key] is None for key in ENVELOPE_KEYS[1:])
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.fixture
async def api(make_api: ApiFactory) -> AuthApi:
    return await make_api()


# --- happy paths ---------------------------------------------------------------------------


async def test_first_pin_setup_then_sign_in_and_unlock_on_the_trusted_device(api: AuthApi) -> None:
    user_id, first = await api.onboard()
    assert first["accessToken"] and first["refreshToken"]
    for path in ("/auth/sign-in", "/auth/unlock"):
        data = envelope(
            await api.post(path, phoneNumber=PHONE, pin=PIN, deviceId=DEVICE), 200, "authenticated"
        )
        assert data["accessToken"] and data["refreshToken"]
        assert [data[k] for k in ENVELOPE_KEYS[3:]] == [None, None, None, None]
    session = await api.client.get(
        "/auth/session", headers={"Authorization": f"Bearer {first['accessToken']}"}
    )
    assert session.status_code == 200
    assert session.headers["content-type"] == JSON_UTF8
    body = json.loads(session.content)
    assert list(body) == ["userId", "firstName", "lastName", "role", "permissions"]
    assert body["userId"] == str(user_id)
    assert (body["firstName"], body["lastName"], body["role"]) == ("Jane", "Doe", "Owner")
    assert body["permissions"] and all(isinstance(p, str) for p in body["permissions"])


async def test_a_new_device_is_verified_by_the_mailed_code(api: AuthApi) -> None:
    await api.onboard()
    before = len(api.mail.sent)
    data = envelope(await api.sign_in(device=OTHER_DEVICE), 202, "verification_required")
    assert data["maskedEmail"] == "j***@example.com"
    assert data["developmentCode"] is None
    assert len(api.mail.sent) == before + 1, "the new-device mail is sent before the reply"
    message = api.mail.sent[-1]
    assert (message.to, message.subject) == (EMAIL, "Your verification code")
    assert message.text.startswith("Code: ")
    assert message.text.endswith("\nFor: Confirm this device\nDevice: Unknown device")
    code = code_of(message.text)
    wrong = await api.post(
        "/auth/verify-device", phoneNumber=PHONE, code="000000", deviceId=OTHER_DEVICE
    )
    if code != "000000":
        refused(wrong)
    verified = envelope(
        await api.post("/auth/verify-device", phoneNumber=PHONE, code=code, deviceId=OTHER_DEVICE),
        200,
        "authenticated",
    )
    assert verified["accessToken"] and verified["refreshToken"]
    envelope(await api.sign_in(device=OTHER_DEVICE), 200, "authenticated")


async def test_pin_reset_by_email_then_the_new_pin_signs_in(api: AuthApi) -> None:
    user_id, first = await api.onboard()
    before = len(api.mail.sent)
    envelope(
        await api.post("/auth/pin-reset/request", phoneNumber=PHONE, deviceId=OTHER_DEVICE),
        202,
        "check_email",
    )
    await api.delivered(before + 1)
    assert "\nFor: Reset PIN\n" in api.mail.sent[-1].text
    code = code_of(api.mail.sent[-1].text)
    envelope(
        await api.post(
            "/auth/pin-reset/verify", phoneNumber=PHONE, code=code, deviceId=OTHER_DEVICE
        ),
        200,
        "code_verified",
    )
    envelope(
        await api.post(
            "/auth/pin-reset/complete",
            phoneNumber=PHONE,
            pin=NEW_PIN,
            code=code,
            deviceId=OTHER_DEVICE,
        ),
        200,
        "authenticated",
    )
    envelope(await api.sign_in(pin=NEW_PIN, device=OTHER_DEVICE), 200, "authenticated")
    refused(await api.sign_in(pin=PIN, device=DEVICE))
    old_session = await api.client.get(
        "/auth/session", headers={"Authorization": f"Bearer {first['accessToken']}"}
    )
    assert old_session.status_code == 401, "a PIN reset ends every outstanding access token"
    assert user_row(api.owner, user_id)["security_version"] >= 1


async def test_refresh_rotates_and_a_replay_ends_the_device_session(api: AuthApi) -> None:
    _, first = await api.onboard()
    rotated = envelope(
        await api.post("/auth/refresh", refreshToken=first["refreshToken"], deviceId=DEVICE),
        200,
        "authenticated",
    )
    assert rotated["refreshToken"] != first["refreshToken"]
    assert rotated["accessToken"]
    refused(await api.post("/auth/refresh", refreshToken=first["refreshToken"], deviceId=DEVICE))
    refused(await api.post("/auth/refresh", refreshToken=rotated["refreshToken"], deviceId=DEVICE))
    envelope(await api.sign_in(), 200, "authenticated")


async def test_refresh_from_another_device_is_refused(api: AuthApi) -> None:
    _, first = await api.onboard()
    refused(
        await api.post("/auth/refresh", refreshToken=first["refreshToken"], deviceId=OTHER_DEVICE)
    )
    envelope(
        await api.post("/auth/refresh", refreshToken=first["refreshToken"], deviceId=DEVICE),
        200,
        "authenticated",
    )


async def test_sign_out_always_answers_signed_out_and_ends_the_refresh_token(
    api: AuthApi,
) -> None:
    _, first = await api.onboard()
    known = await api.post("/auth/sign-out", refreshToken=first["refreshToken"], deviceId=DEVICE)
    unknown = await api.post("/auth/sign-out", refreshToken="never-issued", deviceId=DEVICE)
    envelope(known, 200, "signed_out")
    assert seen(known) == seen(unknown)
    refused(await api.post("/auth/refresh", refreshToken=first["refreshToken"], deviceId=DEVICE))
    session = await api.client.get(
        "/auth/session", headers={"Authorization": f"Bearer {first['accessToken']}"}
    )
    assert session.status_code == 200, "access tokens live until exp after sign-out"


async def test_revoking_the_own_device_stops_its_token_at_once(api: AuthApi) -> None:
    _, first = await api.onboard()
    bearer = {"Authorization": f"Bearer {first['accessToken']}"}
    other = await api.client.post(f"/auth/devices/{OTHER_DEVICE}/revoke", headers=bearer)
    assert other.status_code == 403
    assert other.content == b""
    assert other.headers["x-request-id"]
    revoked = await api.client.post(f"/auth/devices/{DEVICE}/revoke", headers=bearer)
    data = envelope(revoked, 200, "device_revoked")
    assert all(data[key] is None for key in ENVELOPE_KEYS[1:])
    after = await api.client.get("/auth/session", headers=bearer)
    assert after.status_code == 401
    refused(await api.post("/auth/refresh", refreshToken=first["refreshToken"], deviceId=DEVICE))
    envelope(await api.sign_in(), 202, "verification_required")


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "Bearer not-a-token"},
        {"Authorization": "Basic dXNlcjpwYXNz"},
        {"Authorization": "Bearer"},
    ],
)
async def test_bearer_routes_answer_an_empty_401_with_the_challenge(
    api: AuthApi, headers: dict[str, str]
) -> None:
    for response in (
        await api.client.get("/auth/session", headers=headers),
        await api.client.post(f"/auth/devices/{DEVICE}/revoke", headers=headers),
    ):
        assert response.status_code == 401
        assert response.content == b""
        assert response.headers["www-authenticate"] == "Bearer"
        assert response.headers["x-request-id"]


async def test_the_session_check_ends_tokens_after_a_version_bump_and_a_removal(
    api: AuthApi,
) -> None:
    user_id, first = await api.onboard()
    bearer = {"Authorization": f"Bearer {first['accessToken']}"}
    assert (await api.client.get("/auth/session", headers=bearer)).status_code == 200
    version = user_row(api.owner, user_id)["security_version"]
    set_user(api.owner, user_id, security_version=version + 1)
    assert (await api.client.get("/auth/session", headers=bearer)).status_code == 401
    renewed = envelope(
        await api.post("/auth/refresh", refreshToken=first["refreshToken"], deviceId=DEVICE),
        200,
        "authenticated",
    )
    bearer = {"Authorization": f"Bearer {renewed['accessToken']}"}
    assert (await api.client.get("/auth/session", headers=bearer)).status_code == 200
    call(api.operator, "ops_remove_user", "test-operator", "req-remove", EMAIL, api.clock.now())
    assert (await api.client.get("/auth/session", headers=bearer)).status_code == 401


async def test_an_expired_access_token_is_refused(api: AuthApi) -> None:
    _, first = await api.onboard()
    bearer = {"Authorization": f"Bearer {first['accessToken']}"}
    # The token is ten minutes old 600 s after its issue; onboarding already moved the clock 61 s.
    api.clock.advance(600 - 61)
    assert (await api.client.get("/auth/session", headers=bearer)).status_code == 200
    api.clock.advance(1)
    assert (await api.client.get("/auth/session", headers=bearer)).status_code == 401


# --- refusals and the byte-for-byte rule ---------------------------------------------------


async def test_the_sign_in_refusals_are_byte_for_byte_identical(api: AuthApi) -> None:
    jane, _ = await api.onboard()
    removed = api.provision(email="removed@example.com", phone="0722222222")
    set_user(api.owner, removed, status="removed")
    for path in ("/auth/sign-in", "/auth/unlock"):
        unknown = seen(await api.post(path, phoneNumber=UNKNOWN_PHONE, pin=PIN, deviceId=DEVICE))
        assert unknown[0] == 401
        answers = {
            "not a number": await api.post(path, phoneNumber="12345", pin=PIN, deviceId=DEVICE),
            "removed": await api.post(path, phoneNumber="0722222222", pin=PIN, deviceId=DEVICE),
            "wrong pin untrusted": await api.post(
                path, phoneNumber=PHONE, pin="0000", deviceId=OTHER_DEVICE
            ),
        }
        set_user(api.owner, jane, failed_attempts=5)
        answers["locked on every device, untrusted"] = await api.post(
            path, phoneNumber=PHONE, pin=PIN, deviceId=OTHER_DEVICE
        )
        set_user(api.owner, jane, failed_attempts=0, untrusted_failed_attempts=5)
        answers["locked for new devices, untrusted"] = await api.post(
            path, phoneNumber=PHONE, pin=PIN, deviceId=OTHER_DEVICE
        )
        set_user(api.owner, jane, untrusted_failed_attempts=0, pin_reset_required=True)
        for device in (DEVICE, OTHER_DEVICE):
            answers[f"forced reset on {device}"] = await api.post(
                path, phoneNumber=PHONE, pin=PIN, deviceId=device
            )
        set_user(api.owner, jane, pin_reset_required=False)
        for name, response in answers.items():
            refused(response)
            assert seen(response) == unknown, name


async def test_the_code_routes_refuse_a_non_normalising_number_like_an_unknown_one(
    api: AuthApi,
) -> None:
    for path in (
        "/auth/verify-device",
        "/auth/setup-pin/verify",
        "/auth/setup-pin/complete",
        "/auth/pin-reset/verify",
        "/auth/pin-reset/complete",
    ):
        unknown = await api.post(
            path, phoneNumber=UNKNOWN_PHONE, pin=PIN, code="123456", deviceId=DEVICE
        )
        malformed = await api.post(
            path, phoneNumber="12345", pin=PIN, code="123456", deviceId=DEVICE
        )
        refused(unknown)
        assert seen(malformed) == seen(unknown), path


@pytest.mark.parametrize(
    ("path", "eligible_pin", "ineligible_pin"),
    [("/auth/setup-pin/request", None, PIN), ("/auth/pin-reset/request", PIN, None)],
)
async def test_code_requests_answer_the_same_whether_or_not_mail_was_sent(
    api: AuthApi, path: str, eligible_pin: str | None, ineligible_pin: str | None
) -> None:
    eligible = api.provision(email="eligible@example.com", phone="0733333333")
    ineligible = api.provision(email="ineligible@example.com", phone="0744444444")
    pin_hash = await Pbkdf2PinHasher(PIN_ITERATIONS_TESTING).hash(PIN)
    set_user(api.owner, eligible, pin_hash=pin_hash if eligible_pin else None)
    set_user(api.owner, ineligible, pin_hash=pin_hash if ineligible_pin else None)

    sent = await api.post(path, phoneNumber="0733333333", deviceId=DEVICE)
    answers = [
        await api.post(path, phoneNumber=UNKNOWN_PHONE, deviceId=DEVICE),
        await api.post(path, phoneNumber="12345", deviceId=DEVICE),
        await api.post(path, phoneNumber="0744444444", deviceId=DEVICE),
        await api.post(path, phoneNumber="0733333333", deviceId=DEVICE),
    ]
    data = envelope(sent, 202, "check_email")
    assert all(data[key] is None for key in ENVELOPE_KEYS[1:])
    for response in answers:
        assert seen(response) == seen(sent)
    await api.delivered(1)
    await asyncio.sleep(0.05)
    assert [m.to for m in api.mail.sent] == ["eligible@example.com"]


async def test_a_new_pin_shape_is_refused_before_the_number_is_looked_at(api: AuthApi) -> None:
    for path in ("/auth/setup-pin/complete", "/auth/pin-reset/complete"):
        for pin in ("123", "1111", "1234", "4321", "12a4"):
            data = envelope(
                await api.post(path, phoneNumber=UNKNOWN_PHONE, pin=pin, code="1", deviceId=DEVICE),
                400,
                "invalid_pin",
            )
            assert data["minimumPinLength"] == 4
            assert current_statement_count() == 0, (path, pin)


async def test_wrong_codes_are_refused_and_counted_on_the_verify_routes(api: AuthApi) -> None:
    user_id, _ = await api.onboard()
    envelope(
        await api.post("/auth/pin-reset/request", phoneNumber=PHONE, deviceId=DEVICE),
        202,
        "check_email",
    )
    await api.delivered(2)
    code = code_of(api.mail.sent[-1].text)
    wrong = "111111" if code != "111111" else "222222"
    refused(
        await api.post("/auth/pin-reset/verify", phoneNumber=PHONE, code=wrong, deviceId=DEVICE)
    )
    refused(await api.post("/auth/setup-pin/verify", phoneNumber=PHONE, code=code, deviceId=DEVICE))
    refused(
        await api.post(
            "/auth/pin-reset/verify", phoneNumber=PHONE, code=code, deviceId=OTHER_DEVICE
        )
    )
    (reset,) = [c for c in codes(api.owner, user_id) if c["purpose"] == "pin_reset"]
    assert reset["failed_attempts"] == 1
    envelope(
        await api.post("/auth/pin-reset/verify", phoneNumber=PHONE, code=code, deviceId=DEVICE),
        200,
        "code_verified",
    )


async def test_every_new_pin_is_four_digits_whatever_the_organization_pin_length(
    api: AuthApi,
) -> None:
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
    wrong = "111111" if code != "111111" else "222222"
    refused(
        await api.post(
            "/auth/setup-pin/complete", phoneNumber=PHONE, pin=PIN, code=wrong, deviceId=DEVICE
        )
    )
    for longer in ("864209", "86420"):
        data = envelope(
            await api.post(
                "/auth/setup-pin/complete",
                phoneNumber=PHONE,
                pin=longer,
                code=code,
                deviceId=DEVICE,
            ),
            400,
            "invalid_pin",
        )
        assert data["minimumPinLength"] == 4
    envelope(
        await api.post(
            "/auth/setup-pin/complete", phoneNumber=PHONE, pin=PIN, code=code, deviceId=DEVICE
        ),
        200,
        "authenticated",
    )


# --- pre-validation ------------------------------------------------------------------------

_VALID = {"deviceId": DEVICE, "phoneNumber": PHONE}
_FIELD_CASES: list[tuple[str, dict[str, Any]]] = [
    ("deviceId empty", {"deviceId": ""}),
    ("deviceId over 128", {"deviceId": "d" * 129}),
    ("phoneNumber over 14", {"phoneNumber": "0" * 15}),
    ("email over 320", {"email": "x" * 64 + "@" + "d" * 252 + ".com"}),
    ("email not an address", {"email": "Jane <jane@example.com>"}),
    ("pin over 8", {"pin": "123456789"}),
    ("code over 32", {"code": "1" * 33}),
    ("refreshToken over 256", {"refreshToken": "r" * 257}),
    ("U+0000", {"deviceId": "phone" + chr(0)}),
    *[(f"{name} null", {name: None}) for name in FIELDS],
]
_RAW_CASES: list[tuple[str, bytes, dict[str, str]]] = [
    ("malformed JSON", b'{"deviceId":', {"content-type": "application/json"}),
    ("not an object", b'["phone-1"]', {"content-type": "application/json"}),
    ("a number field", b'{"deviceId": 7}', {"content-type": "application/json"}),
    ("unpaired surrogate", b'{"deviceId": "\\ud800"}', {"content-type": "application/json"}),
    ("no body", b"", {"content-type": "application/json"}),
    ("no content type", json.dumps(_VALID).encode(), {}),
    ("text content type", json.dumps(_VALID).encode(), {"content-type": "text/plain"}),
]


async def test_every_field_is_pre_validated_on_every_route_before_any_lookup(
    api: AuthApi,
) -> None:
    for path in BODY_ROUTES:
        for name, change in _FIELD_CASES:
            body = {**auth_body(**_VALID), **change}
            response = await api.client.post(path, json=body)
            data = envelope(response, 400, "invalid_request")
            assert all(data[key] is None for key in ENVELOPE_KEYS[1:]), (path, name)
            assert current_statement_count() == 0, (path, name)
        for name, raw, headers in _RAW_CASES:
            response = await api.client.post(path, content=raw, headers=headers)
            envelope(response, 400, "invalid_request")
            assert current_statement_count() == 0, (path, name)
    attempts = api.owner.execute("SELECT count(*) AS n FROM identity.sign_in_attempts").fetchone()
    assert attempts is not None and attempts["n"] == 0


async def test_the_exact_bounds_pass_pre_validation(api: AuthApi) -> None:
    body = auth_body(
        deviceId="d" * 128,
        phoneNumber="+254 7123 4567",
        email="x" * 64 + "@" + "d" * 251 + ".com",
        pin="12345678",
        code="1" * 32,
        refreshToken="r" * 256,
    )
    assert len(body["phoneNumber"]) == 14
    assert len(body["email"]) == 320
    refused(await api.client.post("/auth/sign-in", json=body))
    missing = await api.client.post("/auth/sign-in", json={"deviceId": DEVICE})
    refused(missing)


# --- lockout, pause and the untrusted cap on the manual clock ------------------------------


async def test_five_wrong_pins_on_a_trusted_device_lock_every_device_until_a_reset(
    api: AuthApi,
) -> None:
    user_id, _ = await api.onboard()
    for _ in range(4):
        refused(await api.sign_in(pin="0000"))
    paused = envelope(await api.sign_in(pin="0000"), 423, "paused")
    assert paused["retryAfterSeconds"] == 900
    assert [paused[k] for k in ENVELOPE_KEYS[1:3]] == [None, None]
    still = envelope(await api.sign_in(), 423, "paused")
    assert still["retryAfterSeconds"] == 900
    # The lock does not lapse: the paused screen's countdown ends in another paused answer.
    api.clock.advance(900.5)
    assert envelope(await api.sign_in(), 423, "paused")["retryAfterSeconds"] == 900
    refused(await api.sign_in(device=OTHER_DEVICE))
    assert user_row(api.owner, user_id)["failed_attempts"] == 5


async def test_the_organization_policy_sets_the_paused_timer(api: AuthApi) -> None:
    user_id, _ = await api.onboard()
    api.owner.execute(
        "UPDATE tenancy.organization_security_policies SET lockout_threshold = 3, "
        "lockout_minutes = 2 WHERE organization_id = (SELECT organization_id "
        "FROM tenancy.memberships WHERE user_id = %s)",
        (user_id,),
    )
    for _ in range(4):
        refused(await api.sign_in(pin="0000"))
    assert envelope(await api.sign_in(pin="0000"), 423, "paused")["retryAfterSeconds"] == 120


async def test_five_wrong_pins_from_untrusted_devices_lock_new_devices_only(
    api: AuthApi,
) -> None:
    user_id, _ = await api.onboard()
    unknown = seen(await api.sign_in(phone=UNKNOWN_PHONE, device=OTHER_DEVICE))
    for _ in range(5):
        refused(await api.sign_in(pin="0000", device=OTHER_DEVICE))
    capped = await api.sign_in(device=OTHER_DEVICE)
    assert seen(capped) == unknown
    assert user_row(api.owner, user_id)["untrusted_failed_attempts"] == 5
    envelope(await api.sign_in(), 200, "authenticated")
    assert seen(await api.sign_in(device="third-device")) == unknown


async def test_a_verified_new_device_clears_the_new_devices_lock(api: AuthApi) -> None:
    user_id, _ = await api.onboard()
    envelope(await api.sign_in(device=OTHER_DEVICE), 202, "verification_required")
    code = code_of(api.mail.sent[-1].text)
    for _ in range(5):
        refused(await api.sign_in(pin="0000", device="third-device"))
    refused(await api.sign_in(device="third-device"))
    envelope(
        await api.post("/auth/verify-device", phoneNumber=PHONE, code=code, deviceId=OTHER_DEVICE),
        200,
        "authenticated",
    )
    assert user_row(api.owner, user_id)["untrusted_failed_attempts"] == 0
    envelope(await api.sign_in(device="third-device"), 202, "verification_required")


async def test_a_pin_reset_lifts_both_locks(api: AuthApi) -> None:
    user_id, _ = await api.onboard()
    for _ in range(5):
        await api.sign_in(pin="0000", device=OTHER_DEVICE)
    for _ in range(5):
        await api.sign_in(pin="0000")
    assert envelope(await api.sign_in(), 423, "paused")
    before = len(api.mail.sent)
    envelope(
        await api.post("/auth/pin-reset/request", phoneNumber=PHONE, deviceId=OTHER_DEVICE),
        202,
        "check_email",
    )
    await api.delivered(before + 1)
    code = code_of(api.mail.sent[-1].text)
    envelope(
        await api.post(
            "/auth/pin-reset/complete",
            phoneNumber=PHONE,
            pin=NEW_PIN,
            code=code,
            deviceId=OTHER_DEVICE,
        ),
        200,
        "authenticated",
    )
    row = user_row(api.owner, user_id)
    assert (row["failed_attempts"], row["untrusted_failed_attempts"]) == (0, 0)
    # The reset removed every other device: the old phone now needs a code.
    envelope(await api.sign_in(pin=NEW_PIN, device=OTHER_DEVICE), 200, "authenticated")
    envelope(await api.sign_in(pin=NEW_PIN), 202, "verification_required")


# --- mail timing, the 503 path and development codes ----------------------------------------


async def test_a_failed_new_device_mail_is_503_and_withdraws_the_code(api: AuthApi) -> None:
    user_id, _ = await api.onboard()
    api.mail.fail_next()
    data = envelope(await api.sign_in(device=OTHER_DEVICE), 503, "service_unavailable")
    assert all(data[key] is None for key in ENVELOPE_KEYS[1:])
    (withdrawn,) = [c for c in codes(api.owner, user_id) if c["purpose"] == "new_device"]
    assert withdrawn["consumed"] and withdrawn["expires_at"] == withdrawn["created_at"]
    envelope(await api.sign_in(device=OTHER_DEVICE), 202, "verification_required")
    assert "\nFor: Confirm this device\n" in api.mail.sent[-1].text


async def test_a_new_device_mail_that_hangs_is_cut_off_at_the_mail_timeout(
    make_api: ApiFactory,
) -> None:
    api = await make_api(email_timeout_seconds=1)
    await api.onboard()
    api.mail.hang_next()
    envelope(await api.sign_in(device=OTHER_DEVICE), 503, "service_unavailable")


async def test_setup_and_reset_codes_are_mailed_after_the_reply(make_api: ApiFactory) -> None:
    api = await make_api(shutdown_grace_seconds=1)
    user_id = api.provision()
    api.mail.hang_next()
    response = await asyncio.wait_for(
        api.post("/auth/setup-pin/request", phoneNumber=PHONE, deviceId=DEVICE), timeout=5
    )
    envelope(response, 202, "check_email")
    await api.attempted(1)
    assert api.mail.sent == []
    (code,) = codes(api.owner, user_id)
    assert not code["consumed"]


async def test_a_failed_setup_mail_withdraws_the_code_and_the_answer_stays_202(
    api: AuthApi,
) -> None:
    user_id = api.provision()
    api.mail.fail_next()
    envelope(
        await api.post("/auth/setup-pin/request", phoneNumber=PHONE, deviceId=DEVICE),
        202,
        "check_email",
    )
    for _ in range(200):
        (code,) = codes(api.owner, user_id)
        if code["consumed"]:
            break
        await asyncio.sleep(0.02)
    assert code["consumed"] and code["expires_at"] == code["created_at"]
    envelope(
        await api.post("/auth/setup-pin/request", phoneNumber=PHONE, deviceId=DEVICE),
        202,
        "check_email",
    )
    await api.delivered(1)


async def test_development_codes_are_returned_in_development(make_api: ApiFactory) -> None:
    api = await make_api(env="development", development_codes=True)
    api.provision()
    requested = envelope(
        await api.post("/auth/setup-pin/request", phoneNumber=PHONE, deviceId=DEVICE),
        202,
        "check_email",
    )
    await api.delivered(1)
    assert requested["developmentCode"] == code_of(api.mail.sent[-1].text)
    code = requested["developmentCode"]
    envelope(
        await api.post(
            "/auth/setup-pin/complete", phoneNumber=PHONE, pin=PIN, code=code, deviceId=DEVICE
        ),
        200,
        "authenticated",
    )
    first = envelope(await api.sign_in(device=OTHER_DEVICE), 202, "verification_required")
    assert first["developmentCode"] == code_of(api.mail.sent[-1].text)
    again = envelope(await api.sign_in(device=OTHER_DEVICE), 202, "verification_required")
    assert again["developmentCode"] == code_of(api.mail.sent[-1].text), "cooldown skipped"


async def test_development_codes_are_absent_in_testing(api: AuthApi) -> None:
    api.provision()
    requested = envelope(
        await api.post("/auth/setup-pin/request", phoneNumber=PHONE, deviceId=DEVICE),
        202,
        "check_email",
    )
    assert requested["developmentCode"] is None


# --- one PBKDF2 derivation per sign-in, budgets, rate limit, logs --------------------------


async def test_every_sign_in_attempt_runs_exactly_one_derivation(make_api: ApiFactory) -> None:
    calls: list[str] = []
    spy = PinHasherSpy(Pbkdf2PinHasher(PIN_ITERATIONS_TESTING), calls)
    api = await make_api(pin_hasher=spy)
    await api.onboard()
    attempts = [
        {},
        {"pin": "0000"},
        {"device": OTHER_DEVICE},
        {"phone": UNKNOWN_PHONE},
        {"phone": "12345"},
    ]
    for attempt in attempts:
        calls.clear()
        await api.sign_in(**attempt)
        assert spy.derivations == 1, attempt


async def test_each_route_stays_within_its_statement_budget(api: AuthApi) -> None:
    _, first = await api.onboard()

    async def budget(response: Awaitable[httpx.Response]) -> int:
        await response
        return current_statement_count()

    assert await budget(api.sign_in()) == 2
    assert await budget(api.post("/auth/unlock", phoneNumber=PHONE, pin=PIN, deviceId=DEVICE)) == 2
    assert await budget(api.sign_in(phone=UNKNOWN_PHONE)) == 2
    assert (
        await budget(api.post("/auth/verify-device", phoneNumber=PHONE, code="1", deviceId=DEVICE))
        == 1
    )
    for path in ("/auth/setup-pin/request", "/auth/pin-reset/request"):
        api.clock.advance(61)
        assert await budget(api.post(path, phoneNumber=PHONE, deviceId=DEVICE)) == 1
    # A reset completion first reads the hash the new PIN must differ from.
    for path, statements in (
        ("/auth/setup-pin/verify", 1),
        ("/auth/setup-pin/complete", 1),
        ("/auth/pin-reset/verify", 1),
        ("/auth/pin-reset/complete", 2),
    ):
        assert (
            await budget(api.post(path, phoneNumber=PHONE, pin=NEW_PIN, code="1", deviceId=DEVICE))
            == statements
        ), path
    assert (
        await budget(api.post("/auth/refresh", refreshToken=first["refreshToken"], deviceId=DEVICE))
        == 1
    )
    assert await budget(api.post("/auth/sign-out", refreshToken="x", deviceId=DEVICE)) == 1
    renewed = envelope(await api.sign_in(), 200, "authenticated")
    bearer = {"Authorization": f"Bearer {renewed['accessToken']}"}
    assert await budget(api.client.get("/auth/session", headers=bearer)) == 1
    assert await budget(api.client.post(f"/auth/devices/{DEVICE}/revoke", headers=bearer)) == 2


async def test_the_rate_limit_answers_429_per_forwarded_client_address(
    make_api: ApiFactory,
) -> None:
    api = await make_api(rate_limit_auth_per_minute=2)
    first = {"X-Forwarded-For": "203.0.113.5"}
    second = {"X-Forwarded-For": "203.0.113.6"}
    for _ in range(2):
        assert (await api.post("/auth/sign-in", headers=first, deviceId="")).status_code == 400
    limited = await api.post("/auth/sign-in", headers=first, deviceId="")
    assert limited.status_code == 429
    assert limited.content == b""
    assert limited.headers["retry-after"] == "60"
    assert limited.headers["x-request-id"]
    assert (await api.client.get("/auth/session", headers=first)).status_code == 429
    assert (await api.post("/auth/sign-in", headers=second, deviceId="")).status_code == 400
    api.clock.advance(60)
    assert (await api.post("/auth/sign-in", headers=first, deviceId="")).status_code == 400


async def test_bodies_that_do_not_parse_count_toward_the_rate_limit(
    make_api: ApiFactory,
) -> None:
    api = await make_api(rate_limit_auth_per_minute=2)
    malformed = await api.client.post(
        "/auth/sign-in", content=b'{"deviceId":', headers={"content-type": "application/json"}
    )
    envelope(malformed, 400, "invalid_request")
    plain = await api.client.post(
        "/auth/sign-in", content=b"phone-1", headers={"content-type": "text/plain"}
    )
    envelope(plain, 400, "invalid_request")
    limited = await api.post("/auth/sign-in", phoneNumber=PHONE, pin=PIN, deviceId=DEVICE)
    assert limited.status_code == 429
    assert limited.content == b""
    assert current_statement_count() == 0


async def test_pin_hashing_at_capacity_answers_503_before_any_decision(
    make_api: ApiFactory,
) -> None:
    api = await make_api()
    user_id, _ = await api.onboard()
    busy = await make_api(pin_hasher=HasherAtCapacity(PIN_ITERATIONS_TESTING))
    for phone in (PHONE, UNKNOWN_PHONE):
        response = await busy.post("/auth/sign-in", phoneNumber=phone, pin=NEW_PIN, deviceId=DEVICE)
        assert response.status_code == 503
        assert response.headers["retry-after"] == "1"
        assert response.json()["title"] == "The service is not available right now."
    assert user_row(api.owner, user_id)["failed_attempts"] == 0


async def test_the_forwarded_address_is_ignored_from_an_untrusted_peer(
    make_api: ApiFactory,
) -> None:
    api = await make_api(rate_limit_auth_per_minute=2, peer=("198.51.100.7", 40000))
    for address in ("203.0.113.5", "203.0.113.6"):
        response = await api.post(
            "/auth/sign-in", headers={"X-Forwarded-For": address}, deviceId=""
        )
        assert response.status_code == 400
    limited = await api.post(
        "/auth/sign-in", headers={"X-Forwarded-For": "203.0.113.7"}, deviceId=""
    )
    assert limited.status_code == 429


@pytest.mark.parametrize(
    ("method", "path"), [("GET", "/auth/session"), ("POST", f"/auth/devices/{DEVICE}/revoke")]
)
async def test_the_rate_limit_counts_bearer_routes_before_authentication(
    make_api: ApiFactory, method: str, path: str
) -> None:
    api = await make_api(rate_limit_auth_per_minute=1)
    first = await api.client.request(method, path)
    assert first.status_code == 401
    assert first.headers["www-authenticate"] == "Bearer"
    limited = await api.client.request(method, path, headers={"Authorization": "Bearer x.y.z"})
    assert limited.status_code == 429
    assert limited.content == b""
    assert limited.headers["retry-after"] == "60"
    assert "www-authenticate" not in limited.headers
    assert (await api.post("/auth/sign-in", deviceId="")).status_code == 429
    assert current_statement_count() == 0


async def test_no_pin_code_token_phone_or_email_reaches_the_log(
    make_api: ApiFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    api = await make_api(log_level="DEBUG", log_format="json")
    pin, wrong_pin = "86420975", "19283746"
    user_id, first = await api.onboard()
    setup_code = code_of(api.mail.sent[-1].text)
    # A PIN of eight digits set before the four-digit rule: distinctive in the log.
    set_user(api.owner, user_id, pin_hash=await api.container.pin_hasher.hash(pin))
    envelope(await api.sign_in(pin=pin, device=OTHER_DEVICE), 202, "verification_required")
    device_code = code_of(api.mail.sent[-1].text)
    await api.post(
        "/auth/verify-device", phoneNumber=PHONE, code=device_code, deviceId=OTHER_DEVICE
    )
    rotated = envelope(
        await api.post("/auth/refresh", refreshToken=first["refreshToken"], deviceId=DEVICE),
        200,
        "authenticated",
    )
    await api.client.get(
        "/auth/session", headers={"Authorization": f"Bearer {rotated['accessToken']}"}
    )
    await api.sign_in(pin=wrong_pin)
    started = await api.client.post(
        "/auth/code",
        json={
            "phoneNumber": PHONE,
            "deviceId": "third-device",
            "purpose": "new_device",
            "code": "000000",
        },
    )
    assert started.status_code == 401
    api.clock.advance(61)
    await api.post("/auth/sign-in", phoneNumber=PHONE, pin=pin, deviceId="third-device")
    third_code = code_of(api.mail.sent[-1].text)
    trusted = await api.client.post(
        "/auth/code",
        json={
            "phoneNumber": PHONE,
            "deviceId": "third-device",
            "deviceName": "Kitchen tablet",
            "purpose": "new_device",
            "code": third_code,
        },
    )
    device_token = trusted.json()["deviceToken"]
    assert device_token
    await api.client.post(
        "/auth/pin",
        json={
            "phoneNumber": PHONE,
            "deviceId": "third-device",
            "deviceToken": device_token,
            "pin": pin,
        },
    )
    await api.client.post(
        "/auth/pin/change",
        json={"currentPin": pin, "newPin": "2580"},
        headers={"Authorization": f"Bearer {trusted.json()['accessToken']}"},
    )
    logs = capsys.readouterr().err
    assert "request.completed" in logs
    secrets = {
        "pin": pin,
        "wrong pin": wrong_pin,
        "setup code": setup_code,
        "device code": device_code,
        "third device code": third_code,
        "device token": device_token,
        "refresh token": first["refreshToken"],
        "rotated refresh token": rotated["refreshToken"],
        "access token": rotated["accessToken"],
        "phone": "712345678",
        "email": EMAIL,
    }
    for name, value in secrets.items():
        assert value not in logs, name
