"""``ResolveSession`` orchestration: the token is verified first (a bad token never reaches
the database), then the session is resolved on every request with no cache."""

from __future__ import annotations

import pytest

from xcode_api.application.auth.resolve_session import ResolveSessionCommand
from xcode_api.application.auth.sign_in import SignInCommand
from xcode_api.domain.errors import SessionInvalid

from .conftest import PIN, TRUSTED, AuthKit


async def _access_token(kit: AuthKit) -> str:
    envelope = await kit.sign_in().execute(SignInCommand("req-0", "0712345678", PIN, TRUSTED))
    assert envelope.access_token is not None
    kit.calls.clear()
    return envelope.access_token


async def test_a_valid_token_resolves_to_the_principal(kit: AuthKit) -> None:
    user_id = await kit.account()
    token = await _access_token(kit)
    session = await kit.resolve_session().execute(ResolveSessionCommand(token))
    assert kit.calls == ["resolve_session"]
    principal = session.principal
    assert (principal.user_id, principal.device_id, principal.role) == (user_id, TRUSTED, "Owner")
    assert principal.organization_id == kit.identity.user(user_id).organization_id
    assert principal.permissions == session.claims.permissions


async def test_a_bad_token_never_reaches_the_repository(kit: AuthKit) -> None:
    await kit.account()
    token = await _access_token(kit)
    with pytest.raises(SessionInvalid):
        await kit.resolve_session().execute(ResolveSessionCommand(token + "x"))
    assert kit.calls == []


async def test_nothing_is_cached_between_requests(kit: AuthKit) -> None:
    user_id = await kit.account()
    token = await _access_token(kit)
    await kit.resolve_session().execute(ResolveSessionCommand(token))
    kit.identity.set_user(user_id, security_version=kit.identity.user(user_id).security_version + 1)
    with pytest.raises(SessionInvalid):
        await kit.resolve_session().execute(ResolveSessionCommand(token))
    assert kit.calls == ["resolve_session", "resolve_session"]
