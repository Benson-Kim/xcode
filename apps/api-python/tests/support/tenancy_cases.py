"""Parity cases for ``FakeTenancyRepository``: each case runs the same calls against the fake
and against ``TenancyRoutines`` on PostgreSQL, and the two observations must be equal.

An observation records every call's result in a form free of generated ids: write results by
outcome and version, refusals by type and code, people and history entries by their fields
with UUIDs replaced by the order they first appeared in."""

from __future__ import annotations

import dataclasses
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

from xcode_api.application.repositories import TenancyRepository
from xcode_api.domain.errors import DomainRefusal
from xcode_api.domain.tenancy import (
    BackLimitInput,
    HistoryFilter,
    HistoryQuery,
    PeopleQuery,
    PersonDetails,
    PersonDeviceRemoval,
    PersonPinReset,
    PersonQuery,
    PersonSave,
    PersonSignOut,
    SettingsSave,
    TenantContext,
)

from .fakes import FakeTenancyRepository, role_rights
from .scenario import Conn, provision

NOW = datetime(2026, 10, 9, 7, 0, tzinfo=UTC)
_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


@dataclass
class TenancyWorld:
    """The repository under test and the Owner who acts in it."""

    repository: TenancyRepository
    owner: TenantContext
    seen: list[Any] = field(default_factory=list)

    async def record(self, call: Awaitable[Any]) -> Any:
        try:
            result = await call
        except DomainRefusal as refusal:
            self.seen.append(("refused", type(refusal).__name__, refusal.code))
            return None
        self.seen.append(_plain(result))
        return result


def fake_world() -> TenancyWorld:
    fake = FakeTenancyRepository()
    owner = fake.add_member(
        email="ann@example.com", phone="0711000111", first_name="Ann", last_name="Owner"
    )
    return TenancyWorld(fake, TenantContext(owner, fake.organization_id, "req-parity", NOW))


def database_world(repository: TenancyRepository, operator: Conn) -> TenancyWorld:
    result = provision(
        operator,
        email="ann@example.com",
        phone="0711000111",
        role="Owner",
        first_name="Ann",
        last_name="Owner",
        now=NOW,
    )
    context = TenantContext(
        UUID(result["user_id"]), UUID(result["organization_id"]), "req-parity", NOW
    )
    return TenancyWorld(repository, context)


def _plain(value: Any) -> Any:
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: _plain(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, tuple | list):
        return [_plain(v) for v in value]
    return value


def normalised(seen: list[Any]) -> list[Any]:
    """The observation with every UUID replaced by ``#n``, its order of first appearance."""
    order: dict[str, str] = {}

    def rename(value: Any) -> Any:
        if isinstance(value, UUID):
            value = str(value)
        if isinstance(value, str):
            return _UUID.sub(lambda m: order.setdefault(m.group(0), f"#{len(order)}"), value)
        if isinstance(value, dict):
            return {k: rename(v) for k, v in value.items()}
        if isinstance(value, list):
            return [rename(v) for v in value]
        if isinstance(value, tuple):
            return tuple(rename(v) for v in value)
        return value

    return [rename(item) for item in seen]


def jane(**changes: Any) -> PersonDetails:
    details = PersonDetails(
        first_name="Jane",
        last_name="Njeri",
        email="jane@example.com",
        phone_number="0722000111",
        role="Revenue clerk",
        scope_mode="all",
        company_ids=(),
        vehicle_ids=(),
        permissions=role_rights("Revenue clerk"),
        approval_limit=None,
    )
    return dataclasses.replace(details, **changes)


def history(page: int = 1, page_size: int = 25, **filters: Any) -> HistoryFilter:
    values: dict[str, Any] = {
        "section": None,
        "from_date": None,
        "to_date": None,
        "text": None,
        "before": None,
        "include_total": True,
    }
    values.update(filters)
    return HistoryFilter(page=page, page_size=page_size, **values)


async def _create(world: TenancyWorld, details: PersonDetails) -> UUID | None:
    result = await world.record(
        world.repository.create_person(PersonSave(world.owner, None, details, None))
    )
    return None if result is None else result.id


async def _update(
    world: TenancyWorld, user_id: UUID, details: PersonDetails, version: int | None
) -> None:
    await world.record(
        world.repository.update_person(PersonSave(world.owner, user_id, details, version))
    )


async def _history(world: TenancyWorld, query: HistoryFilter) -> None:
    await world.record(world.repository.list_history(HistoryQuery(world.owner, query)))


async def _settings(
    world: TenancyWorld, section: str, value: Any, reason: str | None = None
) -> None:
    await world.record(
        world.repository.save_settings(SettingsSave(world.owner, section, value, reason, None))
    )


async def create_and_read_a_person(world: TenancyWorld) -> None:
    user_id = await _create(world, jane())
    assert user_id is not None
    await world.record(world.repository.get_person(PersonQuery(world.owner, user_id)))
    await _history(world, history(section="people"))


async def refuse_a_malformed_person(world: TenancyWorld) -> None:
    await _create(world, jane(first_name="  "))
    await _create(world, jane(email="not-an-email"))
    await _create(world, jane(phone_number="12345"))
    await _create(world, jane(scope_mode="everything"))
    await _create(world, jane(permissions=()))
    await _create(world, jane(role="Driver"))
    await _create(world, jane(permissions=("revenue.view", "no.such_key")))
    await _create(world, jane())
    await _create(world, jane(phone_number="0733000222"))


async def update_a_person_at_their_version(world: TenancyWorld) -> None:
    user_id = await _create(world, jane())
    assert user_id is not None
    fleet = jane(role="Fleet manager", permissions=role_rights("Fleet manager"))
    await _update(world, user_id, fleet, None)
    await _update(world, user_id, fleet, 1)
    await _update(world, user_id, fleet, 1)
    await _update(world, user_id, fleet, 2)
    renamed = dataclasses.replace(fleet, first_name="Janet", phone_number="0733000222")
    await _update(world, user_id, renamed, 2)
    await world.record(world.repository.get_person(PersonQuery(world.owner, user_id)))
    await _history(world, history(section="people"))


async def keep_a_back_dating_limit(world: TenancyWorld) -> None:
    for refused in (
        BackLimitInput("weeks", 1, None),
        BackLimitInput("none", 3, None),
        BackLimitInput("days", None, None),
        BackLimitInput("days", 3651, None),
        BackLimitInput("months", 121, None),
        BackLimitInput("days", -1, None),
        BackLimitInput(None, 3, None),
        BackLimitInput(None, None, date(2026, 10, 1)),
        BackLimitInput("none", None, date(2026, 10, 10)),
    ):
        await _create(world, jane(back_limit=refused))
    user_id = await _create(world, jane())
    assert user_id is not None
    await _update(world, user_id, jane(), 1)
    await _update(world, user_id, jane(back_limit=BackLimitInput("days", 7, None)), 1)
    await _update(
        world, user_id, jane(back_limit=BackLimitInput("months", 1, date(2026, 10, 9))), 1
    )
    await _update(world, user_id, jane(back_limit=BackLimitInput("days", 0, None)), 2)
    await _update(world, user_id, jane(back_limit=BackLimitInput("none", None, None)), 3)
    await world.record(world.repository.get_person(PersonQuery(world.owner, user_id)))
    await world.record(world.repository.my_scope(world.owner))
    await _history(world, history(section="people"))


async def filter_people_by_status(world: TenancyWorld) -> None:
    await _create(world, jane())
    for status in (
        None,
        "",
        "all",
        "active",
        "not_signed_in",
        "waiting",
        "pin_reset_due",
        "locked",
        "blocked",
        "none",
        "asleep",
        "Active",
    ):
        await world.record(
            world.repository.list_people(PeopleQuery(world.owner, 1, 25, status=status))
        )


async def act_on_sign_in_without_devices(world: TenancyWorld) -> None:
    user_id = await _create(world, jane())
    assert user_id is not None
    owner = world.owner
    await world.record(world.repository.sign_out_person(PersonSignOut(owner, user_id)))
    await world.record(world.repository.require_pin_reset(PersonPinReset(owner, user_id)))
    await world.record(
        world.repository.remove_person_device(PersonDeviceRemoval(owner, user_id, user_id))
    )
    await world.record(world.repository.sign_out_person(PersonSignOut(owner, owner.actor_id)))
    await world.record(world.repository.require_pin_reset(PersonPinReset(owner, owner.actor_id)))
    await world.record(
        world.repository.remove_person_device(PersonDeviceRemoval(owner, owner.actor_id, user_id))
    )
    await _history(world, history(section="signIn"))


async def save_settings_sections(world: TenancyWorld) -> None:
    await _settings(world, "branding", {"display_name": "North Star"})
    await _settings(world, "branding", {"display_name": "North Star"})
    await _settings(world, "localization", {"first_day_of_week": 0, "currency": "USD"}, "Audit")
    await _settings(world, "localization", {"use_groupping": False})
    await _settings(world, "localization", {"use_groupping": True, "use_grouping": False})
    await _settings(world, "securityPolicy", {"lockout_threshold": 3})
    await _settings(world, "organization", {"name": "North Star Fleet", "slug": "north-star"})
    await _settings(world, "businessDate", "2026-10-08")
    await _settings(world, "businessDate", None)
    await _settings(world, "nothing", {})
    await _history(world, history())


async def page_the_change_log(world: TenancyWorld) -> None:
    for days in range(1, 8):
        await _settings(world, "securityPolicy", {"lockout_minutes": days})
    for page in (1, 2, 3, 4):
        await _history(world, history(page=page, page_size=2))
    await _history(world, history(page_size=2, before=8))
    await _history(world, history(page_size=2, before=6))
    await _history(world, history(page_size=2, before=4, include_total=False))
    await _history(world, history(page_size=3, text="PAUSE IN MINUTES TO 7"))
    await _history(world, history(before=0))


@dataclass(frozen=True)
class TenancyCase:
    name: str
    run: Callable[[TenancyWorld], Awaitable[None]]


CASES = (
    TenancyCase("create_and_read_a_person", create_and_read_a_person),
    TenancyCase("refuse_a_malformed_person", refuse_a_malformed_person),
    TenancyCase("update_a_person_at_their_version", update_a_person_at_their_version),
    TenancyCase("keep_a_back_dating_limit", keep_a_back_dating_limit),
    TenancyCase("filter_people_by_status", filter_people_by_status),
    TenancyCase("act_on_sign_in_without_devices", act_on_sign_in_without_devices),
    TenancyCase("save_settings_sections", save_settings_sections),
    TenancyCase("page_the_change_log", page_the_change_log),
)
