"""Vehicle routes (``docs/06-http-contract.md`` section 2.3). Each handler builds
the command, tells one use case and maps the outcome; the routines decide every rule."""

from __future__ import annotations

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query
from starlette.responses import Response

from ...application.caller import Caller
from ...application.setup.create_vehicle import CreateVehicleCommand
from ...application.setup.get_vehicle_report import GetVehicleReportQuery
from ...application.setup.list_company_options import ListCompanyOptionsQuery
from ...application.setup.list_target_sets import ListTargetSetsQuery
from ...application.setup.list_vehicles import ListVehiclesQuery
from ...application.setup.remove_target_set import RemoveTargetSetCommand
from ...application.setup.restore_vehicle import RestoreVehicleCommand
from ...application.setup.retire_vehicle import RetireVehicleCommand
from ...application.setup.save_target_set import SaveTargetSetCommand
from ...application.setup.update_vehicle import UpdateVehicleCommand
from ...container import Container
from ..dependencies import container, current_caller
from ..responses import respond
from ..routing import SetupRoute
from ..schemas.access import CompanyOption, IdResponse
from ..schemas.common import Page, problem_responses
from ..schemas.setup import (
    SaveTargetSet,
    SaveVehicle,
    TargetSetDto,
    VehicleDto,
    VehicleLifecycleRequest,
    VehicleReportDto,
    VehicleRestoreRequest,
)

CallerDep = Annotated[Caller, Depends(current_caller)]
ContainerDep = Annotated[Container, Depends(container)]
PageNumber = Annotated[int, Query(alias="page", ge=-(2**31), le=2**31 - 1)]
PageSize = Annotated[int, Query(alias="pageSize", ge=-(2**31), le=2**31 - 1)]
VehicleId = Annotated[UUID, Path(alias="id")]
CompanyFilter = Annotated[UUID | None, Query(alias="companyId")]

router = APIRouter(prefix="/setup", tags=["Setup"], route_class=SetupRoute)


@router.get(
    "/vehicles",
    operation_id="ListSetupVehicles",
    response_model=Page[VehicleDto],
    responses=problem_responses(400, 403),
)
async def list_vehicles(
    caller: CallerDep,
    c: ContainerDep,
    page: PageNumber = 1,
    page_size: PageSize = 25,
    company_id: CompanyFilter = None,
) -> Response:
    vehicles = await c.list_vehicles.execute(ListVehiclesQuery(caller, company_id, page, page_size))
    return respond(
        Page[VehicleDto](
            items=[VehicleDto.from_record(vehicle) for vehicle in vehicles.items],
            page_number=page,
            page_size=page_size,
            total=vehicles.total,
        )
    )


@router.post(
    "/vehicles",
    operation_id="CreateSetupVehicle",
    response_model=IdResponse,
    responses=problem_responses(400, 403, 404),
)
async def create_vehicle(body: SaveVehicle, caller: CallerDep, c: ContainerDep) -> Response:
    result = await c.create_vehicle.execute(
        CreateVehicleCommand(caller, body.details(), body.reason)
    )
    return respond(IdResponse(id=result.id))


@router.put(
    "/vehicles/{id:uuid}",
    operation_id="UpdateSetupVehicle",
    response_model=IdResponse,
    responses=problem_responses(400, 403, 404),
)
async def update_vehicle(
    vehicle_id: VehicleId, body: SaveVehicle, caller: CallerDep, c: ContainerDep
) -> Response:
    result = await c.update_vehicle.execute(
        UpdateVehicleCommand(caller, vehicle_id, body.details(), body.reason)
    )
    return respond(IdResponse(id=result.id))


@router.get(
    "/vehicles/company-options",
    operation_id="ListVehicleCompanyOptions",
    response_model=list[CompanyOption],
    responses=problem_responses(403),
)
async def list_company_options(caller: CallerDep, c: ContainerDep) -> Response:
    options = await c.list_company_options.execute(ListCompanyOptionsQuery(caller))
    return respond([CompanyOption.from_record(option) for option in options])


@router.post(
    "/vehicles/{id:uuid}/retire",
    operation_id="RetireSetupVehicle",
    response_model=IdResponse,
    responses=problem_responses(400, 403, 404),
)
async def retire_vehicle(
    vehicle_id: VehicleId, body: VehicleLifecycleRequest, caller: CallerDep, c: ContainerDep
) -> Response:
    result = await c.retire_vehicle.execute(
        RetireVehicleCommand(caller, vehicle_id, body.left_on, body.reason)
    )
    return respond(IdResponse(id=result.id))


@router.post(
    "/vehicles/{id:uuid}/restore",
    operation_id="RestoreSetupVehicle",
    response_model=IdResponse,
    responses=problem_responses(400, 403, 404),
)
async def restore_vehicle(
    vehicle_id: VehicleId, body: VehicleRestoreRequest, caller: CallerDep, c: ContainerDep
) -> Response:
    result = await c.restore_vehicle.execute(
        RestoreVehicleCommand(caller, vehicle_id, body.returned_on, body.reason)
    )
    return respond(IdResponse(id=result.id))


@router.get(
    "/vehicles/{id:uuid}/report",
    operation_id="GetSetupVehicleReport",
    response_model=VehicleReportDto,
    responses=problem_responses(400, 403, 404),
)
async def get_vehicle_report(
    *,
    vehicle_id: VehicleId,
    caller: CallerDep,
    c: ContainerDep,
    period: str | None = None,
    from_date: Annotated[date | None, Query(alias="from")] = None,
    through: date | None = None,
) -> Response:
    report = await c.get_vehicle_report.execute(
        GetVehicleReportQuery(caller, vehicle_id, period, from_date, through)
    )
    return respond(VehicleReportDto.from_record(report))


@router.get(
    "/vehicles/{id:uuid}/targets",
    operation_id="ListVehicleTargets",
    response_model=list[TargetSetDto],
    responses=problem_responses(403, 404),
)
async def list_target_sets(vehicle_id: VehicleId, caller: CallerDep, c: ContainerDep) -> Response:
    sets = await c.list_target_sets.execute(ListTargetSetsQuery(caller, vehicle_id))
    return respond([TargetSetDto.from_record(target_set) for target_set in sets])


@router.post(
    "/vehicles/{id:uuid}/targets",
    operation_id="SaveVehicleTargets",
    response_model=IdResponse,
    responses=problem_responses(400, 403, 404),
)
async def save_target_set(
    vehicle_id: VehicleId, body: SaveTargetSet, caller: CallerDep, c: ContainerDep
) -> Response:
    result = await c.save_target_set.execute(
        SaveTargetSetCommand(caller, vehicle_id, body.starts_on, body.day_amounts())
    )
    return respond(IdResponse(id=result.id))


@router.post(
    "/vehicle-targets/{id:uuid}/remove",
    operation_id="RemoveVehicleTargets",
    response_model=IdResponse,
    responses=problem_responses(400, 403, 404),
)
async def remove_target_set(set_id: VehicleId, caller: CallerDep, c: ContainerDep) -> Response:
    result = await c.remove_target_set.execute(RemoveTargetSetCommand(caller, set_id))
    return respond(IdResponse(id=result.id))
