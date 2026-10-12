from __future__ import annotations

import os
from typing import Any

import pytest

from xcode_api.cli.commands import serve
from xcode_api.cli.main import main
from xcode_api.http.middleware import client_address


def _scope(peer: str, *forwarded: str) -> dict[str, Any]:
    headers = [(b"x-forwarded-for", value.encode()) for value in forwarded]
    return {"type": "http", "client": (peer, 1234), "headers": headers}


def test_a_second_forwarded_line_is_read_after_the_first() -> None:
    # A proxy that adds its own X-Forwarded-For line keeps the client's line first; the
    # lines form one list in order (RFC 9110 section 5.3), so the proxy's entry is last.
    scope = _scope("10.0.0.5", "203.0.113.9", "198.51.100.7")
    assert client_address(scope, ["10.0.0.0/8"]) == "198.51.100.7"


def test_forwarded_lines_are_walked_as_one_list() -> None:
    scope = _scope("10.0.0.5", "203.0.113.9, 10.0.0.7", "10.0.0.6")
    assert client_address(scope, ["10.0.0.0/8"]) == "203.0.113.9"


def test_serve_leaves_forwarded_headers_to_the_trusted_proxies_setting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in [key for key in os.environ if key.startswith("XCODE_")]:
        monkeypatch.delenv(name)
    monkeypatch.setenv("XCODE_ENV", "testing")
    monkeypatch.setenv("XCODE_DATABASE_URL", "postgresql://xcode_app@localhost/xcode")
    monkeypatch.setenv("XCODE_MAIL_BACKEND", "log")
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(serve.uvicorn, "run", lambda *args, **kwargs: calls.append(kwargs))
    assert main(["serve"]) == 0
    assert calls[0]["proxy_headers"] is False
