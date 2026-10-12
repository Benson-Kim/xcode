"""XCODE_* settings (docs/08-operability.md section 1).

``Settings`` is what the API process validates: every violation is collected and reported
at once, and ``summary()`` never contains a secret. ``CliSettings`` is the much smaller set
the ``db`` and operator commands need (the environment, their connection URL and the
operator name), so a migration job never has to carry the API's secrets just to pass
validation.
"""

from __future__ import annotations

import ipaddress
import os
import secrets
from collections.abc import Mapping
from enum import StrEnum
from functools import cached_property
from pathlib import Path
from typing import Annotated, Any, Self
from urllib.parse import unquote

from pydantic import Field, PrivateAttr, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# PBKDF2 iteration count carried over from the .NET Security.cs; changing it is a migration.
PIN_ITERATIONS_DEFAULT = 210_000
# The test factory's count: the real algorithm, cheap enough for every test container.
PIN_ITERATIONS_TESTING = 1_000

_SECRET_UNSET = "<unset>"  # noqa: S105 - a display marker, not a credential
_SECRET_SET = "<set>"  # noqa: S105 - a display marker, not a credential
_SECRET_GENERATED = "<generated>"  # noqa: S105 - a display marker, not a credential

RATE_LIMIT_AUTH_PER_MINUTE_TESTING = 10_000
RATE_LIMIT_PIN_TESTING = 10_000

LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
OPERATOR_MAX_LENGTH = 128


class Environment(StrEnum):
    development = "development"
    testing = "testing"
    production = "production"


class SettingsError(Exception):
    """Raised by :func:`load_settings` with every violation message collected."""

    def __init__(self, messages: list[str]) -> None:
        self.messages = messages
        super().__init__("; ".join(messages))


def _split_list(value: Any) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [item.strip() for item in str(value).split(",") if item.strip()]


def _operator_errors(operator: str) -> list[str]:
    errors: list[str] = []
    if len(operator) > OPERATOR_MAX_LENGTH:
        errors.append(f"XCODE_OPERATOR must be at most {OPERATOR_MAX_LENGTH} characters")
    if operator and not all(0x20 <= ord(ch) <= 0x7E for ch in operator):
        errors.append("XCODE_OPERATOR must be printable ASCII")
    return errors


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="XCODE_",
        extra="ignore",
        case_sensitive=False,
    )

    env: Environment

    database_url: str = ""
    migration_database_url: str = ""
    database_operator_url: str = ""
    database_pool_min: int = 2
    database_pool_max: int = 10
    database_allow_require_sslmode: bool = False

    auth_signing_key: str = ""
    auth_previous_signing_keys: Annotated[list[str], NoDecode] = Field(default_factory=list)
    auth_issuer: str = "xcode-api"
    auth_audience: str = "xcode-clients"
    auth_trust_lifetime_days: int | None = None
    auth_pin_iterations: int = PIN_ITERATIONS_DEFAULT

    rate_limit_backend: str = "memory"
    rate_limit_auth_per_minute: int = 30
    rate_limit_pin_per_address: int = 20
    rate_limit_pin_per_device: int = 10

    trusted_proxies: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["127.0.0.1", "::1"]
    )
    cors_origins: Annotated[list[str], NoDecode] = Field(default_factory=list)
    allowed_hosts: Annotated[list[str], NoDecode] = Field(default_factory=lambda: ["*"])

    mail_backend: str = "smtp"
    email_host: str = ""
    email_port: int = 587
    email_from: str = ""
    email_username: str = ""
    email_password: str = ""
    email_timeout_seconds: int = 10
    email_tls: bool = True

    log_format: str = "json"
    log_level: str = "INFO"

    development_codes: bool = False
    demo_seed: bool = False
    auto_migrate: bool = False
    openapi_enabled: bool | None = None
    metrics_enabled: bool = False
    shutdown_grace_seconds: int = 10
    operator: str = ""

    _auth_signing_key_generated: bool = PrivateAttr(default=False)

    # --- list coercion from comma-separated environment values -----------------------

    @field_validator(
        "auth_previous_signing_keys",
        "trusted_proxies",
        "cors_origins",
        "allowed_hosts",
        mode="before",
    )
    @classmethod
    def _coerce_list(cls, value: Any) -> list[str]:
        return _split_list(value)

    @field_validator("auth_trust_lifetime_days", mode="before")
    @classmethod
    def _coerce_optional_int(cls, value: Any) -> Any:
        if value is None or value == "":
            return None
        return value

    @field_validator("openapi_enabled", mode="before")
    @classmethod
    def _coerce_optional_bool(cls, value: Any) -> Any:
        if value is None or value == "":
            return None
        return value

    @field_validator("log_level", mode="before")
    @classmethod
    def _normalise_log_level(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip().upper()
        return value

    # --- cross-field validation; collects every violation ----------------------------

    @model_validator(mode="after")
    def _validate(self) -> Self:
        if (
            self.env is Environment.testing
            and "rate_limit_auth_per_minute" not in self.model_fields_set
        ):
            self.rate_limit_auth_per_minute = RATE_LIMIT_AUTH_PER_MINUTE_TESTING
        if self.env is Environment.testing:
            for name in ("rate_limit_pin_per_address", "rate_limit_pin_per_device"):
                if name not in self.model_fields_set:
                    setattr(self, name, RATE_LIMIT_PIN_TESTING)
        errors: list[str] = []
        self._check_database(errors)
        self._check_pool(errors)
        self._check_auth(errors)
        self._check_rate_limit(errors)
        self._check_proxies(errors)
        self._check_origins_and_hosts(errors)
        self._check_mail(errors)
        self._check_logging(errors)
        self._check_safety_switches(errors)
        errors.extend(_operator_errors(self.operator))
        if errors:
            raise ValueError("\n".join(errors))
        if not self.auth_signing_key:
            # Development and testing get a random key per process, as the .NET API did;
            # tokens then do not survive a restart, which is the documented behaviour.
            self.auth_signing_key = secrets.token_urlsafe(32)
            self._auth_signing_key_generated = True
        return self

    @property
    def is_development(self) -> bool:
        return self.env is Environment.development

    @property
    def is_testing(self) -> bool:
        return self.env is Environment.testing

    @property
    def is_production(self) -> bool:
        return self.env is Environment.production

    @cached_property
    def openapi_is_enabled(self) -> bool:
        if self.openapi_enabled is not None:
            return self.openapi_enabled
        return self.env in (Environment.development, Environment.testing)

    @property
    def auth_signing_key_generated(self) -> bool:
        """True when the key was generated for this process because none was configured."""
        return self._auth_signing_key_generated

    def _check_database(self, errors: list[str]) -> None:
        if not self.database_url:
            errors.append("XCODE_DATABASE_URL is required")
            return
        if self.env is Environment.production:
            keywords = database_url_keywords(self.database_url)
            sslmode = None if keywords is None else keywords.get("sslmode")
            if sslmode == "verify-full":
                return
            if sslmode == "require" and self.database_allow_require_sslmode:
                return
            if keywords is not None and connects_locally(keywords, os.environ):
                return
            errors.append(
                "XCODE_DATABASE_URL must use sslmode=verify-full in production "
                "(or sslmode=require with XCODE_DATABASE_ALLOW_REQUIRE_SSLMODE=true), "
                "unless every host it reaches is a Unix socket or the loopback interface"
            )

    def _check_pool(self, errors: list[str]) -> None:
        if self.database_pool_min < 1:
            errors.append("XCODE_DATABASE_POOL_MIN must be at least 1")
        if self.database_pool_max < 1:
            errors.append("XCODE_DATABASE_POOL_MAX must be at least 1")
        if self.database_pool_max < self.database_pool_min:
            errors.append(
                "XCODE_DATABASE_POOL_MAX must be greater than or equal to XCODE_DATABASE_POOL_MIN"
            )

    def _check_auth(self, errors: list[str]) -> None:
        needs_key = self.env is Environment.production
        if needs_key and len(self.auth_signing_key.encode("utf-8")) < 32:
            errors.append("XCODE_AUTH_SIGNING_KEY must be at least 32 bytes in production")
        elif self.auth_signing_key and len(self.auth_signing_key.encode("utf-8")) < 32:
            errors.append("XCODE_AUTH_SIGNING_KEY must be at least 32 bytes when set")
        for key in self.auth_previous_signing_keys:
            if len(key.encode("utf-8")) < 32:
                errors.append(
                    "every XCODE_AUTH_PREVIOUS_SIGNING_KEYS entry must be at least 32 bytes"
                )
                break
        if self.auth_trust_lifetime_days is not None and self.auth_trust_lifetime_days <= 0:
            errors.append("XCODE_AUTH_TRUST_LIFETIME_DAYS must be positive or empty")
        if self.auth_pin_iterations <= 0:
            errors.append("XCODE_AUTH_PIN_ITERATIONS must be positive")

    def _check_rate_limit(self, errors: list[str]) -> None:
        if self.rate_limit_backend not in ("memory", "postgres"):
            errors.append("XCODE_RATE_LIMIT_BACKEND must be memory or postgres")
        if self.rate_limit_auth_per_minute <= 0:
            errors.append("XCODE_RATE_LIMIT_AUTH_PER_MINUTE must be positive")
        if self.rate_limit_pin_per_address <= 0:
            errors.append("XCODE_RATE_LIMIT_PIN_PER_ADDRESS must be positive")
        if self.rate_limit_pin_per_device <= 0:
            errors.append("XCODE_RATE_LIMIT_PIN_PER_DEVICE must be positive")

    def _check_proxies(self, errors: list[str]) -> None:
        for proxy in self.trusted_proxies:
            try:
                ipaddress.ip_network(proxy, strict=False)
            except ValueError:
                errors.append(
                    f"XCODE_TRUSTED_PROXIES entry is not an IP address or network: {proxy}"
                )

    def _check_origins_and_hosts(self, errors: list[str]) -> None:
        if self.env is not Environment.development and "*" in self.cors_origins:
            errors.append("XCODE_CORS_ORIGINS must not be * outside development")
        if self.env is Environment.production:
            if not self.allowed_hosts or "*" in self.allowed_hosts:
                errors.append("XCODE_ALLOWED_HOSTS must list real hosts in production (no *)")

    def _check_mail(self, errors: list[str]) -> None:
        if self.mail_backend not in ("log", "smtp"):
            errors.append("XCODE_MAIL_BACKEND must be log or smtp")
        if self.mail_backend == "log" and self.env is Environment.production:
            errors.append("XCODE_MAIL_BACKEND=log is refused in production")
        if self.mail_backend == "smtp":
            if not self.email_host:
                errors.append("XCODE_EMAIL_HOST is required when XCODE_MAIL_BACKEND=smtp")
            if not self.email_from:
                errors.append("XCODE_EMAIL_FROM is required when XCODE_MAIL_BACKEND=smtp")
        if self.email_timeout_seconds <= 0:
            errors.append("XCODE_EMAIL_TIMEOUT_SECONDS must be positive")
        if (
            self.mail_backend == "smtp"
            and self.email_tls
            and self.email_port not in (465, 587)
            and self.env is not Environment.development
        ):
            errors.append(
                "XCODE_EMAIL_PORT must be 465 or 587 outside development "
                "(any port only with XCODE_EMAIL_TLS=false to a relay on this machine)"
            )
        if (
            not self.email_tls
            and self.env is not Environment.development
            and not is_local_host(self.email_host)
        ):
            errors.append(
                "XCODE_EMAIL_TLS=false is allowed outside development only for a relay on this "
                "machine (localhost or a loopback address)"
            )

    def _check_logging(self, errors: list[str]) -> None:
        if self.log_format not in ("console", "json"):
            errors.append("XCODE_LOG_FORMAT must be console or json")
        if self.log_format == "console" and self.env is Environment.production:
            errors.append("XCODE_LOG_FORMAT=console is not allowed in production")
        if self.log_level not in LOG_LEVELS:
            errors.append("XCODE_LOG_LEVEL must be one of " + ", ".join(LOG_LEVELS))

    def _check_safety_switches(self, errors: list[str]) -> None:
        if self.development_codes and self.env is not Environment.development:
            errors.append("XCODE_DEVELOPMENT_CODES=true is refused unless XCODE_ENV is development")
        if self.demo_seed and self.env is not Environment.development:
            errors.append("XCODE_DEMO_SEED=true is refused unless XCODE_ENV is development")
        if self.auto_migrate and self.env is not Environment.development:
            errors.append("XCODE_AUTO_MIGRATE=true is refused unless XCODE_ENV is development")
        if self.auto_migrate and not self.migration_database_url:
            errors.append("XCODE_MIGRATION_DATABASE_URL is required when XCODE_AUTO_MIGRATE=true")
        if self.demo_seed and not self.database_operator_url:
            errors.append("XCODE_DATABASE_OPERATOR_URL is required when XCODE_DEMO_SEED=true")
        if self.shutdown_grace_seconds < 0:
            errors.append("XCODE_SHUTDOWN_GRACE_SECONDS must not be negative")

    # --- test factory and startup summary --------------------------------------------

    @classmethod
    def for_tests(cls, **overrides: Any) -> Settings:
        base: dict[str, Any] = {
            "env": Environment.testing,
            "database_url": "postgresql://xcode_app@localhost:5432/xcode_test",
            "auth_signing_key": secrets.token_urlsafe(32),
            "mail_backend": "log",
            "log_format": "console",
            "rate_limit_auth_per_minute": RATE_LIMIT_AUTH_PER_MINUTE_TESTING,
            "rate_limit_pin_per_address": RATE_LIMIT_PIN_TESTING,
            "rate_limit_pin_per_device": RATE_LIMIT_PIN_TESTING,
            "openapi_enabled": True,
            "auth_pin_iterations": PIN_ITERATIONS_TESTING,
        }
        base.update(overrides)
        return cls(**base)

    def summary(self) -> dict[str, Any]:
        """A dict for the startup log: secrets collapsed, previous keys shown as a count."""
        return {
            "env": self.env.value,
            "database_url": _redact_url(self.database_url),
            "migration_database_url": _redact_url(self.migration_database_url),
            "database_operator_url": _redact_url(self.database_operator_url),
            "database_pool_min": self.database_pool_min,
            "database_pool_max": self.database_pool_max,
            "database_allow_require_sslmode": self.database_allow_require_sslmode,
            "auth_signing_key": _signing_key_marker(self),
            "auth_previous_signing_keys_count": len(self.auth_previous_signing_keys),
            "auth_issuer": self.auth_issuer,
            "auth_audience": self.auth_audience,
            "auth_trust_lifetime_days": self.auth_trust_lifetime_days,
            "auth_pin_iterations": self.auth_pin_iterations,
            "rate_limit_backend": self.rate_limit_backend,
            "rate_limit_auth_per_minute": self.rate_limit_auth_per_minute,
            "rate_limit_pin_per_address": self.rate_limit_pin_per_address,
            "rate_limit_pin_per_device": self.rate_limit_pin_per_device,
            "trusted_proxies": list(self.trusted_proxies),
            "cors_origins": list(self.cors_origins),
            "allowed_hosts": list(self.allowed_hosts),
            "mail_backend": self.mail_backend,
            "email_host": self.email_host,
            "email_port": self.email_port,
            "email_from": self.email_from,
            "email_username": self.email_username,
            "email_password": _SECRET_SET if self.email_password else _SECRET_UNSET,
            "email_timeout_seconds": self.email_timeout_seconds,
            "email_tls": self.email_tls,
            "log_format": self.log_format,
            "log_level": self.log_level,
            "development_codes": self.development_codes,
            "demo_seed": self.demo_seed,
            "auto_migrate": self.auto_migrate,
            "openapi_enabled": self.openapi_is_enabled,
            "metrics_enabled": self.metrics_enabled,
            "shutdown_grace_seconds": self.shutdown_grace_seconds,
            "operator": self.operator,
        }


def _signing_key_marker(settings: Settings) -> str:
    if settings.auth_signing_key_generated:
        return _SECRET_GENERATED
    return _SECRET_SET if settings.auth_signing_key else _SECRET_UNSET


def database_url_keywords(url: str) -> dict[str, str] | None:
    """The keywords a ``postgresql://`` URL sets, read as libpq reads them: the query
    overrides the hosts of the authority, keys and values are percent-decoded, a repeated key
    keeps its last value, and ``#`` and ``+`` are literal. ``None`` for any other form (a
    key/value string, another scheme), which the TLS rule then treats as unprotected. The
    driver is outside this module's layer, so ``tests/unit/test_settings.py`` holds this
    reading against libpq's own parser."""
    for scheme in ("postgresql://", "postgres://"):
        if url.startswith(scheme):
            rest = url.removeprefix(scheme)
            break
    else:
        return None
    location, _, query = rest.partition("?")
    authority = location.split("/", 1)[0].rpartition("@")[2]
    hosts = [_host_of(entry) for entry in authority.split(",")]
    keywords: dict[str, str] = {}
    if any(hosts):
        keywords["host"] = ",".join(hosts)
    for pair in query.split("&") if query else ():
        key, _, value = pair.partition("=")
        keywords[unquote(key)] = unquote(value)
    return keywords


def _host_of(entry: str) -> str:
    if entry.startswith("["):
        return entry[1:].split("]", 1)[0]
    return unquote(entry.split(":", 1)[0])


def connects_locally(keywords: Mapping[str, str], environ: Mapping[str, str]) -> bool:
    """True when every address libpq may reach is a Unix socket or the loopback interface,
    traffic that never leaves the machine (a database beside the API on one host). What the
    URL leaves out libpq takes from ``PGHOST`` and ``PGHOSTADDR``, so they are read the same
    way; a service file may supply either, so a named service never counts as local. A
    numeric ``hostaddr`` decides where libpq connects, whatever the host name says."""
    if keywords.get("service") or environ.get("PGSERVICE"):
        return False
    hosts = _listed(keywords.get("host", environ.get("PGHOST", "")))
    addresses = _listed(keywords.get("hostaddr", environ.get("PGHOSTADDR", "")))
    if any(address and not _is_loopback(address) for address in addresses):
        return False
    if addresses and all(addresses):
        return True
    return all(_is_local_host(host) for host in hosts)


def _listed(value: str) -> list[str]:
    return [part.strip() for part in value.split(",")] if value else []


def _is_local_host(host: str) -> bool:
    # Empty is libpq's default (the Unix socket, or localhost on Windows); "/" starts a
    # socket directory and "@" an abstract socket.
    if not host or host.startswith(("/", "@")) or host.lower() == "localhost":
        return True
    return _is_loopback(host)


def is_local_host(host: str) -> bool:
    """``localhost`` or a loopback address literal: a server on this machine."""
    return host.lower() == "localhost" or _is_loopback(host)


def _is_loopback(address: str) -> bool:
    try:
        return ipaddress.ip_address(address).is_loopback
    except ValueError:
        return False


_URL_SECRET_KEYWORDS = frozenset({"password", "sslpassword"})


def _redact_url(url: str) -> str:
    """The URL without its userinfo and with the value of every password keyword libpq reads
    from the query replaced; any other form (a key/value string) is shown only as set."""
    if not url:
        return _SECRET_UNSET
    if not url.startswith(("postgresql://", "postgres://")):
        return _SECRET_SET
    scheme, _, rest = url.partition("://")
    location, question, query = rest.partition("?")
    pairs = []
    for pair in query.split("&") if query else ():
        key, equals, _ = pair.partition("=")
        hidden = unquote(key) in _URL_SECRET_KEYWORDS
        pairs.append(f"{key}={_SECRET_SET}" if hidden and equals else pair)
    return f"{scheme}://{location.rpartition('@')[2]}{question}{'&'.join(pairs)}"


def load_settings(**overrides: Any) -> Settings:
    """Load settings from the environment, collecting every violation.

    ``.env`` is read only when the resolved environment is development; in any other
    environment a present ``.env`` is ignored (the warning is logged once logging is
    configured). Raises :class:`SettingsError` listing every bad or missing variable.
    """
    env_file = ".env" if _should_read_env_file() else None
    try:
        return Settings(_env_file=env_file, **overrides)
    except ValidationError as exc:
        raise SettingsError(_messages_from(exc)) from exc


class CliSettings(BaseSettings):
    """What the ``db`` and operator commands need: nothing of the API's own configuration.

    ``XCODE_MIGRATION_DATABASE_URL`` (role ``xcode_owner``) serves the ``db`` commands and
    ``XCODE_DATABASE_OPERATOR_URL`` (role ``xcode_operator``) the user and seed commands;
    each command checks that the URL it needs is set. The ``.env`` rule is the same as for
    :class:`Settings`.
    """

    model_config = SettingsConfigDict(
        env_prefix="XCODE_",
        extra="ignore",
        case_sensitive=False,
    )

    env: Environment
    migration_database_url: str = ""
    database_operator_url: str = ""
    operator: str = ""
    auth_pin_iterations: int = PIN_ITERATIONS_DEFAULT

    @model_validator(mode="after")
    def _validate(self) -> Self:
        errors = _operator_errors(self.operator)
        if self.auth_pin_iterations <= 0:
            errors.append("XCODE_AUTH_PIN_ITERATIONS must be positive")
        if errors:
            raise ValueError("\n".join(errors))
        return self

    @property
    def is_development(self) -> bool:
        return self.env is Environment.development


def load_cli_settings(**overrides: Any) -> CliSettings:
    """Load :class:`CliSettings` from the environment; raises :class:`SettingsError`."""
    env_file = ".env" if _should_read_env_file() else None
    try:
        return CliSettings(_env_file=env_file, **overrides)
    except ValidationError as exc:
        raise SettingsError(_messages_from(exc)) from exc


def env_file_present_but_ignored() -> bool:
    """True when a ``.env`` exists but the environment is not development (so it is ignored)."""
    return Path(".env").is_file() and _resolved_env() != "development"


def _should_read_env_file() -> bool:
    return Path(".env").is_file() and _resolved_env() == "development"


def _resolved_env() -> str | None:
    """The environment as the OS sets it, else as a present ``.env`` declares it."""
    os_value = _raw_env_value()
    if os_value:
        return os_value
    return _env_value_from_dotenv()


def _raw_env_value() -> str | None:
    return os.environ.get("XCODE_ENV")


def _env_value_from_dotenv() -> str | None:
    path = Path(".env")
    if not path.is_file():
        return None
    try:
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            name, _, value = line.partition("=")
            if name.strip() == "XCODE_ENV":
                return value.split("#", 1)[0].strip()
    except OSError:
        return None
    return None


def _messages_from(exc: ValidationError) -> list[str]:
    messages: list[str] = []
    for error in exc.errors():
        msg = str(error.get("msg", ""))
        if error.get("type") == "value_error":
            # Our cross-field validator packs several messages into one ValueError.
            for line in msg.removeprefix("Value error, ").splitlines():
                stripped = line.strip()
                if stripped:
                    messages.append(stripped)
            continue
        # A field-level error (missing, wrong type): name the variable it is about.
        loc = [str(part) for part in error.get("loc", ()) if part not in ("__root__",)]
        field = f"XCODE_{loc[0].upper()}" if loc else "settings"
        messages.append(f"{field}: {msg}")
    return messages
