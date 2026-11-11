"""Invitations against the real database (``docs/07-auth.md`` section 13, rows A14 and S57):
adding a person mails a link and a code, the link with the person's number answers a
one-time setup code, every mismatch answers the same 401, a problem is told only once the
token and the number both match, the shape check and the two throttles, and send-again with
its refusals."""

from __future__ import annotations

import json
import re
from typing import Any

import httpx
import pytest

from ..support.client import ENVELOPE_KEYS, JSON_UTF8, ApiFactory, AuthApi, envelope
from ..support.fakes import role_rights
from ..support.setup_client import FORBIDDEN, INVALID, NOT_FOUND, Member, empty, join, ok, problem

pytestmark = pytest.mark.asyncio(loop_scope="session")

REDEEM_KEYS = [*ENVELOPE_KEYS, "code", "inviteProblem"]
LINK = re.compile(r"(https?://[^/\s]+)/invite#([A-Za-z0-9_-]{43})$", re.MULTILINE)
CODE = re.compile(r"type (\d{3}) (\d{3})\.")
NOT_NEEDED = "This person has already set up their PIN and needs no invitation."
PERSON_PHONE = "0722000111"
PERSON_EMAIL = "jane.njeri@example.com"
OTHER_PHONE = "0722000222"
OTHER_EMAIL = "paul.otieno@example.com"
WEEK = 7 * 24 * 3600
SELF = "Use the profile menu for your own PIN and devices."


@pytest.fixture
async def api(make_api: ApiFactory) -> AuthApi:
    return await make_api()


@pytest.fixture
async def owner(api: AuthApi) -> Member:
    return await join(api, email="ann@example.com", phone="0711000111", role="Owner")


def person(**changes: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "firstName": "Jane",
        "lastName": "Njeri",
        "email": PERSON_EMAIL,
        "phoneNumber": PERSON_PHONE,
        "role": "Revenue clerk",
        "scopeMode": "all",
        "companyIds": [],
        "vehicleIds": [],
        "permissions": list(role_rights("Revenue clerk")),
        "approvalLimit": None,
    }
    body.update(changes)
    return body


async def invite(api: AuthApi, owner: Member, **changes: Any) -> str:
    """Add a person and wait for their invitation mail; return the new person's id."""
    before = len(api.mail.sent)
    created = ok(
        await api.client.post("/setup/people", json=person(**changes), headers=owner.headers)
    )
    await api.delivered(before + 1)
    return str(created["id"])


def invitation(api: AuthApi, email: str) -> tuple[str, str, str]:
    """The newest invitation mailed to ``email``: (link host, token, code)."""
    mail = next(m for m in reversed(api.mail.sent) if m.to == email and "/invite#" in m.text)
    link = LINK.search(mail.text)
    code = CODE.search(mail.text)
    assert link is not None and code is not None, mail.text
    return link.group(1), link.group(2), code.group(1) + code.group(2)


async def redeem(api: AuthApi, **fields: Any) -> httpx.Response:
    body = {"token": "", "phoneNumber": "", "deviceId": "phone-9", "deviceName": "Work phone"}
    body.update(fields)
    return await api.client.post("/auth/invite/redeem", json=body)


def answer(response: httpx.Response, status_code: int, status: str) -> dict[str, Any]:
    assert response.status_code == status_code, response.content
    assert response.headers["content-type"] == JSON_UTF8
    data: dict[str, Any] = json.loads(response.content)
    assert list(data) == REDEEM_KEYS
    assert data["status"] == status
    return data


async def test_a_new_person_is_mailed_a_link_and_a_code_on_the_configured_host(
    api: AuthApi, owner: Member
) -> None:
    before = len(api.mail.sent)
    headers = {**owner.headers, "X-Forwarded-Host": "evil.example", "Forwarded": "host=evil"}
    ok(await api.client.post("/setup/people", json=person(), headers=headers))
    await api.delivered(before + 1)
    host, token, code = invitation(api, PERSON_EMAIL)
    mail = api.mail.sent[-1]
    assert "evil" not in mail.text and "evil" not in (mail.html or "")
    assert host in ("http://localhost:3000", str(api.container.settings.public_web_url))
    assert len(token) == 43 and len(code) == 6
    assert PERSON_PHONE not in mail.text and "+254722000111" not in mail.text
    assert token not in str(mail.tags) and code not in str(mail.tags)


async def test_the_link_and_number_answer_a_code_that_sets_the_first_pin(
    api: AuthApi, owner: Member
) -> None:
    user_id = await invite(api, owner)
    _, token, _ = invitation(api, PERSON_EMAIL)
    redeemed = answer(
        await redeem(api, token=token, phoneNumber=PERSON_PHONE), 202, "verification_required"
    )
    assert re.fullmatch(r"\d{6}", redeemed["code"])
    assert redeemed["inviteProblem"] is None
    assert redeemed["accessToken"] is None and redeemed["developmentCode"] is None
    done = await api.client.post(
        "/auth/pin/new",
        json={
            "phoneNumber": PERSON_PHONE,
            "deviceId": "phone-9",
            "deviceName": "Work phone",
            "purpose": "first_setup",
            "code": redeemed["code"],
            "pin": "3971",
        },
    )
    assert done.status_code == 200, done.content
    assert json.loads(done.content)["status"] == "authenticated"
    read = ok(await api.client.get(f"/setup/people/{user_id}", headers=owner.headers))
    assert read["hasPin"] is True and read["signIn"]["invitation"] is None
    used = answer(
        await redeem(api, token=token, phoneNumber=PERSON_PHONE), 401, "authentication_failed"
    )
    assert used["inviteProblem"] == "used" and used["code"] is None


async def test_an_invited_number_starts_with_the_invitation_flag_and_no_mailed_code(
    api: AuthApi, owner: Member
) -> None:
    await invite(api, owner)
    before = len(api.mail.sent)
    response = await api.client.post(
        "/auth/start", json={"phoneNumber": PERSON_PHONE, "deviceId": "phone-9"}
    )
    assert response.status_code == 202, response.content
    data = json.loads(response.content)
    assert data["status"] == "verification_required"
    assert (data["purpose"], data["invitation"]) == ("first_setup", True)
    assert data["maskedEmail"] == "j***@example.com"
    assert data["developmentCode"] is None
    await invite(api, owner, firstName="Paul", email=OTHER_EMAIL, phoneNumber=OTHER_PHONE)
    assert [mail.to for mail in api.mail.sent[before:]] == [OTHER_EMAIL]


async def test_every_mismatch_answers_the_same_bytes(api: AuthApi, owner: Member) -> None:
    await invite(api, owner)
    await invite(api, owner, firstName="Paul", email=OTHER_EMAIL, phoneNumber=OTHER_PHONE)
    _, mine, _ = invitation(api, PERSON_EMAIL)
    _, theirs, _ = invitation(api, OTHER_EMAIL)
    unknown = "A" * 43
    answers = [
        await redeem(api, token=unknown, phoneNumber=PERSON_PHONE),
        await redeem(api, token=mine, phoneNumber="0733000999"),
        await redeem(api, token=mine, phoneNumber=OTHER_PHONE),
        await redeem(api, token=theirs, phoneNumber=PERSON_PHONE),
    ]
    for response in answers:
        data = answer(response, 401, "authentication_failed")
        assert data["inviteProblem"] is None and data["code"] is None
        assert response.headers["www-authenticate"] == "Bearer"
    assert len({r.content for r in answers}) == 1


async def test_a_problem_is_told_only_when_the_token_and_number_match(
    api: AuthApi, owner: Member
) -> None:
    await invite(api, owner)
    _, token, _ = invitation(api, PERSON_EMAIL)
    api.clock.advance(WEEK + 1)
    expired = answer(
        await redeem(api, token=token, phoneNumber=PERSON_PHONE), 401, "authentication_failed"
    )
    assert expired["inviteProblem"] == "expired"
    hidden = answer(
        await redeem(api, token=token, phoneNumber="0733000999"), 401, "authentication_failed"
    )
    assert hidden["inviteProblem"] is None


async def test_blocking_the_person_revokes_the_invitation(api: AuthApi, owner: Member) -> None:
    user_id = await invite(api, owner)
    _, token, _ = invitation(api, PERSON_EMAIL)
    ok(
        await api.client.post(
            f"/setup/people/{user_id}/deactivate",
            json={"version": 1, "reason": "Left"},
            headers=owner.headers,
        )
    )
    revoked = answer(
        await redeem(api, token=token, phoneNumber=PERSON_PHONE), 401, "authentication_failed"
    )
    assert revoked["inviteProblem"] == "revoked"


@pytest.mark.parametrize(
    "fields",
    [
        {"token": ""},
        {"phoneNumber": ""},
        {"token": "A" * 129},
        {"deviceName": "x" * 101},
        {"token": None},
        {"token": 42},
    ],
)
async def test_a_bad_shape_is_the_invalid_request_envelope(
    api: AuthApi, fields: dict[str, Any]
) -> None:
    body: dict[str, Any] = {"token": "A" * 43, "phoneNumber": PERSON_PHONE}
    body.update(fields)
    envelope(await redeem(api, **body), 400, "invalid_request")


async def test_extra_properties_are_ignored(api: AuthApi, owner: Member) -> None:
    user_id = await invite(api, owner)
    _, token, _ = invitation(api, PERSON_EMAIL)
    answer(
        await redeem(
            api,
            token=token,
            phoneNumber=PERSON_PHONE,
            role="Owner",
            userId=str(owner.user_id),
            organizationId="00000000-0000-4000-8000-000000000000",
            pinHash="x",
        ),
        202,
        "verification_required",
    )
    read = ok(await api.client.get(f"/setup/people/{user_id}", headers=owner.headers))
    assert read["role"] == "Revenue clerk"


async def test_one_link_is_throttled_by_its_digest(make_api: ApiFactory) -> None:
    api = await make_api(rate_limit_pin_per_device=3)
    owner = await join(api, email="ann@example.com", phone="0711000111", role="Owner")
    await invite(api, owner)
    _, token, _ = invitation(api, PERSON_EMAIL)
    for phone in ("0733000901", "0733000902", "0733000903"):
        answer(await redeem(api, token=token, phoneNumber=phone), 401, "authentication_failed")
    limited = await redeem(api, token=token, phoneNumber=PERSON_PHONE)
    assert limited.status_code == 429, limited.content
    other = await redeem(api, token="B" * 43, phoneNumber=PERSON_PHONE)
    answer(other, 401, "authentication_failed")


async def test_one_address_is_throttled_before_the_shape_check(make_api: ApiFactory) -> None:
    api = await make_api(rate_limit_pin_per_address=2)
    for _ in range(2):
        envelope(await redeem(api, token="", phoneNumber=""), 400, "invalid_request")
    limited = await redeem(api, token="A" * 43, phoneNumber=PERSON_PHONE)
    assert limited.status_code == 429, limited.content


async def test_send_again_replaces_the_link(api: AuthApi, owner: Member) -> None:
    user_id = await invite(api, owner)
    _, first, _ = invitation(api, PERSON_EMAIL)
    before = len(api.mail.sent)
    response = await api.client.post(f"/setup/people/{user_id}/invitation", headers=owner.headers)
    assert ok(response) == {"id": user_id}
    await api.delivered(before + 1)
    shown = ok(await api.client.get(f"/setup/people/{user_id}", headers=owner.headers))
    live = shown["signIn"]["invitation"]
    assert sorted(live) == ["expiresAt", "sentAt", "state"]
    assert live["state"] in ("pending", "sent") and live["expiresAt"] is not None
    _, second, _ = invitation(api, PERSON_EMAIL)
    assert second != first
    replaced = answer(
        await redeem(api, token=first, phoneNumber=PERSON_PHONE), 401, "authentication_failed"
    )
    assert replaced["inviteProblem"] == "revoked"
    answer(await redeem(api, token=second, phoneNumber=PERSON_PHONE), 202, "verification_required")


async def test_send_again_refusals(api: AuthApi, owner: Member) -> None:
    clerk = await join(api, email="joy@example.com", phone="0711000222", role="Revenue clerk")
    user_id = await invite(api, owner)
    base = "/setup/people"
    problem(
        await api.client.post(f"{base}/{user_id}/invitation", headers=clerk.headers),
        403,
        FORBIDDEN,
    )
    problem(
        await api.client.post(f"{base}/{clerk.user_id}/invitation", headers=owner.headers),
        400,
        INVALID,
        NOT_NEEDED,
    )
    problem(
        await api.client.post(f"{base}/{owner.user_id}/invitation", headers=owner.headers),
        400,
        INVALID,
        SELF,
    )
    unknown = "00000000-0000-4000-8000-000000000000"
    problem(
        await api.client.post(f"{base}/{unknown}/invitation", headers=owner.headers),
        404,
        NOT_FOUND,
    )
    empty(await api.client.post(f"{base}/not-a-uuid/invitation", headers=owner.headers), 404)
    anonymous = await api.client.post(f"{base}/{user_id}/invitation")
    assert anonymous.status_code == 401
