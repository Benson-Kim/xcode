"""Company routes (``docs/06-http-contract.md`` section 2.3). Each handler builds
the command, tells one use case and maps the outcome; the routines decide every rule."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query
from starlette.responses import Response

from ...application.caller import Caller
from ...application.setup.archive_company import ArchiveCompanyCommand
from ...application.setup.create_company import CreateCompanyCommand
from ...application.setup.list_companies import ListCompaniesQuery
from ...application.setup.rename_company import RenameCompanyCommand
from ...application.setup.restore_company import RestoreCompanyCommand
from ...container import Container
from ..dependencies import container, current_caller
from ..responses import respond
from ..routing import SetupRoute
from ..schemas.access import IdResponse
from ..schemas.common import Page, problem_responses
from ..schemas.setup import CompanyDto, CompanyLifecycleRequest, SaveCompany

CallerDep = Annotated[Caller, Depends(current_caller)]
ContainerDep = Annotated[Container, Depends(container)]
PageNumber = Annotated[int, Query(alias="page", ge=-(2**31), le=2**31 - 1)]
PageSize = Annotated[int, Query(alias="pageSize", ge=-(2**31), le=2**31 - 1)]
CompanyId = Annotated[UUID, Path(alias="id")]

router = APIRouter(prefix="/setup", tags=["Setup"], route_class=SetupRoute)


@router.get(
    "/companies",
    operation_id="ListSetupCompanies",
    response_model=Page[CompanyDto],
    responses=problem_responses(400, 403),
)
async def list_companies(
    caller: CallerDep, c: ContainerDep, page: PageNumber = 1, page_size: PageSize = 25
) -> Response:
    companies = await c.list_companies.execute(ListCompaniesQuery(caller, page, page_size))
    return respond(
        Page[CompanyDto](
            items=[CompanyDto.from_record(company) for company in companies.items],
            page_number=page,
            page_size=page_size,
            total=companies.total,
        )
    )


@router.post(
    "/companies",
    operation_id="CreateSetupCompany",
    response_model=IdResponse,
    responses=problem_responses(400, 403),
)
async def create_company(body: SaveCompany, caller: CallerDep, c: ContainerDep) -> Response:
    result = await c.create_company.execute(CreateCompanyCommand(caller, body.name, body.reason))
    return respond(IdResponse(id=result.id))


@router.put(
    "/companies/{id:uuid}",
    operation_id="RenameSetupCompany",
    response_model=IdResponse,
    responses=problem_responses(400, 403, 404),
)
async def rename_company(
    company_id: CompanyId, body: SaveCompany, caller: CallerDep, c: ContainerDep
) -> Response:
    result = await c.rename_company.execute(
        RenameCompanyCommand(caller, company_id, body.name, body.reason)
    )
    return respond(IdResponse(id=result.id))


@router.post(
    "/companies/{id:uuid}/archive",
    operation_id="ArchiveSetupCompany",
    response_model=IdResponse,
    responses=problem_responses(400, 403, 404),
)
async def archive_company(
    company_id: CompanyId, body: CompanyLifecycleRequest, caller: CallerDep, c: ContainerDep
) -> Response:
    result = await c.archive_company.execute(ArchiveCompanyCommand(caller, company_id, body.reason))
    return respond(IdResponse(id=result.id))


@router.post(
    "/companies/{id:uuid}/restore",
    operation_id="RestoreSetupCompany",
    response_model=IdResponse,
    responses=problem_responses(400, 403, 404),
)
async def restore_company(
    company_id: CompanyId, body: CompanyLifecycleRequest, caller: CallerDep, c: ContainerDep
) -> Response:
    result = await c.restore_company.execute(RestoreCompanyCommand(caller, company_id, body.reason))
    return respond(IdResponse(id=result.id))
