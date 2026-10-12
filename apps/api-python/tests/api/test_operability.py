"""Operability against the real database: health, readiness and startup refusals."""

from __future__ import annotations

import asyncio
import threading

import anyio.to_thread
import httpx
import psycopg
import pytest
import structlog

import xcode_api.main as main_module
from xcode_api.container import build_container
from xcode_api.db.pool import open_pool
from xcode_api.main import ContractVersionMismatch, create_app
from xcode_api.settings import Settings

from ..support.client import ApiFactory
from ..support.setup_client import join


async def test_health_ready_is_200_against_the_database(
    db_client: httpx.AsyncClient,
) -> None:
    response = await db_client.get("/health/ready")
    assert response.status_code == 200
    assert response.text == "Healthy"


async def test_health_live_is_always_200(db_client: httpx.AsyncClient) -> None:
    response = await db_client.get("/health/live")
    assert response.status_code == 200


async def test_health_ready_is_503_without_leaking_detail_when_db_unreachable(
    db_settings: Settings,
) -> None:
    dead = Settings.for_tests(
        database_url="postgresql://xcode_app:xcode_app@127.0.0.1:1/xcode",
        migration_database_url=db_settings.migration_database_url,
    )
    pool = open_pool(dead)
    container = build_container(dead, pool)
    app = create_app(dead, container)
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    # Open the pool without the full lifespan contract check (which would also fail).
    await pool.open(wait=False)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.get("/health/ready")
        assert response.status_code == 503
        assert response.text == "Unhealthy"
        assert "xcode" not in response.text.lower() or response.text == "Unhealthy"
    finally:
        await pool.close()


async def test_startup_refuses_a_contract_version_mismatch(
    db_settings: Settings,
    pool: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(main_module, "EXPECTED_CONTRACT_VERSION", 9999)
    container = build_container(db_settings, pool)  # type: ignore[arg-type]
    app = create_app(db_settings, container)
    with pytest.raises(ContractVersionMismatch):
        async with app.router.lifespan_context(app):
            pass


async def test_request_log_line_counts_routine_calls(db_client: httpx.AsyncClient) -> None:
    events: list[dict[str, object]] = []

    def capture(_logger: object, _method: str, event: dict[str, object]) -> dict[str, object]:
        events.append(dict(event))
        return event

    old_config = structlog.get_config()
    structlog.configure(
        processors=[structlog.stdlib.add_log_level, capture, structlog.processors.JSONRenderer()],
        wrapper_class=structlog.make_filtering_bound_logger(20),  # INFO
    )
    try:
        response = await db_client.get("/health/ready")
    finally:
        structlog.configure(**old_config)
    assert response.status_code == 200
    completed = [e for e in events if e.get("event") == "request.completed"]
    assert completed, "no request.completed log line captured"
    # SELECT 1 is a raw probe; api.meta_contract_version is the one routine call.
    assert completed[-1]["statements"] == 1
    assert completed[-1]["route"] == "/health/ready"


# --- the startup sequence (docs/08-operability.md section 6) ------------------------------


class _Events:
    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []
        self._old = structlog.get_config()

    def __enter__(self) -> _Events:
        def capture(_logger: object, _method: str, event: dict[str, object]) -> dict[str, object]:
            self.events.append(dict(event))
            return event

        structlog.configure(
            processors=[
                structlog.stdlib.add_log_level,
                capture,
                structlog.processors.JSONRenderer(),
            ],
            wrapper_class=structlog.make_filtering_bound_logger(20),
        )
        return self

    def __exit__(self, *exc: object) -> None:
        structlog.configure(**self._old)

    def named(self, name: str) -> list[dict[str, object]]:
        return [e for e in self.events if e.get("event") == name]


async def test_startup_warns_about_active_users_without_a_membership(
    db_settings: Settings, pool: object, owner_url: str
) -> None:
    with psycopg.connect(owner_url, autocommit=True) as owner:
        owner.execute(
            "INSERT INTO identity.users (email, phone_number) "
            "VALUES ('lone@example.com', '+254733000001')"
        )
    app = create_app(db_settings, build_container(db_settings, pool))  # type: ignore[arg-type]
    with _Events() as log:
        async with app.router.lifespan_context(app):
            pass
    warnings = log.named("startup.unassigned_users")
    assert len(warnings) == 1
    assert warnings[0]["level"] == "warning"
    assert warnings[0]["message"] == (
        "1 active users have no organization membership and cannot sign in"
    )


async def test_startup_without_unassigned_users_logs_no_warning(
    db_settings: Settings, pool: object
) -> None:
    app = create_app(db_settings, build_container(db_settings, pool))  # type: ignore[arg-type]
    with _Events() as log:
        async with app.router.lifespan_context(app):
            pass
    assert log.named("startup.unassigned_users") == []
    assert log.named("startup.contract_version_ok")


async def test_the_default_startup_reads_and_never_migrates(
    app_url: str, owner_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name, value in {
        "XCODE_ENV": "testing",
        "XCODE_DATABASE_URL": app_url,
        "XCODE_MAIL_BACKEND": "log",
        "XCODE_LOG_FORMAT": "console",
        "XCODE_DATABASE_OPERATOR_URL": "postgresql://nobody@127.0.0.1:1/none",
        "XCODE_MIGRATION_DATABASE_URL": "postgresql://nobody@127.0.0.1:1/none",
    }.items():
        monkeypatch.setenv(name, value)
    snapshot = (
        "SELECT (SELECT count(*) FROM pg_class AS c JOIN pg_namespace AS n "
        "ON n.oid = c.relnamespace WHERE n.nspname NOT LIKE 'pg\\_%%' "
        "AND n.nspname <> 'information_schema'), "
        "(SELECT count(*) FROM ops.schema_migrations), "
        "(SELECT count(*) FROM ops.routine_versions), "
        "(SELECT count(*) FROM ops.operator_actions)"
    )
    with psycopg.connect(owner_url, autocommit=True) as owner:
        before = owner.execute(snapshot).fetchone()
        app = main_module.build_default_app()
        with _Events() as log:
            async with app.router.lifespan_context(app):
                transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
                async with httpx.AsyncClient(
                    transport=transport, base_url="http://testserver"
                ) as client:
                    ready = await client.get("/health/ready")
        after = owner.execute(snapshot).fetchone()
    assert ready.status_code == 200
    assert after == before
    assert log.named("startup.contract_version_ok")
    assert log.named("db.role_unexpected") == []


async def test_readiness_is_unhealthy_until_the_startup_checks_pass(
    db_settings: Settings, pool: object
) -> None:
    app = create_app(db_settings, build_container(db_settings, pool))  # type: ignore[arg-type]
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        before = await client.get("/health/ready")
        async with app.router.lifespan_context(app):
            during = await client.get("/health/ready")
        after = await client.get("/health/ready")
    assert (before.status_code, during.status_code, after.status_code) == (503, 200, 503)
    assert before.text == "Unhealthy"


async def test_readiness_charges_the_shared_limiter_when_it_is_postgres(
    app_url: str, owner_url: str
) -> None:
    settings = Settings.for_tests(database_url=app_url, rate_limit_backend="postgres")
    pool = open_pool(settings)
    await pool.open(wait=True, timeout=30)
    try:
        app = create_app(settings, build_container(settings, pool))
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=transport, base_url="http://testserver"
            ) as client:
                ready = await client.get("/health/ready")
    finally:
        await pool.close()
    assert ready.status_code == 200
    with psycopg.connect(owner_url, autocommit=True) as owner:
        windows = owner.execute(
            "SELECT count(*) FROM ops.rate_limit_windows WHERE key = 'health:ready'"
        ).fetchone()
    assert windows == (1,)


async def test_the_pool_budget_ends_startup_when_the_database_is_unreachable() -> None:
    dead = Settings.for_tests(database_url="postgresql://xcode_app:x@127.0.0.1:1/xcode")
    pool = open_pool(dead)
    try:
        with pytest.raises(main_module.DatabaseUnreachable):
            await main_module.open_and_check(pool, 0.5)
    finally:
        await pool.close()


async def test_concurrent_requests_start_no_more_worker_threads_than_the_cap(
    make_api: ApiFactory,
) -> None:
    api = await make_api()
    member = await join(api, email="ann@example.com", phone="0711000111", role="Owner")
    main_module.cap_worker_threads()
    before = threading.active_count()
    peak = before
    running = True

    async def sample() -> None:
        nonlocal peak
        while running:
            peak = max(peak, threading.active_count())
            await asyncio.sleep(0)

    sampler = asyncio.create_task(sample())
    responses = await asyncio.gather(
        *(api.client.get("/setup/history", headers=member.headers) for _ in range(120))
    )
    running = False
    await sampler
    assert {r.status_code for r in responses} == {200}
    assert peak - before <= main_module.WORKER_THREADS
    assert anyio.to_thread.current_default_thread_limiter().total_tokens == (
        main_module.WORKER_THREADS
    )
