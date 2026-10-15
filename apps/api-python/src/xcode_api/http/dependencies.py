"""FastAPI dependencies: container access, client address, auth rate limiting, and the
bearer principal every authenticated router uses."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.responses import Response
from structlog.contextvars import bind_contextvars

from ..application.auth.resolve_session import ResolvedSession, ResolveSessionCommand
from ..application.caller import Caller
from ..container import Container
from ..domain.errors import SessionInvalid
from ..domain.identity import Principal

AUTH_WINDOW_SECONDS = 60
PIN_WINDOW_SECONDS = 600

# Declares components.securitySchemes.Bearer (http, bearer, JWT) and the operation security;
# a missing or non-bearer header yields None and the uniform 401.
_bearer = HTTPBearer(scheme_name="Bearer", bearerFormat="JWT", auto_error=False)


def container(request: Request) -> Container:
    result: Container = request.app.state.container
    return result


def client_address(request: Request) -> str:
    return getattr(request.state, "client_address", None) or "unknown"


def request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "") or ""


async def current_session(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> ResolvedSession:
    """``Authorization: Bearer`` only: verify the token, resolve the session in the database
    and bind ``actor_id`` and ``organization_id`` to the log context. Any failure raises
    ``SessionInvalid``: 401, empty body, ``WWW-Authenticate: Bearer``."""
    if credentials is None:
        raise SessionInvalid()
    session = await container(request).resolve_session.execute(
        ResolveSessionCommand(credentials.credentials)
    )
    principal = session.principal
    actor_id = str(principal.user_id)
    organization_id = None if principal.organization_id is None else str(principal.organization_id)
    request.state.actor_id = actor_id
    request.state.organization_id = organization_id
    bind_contextvars(actor_id=actor_id, organization_id=organization_id)
    return session


async def current_principal(
    session: Annotated[ResolvedSession, Depends(current_session)],
) -> Principal:
    return session.principal


async def current_caller(
    request: Request, principal: Annotated[Principal, Depends(current_principal)]
) -> Caller:
    """The authenticated caller of a tenant route: the resolved principal and the request id."""
    return Caller(principal, request_id(request))


async def auth_rate_limit(request: Request) -> None:
    """Charge one hit on the ``auth:<address>`` key; a refusal is a 429 with an empty body
    and ``Retry-After``. Applied to every ``/auth`` route and charged once per request: the
    auth router calls it itself for a body FastAPI refuses before any dependency runs."""
    if getattr(request.state, "auth_rate_limit_charged", False):
        return
    request.state.auth_rate_limit_charged = True
    c = container(request)
    settings = c.settings
    address = client_address(request)
    decision = await c.rate_limiter.hit(
        f"auth:{address}",
        settings.rate_limit_auth_per_minute,
        AUTH_WINDOW_SECONDS,
        c.clock.now(),
    )
    if not decision.allowed:
        raise _RateLimited(decision.retry_after_seconds)


async def pin_rate_limit(request: Request, device_id: str, *, address: bool = True) -> None:
    """The PIN throttle of the routes that check a PIN: one hit on ``auth_pin:address:<address>``
    (unless ``address`` is false because the route charged it before authentication) and one
    on ``auth_pin:device:<deviceId>``, each in a ten-minute window; a refusal is the empty 429
    with ``Retry-After``. Charged after the ``auth`` policy and before pre-validation."""
    c = container(request)
    now = c.clock.now()
    if address:
        await _charge(
            c,
            f"auth_pin:address:{client_address(request)}",
            c.settings.rate_limit_pin_per_address,
            now,
        )
    await _charge(c, f"auth_pin:device:{device_id}", c.settings.rate_limit_pin_per_device, now)


async def pin_address_limit(request: Request) -> None:
    """The per-address half of the PIN throttle, as a dependency that runs before
    authentication on the bearer route that checks a PIN."""
    c = container(request)
    await _charge(
        c,
        f"auth_pin:address:{client_address(request)}",
        c.settings.rate_limit_pin_per_address,
        c.clock.now(),
    )


async def _charge(c: Container, key: str, limit: int, now: datetime) -> None:
    decision = await c.rate_limiter.hit(key, limit, PIN_WINDOW_SECONDS, now)
    if not decision.allowed:
        raise _RateLimited(decision.retry_after_seconds)


class _RateLimited(Exception):  # noqa: N818 - internal signal, not an error surfaced to users
    def __init__(self, retry_after_seconds: int) -> None:
        self.retry_after_seconds = retry_after_seconds
        super().__init__("rate limited")


async def rate_limited_handler(request: Request, exc: Exception) -> Response:
    if not isinstance(exc, _RateLimited):  # pragma: no cover - registered per type
        raise exc
    return Response(
        status_code=429,
        headers={"Retry-After": str(exc.retry_after_seconds)},
    )
