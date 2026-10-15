from __future__ import annotations

import logging
import sys

import structlog
from structlog.contextvars import merge_contextvars

from xcode_api.infra.logging import (
    bind_request_context,
    clear_request_context,
    configure_cli_logging,
    configure_logging,
    redact_processor,
)
from xcode_api.settings import Settings


def _redact(event: dict[str, object]) -> dict[str, object]:
    return dict(redact_processor(None, "info", dict(event)))


def test_redaction_at_top_level() -> None:
    out = _redact({"pin": "1234", "route": "/auth/sign-in"})
    assert out["pin"] == "[redacted]"
    assert out["route"] == "/auth/sign-in"


def test_redaction_at_depth() -> None:
    out = _redact({"claims": {"sub": "u1", "access_token": "secret", "nested": {"phone": "+2547"}}})
    claims = out["claims"]
    assert isinstance(claims, dict)
    assert claims["access_token"] == "[redacted]"
    assert claims["nested"]["phone"] == "[redacted]"
    assert claims["sub"] == "u1"


def test_redaction_covers_every_sensitive_substring() -> None:
    event = {
        k: "x"
        for k in ("pin", "code", "token", "authorization", "password", "phone", "email", "secret")
    }
    out = _redact(event)
    assert all(v == "[redacted]" for v in out.values())


def test_recipient_hash_key_is_not_redacted() -> None:
    out = _redact({"recipient_hash": "abcdef012345"})
    assert out["recipient_hash"] == "abcdef012345"


def test_request_context_is_merged_into_events() -> None:
    try:
        bind_request_context("req-1", actor_id="u1", organization_id="o1")
        event = merge_contextvars(None, "info", {"event": "request.completed", "status": 200})
    finally:
        clear_request_context()
    assert event["request_id"] == "req-1"
    assert event["actor_id"] == "u1"
    assert event["organization_id"] == "o1"
    assert event["event"] == "request.completed"


def _renderer_type() -> type[object]:
    formatter = logging.getLogger().handlers[0].formatter
    assert isinstance(formatter, structlog.stdlib.ProcessorFormatter)
    return type(formatter.processors[-1])


def test_console_renderer_whenever_console_is_configured() -> None:
    configure_logging(Settings.for_tests(env="development", mail_backend="log"))
    assert _renderer_type() is structlog.dev.ConsoleRenderer
    configure_logging(Settings.for_tests())  # testing with log_format=console
    assert _renderer_type() is structlog.dev.ConsoleRenderer


def test_logs_go_to_stderr_and_the_cli_logs_at_info_in_console_form() -> None:
    configure_logging(Settings.for_tests(log_level="DEBUG"))
    handler = logging.getLogger().handlers[0]
    assert isinstance(handler, logging.StreamHandler)
    assert handler.stream is sys.stderr
    assert logging.getLogger().level == logging.DEBUG
    configure_cli_logging()
    handler = logging.getLogger().handlers[0]
    assert isinstance(handler, logging.StreamHandler)
    assert handler.stream is sys.stderr
    assert logging.getLogger().level == logging.INFO
    assert _renderer_type() is structlog.dev.ConsoleRenderer
    assert structlog.get_logger("xcode_api.db").is_enabled_for(logging.DEBUG) is False


def test_json_renderer_outside_console_mode() -> None:
    configure_logging(Settings.for_tests(log_format="json"))
    assert _renderer_type() is structlog.processors.JSONRenderer
    prod = Settings.for_tests(
        env="production",
        log_format="json",
        database_url="postgresql://xcode_app@db/xcode?sslmode=verify-full",
        auth_signing_key="k" * 32,
        allowed_hosts="h",
        mail_backend="smtp",
        email_host="h",
        email_from="a@b.co",
    )
    configure_logging(prod)
    assert _renderer_type() is structlog.processors.JSONRenderer
