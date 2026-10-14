"""Report routes (``docs/06-http-contract.md`` 2.13.2): the catalogue, one page of a fleet
or petty-cash report, and a report as an Excel or PDF file. Each handler builds the query,
tells one use case and maps the outcome; the routines decide every rule. The group of an
export is ``fleet`` or ``pettycash``, anything else an empty 404, as .NET answered."""

from __future__ import annotations

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from starlette.exceptions import HTTPException
from starlette.responses import Response

from ...application.caller import Caller
from ...application.reports.export_report import ExportReportQuery
from ...application.reports.get_report import GetReportQuery
from ...application.reports.get_reports_access import GetReportsAccessQuery
from ...container import Container
from ...domain.reports import PDF_CONTENT_TYPE, XLSX_CONTENT_TYPE, ReportGroup
from ..dependencies import container, current_caller
from ..responses import file_response, respond
from ..routing import SetupRoute
from ..schemas.common import problem_responses
from ..schemas.reports import ReportsAccessDto, ReportTableDto

CallerDep = Annotated[Caller, Depends(current_caller)]
ContainerDep = Annotated[Container, Depends(container)]
FromDay = Annotated[date | None, Query(alias="from")]
ToDay = Annotated[date | None, Query(alias="to")]
CompanyFilter = Annotated[UUID | None, Query(alias="companyId")]
HolderFilter = Annotated[UUID | None, Query(alias="holderId")]
PageNumber = Annotated[int, Query(alias="page", ge=-(2**31), le=2**31 - 1)]
PageSize = Annotated[int, Query(alias="pageSize", ge=-(2**31), le=2**31 - 1)]

FILE_RESPONSES = {
    200: {
        "description": "The file",
        "content": {XLSX_CONTENT_TYPE: {}, PDF_CONTENT_TYPE: {}},
    },
    **problem_responses(400, 403, 404),
}

router = APIRouter(prefix="/setup/reports", tags=["Reports"], route_class=SetupRoute)


@router.get(
    "",
    operation_id="GetReportsAccess",
    response_model=ReportsAccessDto,
    responses=problem_responses(403),
)
async def get_reports_access(caller: CallerDep, c: ContainerDep) -> Response:
    access = await c.get_reports_access.execute(GetReportsAccessQuery(caller))
    return respond(ReportsAccessDto.from_record(access))


@router.get(
    "/fleet/{report}",
    operation_id="GetFleetReport",
    response_model=ReportTableDto,
    responses=problem_responses(400, 403, 404),
)
async def get_fleet_report(
    report: str,
    *,
    caller: CallerDep,
    c: ContainerDep,
    from_date: FromDay = None,
    to_date: ToDay = None,
    company_id: CompanyFilter = None,
    q: str | None = None,
    page: PageNumber = 1,
    page_size: PageSize = 50,
) -> Response:
    table = await c.get_report.execute(
        GetReportQuery(
            caller,
            ReportGroup.FLEET,
            report,
            from_date,
            to_date,
            company_id,
            None,
            q,
            page,
            page_size,
        )
    )
    return respond(ReportTableDto.from_record(table))


@router.get(
    "/pettycash/{report}",
    operation_id="GetPettyCashReport",
    response_model=ReportTableDto,
    responses=problem_responses(400, 403, 404),
)
async def get_pettycash_report(
    report: str,
    *,
    caller: CallerDep,
    c: ContainerDep,
    from_date: FromDay = None,
    to_date: ToDay = None,
    holder_id: HolderFilter = None,
    q: str | None = None,
    page: PageNumber = 1,
    page_size: PageSize = 50,
) -> Response:
    table = await c.get_report.execute(
        GetReportQuery(
            caller,
            ReportGroup.PETTYCASH,
            report,
            from_date,
            to_date,
            None,
            holder_id,
            q,
            page,
            page_size,
        )
    )
    return respond(ReportTableDto.from_record(table))


@router.get(
    "/{group}/{report}/export",
    operation_id="ExportReport",
    response_class=Response,
    responses=FILE_RESPONSES,
)
async def export_report(
    group: str,
    report: str,
    *,
    caller: CallerDep,
    c: ContainerDep,
    from_date: FromDay = None,
    to_date: ToDay = None,
    holder_id: HolderFilter = None,
    company_id: CompanyFilter = None,
    q: str | None = None,
    format: str | None = None,
) -> Response:
    if group not in (ReportGroup.FLEET, ReportGroup.PETTYCASH):
        raise HTTPException(status_code=404)
    file = await c.export_report.execute(
        ExportReportQuery(
            caller, group, report, from_date, to_date, company_id, holder_id, q, format
        )
    )
    return file_response(file)
