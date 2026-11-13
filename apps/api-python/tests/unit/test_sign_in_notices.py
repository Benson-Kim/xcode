"""``SignInNotices``: right after a change it claims that person's notices in the change's own
context and queues one mail each; the sweep claims without a context; each send records sent
or failed at the clock's time; and a failed claim is logged and left to the sweep, since the
change is already saved."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime
from uuid import UUID, uuid4

import pytest

from xcode_api.application.access.sign_in_notices import SEND_LIMIT, SignInNotices
from xcode_api.application.ports import SignInNotice
from xcode_api.domain.tenancy import PendingSignInNotice, SignInNoticeKind, TenantContext

from ..support.clock import ManualClock

ORG = UUID("3e0d8c7b-1a2b-4c5d-8e9f-0a1b2c3d4e5f")
JANE = UUID("9a8b7c6d-5e4f-4a3b-8c2d-1e0f9a8b7c6d")


def _pending(kind: SignInNoticeKind, address: str, hint: str | None = None) -> PendingSignInNotice:
    return PendingSignInNotice(
        notice_id=uuid4(),
        organization_id=ORG,
        address=address,
        kind=kind,
        first_name="Jane",
        actor_name="Olive Owner",
        organization_name="Metro Trans",
        new_address_hint=hint,
    )


class _Tenancy:
    def __init__(self, claimable: list[PendingSignInNotice], *, fail: bool = False) -> None:
        self.claimable = claimable
        self.fail = fail
        self.claims: list[tuple[datetime, int, TenantContext | None, UUID | None]] = []
        self.results: list[tuple[UUID, bool, datetime]] = []

    async def claim_sign_in_notices(
        self,
        now: datetime,
        limit: int,
        *,
        context: TenantContext | None = None,
        user_id: UUID | None = None,
    ) -> list[PendingSignInNotice]:
        self.claims.append((now, limit, context, user_id))
        if self.fail:
            raise ConnectionError("the database went away")
        return self.claimable

    async def record_sign_in_notice(self, notice_id: UUID, sent: bool, now: datetime) -> None:
        self.results.append((notice_id, sent, now))


Callback = Callable[[], Awaitable[None]]


class _Notifier:
    def __init__(self) -> None:
        self.queued: list[tuple[SignInNotice, Callback, Callback]] = []

    def notify(self, notice: SignInNotice, *, on_sent: Callback, on_failure: Callback) -> None:
        self.queued.append((notice, on_sent, on_failure))


def _service(tenancy: _Tenancy) -> tuple[SignInNotices, _Notifier, ManualClock]:
    clock, notifier = ManualClock(), _Notifier()
    service = SignInNotices(tenancy, clock, notifier)  # type: ignore[arg-type]
    return service, notifier, clock


def _context(clock: ManualClock) -> TenantContext:
    return TenantContext(actor_id=uuid4(), organization_id=ORG, request_id="req-1", now=clock.now())


async def test_after_a_change_each_claimed_notice_is_queued_as_one_mail() -> None:
    old = _pending(SignInNoticeKind.OLD, "jane@example.com", "j***@example.org")
    new = _pending(SignInNoticeKind.NEW, "janet@example.org")
    tenancy = _Tenancy([old, new])
    service, notifier, clock = _service(tenancy)
    context = _context(clock)

    assert await service.send_for(context, JANE) == 2

    assert tenancy.claims == [(clock.now(), SEND_LIMIT, context, JANE)]
    assert [n for n, _, _ in notifier.queued] == [
        SignInNotice(
            to="jane@example.com",
            kind=SignInNoticeKind.OLD,
            first_name="Jane",
            actor_name="Olive Owner",
            organization_name="Metro Trans",
            new_address_hint="j***@example.org",
        ),
        SignInNotice(
            to="janet@example.org",
            kind=SignInNoticeKind.NEW,
            first_name="Jane",
            actor_name="Olive Owner",
            organization_name="Metro Trans",
        ),
    ]


async def test_each_send_records_sent_or_failed_for_its_own_notice_at_the_clock() -> None:
    old = _pending(SignInNoticeKind.OLD, "jane@example.com")
    new = _pending(SignInNoticeKind.NEW, "janet@example.org")
    tenancy = _Tenancy([old, new])
    service, notifier, clock = _service(tenancy)
    await service.send_for(_context(clock), JANE)
    (_, sent_old, _), (_, _, failed_new) = notifier.queued

    clock.advance(30)
    await sent_old()
    await failed_new()

    assert tenancy.results == [
        (old.notice_id, True, clock.now()),
        (new.notice_id, False, clock.now()),
    ]


async def test_the_sweep_claims_without_a_context_up_to_its_limit() -> None:
    tenancy = _Tenancy([_pending(SignInNoticeKind.CURRENT, "jane@example.com")])
    service, notifier, clock = _service(tenancy)

    assert await service.sweep(20) == 1

    assert tenancy.claims == [(clock.now(), 20, None, None)]
    assert len(notifier.queued) == 1


async def test_a_failed_claim_after_a_change_is_logged_and_left_to_the_sweep(
    caplog: pytest.LogCaptureFixture,
) -> None:
    tenancy = _Tenancy([_pending(SignInNoticeKind.OLD, "jane@example.com")], fail=True)
    service, notifier, clock = _service(tenancy)

    assert await service.send_for(_context(clock), JANE) == 0

    assert notifier.queued == []
    assert "sign_in_notice.claim_failed" in caplog.text
    assert "jane@example.com" not in caplog.text


async def test_a_failed_sweep_claim_is_raised_for_the_job_to_log() -> None:
    service, _, _ = _service(_Tenancy([], fail=True))
    with pytest.raises(ConnectionError):
        await service.sweep(20)
