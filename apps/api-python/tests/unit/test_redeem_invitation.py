"""``RedeemInvitation``: only digests reach the routine, the first-setup code is answered once
on a match, and a refusal tells its problem only when the routine names one."""

from __future__ import annotations

from typing import cast
from uuid import uuid4

import pytest

from xcode_api.application.auth.redeem_invitation import (
    InvitationRedeemed,
    RedeemInvitation,
    RedeemInvitationCommand,
)
from xcode_api.application.repositories import IdentityRepository
from xcode_api.domain.identity import AuthOutcome, AuthOutcomeKind, EnvelopeStatus, SignInRefusal
from xcode_api.domain.invitations import InvitationRedeem, InviteProblem
from xcode_api.domain.policies import refusal_answer
from xcode_api.domain.values import PhoneNumber
from xcode_api.security.device_tokens import RandomDeviceTokens
from xcode_api.security.digests import KeyedDigester

from ..support.clock import ManualClock
from ..support.fakes import FixedSecrets
from .conftest import SIGNING_KEY

TOKEN = "link-token-from-the-mail"
PHONE = "0712345678"
DEVICE = "phone-1"


class _IdentityStub:
    def __init__(self, outcome: AuthOutcome) -> None:
        self.outcome = outcome
        self.calls: list[InvitationRedeem] = []

    async def invite_redeem(self, command: InvitationRedeem) -> AuthOutcome:
        self.calls.append(command)
        return self.outcome


def _use_case(outcome: AuthOutcome) -> tuple[RedeemInvitation, _IdentityStub, ManualClock]:
    identity = _IdentityStub(outcome)
    clock = ManualClock()
    use_case = RedeemInvitation(
        cast(IdentityRepository, identity),
        clock,
        digests=KeyedDigester(SIGNING_KEY),
        secrets=FixedSecrets(),
        device_tokens=RandomDeviceTokens(),
    )
    return use_case, identity, clock


def _command(phone: str = PHONE) -> RedeemInvitationCommand:
    return RedeemInvitationCommand("req-1", TOKEN, phone, DEVICE)


def _refused(refusal: SignInRefusal) -> AuthOutcome:
    return AuthOutcome(AuthOutcomeKind.REFUSED, refusal=refusal)


async def test_a_match_answers_the_code_once_and_stores_only_digests() -> None:
    issued = AuthOutcome(AuthOutcomeKind.VERIFICATION_REQUIRED, code_id=uuid4())
    use_case, identity, clock = _use_case(issued)

    result = await use_case.execute(_command())

    assert result.envelope.status is EnvelopeStatus.VERIFICATION_REQUIRED
    assert result.code == FixedSecrets().code
    assert result.problem is None
    [sent] = identity.calls
    assert sent.token_hash == RandomDeviceTokens().digest(TOKEN) != TOKEN
    assert sent.code_hash == KeyedDigester(SIGNING_KEY).digest(result.code) != result.code
    assert sent.phone == cast(PhoneNumber, PhoneNumber.parse(PHONE)).value
    assert (sent.request_id, sent.device_id, sent.now) == ("req-1", DEVICE, clock.now())


async def test_an_unknown_token_wrong_number_or_other_persons_token_tells_nothing() -> None:
    use_case, _, _ = _use_case(_refused(SignInRefusal.INVITE_INVALID))

    result = await use_case.execute(_command())

    assert result.envelope.status is EnvelopeStatus.AUTHENTICATION_FAILED
    assert (result.code, result.problem) == (None, None)


@pytest.mark.parametrize(
    ("refusal", "problem"),
    [
        (SignInRefusal.INVITE_EXPIRED, InviteProblem.EXPIRED),
        (SignInRefusal.INVITE_USED, InviteProblem.USED),
        (SignInRefusal.INVITE_REVOKED, InviteProblem.REVOKED),
    ],
)
async def test_a_matched_but_spent_invitation_tells_its_problem_and_no_code(
    refusal: SignInRefusal, problem: InviteProblem
) -> None:
    use_case, _, _ = _use_case(_refused(refusal))

    result = await use_case.execute(_command())

    assert result.envelope.status is EnvelopeStatus.AUTHENTICATION_FAILED
    assert (result.code, result.problem) == (None, problem)


async def test_no_stored_code_means_no_code_in_the_answer() -> None:
    use_case, _, _ = _use_case(AuthOutcome(AuthOutcomeKind.VERIFICATION_REQUIRED))

    result = await use_case.execute(_command())

    assert result.code is None


async def test_a_number_that_does_not_parse_reaches_the_routine_as_typed() -> None:
    use_case, identity, _ = _use_case(_refused(SignInRefusal.INVITE_INVALID))

    await use_case.execute(_command(phone="not a number"))

    assert identity.calls[0].phone == "not a number"


async def test_the_throttle_key_is_the_token_digest_never_the_token() -> None:
    use_case, _, _ = _use_case(_refused(SignInRefusal.INVITE_INVALID))

    assert use_case.token_key(TOKEN) == RandomDeviceTokens().digest(TOKEN)
    assert TOKEN not in use_case.token_key(TOKEN)


def test_reprs_never_show_the_token_number_or_code() -> None:
    command = _command()
    redeemed = InvitationRedeemed(refusal_answer(), code="048213")

    assert TOKEN not in repr(command) and PHONE not in repr(command)
    assert "048213" not in repr(redeemed)
