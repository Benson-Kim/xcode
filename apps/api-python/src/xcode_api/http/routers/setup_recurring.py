"""Scheduled expense and saving routes (``docs/06-http-contract.md`` section 2.4).
Each handler builds the command, tells one use case and maps the outcome; the routines decide
every rule."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query
from starlette.responses import Response

from ...application.caller import Caller
from ...application.setup.cancel_recurring_stop import CancelRecurringStopCommand
from ...application.setup.create_recurring import CreateRecurringCommand
from ...application.setup.get_recurring_runs import GetRecurringRunsQuery
from ...application.setup.get_recurring_summary import GetRecurringSummaryQuery
from ...application.setup.list_recurring import ListRecurringQuery
from ...application.setup.list_vehicle_options import ListVehicleOptionsQuery
from ...application.setup.pause_recurring import PauseRecurringCommand
from ...application.setup.resume_recurring import ResumeRecurringCommand
from ...application.setup.revise_recurring import ReviseRecurringCommand
from ...application.setup.stop_recurring import StopRecurringCommand
from ...container import Container
from ..dependencies import container, current_caller
from ..responses import respond
from ..routing import SetupRoute
from ..schemas.access import IdResponse
from ..schemas.common import Page, problem_responses
from ..schemas.setup import (
    RecurringDto,
    RecurringRunsDto,
    RecurringSummaryDto,
    RecurringVehicleOption,
    SaveRecurring,
    StopRecurring,
)

CallerDep = Annotated[Caller, Depends(current_caller)]
ContainerDep = Annotated[Container, Depends(container)]
PageNumber = Annotated[int, Query(alias="page", ge=-(2**31), le=2**31 - 1)]
PageSize = Annotated[int, Query(alias="pageSize", ge=-(2**31), le=2**31 - 1)]
ItemId = Annotated[UUID, Path(alias="id")]
CompanyFilter = Annotated[UUID | None, Query(alias="companyId")]

router = APIRouter(prefix="/setup", tags=["Setup"], route_class=SetupRoute)


@router.get(
    "/recurring",
    operation_id="ListSetupRecurring",
    response_model=Page[RecurringDto],
    responses=problem_responses(400, 403),
)
async def list_recurring(
    *,
    caller: CallerDep,
    c: ContainerDep,
    page: PageNumber = 1,
    page_size: PageSize = 25,
    kind: str | None = None,
    company_id: CompanyFilter = None,
    status: str | None = None,
) -> Response:
    items = await c.list_recurring.execute(
        ListRecurringQuery(caller, kind, company_id, status, page, page_size)
    )
    return respond(
        Page[RecurringDto](
            items=[RecurringDto.from_record(item) for item in items.items],
            page_number=page,
            page_size=page_size,
            total=items.total,
        )
    )


@router.get(
    "/recurring/summary",
    operation_id="GetSetupRecurringSummary",
    response_model=RecurringSummaryDto,
    responses=problem_responses(403),
)
async def get_recurring_summary(caller: CallerDep, c: ContainerDep) -> Response:
    summary = await c.get_recurring_summary.execute(GetRecurringSummaryQuery(caller))
    return respond(RecurringSummaryDto.from_record(summary))


@router.get(
    "/recurring/vehicle-options",
    operation_id="ListRecurringVehicleOptions",
    response_model=list[RecurringVehicleOption],
    responses=problem_responses(403),
)
async def list_vehicle_options(caller: CallerDep, c: ContainerDep) -> Response:
    options = await c.list_vehicle_options.execute(ListVehicleOptionsQuery(caller))
    return respond([RecurringVehicleOption.from_record(option) for option in options])


@router.post(
    "/recurring",
    operation_id="CreateSetupRecurring",
    response_model=IdResponse,
    responses=problem_responses(400, 403, 404),
)
async def create_recurring(body: SaveRecurring, caller: CallerDep, c: ContainerDep) -> Response:
    result = await c.create_recurring.execute(
        CreateRecurringCommand(caller, body.definition(), body.reason)
    )
    return respond(IdResponse(id=result.id))


@router.put(
    "/recurring/{id:uuid}",
    operation_id="ReviseSetupRecurring",
    response_model=IdResponse,
    responses=problem_responses(400, 403, 404),
)
async def revise_recurring(
    item_id: ItemId, body: SaveRecurring, caller: CallerDep, c: ContainerDep
) -> Response:
    result = await c.revise_recurring.execute(
        ReviseRecurringCommand(caller, item_id, body.definition(), body.reason)
    )
    return respond(IdResponse(id=result.id))


@router.post(
    "/recurring/{id:uuid}/stop",
    operation_id="StopSetupRecurring",
    response_model=IdResponse,
    responses=problem_responses(400, 403, 404),
)
async def stop_recurring(
    item_id: ItemId, body: StopRecurring, caller: CallerDep, c: ContainerDep
) -> Response:
    result = await c.stop_recurring.execute(
        StopRecurringCommand(caller, item_id, body.confirmed, body.reason)
    )
    return respond(IdResponse(id=result.id))


@router.post(
    "/recurring/{id:uuid}/restore",
    operation_id="CancelSetupRecurringStop",
    response_model=IdResponse,
    responses=problem_responses(400, 403, 404),
)
async def cancel_recurring_stop(item_id: ItemId, caller: CallerDep, c: ContainerDep) -> Response:
    result = await c.cancel_recurring_stop.execute(CancelRecurringStopCommand(caller, item_id))
    return respond(IdResponse(id=result.id))


@router.get(
    "/recurring/{id:uuid}/runs",
    operation_id="GetSetupRecurringRuns",
    response_model=RecurringRunsDto,
    responses=problem_responses(403, 404),
)
async def get_recurring_runs(item_id: ItemId, caller: CallerDep, c: ContainerDep) -> Response:
    runs = await c.get_recurring_runs.execute(GetRecurringRunsQuery(caller, item_id))
    return respond(RecurringRunsDto.from_record(runs))


@router.post(
    "/recurring/{id:uuid}/pause",
    operation_id="PauseSetupRecurring",
    response_model=IdResponse,
    responses=problem_responses(400, 403, 404),
)
async def pause_recurring(item_id: ItemId, caller: CallerDep, c: ContainerDep) -> Response:
    result = await c.pause_recurring.execute(PauseRecurringCommand(caller, item_id))
    return respond(IdResponse(id=result.id))


@router.post(
    "/recurring/{id:uuid}/resume",
    operation_id="ResumeSetupRecurring",
    response_model=IdResponse,
    responses=problem_responses(400, 403, 404),
)
async def resume_recurring(item_id: ItemId, caller: CallerDep, c: ContainerDep) -> Response:
    result = await c.resume_recurring.execute(ResumeRecurringCommand(caller, item_id))
    return respond(IdResponse(id=result.id))
