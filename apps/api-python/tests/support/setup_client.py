"""Helpers of the ``/setup`` contract tests: members signed in through the real flow, the
problem-body and plain-body checks, and the per-request statement count."""

from __future__ import annotations

import json
from collections.abc import Awaitable
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import httpx

from xcode_api.db.pool import current_statement_count

from .client import AuthApi, bearer

JSON_UTF8 = "application/json; charset=utf-8"
PROBLEM = "application/problem+json"
FORBIDDEN = "Not permitted in this organization or data scope."
NOT_FOUND = "Record not found in your scope."
INVALID = "Invalid setup change"
STALE = "Settings changed. Reload before saving."
SECURITY_HEADERS = {
    "cache-control": "no-store",
    "x-content-type-options": "nosniff",
    "referrer-policy": "no-referrer",
}


@dataclass(frozen=True)
class Member:
    user_id: UUID
    tokens: dict[str, Any]

    @property
    def headers(self) -> dict[str, str]:
        return bearer(self.tokens)


async def join(
    api: AuthApi, *, email: str, phone: str, role: str, device: str | None = None
) -> Member:
    """Provision a person with ``role`` and sign them in through the setup-PIN flow."""
    user_id, tokens = await api.onboard(
        email=email, phone=phone, role=role, device=device or f"device-{phone[-4:]}"
    )
    return Member(user_id, tokens)


def ok(response: httpx.Response, status: int = 200) -> Any:
    """Assert a JSON answer with the request id and security headers; return the body."""
    assert response.status_code == status, response.content
    assert response.headers["content-type"] == JSON_UTF8
    assert response.headers.get("x-request-id")
    for name, value in SECURITY_HEADERS.items():
        assert response.headers[name] == value
    return json.loads(response.content)


def problem(
    response: httpx.Response, status: int, title: str, detail: str | None = None
) -> dict[str, Any]:
    """Assert a problem body with this status, title and detail (absent when ``None``)."""
    assert response.status_code == status, response.content
    assert response.headers["content-type"] == PROBLEM
    body: dict[str, Any] = json.loads(response.content)
    assert body["type"] == "about:blank"
    assert body["title"] == title
    assert body["status"] == status
    assert body["requestId"] == response.headers["x-request-id"]
    if detail is None:
        assert "detail" not in body
    else:
        assert body["detail"] == detail
    return body


def empty(response: httpx.Response, status: int) -> None:
    assert response.status_code == status, response.content
    assert response.content == b""
    assert response.headers.get("x-request-id")


async def statements(call: Awaitable[httpx.Response]) -> tuple[httpx.Response, int]:
    response = await call
    return response, current_statement_count()
