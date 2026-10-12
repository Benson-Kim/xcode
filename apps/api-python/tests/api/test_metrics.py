"""``GET /metrics`` against the real database (``docs/08-operability.md`` section 5): every
series after one request of each kind, labels that never carry an id, a phone number, an
address or a raw path, the four internal refusal reasons only, and no route at all when the
flag is off."""

from __future__ import annotations

import re
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack
from typing import Any

import httpx
import pytest
from prometheus_client.parser import text_string_to_metric_families
from psycopg_pool import AsyncConnectionPool

from xcode_api.container import build_container
from xcode_api.main import create_app, pool_states
from xcode_api.settings import Settings

from ..support.client import AuthApi
from ..support.clock import ManualClock
from ..support.mail import MailSpy
from ..support.scenario import Conn
from ..support.setup_client import join

pytestmark = pytest.mark.asyncio(loop_scope="session")

SERIES = {
    "http_requests_total",
    "http_request_duration_seconds",
    "db_routine_duration_seconds",
    "db_pool_connections",
    "auth_refusals_total",
    "mail_queue_depth",
    "rate_limit_rejections_total",
}
LABELS = {
    "route": re.compile(r"^(/[a-z0-9{}._-]*)+$|^unmatched$"),
    "method": re.compile(r"^(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)$"),
    "status": re.compile(r"^[1-5][0-9]{2}$"),
    "routine": re.compile(r"^[a-z_][a-z0-9_]*$"),
    "state": re.compile(r"^(idle|busy|waiting)$"),
    "reason": re.compile(r"^(unknown|paused|capped|wrong_pin)$"),
    "le": re.compile(r"^([0-9.]+|\+Inf)$"),
}
UNKNOWN_PHONE = "0799123456"


async def _app(
    stack: AsyncExitStack,
    settings: Settings,
    pool: AsyncConnectionPool[Any],
    clock: ManualClock,
    mail: MailSpy,
) -> httpx.AsyncClient:
    container = build_container(settings, pool, clock=clock, mailer=mail)
    app = create_app(settings, container, pool_states=lambda: pool_states(pool))
    await stack.enter_async_context(app.router.lifespan_context(app))
    transport = httpx.ASGITransport(
        app=app, raise_app_exceptions=False, client=("127.0.0.1", 50000)
    )
    return await stack.enter_async_context(
        httpx.AsyncClient(transport=transport, base_url="http://testserver")
    )


@pytest.fixture
async def metered(
    app_url: str,
    owner_url: str,
    pool: AsyncConnectionPool[Any],
    manual_clock: ManualClock,
    mail_spy: MailSpy,
    operator_conn: Conn,
    owner_conn: Conn,
) -> AsyncIterator[AuthApi]:
    settings = Settings.for_tests(
        database_url=app_url,
        migration_database_url=owner_url,
        metrics_enabled=True,
        allowed_hosts=["api.example.com"],
    )
    async with AsyncExitStack() as stack:
        client = await _app(stack, settings, pool, manual_clock, mail_spy)
        client.headers["host"] = "api.example.com"
        container = client._transport.app.state.container  # type: ignore[attr-defined]
        yield AuthApi(client, mail_spy, manual_clock, container, operator_conn, owner_conn)


def _families(text: str) -> dict[str, Any]:
    return {family.name: family for family in text_string_to_metric_families(text)}


def _value(families: dict[str, Any], sample_name: str, **labels: str) -> float:
    for family in families.values():
        for sample in family.samples:
            if sample.name == sample_name and all(
                sample.labels.get(k) == v for k, v in labels.items()
            ):
                return float(sample.value)
    return 0.0


async def test_every_series_appears_after_one_request_of_each_kind(metered: AuthApi) -> None:
    member = await join(metered, email="ann@example.com", phone="0711000111", role="Owner")
    assert (await metered.client.get("/health/ready")).status_code == 200
    assert (await metered.client.get("/setup/people", headers=member.headers)).status_code == 200
    unknown = await metered.sign_in(phone=UNKNOWN_PHONE, pin="5826", device="browser")
    wrong = await metered.sign_in(phone="0711000111", pin="0000", device="device-0111")
    assert unknown.status_code == 401
    assert wrong.status_code == 401
    assert (await metered.client.get("/no/such/route/0711000111")).status_code == 404

    response = await metered.client.get("/metrics", headers={"host": "10.0.0.7:5000"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    families = _families(response.text)

    assert set(families) >= {name.removesuffix("_total") for name in SERIES}
    assert _value(families, "http_requests_total", route="/setup/people", status="200") == 1
    assert _value(families, "http_requests_total", route="unmatched", status="404") == 1
    assert _value(families, "http_request_duration_seconds_count", route="/health/ready") == 1
    assert _value(families, "db_routine_duration_seconds_count", routine="people_list") == 1
    assert _value(families, "db_routine_duration_seconds_count", routine="meta_contract_version")
    assert _value(families, "auth_refusals_total", reason="unknown") == 1
    assert _value(families, "auth_refusals_total", reason="wrong_pin") == 1
    states = {sample.labels["state"] for sample in families["db_pool_connections"].samples}
    assert states == {"idle", "busy", "waiting"}
    assert _value(families, "mail_queue_depth") >= 0


async def test_labels_never_carry_an_id_a_phone_an_address_or_a_raw_path(
    metered: AuthApi,
) -> None:
    member = await join(metered, email="ann@example.com", phone="0711000111", role="Owner")
    await metered.client.get(f"/setup/people/{member.user_id}", headers=member.headers)
    await metered.sign_in(phone=UNKNOWN_PHONE, pin="5826", device="browser")
    await metered.client.get("/no/such/route/ann@example.com")
    text = (await metered.client.get("/metrics")).text
    for family in text_string_to_metric_families(text):
        for sample in family.samples:
            for name, value in sample.labels.items():
                assert name in LABELS, (sample.name, name)
                assert LABELS[name].match(value), (sample.name, name, value)
    assert str(member.user_id) not in text
    for secret in ("0711000111", UNKNOWN_PHONE, "ann@example.com", "127.0.0.1", "browser"):
        assert secret not in text


async def test_rate_limited_requests_are_counted(
    app_url: str,
    owner_url: str,
    pool: AsyncConnectionPool[Any],
    manual_clock: ManualClock,
    mail_spy: MailSpy,
) -> None:
    settings = Settings.for_tests(
        database_url=app_url,
        migration_database_url=owner_url,
        metrics_enabled=True,
        rate_limit_auth_per_minute=1,
    )
    async with AsyncExitStack() as stack:
        client = await _app(stack, settings, pool, manual_clock, mail_spy)
        body = {"phoneNumber": UNKNOWN_PHONE, "pin": "5826", "deviceId": "browser"}
        first = await client.post("/auth/sign-in", json=body)
        second = await client.post("/auth/sign-in", json=body)
        families = _families((await client.get("/metrics")).text)
    assert (first.status_code, second.status_code) == (401, 429)
    assert _value(families, "rate_limit_rejections_total") == 1
    assert _value(families, "http_requests_total", route="/auth/sign-in", status="429") == 1


async def test_the_route_is_absent_when_metrics_are_off(client: httpx.AsyncClient) -> None:
    response = await client.get("/metrics")
    assert response.status_code == 404
