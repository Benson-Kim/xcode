"""Access and people routes (``docs/06-http-contract.md`` sections 2.2 and 2.12.2). Each
handler builds the command, tells one use case and maps the outcome; the routines decide every
rule."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Path, Query
from starlette.responses import Response

from ...application.access.create_person import CreatePersonCommand
from ...application.access.delete_access_role import DeleteAccessRoleCommand
from ...application.access.delete_person import DeletePersonCommand
from ...application.access.erase_person import ErasePersonCommand
from ...application.access.get_access_catalog import GetAccessCatalogQuery
from ...application.access.get_my_scope import GetMyScopeQuery
from ...application.access.get_person import GetPersonQuery
from ...application.access.get_scope_options import GetScopeOptionsQuery
from ...application.access.invite_person import InvitePersonCommand
from ...application.access.list_access_roles import ListAccessRolesQuery
from ...application.access.list_people import ListPeopleQuery
from ...application.access.remove_person_device import RemovePersonDeviceCommand
from ...application.access.request_account_deletion import RequestAccountDeletionCommand
from ...application.access.require_pin_reset import RequirePinResetCommand
from ...application.access.save_access_role import SaveAccessRoleCommand
from ...application.access.set_person_active import SetPersonActiveCommand
from ...application.access.sign_out_person import SignOutPersonCommand
from ...application.access.update_person import UpdatePersonCommand
from ...application.caller import Caller
from ...container import Container
from ..dependencies import container, current_caller
from ..responses import respond
from ..routing import SetupRoute
from ..schemas.access import (
    AccessRole,
    IdResponse,
    MyScope,
    PermissionGroup,
    PersonDetailDto,
    PersonDto,
    PersonErasureRequest,
    PersonLifecycleRequest,
    SaveAccessRole,
    SavePerson,
    ScopeOptions,
    UpdateAccessRole,
)
from ..schemas.common import Page, problem_responses

CallerDep = Annotated[Caller, Depends(current_caller)]
ContainerDep = Annotated[Container, Depends(container)]
PageNumber = Annotated[int, Query(alias="page", ge=-(2**31), le=2**31 - 1)]
PageSize = Annotated[int, Query(alias="pageSize", ge=-(2**31), le=2**31 - 1)]
PersonId = Annotated[UUID, Path(alias="id")]
RoleId = Annotated[UUID, Path(alias="id")]
DeviceId = Annotated[UUID, Path(alias="deviceId")]

router = APIRouter(prefix="/setup", tags=["Setup"], route_class=SetupRoute)


@router.get(
    "/access/catalog",
    operation_id="GetAccessCatalog",
    response_model=list[PermissionGroup],
    responses=problem_responses(403),
)
async def get_access_catalog(caller: CallerDep, c: ContainerDep) -> Response:
    groups = await c.get_access_catalog.execute(GetAccessCatalogQuery(caller))
    return respond([PermissionGroup.from_record(group) for group in groups])


@router.get(
    "/access/roles",
    operation_id="ListAccessRoles",
    response_model=list[AccessRole],
    responses=problem_responses(403),
)
async def list_access_roles(caller: CallerDep, c: ContainerDep) -> Response:
    roles = await c.list_access_roles.execute(ListAccessRolesQuery(caller))
    return respond([AccessRole.from_record(role) for role in roles])


@router.post(
    "/access/roles",
    operation_id="CreateAccessRole",
    response_model=AccessRole,
    responses=problem_responses(400, 403),
)
async def create_access_role(body: SaveAccessRole, caller: CallerDep, c: ContainerDep) -> Response:
    """A custom role. The name is unique ignoring case and is not a built-in role's; the
    permissions are catalogue keys the caller holds, and come back with their dependencies."""
    role = await c.save_access_role.execute(
        SaveAccessRoleCommand(caller, None, body.name, body.permission_keys())
    )
    return respond(AccessRole.from_record(role))


@router.put(
    "/access/roles/{id:uuid}",
    operation_id="UpdateAccessRole",
    response_model=AccessRole,
    responses=problem_responses(400, 403, 404, 409),
)
async def update_access_role(
    role_id: RoleId, body: UpdateAccessRole, caller: CallerDep, c: ContainerDep
) -> Response:
    """Rename a custom role or change its permissions at the version the caller saw: 409 only
    for a stale version. Everyone holding the role signs in again to get the change."""
    role = await c.save_access_role.execute(
        SaveAccessRoleCommand(caller, role_id, body.name, body.permission_keys(), body.version)
    )
    return respond(AccessRole.from_record(role))


@router.delete(
    "/access/roles/{id:uuid}",
    operation_id="DeleteAccessRole",
    response_model=IdResponse,
    responses=problem_responses(400, 403, 404, 409),
)
async def delete_access_role(role_id: RoleId, caller: CallerDep, c: ContainerDep) -> Response:
    """A custom role nobody holds, active or blocked; 409 says how many people hold it."""
    result = await c.delete_access_role.execute(DeleteAccessRoleCommand(caller, role_id))
    return respond(IdResponse(id=result.id))


@router.get(
    "/access/scope-options",
    operation_id="GetAccessScopeOptions",
    response_model=ScopeOptions,
    responses=problem_responses(403),
)
async def get_scope_options(caller: CallerDep, c: ContainerDep) -> Response:
    options = await c.get_scope_options.execute(GetScopeOptionsQuery(caller))
    return respond(ScopeOptions.from_record(options))


@router.get(
    "/access/me",
    operation_id="GetMyAccessScope",
    response_model=MyScope,
    responses=problem_responses(403),
)
async def get_my_scope(caller: CallerDep, c: ContainerDep) -> Response:
    scope = await c.get_my_scope.execute(GetMyScopeQuery(caller))
    return respond(MyScope.from_record(scope))


@router.post(
    "/me/deletion-request",
    operation_id="RequestMyAccountDeletion",
    status_code=202,
    responses=problem_responses(403),
)
async def request_account_deletion(caller: CallerDep, c: ContainerDep) -> Response:
    """Delete my account: record the caller's own request and notify the administrators who can
    block members. Always answers 202 with no body; a repeat within 24 hours records nothing and
    notifies no one, so the reply never reveals whether a request was already made."""
    await c.request_account_deletion.execute(RequestAccountDeletionCommand(caller))
    return Response(status_code=202)


@router.get(
    "/people",
    operation_id="ListPeople",
    response_model=Page[PersonDto],
    responses=problem_responses(400, 403),
)
async def list_people(
    *,
    caller: CallerDep,
    c: ContainerDep,
    page: PageNumber = 1,
    page_size: PageSize = 25,
    role: str | None = None,
    status: str | None = None,
) -> Response:
    people = await c.list_people.execute(ListPeopleQuery(caller, page, page_size, role, status))
    return respond(
        Page[PersonDto](
            items=[PersonDto.from_record(person) for person in people.items],
            page_number=page,
            page_size=page_size,
            total=people.total,
        )
    )


@router.get(
    "/people/{id:uuid}",
    operation_id="GetPerson",
    response_model=PersonDetailDto,
    responses=problem_responses(403, 404),
)
async def get_person(person_id: PersonId, caller: CallerDep, c: ContainerDep) -> Response:
    person = await c.get_person.execute(GetPersonQuery(caller, person_id))
    return respond(PersonDetailDto.from_record(person))


@router.post(
    "/people",
    operation_id="CreatePerson",
    response_model=IdResponse,
    responses=problem_responses(400, 403, 409),
)
async def create_person(body: SavePerson, caller: CallerDep, c: ContainerDep) -> Response:
    result = await c.create_person.execute(CreatePersonCommand(caller, body.details()))
    return respond(IdResponse(id=result.id))


@router.put(
    "/people/{id:uuid}",
    operation_id="UpdatePerson",
    response_model=IdResponse,
    responses=problem_responses(400, 403, 404, 409),
)
async def update_person(
    person_id: PersonId,
    body: SavePerson,
    caller: CallerDep,
    c: ContainerDep,
) -> Response:
    result = await c.update_person.execute(
        UpdatePersonCommand(caller, person_id, body.details(), body.version)
    )
    return respond(IdResponse(id=result.id))


@router.delete(
    "/people/{id:uuid}",
    operation_id="DeletePerson",
    response_model=IdResponse,
    responses=problem_responses(403, 404, 409),
)
async def delete_person(person_id: PersonId, caller: CallerDep, c: ContainerDep) -> Response:
    """Permanent, and only for a person nothing refers to (409 otherwise: block them instead).
    The account goes too when they belong to no other organization."""
    result = await c.delete_person.execute(DeletePersonCommand(caller, person_id))
    return respond(IdResponse(id=result.id))


OptionalLifecycle = Annotated[PersonLifecycleRequest | None, Body()]


@router.post(
    "/people/{id:uuid}/activate",
    operation_id="ActivatePerson",
    response_model=IdResponse,
    responses=problem_responses(400, 403, 404, 409),
)
async def activate_person(
    person_id: PersonId,
    caller: CallerDep,
    c: ContainerDep,
    body: OptionalLifecycle = None,
) -> Response:
    return await _set_active(c, caller, person_id, True, body)


@router.post(
    "/people/{id:uuid}/deactivate",
    operation_id="DeactivatePerson",
    response_model=IdResponse,
    responses=problem_responses(400, 403, 404, 409),
)
async def deactivate_person(
    person_id: PersonId,
    caller: CallerDep,
    c: ContainerDep,
    body: OptionalLifecycle = None,
) -> Response:
    return await _set_active(c, caller, person_id, False, body)


async def _set_active(
    c: Container, caller: Caller, user_id: UUID, active: bool, body: PersonLifecycleRequest | None
) -> Response:
    lifecycle = body or PersonLifecycleRequest()
    result = await c.set_person_active.execute(
        SetPersonActiveCommand(caller, user_id, active, lifecycle.version, lifecycle.reason)
    )
    return respond(IdResponse(id=result.id))


@router.post(
    "/people/{id:uuid}/erasure",
    operation_id="ErasePerson",
    response_model=IdResponse,
    responses=problem_responses(400, 403, 404, 409),
)
async def erase_person(
    person_id: PersonId,
    body: PersonErasureRequest,
    caller: CallerDep,
    c: ContainerDep,
) -> Response:
    """Irreversible: the person's name, email and mobile number are erased from this
    organization and its history. The person must be blocked and belong to no other
    organization; a repeat on an erased person changes nothing."""
    result = await c.erase_person.execute(
        ErasePersonCommand(caller, person_id, body.version, body.reason)
    )
    return respond(IdResponse(id=result.id))


@router.post(
    "/people/{id:uuid}/sign-out",
    operation_id="SignOutPerson",
    response_model=IdResponse,
    responses=problem_responses(400, 403, 404),
)
async def sign_out_person(person_id: PersonId, caller: CallerDep, c: ContainerDep) -> Response:
    result = await c.sign_out_person.execute(SignOutPersonCommand(caller, person_id))
    return respond(IdResponse(id=result.id))


@router.post(
    "/people/{id:uuid}/pin-reset",
    operation_id="RequirePersonPinReset",
    response_model=IdResponse,
    responses=problem_responses(400, 403, 404),
)
async def require_pin_reset(person_id: PersonId, caller: CallerDep, c: ContainerDep) -> Response:
    result = await c.require_pin_reset.execute(RequirePinResetCommand(caller, person_id))
    return respond(IdResponse(id=result.id))


@router.post(
    "/people/{id:uuid}/invitation",
    operation_id="InvitePerson",
    response_model=IdResponse,
    responses=problem_responses(400, 403, 404),
)
async def invite_person(person_id: PersonId, caller: CallerDep, c: ContainerDep) -> Response:
    """Send again: a fresh link and code replace any pending invitation. The body is empty;
    the routine decides who may be invited and refuses one who needs none."""
    result = await c.invite_person.execute(InvitePersonCommand(caller, person_id))
    return respond(IdResponse(id=result.id))


@router.post(
    "/people/{id:uuid}/trusted-devices/{deviceId:uuid}/remove",
    operation_id="RemovePersonDevice",
    response_model=IdResponse,
    responses=problem_responses(400, 403, 404),
)
async def remove_person_device(
    person_id: PersonId, device_id: DeviceId, caller: CallerDep, c: ContainerDep
) -> Response:
    result = await c.remove_person_device.execute(
        RemovePersonDeviceCommand(caller, person_id, device_id)
    )
    return respond(IdResponse(id=result.id))
