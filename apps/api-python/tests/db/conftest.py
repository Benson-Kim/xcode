"""Fixtures of the routine tests: an executor connection (helpers run as
``xcode_api_executor`` under row-level security, exactly as inside a routine) and the
default account."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from ..support.database import executor_connection
from ..support.scenario import Account, Auth, Conn, make_account


@pytest.fixture
def executor(owner_url: str) -> Iterator[Conn]:
    with executor_connection(owner_url) as conn:
        yield conn


@pytest.fixture
def auth(app_conn: Conn) -> Auth:
    return Auth(app_conn)


@pytest.fixture
def account(operator_conn: Conn, owner_conn: Conn) -> Account:
    """Jane Doe, Owner of the single organization, with a PIN and one trusted device."""
    return make_account(operator_conn, owner_conn)
