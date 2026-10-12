"""The authenticated caller of a tenant route, and the tenant context a use case builds from
it: the actor and organization the session resolved, the request id, and ``now`` from the
clock."""

from __future__ import annotations

from dataclasses import dataclass

from ..domain.identity import Principal
from ..domain.tenancy import TenantContext
from .ports import Clock


@dataclass(frozen=True, slots=True)
class Caller:
    principal: Principal
    request_id: str

    def context(self, clock: Clock) -> TenantContext:
        return TenantContext(
            actor_id=self.principal.user_id,
            organization_id=self.principal.organization_id,
            request_id=self.request_id,
            now=clock.now(),
        )
