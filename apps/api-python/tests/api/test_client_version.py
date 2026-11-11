"""The 426 for an outdated mobile build: ``X-XCODE-Client: mobile/<version>`` below
``XCODE_MIN_MOBILE_VERSION``, or not a version at all, answers ``update_required`` on every
route but the health probes, before authentication; any other caller is never checked."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable

import httpx
import pytest

from xcode_api.container import Container
from xcode_api.main import create_app
from xcode_api.settings import Settings

from ..support.fakes import FakeOpsRepository

MINIMUM = "1.4.0"
HEADER = "X-XCODE-Client"
UPDATE_REQUIRED = {
    "status": "update_required",
    "minimumVersion": MINIMUM,
    "message": "This version of the app is no longer supported. Update the app to continue.",
}


async def _serve(app) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
            yield c


@pytest.fixture
def gated_app(
    make_settings: Callable[..., Settings],
    ops: FakeOpsRepository,
    make_container: Callable[[Settings, FakeOpsRepository], Container],
):
    settings = make_settings(min_mobile_version=MINIMUM, metrics_enabled=True)
    return create_app(settings, make_container(settings, ops))


@pytest.fixture
async def gated(gated_app) -> AsyncIterator[httpx.AsyncClient]:
    async for c in _serve(gated_app):
        yield c


@pytest.mark.parametrize("build", ["mobile/1.3.9", "mobile/0.9", "mobile/1.3.10"])
async def test_an_older_mobile_build_is_told_to_update(
    gated: httpx.AsyncClient, build: str
) -> None:
    r = await gated.get("/auth/session", headers={HEADER: build})
    assert r.status_code == 426
    assert r.json() == UPDATE_REQUIRED
    assert r.headers["content-type"] == "application/json; charset=utf-8"
    assert r.headers["x-request-id"]
    assert r.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    "build", ["mobile/", "mobile/latest", "mobile/1.4.0-beta", "mobile/1..4", "mobile/v1.5.0"]
)
async def test_a_mobile_build_without_a_readable_version_is_told_to_update(
    gated: httpx.AsyncClient, build: str
) -> None:
    r = await gated.get("/auth/session", headers={HEADER: build})
    assert r.status_code == 426
    assert r.json()["status"] == "update_required"


@pytest.mark.parametrize("build", ["mobile/1.4.0", "mobile/1.4", "mobile/1.4.1", "mobile/2.0.0"])
async def test_a_build_at_or_above_the_minimum_reaches_the_route(
    gated: httpx.AsyncClient, build: str
) -> None:
    r = await gated.get("/auth/session", headers={HEADER: build})
    assert r.status_code == 401
    assert r.content == b""


@pytest.mark.parametrize(
    "headers", [{}, {HEADER: "web/1.0.0"}, {HEADER: "Mobile/1.0.0"}, {HEADER: "1.0.0"}]
)
async def test_a_caller_that_is_not_a_mobile_build_is_never_checked(
    gated: httpx.AsyncClient, headers: dict[str, str]
) -> None:
    r = await gated.get("/auth/session", headers=headers)
    assert r.status_code == 401


async def test_the_answer_comes_before_authentication_and_the_body_on_every_route(
    gated: httpx.AsyncClient,
) -> None:
    old = {HEADER: "mobile/1.0.0"}
    listed = await gated.get("/setup/companies", headers=old)
    signed_in = await gated.post(
        "/auth/sign-in",
        headers=old,
        json={},
    )
    unknown = await gated.get("/no/such/route", headers=old)
    for r in (listed, signed_in, unknown):
        assert r.status_code == 426
        assert r.json() == UPDATE_REQUIRED


@pytest.mark.parametrize("path", ["/health/live", "/health/ready", "/health"])
async def test_the_health_probes_answer_any_build(gated: httpx.AsyncClient, path: str) -> None:
    r = await gated.get(path, headers={HEADER: "mobile/0.1.0"})
    assert r.status_code == 200


async def test_the_answer_is_counted_as_a_426(gated_app) -> None:
    async for c in _serve(gated_app):
        await c.get("/auth/session", headers={HEADER: "mobile/1.0.0"})
    sample = gated_app.state.metrics.registry.get_sample_value(
        "http_requests_total", {"route": "unmatched", "method": "GET", "status": "426"}
    )
    assert sample == 1


async def test_without_a_minimum_every_build_reaches_the_route(client: httpx.AsyncClient) -> None:
    r = await client.get("/auth/session", headers={HEADER: "mobile/0.0.1"})
    assert r.status_code == 401
