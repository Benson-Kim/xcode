"""Raw rows for schema tests: one complete organization with a row in every table.

Inserted as ``xcode_owner`` (the table owner, so row-level security does not apply) in one
transaction, which lets the deferred allocation check see the version and its shares
together. ``scenario.py`` is the routine-based builder; schema tests need rows in tables
that no routine writes yet.
"""

from __future__ import annotations

import secrets
from dataclasses import asdict, dataclass
from typing import Any
from uuid import UUID

import psycopg

Conn = psycopg.Connection[dict[str, Any]]

PNG_BYTES = bytes.fromhex("89504e470d0a1a0a") + b"\x00" * 8


@dataclass(frozen=True, slots=True)
class OrganizationRows:
    org: UUID
    user: UUID
    user2: UUID
    role: UUID
    company: UUID
    vehicle: UUID
    vehicle2: UUID
    target_set: UUID
    away: UUID
    investment: UUID
    main_category: UUID
    category: UUID
    item: UUID
    recurring: UUID
    version: UUID
    allocation: UUID
    record: UUID
    change_log_id: UUID
    code: UUID
    device: UUID
    token: UUID
    entry: UUID
    central: UUID
    pause: UUID
    saving: UUID
    saving_version: UUID

    def params(self) -> dict[str, UUID]:
        return asdict(self)


def _one(conn: Conn, sql: str, params: dict[str, Any]) -> Any:
    row = conn.execute(sql, params).fetchone()  # type: ignore[arg-type]
    assert row is not None
    return next(iter(row.values()))


def _phone() -> str:
    return "+2547" + "".join(secrets.choice("0123456789") for _ in range(8))


def seed_organization(conn: Conn, slug: str | None = None) -> OrganizationRows:
    slug = slug or f"org-{secrets.token_hex(4)}"
    with conn.transaction():
        return _seed(conn, slug)


def _seed(conn: Conn, slug: str) -> OrganizationRows:
    tag = secrets.token_hex(4)
    p: dict[str, Any] = {"slug": slug, "tag": tag}
    p["user"] = _one(
        conn,
        "INSERT INTO identity.users (email, phone_number, pin_hash) "
        "VALUES ('owner-' || %(tag)s || '@example.com', %(phone)s, 'c2FsdA==.aGFzaA==') "
        "RETURNING id",
        {**p, "phone": _phone()},
    )
    p["user2"] = _one(
        conn,
        "INSERT INTO identity.users (email, phone_number) "
        "VALUES ('clerk-' || %(tag)s || '@example.com', %(phone)s) RETURNING id",
        {**p, "phone": _phone()},
    )
    p["code"] = _one(
        conn,
        "INSERT INTO identity.verification_codes (user_id, purpose, device_id, code_hash, "
        "expires_at) VALUES (%(user)s, 'new_device', 'device-1', repeat('A', 64), "
        "now() + interval '10 minutes') RETURNING id",
        p,
    )
    p["device"] = _one(
        conn,
        "INSERT INTO identity.trusted_devices (user_id, device_id, trusted_at, last_used_at) "
        "VALUES (%(user)s, 'device-1', now(), now()) RETURNING id",
        p,
    )
    p["token"] = _one(
        conn,
        "INSERT INTO identity.refresh_tokens (user_id, device_id, token_hash, expires_at) "
        "VALUES (%(user)s, 'device-1', upper(md5(%(tag)s) || md5(%(tag)s)), "
        "now() + interval '30 days') RETURNING id",
        p,
    )
    conn.execute(
        "INSERT INTO identity.sign_in_attempts (occurred_at, operation, outcome, user_id, "
        "phone_digest, device_id, request_id) VALUES (now(), 'sign_in', 'authenticated', "
        "%(user)s, repeat('a', 64), 'device-1', 'request-1')",
        p,
    )
    p["org"] = _one(
        conn,
        "INSERT INTO tenancy.organizations (slug, name) VALUES (%(slug)s, 'Organization') "
        "RETURNING id",
        p,
    )
    conn.execute(
        "INSERT INTO tenancy.memberships (organization_id, user_id, first_name, last_name, "
        "approval_limit) VALUES (%(org)s, %(user)s, 'Owen', 'Owner', 1000), "
        "(%(org)s, %(user2)s, 'Clara', 'Clerk', NULL)",
        p,
    )
    conn.execute(
        "INSERT INTO tenancy.organization_localizations (organization_id) VALUES (%(org)s)", p
    )
    conn.execute("INSERT INTO tenancy.organization_brandings (organization_id) VALUES (%(org)s)", p)
    conn.execute(
        "INSERT INTO tenancy.organization_logos (organization_id, content_type, data) "
        "VALUES (%(org)s, 'image/png', %(png)s)",
        {**p, "png": PNG_BYTES},
    )
    conn.execute(
        "INSERT INTO tenancy.organization_security_policies (organization_id) VALUES (%(org)s)",
        p,
    )
    conn.execute(
        "INSERT INTO tenancy.organization_revenue_settings (organization_id) VALUES (%(org)s)",
        p,
    )
    conn.execute(
        "INSERT INTO tenancy.user_preferences (organization_id, user_id, theme_mode) "
        "VALUES (%(org)s, %(user)s, 'dark')",
        p,
    )
    p["role"] = _one(
        conn,
        "INSERT INTO tenancy.roles (organization_id, name) VALUES (%(org)s, 'Owner') RETURNING id",
        p,
    )
    conn.execute(
        "INSERT INTO tenancy.roles (organization_id, name) VALUES (%(org)s, 'Revenue clerk')", p
    )
    conn.execute(
        "INSERT INTO tenancy.person_roles (organization_id, user_id, role_id) "
        "VALUES (%(org)s, %(user)s, %(role)s)",
        p,
    )
    conn.execute(
        "INSERT INTO tenancy.permission_overrides (organization_id, user_id, permission, granted) "
        "VALUES (%(org)s, %(user)s, 'dash.capture', true)",
        p,
    )
    p["company"] = _one(
        conn,
        "INSERT INTO setup.psv_companies (organization_id, name) VALUES (%(org)s, 'Metro Trans') "
        "RETURNING id",
        p,
    )
    p["vehicle"] = _one(
        conn,
        "INSERT INTO setup.fleet_vehicles (organization_id, company_id, registration, "
        "fleet_number, joined_on, initial_investment) VALUES (%(org)s, %(company)s, 'KDA 482M', "
        "'MT-01', DATE '2026-01-05', 2500000) RETURNING id",
        p,
    )
    p["vehicle2"] = _one(
        conn,
        "INSERT INTO setup.fleet_vehicles (organization_id, company_id, registration, joined_on) "
        "VALUES (%(org)s, %(company)s, 'KDB 100A', DATE '2026-01-05') RETURNING id",
        p,
    )
    conn.execute(
        "INSERT INTO tenancy.data_scopes (organization_id, user_id, all_companies) "
        "VALUES (%(org)s, %(user)s, true)",
        p,
    )
    conn.execute(
        "INSERT INTO tenancy.data_scope_companies (organization_id, user_id, company_id) "
        "VALUES (%(org)s, %(user2)s, %(company)s)",
        p,
    )
    conn.execute(
        "INSERT INTO tenancy.data_scope_vehicles (organization_id, user_id, vehicle_id) "
        "VALUES (%(org)s, %(user2)s, %(vehicle)s)",
        p,
    )
    p["target_set"] = _one(
        conn,
        "INSERT INTO setup.vehicle_target_sets (organization_id, vehicle_id, starts_on, monday, "
        "tuesday, wednesday, thursday, friday, saturday, sunday, created_by) VALUES (%(org)s, "
        "%(vehicle)s, DATE '2026-01-05', 3000, 3000, 3000, 3000, 3000, 3500, 2500, %(user)s) "
        "RETURNING id",
        p,
    )
    p["away"] = _one(
        conn,
        "INSERT INTO setup.vehicle_away_periods (organization_id, vehicle_id, left_on, "
        "returned_on) VALUES (%(org)s, %(vehicle)s, DATE '2026-03-02', DATE '2026-03-09') "
        "RETURNING id",
        p,
    )
    p["investment"] = _one(
        conn,
        "INSERT INTO setup.vehicle_investments (organization_id, vehicle_id, invested_on, "
        "description, amount, recorded_by, recorded_at) VALUES (%(org)s, %(vehicle)s, "
        "DATE '2026-01-05', 'Purchase', 2500000, %(user)s, now()) RETURNING id",
        p,
    )
    p["main_category"] = _one(
        conn,
        "INSERT INTO setup.expense_main_categories (organization_id, name) "
        "VALUES (%(org)s, 'Recurring charges') RETURNING id",
        p,
    )
    p["category"] = _one(
        conn,
        "INSERT INTO setup.expense_categories (organization_id, name, bucket, main_category_id) "
        "VALUES (%(org)s, 'Insurance', 2, %(main_category)s) RETURNING id",
        p,
    )
    p["item"] = _one(
        conn,
        "INSERT INTO setup.expense_items (organization_id, category_id, name) "
        "VALUES (%(org)s, %(category)s, 'Comprehensive cover') RETURNING id",
        p,
    )
    p["recurring"] = _one(
        conn,
        "INSERT INTO setup.recurring_items (organization_id) VALUES (%(org)s) RETURNING id",
        p,
    )
    p["version"] = _one(
        conn,
        "INSERT INTO setup.recurring_versions (organization_id, item_id, revision, "
        "effective_from, name, kind, amount, frequency, day, last_day, month, start_on, "
        "expense_item_id, bucket) VALUES (%(org)s, %(recurring)s, 1, DATE '2026-01-01', "
        "'Insurance', 1, 1000, 3, 15, false, NULL, DATE '2026-01-01', %(item)s, 2) RETURNING id",
        p,
    )
    p["allocation"] = _one(
        conn,
        "INSERT INTO setup.recurring_allocations (organization_id, version_id, vehicle_id, "
        "amount) VALUES (%(org)s, %(version)s, %(vehicle)s, 600) RETURNING id",
        p,
    )
    conn.execute(
        "INSERT INTO setup.recurring_allocations (organization_id, version_id, vehicle_id, "
        "amount) VALUES (%(org)s, %(version)s, %(vehicle2)s, 400)",
        p,
    )
    p["record"] = _one(
        conn,
        "INSERT INTO revenue.records (organization_id, vehicle_id, business_date, amount, "
        "captured_at, captured_by, updated_by) VALUES (%(org)s, %(vehicle)s, DATE '2026-02-02', "
        "3000, now(), %(user)s, %(user)s) RETURNING id",
        p,
    )
    p["entry"] = _one(
        conn,
        "INSERT INTO pettycash.entries (organization_id, holder_id, kind, entry_date, vehicle_id, "
        "expense_item_id, unit_amount, status, reviewed_by, reviewed_at, recorded_by, "
        "recorded_at, updated_by, updated_at, removed_by, removed_at, removal_reason) "
        "VALUES (%(org)s, %(user)s, 2, DATE '2026-02-02', %(vehicle)s, %(item)s, 450, 2, "
        "%(user)s, now(), %(user)s, now(), %(user)s, now(), %(user)s, now(), 'Recorded twice.') "
        "RETURNING id",
        p,
    )
    p["central"] = _one(
        conn,
        "WITH n AS (SELECT gen_random_uuid() AS id) INSERT INTO expenses.entries (organization_id, "
        "id, entry_date, vehicle_id, expense_item_id, units, unit_amount, note, group_id, "
        "group_size, group_total, group_units, group_unit_amount, recorded_by, recorded_at, "
        "updated_by, updated_at, removed_by, removed_at, removal_reason) SELECT %(org)s, n.id, "
        "DATE '2026-02-02', %(vehicle)s, %(item)s, 2, 250, 'Front tyres', n.id, 1, 500, 2, 250, "
        "%(user)s, now(), %(user)s, now(), %(user)s, now(), 'Recorded twice.' FROM n RETURNING id",
        p,
    )
    p["pause"] = _one(
        conn,
        "INSERT INTO setup.recurring_pauses (organization_id, item_id, paused_from, "
        "paused_through) VALUES (%(org)s, %(recurring)s, DATE '2026-03-01', "
        "DATE '2026-03-10') RETURNING id",
        p,
    )
    p["saving"] = _one(
        conn,
        "INSERT INTO setup.recurring_items (organization_id) VALUES (%(org)s) RETURNING id",
        p,
    )
    p["saving_version"] = _one(
        conn,
        "INSERT INTO setup.recurring_versions (organization_id, item_id, revision, "
        "effective_from, name, kind, amount, frequency, day, last_day, month, start_on, "
        "condition_min, condition_days) VALUES (%(org)s, %(saving)s, 1, DATE '2026-01-01', "
        "'Tyre fund', 2, 100, 3, 1, false, NULL, DATE '2026-01-01', 2000, 7) RETURNING id",
        p,
    )
    conn.execute(
        "INSERT INTO setup.recurring_allocations (organization_id, version_id, vehicle_id, "
        "amount) VALUES (%(org)s, %(saving_version)s, %(vehicle)s, 100)",
        p,
    )
    conn.execute(
        "INSERT INTO setup.saving_openings (organization_id, item_id, opened_on) "
        "VALUES (%(org)s, %(saving)s, DATE '2026-01-15')",
        p,
    )
    conn.execute(
        "INSERT INTO setup.saving_opening_amounts (organization_id, item_id, vehicle_id, amount) "
        "VALUES (%(org)s, %(saving)s, %(vehicle)s, 500)",
        p,
    )
    conn.execute(
        "INSERT INTO setup.saving_runs (organization_id, item_id, run_on, vehicle_id, version_id, "
        "amount, state, revenue, decided_at) VALUES (%(org)s, %(saving)s, DATE '2026-02-01', "
        "%(vehicle)s, %(saving_version)s, 100, 1, 2500, now())",
        p,
    )
    p["change_log_id"] = _one(
        conn,
        "INSERT INTO tenancy.change_log (organization_id, version, section, entity_id, "
        "vehicle_id, actor_id, reason, occurred_at, before, after, request_id) VALUES "
        "(%(org)s, 2, 'vehicles', %(vehicle)s, %(vehicle)s, %(user)s, 'Added vehicle KDA 482M', "
        "now(), 'null', '{}', 'request-1') RETURNING id",
        p,
    )
    conn.execute(
        "INSERT INTO tenancy.audit_events (organization_id, actor_id, action, entity, after, "
        "occurred_at, request_id) VALUES (%(org)s, %(user)s, 'setup.vehicles', 'vehicle', "
        "'{}', now(), 'request-1')",
        p,
    )
    conn.execute("UPDATE tenancy.organizations SET settings_version = 2 WHERE id = %(org)s", p)
    fields = OrganizationRows.__dataclass_fields__
    return OrganizationRows(**{name: p[name] for name in fields})
