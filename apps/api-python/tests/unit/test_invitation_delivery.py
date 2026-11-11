"""The invitation outbox in the application: fresh pairs, post-commit delivery that records its
result, a start failure left to the sweep, the sweep's pairing, and the redeem problem rule."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from tests.support.fakes import FakeInvitationRepository
from xcode_api.application.access.invitation_delivery import (
    InvitationDelivery,
    InvitationPair,
    InvitationSecrets,
)
from xcode_api.application.ports import InvitationMail
from xcode_api.domain.identity import SignInRefusal
from xcode_api.domain.invitations import InviteProblem, PendingInvitation, invite_problem
from xcode_api.security.device_tokens import RandomDeviceTokens, device_token_digest
from xcode_api.security.digests import KeyedDigester
from xcode_api.security.secret_source import RandomSecretSource

NOW = datetime(2026, 11, 10, 9, 0, tzinfo=UTC)
DIGESTS = KeyedDigester("k" * 48)


class _Clock:
    def now(self) -> datetime:
        return NOW


class _Mailer:
    def __init__(self) -> None:
        self.queued: list[
            tuple[InvitationMail, Callable[[], Awaitable[None]], Callable[[], Awaitable[None]]]
        ] = []

    def send_later(
        self,
        mail: InvitationMail,
        *,
        on_sent: Callable[[], Awaitable[None]],
        on_failure: Callable[[], Awaitable[None]],
    ) -> None:
        self.queued.append((mail, on_sent, on_failure))


def _secrets() -> InvitationSecrets:
    return InvitationSecrets(RandomDeviceTokens(), RandomSecretSource(), DIGESTS)


def _pending(pair_index: int | None = None) -> PendingInvitation:
    return PendingInvitation(
        invitation_id=uuid4(),
        email="jane@example.com",
        first_name="Jane",
        organization_name="Rada",
        inviter_name="Amos",
        support_email=None,
        expires_at=NOW,
        time_zone="Africa/Nairobi",
        pair_index=pair_index,
    )


def _delivery(repo: FakeInvitationRepository, mailer: _Mailer) -> InvitationDelivery:
    return InvitationDelivery(repo, _Clock(), mailer, _secrets())


def test_a_pair_stores_only_digests_and_hides_its_secrets() -> None:
    pair = _secrets().new()
    assert pair.hashes.token_hash == device_token_digest(pair.token)
    assert pair.hashes.code_hash == DIGESTS.digest(pair.code)
    assert len(pair.code) == 6 and pair.code.isdigit()
    assert pair.token not in repr(pair) and pair.code not in repr(pair)
    assert _secrets().new().token != pair.token


async def test_send_queues_the_started_invitation_and_records_each_result() -> None:
    repo, mailer = FakeInvitationRepository(), _Mailer()
    pair = _secrets().new()
    repo.pending[pair.hashes.token_hash] = _pending()
    await _delivery(repo, mailer).send(pair, request_id="req-1")
    ((mail, on_sent, on_failure),) = mailer.queued
    assert (mail.token, mail.code, mail.to, mail.request_id) == (
        pair.token,
        pair.code,
        "jane@example.com",
        "req-1",
    )
    await on_sent()
    await on_failure()
    assert repo.results == [(pair.hashes.token_hash, True), (pair.hashes.token_hash, False)]


async def test_send_without_a_started_invitation_mails_nothing() -> None:
    repo, mailer = FakeInvitationRepository(), _Mailer()
    pair = _secrets().new()
    await _delivery(repo, mailer).send(pair, request_id=None)
    assert repo.started == [pair.hashes.token_hash]
    assert mailer.queued == []


async def test_a_failed_start_is_left_to_the_sweep(caplog: pytest.LogCaptureFixture) -> None:
    class _Down(FakeInvitationRepository):
        async def start_delivery(self, token_hash: str, now: datetime) -> PendingInvitation | None:
            raise RuntimeError("db down")

    mailer = _Mailer()
    pair: InvitationPair = _secrets().new()
    await _delivery(_Down(), mailer).send(pair, request_id="req-2")
    assert mailer.queued == []
    assert "invitation.start_failed" in caplog.text
    assert pair.token not in caplog.text and pair.code not in caplog.text


async def test_the_sweep_mails_each_claim_with_its_own_pair() -> None:
    repo, mailer = FakeInvitationRepository(), _Mailer()
    repo.claimable = [_pending(2), _pending(0), _pending(9)]
    assert await _delivery(repo, mailer).sweep(3) == 3
    ((limit, token_hashes, code_hashes),) = repo.claims
    assert limit == 3 and len(token_hashes) == len(code_hashes) == 3
    sent = [device_token_digest(mail.token) for mail, _, _ in mailer.queued]
    assert sent == [token_hashes[2], token_hashes[0]]
    assert [DIGESTS.digest(mail.code) for mail, _, _ in mailer.queued] == [
        code_hashes[2],
        code_hashes[0],
    ]


@pytest.mark.parametrize(
    ("refusal", "problem"),
    [
        (SignInRefusal.INVITE_EXPIRED, InviteProblem.EXPIRED),
        (SignInRefusal.INVITE_USED, InviteProblem.USED),
        (SignInRefusal.INVITE_REVOKED, InviteProblem.REVOKED),
        (SignInRefusal.INVITE_INVALID, None),
        (None, None),
    ],
)
def test_only_a_matched_redeem_tells_its_problem(
    refusal: SignInRefusal | None, problem: InviteProblem | None
) -> None:
    assert invite_problem(refusal) is problem
