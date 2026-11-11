"""What a request reports to the metrics while it runs (``docs/08-operability.md`` section 5).

The HTTP layer binds the app's metrics to ``active_metrics`` for one request; the gateway
reports each routine's duration and the auth routines' refusals through it; the lifespan
binds it for the mail queue and the sweep, which report invitation events. Nothing is
reported when metrics are off. Refusal reasons are the four internal words of the
document and bursts are one of two kinds, never a per-account value.
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import Protocol

from ..domain.identity import AuthOutcome, AuthOutcomeKind, SignInRefusal


class RuntimeMetrics(Protocol):
    def routine_finished(self, routine: str, seconds: float) -> None: ...

    def auth_refused(self, reason: str) -> None: ...

    def auth_burst(self, kind: str) -> None: ...

    def invitation(self, event: str) -> None: ...


active_metrics: ContextVar[RuntimeMetrics | None] = ContextVar("xcode_metrics", default=None)

_REFUSAL_REASONS = {
    SignInRefusal.UNKNOWN_NUMBER: "unknown",
    SignInRefusal.WRONG_PIN: "wrong_pin",
    SignInRefusal.PAUSED_UNTRUSTED: "paused",
    SignInRefusal.UNTRUSTED_CAP: "capped",
}


def refusal_reason(outcome: AuthOutcome) -> str | None:
    """``unknown``, ``paused``, ``capped`` or ``wrong_pin`` for a sign-in refusal; else None."""
    if outcome.outcome in (AuthOutcomeKind.PAUSED, AuthOutcomeKind.PIN_LOCKED):
        return "paused"
    if outcome.refusal is None:
        return None
    return _REFUSAL_REASONS.get(outcome.refusal)


def burst_kind(outcome: AuthOutcome) -> str | None:
    """``wrong_pin`` or ``wrong_code`` when this refusal used a number's last try; else None."""
    if outcome.outcome is AuthOutcomeKind.PIN_LOCKED:
        return "wrong_pin"
    if outcome.tries_left == 0 and outcome.refusal in (
        SignInRefusal.WRONG_PIN,
        SignInRefusal.WRONG_CODE,
    ):
        return str(outcome.refusal)
    return None


def report_invitation(event: str) -> None:
    """``sent``, ``failed`` or ``redeemed``."""
    metrics = active_metrics.get()
    if metrics is not None:
        metrics.invitation(event)


def report_routine(routine: str, seconds: float) -> None:
    metrics = active_metrics.get()
    if metrics is not None:
        metrics.routine_finished(routine, seconds)


def report_auth_outcome(outcome: AuthOutcome) -> None:
    metrics = active_metrics.get()
    if metrics is None:
        return
    reason = refusal_reason(outcome)
    if reason is not None:
        metrics.auth_refused(reason)
    burst = burst_kind(outcome)
    if burst is not None:
        metrics.auth_burst(burst)
