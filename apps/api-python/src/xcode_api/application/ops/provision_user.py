"""Provision a person: create or re-activate them in the database's single organization."""

from __future__ import annotations

from dataclasses import dataclass, field

from ...domain.identity import ProvisionedUser, UserProvisioning
from ..ports import Clock
from ..repositories import OpsRepository


@dataclass(frozen=True, slots=True)
class ProvisionUserCommand:
    operator: str
    request_id: str
    email: str = field(repr=False)
    phone: str = field(repr=False)
    role: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    organization_name: str | None = None


class ProvisionUser:
    def __init__(self, ops: OpsRepository, clock: Clock) -> None:
        self._ops = ops
        self._clock = clock

    async def execute(self, command: ProvisionUserCommand) -> ProvisionedUser:
        return await self._ops.provision_user(
            UserProvisioning(
                operator=command.operator,
                request_id=command.request_id,
                email=command.email,
                phone=command.phone,
                role=command.role,
                first_name=command.first_name,
                last_name=command.last_name,
                organization_name=command.organization_name,
                now=self._clock.now(),
            )
        )
