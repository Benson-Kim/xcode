"""Investment routes (``docs/06-http-contract.md`` section 2.7). Each handler
builds the command, tells one use case and maps the outcome; the routines decide every rule.
The delete reads no body."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path
from starlette.responses import Response

from ...application.caller import Caller
from ...application.setup.create_investment import CreateInvestmentCommand
from ...application.setup.delete_investment import DeleteInvestmentCommand
from ...application.setup.get_investment import GetInvestmentQuery
from ...application.setup.update_investment import UpdateInvestmentCommand
from ...container import Container
from ..dependencies import container, current_caller
from ..responses import respond
from ..routing import SetupRoute
from ..schemas.access import IdResponse
from ..schemas.common import problem_responses
from ..schemas.setup import InvestmentDto, SaveInvestment

CallerDep = Annotated[Caller, Depends(current_caller)]
ContainerDep = Annotated[Container, Depends(container)]
RecordId = Annotated[UUID, Path(alias="id")]

router = APIRouter(prefix="/setup", tags=["Setup"], route_class=SetupRoute)


@router.get(
    "/vehicles/{id:uuid}/investment",
    operation_id="GetVehicleInvestment",
    response_model=InvestmentDto,
    responses=problem_responses(403, 404),
)
async def get_investment(vehicle_id: RecordId, caller: CallerDep, c: ContainerDep) -> Response:
    investment = await c.get_investment.execute(GetInvestmentQuery(caller, vehicle_id))
    return respond(InvestmentDto.from_record(investment))


@router.post(
    "/vehicles/{id:uuid}/investment",
    operation_id="AddVehicleInvestment",
    response_model=IdResponse,
    responses=problem_responses(400, 403, 404),
)
async def create_investment(
    vehicle_id: RecordId, body: SaveInvestment, caller: CallerDep, c: ContainerDep
) -> Response:
    result = await c.create_investment.execute(
        CreateInvestmentCommand(caller, vehicle_id, body.details())
    )
    return respond(IdResponse(id=result.id))


@router.put(
    "/investment/{id:uuid}",
    operation_id="UpdateVehicleInvestment",
    response_model=IdResponse,
    responses=problem_responses(400, 403, 404),
)
async def update_investment(
    entry_id: RecordId, body: SaveInvestment, caller: CallerDep, c: ContainerDep
) -> Response:
    result = await c.update_investment.execute(
        UpdateInvestmentCommand(caller, entry_id, body.details())
    )
    return respond(IdResponse(id=result.id))


@router.delete(
    "/investment/{id:uuid}",
    operation_id="DeleteVehicleInvestment",
    response_model=IdResponse,
    responses=problem_responses(403, 404),
)
async def delete_investment(entry_id: RecordId, caller: CallerDep, c: ContainerDep) -> Response:
    result = await c.delete_investment.execute(DeleteInvestmentCommand(caller, entry_id))
    return respond(IdResponse(id=result.id))
