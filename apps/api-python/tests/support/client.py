"""An httpx client on the real app and database, with the steps every authenticated test
needs: provision a person through the operator routine and set the first PIN through the
real setup flow (A04, A05, A06), so tokens come from the routines, never minted by hand."""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import httpx

from xcode_api.container import Container

from .clock import ManualClock
from .mail import MailSpy
from .scenario import Conn, provision

PHONE = "0712345678"
EMAIL = "jane.doe@example.com"
PIN = "3971"
DEVICE = "phone-1"

FIELDS = ("email", "phoneNumber", "pin", "deviceId", "code", "refreshToken")
ENVELOPE_KEYS = [
    "status",
    "accessToken",
    "refreshToken",
    "retryAfterSeconds",
    "developmentCode",
    "maskedEmail",
    "minimumPinLength",
]
JSON_UTF8 = "application/json; charset=utf-8"


def auth_body(**fields: Any) -> dict[str, Any]:
    """The six strings every ``/auth`` body carries, ``""`` where the test gives none."""
    return {name: fields.get(name, "") for name in FIELDS}


def envelope(response: httpx.Response, status_code: int, status: str) -> dict[str, Any]:
    """Assert the status, the content type, the request id and the seven envelope
    properties in order; return the body."""
    assert response.status_code == status_code, response.content
    assert response.headers["content-type"] == JSON_UTF8
    assert response.headers["x-request-id"]
    data: dict[str, Any] = json.loads(response.content)
    assert list(data) == ENVELOPE_KEYS
    assert data["status"] == status
    return data


def bearer(tokens: dict[str, Any]) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['accessToken']}"}


def code_of(text: str) -> str:
    match = re.match(r"Code: (\d{6})\nFor: [A-Za-z ]+\nDevice: [A-Za-z0-9 .()+-]+$", text)
    assert match is not None, text
    return match.group(1)


@dataclass
class AuthApi:
    client: httpx.AsyncClient
    mail: MailSpy
    clock: ManualClock
    container: Container
    operator: Conn
    owner: Conn

    async def post(
        self, path: str, *, headers: dict[str, str] | None = None, **fields: Any
    ) -> httpx.Response:
        response = await self.client.post(path, json=auth_body(**fields), headers=headers)
        assert response.headers.get("x-request-id")
        return response

    async def sign_in(
        self, *, phone: str = PHONE, pin: str = PIN, device: str = DEVICE
    ) -> httpx.Response:
        return await self.post("/auth/sign-in", phoneNumber=phone, pin=pin, deviceId=device)

    async def delivered(self, count: int) -> None:
        for _ in range(500):
            if len(self.mail.sent) >= count:
                return
            await asyncio.sleep(0.01)
        raise AssertionError(f"expected {count} delivered mails, got {len(self.mail.sent)}")

    async def attempted(self, count: int) -> None:
        for _ in range(500):
            if len(self.mail.attempts) >= count:
                await asyncio.sleep(0.05)
                return
            await asyncio.sleep(0.01)
        raise AssertionError(f"expected {count} mail attempts, got {len(self.mail.attempts)}")

    def provision(self, *, email: str = EMAIL, phone: str = PHONE, role: str | None = None) -> UUID:
        result = provision(
            self.operator,
            email=email,
            phone=phone,
            role=role,
            first_name="Jane",
            last_name="Doe",
            now=self.clock.now(),
        )
        return UUID(result["user_id"])

    async def onboard(
        self,
        *,
        email: str = EMAIL,
        phone: str = PHONE,
        device: str = DEVICE,
        pin: str = PIN,
        role: str | None = None,
    ) -> tuple[UUID, dict[str, Any]]:
        """Provision a person and set the first PIN through A04, A05 and A06; the device is
        then trusted and the answer carries the first token pair. The clock then moves past
        the minute of the first-PIN code, so the person's next code is not held by the
        one-code-a-minute rule."""
        user_id = self.provision(email=email, phone=phone, role=role)
        before = len(self.mail.sent)
        envelope(
            await self.post("/auth/setup-pin/request", phoneNumber=phone, deviceId=device),
            202,
            "check_email",
        )
        await self.delivered(before + 1)
        code = code_of(self.mail.sent[-1].text)
        envelope(
            await self.post(
                "/auth/setup-pin/verify", phoneNumber=phone, code=code, deviceId=device
            ),
            200,
            "code_verified",
        )
        data = envelope(
            await self.post(
                "/auth/setup-pin/complete", phoneNumber=phone, pin=pin, code=code, deviceId=device
            ),
            200,
            "authenticated",
        )
        self.clock.advance(61)
        return user_id, data


ApiFactory = Callable[..., Awaitable[AuthApi]]
