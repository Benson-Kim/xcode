"""The change-log route (``docs/06-http-contract.md`` section 2.5)."""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from starlette.responses import Response

from ...application.caller import Caller
from ...application.organization.list_history import ListHistoryQuery
from ...container import Container
from ...domain.tenancy import HistoryFilter
from ..dependencies import container, current_caller
from ..responses import respond
from ..routing import SetupRoute
from ..schemas.common import problem_responses
from ..schemas.history import HistoryPage

CallerDep = Annotated[Caller, Depends(current_caller)]
ContainerDep = Annotated[Container, Depends(container)]
Int32 = Annotated[int, Query(ge=-(2**31), le=2**31 - 1)]

router = APIRouter(prefix="/setup", tags=["Setup"], route_class=SetupRoute)


@router.get(
    "/history",
    operation_id="ListSetupHistory",
    response_model=HistoryPage,
    responses=problem_responses(400, 403),
)
async def list_history(
    *,
    caller: CallerDep,
    c: ContainerDep,
    page: Int32 = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=-(2**31), le=2**31 - 1)] = 25,
    section: str | None = None,
    from_date: Annotated[date | None, Query(alias="from")] = None,
    to_date: Annotated[date | None, Query(alias="to")] = None,
    text: str | None = None,
    before: Annotated[int | None, Query(ge=-(2**63), le=2**63 - 1)] = None,
    include_total: Annotated[bool, Query(alias="includeTotal")] = True,
) -> Response:
    history = await c.list_history.execute(
        ListHistoryQuery(
            caller,
            HistoryFilter(
                page=page,
                page_size=page_size,
                section=section,
                from_date=from_date,
                to_date=to_date,
                text=text,
                before=before,
                include_total=include_total,
            ),
        )
    )
    return respond(HistoryPage.from_page(history, page, page_size))
