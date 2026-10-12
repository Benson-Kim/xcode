"""Response compression against the real database (``docs/06-http-contract.md`` section 1.4,
the .NET ``CompressionTests``): ``/setup/`` answers above 1 KiB are gzipped for a client that
accepts it and keep the request id and the security headers; every ``/setup/`` answer
carries ``Vary: Accept-Encoding``; ``/auth/`` answers and health are never compressed."""

from __future__ import annotations

import gzip
import json

import httpx
import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route

from xcode_api.http.middleware import SetupCompressionMiddleware

from ..support.client import ApiFactory, AuthApi
from ..support.setup_client import SECURITY_HEADERS, Member, join

pytestmark = pytest.mark.asyncio(loop_scope="session")

GZIP = {"accept-encoding": "gzip"}
IDENTITY = {"accept-encoding": "identity"}


@pytest.fixture
async def api(make_api: ApiFactory) -> AuthApi:
    return await make_api()


@pytest.fixture
async def owner(api: AuthApi) -> Member:
    return await join(api, email="ann@example.com", phone="0711000111", role="Owner")


async def _raw(api: AuthApi, path: str, headers: dict[str, str]) -> tuple[httpx.Response, bytes]:
    async with api.client.stream("GET", path, headers=headers) as response:
        raw = b"".join([chunk async for chunk in response.aiter_raw()])
    return response, raw


@pytest.mark.parametrize("path", ["/setup/access/catalog", "/setup/history?pageSize=100"])
async def test_a_large_setup_answer_is_gzipped_for_a_client_that_accepts_it(
    api: AuthApi, owner: Member, path: str
) -> None:
    for number in range(12):
        created = await api.client.post(
            "/setup/companies", json={"name": f"Company {number:02d}"}, headers=owner.headers
        )
        assert created.status_code == 200, created.content
    plain, plain_raw = await _raw(api, path, {**owner.headers, **IDENTITY})
    assert plain.status_code == 200
    assert "content-encoding" not in plain.headers
    assert "accept-encoding" in plain.headers["vary"].lower()
    assert len(plain_raw) > 1024
    sent_id = "compression-test-0001"
    packed, packed_raw = await _raw(api, path, {**owner.headers, **GZIP, "x-request-id": sent_id})
    assert packed.status_code == 200
    assert packed.headers["content-encoding"] == "gzip"
    assert "accept-encoding" in packed.headers["vary"].lower()
    assert packed.headers["x-request-id"] == sent_id
    for name, value in SECURITY_HEADERS.items():
        assert packed.headers[name] == value
    assert int(packed.headers["content-length"]) == len(packed_raw)
    assert len(packed_raw) < len(plain_raw) / 2
    assert json.loads(gzip.decompress(packed_raw)) == json.loads(plain_raw)


async def test_a_small_setup_answer_is_sent_plain_but_still_varies(
    api: AuthApi, owner: Member
) -> None:
    response, raw = await _raw(api, "/setup/access/me", {**owner.headers, **GZIP})
    assert response.status_code == 200
    assert len(raw) <= 1024
    assert "content-encoding" not in response.headers
    assert "accept-encoding" in response.headers["vary"].lower()


async def test_auth_answers_are_never_compressed(api: AuthApi, owner: Member) -> None:
    for encoding in ("gzip", "gzip, deflate, br"):
        response = await api.client.post(
            "/auth/refresh",
            json={"refreshToken": owner.tokens["refreshToken"], "deviceId": "device-0111"},
            headers={"accept-encoding": encoding},
        )
        assert response.status_code == 200, response.content
        assert "content-encoding" not in response.headers
        assert "accept-encoding" not in response.headers.get("vary", "").lower()
        assert "accessToken" in response.json()
        owner.tokens.update(response.json())


@pytest.mark.parametrize("path", ["/health", "/health/live", "/health/ready"])
async def test_health_is_never_compressed(api: AuthApi, path: str) -> None:
    response = await api.client.get(path, headers=GZIP)
    assert response.status_code == 200
    assert "content-encoding" not in response.headers
    assert "vary" not in response.headers


async def test_a_spreadsheet_is_never_gzipped_but_a_large_pdf_is() -> None:
    xlsx = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    async def spreadsheet(request: Request) -> Response:
        return Response(b"PK" + b"x" * 4096, media_type=xlsx)

    async def document(request: Request) -> Response:
        return Response(b"%PDF" + b"x" * 4096, media_type="application/pdf")

    app = SetupCompressionMiddleware(
        Starlette(routes=[Route("/setup/a.xlsx", spreadsheet), Route("/setup/a.pdf", document)])
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        sheet = await c.get("/setup/a.xlsx", headers=GZIP)
        pdf = await c.get("/setup/a.pdf", headers=GZIP)
    assert "content-encoding" not in sheet.headers
    assert "accept-encoding" in sheet.headers["vary"].lower()
    assert pdf.headers["content-encoding"] == "gzip"
