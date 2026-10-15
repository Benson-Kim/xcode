"""Fixtures of the HTTP contract tests on the real database."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import AsyncExitStack
from typing import Any

import httpx
import pytest
from psycopg_pool import AsyncConnectionPool

from xcode_api.container import build_container
from xcode_api.main import create_app
from xcode_api.settings import Settings

from ..support.client import ApiFactory, AuthApi
from ..support.clock import ManualClock
from ..support.mail import MailSpy
from ..support.scenario import Conn


@pytest.fixture
async def make_api(
    app_url: str,
    owner_url: str,
    pool: AsyncConnectionPool[Any],
    manual_clock: ManualClock,
    mail_spy: MailSpy,
    operator_conn: Conn,
    owner_conn: Conn,
) -> AsyncIterator[ApiFactory]:
    async with AsyncExitStack() as stack:

        async def factory(
            *, peer: tuple[str, int] = ("127.0.0.1", 50000), **overrides: Any
        ) -> AuthApi:
            pin_hasher = overrides.pop("pin_hasher", None)
            settings = Settings.for_tests(
                database_url=app_url, migration_database_url=owner_url, **overrides
            )
            container = build_container(
                settings, pool, clock=manual_clock, mailer=mail_spy, pin_hasher=pin_hasher
            )
            app = create_app(settings, container)
            await stack.enter_async_context(app.router.lifespan_context(app))
            transport = httpx.ASGITransport(app=app, raise_app_exceptions=False, client=peer)
            client = await stack.enter_async_context(
                httpx.AsyncClient(transport=transport, base_url="http://testserver")
            )
            return AuthApi(client, mail_spy, manual_clock, container, operator_conn, owner_conn)

        yield factory
