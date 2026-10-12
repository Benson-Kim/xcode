from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest

from xcode_api.cli.main import COMMANDS, build_parser, main

USER_COMMANDS = ("provision-user", "remove-user", "clear-pause", "revoke-sessions", "account-state")
OPERABILITY = Path(__file__).resolve().parents[2] / "docs" / "08-operability.md"
SECRETS = {
    "XCODE_AUTH_SIGNING_KEY": "help-must-not-show-this-signing-key-0123456789",
    "XCODE_EMAIL_PASSWORD": "help-must-not-show-this-mail-password",
    "XCODE_DATABASE_URL": "postgresql://xcode_app:help-db-secret@localhost/xcode",
    "XCODE_DATABASE_OPERATOR_URL": "postgresql://xcode_operator:help-op-secret@localhost/xcode",
    "XCODE_MIGRATION_DATABASE_URL": "postgresql://xcode_owner:help-owner-secret@localhost/x",
}


def _documented_commands() -> list[str]:
    """The first word of every command cell of ``docs/08-operability.md`` section 8."""
    text = OPERABILITY.read_text("utf-8").replace("\r", "")
    section = text.split("## 8. CLI", 1)[1].split("\n## ", 1)[0]
    return re.findall(r"^\| `([a-z][a-z-]*)", section, flags=re.MULTILINE)


def test_registry_lists_every_command() -> None:
    names = {module.NAME for module in COMMANDS}
    assert names == {"serve", "db", "openapi", "settings-check", "seed-demo", *USER_COMMANDS}


def test_registry_equals_the_documented_table() -> None:
    documented = _documented_commands()
    assert len(documented) == len(set(documented))
    assert sorted(documented) == sorted(module.NAME for module in COMMANDS)


@pytest.mark.parametrize("name", sorted(module.NAME for module in COMMANDS))
def test_every_command_has_help_that_names_no_secret(
    name: str, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    for key, value in SECRETS.items():
        monkeypatch.setenv(key, value)
    with pytest.raises(SystemExit) as exit_info:
        main([name, "--help"])
    assert exit_info.value.code == 0
    out = capsys.readouterr().out
    assert name in out
    for value in SECRETS.values():
        assert value not in out
    for word in ("help-db-secret", "help-op-secret", "help-owner-secret"):
        assert word not in out


@pytest.mark.parametrize("env", ["testing", "production"])
def test_seed_demo_is_refused_outside_development_before_connecting(
    env: str, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_xcode_env(monkeypatch)
    monkeypatch.setenv("XCODE_ENV", env)
    monkeypatch.setenv("XCODE_DATABASE_OPERATOR_URL", "postgresql://xcode_operator@127.0.0.1:1/x")
    assert main(["seed-demo"]) == 1
    assert capsys.readouterr().out.strip() == "refused: seed_development_only"


def test_seed_demo_exits_2_without_the_operator_url(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_xcode_env(monkeypatch)
    monkeypatch.setenv("XCODE_ENV", "development")
    assert main(["seed-demo"]) == 2
    assert capsys.readouterr().out.strip() == (
        "XCODE_DATABASE_OPERATOR_URL is required for seed-demo"
    )


def test_seed_demo_reports_an_unreachable_server_without_a_traceback(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_xcode_env(monkeypatch)
    monkeypatch.setenv("XCODE_ENV", "development")
    monkeypatch.setenv("XCODE_AUTH_PIN_ITERATIONS", "1")
    monkeypatch.setenv("XCODE_DATABASE_OPERATOR_URL", "postgresql://xcode_operator@127.0.0.1:1/x")
    monkeypatch.setattr("xcode_api.cli.commands.seed.CONNECT_TIMEOUT_SECONDS", 0.5)
    assert main(["seed-demo"]) == 1
    assert capsys.readouterr().out.strip() == "could not connect to the database as the operator"


def test_provision_user_parses_its_options() -> None:
    args = build_parser().parse_args(
        [
            "provision-user",
            "--email",
            "owner@example.com",
            "--phone",
            "0712345678",
            "--role",
            "Office admin",
            "--first-name",
            "Grace",
            "--last-name",
            "Achieng",
            "--organization-name",
            "North Star",
        ]
    )
    assert (args.email, args.phone, args.role) == (
        "owner@example.com",
        "0712345678",
        "Office admin",
    )
    assert (args.first_name, args.last_name, args.organization_name) == (
        "Grace",
        "Achieng",
        "North Star",
    )
    minimal = build_parser().parse_args(["provision-user", "--email", "a@b.c", "--phone", "1"])
    assert (minimal.role, minimal.first_name, minimal.organization_name) == (None, None, None)


@pytest.mark.parametrize(
    "argv",
    [
        ["provision-user", "--email", "owner@example.com"],
        ["provision-user", "--phone", "0712345678"],
        *[[name] for name in USER_COMMANDS],
    ],
)
def test_user_commands_require_their_arguments(argv: list[str]) -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(argv)


@pytest.mark.parametrize("name", USER_COMMANDS)
def test_user_commands_exit_2_without_the_operator_url(
    name: str, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_xcode_env(monkeypatch)
    monkeypatch.setenv("XCODE_ENV", "testing")
    argv = [name, "--email", "owner@example.com"]
    if name == "provision-user":
        argv += ["--phone", "0712345678"]
    code = main(argv)
    out = capsys.readouterr().out
    assert code == 2
    assert out.strip() == f"XCODE_DATABASE_OPERATOR_URL is required for {name}"


def test_user_commands_report_an_unreachable_server_without_a_traceback(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_xcode_env(monkeypatch)
    monkeypatch.setenv("XCODE_ENV", "testing")
    monkeypatch.setenv(
        "XCODE_DATABASE_OPERATOR_URL",
        "postgresql://xcode_operator:xcode_operator@127.0.0.1:1/xcode?connect_timeout=1",
    )
    monkeypatch.setattr("xcode_api.cli.commands.users.CONNECT_TIMEOUT_SECONDS", 2.0)
    code = main(["account-state", "--email", "owner@example.com"])
    out = capsys.readouterr().out
    assert code == 1
    assert "could not connect to the database as the operator" in out
    assert "xcode_operator:xcode_operator" not in out


def test_parser_requires_a_subcommand() -> None:
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([])


def _clear_xcode_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in list(os.environ):
        if key.startswith("XCODE_"):
            monkeypatch.delenv(key, raising=False)


def test_settings_check_exits_2_on_violation(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_xcode_env(monkeypatch)
    monkeypatch.setenv("XCODE_ENV", "production")
    code = main(["settings-check"])
    out = capsys.readouterr().out
    assert code == 2
    assert "XCODE_DATABASE_URL" in out


def test_settings_check_prints_summary_and_exits_0(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_xcode_env(monkeypatch)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("XCODE_ENV", "testing")
    monkeypatch.setenv("XCODE_DATABASE_URL", "postgresql://xcode_app@localhost/xcode")
    monkeypatch.setenv("XCODE_MAIL_BACKEND", "log")
    code = main(["settings-check"])
    out = capsys.readouterr().out
    assert code == 0
    summary = json.loads(out)
    assert summary["env"] == "testing"
    assert summary["auth_signing_key"] == "<generated>"
    assert "k" * 32 not in out


def test_settings_check_summary_has_no_secret(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_xcode_env(monkeypatch)
    secret = "s" * 40
    monkeypatch.setenv("XCODE_ENV", "testing")
    monkeypatch.setenv("XCODE_DATABASE_URL", "postgresql://xcode_app@localhost/xcode")
    monkeypatch.setenv("XCODE_MAIL_BACKEND", "log")
    monkeypatch.setenv("XCODE_AUTH_SIGNING_KEY", secret)
    main(["settings-check"])
    assert secret not in capsys.readouterr().out


def test_db_command_reports_an_unreachable_server_without_a_traceback(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_xcode_env(monkeypatch)
    monkeypatch.setenv("XCODE_ENV", "testing")
    monkeypatch.setenv(
        "XCODE_MIGRATION_DATABASE_URL",
        "postgresql://xcode_owner:xcode_owner@127.0.0.1:1/xcode?connect_timeout=1",
    )
    code = main(["db", "status"])
    out = capsys.readouterr().out
    assert code == 1
    assert out.startswith("cannot connect with XCODE_MIGRATION_DATABASE_URL")
    assert "xcode_owner:xcode_owner" not in out


def test_db_command_needs_only_the_migration_url(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_xcode_env(monkeypatch)
    monkeypatch.setenv("XCODE_ENV", "testing")
    code = main(["db", "status"])
    out = capsys.readouterr().out
    assert code == 2
    assert "XCODE_MIGRATION_DATABASE_URL" in out
    assert "XCODE_DATABASE_URL" not in out
    assert "XCODE_MAIL_BACKEND" not in out
