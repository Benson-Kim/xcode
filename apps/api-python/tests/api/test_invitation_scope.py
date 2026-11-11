"""Send-again stays inside the caller's organization and the Owner lock (row S57): another
organization's person is not found and gets nothing, and only an Owner sends to an Owner."""

from __future__ import annotations

import pytest

from ..support.client import ApiFactory, AuthApi
from ..support.fakes import role_rights
from ..support.rows import seed_organization
from ..support.setup_client import FORBIDDEN, NOT_FOUND, Member, join, ok, problem
from .test_invitations import invite

pytestmark = pytest.mark.asyncio(loop_scope="session")

OWNER_EDIT = "Only an Owner can change, remove or sign out an Owner."


@pytest.fixture
async def api(make_api: ApiFactory) -> AuthApi:
    return await make_api()


@pytest.fixture
async def owner(api: AuthApi) -> Member:
    return await join(api, email="ann@example.com", phone="0711000111", role="Owner")


def invitations_of(api: AuthApi, user_id: object) -> int:
    row = api.owner.execute(
        "SELECT count(*) AS n FROM identity.invitations WHERE user_id = %s", (user_id,)
    ).fetchone()
    assert row is not None
    return int(row["n"])


def invitation_rows(api: AuthApi, user_id: object) -> list[dict[str, object]]:
    return api.owner.execute(
        "SELECT id, token_hash, code_hash, delivery_state, delivery_attempts, revoked_at "
        "FROM identity.invitations WHERE user_id = %s ORDER BY id",
        (user_id,),
    ).fetchall()


async def test_another_organizations_person_is_not_found_and_gets_nothing(
    api: AuthApi, owner: Member
) -> None:
    other = seed_organization(api.owner)
    seeded = invitation_rows(api, other.user2)
    assert [row["id"] for row in seeded] == [other.invitation]
    before = len(api.mail.sent)
    problem(
        await api.client.post(f"/setup/people/{other.user2}/invitation", headers=owner.headers),
        404,
        NOT_FOUND,
    )
    assert invitation_rows(api, other.user2) == seeded
    assert len(api.mail.sent) == before


async def test_only_an_owner_sends_an_owner_an_invitation(api: AuthApi, owner: Member) -> None:
    second = await invite(api, owner, role="Owner", permissions=list(role_rights("Owner")))
    admin = await join(api, email="admin@example.com", phone="0744000111", role="Office admin")
    path = f"/setup/people/{second}/invitation"
    before = len(api.mail.sent)
    problem(await api.client.post(path, headers=admin.headers), 403, FORBIDDEN, OWNER_EDIT)
    assert invitations_of(api, second) == 1
    assert len(api.mail.sent) == before
    assert ok(await api.client.post(path, headers=owner.headers)) == {"id": second}
    await api.delivered(before + 1)
