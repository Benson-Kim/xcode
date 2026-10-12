from __future__ import annotations

from collections.abc import AsyncIterator, Callable

import httpx
import pytest
from structlog.testing import capture_logs

from xcode_api.container import Container
from xcode_api.main import create_app
from xcode_api.settings import Settings

from ..support.fakes import FakeOpsRepository


async def _client(app) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
            yield c


@pytest.fixture
async def hosted(
    make_settings: Callable[..., Settings],
    ops: FakeOpsRepository,
    make_container: Callable[[Settings, FakeOpsRepository], Container],
) -> AsyncIterator[httpx.AsyncClient]:
    settings = make_settings(allowed_hosts=["api.example.com"])
    async for c in _client(create_app(settings, make_container(settings, ops))):
        yield c


@pytest.mark.parametrize("path", ["/health/live", "/health/ready", "/health"])
async def test_a_probe_by_address_reaches_the_health_routes(
    hosted: httpx.AsyncClient, path: str
) -> None:
    # The image's HEALTHCHECK and a load balancer call the process by address, not by the
    # public host name that XCODE_ALLOWED_HOSTS lists.
    r = await hosted.get(path, headers={"host": "127.0.0.1:5000"})
    assert r.status_code == 200
    assert r.headers["x-request-id"]
    assert r.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(("host", "expected"), [("api.example.com", 200), ("evil.example", 400)])
async def test_every_other_route_still_checks_the_host(
    hosted: httpx.AsyncClient, host: str, expected: int
) -> None:
    r = await hosted.get("/openapi/v1.json", headers={"host": host})
    assert r.status_code == expected


async def test_a_health_lookalike_path_still_checks_the_host(hosted: httpx.AsyncClient) -> None:
    r = await hosted.get("/health/live/", headers={"host": "evil.example"})
    assert r.status_code == 400


async def test_the_request_log_names_the_route_template_not_the_path(
    client: httpx.AsyncClient,
) -> None:
    with capture_logs() as logs:
        r = await client.post("/auth/devices/3f1c0a52-2a7e-4a8e-9a43-5d1f3c1b2e10/revoke")
    assert r.status_code == 401
    lines = [entry for entry in logs if entry["event"] == "request.completed"]
    assert [entry["route"] for entry in lines] == ["/auth/devices/{id}/revoke"]


async def test_the_request_log_keeps_the_path_when_no_route_matched(
    client: httpx.AsyncClient,
) -> None:
    with capture_logs() as logs:
        r = await client.get("/no/such/route")
    assert r.status_code == 404
    lines = [entry for entry in logs if entry["event"] == "request.completed"]
    assert [entry["route"] for entry in lines] == ["/no/such/route"]


async def test_a_failed_readiness_probe_logs_its_reason_and_answers_without_it(
    settings: Settings,
    make_container: Callable[[Settings, FakeOpsRepository], Container],
) -> None:
    app = create_app(settings, make_container(settings, FakeOpsRepository(healthy=False)))
    async for c in _client(app):
        with capture_logs() as logs:
            r = await c.get("/health/ready")
    assert (r.status_code, r.text) == (503, "Unhealthy")
    failed = [entry for entry in logs if entry["event"] == "health.ready.failed"]
    assert len(failed) == 1
    assert failed[0]["reason"]
    assert failed[0]["reason"] not in r.text


async def test_cors_answers_only_the_listed_origin_and_never_allows_credentials(
    make_settings: Callable[..., Settings],
    ops: FakeOpsRepository,
    make_container: Callable[[Settings, FakeOpsRepository], Container],
) -> None:
    settings = make_settings(cors_origins=["https://app.example.com"])
    preflight = {"access-control-request-method": "POST", "access-control-request-headers": "x-a"}
    async for c in _client(create_app(settings, make_container(settings, ops))):
        allowed = await c.options(
            "/auth/sign-in", headers={"origin": "https://app.example.com", **preflight}
        )
        foreign = await c.options(
            "/auth/sign-in", headers={"origin": "https://evil.example", **preflight}
        )
        simple = await c.get("/health", headers={"origin": "https://evil.example"})
    assert allowed.headers["access-control-allow-origin"] == "https://app.example.com"
    assert "access-control-allow-credentials" not in allowed.headers
    assert "x-a" in allowed.headers["access-control-allow-headers"].lower()
    assert "access-control-allow-origin" not in foreign.headers
    assert "access-control-allow-origin" not in simple.headers
