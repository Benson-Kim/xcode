"""Revenue routes (``docs/06-http-contract.md`` section 2.8): the week grid, the dashboard
and the day's capture, which is also where the phones replay their offline queue. Each handler
builds the query or command, tells one use case and maps the outcome; the routines decide
every rule. A replayed capture answers like any other."""

from __future__ import annotations

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query
from starlette.responses import Response

from ...application.caller import Caller
from ...application.revenue.capture_revenue import CaptureRevenueCommand
from ...application.revenue.get_dashboard import GetRevenueDashboardQuery
from ...application.revenue.get_week import GetRevenueWeekQuery
from ...container import Container
from ..dependencies import container, current_caller
from ..responses import respond
from ..routing import SetupRoute
from ..schemas.common import problem_responses
from ..schemas.revenue import (
    RevenueDashboardDto,
    RevenueSaved,
    RevenueWeekDto,
    SaveRevenue,
)

CallerDep = Annotated[Caller, Depends(current_caller)]
ContainerDep = Annotated[Container, Depends(container)]
CompanyFilter = Annotated[UUID | None, Query(alias="companyId")]

router = APIRouter(prefix="/setup/revenue", tags=["Revenue"], route_class=SetupRoute)


@router.get(
    "",
    operation_id="GetRevenueWeek",
    response_model=RevenueWeekDto,
    responses=problem_responses(400, 403, 404),
)
async def get_week(
    *,
    caller: CallerDep,
    c: ContainerDep,
    week_start: Annotated[date | None, Query(alias="weekStart")] = None,
    company_id: CompanyFilter = None,
    vehicle_id: Annotated[UUID | None, Query(alias="vehicleId")] = None,
    page: Annotated[int | None, Query(alias="page", ge=-(2**31), le=2**31 - 1)] = None,
    page_size: Annotated[int | None, Query(alias="pageSize", ge=-(2**31), le=2**31 - 1)] = None,
    q: str | None = None,
) -> Response:
    week = await c.get_revenue_week.execute(
        GetRevenueWeekQuery(caller, week_start, company_id, vehicle_id, page, page_size, q)
    )
    return respond(RevenueWeekDto.from_record(week))


@router.get(
    "/dashboard",
    operation_id="GetRevenueDashboard",
    response_model=RevenueDashboardDto,
    responses=problem_responses(400, 403),
)
async def get_dashboard(
    caller: CallerDep,
    c: ContainerDep,
    period: str | None = None,
    company_id: CompanyFilter = None,
) -> Response:
    dashboard = await c.get_revenue_dashboard.execute(
        GetRevenueDashboardQuery(caller, period, company_id)
    )
    return respond(RevenueDashboardDto.from_record(dashboard))


@router.put(
    "/{vehicleId:uuid}/{date}",
    operation_id="SaveRevenue",
    response_model=RevenueSaved,
    responses=problem_responses(400, 403, 404, 409),
)
async def save_revenue(
    vehicle_id: Annotated[UUID, Path(alias="vehicleId")],
    day: Annotated[date, Path(alias="date")],
    body: SaveRevenue,
    caller: CallerDep,
    c: ContainerDep,
) -> Response:
    result = await c.capture_revenue.execute(
        CaptureRevenueCommand(
            caller,
            vehicle_id,
            day,
            body.amount,
            body.reason,
            body.note,
            body.version,
            body.captured_at,
        )
    )
    return respond(RevenueSaved(id=result.id, version=result.version))
