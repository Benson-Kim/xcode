"""Shared fixtures.

The fake-based fixtures (``client``, ``ops``, ``settings`` …) drive the pure HTTP-plumbing
tests with no database. The database-backed fixtures (``harness``, ``database``, ``pool``,
``db_container``, ``db_client`` …) drive ``tests/db`` and the operability tests against a
real PostgreSQL template clone; they skip when no database is reachable
(``docs/09-testing.md`` section 2).
"""

from __future__ import annotations

import asyncio
import secrets
import sys
from collections.abc import AsyncIterator, Callable, Iterator

import httpx
import psycopg
import pytest
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from xcode_api.container import Container, build_container
from xcode_api.db.pool import open_pool, reset_statement_counter
from xcode_api.db.routines.ops import OpsRoutines
from xcode_api.main import create_app
from xcode_api.settings import Settings

from .support.clock import ManualClock
from .support.database import Harness, start_harness
from .support.fakes import (
    FakeExpensesRepository,
    FakeIdentityRepository,
    FakeOpsRepository,
    FakePettyCashRepository,
    FakeReportsRepository,
    FakeRevenueRepository,
    FakeSetupRepository,
    FakeTenancyRepository,
)
from .support.mail import MailSpy


def _selector_loop() -> asyncio.AbstractEventLoop:
    # psycopg's async pool cannot run on Windows' default ProactorEventLoop; the selector
    # loop is required (on Linux/CI the default loop already is one).
    if sys.platform == "win32":
        return asyncio.SelectorEventLoop()
    return asyncio.new_event_loop()


def pytest_asyncio_loop_factories(
    config: pytest.Config, item: pytest.Item
) -> dict[str, Callable[[], asyncio.AbstractEventLoop]]:
    del config, item
    return {"selector": _selector_loop}


@pytest.fixture
def manual_clock() -> ManualClock:
    return ManualClock()


@pytest.fixture
def ops() -> FakeOpsRepository:
    return FakeOpsRepository()


@pytest.fixture
def make_settings() -> Callable[..., Settings]:
    def factory(**overrides: object) -> Settings:
        return Settings.for_tests(**overrides)

    return factory


@pytest.fixture
def settings(make_settings: Callable[..., Settings]) -> Settings:
    return make_settings()


@pytest.fixture
def make_container(
    manual_clock: ManualClock,
) -> Callable[[Settings, FakeOpsRepository], Container]:
    def factory(settings: Settings, ops: FakeOpsRepository) -> Container:
        tenancy = FakeTenancyRepository()
        setup = FakeSetupRepository(tenancy)
        pettycash = FakePettyCashRepository(setup)
        revenue = FakeRevenueRepository(setup)
        return build_container(
            settings,
            ops=ops,
            identity=FakeIdentityRepository(),
            tenancy=tenancy,
            setup=setup,
            revenue=revenue,
            pettycash=pettycash,
            expenses=FakeExpensesRepository(setup, pettycash),
            reports=FakeReportsRepository(setup, revenue),
            clock=manual_clock,
        )

    return factory


@pytest.fixture
async def client(
    settings: Settings,
    ops: FakeOpsRepository,
    make_container: Callable[[Settings, FakeOpsRepository], Container],
) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(settings, make_container(settings, ops))
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
            yield c


# --- database-backed fixtures ---------------------------------------------------------


def _unique_db_name(prefix: str, worker_id: str) -> str:
    # A random suffix so a database left behind by a killed run never collides with a new one.
    return f"{prefix}_{worker_id}_{secrets.token_hex(6)}"


@pytest.fixture(scope="session")
def worker_id(request: pytest.FixtureRequest) -> str:
    """The pytest-xdist worker name, or ``main`` when xdist is not loaded (serial runs)."""
    config = request.config
    return str(getattr(config, "workerinput", {}).get("workerid", "main"))


@pytest.fixture(scope="session")
def harness() -> Iterator[Harness]:
    yield from start_harness()


@pytest.fixture
def database(harness: Harness, worker_id: str) -> Iterator[tuple[str, str]]:
    name = _unique_db_name("test", worker_id)
    app_url, owner_url = harness.create_test_database(name)
    try:
        yield app_url, owner_url
    finally:
        harness.drop_test_database(name)


@pytest.fixture
def fresh_owner_url(harness: Harness, worker_id: str) -> Iterator[str]:
    """A schema-only database (no migrations applied) for migration-runner tests."""
    name = _unique_db_name("fresh", worker_id)
    owner_url = harness.create_schema_only_database(name)
    try:
        yield owner_url
    finally:
        harness.drop_test_database(name)


@pytest.fixture
def app_url(database: tuple[str, str]) -> str:
    return database[0]


@pytest.fixture
def owner_url(database: tuple[str, str]) -> str:
    return database[1]


@pytest.fixture
def db_settings(app_url: str, owner_url: str) -> Settings:
    return Settings.for_tests(database_url=app_url, migration_database_url=owner_url)


@pytest.fixture
async def pool(db_settings: Settings) -> AsyncIterator[AsyncConnectionPool[object]]:
    p = open_pool(db_settings)
    await p.open(wait=True, timeout=15)
    try:
        yield p
    finally:
        await p.close()


@pytest.fixture
def mail_spy() -> MailSpy:
    return MailSpy()


@pytest.fixture
def db_container(
    db_settings: Settings,
    pool: AsyncConnectionPool[object],
    manual_clock: ManualClock,
    mail_spy: MailSpy,
) -> Container:
    return build_container(
        db_settings,
        pool,
        ops=OpsRoutines(pool),
        clock=manual_clock,
        mailer=mail_spy,
    )


@pytest.fixture
async def db_client(
    db_settings: Settings, db_container: Container
) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(db_settings, db_container)
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
            yield c


@pytest.fixture
def statement_counter() -> Iterator[Callable[[], int]]:
    from xcode_api.db.pool import current_statement_count

    reset_statement_counter()
    yield current_statement_count


@pytest.fixture
def owner_conn(owner_url: str) -> Iterator[psycopg.Connection[dict[str, object]]]:
    conn = psycopg.connect(owner_url, autocommit=True, row_factory=dict_row)
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture
def app_conn(app_url: str) -> Iterator[psycopg.Connection[dict[str, object]]]:
    conn = psycopg.connect(app_url, autocommit=True, row_factory=dict_row)
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture
def operator_conn(
    database: tuple[str, str],
) -> Iterator[psycopg.Connection[dict[str, object]]]:
    from urllib.parse import urlsplit

    parts = urlsplit(database[0])
    host = parts.hostname or "localhost"
    port = f":{parts.port}" if parts.port else ""
    query = f"?{parts.query}" if parts.query else ""
    dbname = parts.path.lstrip("/")
    url = f"{parts.scheme}://xcode_operator:xcode_operator@{host}{port}/{dbname}{query}"
    conn = psycopg.connect(url, autocommit=True, row_factory=dict_row)
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture
def competing_writer(app_url: str) -> Iterator[psycopg.Connection[dict[str, object]]]:
    conn = psycopg.connect(app_url, autocommit=True, row_factory=dict_row)
    try:
        yield conn
    finally:
        conn.close()
