"""RFC 9457 problem-details encoder and the exception handlers (docs/06 section 1.6)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import structlog
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from pydantic import ValidationError
from pydantic.alias_generators import to_camel
from starlette.exceptions import HTTPException

from ..application.errors import IntegrityBug, TransientFailure
from ..domain.errors import DomainRefusal, SessionInvalid
from .messages import INVALID_TITLE, message_for
from .responses import JsonResponse
from .schemas.common import ApiModel
from .schemas.pettycash import PettyCashEntryDto
from .schemas.revenue import RevenueCellDto

logger = structlog.get_logger("xcode_api.http")

PROBLEM_CONTENT_TYPE = "application/problem+json"

# Stamped onto error responses directly: Starlette's outermost ServerErrorMiddleware builds
# the 500 response outside our middleware, so the security headers are set here as well.
SECURITY_HEADERS = {
    "cache-control": "no-store",
    "x-content-type-options": "nosniff",
    "referrer-policy": "no-referrer",
}

_GENERIC_500_TITLE = "An error occurred while processing your request."
_TRANSIENT_503_TITLE = "The service is not available right now."

# Framework refusals the .NET API answered with an empty body (docs/06 section 1.6):
# unknown route, wrong method (with ``Allow``), unsupported media type.
_EMPTY_BODY_STATUSES = frozenset({404, 405, 415})

# Refusal members that hold a contract model, written as that model is in a 200 answer.
_EXTENSION_MODELS: Mapping[tuple[str, str], type[ApiModel]] = {
    ("revenue_version_conflict", "current"): RevenueCellDto,
    ("pettycash_entry_changed", "current"): PettyCashEntryDto,
    ("pettycash_already_saved", "current"): PettyCashEntryDto,
}


def request_id_of(request: Request) -> str:
    return getattr(request.state, "request_id", "") or ""


def trace_id_of(request: Request) -> str:
    return getattr(request.state, "trace_id", None) or request_id_of(request)


def problem(
    status: int,
    title: str,
    detail: str | None = None,
    *,
    request_id: str,
    trace_id: str | None = None,
    headers: dict[str, str] | None = None,
    **extensions: Any,
) -> JSONResponse:
    body: dict[str, Any] = {
        "type": "about:blank",
        "title": title,
        "status": status,
    }
    if detail is not None:
        body["detail"] = detail
    body["requestId"] = request_id
    body["traceId"] = trace_id if trace_id is not None else request_id
    body.update(extensions)
    merged = {**SECURITY_HEADERS, "x-request-id": request_id}
    if headers:
        merged.update(headers)
    return JSONResponse(
        status_code=status,
        content=body,
        media_type=PROBLEM_CONTENT_TYPE,
        headers=merged,
    )


async def domain_refusal_handler(request: Request, exc: Exception) -> Response:
    if not isinstance(exc, DomainRefusal):  # pragma: no cover - registered per type
        raise exc
    if isinstance(exc, SessionInvalid):
        # The bearer check never says why: an empty 401 with the challenge (docs/06 1.3).
        headers = {
            **SECURITY_HEADERS,
            "x-request-id": request_id_of(request),
            "www-authenticate": "Bearer",
        }
        return Response(status_code=401, headers=headers)
    # Every refusal answers from the message catalogue; a code it lacks is a bug, not a
    # sentence to improvise, and so is a sentence parameter the routine did not send or a
    # member that does not fit its contract model.
    message = message_for(exc.code)
    parameters = dict(exc.detail)
    try:
        if message is None:
            raise KeyError(exc.code)
        detail = message.sentence(parameters)
        extensions = {
            to_camel(key): _extension(exc.code, key, parameters.get(key))
            for key in message.extensions
        }
    except (KeyError, ValidationError):
        logger.error("request.refusal_without_message", code=exc.code)
        return _server_error(request)
    rid = request_id_of(request)
    if message.plain:
        return JsonResponse(
            {"detail": detail},
            status_code=message.status,
            headers={**SECURITY_HEADERS, "x-request-id": rid},
        )
    return problem(
        message.status,
        message.title or "",
        detail,
        request_id=rid,
        trace_id=trace_id_of(request),
        **extensions,
    )


def _extension(code: str, key: str, value: Any) -> Any:
    model = _EXTENSION_MODELS.get((code, key))
    if model is None or value is None:
        return value
    return model.model_validate(value).model_dump(mode="json", by_alias=True)


async def validation_handler(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, RequestValidationError):  # pragma: no cover - registered per type
        raise exc
    errors: dict[str, list[str]] = {}
    first_message: str | None = None
    for error in exc.errors():
        loc = [str(part) for part in error.get("loc", ()) if part != "body"]
        field = ".".join(loc) or "body"
        message = str(error.get("msg", "invalid"))
        errors.setdefault(field, []).append(message)
        if first_message is None:
            first_message = message
    return problem(
        400,
        INVALID_TITLE,
        first_message,
        request_id=request_id_of(request),
        trace_id=trace_id_of(request),
        errors=errors,
    )


async def http_exception_handler(request: Request, exc: Exception) -> Response:
    """Framework ``HTTPException``: empty body where .NET answered empty (404, 405, 415,
    keeping headers such as ``Allow``), a problem body everywhere else (for example the
    413 raised while a chunked body streams past the cap)."""
    if not isinstance(exc, HTTPException):  # pragma: no cover - registered per type
        raise exc
    rid = request_id_of(request)
    if exc.status_code in _EMPTY_BODY_STATUSES:
        headers = {**SECURITY_HEADERS, "x-request-id": rid, **(exc.headers or {})}
        return Response(status_code=exc.status_code, headers=headers)
    title = exc.detail if isinstance(exc.detail, str) and exc.detail else "Request refused"
    return problem(
        exc.status_code,
        title,
        request_id=rid,
        trace_id=trace_id_of(request),
        headers=dict(exc.headers or {}),
    )


async def transient_handler(request: Request, exc: Exception) -> JSONResponse:
    return problem(
        503,
        _TRANSIENT_503_TITLE,
        request_id=request_id_of(request),
        trace_id=trace_id_of(request),
        headers={"Retry-After": "1"},
    )


async def integrity_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error("request.integrity_bug", exception=type(exc).__name__)
    return _server_error(request)


async def unexpected_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error("request.unhandled", exception=type(exc).__name__)
    return _server_error(request)


def _server_error(request: Request) -> JSONResponse:
    rid = request_id_of(request)
    body = {
        "type": "about:blank",
        "title": _GENERIC_500_TITLE,
        "status": 500,
        "traceId": trace_id_of(request),
        "requestId": rid,
    }
    return JSONResponse(
        status_code=500,
        content=body,
        media_type=PROBLEM_CONTENT_TYPE,
        headers={**SECURITY_HEADERS, "x-request-id": rid},
    )


def register_exception_handlers(app: Any) -> None:
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_handler)
    app.add_exception_handler(DomainRefusal, domain_refusal_handler)
    app.add_exception_handler(TransientFailure, transient_handler)
    app.add_exception_handler(IntegrityBug, integrity_handler)
    app.add_exception_handler(Exception, unexpected_handler)
