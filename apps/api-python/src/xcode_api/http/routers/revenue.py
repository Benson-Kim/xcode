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
from ...application.revenue.export_week import ExportRevenueWeekQuery
from ...application.revenue.get_dashboard import GetRevenueDashboardQuery
from ...application.revenue.get_day import GetRevenueDayQuery
from ...application.revenue.get_week import GetRevenueWeekQuery
from ...application.revenue.save_day import SaveRevenueDayCommand
from ...container import Container
from ...domain.reports import PDF_CONTENT_TYPE, XLSX_CONTENT_TYPE
from ...domain.revenue import RevenueDayRow
from ..dependencies import container, current_caller
from ..responses import file_response, respond
from ..routing import SetupRoute
from ..schemas.common import problem_responses
from ..schemas.revenue import (
    RevenueDashboardDto,
    RevenueDayDto,
    RevenueDaySaved,
    RevenueSaved,
    RevenueWeekDto,
    SaveRevenue,
    SaveRevenueDay,
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


@router.get(
    "/day",
    operation_id="GetRevenueDay",
    response_model=RevenueDayDto,
    responses=problem_responses(400, 403),
)
async def get_day(
    caller: CallerDep,
    c: ContainerDep,
    day: Annotated[date | None, Query(alias="date")] = None,
    company_id: CompanyFilter = None,
) -> Response:
    result = await c.get_revenue_day.execute(GetRevenueDayQuery(caller, day, company_id))
    return respond(RevenueDayDto.from_record(result))


@router.put(
    "/day/{date}",
    operation_id="SaveRevenueDay",
    response_model=RevenueDaySaved,
    responses=problem_responses(400, 403, 404, 409),
)
async def save_day(
    day: Annotated[date, Path(alias="date")],
    body: SaveRevenueDay,
    caller: CallerDep,
    c: ContainerDep,
) -> Response:
    rows = tuple(
        RevenueDayRow(r.vehicle_id, r.amount, r.reason, r.note, r.version) for r in body.rows
    )
    result = await c.save_revenue_day.execute(SaveRevenueDayCommand(caller, day, rows))
    return respond(RevenueDaySaved.from_record(result))


@router.get(
    "/export",
    operation_id="ExportRevenueWeek",
    response_class=Response,
    responses={
        200: {"description": "The file", "content": {XLSX_CONTENT_TYPE: {}, PDF_CONTENT_TYPE: {}}},
        **problem_responses(400, 403),
    },
)
async def export_week(
    *,
    caller: CallerDep,
    c: ContainerDep,
    week_start: Annotated[date | None, Query(alias="weekStart")] = None,
    company_id: CompanyFilter = None,
    format: str | None = None,
) -> Response:
    file = await c.export_revenue_week.execute(
        ExportRevenueWeekQuery(caller, week_start, company_id, format)
    )
    return file_response(file)


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
