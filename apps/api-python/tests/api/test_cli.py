"""The CLI user commands against a real database as ``xcode_operator``: each command's effect,
its ``ops.operator_actions`` row with the operator's name (``docs/12-security.md`` section 2),
and output that carries ids and counts only."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Iterator
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import psycopg
import pytest

from xcode_api.application.ops.seed_demo import DEMO_PINS
from xcode_api.cli.main import main
from xcode_api.security.pins import Pbkdf2PinHasher

Conn = psycopg.Connection[dict[str, Any]]
OPERATOR = "support-desk"
EMAIL = "owner@example.com"


@pytest.fixture
def cli(app_url: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    for key in [k for k in os.environ if k.startswith("XCODE_")]:
        monkeypatch.delenv(key, raising=False)
    parts = urlsplit(app_url)
    operator_url = urlunsplit(
        (
            parts.scheme,
            f"xcode_operator:xcode_operator@{parts.hostname}:{parts.port}",
            parts.path,
            parts.query,
            parts.fragment,
        )
    )
    monkeypatch.setenv("XCODE_ENV", "testing")
    monkeypatch.setenv("XCODE_DATABASE_OPERATOR_URL", operator_url)
    monkeypatch.setenv("XCODE_OPERATOR", OPERATOR)
    yield


def _run(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, str]:
    code = main(list(argv))
    captured = capsys.readouterr()
    # Logs go to stderr; stdout is the command's output and nothing else.
    assert "db.routine" not in captured.out, captured.out
    return code, captured.out.strip()


def _fields(output: str) -> dict[str, str]:
    first = output.splitlines()[0]
    return dict(pair.split("=", 1) for pair in first.split())


def _actions(owner: Conn, action: str) -> list[dict[str, Any]]:
    return owner.execute(
        "SELECT operator, target, detail FROM ops.operator_actions WHERE action = %s ORDER BY id",
        (action,),
    ).fetchall()


def _provision(capsys: pytest.CaptureFixture[str]) -> dict[str, str]:
    code, out = _run(capsys, "provision-user", "--email", EMAIL, "--phone", "0712345678")
    assert code == 0, out
    return _fields(out)


@pytest.mark.usefixtures("cli")
def test_provision_user_creates_the_person_and_records_the_operator(
    capsys: pytest.CaptureFixture[str], owner_conn: Conn
) -> None:
    code, out = _run(
        capsys,
        "provision-user",
        "--email",
        EMAIL,
        "--phone",
        "0712345678",
        "--role",
        "Office admin",
        "--first-name",
        "Grace",
        "--last-name",
        "Achieng",
    )
    assert code == 0
    fields = _fields(out)
    assert (fields["created_user"], fields["created_organization"]) == ("yes", "yes")
    assert out.splitlines()[1] == "They can now set a PIN with an email code."
    assert "0712345678" not in out
    assert EMAIL not in out
    row = owner_conn.execute(
        "SELECT u.id::text AS id, m.first_name, m.last_name FROM identity.users u "
        "JOIN tenancy.memberships m ON m.user_id = u.id WHERE u.email = %s",
        (EMAIL,),
    ).fetchone()
    assert row == {"id": fields["user_id"], "first_name": "Grace", "last_name": "Achieng"}
    actions = _actions(owner_conn, "provision-user")
    assert [(a["operator"], a["target"]) for a in actions] == [(OPERATOR, EMAIL)]


@pytest.mark.usefixtures("cli")
def test_account_state_prints_counts_and_never_a_hash(
    capsys: pytest.CaptureFixture[str], owner_conn: Conn
) -> None:
    user_id = _provision(capsys)["user_id"]
    code, out = _run(capsys, "account-state", "--email", EMAIL)
    assert code == 0
    assert _fields(out) == {
        "user_id": user_id,
        "status": "active",
        "has_pin": "no",
        "pin_reset_required": "no",
        "sign_in_status": "not_signed_in",
        "last_signed_in_at": "none",
        "failed_attempts": "0",
        "untrusted_failed_attempts": "0",
        "trusted_devices": "0",
        "live_refresh_tokens": "0",
        "active_membership": "yes",
    }
    assert [a["operator"] for a in _actions(owner_conn, "account-state")] == [OPERATOR]


@pytest.mark.usefixtures("cli")
def test_clear_pause_clears_both_lock_scopes(
    capsys: pytest.CaptureFixture[str], owner_conn: Conn
) -> None:
    user_id = _provision(capsys)["user_id"]
    owner_conn.execute(
        "UPDATE identity.users SET failed_attempts = 5, untrusted_failed_attempts = 5 "
        "WHERE id = %s",
        (user_id,),
    )
    code, out = _run(capsys, "clear-pause", "--email", EMAIL)
    assert code == 0
    assert _fields(out) == {"user_id": user_id, "was_locked": "yes"}
    row = owner_conn.execute(
        "SELECT failed_attempts, untrusted_failed_attempts FROM identity.users WHERE id = %s",
        (user_id,),
    ).fetchone()
    assert row == {"failed_attempts": 0, "untrusted_failed_attempts": 0}
    assert [a["operator"] for a in _actions(owner_conn, "clear-pause")] == [OPERATOR]


@pytest.mark.usefixtures("cli")
def test_revoke_sessions_revokes_devices_and_tokens(
    capsys: pytest.CaptureFixture[str], owner_conn: Conn
) -> None:
    user_id = _provision(capsys)["user_id"]
    owner_conn.execute(
        "INSERT INTO identity.trusted_devices (user_id, device_id, trusted_at, last_used_at) "
        "VALUES (%s, 'phone', now(), now())",
        (user_id,),
    )
    owner_conn.execute(
        "INSERT INTO identity.refresh_tokens (user_id, device_id, token_hash, expires_at) "
        "VALUES (%s, 'phone', repeat('B', 64), now() + interval '1 day')",
        (user_id,),
    )
    code, out = _run(capsys, "revoke-sessions", "--email", EMAIL)
    assert code == 0
    assert _fields(out) == {"user_id": user_id, "devices": "1", "tokens": "1"}
    version = owner_conn.execute(
        "SELECT security_version FROM identity.users WHERE id = %s", (user_id,)
    ).fetchone()
    assert version == {"security_version": 1}
    assert [a["operator"] for a in _actions(owner_conn, "revoke-sessions")] == [OPERATOR]


@pytest.mark.usefixtures("cli")
def test_remove_user_marks_the_user_removed(
    capsys: pytest.CaptureFixture[str], owner_conn: Conn
) -> None:
    user_id = _provision(capsys)["user_id"]
    code, out = _run(capsys, "remove-user", "--email", EMAIL)
    assert code == 0
    assert _fields(out) == {"user_id": user_id, "removed": "yes", "tokens": "0"}
    status = owner_conn.execute(
        "SELECT status FROM identity.users WHERE id = %s", (user_id,)
    ).fetchone()
    assert status == {"status": "removed"}
    assert [a["operator"] for a in _actions(owner_conn, "remove-user")] == [OPERATOR]


@pytest.mark.usefixtures("cli")
def test_a_refusal_exits_1_with_its_code_and_is_recorded(
    capsys: pytest.CaptureFixture[str], owner_conn: Conn
) -> None:
    code, out = _run(capsys, "remove-user", "--email", "Nobody@Example.com")
    assert (code, out) == (1, "refused: not_found")
    actions = _actions(owner_conn, "remove-user")
    assert len(actions) == 1
    assert (actions[0]["operator"], actions[0]["target"]) == (OPERATOR, "nobody@example.com")
    assert actions[0]["detail"]["refused"] == "not_found"

    code, out = _run(capsys, "provision-user", "--email", "not-an-email", "--phone", "0712345678")
    assert (code, out) == (1, "refused: people_email_invalid")


# --- seed-demo ----------------------------------------------------------------------------


@pytest.mark.usefixtures("cli")
@pytest.mark.parametrize("env", ["testing", "production"])
def test_seed_demo_is_refused_outside_development_and_writes_nothing(
    capsys: pytest.CaptureFixture[str],
    owner_conn: Conn,
    monkeypatch: pytest.MonkeyPatch,
    env: str,
) -> None:
    monkeypatch.setenv("XCODE_ENV", env)
    code, out = _run(capsys, "seed-demo")
    assert (code, out) == (1, "refused: seed_development_only")
    assert owner_conn.execute("SELECT count(*) AS n FROM tenancy.organizations").fetchone() == {
        "n": 0
    }
    assert _actions(owner_conn, "seed-demo") == []


@pytest.mark.usefixtures("cli")
def test_seed_demo_seeds_once_and_the_pins_verify(
    capsys: pytest.CaptureFixture[str], owner_conn: Conn, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XCODE_ENV", "development")
    monkeypatch.setenv("XCODE_AUTH_PIN_ITERATIONS", "1000")
    code, out = _run(capsys, "seed-demo")
    assert code == 0, out
    first = _fields(out)
    assert first["created"] == "yes"
    code, out = _run(capsys, "seed-demo")
    assert code == 0, out
    assert _fields(out) == {"organization_id": first["organization_id"], "created": "no"}
    actions = _actions(owner_conn, "seed-demo")
    assert [(a["operator"], a["target"]) for a in actions] == [(OPERATOR, "demo-fleet")] * 2
    stored = {
        row["email"]: row["pin_hash"]
        for row in owner_conn.execute("SELECT email, pin_hash FROM identity.users").fetchall()
    }
    hasher = Pbkdf2PinHasher(1000)
    for email, pin in DEMO_PINS.items():
        assert asyncio.run(hasher.verify(pin, stored[email])), email
    assert stored["brian.mwangi@metrotrans.co.ke"] is None
