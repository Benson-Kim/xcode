"""Request id, client address, security headers, request log, and the body cap."""

from __future__ import annotations

import ipaddress
import re
import time
import uuid
from typing import Protocol

import structlog
from starlette.datastructures import MutableHeaders
from starlette.exceptions import HTTPException
from starlette.middleware.gzip import DEFAULT_EXCLUDED_CONTENT_TYPES, GZipMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send
from structlog.contextvars import bind_contextvars, clear_contextvars

from ..application.observability import RuntimeMetrics, active_metrics
from .errors import problem

logger = structlog.get_logger("xcode_api.http")

IpNetwork = ipaddress.IPv4Network | ipaddress.IPv6Network

REQUEST_ID_HEADER = "x-request-id"
BODY_CAP_BYTES = 1024 * 1024

_PRINTABLE_ASCII = re.compile(r"^[\x20-\x7e]{1,128}$")

BODY_TOO_LARGE_TITLE = "Request body too large"


class StatementCounter(Protocol):
    """Per-request routine-call counter the composition root hands to the middleware."""

    def reset(self) -> None: ...

    def current(self) -> int: ...


class RequestMetrics(RuntimeMetrics, Protocol):
    """The app's metrics as the HTTP layer reports to them."""

    def request_finished(self, route: str, method: str, status: int, seconds: float) -> None: ...

    def rate_limit_rejected(self) -> None: ...


UNMATCHED_ROUTE = "unmatched"


class _NoStatementCounter:
    def reset(self) -> None:
        return None

    def current(self) -> int:
        return 0


_SECURITY_HEADERS = {
    "cache-control": "no-store",
    "x-content-type-options": "nosniff",
    "referrer-policy": "no-referrer",
}


def _valid_request_id(value: str | None) -> str:
    if value and _PRINTABLE_ASCII.match(value):
        return value
    return str(uuid.uuid4())


def client_address(scope: Scope, trusted_proxies: list[str]) -> str:
    """Resolve the client address from the peer and ``X-Forwarded-For``.

    ``X-Forwarded-For`` is walked right to left starting from the peer; the first untrusted
    hop wins. The header is ignored entirely when the peer is untrusted.
    """
    client = scope.get("client")
    peer: str | None = client[0] if client else None
    if peer is None:
        return "unknown"

    networks = _parse_networks(trusted_proxies)
    if not _is_trusted(peer, networks):
        return peer

    # Several X-Forwarded-For lines are one list in order (RFC 9110 section 5.3); a proxy
    # that adds its own line instead of appending must not leave the client's line in charge.
    forwarded = ",".join(_header_values(scope, b"x-forwarded-for"))
    if not forwarded:
        return peer
    hops = [hop.strip() for hop in forwarded.split(",") if hop.strip()]
    for hop in reversed(hops):
        if not _is_trusted(hop, networks):
            return hop
    # Every hop was trusted; fall back to the left-most forwarded address.
    return hops[0] if hops else peer


def _parse_networks(values: list[str]) -> list[IpNetwork]:
    networks: list[IpNetwork] = []
    for value in values:
        try:
            networks.append(ipaddress.ip_network(value, strict=False))
        except ValueError:
            continue
    return networks


def _is_trusted(address: str, networks: list[IpNetwork]) -> bool:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    return any(ip in net for net in networks)


def _header(scope: Scope, name: bytes) -> str | None:
    values = _header_values(scope, name)
    return values[0] if values else None


def _header_values(scope: Scope, name: bytes) -> list[str]:
    return [value.decode("latin-1") for key, value in scope.get("headers", []) if key == name]


def _route_template(scope: Scope) -> str:
    route = scope.get("route")
    template = getattr(route, "path_format", None)
    return template if isinstance(template, str) else str(scope.get("path", ""))


class RequestContextMiddleware:
    """Assigns the request id, binds log context, applies security headers, logs one line.

    No ``Server`` header is added (uvicorn's is switched off by ``server_header=False`` in
    the ``serve`` command; this middleware strips any that slips through and never sets
    one). The statement counter is reset per request so the log line carries the number
    of routine calls the request made.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        trusted_proxies: list[str],
        statement_counter: StatementCounter | None = None,
    ) -> None:
        self._app = app
        self._trusted_proxies = trusted_proxies
        self._statements = statement_counter or _NoStatementCounter()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        request_id = _valid_request_id(_header(scope, b"x-request-id"))
        address = client_address(scope, self._trusted_proxies)
        scope.setdefault("state", {})
        scope["state"]["request_id"] = request_id
        scope["state"]["client_address"] = address

        bind_contextvars(request_id=request_id)
        self._statements.reset()
        start = time.perf_counter()
        status_holder = {"status": 500}

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                status_holder["status"] = message["status"]
                headers = _MutableHeaders(message.setdefault("headers", []))
                for name, value in _SECURITY_HEADERS.items():
                    headers.setdefault(name, value)
                headers.set("x-request-id", request_id)
                headers.discard("server")
            await send(message)

        try:
            await self._app(scope, receive, send_wrapper)
        finally:
            duration_ms = round((time.perf_counter() - start) * 1000, 3)
            route = _route_template(scope)
            status = status_holder["status"]
            event = {
                "route": route,
                "method": scope.get("method"),
                "status": status,
                "duration_ms": duration_ms,
                "request_id": request_id,
                "actor_id": scope["state"].get("actor_id"),
                "organization_id": scope["state"].get("organization_id"),
                "statements": self._statements.current(),
            }
            if status >= 500:
                logger.error("request.completed", **event)
            else:
                logger.info("request.completed", **event)
            clear_contextvars()


HEALTH_PATHS = frozenset({"/health/live", "/health/ready", "/health"})
METRICS_PATH = "/metrics"


class HostCheckMiddleware:
    """``XCODE_ALLOWED_HOSTS`` on every route but the health probes and ``/metrics``, which
    the image's HEALTHCHECK, load balancers and the scraper call by address; their bodies
    do not depend on the host."""

    def __init__(self, app: ASGIApp, *, allowed_hosts: list[str]) -> None:
        self._app = app
        self._checked = TrustedHostMiddleware(app, allowed_hosts=allowed_hosts)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path")
        if scope["type"] == "http" and (path in HEALTH_PATHS or path == METRICS_PATH):
            await self._app(scope, receive, send)
            return
        await self._checked(scope, receive, send)


COMPRESSED_PREFIX = "/setup/"
COMPRESSION_THRESHOLD_BYTES = 1024
# Already a zip archive: gzip would spend CPU for nothing.
UNCOMPRESSED_TYPES = (
    *DEFAULT_EXCLUDED_CONTENT_TYPES,
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)


class SetupCompressionMiddleware:
    """Gzip for ``/setup/`` answers larger than 1 KiB when the client accepts it, and
    ``Vary: Accept-Encoding`` on every ``/setup/`` answer. Nothing else is compressed: the
    ``/auth`` answers are compared byte for byte and must never carry a secret through a
    compression oracle, and health bodies are constant."""

    def __init__(self, app: ASGIApp) -> None:
        self._app = app
        self._gzip = GZipMiddleware(
            app,
            minimum_size=COMPRESSION_THRESHOLD_BYTES + 1,
            exclude_content_types=UNCOMPRESSED_TYPES,
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not str(scope.get("path", "")).startswith(COMPRESSED_PREFIX):
            await self._app(scope, receive, send)
            return

        async def send_with_vary(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                vary = headers.get("vary", "")
                if "accept-encoding" not in vary.lower():
                    headers.add_vary_header("Accept-Encoding")
            await send(message)

        await self._gzip(scope, receive, send_with_vary)


class MetricsMiddleware:
    """Counts every request by route template, method and status, times it, counts 429s
    as rate-limit rejections, and binds the metrics for the request so the gateway reports
    routine durations and sign-in refusals. A path no route matched is ``unmatched``."""

    def __init__(self, app: ASGIApp, *, metrics: RequestMetrics) -> None:
        self._app = app
        self._metrics = metrics

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        status_holder = {"status": 500}

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                status_holder["status"] = message["status"]
            await send(message)

        token = active_metrics.set(self._metrics)
        start = time.perf_counter()
        try:
            await self._app(scope, receive, send_wrapper)
        finally:
            active_metrics.reset(token)
            route = getattr(scope.get("route"), "path_format", None)
            status = status_holder["status"]
            self._metrics.request_finished(
                route if isinstance(route, str) else UNMATCHED_ROUTE,
                str(scope.get("method", "")),
                status,
                time.perf_counter() - start,
            )
            if status == 429:
                self._metrics.rate_limit_rejected()


class BodyCapMiddleware:
    """Rejects bodies larger than 1 MiB with a 413 problem.

    A declared ``Content-Length`` above the cap is refused before the handler runs. A
    chunked body is counted as it streams; crossing the cap raises ``HTTPException(413)``
    out of the handler's body read, which ``http/errors.py`` renders as the same problem.
    """

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        content_length = _header(scope, b"content-length")
        if content_length is not None and content_length.isdigit():
            if int(content_length) > BODY_CAP_BYTES:
                await self._reject(scope, send)
                return

        received = 0

        async def capped_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > BODY_CAP_BYTES:
                    raise HTTPException(status_code=413, detail=BODY_TOO_LARGE_TITLE)
            return message

        await self._app(scope, capped_receive, send)

    async def _reject(self, scope: Scope, send: Send) -> None:
        request_id = scope.get("state", {}).get("request_id", "")
        response: Response = problem(413, BODY_TOO_LARGE_TITLE, request_id=request_id)

        async def _empty_receive() -> Message:
            return {"type": "http.request", "body": b"", "more_body": False}

        await response(scope, _empty_receive, send)


class _MutableHeaders:
    def __init__(self, raw: list[tuple[bytes, bytes]]) -> None:
        self._raw = raw

    def setdefault(self, name: str, value: str) -> None:
        key = name.lower().encode("latin-1")
        if not any(existing_key == key for existing_key, _ in self._raw):
            self._raw.append((key, value.encode("latin-1")))

    def set(self, name: str, value: str) -> None:
        key = name.lower().encode("latin-1")
        self._raw[:] = [(k, v) for k, v in self._raw if k != key]
        self._raw.append((key, value.encode("latin-1")))

    def discard(self, name: str) -> None:
        key = name.lower().encode("latin-1")
        self._raw[:] = [(k, v) for k, v in self._raw if k != key]
