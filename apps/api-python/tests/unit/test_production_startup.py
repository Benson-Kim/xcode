"""``xcode-api serve`` refuses a bad environment before any socket opens (exit 2, every bad
variable named at once) and turns a failed startup into exit 1: the parity of the .NET
``ProductionStartupTests`` and the safety switches of ``docs/08-operability.md`` section 11."""

from __future__ import annotations

import os

import pytest

from xcode_api.cli.commands import serve
from xcode_api.cli.main import main

PRODUCTION = {
    "XCODE_ENV": "production",
    "XCODE_DATABASE_URL": "postgresql://xcode_app@db.example.com/xcode?sslmode=verify-full",
    "XCODE_AUTH_SIGNING_KEY": "production-test-signing-key-0123456789-abcdef",
    "XCODE_EMAIL_HOST": "smtp.example.com",
    "XCODE_EMAIL_FROM": "noreply@example.com",
    "XCODE_ALLOWED_HOSTS": "api.example.com",
}


@pytest.fixture
def environment(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    for name in list(os.environ):
        if name.startswith("XCODE_"):
            monkeypatch.delenv(name)
    return monkeypatch


def _serve_refuses(
    environment: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    values: dict[str, str],
) -> str:
    started: list[object] = []
    environment.setattr(serve.uvicorn, "run", lambda *a, **k: started.append(a))
    for name, value in values.items():
        environment.setenv(name, value)
    assert main(["serve", "--port", "5055"]) == 2
    assert started == []
    return capsys.readouterr().out


def test_production_without_its_four_values_exits_2_naming_each(
    environment: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    out = _serve_refuses(
        environment, capsys, {"XCODE_ENV": "production", "XCODE_ALLOWED_HOSTS": "api.example.com"}
    )
    for name in (
        "XCODE_DATABASE_URL",
        "XCODE_AUTH_SIGNING_KEY",
        "XCODE_EMAIL_HOST",
        "XCODE_EMAIL_FROM",
    ):
        assert name in out, name


@pytest.mark.parametrize(
    "missing",
    ["XCODE_DATABASE_URL", "XCODE_AUTH_SIGNING_KEY", "XCODE_EMAIL_HOST", "XCODE_EMAIL_FROM"],
)
def test_production_without_one_value_exits_2_naming_it(
    environment: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], missing: str
) -> None:
    values = {name: value for name, value in PRODUCTION.items() if name != missing}
    out = _serve_refuses(environment, capsys, values)
    assert missing in out


@pytest.mark.parametrize(
    ("env", "switch", "value"),
    [
        ("production", "XCODE_MAIL_BACKEND", "log"),
        ("production", "XCODE_DEVELOPMENT_CODES", "true"),
        ("testing", "XCODE_DEVELOPMENT_CODES", "true"),
        ("production", "XCODE_DEMO_SEED", "true"),
        ("testing", "XCODE_DEMO_SEED", "true"),
        ("production", "XCODE_AUTO_MIGRATE", "true"),
        ("testing", "XCODE_AUTO_MIGRATE", "true"),
        ("production", "XCODE_LOG_FORMAT", "console"),
        ("production", "XCODE_CORS_ORIGINS", "*"),
        ("testing", "XCODE_CORS_ORIGINS", "*"),
        ("production", "XCODE_ALLOWED_HOSTS", "*"),
    ],
)
def test_a_safety_switch_outside_its_environments_exits_2(
    environment: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    env: str,
    switch: str,
    value: str,
) -> None:
    values = dict(PRODUCTION, XCODE_ENV=env, XCODE_MAIL_BACKEND="smtp")
    values[switch] = value
    out = _serve_refuses(environment, capsys, values)
    assert switch in out


def test_a_complete_production_environment_starts_uvicorn(
    environment: pytest.MonkeyPatch,
) -> None:
    started: list[dict[str, object]] = []
    environment.setattr(serve.uvicorn, "run", lambda *a, **k: started.append(k))
    for name, value in PRODUCTION.items():
        environment.setenv(name, value)
    assert main(["serve", "--port", "5055"]) == 0
    assert started[0]["port"] == 5055
    assert started[0]["proxy_headers"] is False
    assert started[0]["server_header"] is False


def test_a_failed_startup_exits_1(environment: pytest.MonkeyPatch) -> None:
    def refuse(*args: object, **kwargs: object) -> None:
        raise SystemExit(serve.UVICORN_STARTUP_FAILURE)

    environment.setattr(serve.uvicorn, "run", refuse)
    for name, value in PRODUCTION.items():
        environment.setenv(name, value)
    assert main(["serve"]) == 1
