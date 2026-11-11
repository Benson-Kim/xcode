"""Detection counters: a burst is one number using its last wrong-PIN or wrong-code try, and
invitation events count through the bound metrics with bounded labels only."""

from __future__ import annotations

import pytest

from xcode_api.application.observability import (
    active_metrics,
    burst_kind,
    report_auth_outcome,
    report_invitation,
)
from xcode_api.domain.identity import AuthOutcome, AuthOutcomeKind, SignInRefusal
from xcode_api.infra.metrics import Metrics

PIN, CODE = "wrong_pin", "wrong_code"


def _metrics() -> Metrics:
    return Metrics(pool_states=dict, mail_queue_depth=lambda: 0)


def _sample(metrics: Metrics, name: str, **labels: str) -> float:
    value = metrics.registry.get_sample_value(name, labels)
    return 0.0 if value is None else value


@pytest.mark.parametrize(
    ("outcome", "expected"),
    [
        (AuthOutcome(AuthOutcomeKind.PIN_LOCKED), PIN),
        (AuthOutcome(AuthOutcomeKind.INVALID_PIN, SignInRefusal.WRONG_PIN, tries_left=0), PIN),
        (AuthOutcome(AuthOutcomeKind.REFUSED, SignInRefusal.WRONG_CODE, tries_left=0), CODE),
        (AuthOutcome(AuthOutcomeKind.INVALID_PIN, SignInRefusal.WRONG_PIN, tries_left=1), None),
        (AuthOutcome(AuthOutcomeKind.REFUSED, SignInRefusal.WRONG_CODE, tries_left=2), None),
        (AuthOutcome(AuthOutcomeKind.REFUSED, SignInRefusal.WRONG_CODE), None),
        (AuthOutcome(AuthOutcomeKind.REFUSED, SignInRefusal.UNKNOWN_NUMBER, tries_left=0), None),
        (AuthOutcome(AuthOutcomeKind.AUTHENTICATED), None),
    ],
)
def test_a_burst_is_the_last_try_of_a_pin_or_code(
    outcome: AuthOutcome, expected: str | None
) -> None:
    assert burst_kind(outcome) == expected


def test_bursts_and_invitation_events_reach_the_bound_metrics() -> None:
    metrics = _metrics()
    token = active_metrics.set(metrics)
    try:
        report_auth_outcome(AuthOutcome(AuthOutcomeKind.PIN_LOCKED))
        report_auth_outcome(
            AuthOutcome(AuthOutcomeKind.REFUSED, SignInRefusal.WRONG_CODE, tries_left=0)
        )
        for event in ("sent", "sent", "failed", "redeemed"):
            report_invitation(event)
    finally:
        active_metrics.reset(token)
    assert _sample(metrics, "auth_bursts_total", kind="wrong_pin") == 1
    assert _sample(metrics, "auth_bursts_total", kind="wrong_code") == 1
    assert _sample(metrics, "invitations_total", event="sent") == 2
    assert _sample(metrics, "invitations_total", event="failed") == 1
    assert _sample(metrics, "invitations_total", event="redeemed") == 1


def test_nothing_is_reported_without_bound_metrics() -> None:
    metrics = _metrics()
    report_invitation("sent")
    report_auth_outcome(AuthOutcome(AuthOutcomeKind.PIN_LOCKED))
    assert _sample(metrics, "invitations_total", event="sent") == 0
    assert _sample(metrics, "auth_bursts_total", kind="wrong_pin") == 0
