"""structlog config: request-scoped context, secret redaction, stdlib bridge; the same
chain serves the API (``configure_logging``) and the CLI (``configure_cli_logging``)."""

from __future__ import annotations

import logging
import sys
from collections.abc import MutableMapping
from typing import Any

import structlog
from structlog.contextvars import bind_contextvars, clear_contextvars, merge_contextvars

from ..settings import Settings

# Any key whose lower-cased name contains one of these is redacted at any depth.
_REDACT_SUBSTRINGS = (
    "pin",
    "code",
    "token",
    "authorization",
    "password",
    "phone",
    "email",
    "secret",
)
_REDACTED = "[redacted]"

# Keys that legitimately contain one of the substrings but carry no secret.
_REDACT_ALLOW = frozenset({"recipient_hash", "code_id"})


def _should_redact(key: str) -> bool:
    if key in _REDACT_ALLOW:
        return False
    lowered = key.lower()
    return any(sub in lowered for sub in _REDACT_SUBSTRINGS)


def _redact(value: Any) -> Any:
    if isinstance(value, MutableMapping):
        return {k: (_REDACTED if _should_redact(str(k)) else _redact(v)) for k, v in value.items()}
    if isinstance(value, dict):
        return {k: (_REDACTED if _should_redact(str(k)) else _redact(v)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return type(value)(_redact(item) for item in value)
    return value


def redact_processor(
    _logger: object, _method: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    for key in list(event_dict.keys()):
        if _should_redact(str(key)):
            event_dict[key] = _REDACTED
        else:
            event_dict[key] = _redact(event_dict[key])
    return event_dict


def configure_logging(settings: Settings) -> None:
    # Settings validation already refuses "console" in production; no silent downgrade here.
    _configure(settings.log_level, console=settings.log_format == "console")


CLI_LOG_LEVEL = "INFO"


def configure_cli_logging() -> None:
    """Logs of the ``db`` and operator commands: console lines at INFO on stderr, so stdout
    carries only what the command prints (ids and counts). ``serve`` reconfigures from
    its settings once they are loaded."""
    _configure(CLI_LOG_LEVEL, console=True)


def _configure(level: str, *, console: bool) -> None:
    use_console = console

    shared_processors: list[structlog.typing.Processor] = [
        merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        redact_processor,
    ]

    renderer: structlog.typing.Processor = (
        structlog.dev.ConsoleRenderer() if use_console else structlog.processors.JSONRenderer()
    )

    # Route structlog through the standard library so every logger (ours, uvicorn, psycopg)
    # shares one handler, one processor chain and one renderer.
    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(level)),
        logger_factory=structlog.stdlib.LoggerFactory(),
        # Not cached: a logger bound once would keep its processor chain for ever, so a
        # later configure (the test suite's log capture) would silently see nothing.
        cache_logger_on_first_use=False,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[structlog.stdlib.ProcessorFormatter.remove_processors_meta, renderer],
    )
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(formatter)
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)

    for name in ("uvicorn", "uvicorn.error", "psycopg"):
        lg = logging.getLogger(name)
        lg.handlers = []
        lg.propagate = True
    # The uvicorn access log is disabled; our middleware logs one line per request.
    access = logging.getLogger("uvicorn.access")
    access.handlers = []
    access.propagate = False
    access.disabled = True


def bind_request_context(
    request_id: str,
    actor_id: str | None = None,
    organization_id: str | None = None,
) -> None:
    bindings: dict[str, Any] = {"request_id": request_id}
    if actor_id is not None:
        bindings["actor_id"] = actor_id
    if organization_id is not None:
        bindings["organization_id"] = organization_id
    bind_contextvars(**bindings)


def clear_request_context() -> None:
    clear_contextvars()
