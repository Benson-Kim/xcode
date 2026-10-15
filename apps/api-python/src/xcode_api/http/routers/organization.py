"""Organization settings, logo, appearance and preferences routes (``docs/06-http-contract.md``
section 2.9, tag ``Organization``). The section save answers the two organization refusals as
plain ``{detail}`` bodies (the message catalogue marks them); everything else is a problem."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from starlette.responses import Response

from ...application.caller import Caller
from ...application.organization.delete_organization_logo import DeleteOrganizationLogoCommand
from ...application.organization.get_appearance import GetAppearanceQuery
from ...application.organization.get_organization_settings import GetOrganizationSettingsQuery
from ...application.organization.get_preferences import GetPreferencesQuery
from ...application.organization.update_organization_logo import UpdateOrganizationLogoCommand
from ...application.organization.update_organization_settings import (
    UpdateOrganizationSettingsCommand,
)
from ...application.organization.update_preferences import UpdatePreferencesCommand
from ...container import Container
from ...domain.tenancy import PreferenceChoices
from ..dependencies import container, current_caller
from ..responses import respond
from ..routing import SetupRoute
from ..schemas.common import problem_responses
from ..schemas.organization import (
    AppearanceResponse,
    LogoResponse,
    OrganizationSettingsResponse,
    PreferencesResponse,
    SaveLogo,
    SaveOrganizationSettings,
    SaveUserPreferences,
    SettingsSectionResponse,
    UserPreferenceDto,
)

CallerDep = Annotated[Caller, Depends(current_caller)]
ContainerDep = Annotated[Container, Depends(container)]

router = APIRouter(prefix="/setup", tags=["Organization"], route_class=SetupRoute)


@router.get(
    "/organization/settings",
    operation_id="GetOrganizationSettings",
    response_model=OrganizationSettingsResponse,
    responses=problem_responses(400, 403),
)
async def get_organization_settings(caller: CallerDep, c: ContainerDep) -> Response:
    settings = await c.get_organization_settings.execute(GetOrganizationSettingsQuery(caller))
    return respond(OrganizationSettingsResponse.from_record(settings))


@router.put(
    "/organization/settings/{section}",
    operation_id="UpdateOrganizationSettings",
    response_model=SettingsSectionResponse,
    responses=problem_responses(400, 403, 404, 409),
)
async def update_organization_settings(
    section: str, body: SaveOrganizationSettings, caller: CallerDep, c: ContainerDep
) -> Response:
    await c.update_organization_settings.execute(
        UpdateOrganizationSettingsCommand(
            caller, section, body.document_value(section), body.reason
        )
    )
    return respond(SettingsSectionResponse(section=section))


@router.put(
    "/organization/logo",
    operation_id="UpdateOrganizationLogo",
    response_model=LogoResponse,
    responses=problem_responses(400, 403, 409),
)
async def update_organization_logo(body: SaveLogo, caller: CallerDep, c: ContainerDep) -> Response:
    logo = await c.update_organization_logo.execute(
        UpdateOrganizationLogoCommand(caller, body.data_url, body.reason)
    )
    return respond(LogoResponse(logo=logo))


@router.delete(
    "/organization/logo",
    operation_id="DeleteOrganizationLogo",
    response_model=LogoResponse,
    responses=problem_responses(400, 403, 409),
)
async def delete_organization_logo(
    caller: CallerDep, c: ContainerDep, reason: Annotated[str | None, Query()] = None
) -> Response:
    await c.delete_organization_logo.execute(DeleteOrganizationLogoCommand(caller, reason))
    return respond(LogoResponse(logo=None))


@router.get(
    "/appearance",
    operation_id="GetAppearance",
    response_model=AppearanceResponse,
    responses=problem_responses(400, 403),
)
async def get_appearance(caller: CallerDep, c: ContainerDep) -> Response:
    appearance = await c.get_appearance.execute(GetAppearanceQuery(caller))
    return respond(AppearanceResponse.from_record(appearance))


@router.get(
    "/preferences",
    operation_id="GetUserPreferences",
    response_model=PreferencesResponse,
    responses=problem_responses(403),
)
async def get_preferences(caller: CallerDep, c: ContainerDep) -> Response:
    preferences = await c.get_preferences.execute(GetPreferencesQuery(caller))
    return respond(PreferencesResponse.from_record(preferences))


@router.put(
    "/preferences",
    operation_id="UpdateUserPreferences",
    response_model=UserPreferenceDto,
    responses=problem_responses(400, 403),
)
async def update_preferences(
    body: SaveUserPreferences, caller: CallerDep, c: ContainerDep
) -> Response:
    saved = await c.update_preferences.execute(
        UpdatePreferencesCommand(
            caller,
            PreferenceChoices(
                locale=body.locale,
                time_zone=body.time_zone,
                hour12=body.hour12,
                theme_mode=body.theme_mode,
                reduced_motion=body.reduced_motion,
                font_scale=body.font_scale,
            ),
        )
    )
    return respond(UserPreferenceDto.from_record(saved))
