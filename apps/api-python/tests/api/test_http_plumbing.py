from __future__ import annotations

from collections.abc import AsyncIterator, Callable

import httpx
import pytest
from fastapi import APIRouter, Depends

from xcode_api.container import build_container
from xcode_api.db.contract import EXPECTED_CONTRACT_VERSION
from xcode_api.http.dependencies import auth_rate_limit
from xcode_api.http.middleware import client_address
from xcode_api.http.routing import UNSTORABLE_TEXT, SetupRoute
from xcode_api.http.schemas.common import ApiModel, Money
from xcode_api.main import create_app
from xcode_api.settings import Settings

from ..support.fakes import (
    FakeIdentityRepository,
    FakeOpsRepository,
    FakePettyCashRepository,
    FakeRevenueRepository,
    FakeSetupRepository,
    FakeTenancyRepository,
)


class _Probe(ApiModel):
    amount: Money
    label: str = ""


def _app_with_probe(settings: Settings, ops: FakeOpsRepository):
    container = build_container(
        settings,
        ops=ops,
        identity=FakeIdentityRepository(),
        tenancy=FakeTenancyRepository(),
        setup=FakeSetupRepository(),
        revenue=FakeRevenueRepository(),
        pettycash=FakePettyCashRepository(),
    )
    app = create_app(settings, container)
    router = APIRouter()

    @router.post("/_probe/echo")
    async def echo(body: _Probe) -> dict[str, object]:
        return {"amount": body.amount, "label": body.label}

    @router.get("/_probe/boom")
    async def boom() -> None:
        raise RuntimeError("unexpected")

    @router.get("/_probe/limited", dependencies=[Depends(auth_rate_limit)])
    async def limited() -> dict[str, str]:
        return {"ok": "yes"}

    @router.post("/_probe/model", response_model=_Probe)
    async def model(body: _Probe) -> _Probe:
        return body

    setup = APIRouter(route_class=SetupRoute)

    @setup.post("/_probe/setup")
    async def setup_echo(body: _Probe) -> dict[str, object]:
        return {"label": body.label}

    app.include_router(router)
    app.include_router(setup)
    return app


async def _client(app) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
            yield c


@pytest.fixture
async def probe_client(
    settings: Settings, ops: FakeOpsRepository
) -> AsyncIterator[httpx.AsyncClient]:
    async for c in _client(_app_with_probe(settings, ops)):
        yield c


# --- request id ----------------------------------------------------------------------


async def test_request_id_echoed_when_valid(client: httpx.AsyncClient) -> None:
    r = await client.get("/health/live", headers={"X-Request-ID": "abc-123"})
    assert r.headers["x-request-id"] == "abc-123"


async def test_request_id_generated_when_absent(client: httpx.AsyncClient) -> None:
    r = await client.get("/health/live")
    assert len(r.headers["x-request-id"]) >= 8


async def test_bad_request_id_is_replaced(client: httpx.AsyncClient) -> None:
    r = await client.get("/health/live", headers={"X-Request-ID": "x" * 200})
    assert r.headers["x-request-id"] != "x" * 200


# --- forwarded client address --------------------------------------------------------


def _addr(peer: str, trusted: list[str], xff: str | None = None) -> str:
    headers: list[tuple[bytes, bytes]] = []
    if xff is not None:
        headers.append((b"x-forwarded-for", xff.encode()))
    scope = {"type": "http", "client": (peer, 1234), "headers": headers}
    return client_address(scope, trusted)


def test_untrusted_peer_ignores_forwarded() -> None:
    assert _addr("203.0.113.9", ["127.0.0.1"], "198.51.100.1") == "203.0.113.9"


def test_trusted_peer_single_hop() -> None:
    assert _addr("127.0.0.1", ["127.0.0.1"], "198.51.100.1") == "198.51.100.1"


def test_trusted_peer_chained_hops_first_untrusted_wins() -> None:
    assert _addr("127.0.0.1", ["127.0.0.1", "10.0.0.0/8"], "203.0.113.5, 10.0.0.2") == "203.0.113.5"


def test_ipv6_peer_trusted() -> None:
    assert _addr("::1", ["::1"], "203.0.113.7") == "203.0.113.7"


def test_cidr_trust() -> None:
    assert _addr("10.1.2.3", ["10.0.0.0/8"], "203.0.113.8") == "203.0.113.8"


def test_no_forwarded_returns_peer() -> None:
    assert _addr("127.0.0.1", ["127.0.0.1"]) == "127.0.0.1"


# --- security headers ----------------------------------------------------------------


@pytest.mark.parametrize("path,expected", [("/health/live", 200), ("/nope", 404)])
async def test_security_headers_present(
    client: httpx.AsyncClient, path: str, expected: int
) -> None:
    r = await client.get(path)
    assert r.status_code == expected
    assert r.headers["cache-control"] == "no-store"
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["referrer-policy"] == "no-referrer"
    assert "server" not in {k.lower() for k in r.headers}
    assert r.headers.get("x-request-id")


async def test_security_headers_on_500(probe_client: httpx.AsyncClient) -> None:
    r = await probe_client.get("/_probe/boom")
    assert r.status_code == 500
    assert r.headers["cache-control"] == "no-store"
    assert "server" not in {k.lower() for k in r.headers}


# --- body cap ------------------------------------------------------------------------


async def test_body_cap_returns_413(probe_client: httpx.AsyncClient) -> None:
    big = "x" * (1024 * 1024 + 10)
    r = await probe_client.post(
        "/_probe/echo",
        content=big.encode(),
        headers={"content-type": "application/json"},
    )
    assert r.status_code == 413
    assert r.headers["content-type"].startswith("application/problem+json")
    assert r.json()["title"] == "Request body too large"


async def test_chunked_body_over_cap_returns_the_same_413(probe_client: httpx.AsyncClient) -> None:
    async def chunks() -> AsyncIterator[bytes]:
        for _ in range(17):  # 17 x 64 KiB > 1 MiB, sent without Content-Length
            yield b"x" * 65536

    r = await probe_client.post(
        "/_probe/echo",
        content=chunks(),
        headers={"content-type": "application/json"},
    )
    assert r.status_code == 413
    assert r.headers["content-type"].startswith("application/problem+json")
    assert r.json()["title"] == "Request body too large"
    assert r.headers["x-request-id"]


# --- problem shape and 500 body ------------------------------------------------------


async def test_500_body_has_request_id_and_no_exception(probe_client: httpx.AsyncClient) -> None:
    r = await probe_client.get("/_probe/boom")
    body = r.json()
    assert r.headers["content-type"].startswith("application/problem+json")
    assert body["status"] == 500
    assert body["requestId"]
    assert "traceId" in body
    assert "unexpected" not in str(body)


async def test_validation_problem_shape(probe_client: httpx.AsyncClient) -> None:
    r = await probe_client.post("/_probe/echo", json={"label": "no amount"})
    assert r.status_code == 400
    body = r.json()
    assert body["title"] == "Invalid setup change"
    assert body["requestId"]
    assert "errors" in body


# --- 429 -----------------------------------------------------------------------------


async def test_rate_limit_returns_429_empty_with_retry_after(
    make_settings: Callable[..., Settings], ops: FakeOpsRepository
) -> None:
    settings = make_settings(rate_limit_auth_per_minute=1)
    app = _app_with_probe(settings, ops)
    async for c in _client(app):
        first = await c.get("/_probe/limited")
        assert first.status_code == 200
        second = await c.get("/_probe/limited")
        assert second.status_code == 429
        assert second.content == b""
        assert second.headers["retry-after"]
        assert second.headers["x-request-id"]


# --- health bodies -------------------------------------------------------------------


async def test_health_bodies_and_content_types(client: httpx.AsyncClient) -> None:
    live = await client.get("/health/live")
    assert live.text == "Healthy"
    assert live.headers["content-type"].startswith("text/plain")
    ready = await client.get("/health/ready")
    assert ready.text == "Healthy"
    legacy = await client.get("/health")
    assert legacy.json() == {"status": "ok"}
    assert legacy.headers["content-type"].startswith("application/json")


async def test_readiness_unhealthy_when_database_down(
    settings: Settings, make_container: Callable[..., object]
) -> None:
    ops = FakeOpsRepository(healthy=False)
    app = create_app(
        settings,
        build_container(
            settings,
            ops=ops,
            identity=FakeIdentityRepository(),
            tenancy=FakeTenancyRepository(),
            setup=FakeSetupRepository(),
            revenue=FakeRevenueRepository(),
            pettycash=FakePettyCashRepository(),
        ),
    )
    async for c in _client(app):
        r = await c.get("/health/ready")
        assert r.status_code == 503
        assert r.text == "Unhealthy"


async def test_readiness_unhealthy_when_the_contract_version_moved(settings: Settings) -> None:
    ops = FakeOpsRepository(contract_version=EXPECTED_CONTRACT_VERSION + 1)
    app = create_app(
        settings,
        build_container(
            settings,
            ops=ops,
            identity=FakeIdentityRepository(),
            tenancy=FakeTenancyRepository(),
            setup=FakeSetupRepository(),
            revenue=FakeRevenueRepository(),
            pettycash=FakePettyCashRepository(),
        ),
    )
    # No lifespan: startup itself refuses this database; the probe must still answer 503.
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        r = await c.get("/health/ready")
    assert r.status_code == 503
    assert r.text == "Unhealthy"


# --- framework refusals ------------------------------------------------------------------


async def test_unknown_route_is_an_empty_404(client: httpx.AsyncClient) -> None:
    r = await client.get("/nope")
    assert r.status_code == 404
    assert r.content == b""
    assert r.headers["x-request-id"]
    assert r.headers["cache-control"] == "no-store"


async def test_wrong_method_is_an_empty_405_with_allow(client: httpx.AsyncClient) -> None:
    r = await client.post("/health/live")
    assert r.status_code == 405
    assert r.content == b""
    assert "GET" in r.headers["allow"]


# --- OpenAPI -------------------------------------------------------------------------


async def test_openapi_present_in_testing(client: httpx.AsyncClient) -> None:
    r = await client.get("/openapi/v1.json")
    assert r.status_code == 200
    doc = r.json()
    assert doc["openapi"].startswith("3.")


async def test_openapi_absent_when_disabled(
    make_settings: Callable[..., Settings], ops: FakeOpsRepository
) -> None:
    settings = make_settings(openapi_enabled=False)
    app = create_app(
        settings,
        build_container(
            settings,
            ops=ops,
            identity=FakeIdentityRepository(),
            tenancy=FakeTenancyRepository(),
            setup=FakeSetupRepository(),
            revenue=FakeRevenueRepository(),
            pettycash=FakePettyCashRepository(),
        ),
    )
    async for c in _client(app):
        r = await c.get("/openapi/v1.json")
        assert r.status_code == 404


# --- allowed hosts -------------------------------------------------------------------


@pytest.mark.parametrize(("host", "expected"), [("api.example.com", 200), ("evil.example", 400)])
async def test_a_host_outside_the_allowed_hosts_is_refused(
    make_settings: Callable[..., Settings], ops: FakeOpsRepository, host: str, expected: int
) -> None:
    app = _app_with_probe(make_settings(allowed_hosts=["api.example.com"]), ops)
    async for c in _client(app):
        r = await c.get("/openapi/v1.json", headers={"host": host})
        assert r.status_code == expected


# --- JSON handling -------------------------------------------------------------------


async def test_unknown_properties_ignored(probe_client: httpx.AsyncClient) -> None:
    r = await probe_client.post("/_probe/echo", json={"amount": 10, "label": "x", "unknown": 1})
    assert r.status_code == 200
    assert r.json()["label"] == "x"


async def test_money_refuses_float_with_more_than_two_decimals(
    probe_client: httpx.AsyncClient,
) -> None:
    r = await probe_client.post("/_probe/echo", json={"amount": 1.234})
    assert r.status_code == 400


async def test_money_refuses_text_that_is_not_a_number(probe_client: httpx.AsyncClient) -> None:
    r = await probe_client.post("/_probe/echo", json={"amount": "abc"})
    assert r.status_code == 400
    assert r.json()["title"] == "Invalid setup change"


async def test_a_setup_body_keeps_a_surrogate_pair_and_refuses_what_text_cannot_store(
    probe_client: httpx.AsyncClient,
) -> None:
    json_type = {"content-type": "application/json"}
    pair = '{"amount": 1, "label": "\\ud83d\\ude00"}'
    r = await probe_client.post("/_probe/setup", content=pair, headers=json_type)
    assert r.status_code == 200
    assert r.json() == {"label": chr(0x1F600)}
    for text in ("\\u0000", "\\udc00", "a\\ud83d"):
        body = '{"amount": 1, "label": "' + text + '"}'
        r = await probe_client.post("/_probe/setup", content=body, headers=json_type)
        assert r.status_code == 400
        assert (r.json()["title"], r.json()["detail"]) == ("Invalid setup change", UNSTORABLE_TEXT)
    nested = '{"amount": 1, "label": "x", "extra": [{"k\\u0000": 1}]}'
    r = await probe_client.post("/_probe/setup", content=nested, headers=json_type)
    assert r.status_code == 400
    r = await probe_client.post("/_probe/setup?label=%00", json={"amount": 1})
    assert r.json()["errors"] == {"query.label": [UNSTORABLE_TEXT]}


async def test_money_accepts_two_decimals(probe_client: httpx.AsyncClient) -> None:
    r = await probe_client.post("/_probe/echo", json={"amount": 10.5})
    assert r.status_code == 200
    assert str(r.json()["amount"]) in ("10.5", "10.50")


async def test_money_is_a_json_number_under_a_response_model(
    probe_client: httpx.AsyncClient,
) -> None:
    fractional = await probe_client.post("/_probe/model", json={"amount": 10.5})
    assert fractional.status_code == 200
    assert '"amount":10.5' in fractional.text
    assert isinstance(fractional.json()["amount"], float)
    whole = await probe_client.post("/_probe/model", json={"amount": 2166})
    assert '"amount":2166' in whole.text
    assert isinstance(whole.json()["amount"], int)
