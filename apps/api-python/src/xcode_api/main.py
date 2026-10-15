"""HTTP composition root: ``create_app`` wires settings, container, middleware and routers.

Startup follows ``docs/08-operability.md`` section 6: settings and logging (``serve``),
the pool within 30 s and the role check, the development-only migration and demo seed,
the routine-contract version (a mismatch refuses to start), the unassigned-user warning,
then readiness. Shutdown drains the mail queue for ``XCODE_SHUTDOWN_GRACE_SECONDS`` and
closes the pool (section 7).
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator, Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager

import anyio.to_thread
import structlog
from fastapi import FastAPI
from psycopg_pool import PoolTimeout
from starlette.middleware.cors import CORSMiddleware

from .application.ops.seed_demo import SeedDemo, SeedDemoCommand
from .container import Container, build_container
from .db.contract import EXPECTED_CONTRACT_VERSION
from .db.migrate import Runner, advisory_lock, find_db_dir, open_owner_connection
from .db.pool import (
    Pool,
    StatementCounter,
    check_connection,
    check_role,
    open_operator_pool,
    open_pool,
)
from .db.routines.ops import OpsRoutines
from .http import openapi
from .http.dependencies import _RateLimited, rate_limited_handler
from .http.errors import register_exception_handlers
from .http.middleware import (
    BodyCapMiddleware,
    HostCheckMiddleware,
    MetricsMiddleware,
    RequestContextMiddleware,
    SetupCompressionMiddleware,
)
from .http.routers import (
    access,
    auth,
    auth_steps,
    expenses,
    health,
    history,
    metrics,
    organization,
    pettycash,
    reports,
    revenue,
    setup_companies,
    setup_expenses,
    setup_investment,
    setup_recurring,
    setup_vehicles,
)
from .infra.clock import SystemClock
from .infra.logging import configure_logging
from .infra.metrics import Metrics
from .security.pins import Pbkdf2PinHasher
from .settings import Settings, env_file_present_but_ignored, load_settings

logger = structlog.get_logger("xcode_api")

STARTUP_POOL_TIMEOUT_SECONDS = 30.0
WORKER_THREADS = 4
UNASSIGNED_USERS_WARNING = "{count} active users have no organization membership and cannot sign in"


class ContractVersionMismatch(RuntimeError):  # noqa: N818 - a named startup failure, not an Error type
    """The database's routine-contract version is not the one this package expects."""


class DatabaseUnreachable(RuntimeError):  # noqa: N818 - a named startup failure, not an Error type
    """The pool could not open a connection within the startup budget."""


def create_app(
    settings: Settings,
    container: Container,
    *,
    pool_states: Callable[[], Mapping[str, int]] | None = None,
) -> FastAPI:
    configure_logging(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        await _verify_contract_version(container)
        await _warn_unassigned_users(container)
        container.mail_queue.start()
        app.state.started = True
        try:
            yield
        finally:
            app.state.started = False
            await container.mail_queue.drain(settings.shutdown_grace_seconds)

    app = FastAPI(
        title="xcode-api",
        lifespan=lifespan,
        openapi_url="/openapi/v1.json" if settings.openapi_is_enabled else None,
        docs_url=None,
        redoc_url=None,
    )
    app.state.container = container
    app.state.settings = settings
    app.state.started = False

    # Middleware order (added inner-first, so outermost is last).
    app.add_middleware(BodyCapMiddleware)
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.cors_origins),
            allow_credentials=False,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    if settings.allowed_hosts and settings.allowed_hosts != ["*"]:
        app.add_middleware(HostCheckMiddleware, allowed_hosts=list(settings.allowed_hosts))
    app.add_middleware(SetupCompressionMiddleware)
    if settings.metrics_enabled:
        app.state.metrics = Metrics(
            pool_states=pool_states or dict,
            mail_queue_depth=lambda: container.mail_queue.depth,
        )
        app.add_middleware(MetricsMiddleware, metrics=app.state.metrics)
    app.add_middleware(
        RequestContextMiddleware,
        trusted_proxies=list(settings.trusted_proxies),
        statement_counter=StatementCounter(),
    )

    register_exception_handlers(app)
    app.add_exception_handler(_RateLimited, rate_limited_handler)

    routers = [
        health.router,
        *([metrics.router] if settings.metrics_enabled else []),
        auth.router,
        auth_steps.router,
        access.router,
        history.router,
        organization.router,
        setup_companies.router,
        setup_vehicles.router,
        setup_recurring.router,
        setup_expenses.router,
        setup_investment.router,
        revenue.router,
        pettycash.router,
        expenses.router,
        reports.router,
    ]
    for router in routers:
        app.include_router(router)
    openapi.install(app, routers)

    return app


async def _verify_contract_version(container: Container) -> None:
    version = await container.ops.contract_version()
    if version != EXPECTED_CONTRACT_VERSION:
        logger.error(
            "startup.contract_version_mismatch",
            database_version=version,
            expected_version=EXPECTED_CONTRACT_VERSION,
        )
        raise ContractVersionMismatch(
            f"database routine-contract version {version} != expected {EXPECTED_CONTRACT_VERSION}"
        )
    logger.info("startup.contract_version_ok", version=version)


async def _warn_unassigned_users(container: Container) -> None:
    count = await container.ops.unassigned_user_count()
    if count > 0:
        logger.warning(
            "startup.unassigned_users", message=UNASSIGNED_USERS_WARNING.format(count=count)
        )


def build_default_app() -> FastAPI:
    """Build the app from the environment (used by ``xcode-api serve`` and uvicorn factories).

    The pool is opened inside the lifespan, so nothing connects before uvicorn runs it; a
    failed step raises out of the lifespan and ``serve`` exits 1.
    """
    settings = load_settings()
    configure_logging(settings)
    if env_file_present_but_ignored():
        logger.warning("settings.env_file_ignored", env=settings.env.value)
    if settings.auth_signing_key_generated:
        logger.warning("settings.signing_key_generated", env=settings.env.value)

    pool = open_pool(settings)
    container = build_container(settings, pool)
    base_app = create_app(settings, container, pool_states=lambda: pool_states(pool))
    base_lifespan = base_app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        cap_worker_threads()
        try:
            await open_and_check(pool, STARTUP_POOL_TIMEOUT_SECONDS)
            if settings.is_development:
                await prepare_development(settings)
            logger.info("startup.rate_limit_backend", backend=settings.rate_limit_backend)
            async with base_lifespan(app):
                yield
        finally:
            await pool.close()

    base_app.router.lifespan_context = lifespan
    return base_app


def cap_worker_threads() -> None:
    """Bound the threads the process can start beside the PIN pool's own two: the worker
    threads FastAPI runs synchronous dependencies on (anyio allows 40 by default) and the
    loop's default executor (psycopg resolves host names there; ``cpu + 4`` by default).
    The shared host counts every thread against one cap (``docs/13`` question 43)."""
    anyio.to_thread.current_default_thread_limiter().total_tokens = WORKER_THREADS
    asyncio.get_running_loop().set_default_executor(
        ThreadPoolExecutor(max_workers=WORKER_THREADS, thread_name_prefix="xcode-io")
    )


async def open_and_check(pool: Pool, timeout_seconds: float) -> None:
    try:
        await pool.open(wait=True, timeout=timeout_seconds)
    except PoolTimeout as exc:
        logger.error("startup.database_unreachable", timeout_seconds=timeout_seconds)
        raise DatabaseUnreachable(f"no database connection within {timeout_seconds:g} s") from exc
    await check_connection(pool, timeout_seconds)
    await check_role(pool)


async def prepare_development(settings: Settings) -> None:
    if settings.auto_migrate:
        await asyncio.to_thread(_auto_migrate, settings)
    if settings.demo_seed:
        await _seed_demo(settings)


def pool_states(pool: Pool) -> dict[str, int]:
    stats = pool.get_stats()
    size = stats.get("pool_size", 0)
    idle = stats.get("pool_available", 0)
    return {"idle": idle, "busy": max(size - idle, 0), "waiting": stats.get("requests_waiting", 0)}


def _auto_migrate(settings: Settings) -> None:
    operator = settings.operator or "startup"
    conn = open_owner_connection(settings.migration_database_url)
    try:
        with advisory_lock(conn):
            Runner(conn, operator=operator, db_dir=find_db_dir()).migrate()
    finally:
        conn.close()


async def _seed_demo(settings: Settings) -> None:
    pool = open_operator_pool(settings.database_operator_url)
    await pool.open(wait=True, timeout=STARTUP_POOL_TIMEOUT_SECONDS)
    try:
        use_case = SeedDemo(
            OpsRoutines(pool), SystemClock(), Pbkdf2PinHasher(settings.auth_pin_iterations)
        )
        seeded = await use_case.execute(
            SeedDemoCommand(settings.operator or "startup", uuid.uuid4().hex, settings.env.value)
        )
    finally:
        await pool.close()
    logger.info(
        "startup.demo_seed",
        organization_id=str(seeded.organization_id),
        created=seeded.created,
    )
