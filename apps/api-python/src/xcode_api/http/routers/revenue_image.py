"""The Revenue Summary image's change-log row (``docs/06-http-contract.md`` 2.13.3, X04). The
web draws the picture of the week on screen on the device; this route only records that it was
exported, under the right every revenue export needs."""

from __future__ import annotations

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from starlette.responses import Response

from ...application.caller import Caller
from ...application.revenue.log_summary_image import LogRevenueSummaryImageCommand
from ...container import Container
from ..dependencies import container, current_caller
from ..routing import SetupRoute
from ..schemas.common import ApiModel, problem_responses

CallerDep = Annotated[Caller, Depends(current_caller)]
ContainerDep = Annotated[Container, Depends(container)]

router = APIRouter(prefix="/setup/revenue", tags=["Revenue"], route_class=SetupRoute)


class RevenueSummaryImageLog(ApiModel):
    """The week the picture shows, the company filter and the search, as the screen used them."""

    week_start: date
    company_id: UUID | None = None
    q: str | None = None


@router.post(
    "/export/image",
    operation_id="LogRevenueSummaryImage",
    status_code=204,
    responses=problem_responses(400, 403, 404),
)
async def log_summary_image(
    body: RevenueSummaryImageLog, caller: CallerDep, c: ContainerDep
) -> Response:
    await c.log_revenue_summary_image.execute(
        LogRevenueSummaryImageCommand(caller, body.week_start, body.company_id, body.q)
    )
    return Response(status_code=204)
