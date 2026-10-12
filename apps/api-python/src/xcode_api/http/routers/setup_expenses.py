"""Expense catalogue routes (``docs/06-http-contract.md`` section 2.6). Each
handler builds the command, tells one use case and maps the outcome; the routines decide every
rule. Stop and restore read no body."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query
from starlette.responses import Response

from ...application.caller import Caller
from ...application.setup.create_expense_category import CreateExpenseCategoryCommand
from ...application.setup.create_expense_item import CreateExpenseItemCommand
from ...application.setup.create_expense_main_category import CreateExpenseMainCategoryCommand
from ...application.setup.list_expense_categories import ListExpenseCategoriesQuery
from ...application.setup.list_expense_item_options import ListExpenseItemOptionsQuery
from ...application.setup.list_expense_main_categories import ListExpenseMainCategoriesQuery
from ...application.setup.rename_expense_item import RenameExpenseItemCommand
from ...application.setup.rename_expense_main_category import RenameExpenseMainCategoryCommand
from ...application.setup.set_expense_category_stopped import SetExpenseCategoryStoppedCommand
from ...application.setup.set_expense_item_stopped import SetExpenseItemStoppedCommand
from ...application.setup.update_expense_category import UpdateExpenseCategoryCommand
from ...container import Container
from ..dependencies import container, current_caller
from ..responses import respond
from ..routing import SetupRoute
from ..schemas.access import IdResponse
from ..schemas.common import Page, problem_responses
from ..schemas.setup import (
    ExpenseCategoryDto,
    ExpenseItemOption,
    MainCategoryDto,
    MainCategoryPage,
    SaveExpenseCategory,
    SaveExpenseItem,
    SaveMainCategory,
)

CallerDep = Annotated[Caller, Depends(current_caller)]
ContainerDep = Annotated[Container, Depends(container)]
PageNumber = Annotated[int, Query(alias="page", ge=-(2**31), le=2**31 - 1)]
PageSize = Annotated[int, Query(alias="pageSize", ge=-(2**31), le=2**31 - 1)]
RecordId = Annotated[UUID, Path(alias="id")]

router = APIRouter(prefix="/setup", tags=["Setup"], route_class=SetupRoute)


@router.get(
    "/expense-categories",
    operation_id="ListExpenseCategories",
    response_model=Page[ExpenseCategoryDto],
    responses=problem_responses(400, 403),
)
async def list_expense_categories(
    caller: CallerDep, c: ContainerDep, page: PageNumber = 1, page_size: PageSize = 25
) -> Response:
    categories = await c.list_expense_categories.execute(
        ListExpenseCategoriesQuery(caller, page, page_size)
    )
    return respond(
        Page[ExpenseCategoryDto](
            items=[ExpenseCategoryDto.from_record(category) for category in categories.items],
            page_number=page,
            page_size=page_size,
            total=categories.total,
        )
    )


@router.get(
    "/expense-items/options",
    operation_id="ListExpenseItemOptions",
    response_model=list[ExpenseItemOption],
    responses=problem_responses(403),
)
async def list_expense_item_options(caller: CallerDep, c: ContainerDep) -> Response:
    options = await c.list_expense_item_options.execute(ListExpenseItemOptionsQuery(caller))
    return respond([ExpenseItemOption.from_record(option) for option in options])


@router.post(
    "/expense-categories",
    operation_id="CreateExpenseCategory",
    response_model=IdResponse,
    responses=problem_responses(400, 403, 404),
)
async def create_expense_category(
    body: SaveExpenseCategory, caller: CallerDep, c: ContainerDep
) -> Response:
    result = await c.create_expense_category.execute(
        CreateExpenseCategoryCommand(caller, body.name, body.main_category_id)
    )
    return respond(IdResponse(id=result.id))


@router.put(
    "/expense-categories/{id:uuid}",
    operation_id="UpdateExpenseCategory",
    response_model=IdResponse,
    responses=problem_responses(400, 403, 404),
)
async def update_expense_category(
    category_id: RecordId, body: SaveExpenseCategory, caller: CallerDep, c: ContainerDep
) -> Response:
    result = await c.update_expense_category.execute(
        UpdateExpenseCategoryCommand(
            caller, category_id, body.name, body.main_category_id, body.main_category_given()
        )
    )
    return respond(IdResponse(id=result.id))


@router.post(
    "/expense-categories/{id:uuid}/stop",
    operation_id="StopExpenseCategory",
    response_model=IdResponse,
    responses=problem_responses(400, 403, 404),
)
async def stop_expense_category(
    category_id: RecordId, caller: CallerDep, c: ContainerDep
) -> Response:
    return await _category_stopped(c, caller, category_id, True)


@router.post(
    "/expense-categories/{id:uuid}/restore",
    operation_id="RestoreExpenseCategory",
    response_model=IdResponse,
    responses=problem_responses(400, 403, 404),
)
async def restore_expense_category(
    category_id: RecordId, caller: CallerDep, c: ContainerDep
) -> Response:
    return await _category_stopped(c, caller, category_id, False)


async def _category_stopped(
    c: Container, caller: Caller, category_id: UUID, stopped: bool
) -> Response:
    result = await c.set_expense_category_stopped.execute(
        SetExpenseCategoryStoppedCommand(caller, category_id, stopped)
    )
    return respond(IdResponse(id=result.id))


@router.post(
    "/expense-categories/{id:uuid}/items",
    operation_id="CreateExpenseItem",
    response_model=IdResponse,
    responses=problem_responses(400, 403, 404),
)
async def create_expense_item(
    category_id: RecordId, body: SaveExpenseItem, caller: CallerDep, c: ContainerDep
) -> Response:
    result = await c.create_expense_item.execute(
        CreateExpenseItemCommand(caller, category_id, body.name)
    )
    return respond(IdResponse(id=result.id))


@router.put(
    "/expense-items/{id:uuid}",
    operation_id="RenameExpenseItem",
    response_model=IdResponse,
    responses=problem_responses(400, 403, 404),
)
async def rename_expense_item(
    item_id: RecordId, body: SaveExpenseItem, caller: CallerDep, c: ContainerDep
) -> Response:
    result = await c.rename_expense_item.execute(
        RenameExpenseItemCommand(caller, item_id, body.name)
    )
    return respond(IdResponse(id=result.id))


@router.post(
    "/expense-items/{id:uuid}/stop",
    operation_id="StopExpenseItem",
    response_model=IdResponse,
    responses=problem_responses(400, 403, 404),
)
async def stop_expense_item(item_id: RecordId, caller: CallerDep, c: ContainerDep) -> Response:
    return await _item_stopped(c, caller, item_id, True)


@router.post(
    "/expense-items/{id:uuid}/restore",
    operation_id="RestoreExpenseItem",
    response_model=IdResponse,
    responses=problem_responses(400, 403, 404),
)
async def restore_expense_item(item_id: RecordId, caller: CallerDep, c: ContainerDep) -> Response:
    return await _item_stopped(c, caller, item_id, False)


async def _item_stopped(c: Container, caller: Caller, item_id: UUID, stopped: bool) -> Response:
    result = await c.set_expense_item_stopped.execute(
        SetExpenseItemStoppedCommand(caller, item_id, stopped)
    )
    return respond(IdResponse(id=result.id))


@router.get(
    "/expense-main-categories",
    operation_id="ListExpenseMainCategories",
    response_model=MainCategoryPage,
    responses=problem_responses(400, 403),
)
async def list_expense_main_categories(
    caller: CallerDep, c: ContainerDep, page: PageNumber = 1, page_size: PageSize = 25
) -> Response:
    mains = await c.list_expense_main_categories.execute(
        ListExpenseMainCategoriesQuery(caller, page, page_size)
    )
    return respond(
        MainCategoryPage(
            items=[MainCategoryDto.from_record(main) for main in mains.items],
            page_number=page,
            page_size=page_size,
            total=mains.total,
            categories_without_main=mains.categories_without_main,
        )
    )


@router.post(
    "/expense-main-categories",
    operation_id="CreateExpenseMainCategory",
    response_model=IdResponse,
    responses=problem_responses(400, 403),
)
async def create_expense_main_category(
    body: SaveMainCategory, caller: CallerDep, c: ContainerDep
) -> Response:
    result = await c.create_expense_main_category.execute(
        CreateExpenseMainCategoryCommand(caller, body.name)
    )
    return respond(IdResponse(id=result.id))


@router.put(
    "/expense-main-categories/{id:uuid}",
    operation_id="RenameExpenseMainCategory",
    response_model=IdResponse,
    responses=problem_responses(400, 403, 404),
)
async def rename_expense_main_category(
    main_category_id: RecordId, body: SaveMainCategory, caller: CallerDep, c: ContainerDep
) -> Response:
    result = await c.rename_expense_main_category.execute(
        RenameExpenseMainCategoryCommand(caller, main_category_id, body.name)
    )
    return respond(IdResponse(id=result.id))
