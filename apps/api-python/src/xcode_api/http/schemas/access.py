"""People and access contract models (``docs/inventory/inventory-http-contract.md`` section
3.3): field order is the wire order, names are the camelCase aliases of the fields."""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated
from uuid import UUID

from pydantic import Field

from ...domain.tenancy import BackLimitInput, PersonDetails
from .common import Amount, ApiModel

Int32 = Annotated[int, Field(ge=-(2**31), le=2**31 - 1)]
Int64 = Annotated[int, Field(ge=-(2**63), le=2**63 - 1)]


class PermissionItem(ApiModel):
    key: str
    label: str
    needs: list[str]
    section: str | None


class PermissionGroup(ApiModel):
    name: str
    items: list[PermissionItem]


class AccessRole(ApiModel):
    id: UUID
    name: str
    permissions: list[str]


class CompanyOption(ApiModel):
    id: UUID
    name: str


class VehicleOption(ApiModel):
    id: UUID
    registration: str
    fleet_number: str | None
    company_id: UUID


class ScopeOptions(ApiModel):
    companies: list[CompanyOption]
    vehicles: list[VehicleOption]


class MyScope(ApiModel):
    all_companies: bool
    companies: list[CompanyOption]
    vehicles: list[VehicleOption]
    can_change: str
    earliest: date | None


class BackLimitDto(ApiModel):
    """How far back a person may change records: ``mode`` none, days or months, ``count``
    days or months back, ``from`` the date they may never go before."""

    mode: str
    count: int | None
    from_date: date | None = Field(alias="from")


class ModuleAccessDto(ApiModel):
    name: str
    held: int
    total: int


class PersonDeviceDto(ApiModel):
    id: UUID
    name: str | None
    trusted_at: datetime
    last_used_at: datetime


class PersonSignInDto(ApiModel):
    status: str
    lock: str | None
    last_signed_in_at: datetime | None
    email: str
    devices: list[PersonDeviceDto]


class PersonDto(ApiModel):
    id: UUID
    first_name: str
    last_name: str
    email: str
    phone_number: str
    role: str | None
    active: bool
    scope_mode: str
    company_ids: list[UUID]
    vehicle_ids: list[UUID]
    permissions: list[str]
    approval_limit: Amount | None
    has_pin: bool
    version: int
    other_companies: int
    other_vehicles: int
    status: str
    last_signed_in_at: datetime | None
    back_limit: BackLimitDto
    can_change: str
    modules: list[ModuleAccessDto]
    everything: bool


class PersonDetailDto(PersonDto):
    """``GET /setup/people/{id}``: the person with the "Sign in" pane."""

    sign_in: PersonSignInDto


class BackLimitBody(ApiModel):
    """The back-dating limit of a person save; absent or without a mode keeps the stored one
    (7 days back for a new person)."""

    mode: str | None = None
    count: Int32 | None = None
    from_date: date | None = Field(default=None, alias="from")


class SavePerson(ApiModel):
    """``POST /setup/people`` and ``PUT /setup/people/{id}``; ``version`` is required on
    update (the routine says so) and ignored on create. Missing fields take their defaults and
    the routine refuses what is not a valid person."""

    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None
    phone_number: str | None = None
    role: str | None = None
    scope_mode: str | None = None
    company_ids: list[UUID] = Field(default_factory=list)
    vehicle_ids: list[UUID] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    approval_limit: Amount | None = None
    version: Int64 | None = None
    back_limit: BackLimitBody | None = None

    def details(self) -> PersonDetails:
        return PersonDetails(
            first_name=self.first_name,
            last_name=self.last_name,
            email=self.email,
            phone_number=self.phone_number,
            role=self.role,
            scope_mode=self.scope_mode,
            company_ids=tuple(self.company_ids),
            vehicle_ids=tuple(self.vehicle_ids),
            permissions=tuple(self.permissions),
            approval_limit=self.approval_limit,
            back_limit=None
            if self.back_limit is None
            else BackLimitInput(
                self.back_limit.mode, self.back_limit.count, self.back_limit.from_date
            ),
        )


class PersonLifecycleRequest(ApiModel):
    """The optional body of activate and deactivate."""

    version: Int64 | None = None
    reason: str | None = None


class IdResponse(ApiModel):
    id: UUID
