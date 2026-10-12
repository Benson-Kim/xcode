"""Health routes: live, ready, and the legacy JSON endpoint.

Bodies and content types are fixed by the contract (``docs/06-http-contract.md`` section
1.10). These routes are anonymous and not rate limited; they still carry the request id and
the security headers from the middleware.
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Request
from starlette.responses import JSONResponse, PlainTextResponse

from ..dependencies import container

logger = structlog.get_logger("xcode_api.http")

router = APIRouter()


@router.get("/health/live", include_in_schema=False)
async def health_live() -> PlainTextResponse:
    return PlainTextResponse("Healthy", media_type="text/plain")


@router.get("/health/ready", include_in_schema=False)
async def health_ready(request: Request) -> PlainTextResponse:
    if not getattr(request.app.state, "started", False):
        reason: str | None = "startup has not finished its checks"
    else:
        report = await container(request).check_readiness.execute()
        if report.ready:
            return PlainTextResponse("Healthy", media_type="text/plain")
        reason = report.reason
    logger.warning("health.ready.failed", reason=reason)
    return PlainTextResponse("Unhealthy", status_code=503, media_type="text/plain")


@router.get("/health", include_in_schema=False)
async def health_legacy() -> JSONResponse:
    return JSONResponse({"status": "ok"})
