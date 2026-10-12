from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import pytest
from psycopg.conninfo import conninfo_to_dict
from pydantic import ValidationError

from xcode_api.settings import (
    PIN_ITERATIONS_DEFAULT,
    PIN_ITERATIONS_TESTING,
    Environment,
    Settings,
    SettingsError,
    database_url_keywords,
    env_file_present_but_ignored,
    load_cli_settings,
    load_settings,
)

BASE_PROD = {
    "env": "production",
    "database_url": "postgresql://xcode_app@db:5432/xcode?sslmode=verify-full",
    "auth_signing_key": "x" * 32,
    "allowed_hosts": "api.example.com",
    "cors_origins": "https://app.example.com",
    "mail_backend": "smtp",
    "email_host": "smtp.example.com",
    "email_from": "noreply@example.com",
    "log_format": "json",
}


def _settings(**overrides: object) -> Settings:
    data = {**BASE_PROD, **overrides}
    return Settings(**data)


def _expect_error(variable: str, **overrides: object) -> None:
    with pytest.raises(Exception) as excinfo:
        _settings(**overrides)
    assert variable in str(excinfo.value)


# --- the settings table, one case per rule -------------------------------------------


def test_database_url_required() -> None:
    _expect_error("XCODE_DATABASE_URL", database_url="")


def test_production_requires_verify_full_sslmode() -> None:
    _expect_error("XCODE_DATABASE_URL", database_url="postgresql://xcode_app@db/xcode")


def test_require_sslmode_allowed_with_flag() -> None:
    s = _settings(
        database_url="postgresql://xcode_app@db/xcode?sslmode=require",
        database_allow_require_sslmode=True,
    )
    assert s.is_production


# Each URL must read the same through database_url_keywords as through libpq's own parser
# for every keyword the TLS rule looks at.
LIBPQ_CORPUS = (
    "postgresql://xcode_app@db:5432/xcode?sslmode=verify-full",
    "postgresql://u:p@db.example.com/x?sslmode=verify-full&sslmode=disable",
    "postgresql://u@localhost/x?sslmode=verify-full&ssl%6dode=disable",
    "postgresql://u:p@db.example.com/x?host=/tmp",
    "postgresql://u:p@localhost/x?host=db.example.com",
    "postgres://u:p@localhost/x",
    "postgresql://u:p@[::1]:5432,[2001:db8::1]:5433/x",
    "postgresql://u:p@127.0.0.1:5432,localhost:5433/x?sslmode=disable",
    "postgresql://u:p@%2Fvar%2Frun%2Fpostgresql/x",
    "postgresql://u:p@/x?host=/var/run/postgresql",
    "postgresql://u@localhost/x?hostaddr=10.0.0.5",
    "postgresql://u@db.example.com/x?sslmode=verify-full#frag",
    "postgresql://u@db.example.com/x?sslmode=verify-full+",
    "postgresql://u@localhost/x?service=prod",
    "postgresql:///x",
    "postgresql://u%40corp:p%2Cw@localhost/x",
)
TLS_KEYWORDS = ("host", "hostaddr", "sslmode", "service")


@pytest.mark.parametrize("url", LIBPQ_CORPUS)
def test_the_database_url_is_read_as_libpq_reads_it(url: str) -> None:
    ours = database_url_keywords(url)
    assert ours is not None
    libpq = conninfo_to_dict(url)
    assert {k: ours[k] for k in TLS_KEYWORDS if k in ours} == {
        k: libpq[k] for k in TLS_KEYWORDS if k in libpq
    }


@pytest.fixture
def no_libpq_environment(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    for name in ("PGHOST", "PGHOSTADDR", "PGSERVICE"):
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://xcode_app@localhost/xcode",
        "postgresql://xcode_app@127.0.0.1:5432/xcode?sslmode=disable",
        "postgresql://xcode_app@[::1]/xcode?sslmode=prefer",
        "postgresql://xcode_app@/xcode?host=/var/run/postgresql",
        "postgresql://xcode_app@%2Ftmp/xcode",
        "postgresql://xcode_app@db.example.com/xcode?hostaddr=127.0.0.1",
        "postgresql:///xcode",
    ],
)
@pytest.mark.usefixtures("no_libpq_environment")
def test_production_allows_a_plain_connection_that_never_leaves_the_machine(url: str) -> None:
    assert _settings(database_url=url).is_production


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://xcode_app@db.example.com/xcode?sslmode=disable",
        "postgresql://xcode_app@db.example.com/xcode?sslmode=verify-full&sslmode=disable",
        "postgresql://xcode_app@db.example.com/xcode?sslmode=verify-full&ssl%6dode=disable",
        "postgresql://xcode_app@localhost,db.example.com/xcode",
        "postgresql://xcode_app@localhost/xcode?host=db.example.com",
        "postgresql://xcode_app@localhost/xcode?hostaddr=10.0.0.5",
        "postgresql://xcode_app@localhost/xcode?service=xcode",
        "postgresql://xcode_app@localhost.example.com/xcode",
        "host=localhost dbname=xcode",
    ],
)
@pytest.mark.usefixtures("no_libpq_environment")
def test_production_refuses_a_plain_connection_that_can_leave_the_machine(url: str) -> None:
    _expect_error("XCODE_DATABASE_URL", database_url=url)


@pytest.mark.parametrize(
    ("variable", "value", "url"),
    [
        ("PGHOST", "db.example.com", "postgresql://xcode_app@/xcode"),
        ("PGHOSTADDR", "10.0.0.5", "postgresql://xcode_app@localhost/xcode"),
        ("PGSERVICE", "xcode", "postgresql://xcode_app@localhost/xcode"),
    ],
)
def test_the_libpq_environment_counts_for_what_the_url_leaves_out(
    no_libpq_environment: pytest.MonkeyPatch, variable: str, value: str, url: str
) -> None:
    no_libpq_environment.setenv(variable, value)
    _expect_error("XCODE_DATABASE_URL", database_url=url)


def test_pool_max_below_min_is_refused() -> None:
    _expect_error("XCODE_DATABASE_POOL_MAX", database_pool_min=10, database_pool_max=2)


def test_pool_min_floor() -> None:
    _expect_error("XCODE_DATABASE_POOL_MIN", database_pool_min=0)


def test_operator_length_and_charset() -> None:
    _expect_error("XCODE_OPERATOR", operator="x" * 129)
    _expect_error("XCODE_OPERATOR", operator="bad\x01name")


def test_production_requires_signing_key() -> None:
    _expect_error("XCODE_AUTH_SIGNING_KEY", auth_signing_key="short")


def test_previous_keys_must_be_long_enough() -> None:
    _expect_error("XCODE_AUTH_PREVIOUS_SIGNING_KEYS", auth_previous_signing_keys="short,other")


def test_trust_lifetime_positive_or_empty() -> None:
    _expect_error("XCODE_AUTH_TRUST_LIFETIME_DAYS", auth_trust_lifetime_days=0)
    assert _settings(auth_trust_lifetime_days="").auth_trust_lifetime_days is None


def test_pin_iterations_default_matches_dotnet() -> None:
    assert _settings().auth_pin_iterations == PIN_ITERATIONS_DEFAULT == 210_000


def test_rate_limit_backend_values() -> None:
    _expect_error("XCODE_RATE_LIMIT_BACKEND", rate_limit_backend="redis")


def test_rate_limit_per_minute_positive() -> None:
    _expect_error("XCODE_RATE_LIMIT_AUTH_PER_MINUTE", rate_limit_auth_per_minute=0)


def test_trusted_proxies_must_parse() -> None:
    _expect_error("XCODE_TRUSTED_PROXIES", trusted_proxies="not-an-ip")


def test_trusted_proxies_accepts_cidr() -> None:
    s = _settings(trusted_proxies="10.0.0.0/8,::1")
    assert s.trusted_proxies == ["10.0.0.0/8", "::1"]


def test_cors_wildcard_refused_outside_development() -> None:
    _expect_error("XCODE_CORS_ORIGINS", cors_origins="*")


def test_allowed_hosts_wildcard_refused_in_production() -> None:
    _expect_error("XCODE_ALLOWED_HOSTS", allowed_hosts="*")


def test_mail_backend_values() -> None:
    _expect_error("XCODE_MAIL_BACKEND", mail_backend="sendmail")


def test_smtp_requires_host_and_from() -> None:
    _expect_error("XCODE_EMAIL_HOST", email_host="", email_from="a@b.co")
    _expect_error("XCODE_EMAIL_FROM", email_host="h", email_from="")


def test_log_format_values() -> None:
    _expect_error("XCODE_LOG_FORMAT", log_format="xml")


def test_openapi_default_by_environment() -> None:
    assert _settings().openapi_is_enabled is False
    dev = Settings(
        env="development",
        database_url="postgresql://xcode_app@localhost/xcode",
        mail_backend="log",
    )
    assert dev.openapi_is_enabled is True


@pytest.fixture
def development_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    monkeypatch.chdir(tmp_path)
    for key in list(os.environ):
        if key.startswith("XCODE_"):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("XCODE_ENV", "development")
    monkeypatch.setenv("XCODE_DATABASE_URL", "postgresql://xcode_app@localhost/xcode")
    monkeypatch.setenv("XCODE_MAIL_BACKEND", "log")
    return monkeypatch


@pytest.mark.parametrize(
    ("variable", "value", "field", "expected"),
    [
        (
            "XCODE_DATABASE_OPERATOR_URL",
            "postgresql://xcode_operator@localhost/xcode",
            "database_operator_url",
            "postgresql://xcode_operator@localhost/xcode",
        ),
        ("XCODE_AUTH_ISSUER", "issuer-b", "auth_issuer", "issuer-b"),
        ("XCODE_AUTH_AUDIENCE", "audience-b", "auth_audience", "audience-b"),
        ("XCODE_AUTH_PIN_ITERATIONS", "5000", "auth_pin_iterations", 5000),
        ("XCODE_OPENAPI_ENABLED", "false", "openapi_is_enabled", False),
        ("XCODE_METRICS_ENABLED", "true", "metrics_enabled", True),
        ("XCODE_SHUTDOWN_GRACE_SECONDS", "3", "shutdown_grace_seconds", 3),
    ],
)
def test_each_variable_reaches_its_setting(
    development_environment: pytest.MonkeyPatch,
    variable: str,
    value: str,
    field: str,
    expected: object,
) -> None:
    development_environment.setenv(variable, value)
    assert getattr(load_settings(), field) == expected


@pytest.mark.usefixtures("development_environment")
def test_token_and_runtime_defaults() -> None:
    s = load_settings()
    # The .NET API's Jwt:Issuer and Jwt:Audience (apps/api/appsettings.json).
    assert (s.auth_issuer, s.auth_audience) == ("xcode-api", "xcode-clients")
    assert s.database_operator_url == ""
    assert s.metrics_enabled is False
    assert s.shutdown_grace_seconds == 10


def test_pin_iterations_must_be_positive() -> None:
    _expect_error("XCODE_AUTH_PIN_ITERATIONS", auth_pin_iterations=0)


# --- safety switches (section 11) ----------------------------------------------------


def test_log_mailer_refused_in_production() -> None:
    _expect_error("XCODE_MAIL_BACKEND", mail_backend="log")


def test_development_codes_refused_in_production() -> None:
    _expect_error("XCODE_DEVELOPMENT_CODES", development_codes=True)


def test_development_codes_refused_in_testing() -> None:
    with pytest.raises(Exception) as excinfo:
        Settings.for_tests(development_codes=True)
    assert "XCODE_DEVELOPMENT_CODES" in str(excinfo.value)


def test_development_codes_allowed_in_development() -> None:
    dev = Settings.for_tests(env="development", development_codes=True)
    assert dev.development_codes is True


@pytest.mark.parametrize("seconds", [0, -1])
def test_email_timeout_must_be_positive(seconds: int) -> None:
    _expect_error("XCODE_EMAIL_TIMEOUT_SECONDS", email_timeout_seconds=seconds)


def test_email_timeout_defaults_to_ten_seconds() -> None:
    assert _settings().email_timeout_seconds == 10


def test_email_tls_is_on_by_default() -> None:
    assert _settings().email_tls is True


@pytest.mark.parametrize("host", ["smtp.example.com", "10.0.0.5", "localhost.example.com"])
def test_email_without_tls_is_refused_for_a_relay_on_another_machine(host: str) -> None:
    _expect_error("XCODE_EMAIL_TLS", email_tls=False, email_host=host)


@pytest.mark.parametrize("host", ["127.0.0.1", "::1", "localhost", "LOCALHOST"])
def test_email_without_tls_is_allowed_for_a_relay_on_this_machine(host: str) -> None:
    assert _settings(email_tls=False, email_host=host).email_tls is False


@pytest.mark.parametrize("port", [25, 2525])
def test_an_smtp_port_without_tls_is_refused_at_startup_outside_development(port: int) -> None:
    _expect_error("XCODE_EMAIL_PORT", email_port=port)


def test_any_smtp_port_is_allowed_for_a_relay_on_this_machine_without_tls() -> None:
    assert _settings(email_tls=False, email_host="127.0.0.1", email_port=25).email_port == 25


def test_email_without_tls_is_allowed_for_any_relay_in_development() -> None:
    dev = Settings.for_tests(env="development", email_tls=False, email_host="smtp.example.com")
    assert dev.email_tls is False


def test_test_factory_uses_the_low_documented_pin_iteration_count() -> None:
    assert Settings.for_tests().auth_pin_iterations == PIN_ITERATIONS_TESTING


def test_demo_seed_refused_outside_development() -> None:
    _expect_error("XCODE_DEMO_SEED", demo_seed=True)


def test_auto_migrate_refused_outside_development() -> None:
    _expect_error("XCODE_AUTO_MIGRATE", auto_migrate=True)


def test_console_log_refused_in_production() -> None:
    _expect_error("XCODE_LOG_FORMAT", log_format="console")


# --- several violations reported at once ---------------------------------------------


def test_many_violations_reported_together() -> None:
    with pytest.raises(Exception) as excinfo:
        Settings(
            env="production",
            database_url="postgresql://xcode_app@db/xcode",
            auth_signing_key="short",
            allowed_hosts="*",
            mail_backend="log",
        )
    message = str(excinfo.value)
    for variable in (
        "XCODE_DATABASE_URL",
        "XCODE_AUTH_SIGNING_KEY",
        "XCODE_ALLOWED_HOSTS",
        "XCODE_MAIL_BACKEND",
    ):
        assert variable in message


# --- .env loaded only in development --------------------------------------------------


def test_env_file_loaded_in_development(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / ".env").write_text(
        "XCODE_ENV=development\n"
        "XCODE_DATABASE_URL=postgresql://xcode_app@localhost/xcode\n"
        "XCODE_MAIL_BACKEND=log\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    for key in list(os.environ):
        if key.startswith("XCODE_"):
            monkeypatch.delenv(key, raising=False)
    s = load_settings()
    assert s.env is Environment.development
    assert "localhost" in s.database_url


def test_env_file_ignored_outside_development(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".env").write_text(
        "XCODE_DATABASE_URL=postgresql://should-not-be-read/xcode\n", encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)
    for key in list(os.environ):
        if key.startswith("XCODE_"):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("XCODE_ENV", "testing")
    with pytest.raises(SettingsError) as excinfo:
        load_settings()
    assert "XCODE_DATABASE_URL" in str(excinfo.value)


# --- the summary never contains a secret ---------------------------------------------


def test_summary_hides_secrets() -> None:
    secret = "k" * 40
    password = "p" * 20
    s = _settings(
        auth_signing_key=secret,
        email_password=password,
        database_url="postgresql://user:dbpass@db:5432/xcode?sslmode=verify-full",
    )
    summary = s.summary()
    blob = repr(summary)
    assert secret not in blob
    assert password not in blob
    assert "dbpass" not in blob
    assert summary["auth_signing_key"] == "<set>"
    assert summary["email_password"] == "<set>"


def test_summary_counts_previous_keys() -> None:
    s = _settings(auth_previous_signing_keys=f"{'a' * 32},{'b' * 32}")
    assert s.summary()["auth_previous_signing_keys_count"] == 2


def test_every_setting_is_in_env_example() -> None:
    fields = {f"XCODE_{name.upper()}" for name in Settings.model_fields}
    env_example = (Path(__file__).resolve().parents[2] / ".env.example").read_text(encoding="utf-8")
    declared = {
        line.split("=", 1)[0].strip()
        for line in env_example.splitlines()
        if line.strip() and not line.strip().startswith("#")
    }
    assert fields == declared


def test_for_tests_defaults() -> None:
    s = Settings.for_tests()
    assert s.env is Environment.testing
    assert s.mail_backend == "log"
    assert s.log_format == "console"
    assert s.rate_limit_auth_per_minute == 10000
    assert s.openapi_is_enabled is True
    assert len(s.auth_signing_key) >= 32


# --- log level, console in testing, generated signing key ------------------------------


def test_log_level_validated_and_normalised() -> None:
    _expect_error("XCODE_LOG_LEVEL", log_level="verbose")
    assert _settings(log_level="debug").log_level == "DEBUG"


def test_console_log_allowed_in_testing() -> None:
    assert Settings.for_tests(log_format="console").log_format == "console"


def test_signing_key_generated_outside_production_when_empty() -> None:
    generated = Settings.for_tests(auth_signing_key="")
    assert len(generated.auth_signing_key) >= 32
    assert generated.auth_signing_key_generated is True
    assert generated.summary()["auth_signing_key"] == "<generated>"
    configured = Settings.for_tests()
    assert configured.auth_signing_key_generated is False
    assert configured.summary()["auth_signing_key"] == "<set>"


def test_production_never_generates_a_signing_key() -> None:
    _expect_error("XCODE_AUTH_SIGNING_KEY", auth_signing_key="")


# --- CliSettings: what the db and operator commands need ---------------------------------


def _clear_xcode_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in list(os.environ):
        if key.startswith("XCODE_"):
            monkeypatch.delenv(key, raising=False)


def test_cli_settings_need_only_env_url_and_operator(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_xcode_env(monkeypatch)
    monkeypatch.setenv("XCODE_ENV", "production")
    monkeypatch.setenv("XCODE_MIGRATION_DATABASE_URL", "postgresql://xcode_owner@db/xcode")
    s = load_cli_settings()
    assert s.env is Environment.production
    assert s.migration_database_url.endswith("/xcode")
    assert s.database_operator_url == ""


def test_cli_settings_require_env_and_validate_operator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_xcode_env(monkeypatch)
    with pytest.raises(SettingsError) as missing:
        load_cli_settings()
    assert "XCODE_ENV" in str(missing.value)
    monkeypatch.setenv("XCODE_ENV", "testing")
    monkeypatch.setenv("XCODE_OPERATOR", "x" * 129)
    with pytest.raises(SettingsError) as bad_operator:
        load_cli_settings()
    assert "XCODE_OPERATOR" in str(bad_operator.value)


def test_env_file_present_but_ignored(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / ".env").write_text("XCODE_ENV=development\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    _clear_xcode_env(monkeypatch)
    monkeypatch.setenv("XCODE_ENV", "testing")
    assert env_file_present_but_ignored() is True
    monkeypatch.setenv("XCODE_ENV", "development")
    assert env_file_present_but_ignored() is False


# --- a database password is hidden wherever the URL carries it ------------------------


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://xcode_app@db.example.com/xcode?sslmode=verify-full&password=s3cr3t-pass",
        "postgresql://xcode_app@db.example.com/xcode?sslmode=verify-full&pass%77ord=s3cr3t-pass",
        "postgresql://xcode_app@db.example.com/xcode?sslpassword=s3cr3t-pass&sslmode=verify-full",
        "postgresql://xcode_app:s3cr3t/pass@db.example.com/xcode?sslmode=verify-full",
    ],
)
def test_summary_hides_a_password_in_the_query_of_a_database_url(url: str) -> None:
    s = _settings(database_url=url, migration_database_url=url, database_operator_url=url)
    blob = repr(s.summary())
    assert "s3cr3t" not in blob
    assert "pass@" not in blob


def test_summary_keeps_the_host_and_sslmode_of_a_database_url() -> None:
    url = "postgresql://xcode_app:dbpass@db.example.com:5432/xcode?sslmode=verify-full&password=x"
    s = _settings(database_url=url)
    assert s.summary()["database_url"] == (
        "postgresql://db.example.com:5432/xcode?sslmode=verify-full&password=<set>"
    )


def test_summary_hides_a_key_value_connection_string() -> None:
    conninfo = "host=db.example.com user=xcode_owner password=s3cr3t-pass dbname=xcode"
    s = _settings(migration_database_url=conninfo, database_operator_url=conninfo)
    summary = s.summary()
    assert "s3cr3t-pass" not in repr(summary)
    assert summary["migration_database_url"] == "<set>"


# --- the auth rate limit of the testing environment ------------------------------------


def test_testing_environment_defaults_the_auth_rate_limit_to_10000() -> None:
    s = Settings(
        env="testing", database_url="postgresql://xcode_app@localhost/xcode", mail_backend="log"
    )
    assert s.rate_limit_auth_per_minute == 10_000


def test_an_explicit_auth_rate_limit_wins_in_testing() -> None:
    s = Settings(
        env="testing",
        database_url="postgresql://xcode_app@localhost/xcode",
        mail_backend="log",
        rate_limit_auth_per_minute=30,
    )
    assert s.rate_limit_auth_per_minute == 30


def test_other_environments_default_the_auth_rate_limit_to_30() -> None:
    assert _settings().rate_limit_auth_per_minute == 30


def test_pin_throttles_are_positive() -> None:
    _expect_error("XCODE_RATE_LIMIT_PIN_PER_ADDRESS", rate_limit_pin_per_address=0)
    _expect_error("XCODE_RATE_LIMIT_PIN_PER_DEVICE", rate_limit_pin_per_device=-1)


def test_pin_throttles_default_to_20_per_address_and_10_per_device() -> None:
    s = _settings()
    assert (s.rate_limit_pin_per_address, s.rate_limit_pin_per_device) == (20, 10)


def test_testing_environment_lifts_the_pin_throttles_unless_set() -> None:
    lifted = Settings(
        env="testing", database_url="postgresql://xcode_app@localhost/xcode", mail_backend="log"
    )
    assert (lifted.rate_limit_pin_per_address, lifted.rate_limit_pin_per_device) == (
        10_000,
        10_000,
    )
    chosen = Settings.for_tests(rate_limit_pin_per_address=20, rate_limit_pin_per_device=10)
    assert (chosen.rate_limit_pin_per_address, chosen.rate_limit_pin_per_device) == (20, 10)


# --- the settings matrix: docs/08 sections 1 and 11, .env.example and Settings agree ------

PROJECT = Path(__file__).resolve().parents[2]
_VARIABLE_ROW = re.compile(r"^\| `(XCODE_[A-Z_]+)` \|", re.MULTILINE)
_SWITCH_ROW = re.compile(r"^\| [^|]+ \| `(XCODE_[A-Z_]+)=([^`]+)` \| ([^|]+) \|$", re.MULTILINE)
_ENV_KEY = re.compile(r"^(XCODE_[A-Z_]+)=", re.MULTILINE)
ENVIRONMENTS = ("development", "testing", "production")


def _operability_section(number: int) -> str:
    text = (PROJECT / "docs" / "08-operability.md").read_text("utf-8").replace("\r", "")
    return text.split(f"\n## {number}. ", 1)[1].split("\n## ", 1)[0]


def _settings_variables() -> set[str]:
    return {f"XCODE_{name.upper()}" for name in Settings.model_fields}


def test_the_document_the_env_example_and_settings_name_the_same_variables() -> None:
    documented = set(_VARIABLE_ROW.findall(_operability_section(1)))
    example = set(_ENV_KEY.findall((PROJECT / ".env.example").read_text("utf-8")))
    assert documented == _settings_variables()
    assert example == _settings_variables()


def _base(env: str) -> dict[str, Any]:
    base: dict[str, Any] = {
        "env": env,
        "database_url": "postgresql://xcode_app@db.example.com/xcode?sslmode=verify-full",
        "migration_database_url": "postgresql://xcode_owner@localhost/xcode",
        "database_operator_url": "postgresql://xcode_operator@localhost/xcode",
        "auth_signing_key": "matrix-signing-key-0123456789-abcdefghij",
        "mail_backend": "smtp",
        "email_host": "smtp.example.com",
        "email_from": "noreply@example.com",
        "log_format": "json",
        "allowed_hosts": ["api.example.com"],
        "cors_origins": ["https://web.example.com"],
    }
    return base


def _value(field: str, text: str) -> Any:
    if text in ("true", "false"):
        return text == "true"
    if field in ("cors_origins", "allowed_hosts"):
        return [text]
    return text


SWITCHES = [
    (variable, value, env, env in allowed)
    for variable, value, allowed in _SWITCH_ROW.findall(_operability_section(11))
    for env in ENVIRONMENTS
]


def test_every_switch_of_the_table_is_a_setting() -> None:
    assert len({variable for variable, *_ in SWITCHES}) == 8
    assert {variable for variable, *_ in SWITCHES} <= _settings_variables()


@pytest.mark.parametrize(("variable", "value", "env", "allowed"), SWITCHES)
def test_every_safety_switch_is_refused_outside_its_environments(
    variable: str, value: str, env: str, allowed: bool
) -> None:
    field = variable.removeprefix("XCODE_").lower()
    overrides = _base(env)
    overrides[field] = _value(field, value)
    if allowed:
        settings = Settings(_env_file=None, **overrides)
        assert getattr(settings, field) == overrides[field]
        return
    with pytest.raises(ValidationError) as excinfo:
        Settings(_env_file=None, **overrides)
    assert variable in str(excinfo.value)


@pytest.mark.parametrize(
    ("switch", "needs"),
    [
        ("demo_seed", "XCODE_DATABASE_OPERATOR_URL"),
        ("auto_migrate", "XCODE_MIGRATION_DATABASE_URL"),
    ],
)
def test_a_development_startup_step_needs_its_own_connection(switch: str, needs: str) -> None:
    overrides = _base("development")
    overrides[switch] = True
    overrides[needs.removeprefix("XCODE_").lower()] = ""
    with pytest.raises(ValidationError) as excinfo:
        Settings(_env_file=None, **overrides)
    assert needs in str(excinfo.value)


@pytest.mark.parametrize(
    ("host", "allowed"),
    [
        ("127.0.0.1", True),
        ("::1", True),
        ("localhost", True),
        ("127.0.0.53", True),
        ("smtp.example.com", False),
        ("relay.localhost.example.com", False),
        ("127.0.0.1,smtp.example.com", False),
        ("localhost,127.0.0.1", False),
        ("10.0.0.5", False),
    ],
)
def test_plaintext_mail_in_production_only_to_a_loopback_relay(host: str, allowed: bool) -> None:
    overrides = _base("production")
    overrides.update(email_tls=False, email_host=host, email_port=25)
    if allowed:
        assert Settings(_env_file=None, **overrides).email_tls is False
        return
    with pytest.raises(ValidationError) as excinfo:
        Settings(_env_file=None, **overrides)
    assert "XCODE_EMAIL_TLS" in str(excinfo.value)
