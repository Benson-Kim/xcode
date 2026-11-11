"""``CreateReviewAccount`` and ``xcode-api review-account create``: the PIN and the fixed code
reach the routine only as a PIN hash and the API's keyed digest, a drawn PIN obeys the new-PIN
rule, a second run replaces both, and the command refuses before connecting when it could not
produce a digest the API would match."""

from __future__ import annotations

import os
import secrets
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest

from xcode_api.application.ops.create_review_account import (
    PIN_DRAWS,
    CreateReviewAccount,
    CreateReviewAccountCommand,
)
from xcode_api.cli.main import main
from xcode_api.domain.errors import Forbidden
from xcode_api.domain.policies import new_pin_problem
from xcode_api.security.codes import new_pin
from xcode_api.security.digests import KeyedDigester
from xcode_api.security.pins import Pbkdf2PinHasher
from xcode_api.security.secret_source import RandomSecretSource

from ..support.clock import ManualClock
from ..support.fakes import FakeOpsRepository

NOW = datetime(2026, 11, 11, 9, 0, tzinfo=UTC)
EMAIL = "app.review@example.com"
PHONE = "+254700111222"


def _use_case(
    ops: FakeOpsRepository, key: str, draws: Iterator[str] | None = None
) -> CreateReviewAccount:
    return CreateReviewAccount(
        ops,
        ManualClock(NOW),
        pins=Pbkdf2PinHasher(1),
        codes=KeyedDigester(key),
        secret_source=RandomSecretSource(),
        new_pin=new_pin if draws is None else lambda: next(draws),
    )


def _command(request_id: str = "request-1") -> CreateReviewAccountCommand:
    return CreateReviewAccountCommand("ops", request_id, email=EMAIL, phone=PHONE)


def _seeded() -> FakeOpsRepository:
    ops = FakeOpsRepository()
    ops.demo_seeded = True
    return ops


async def test_the_pin_and_code_reach_the_routine_only_as_hashes_the_api_matches() -> None:
    ops, key = _seeded(), secrets.token_urlsafe(32)
    review = await _use_case(ops, key).execute(_command())
    sent = ops.review_account
    assert sent is not None
    assert review.account.created_user is True
    assert review.code.isdigit() and len(review.code) == 6
    assert sent.code_hash == KeyedDigester(key).digest(review.code)
    assert review.code not in sent.code_hash
    assert review.pin not in sent.pin_hash
    assert await Pbkdf2PinHasher(1).verify(review.pin, sent.pin_hash)
    assert new_pin_problem(review.pin, PHONE) is None
    assert (sent.email, sent.phone, sent.now) == (EMAIL, PHONE, NOW)


async def test_a_second_run_replaces_both_secrets() -> None:
    ops, key = _seeded(), secrets.token_urlsafe(32)
    first = await _use_case(ops, key, iter(["4071"])).execute(_command("request-1"))
    second = await _use_case(ops, key, iter(["5182"])).execute(_command("request-2"))
    sent = ops.review_account
    assert sent is not None
    assert second.account.created_user is False
    assert not await Pbkdf2PinHasher(1).verify(first.pin, sent.pin_hash)
    assert await Pbkdf2PinHasher(1).verify(second.pin, sent.pin_hash)
    assert [a["action"] for a in ops.operator_actions] == ["review-account", "review-account"]


async def test_a_drawn_pin_that_breaks_the_new_pin_rule_is_drawn_again() -> None:
    draws = iter(["1111", "1234", PHONE[-4:], "4071"])
    review = await _use_case(_seeded(), secrets.token_urlsafe(32), draws).execute(_command())
    assert review.pin == "4071"


async def test_a_generator_that_never_draws_an_acceptable_pin_stops() -> None:
    ops = _seeded()
    with pytest.raises(RuntimeError):
        await _use_case(ops, secrets.token_urlsafe(32), iter(["0000"] * PIN_DRAWS)).execute(
            _command()
        )
    assert ops.review_account is None


async def test_outside_a_demo_organization_the_refusal_is_the_routines() -> None:
    ops = FakeOpsRepository()
    with pytest.raises(Forbidden) as refusal:
        await _use_case(ops, secrets.token_urlsafe(32)).execute(_command())
    assert refusal.value.code == "review_demo_only"
    assert ops.review_account is None


async def test_no_secret_shows_in_a_repr() -> None:
    ops = _seeded()
    review = await _use_case(ops, secrets.token_urlsafe(32)).execute(_command())
    sent = ops.review_account
    assert sent is not None
    shown = repr(review) + repr(sent) + repr(_command())
    for name in ("pin=", "code=", "pin_hash=", "code_hash=", "email=", "phone="):
        assert name not in shown
    for value in (sent.pin_hash, sent.code_hash, EMAIL, PHONE):
        assert value not in shown


def test_a_new_pin_is_four_ascii_digits() -> None:
    for _ in range(50):
        pin = new_pin()
        assert len(pin) == 4 and all("0" <= ch <= "9" for ch in pin)


# --- the command ------------------------------------------------------------------------


def _testing_env(monkeypatch: pytest.MonkeyPatch, **values: str) -> None:
    for name in list(os.environ):
        if name.startswith("XCODE_"):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("XCODE_ENV", "testing")
    monkeypatch.setenv("XCODE_DATABASE_URL", "postgresql://xcode_app@127.0.0.1:1/x")
    monkeypatch.setenv("XCODE_MAIL_BACKEND", "log")
    for name, value in values.items():
        monkeypatch.setenv(name, value)


def _create(capsys: pytest.CaptureFixture[str]) -> tuple[int, str]:
    code = main(["review-account", "create", "--email", EMAIL, "--phone", PHONE])
    return code, capsys.readouterr().out.strip()


def test_the_command_exits_2_without_the_operator_url(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _testing_env(monkeypatch, XCODE_AUTH_SIGNING_KEY=secrets.token_urlsafe(32))
    assert _create(capsys) == (2, "XCODE_DATABASE_OPERATOR_URL is required for review-account")


def test_the_command_exits_2_when_the_api_signing_key_is_unset(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _testing_env(
        monkeypatch, XCODE_DATABASE_OPERATOR_URL="postgresql://xcode_operator@127.0.0.1:1/x"
    )
    assert _create(capsys) == (
        2,
        "XCODE_AUTH_SIGNING_KEY is required for review-account: the API digests codes with it",
    )


def test_the_command_exits_2_on_invalid_api_settings(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _testing_env(monkeypatch, XCODE_MIN_MOBILE_VERSION="latest")
    code, out = _create(capsys)
    assert code == 2
    assert "XCODE_MIN_MOBILE_VERSION" in out


def test_the_command_needs_its_action(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["review-account"])
    assert exit_info.value.code == 2
    assert "create" in capsys.readouterr().err
