"""Builders shared by the tenancy routine tests: members of the single organization, the
companies, vehicles, data scopes and permission overrides no routine writes yet (inserted as
``xcode_owner``), calls and refusal checks of the people routines, and change-log rows for
the sections that have no routine yet."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import psycopg
import pytest

from .scenario import T0, Conn, provision

REQUEST = "req-test"
ROLES = ("Fleet manager", "Office admin", "Owner", "Revenue clerk")
CLERK_KEYS = ["dash.gaps", "revenue.view", "revenue.capture"]

PERSON: dict[str, Any] = {
    "first_name": "Jane",
    "last_name": "Njeri",
    "email": "jane@example.com",
    "phone": "0722000111",
    "role": "Revenue clerk",
    "scope_mode": "all",
    "company_ids": [],
    "vehicle_ids": [],
    "permissions": CLERK_KEYS,
    "approval_limit": None,
    "back_limit_mode": None,
    "back_limit_count": None,
    "back_limit_from": None,
}


@dataclass(frozen=True, slots=True)
class Member:
    id: UUID
    org: UUID
    email: str
    phone: str
    first_name: str
    last_name: str
    role: str

    @property
    def name(self) -> str:
        return f"{self.first_name} {self.last_name}"


def provision_member(
    operator: Conn, slot: int, role: str, first_name: str, last_name: str
) -> Member:
    email = f"{first_name}.{last_name}@example.com".lower()
    phone = f"0711{slot:06d}"
    result = provision(
        operator,
        email=email,
        phone=phone,
        role=role,
        first_name=first_name,
        last_name=last_name,
    )
    return Member(
        id=UUID(result["user_id"]),
        org=UUID(result["organization_id"]),
        email=email,
        phone=phone,
        first_name=first_name,
        last_name=last_name,
        role=role,
    )


def add_company(owner: Conn, org: UUID, name: str, *, archived_on: date | None = None) -> UUID:
    row = owner.execute(
        "INSERT INTO setup.psv_companies (organization_id, name, archived_on) "
        "VALUES (%s, %s, %s) RETURNING id",
        (org, name, archived_on),
    ).fetchone()
    assert row is not None
    return UUID(str(row["id"]))


def add_vehicle(
    owner: Conn,
    org: UUID,
    company: UUID,
    registration: str,
    *,
    joined_on: date = date(2026, 1, 1),
    left_on: date | None = None,
    fleet_number: str | None = None,
) -> UUID:
    row = owner.execute(
        "INSERT INTO setup.fleet_vehicles (organization_id, company_id, registration, joined_on, "
        "left_on, fleet_number) VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
        (org, company, registration, joined_on, left_on, fleet_number),
    ).fetchone()
    assert row is not None
    return UUID(str(row["id"]))


def set_scope(
    owner: Conn,
    member: Member | UUID,
    org: UUID,
    *,
    all_companies: bool = False,
    companies: Sequence[UUID] = (),
    vehicles: Sequence[UUID] = (),
) -> None:
    user = member.id if isinstance(member, Member) else member
    for table in ("data_scope_companies", "data_scope_vehicles", "data_scopes"):
        owner.execute(
            f"DELETE FROM tenancy.{table} WHERE organization_id = %s AND user_id = %s", (org, user)
        )
    if all_companies:
        owner.execute(
            "INSERT INTO tenancy.data_scopes (organization_id, user_id, all_companies) "
            "VALUES (%s, %s, true)",
            (org, user),
        )
    for company in companies:
        owner.execute(
            "INSERT INTO tenancy.data_scope_companies (organization_id, user_id, company_id) "
            "VALUES (%s, %s, %s)",
            (org, user, company),
        )
    for vehicle in vehicles:
        owner.execute(
            "INSERT INTO tenancy.data_scope_vehicles (organization_id, user_id, vehicle_id) "
            "VALUES (%s, %s, %s)",
            (org, user, vehicle),
        )


def set_override(owner: Conn, member: Member, permission: str, granted: bool = True) -> None:
    owner.execute(
        "INSERT INTO tenancy.permission_overrides (organization_id, user_id, permission, granted) "
        "VALUES (%s, %s, %s, %s) ON CONFLICT (organization_id, user_id, permission) "
        "DO UPDATE SET granted = EXCLUDED.granted",
        (member.org, member.id, permission, granted),
    )


def set_organization(owner: Conn, org: UUID, **values: Any) -> None:
    assignments = ", ".join(f"{name} = %s" for name in values)
    owner.execute(
        f"UPDATE tenancy.organizations SET {assignments} WHERE id = %s", (*values.values(), org)
    )


def set_localization(owner: Conn, org: UUID, **values: Any) -> None:
    assignments = ", ".join(f"{name} = %s" for name in values)
    owner.execute(
        f"UPDATE tenancy.organization_localizations SET {assignments} WHERE organization_id = %s",
        (*values.values(), org),
    )


def membership(owner: Conn, org: UUID, user: UUID) -> dict[str, Any]:
    row = owner.execute(
        "SELECT * FROM tenancy.memberships WHERE organization_id = %s AND user_id = %s",
        (org, user),
    ).fetchone()
    assert row is not None
    return row


def settings_version(owner: Conn, org: UUID) -> int:
    row = owner.execute(
        "SELECT settings_version FROM tenancy.organizations WHERE id = %s", (org,)
    ).fetchone()
    assert row is not None
    return int(row["settings_version"])


def change_log(owner: Conn, org: UUID) -> list[dict[str, Any]]:
    return owner.execute(
        "SELECT * FROM tenancy.change_log WHERE organization_id = %s ORDER BY version", (org,)
    ).fetchall()


def audit_events(owner: Conn, org: UUID, action: str | None = None) -> list[dict[str, Any]]:
    return owner.execute(
        "SELECT * FROM tenancy.audit_events WHERE organization_id = %s "
        "AND (%s::text IS NULL OR action = %s) ORDER BY id",
        (org, action, action),
    ).fetchall()


def scope_rows(owner: Conn, org: UUID, user: UUID) -> dict[str, Any]:
    flag = owner.execute(
        "SELECT all_companies FROM tenancy.data_scopes WHERE organization_id = %s AND user_id = %s",
        (org, user),
    ).fetchone()
    companies = owner.execute(
        "SELECT company_id FROM tenancy.data_scope_companies "
        "WHERE organization_id = %s AND user_id = %s ORDER BY company_id",
        (org, user),
    ).fetchall()
    vehicles = owner.execute(
        "SELECT vehicle_id FROM tenancy.data_scope_vehicles "
        "WHERE organization_id = %s AND user_id = %s ORDER BY vehicle_id",
        (org, user),
    ).fetchall()
    return {
        "all_companies": None if flag is None else flag["all_companies"],
        "companies": [UUID(str(r["company_id"])) for r in companies],
        "vehicles": [UUID(str(r["vehicle_id"])) for r in vehicles],
    }


def seed_change(
    owner: Conn,
    org: UUID,
    actor: UUID,
    section: str,
    entity: UUID,
    reason: str,
    *,
    vehicle: UUID | None = None,
    occurred_at: datetime = T0,
    before: str | None = None,
    after: str | None = None,
) -> int:
    with owner.transaction():
        row = owner.execute(
            "UPDATE tenancy.organizations SET settings_version = settings_version + 1 "
            "WHERE id = %s RETURNING settings_version",
            (org,),
        ).fetchone()
        assert row is not None
        version = int(row["settings_version"])
        owner.execute(
            "INSERT INTO tenancy.change_log (organization_id, version, section, entity_id, "
            "vehicle_id, actor_id, reason, occurred_at, before, after, request_id) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'seeded')",
            (org, version, section, entity, vehicle, actor, reason, occurred_at, before, after),
        )
    return version


def add_recurring(owner: Conn, org: UUID, revisions: Sequence[Mapping[UUID, Decimal]]) -> UUID:
    with owner.transaction():
        item = owner.execute(
            "INSERT INTO setup.recurring_items (organization_id) VALUES (%s) RETURNING id", (org,)
        ).fetchone()
        assert item is not None
        for number, shares in enumerate(revisions, start=1):
            version = owner.execute(
                "INSERT INTO setup.recurring_versions (organization_id, item_id, revision, "
                "effective_from, name, kind, amount, frequency, day, last_day, month, start_on) "
                "VALUES (%s, %s, %s, DATE '2026-01-01', 'Insurance', 1, %s, 3, 15, false, NULL, "
                "DATE '2026-01-01') RETURNING id",
                (org, item["id"], number, sum(shares.values(), Decimal(0))),
            ).fetchone()
            assert version is not None
            for vehicle, amount in shares.items():
                owner.execute(
                    "INSERT INTO setup.recurring_allocations (organization_id, version_id, "
                    "vehicle_id, amount) VALUES (%s, %s, %s, %s)",
                    (org, version["id"], vehicle, amount),
                )
    return UUID(str(item["id"]))


def write(conn: Conn, routine: str, *args: Any) -> dict[str, Any]:
    placeholders = ", ".join(["%s"] * len(args))
    row = conn.execute(f"SELECT * FROM api.{routine}({placeholders})", args).fetchone()
    assert row is not None
    return row


def refused(
    conn: Conn, routine: str, args: Sequence[Any], sqlstate: str, code: str
) -> psycopg.Error:
    placeholders = ", ".join(["%s"] * len(args))
    with pytest.raises(psycopg.Error) as caught:
        conn.execute(f"SELECT * FROM api.{routine}({placeholders})", tuple(args)).fetchall()
    assert caught.value.sqlstate == sqlstate
    assert caught.value.diag.message_primary == code
    return caught.value


_CREATE = (
    "SELECT * FROM api.people_create(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::uuid[], "
    "%s::uuid[], %s::text[], %s::numeric, %s, %s::integer, %s::date, %s)"
)
_UPDATE = (
    "SELECT * FROM api.people_update(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::uuid[], "
    "%s::uuid[], %s::text[], %s::numeric, %s, %s::integer, %s::date, %s::bigint, %s)"
)


def _create_args(actor: Member, fields: Mapping[str, Any]) -> tuple[Any, ...]:
    p = {**PERSON, **fields}
    return (
        actor.id,
        actor.org,
        REQUEST,
        p["first_name"],
        p["last_name"],
        p["email"],
        p["phone"],
        p["role"],
        p["scope_mode"],
        p["company_ids"],
        p["vehicle_ids"],
        p["permissions"],
        p["approval_limit"],
        p["back_limit_mode"],
        p["back_limit_count"],
        p["back_limit_from"],
        T0,
    )


def _update_args(
    actor: Member, user_id: UUID | None, version: int | None, fields: Mapping[str, Any]
) -> tuple[Any, ...]:
    p = {**PERSON, **fields}
    return (
        actor.id,
        actor.org,
        REQUEST,
        user_id,
        p["first_name"],
        p["last_name"],
        p["email"],
        p["phone"],
        p["role"],
        p["scope_mode"],
        p["company_ids"],
        p["vehicle_ids"],
        p["permissions"],
        p["approval_limit"],
        p["back_limit_mode"],
        p["back_limit_count"],
        p["back_limit_from"],
        version,
        T0,
    )


def create_person(conn: Conn, actor: Member, **fields: Any) -> dict[str, Any]:
    row = conn.execute(_CREATE, _create_args(actor, fields)).fetchone()
    assert row is not None
    return row


def update_person(
    conn: Conn, actor: Member, user_id: UUID | None, version: int | None, **fields: Any
) -> dict[str, Any]:
    row = conn.execute(_UPDATE, _update_args(actor, user_id, version, fields)).fetchone()
    assert row is not None
    return row


def create_refused(
    conn: Conn, actor: Member, sqlstate: str, code: str, **fields: Any
) -> psycopg.Error:
    with pytest.raises(psycopg.Error) as caught:
        conn.execute(_CREATE, _create_args(actor, fields)).fetchall()
    assert caught.value.sqlstate == sqlstate
    assert caught.value.diag.message_primary == code
    return caught.value


def update_refused(
    conn: Conn,
    actor: Member,
    user_id: UUID | None,
    version: int | None,
    sqlstate: str,
    code: str,
    **fields: Any,
) -> psycopg.Error:
    with pytest.raises(psycopg.Error) as caught:
        conn.execute(_UPDATE, _update_args(actor, user_id, version, fields)).fetchall()
    assert caught.value.sqlstate == sqlstate
    assert caught.value.diag.message_primary == code
    return caught.value
