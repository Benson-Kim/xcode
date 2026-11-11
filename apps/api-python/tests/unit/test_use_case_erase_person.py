"""``ErasePerson``: the caller's context and clock reach the repository with the person, the
version and the reason; an erased person's name and contact details leave the history, a
repeat changes nothing, and a person still active or in another organization is refused
before the version is read."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import UUID

import pytest

from xcode_api.application.access.erase_person import ErasePerson, ErasePersonCommand
from xcode_api.application.access.set_person_active import (
    SetPersonActive,
    SetPersonActiveCommand,
)
from xcode_api.application.caller import Caller
from xcode_api.domain.errors import RuleViolation
from xcode_api.domain.identity import Principal
from xcode_api.domain.values import WriteOutcome

from ..support.clock import ManualClock
from ..support.fakes import FakeTenancyRepository

NOW = datetime(2026, 11, 11, 9, 0, tzinfo=UTC)


def _arrange() -> tuple[FakeTenancyRepository, Caller, ManualClock, UUID]:
    tenancy = FakeTenancyRepository()
    owner = tenancy.add_member()
    clerk = tenancy.add_member(
        email="cleo@example.com",
        phone="0733000111",
        role="Revenue clerk",
        first_name="Cleo",
        last_name="Clerk",
    )
    principal = Principal(owner, "phone-1", 0, tenancy.organization_id, "Owner", ())
    return tenancy, Caller(principal, "req-1"), ManualClock(NOW), clerk


async def test_a_blocked_person_is_erased_from_the_people_and_their_history() -> None:
    tenancy, caller, clock, clerk = _arrange()
    await SetPersonActive(tenancy, clock).execute(
        SetPersonActiveCommand(caller, clerk, False, 1, "Asked to leave")
    )
    result = await ErasePerson(tenancy, clock).execute(
        ErasePersonCommand(caller, clerk, 2, "Asked for their account to be deleted")
    )
    assert (result.id, result.version, result.outcome) == (clerk, 3, WriteOutcome.UPDATED)
    assert [entry.reason for entry in tenancy.log] == [
        "Removed access for Former member. Reason: Asked to leave.",
        "Erased the personal details of a former member. "
        "Reason: Asked for their account to be deleted.",
    ]
    blocked = tenancy.log[0]
    for snapshot in (blocked.before, blocked.after):
        assert snapshot is not None
        document = json.loads(snapshot)
        assert (document["FirstName"], document["LastName"]) == ("Former", "member")
        assert (document["Email"], document["PhoneNumber"]) == (None, None)
    assert all("Cleo" not in repr(entry) for entry in tenancy.log)
    assert tenancy.log[-1].entity_id == clerk
    assert tenancy.log[-1].occurred_at == NOW


async def test_a_repeat_on_an_erased_person_changes_nothing() -> None:
    tenancy, caller, clock, clerk = _arrange()
    tenancy.members[clerk].active = False
    use_case = ErasePerson(tenancy, clock)
    first = await use_case.execute(ErasePersonCommand(caller, clerk, 1, "Asked to be deleted"))
    entries = len(tenancy.log)
    again = await use_case.execute(ErasePersonCommand(caller, clerk, 1, None))
    assert again.outcome == WriteOutcome.UNCHANGED
    assert again.version == first.version
    assert len(tenancy.log) == entries


@pytest.mark.parametrize(
    ("blocked", "elsewhere", "code"),
    [(False, False, "people_erase_active"), (True, True, "people_erase_shared")],
    ids=["active", "in-another-organization"],
)
async def test_a_person_who_may_not_be_erased_is_refused_before_the_version(
    blocked: bool, elsewhere: bool, code: str
) -> None:
    tenancy, caller, clock, clerk = _arrange()
    tenancy.members[clerk].active = not blocked
    tenancy.members[clerk].in_other_organization = elsewhere
    with pytest.raises(RuleViolation) as caught:
        await ErasePerson(tenancy, clock).execute(
            ErasePersonCommand(caller, clerk, 99, "Asked to be deleted")
        )
    assert caught.value.code == code
    assert tenancy.log == []
