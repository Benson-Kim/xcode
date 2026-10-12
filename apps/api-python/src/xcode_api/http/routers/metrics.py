"""``GET /metrics``: Prometheus text, mounted only when ``XCODE_METRICS_ENABLED`` is true.

Anonymous and not rate limited, like the health probes; the proxy never forwards it, so
only the scraper on the API's own network reaches it (``docs/08-operability.md`` section 5).
"""

from __future__ import annotations

from typing import Protocol

from fastapi import APIRouter, Request
from starlette.responses import Response

router = APIRouter()


class Exposition(Protocol):
    def exposition(self) -> tuple[bytes, str]: ...


@router.get("/metrics", include_in_schema=False)
async def metrics(request: Request) -> Response:
    source: Exposition = request.app.state.metrics
    body, content_type = source.exposition()
    return Response(body, media_type=content_type)
