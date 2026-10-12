"""Petty-cash routes (``docs/06-http-contract.md`` section 2.11): the screen's overview and
entry list, the entry form's options, the dashboard cards, and the writes on entries. Each
handler builds the query or command, tells one use case and maps the outcome; the routines
decide every rule. A create answers 200 (a replayed create answers like the first)."""

from __future__ import annotations

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query
from starlette.responses import Response

from ...application.caller import Caller
from ...application.pettycash.approve_day import ApprovePettyCashDayCommand
from ...application.pettycash.approve_entries import ApprovePettyCashEntriesCommand
from ...application.pettycash.approve_entry import ApprovePettyCashEntryCommand
from ...application.pettycash.create_entry import CreatePettyCashEntryCommand
from ...application.pettycash.get_dashboard import GetPettyCashDashboardQuery
from ...application.pettycash.get_options import GetPettyCashOptionsQuery
from ...application.pettycash.get_overview import GetPettyCashOverviewQuery
from ...application.pettycash.list_entries import ListPettyCashEntriesQuery
from ...application.pettycash.reject_entry import RejectPettyCashEntryCommand
from ...application.pettycash.remove_entry import RemovePettyCashEntryCommand
from ...application.pettycash.reopen_entry import ReopenPettyCashEntryCommand
from ...application.pettycash.send_back_entry import SendBackPettyCashEntryCommand
from ...application.pettycash.update_entry import UpdatePettyCashEntryCommand
from ...container import Container
from ...domain.pettycash import PettyCashApproved, PettyCashLine, PettyCashSaved, PettyCashTicked
from ..dependencies import container, current_caller
from ..responses import respond
from ..routing import SetupRoute
from ..schemas.common import Page, problem_responses
from ..schemas.pettycash import (
    ApprovePettyCashDay,
    ApprovePettyCashEntries,
    DecidePettyCashEntry,
    PettyCashDashboardDto,
    PettyCashDayApproved,
    PettyCashEntryDto,
    PettyCashOptionsDto,
    PettyCashOverviewDto,
    RemovePettyCashEntry,
    ReviewPettyCashEntry,
    SavePettyCashEntry,
    SendBackPettyCashEntry,
)
from ..schemas.pettycash import PettyCashSaved as PettyCashSavedDto

CallerDep = Annotated[Caller, Depends(current_caller)]
ContainerDep = Annotated[Container, Depends(container)]
Day = Annotated[date | None, Query(alias="date")]
HolderFilter = Annotated[UUID | None, Query(alias="holderId")]
FromDay = Annotated[date | None, Query(alias="from")]
ToDay = Annotated[date | None, Query(alias="to")]
PageNumber = Annotated[int, Query(alias="page", ge=-(2**31), le=2**31 - 1)]
PageSize = Annotated[int, Query(alias="pageSize", ge=-(2**31), le=2**31 - 1)]
EntryId = Annotated[UUID, Path(alias="id")]

router = APIRouter(prefix="/setup/pettycash", tags=["Petty cash"], route_class=SetupRoute)


def _words(text: str | None) -> tuple[str, ...] | None:
    """A comma list: items trimmed, empty ones dropped, repeats removed, order kept."""
    if text is None:
        return None
    words = (part.strip() for part in text.split(","))
    return tuple(dict.fromkeys(word for word in words if word))


def _line(body: SavePettyCashEntry) -> PettyCashLine:
    return PettyCashLine(
        body.kind,
        body.entry_date,
        body.unit_amount,
        body.holder_id,
        body.vehicle_id,
        body.expense_item_id,
        body.units,
        body.payee,
        body.note,
        body.reimbursable,
    )


def _saved(result: PettyCashSaved) -> Response:
    return respond(
        PettyCashSavedDto(
            id=result.id, version=result.version, status=result.status, balance=result.balance
        )
    )


def _approved(result: PettyCashApproved) -> Response:
    return respond(
        PettyCashDayApproved(approved=result.approved, total=result.total, skipped=result.skipped)
    )


@router.get(
    "/overview",
    operation_id="GetPettyCashOverview",
    response_model=PettyCashOverviewDto,
    responses=problem_responses(400, 403, 404),
)
async def get_overview(
    *,
    caller: CallerDep,
    c: ContainerDep,
    day: Day = None,
    period: str | None = None,
    holder_id: HolderFilter = None,
    from_date: FromDay = None,
    to_date: ToDay = None,
) -> Response:
    overview = await c.get_pettycash_overview.execute(
        GetPettyCashOverviewQuery(caller, day, period, holder_id, from_date, to_date)
    )
    return respond(PettyCashOverviewDto.from_record(overview))


@router.get(
    "/entries",
    operation_id="ListPettyCashEntries",
    response_model=Page[PettyCashEntryDto],
    responses=problem_responses(400, 403, 404),
)
async def list_entries(
    *,
    caller: CallerDep,
    c: ContainerDep,
    from_date: FromDay = None,
    to_date: ToDay = None,
    holder_id: HolderFilter = None,
    kind: str | None = None,
    status: str | None = None,
    q: str | None = None,
    page: PageNumber = 1,
    page_size: PageSize = 100,
) -> Response:
    entries = await c.list_pettycash_entries.execute(
        ListPettyCashEntriesQuery(
            caller,
            from_date,
            to_date,
            holder_id,
            _words(kind),
            _words(status),
            q,
            page,
            page_size,
        )
    )
    return respond(
        Page[PettyCashEntryDto](
            items=[PettyCashEntryDto.from_record(entry) for entry in entries.items],
            page_number=page,
            page_size=page_size,
            total=entries.total,
        )
    )


@router.get(
    "/options",
    operation_id="GetPettyCashOptions",
    response_model=PettyCashOptionsDto,
    responses=problem_responses(400, 403),
)
async def get_options(caller: CallerDep, c: ContainerDep, day: Day = None) -> Response:
    options = await c.get_pettycash_options.execute(GetPettyCashOptionsQuery(caller, day))
    return respond(PettyCashOptionsDto.from_record(options))


@router.get(
    "/dashboard",
    operation_id="GetPettyCashDashboard",
    response_model=PettyCashDashboardDto,
    responses=problem_responses(403),
)
async def get_dashboard(caller: CallerDep, c: ContainerDep) -> Response:
    dashboard = await c.get_pettycash_dashboard.execute(GetPettyCashDashboardQuery(caller))
    return respond(PettyCashDashboardDto.from_record(dashboard))


@router.post(
    "/entries",
    operation_id="CreatePettyCashEntry",
    response_model=PettyCashSavedDto,
    responses=problem_responses(400, 403, 404, 409),
)
async def create_entry(body: SavePettyCashEntry, caller: CallerDep, c: ContainerDep) -> Response:
    result = await c.create_pettycash_entry.execute(
        CreatePettyCashEntryCommand(caller, body.id, _line(body))
    )
    return _saved(result)


@router.put(
    "/entries/{id:uuid}",
    operation_id="UpdatePettyCashEntry",
    response_model=PettyCashSavedDto,
    responses=problem_responses(400, 403, 404, 409),
)
async def update_entry(
    entry_id: EntryId, body: SavePettyCashEntry, caller: CallerDep, c: ContainerDep
) -> Response:
    result = await c.update_pettycash_entry.execute(
        UpdatePettyCashEntryCommand(caller, entry_id, _line(body), body.version)
    )
    return _saved(result)


@router.post(
    "/entries/{id:uuid}/approve",
    operation_id="ApprovePettyCashEntry",
    response_model=PettyCashSavedDto,
    responses=problem_responses(400, 403, 404, 409),
)
async def approve_entry(
    entry_id: EntryId, body: ReviewPettyCashEntry, caller: CallerDep, c: ContainerDep
) -> Response:
    result = await c.approve_pettycash_entry.execute(
        ApprovePettyCashEntryCommand(caller, entry_id, body.version)
    )
    return _saved(result)


@router.post(
    "/entries/{id:uuid}/send-back",
    operation_id="SendBackPettyCashEntry",
    response_model=PettyCashSavedDto,
    responses=problem_responses(400, 403, 404, 409),
)
async def send_back_entry(
    entry_id: EntryId, body: SendBackPettyCashEntry, caller: CallerDep, c: ContainerDep
) -> Response:
    result = await c.send_back_pettycash_entry.execute(
        SendBackPettyCashEntryCommand(caller, entry_id, body.version, body.comment)
    )
    return _saved(result)


@router.post(
    "/entries/{id:uuid}/remove",
    operation_id="RemovePettyCashEntry",
    response_model=PettyCashSavedDto,
    responses=problem_responses(400, 403, 404, 409),
)
async def remove_entry(
    entry_id: EntryId, body: RemovePettyCashEntry, caller: CallerDep, c: ContainerDep
) -> Response:
    result = await c.remove_pettycash_entry.execute(
        RemovePettyCashEntryCommand(caller, entry_id, body.version, body.reason)
    )
    return _saved(result)


@router.post(
    "/approve-day",
    operation_id="ApprovePettyCashDay",
    response_model=PettyCashDayApproved,
    responses=problem_responses(400, 403, 404),
)
async def approve_day(body: ApprovePettyCashDay, caller: CallerDep, c: ContainerDep) -> Response:
    result = await c.approve_pettycash_day.execute(
        ApprovePettyCashDayCommand(caller, body.day, body.to, body.holder_id)
    )
    return _approved(result)


@router.post(
    "/approve",
    operation_id="ApprovePettyCashEntries",
    response_model=PettyCashDayApproved,
    responses=problem_responses(400, 403, 404, 409),
)
async def approve_entries(
    body: ApprovePettyCashEntries, caller: CallerDep, c: ContainerDep
) -> Response:
    ticked = tuple(PettyCashTicked(entry.id, entry.version) for entry in body.entries or ())
    result = await c.approve_pettycash_entries.execute(
        ApprovePettyCashEntriesCommand(caller, ticked)
    )
    return _approved(result)


@router.post(
    "/entries/{id:uuid}/reject",
    operation_id="RejectPettyCashEntry",
    response_model=PettyCashSavedDto,
    responses=problem_responses(400, 403, 404, 409),
)
async def reject_entry(
    entry_id: EntryId, body: DecidePettyCashEntry, caller: CallerDep, c: ContainerDep
) -> Response:
    result = await c.reject_pettycash_entry.execute(
        RejectPettyCashEntryCommand(caller, entry_id, body.version, body.reason)
    )
    return _saved(result)


@router.post(
    "/entries/{id:uuid}/reopen",
    operation_id="ReopenPettyCashEntry",
    response_model=PettyCashSavedDto,
    responses=problem_responses(400, 403, 404, 409),
)
async def reopen_entry(
    entry_id: EntryId, body: DecidePettyCashEntry, caller: CallerDep, c: ContainerDep
) -> Response:
    result = await c.reopen_pettycash_entry.execute(
        ReopenPettyCashEntryCommand(caller, entry_id, body.version, body.reason)
    )
    return _saved(result)
