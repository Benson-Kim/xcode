"""``TenancyRoutines``: the real ``TenancyRepository``, one typed method per access, people,
change-log and organization routine. Reads are marked idempotent, so only they are retried on
a transient SQLSTATE; every command runs once."""

from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb
from psycopg_pool import AsyncConnectionPool

from ...application.errors import IntegrityBug
from ...domain.tenancy import (
    AccessRole,
    Appearance,
    HistoryPage,
    HistoryQuery,
    LogoRemoval,
    LogoSave,
    MyScope,
    OrganizationSettings,
    PeoplePage,
    PeopleQuery,
    PermissionGroup,
    Person,
    PersonDetails,
    PersonDeviceRemoval,
    PersonLifecycle,
    PersonPinReset,
    PersonQuery,
    PersonSave,
    PersonSignOut,
    Preferences,
    PreferencesSave,
    ScopeOptions,
    SettingsSave,
    TenantContext,
    UserPreferences,
)
from ...domain.values import WriteResult
from ..session import call
from ..types import document, write_result


def _tenant(context: TenantContext) -> tuple[Any, ...]:
    return (context.actor_id, context.organization_id, context.request_id)


def _back_limit(details: PersonDetails) -> tuple[Any, ...]:
    limit = details.back_limit
    if limit is None:
        return (None, None, None)
    return (limit.mode, limit.count, limit.from_date)


class TenancyRoutines:
    """Access, people, change-log and organization routines (``api.access_*``,
    ``api.people_*``, ``api.history_list``, ``api.organization_*``, ``api.preferences_*``)."""

    def __init__(self, pool: AsyncConnectionPool[Any]) -> None:
        self._pool = pool

    async def access_catalog(self, context: TenantContext) -> tuple[PermissionGroup, ...]:
        groups = await self._read("access_catalog_list", *_tenant(context), context.now)
        return tuple(document(g, PermissionGroup, "api.access_catalog_list") for g in groups)

    async def access_roles(self, context: TenantContext) -> tuple[AccessRole, ...]:
        roles = await self._read("access_role_list", *_tenant(context), context.now)
        return tuple(document(r, AccessRole, "api.access_role_list") for r in roles)

    async def scope_options(self, context: TenantContext) -> ScopeOptions:
        value = await self._read("access_scope_options", *_tenant(context), context.now)
        return document(value, ScopeOptions, "api.access_scope_options")

    async def my_scope(self, context: TenantContext) -> MyScope:
        value = await self._read("access_my_scope", *_tenant(context), context.now)
        return document(value, MyScope, "api.access_my_scope")

    async def list_people(self, query: PeopleQuery) -> PeoplePage:
        value = await self._read(
            "people_list",
            *_tenant(query.context),
            query.page,
            query.page_size,
            query.role,
            query.status,
            query.context.now,
        )
        return document(value, PeoplePage, "api.people_list")

    async def get_person(self, query: PersonQuery) -> Person:
        value = await self._read(
            "people_get", *_tenant(query.context), query.user_id, query.context.now
        )
        return document(value, Person, "api.people_get")

    async def create_person(self, command: PersonSave) -> WriteResult:
        d = command.details
        return await self._write(
            "people_create",
            *_tenant(command.context),
            d.first_name,
            d.last_name,
            d.email,
            d.phone_number,
            d.role,
            d.scope_mode,
            list(d.company_ids),
            list(d.vehicle_ids),
            list(d.permissions),
            d.approval_limit,
            *_back_limit(d),
            command.context.now,
        )

    async def update_person(self, command: PersonSave) -> WriteResult:
        d = command.details
        return await self._write(
            "people_update",
            *_tenant(command.context),
            command.user_id,
            d.first_name,
            d.last_name,
            d.email,
            d.phone_number,
            d.role,
            d.scope_mode,
            list(d.company_ids),
            list(d.vehicle_ids),
            list(d.permissions),
            d.approval_limit,
            *_back_limit(d),
            command.expected_version,
            command.context.now,
        )

    async def set_person_active(self, command: PersonLifecycle) -> WriteResult:
        return await self._write(
            "people_set_active",
            *_tenant(command.context),
            command.user_id,
            command.active,
            command.expected_version,
            command.reason,
            command.context.now,
        )

    async def sign_out_person(self, command: PersonSignOut) -> WriteResult:
        return await self._write(
            "people_sign_out", *_tenant(command.context), command.user_id, command.context.now
        )

    async def require_pin_reset(self, command: PersonPinReset) -> WriteResult:
        return await self._write(
            "people_pin_reset", *_tenant(command.context), command.user_id, command.context.now
        )

    async def remove_person_device(self, command: PersonDeviceRemoval) -> WriteResult:
        return await self._write(
            "people_device_remove",
            *_tenant(command.context),
            command.user_id,
            command.device_id,
            command.context.now,
        )

    async def list_history(self, query: HistoryQuery) -> HistoryPage:
        f = query.filter
        value = await self._read(
            "history_list",
            *_tenant(query.context),
            f.page,
            f.page_size,
            f.section,
            f.from_date,
            f.to_date,
            f.text,
            f.before,
            f.include_total,
            query.context.now,
        )
        return document(value, HistoryPage, "api.history_list")

    async def organization_settings(self, context: TenantContext) -> OrganizationSettings:
        value = await self._read("organization_settings_get", *_tenant(context), context.now)
        return document(value, OrganizationSettings, "api.organization_settings_get")

    async def save_settings(self, command: SettingsSave) -> WriteResult:
        return await self._write(
            "organization_settings_set",
            *_tenant(command.context),
            command.section,
            Jsonb(command.value),
            command.reason,
            command.expected_version,
            command.context.now,
        )

    async def save_logo(self, command: LogoSave) -> WriteResult:
        return await self._write(
            "organization_logo_set",
            *_tenant(command.context),
            command.logo.content_type,
            command.logo.data,
            command.reason,
            command.context.now,
        )

    async def delete_logo(self, command: LogoRemoval) -> WriteResult:
        return await self._write(
            "organization_logo_delete",
            *_tenant(command.context),
            command.reason,
            command.context.now,
        )

    async def appearance(self, context: TenantContext) -> Appearance:
        value = await self._read("organization_appearance_get", *_tenant(context), context.now)
        return document(value, Appearance, "api.organization_appearance_get")

    async def preferences(self, context: TenantContext) -> Preferences:
        value = await self._read("preferences_get", *_tenant(context), context.now)
        return document(value, Preferences, "api.preferences_get")

    async def save_preferences(self, command: PreferencesSave) -> UserPreferences:
        c = command.choices
        rows = await call(
            self._pool,
            "preferences_set",
            *_tenant(command.context),
            c.locale,
            c.time_zone,
            c.hour12,
            c.theme_mode,
            c.reduced_motion,
            c.font_scale,
            command.context.now,
        )
        return document(_single(rows, "preferences_set"), UserPreferences, "api.preferences_set")

    async def _read(self, routine: str, *args: Any) -> Any:
        rows = await call(self._pool, routine, *args, idempotent=True)
        return _single(rows, routine)

    async def _write(self, routine: str, *args: Any) -> WriteResult:
        rows = await call(self._pool, routine, *args)
        if len(rows) != 1:
            raise IntegrityBug(f"api.{routine} returned {len(rows)} rows, expected one")
        return write_result(rows[0])


def _single(rows: list[dict[str, Any]], routine: str) -> Any:
    if len(rows) != 1 or routine not in rows[0]:
        raise IntegrityBug(f"api.{routine} returned no single value")
    value = rows[0][routine]
    if value is None:
        raise IntegrityBug(f"api.{routine} returned null")
    return value
