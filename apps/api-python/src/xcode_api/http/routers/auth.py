"""The thirteen ``/auth`` routes (``docs/06-http-contract.md`` section 2.1).

Every route is rate limited before anything else, the two bearer routes included (as the
.NET limiter middleware ran before authentication). Anonymous routes
pre-validate the six request strings and answer ``400 invalid_request`` before any lookup;
a body that does not parse into the six strings gets the same envelope, so every answer
below 500 is JSON with a string ``status``.
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from types import MappingProxyType
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Request
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from starlette.exceptions import HTTPException
from starlette.responses import Response

from ...application.auth.complete_pin import CompletePinCommand
from ...application.auth.get_session import GetSessionQuery
from ...application.auth.refresh import RefreshCommand
from ...application.auth.request_code import RequestCodeCommand
from ...application.auth.resolve_session import ResolvedSession
from ...application.auth.revoke_device import RevokeDeviceCommand
from ...application.auth.sign_in import SignInCommand
from ...application.auth.sign_out import SignOutCommand
from ...application.auth.verify_code import VerifyCodeCommand
from ...application.auth.verify_device import VerifyDeviceCommand
from ...domain.identity import AuthEnvelope, CodePurpose, EnvelopeStatus, Principal
from ...domain.policies import invalid_request_answer
from ..dependencies import (
    auth_rate_limit,
    container,
    current_principal,
    current_session,
    pin_rate_limit,
    request_id,
)
from ..responses import JsonResponse
from ..schemas.auth import (
    AuthRequestFields,
    AuthResponse,
    AuthSessionResponse,
    PinResetCodeRequest,
    PinResetCompleteRequest,
    PinResetVerifyRequest,
    RefreshRequest,
    SetupPinCodeRequest,
    SetupPinCompleteRequest,
    SetupPinVerifyRequest,
    SignInRequest,
    SignOutRequest,
    UnlockRequest,
    VerifyDeviceRequest,
)

HTTP_STATUS = MappingProxyType(
    {
        EnvelopeStatus.AUTHENTICATED: 200,
        EnvelopeStatus.VERIFICATION_REQUIRED: 202,
        EnvelopeStatus.CHECK_EMAIL: 202,
        EnvelopeStatus.CODE_VERIFIED: 200,
        EnvelopeStatus.PAUSED: 423,
        EnvelopeStatus.AUTHENTICATION_FAILED: 401,
        EnvelopeStatus.INVALID_PIN: 400,
        EnvelopeStatus.INVALID_REQUEST: 400,
        EnvelopeStatus.SIGNED_OUT: 200,
        EnvelopeStatus.DEVICE_REVOKED: 200,
        EnvelopeStatus.SERVICE_UNAVAILABLE: 503,
    }
)

_DESCRIPTIONS = MappingProxyType(
    {
        202: "Accepted (verification_required or check_email)",
        400: "invalid_request or invalid_pin",
        401: "authentication_failed",
        423: "paused",
        503: "service_unavailable",
    }
)
_EMPTY = MappingProxyType(
    {
        401: "Missing, invalid or revoked access token (empty body)",
        403: "Another device's id (empty body)",
        429: "Too many requests (empty body, Retry-After)",
    }
)


AuthJsonResponse = JsonResponse


def envelope_response(envelope: AuthEnvelope) -> Response:
    status = HTTP_STATUS[envelope.status]
    body = AuthResponse.from_envelope(envelope).model_dump(mode="json", by_alias=True)
    headers = {"WWW-Authenticate": "Bearer"} if status == 401 else None
    return AuthJsonResponse(body, status_code=status, headers=headers)


class _AuthRoute(APIRoute):
    """A body that is not JSON, not an object of strings, or a ``null`` field is the
    ``invalid_request`` envelope, never the generic validation problem. FastAPI refuses a
    body that does not parse before any dependency runs, so the route charges the rate limit
    itself on that path (``auth_rate_limit`` charges a request once)."""

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
    return envelope_response(invalid_request_answer())


def _documented(*statuses: int) -> dict[int | str, dict[str, Any]]:
    responses: dict[int | str, dict[str, Any]] = {
        status: {"model": AuthResponse, "description": _DESCRIPTIONS[status]} for status in statuses
    }
    responses[429] = {"description": _EMPTY[429]}
    return responses


def _empty(*statuses: int) -> dict[int | str, dict[str, Any]]:
    return {status: {"description": _EMPTY[status]} for status in statuses}


router = APIRouter(route_class=_AuthRoute)
_LIMITED = [Depends(auth_rate_limit)]


@router.post(
    "/auth/sign-in",
    response_model=AuthResponse,
    responses=_documented(202, 400, 401, 423, 503),
    dependencies=_LIMITED,
)
async def sign_in(request: Request, body: SignInRequest) -> Response:
    return await _sign_in(request, body)


@router.post(
    "/auth/unlock",
    response_model=AuthResponse,
    responses=_documented(202, 400, 401, 423, 503),
    dependencies=_LIMITED,
)
async def unlock(request: Request, body: UnlockRequest) -> Response:
    return await _sign_in(request, body)


@router.post(
    "/auth/verify-device",
    response_model=AuthResponse,
    responses=_documented(400, 401),
    dependencies=_LIMITED,
)
async def verify_device(request: Request, body: VerifyDeviceRequest) -> Response:
    if not body.shape_valid():
        return envelope_response(invalid_request_answer())
    envelope = await container(request).verify_device.execute(
        VerifyDeviceCommand(request_id(request), body.phone_number, body.code, body.device_id)
    )
    return envelope_response(envelope)


@router.post(
    "/auth/setup-pin/request",
    response_model=AuthResponse,
    responses=_documented(202, 400),
    dependencies=_LIMITED,
)
async def setup_pin_request(request: Request, body: SetupPinCodeRequest) -> Response:
    return await _request_code(request, body, CodePurpose.FIRST_SETUP)


@router.post(
    "/auth/setup-pin/verify",
    response_model=AuthResponse,
    responses=_documented(400, 401),
    dependencies=_LIMITED,
)
async def setup_pin_verify(request: Request, body: SetupPinVerifyRequest) -> Response:
    return await _verify_code(request, body, CodePurpose.FIRST_SETUP)


@router.post(
    "/auth/setup-pin/complete",
    response_model=AuthResponse,
    responses=_documented(400, 401),
    dependencies=_LIMITED,
)
async def setup_pin_complete(request: Request, body: SetupPinCompleteRequest) -> Response:
    return await _complete_pin(request, body, CodePurpose.FIRST_SETUP)


@router.post(
    "/auth/pin-reset/request",
    response_model=AuthResponse,
    responses=_documented(202, 400),
    dependencies=_LIMITED,
)
async def pin_reset_request(request: Request, body: PinResetCodeRequest) -> Response:
    return await _request_code(request, body, CodePurpose.PIN_RESET)


@router.post(
    "/auth/pin-reset/verify",
    response_model=AuthResponse,
    responses=_documented(400, 401),
    dependencies=_LIMITED,
)
async def pin_reset_verify(request: Request, body: PinResetVerifyRequest) -> Response:
    return await _verify_code(request, body, CodePurpose.PIN_RESET)


@router.post(
    "/auth/pin-reset/complete",
    response_model=AuthResponse,
    responses=_documented(400, 401),
    dependencies=_LIMITED,
)
async def pin_reset_complete(request: Request, body: PinResetCompleteRequest) -> Response:
    return await _complete_pin(request, body, CodePurpose.PIN_RESET)


@router.post(
    "/auth/refresh",
    response_model=AuthResponse,
    responses=_documented(400, 401),
    dependencies=_LIMITED,
)
async def refresh(request: Request, body: RefreshRequest) -> Response:
    if not body.shape_valid():
        return envelope_response(invalid_request_answer())
    envelope = await container(request).refresh.execute(
        RefreshCommand(request_id(request), body.refresh_token, body.device_id)
    )
    return envelope_response(envelope)


@router.post(
    "/auth/sign-out",
    response_model=AuthResponse,
    responses=_documented(400),
    dependencies=_LIMITED,
)
async def sign_out(request: Request, body: SignOutRequest) -> Response:
    if not body.shape_valid():
        return envelope_response(invalid_request_answer())
    envelope = await container(request).sign_out.execute(
        SignOutCommand(request_id(request), body.refresh_token, body.device_id)
    )
    return envelope_response(envelope)


@router.post(
    "/auth/devices/{id}/revoke",
    response_model=AuthResponse,
    responses=_empty(401, 403, 429),
    dependencies=_LIMITED,
)
async def revoke_device(
    request: Request,
    device: Annotated[str, Path(alias="id")],
    principal: Annotated[Principal, Depends(current_principal)],
) -> Response:
    if device != principal.device_id:
        return Response(status_code=403)
    envelope = await container(request).revoke_device.execute(
        RevokeDeviceCommand(request_id(request), principal.user_id, principal.device_id)
    )
    return envelope_response(envelope)


@router.get(
    "/auth/session",
    response_model=AuthSessionResponse,
    responses=_empty(401, 429),
    dependencies=_LIMITED,
)
async def session(
    request: Request,
    resolved: Annotated[ResolvedSession, Depends(current_session)],
) -> Response:
    view = await container(request).get_session.execute(GetSessionQuery(resolved.claims))
    return AuthJsonResponse(
        AuthSessionResponse.from_view(view).model_dump(mode="json", by_alias=True)
    )


async def _sign_in(request: Request, body: AuthRequestFields) -> Response:
    await pin_rate_limit(request, body.device_id)
    if not body.shape_valid():
        return envelope_response(invalid_request_answer())
    envelope = await container(request).sign_in.execute(
        SignInCommand(request_id(request), body.phone_number, body.pin, body.device_id)
    )
    return envelope_response(envelope)


async def _request_code(
    request: Request, body: AuthRequestFields, purpose: CodePurpose
) -> Response:
    if not body.shape_valid():
        return envelope_response(invalid_request_answer())
    envelope = await container(request).request_code.execute(
        RequestCodeCommand(request_id(request), body.phone_number, body.device_id, purpose)
    )
    return envelope_response(envelope)


async def _verify_code(request: Request, body: AuthRequestFields, purpose: CodePurpose) -> Response:
    if not body.shape_valid():
        return envelope_response(invalid_request_answer())
    envelope = await container(request).verify_code.execute(
        VerifyCodeCommand(
            request_id(request), body.phone_number, body.code, body.device_id, purpose
        )
    )
    return envelope_response(envelope)


async def _complete_pin(
    request: Request, body: AuthRequestFields, purpose: CodePurpose
) -> Response:
    if not body.shape_valid():
        return envelope_response(invalid_request_answer())
    envelope = await container(request).complete_pin.execute(
        CompletePinCommand(
            request_id(request), body.phone_number, body.pin, body.code, body.device_id, purpose
        )
    )
    return envelope_response(envelope)
