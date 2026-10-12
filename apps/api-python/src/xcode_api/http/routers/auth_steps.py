"""The number-first sign-in routes and the profile's PIN and device routes
(``docs/06-http-contract.md`` 2.12.1, ``docs/07-auth.md`` section 12). New in Python; the
thirteen released routes of ``auth.py`` stay as they are for v2.11 phones.

Every route is rate limited before anything else; the routes that check a PIN are also
throttled per address and per device. A body that does not parse into the route's fields is
the ``invalid_request`` step envelope, so every answer below 500 but the empty 401, 404 and
429 is JSON with a string ``status``.
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from types import MappingProxyType
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Request
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from starlette.exceptions import HTTPException
from starlette.responses import Response

from ...application.auth.change_pin import ChangePinCommand
from ...application.auth.complete_pin import CompletePinCommand
from ...application.auth.enter_code import EnterCodeCommand
from ...application.auth.enter_pin import EnterPinCommand
from ...application.auth.list_trusted_devices import ListTrustedDevicesQuery
from ...application.auth.remove_trusted_device import RemoveTrustedDeviceCommand
from ...application.auth.request_code import RequestCodeCommand
from ...application.auth.resend_code import ResendCodeCommand
from ...application.auth.start_sign_in import StartSignInCommand
from ...domain.errors import NotFound
from ...domain.identity import AuthEnvelope, CodePurpose, EnvelopeStatus, Principal
from ...domain.policies import invalid_request_answer
from ..dependencies import (
    auth_rate_limit,
    container,
    current_principal,
    pin_address_limit,
    pin_rate_limit,
    request_id,
)
from ..responses import JsonResponse
from ..schemas.auth_steps import (
    ChangePinRequest,
    CodeStepRequest,
    ForgotPinRequest,
    NewPinRequest,
    PinRequest,
    ResendRequest,
    StartRequest,
    StepResponse,
    TrustedDeviceResponse,
)
from .auth import HTTP_STATUS

STEP_STATUS = MappingProxyType(
    {
        **HTTP_STATUS,
        EnvelopeStatus.PIN_REQUIRED: 200,
        EnvelopeStatus.PIN_LOCKED: 423,
        EnvelopeStatus.BLOCKED: 403,
        EnvelopeStatus.CODE_RESENT: 202,
        EnvelopeStatus.PIN_CHANGED: 200,
    }
)

_DESCRIPTIONS = MappingProxyType(
    {
        202: "Accepted (verification_required or code_resent)",
        400: "invalid_request or invalid_pin",
        401: "authentication_failed",
        403: "blocked",
        423: "pin_locked",
        503: "service_unavailable",
    }
)
_EMPTY = MappingProxyType(
    {
        401: "Missing, invalid or revoked access token (empty body)",
        404: "Not one of your live devices (empty body)",
        429: "Too many requests (empty body, Retry-After)",
    }
)


def step_response(envelope: AuthEnvelope) -> Response:
    status = STEP_STATUS[envelope.status]
    body = StepResponse.from_envelope(envelope).model_dump(mode="json", by_alias=True)
    headers = {"WWW-Authenticate": "Bearer"} if status == 401 else None
    return JsonResponse(body, status_code=status, headers=headers)


class _StepRoute(APIRoute):
    """A body that is not JSON, not an object of the route's types, or a ``null`` field is the
    ``invalid_request`` step envelope; FastAPI refuses such a body before any dependency runs,
    so the route charges the rate limit itself on that path."""

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        handler = super().get_route_handler()

        async def route(request: Request) -> Response:
            try:
                return await handler(request)
            except RequestValidationError:
                return await _invalid_request(request)
            except HTTPException as exc:
                if exc.status_code == 400:
                    return await _invalid_request(request)
                raise

        return route


async def _invalid_request(request: Request) -> Response:
    await auth_rate_limit(request)
    return step_response(invalid_request_answer())


def _documented(*statuses: int) -> dict[int | str, dict[str, Any]]:
    responses: dict[int | str, dict[str, Any]] = {
        status: {"model": StepResponse, "description": _DESCRIPTIONS[status]} for status in statuses
    }
    responses[429] = {"description": _EMPTY[429]}
    return responses


def _empty(*statuses: int) -> dict[int | str, dict[str, Any]]:
    return {status: {"description": _EMPTY[status]} for status in statuses}


router = APIRouter(route_class=_StepRoute)
_LIMITED = [Depends(auth_rate_limit)]


@router.post(
    "/auth/start",
    response_model=StepResponse,
    responses=_documented(202, 400, 403, 423),
    dependencies=_LIMITED,
)
async def start(request: Request, body: StartRequest) -> Response:
    if not body.shape_valid():
        return step_response(invalid_request_answer())
    envelope = await container(request).start_sign_in.execute(
        StartSignInCommand(
            request_id(request), body.phone_number, body.device_id, body.token, body.name
        )
    )
    return step_response(envelope)


@router.post(
    "/auth/pin",
    response_model=StepResponse,
    responses=_documented(202, 400, 401, 403, 423, 503),
    dependencies=_LIMITED,
)
async def pin(request: Request, body: PinRequest) -> Response:
    await pin_rate_limit(request, body.device_id)
    if not body.shape_valid():
        return step_response(invalid_request_answer())
    envelope = await container(request).enter_pin.execute(
        EnterPinCommand(
            request_id(request),
            body.phone_number,
            body.device_id,
            body.token,
            body.name,
            body.pin,
        )
    )
    return step_response(envelope)


@router.post(
    "/auth/code",
    response_model=StepResponse,
    responses=_documented(202, 400, 401),
    dependencies=_LIMITED,
)
async def code(request: Request, body: CodeStepRequest) -> Response:
    if not body.shape_valid():
        return step_response(invalid_request_answer())
    envelope = await container(request).enter_code.execute(
        EnterCodeCommand(
            request_id(request),
            body.phone_number,
            body.device_id,
            body.name,
            CodePurpose(body.purpose),
            body.code,
            body.trust_device,
        )
    )
    return step_response(envelope)


@router.post(
    "/auth/code/resend",
    response_model=StepResponse,
    responses=_documented(202, 400),
    dependencies=_LIMITED,
)
async def resend_code(request: Request, body: ResendRequest) -> Response:
    if not body.shape_valid():
        return step_response(invalid_request_answer())
    envelope = await container(request).resend_code.execute(
        ResendCodeCommand(
            request_id(request),
            body.phone_number,
            body.device_id,
            body.name,
            CodePurpose(body.purpose),
        )
    )
    return step_response(envelope)


@router.post(
    "/auth/pin/forgot",
    response_model=StepResponse,
    responses=_documented(202, 400),
    dependencies=_LIMITED,
)
async def forgot_pin(request: Request, body: ForgotPinRequest) -> Response:
    if not body.shape_valid():
        return step_response(invalid_request_answer())
    envelope = await container(request).request_code.execute(
        RequestCodeCommand(
            request_id(request),
            body.phone_number,
            body.device_id,
            CodePurpose.PIN_RESET,
            device_name=body.name,
            step=True,
        )
    )
    return step_response(envelope)


@router.post(
    "/auth/pin/new",
    response_model=StepResponse,
    responses=_documented(400, 401),
    dependencies=_LIMITED,
)
async def new_pin(request: Request, body: NewPinRequest) -> Response:
    if not body.shape_valid():
        return step_response(invalid_request_answer())
    envelope = await container(request).complete_pin.execute(
        CompletePinCommand(
            request_id(request),
            body.phone_number,
            body.pin,
            body.code,
            body.device_id,
            CodePurpose(body.purpose),
            device_name=body.name,
            trust=body.trust_device,
            step=True,
        )
    )
    return step_response(envelope)


@router.post(
    "/auth/pin/change",
    response_model=StepResponse,
    responses={**_documented(400, 401, 423), **_empty(401)},
    dependencies=[Depends(auth_rate_limit), Depends(pin_address_limit)],
)
async def change_pin(
    request: Request,
    body: ChangePinRequest,
    principal: Annotated[Principal, Depends(current_principal)],
) -> Response:
    await pin_rate_limit(request, principal.device_id, address=False)
    if not body.shape_valid():
        return step_response(invalid_request_answer())
    envelope = await container(request).change_pin.execute(
        ChangePinCommand(
            request_id(request),
            principal.user_id,
            principal.device_id,
            body.current_pin,
            body.new_pin,
        )
    )
    return step_response(envelope)


@router.get(
    "/auth/trusted-devices",
    response_model=list[TrustedDeviceResponse],
    responses=_empty(401, 429),
    dependencies=_LIMITED,
)
async def trusted_devices(
    request: Request,
    principal: Annotated[Principal, Depends(current_principal)],
) -> Response:
    views = await container(request).list_trusted_devices.execute(
        ListTrustedDevicesQuery(principal.user_id, principal.device_id)
    )
    return JsonResponse(
        [TrustedDeviceResponse.from_view(v).model_dump(mode="json", by_alias=True) for v in views]
    )


@router.post(
    "/auth/trusted-devices/{id:uuid}/remove",
    response_model=StepResponse,
    responses=_empty(401, 404, 429),
    dependencies=_LIMITED,
)
async def remove_trusted_device(
    request: Request,
    row_id: Annotated[UUID, Path(alias="id")],
    principal: Annotated[Principal, Depends(current_principal)],
) -> Response:
    try:
        envelope = await container(request).remove_trusted_device.execute(
            RemoveTrustedDeviceCommand(request_id(request), principal.user_id, row_id)
        )
    except NotFound:
        return Response(status_code=404)
    return step_response(envelope)
