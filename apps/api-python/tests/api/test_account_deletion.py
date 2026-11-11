"""``POST /setup/me/deletion-request`` against the real database (``docs/06-http-contract.md``
section 2.2): a member records their own account-deletion request. The reply is always 202 with
no body; the first request queues one notice to each administrator who can block members after
the reply; a repeat within 24 hours queues none, so the reply never reveals whether a request
was already made; an anonymous caller gets the uniform 401."""

from __future__ import annotations

import asyncio

import pytest

from xcode_api.application.ports import MailMessage
from xcode_api.infra.mail import DELETION_REQUEST_SUBJECT

from ..support.client import ApiFactory, AuthApi
from ..support.setup_client import Member, empty, join

pytestmark = pytest.mark.asyncio(loop_scope="session")

PATH = "/setup/me/deletion-request"


@pytest.fixture
async def api(make_api: ApiFactory) -> AuthApi:
    return await make_api()


@pytest.fixture
async def owner(api: AuthApi) -> Member:
    return await join(api, email="ann@example.com", phone="0711000111", role="Owner")


@pytest.fixture
async def office(api: AuthApi, owner: Member) -> Member:
    return await join(api, email="omar@example.com", phone="0722000111", role="Office admin")


@pytest.fixture
async def clerk(api: AuthApi, owner: Member) -> Member:
    return await join(api, email="cleo@example.com", phone="0733000111", role="Revenue clerk")


def _notices(api: AuthApi) -> list[MailMessage]:
    return [m for m in api.mail.sent if m.tags.get("purpose") == "deletion_request"]


async def _wait_notices(api: AuthApi, count: int) -> list[MailMessage]:
    for _ in range(500):
        if len(_notices(api)) >= count:
            await asyncio.sleep(0.05)
            return _notices(api)
        await asyncio.sleep(0.01)
    raise AssertionError(f"expected {count} deletion notices, saw {len(_notices(api))}")


async def test_the_first_request_answers_202_and_notifies_each_admin_who_can_block(
    api: AuthApi, owner: Member, office: Member, clerk: Member
) -> None:
    empty(await api.client.post(PATH, headers=clerk.headers), 202)
    notices = await _wait_notices(api, 2)
    assert len(notices) == 2
    assert {m.to for m in notices} == {"ann@example.com", "omar@example.com"}
    assert all(m.subject == DELETION_REQUEST_SUBJECT for m in notices)
    assert all(m.tags.get("request_id") for m in notices)


async def test_a_repeat_within_the_day_answers_202_and_queues_no_notice(
    api: AuthApi, owner: Member, clerk: Member
) -> None:
    empty(await api.client.post(PATH, headers=clerk.headers), 202)
    assert len(await _wait_notices(api, 1)) == 1
    empty(await api.client.post(PATH, headers=clerk.headers), 202)
    await asyncio.sleep(0.1)
    assert len(_notices(api)) == 1


async def test_the_request_id_is_echoed_on_the_empty_reply(
    api: AuthApi, owner: Member, clerk: Member
) -> None:
    headers = {**clerk.headers, "X-Request-ID": "trace-deletion-1"}
    response = await api.client.post(PATH, headers=headers)
    empty(response, 202)
    assert response.headers["x-request-id"] == "trace-deletion-1"
    assert response.headers["cache-control"] == "no-store"


async def test_an_anonymous_caller_gets_the_uniform_401(api: AuthApi) -> None:
    response = await api.client.post(PATH)
    empty(response, 401)
    assert response.headers["www-authenticate"] == "Bearer"
    garbled = await api.client.post(PATH, headers={"Authorization": "Bearer not-a-token"})
    empty(garbled, 401)
    assert _notices(api) == []
