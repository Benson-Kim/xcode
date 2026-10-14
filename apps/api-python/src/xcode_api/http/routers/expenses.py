"""Central-expense routes (``docs/06-http-contract.md`` section 2.13.1): the ledger, the
form's options, and the record, change and remove of purchases and their rows. Each handler
builds the query or command, tells one use case and maps the outcome; the routines decide
every rule. A record answers 200 (a retried purchase answers its rows)."""

from __future__ import annotations

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query
from starlette.responses import Response

from ...application.caller import Caller
from ...application.expenses.change_expense import ChangeExpenseCommand
from ...application.expenses.export_ledger import ExportExpenseLedgerQuery
from ...application.expenses.get_ledger import GetExpenseLedgerQuery
from ...application.expenses.get_options import GetExpenseOptionsQuery
from ...application.expenses.record_expense import RecordExpenseCommand
from ...application.expenses.remove_expense import RemoveExpenseCommand
from ...container import Container
from ...domain.expenses import ExpenseAllocation, ExpenseSaved
from ...domain.reports import PDF_CONTENT_TYPE, XLSX_CONTENT_TYPE
from ..dependencies import container, current_caller
from ..responses import file_response, respond
from ..routing import SetupRoute
from ..schemas.common import problem_responses
from ..schemas.expenses import (
    ChangeExpense,
    ExpenseLedgerDto,
    ExpenseOptionsDto,
    ExpenseRecordedDto,
    ExpenseSavedDto,
    RecordExpense,
    RemoveExpense,
)

CallerDep = Annotated[Caller, Depends(current_caller)]
ContainerDep = Annotated[Container, Depends(container)]
Day = Annotated[date | None, Query(alias="date")]
FromDay = Annotated[date | None, Query(alias="from")]
ToDay = Annotated[date | None, Query(alias="to")]
PageNumber = Annotated[int, Query(alias="page", ge=-(2**31), le=2**31 - 1)]
PageSize = Annotated[int, Query(alias="pageSize", ge=-(2**31), le=2**31 - 1)]
EntryId = Annotated[UUID, Path(alias="id")]

router = APIRouter(prefix="/setup/expenses", tags=["Central expenses"], route_class=SetupRoute)


def _saved(result: ExpenseSaved) -> Response:
    return respond(ExpenseSavedDto(id=result.id, version=result.version))


@router.get(
    "/ledger",
    operation_id="GetExpenseLedger",
    response_model=ExpenseLedgerDto,
    responses=problem_responses(400, 403),
)
async def get_ledger(
    *,
    caller: CallerDep,
    c: ContainerDep,
    from_date: FromDay = None,
    to_date: ToDay = None,
    source: str | None = None,
    q: str | None = None,
    page: PageNumber = 1,
    page_size: PageSize = 100,
) -> Response:
    ledger = await c.get_expense_ledger.execute(
        GetExpenseLedgerQuery(caller, from_date, to_date, source, q, page, page_size)
    )
    return respond(ExpenseLedgerDto.from_record(ledger))


@router.get(
    "/options",
    operation_id="GetExpenseOptions",
    response_model=ExpenseOptionsDto,
    responses=problem_responses(400, 403),
)
async def get_options(caller: CallerDep, c: ContainerDep, day: Day = None) -> Response:
    options = await c.get_expense_options.execute(GetExpenseOptionsQuery(caller, day))
    return respond(ExpenseOptionsDto.from_record(options))


@router.post(
    "/entries",
    operation_id="RecordExpense",
    response_model=ExpenseRecordedDto,
    responses=problem_responses(400, 403, 409),
)
async def record_expense(body: RecordExpense, caller: CallerDep, c: ContainerDep) -> Response:
    allocations = (
        None
        if body.allocations is None
        else tuple(ExpenseAllocation(a.vehicle_id, a.amount) for a in body.allocations)
    )
    result = await c.record_expense.execute(
        RecordExpenseCommand(
            caller,
            body.id,
            body.entry_date,
            body.expense_item_id,
            body.units,
            body.unit_amount,
            body.note,
            allocations,
        )
    )
    return respond(ExpenseRecordedDto(ids=list(result.ids), total=result.total))


@router.put(
    "/entries/{id:uuid}",
    operation_id="ChangeExpense",
    response_model=ExpenseSavedDto,
    responses=problem_responses(400, 403, 404, 409),
)
async def change_expense(
    entry_id: EntryId, body: ChangeExpense, caller: CallerDep, c: ContainerDep
) -> Response:
    result = await c.change_expense.execute(
        ChangeExpenseCommand(
            caller,
            entry_id,
            body.entry_date,
            body.vehicle_id,
            body.expense_item_id,
            body.units,
            body.unit_amount,
            body.note,
            body.version,
        )
    )
    return _saved(result)


@router.post(
    "/entries/{id:uuid}/remove",
    operation_id="RemoveExpense",
    response_model=ExpenseSavedDto,
    responses=problem_responses(400, 403, 404, 409),
)
async def remove_expense(
    entry_id: EntryId, body: RemoveExpense, caller: CallerDep, c: ContainerDep
) -> Response:
    result = await c.remove_expense.execute(
        RemoveExpenseCommand(caller, entry_id, body.version, body.reason)
    )
    return _saved(result)


@router.get(
    "/export",
    operation_id="ExportExpenseLedger",
    response_class=Response,
    responses={
        200: {"description": "The file", "content": {XLSX_CONTENT_TYPE: {}, PDF_CONTENT_TYPE: {}}},
        **problem_responses(400, 403),
    },
)
async def export_ledger(
    *,
    caller: CallerDep,
    c: ContainerDep,
    from_date: FromDay = None,
    to_date: ToDay = None,
    source: str | None = None,
    q: str | None = None,
    format: str | None = None,
) -> Response:
    file = await c.export_expense_ledger.execute(
        ExportExpenseLedgerQuery(caller, from_date, to_date, source, q, format)
    )
    return file_response(file)
