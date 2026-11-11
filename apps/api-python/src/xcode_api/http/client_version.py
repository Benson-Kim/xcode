"""The minimum mobile build. A request whose ``X-XCODE-Client`` is ``mobile/<version>`` with a
version below ``XCODE_MIN_MOBILE_VERSION``, or not a dotted numeric version at all, answers
426 ``update_required`` on every route but the health probes. A missing header or another
client (the web BFF, builds from before the header) is not checked: this keeps outdated apps
off a changed contract and is not an access control."""

from __future__ import annotations

from starlette.types import ASGIApp, Receive, Scope, Send

from ..domain.identity import EnvelopeStatus
from ..settings import dotted_version
from .middleware import HEALTH_PATHS
from .responses import JsonResponse

CLIENT_HEADER = b"x-xcode-client"
MOBILE_PREFIX = "mobile/"
UPDATE_REQUIRED_HTTP_STATUS = 426
UPDATE_REQUIRED_MESSAGE = (
    "This version of the app is no longer supported. Update the app to continue."
)


class ClientVersionMiddleware:
    def __init__(self, app: ASGIApp, *, minimum_version: str) -> None:
        minimum = dotted_version(minimum_version)
        if minimum is None:
            raise ValueError(f"not a dotted numeric version: {minimum_version!r}")
        self._app = app
        self._minimum = minimum
        self._body = {
            "status": EnvelopeStatus.UPDATE_REQUIRED.value,
            "minimumVersion": minimum_version,
            "message": UPDATE_REQUIRED_MESSAGE,
        }

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        exempt = scope["type"] != "http" or scope.get("path") in HEALTH_PATHS
        if exempt or not self._outdated(scope):
            await self._app(scope, receive, send)
            return
        response = JsonResponse(self._body, status_code=UPDATE_REQUIRED_HTTP_STATUS)
        await response(scope, receive, send)

    def _outdated(self, scope: Scope) -> bool:
        headers = scope.get("headers", [])
        client = next((v.decode("latin-1") for k, v in headers if k == CLIENT_HEADER), None)
        if client is None or not client.startswith(MOBILE_PREFIX):
            return False
        version = dotted_version(client.removeprefix(MOBILE_PREFIX).strip())
        return version is None or version < self._minimum
