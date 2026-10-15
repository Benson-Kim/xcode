"""The five operator use cases: each passes the operator, request id and the clock's instant
to its repository method and returns the record unchanged; the fake satisfies the whole
``OpsRepository`` Protocol."""

from __future__ import annotations

import pytest

from xcode_api.application.ops.clear_pause import ClearPause, ClearPauseCommand
from xcode_api.application.ops.provision_user import ProvisionUser, ProvisionUserCommand
from xcode_api.application.ops.read_account_state import ReadAccountState, ReadAccountStateCommand
from xcode_api.application.ops.remove_user import RemoveUser, RemoveUserCommand
from xcode_api.application.ops.revoke_sessions import RevokeSessions, RevokeSessionsCommand
from xcode_api.application.repositories import OpsRepository
from xcode_api.domain.errors import NotFound
from xcode_api.domain.identity import UserStatus

from ..support.clock import ManualClock
from ..support.fakes import FakeOpsRepository

EMAIL = "owner@example.com"


def test_the_fake_satisfies_the_ops_repository_protocol() -> None:
    assert isinstance(FakeOpsRepository(), OpsRepository)


async def test_provision_then_state_remove_and_revoke_pass_the_clock_instant() -> None:
    ops, clock = FakeOpsRepository(), ManualClock()
    provisioned = await ProvisionUser(ops, clock).execute(
        ProvisionUserCommand("alice", "req-1", EMAIL, "0712345678")
    )
    assert (provisioned.created_user, provisioned.created_organization) == (True, True)
    assert ops.operator_actions[-1]["detail"] == {"request_id": "req-1"}

    account = ops.accounts[EMAIL]
    account.failed_attempts = 5
    account.untrusted_failed_attempts = 2
    account.trusted_devices = 2
    account.live_refresh_tokens = 1

    state = await ReadAccountState(ops, clock).execute(
        ReadAccountStateCommand("alice", "req-2", EMAIL)
    )
    assert (state.user_id, state.status, state.trusted_devices) == (
        provisioned.user_id,
        UserStatus.ACTIVE,
        2,
    )

    clock.advance(10 * 60)
    cleared = await ClearPause(ops, clock).execute(ClearPauseCommand("alice", "req-3", EMAIL))
    assert cleared.was_locked is True  # a lock does not lapse with the clock
    assert (account.failed_attempts, account.untrusted_failed_attempts) == (0, 0)

    revoked = await RevokeSessions(ops, clock).execute(
        RevokeSessionsCommand("alice", "req-4", EMAIL)
    )
    assert (revoked.devices, revoked.tokens, account.security_version) == (2, 1, 1)

    removed = await RemoveUser(ops, clock).execute(RemoveUserCommand("alice", "req-5", EMAIL))
    assert (removed.removed, account.status) == (True, UserStatus.REMOVED)
    assert [a["action"] for a in ops.operator_actions] == [
        "provision-user",
        "account-state",
        "clear-pause",
        "revoke-sessions",
        "remove-user",
    ]
    assert all(a["operator"] == "alice" for a in ops.operator_actions)


async def test_an_unknown_email_is_not_found() -> None:
    with pytest.raises(NotFound):
        await RemoveUser(FakeOpsRepository(), ManualClock()).execute(
            RemoveUserCommand("alice", "req", "nobody@example.com")
        )
