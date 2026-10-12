"""Accounts and calls for the routine tests: provisioned through ``api.ops_provision_user``
as ``xcode_operator``, adjusted as ``xcode_owner`` where a test needs state no routine
writes yet (a PIN hash, a trusted device), and exercised as ``xcode_app``."""

from __future__ import annotations

import base64
import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID

import psycopg

Conn = psycopg.Connection[dict[str, Any]]

T0 = datetime(2026, 10, 9, 7, 0, 0, tzinfo=UTC)
PHONE = "0712345678"
NORMALIZED = "+254712345678"
EMAIL = "jane.doe@example.com"
TRUSTED = "trusted-device"
UNTRUSTED = "untrusted-device"
PIN_HASH = base64.b64encode(b"s" * 16).decode() + "." + base64.b64encode(b"k" * 32).decode()
NEW_PIN_HASH = base64.b64encode(b"t" * 16).decode() + "." + base64.b64encode(b"n" * 32).decode()
NAIROBI_OFFSET = timedelta(hours=3)


def digest(value: str) -> str:
    """A 64-character upper-case hex digest, the shape of the service's keyed digests."""
    return hashlib.sha256(value.encode()).hexdigest().upper()


CODE_HASH = digest("code:123456")
WRONG_CODE_HASH = digest("code:000000")
NEW_CODE_HASH = digest("code:777777")


def new_token_hash() -> str:
    return digest(f"token:{secrets.token_hex(16)}")


def call(conn: Conn, routine: str, *args: Any) -> Any:
    placeholders = ", ".join(["%s"] * len(args))
    row = conn.execute(f"SELECT api.{routine}({placeholders}) AS r", args).fetchone()
    assert row is not None
    return row["r"]


@dataclass(frozen=True, slots=True)
class Account:
    user_id: UUID
    organization_id: UUID
    email: str
    phone: str


def provision(
    operator: Conn,
    *,
    email: str = EMAIL,
    phone: str = PHONE,
    role: str | None = None,
    first_name: str | None = None,
    last_name: str | None = None,
    organization_name: str | None = None,
    now: datetime = T0,
) -> dict[str, Any]:
    result: dict[str, Any] = call(
        operator,
        "ops_provision_user",
        "test-operator",
        "req-provision",
        email,
        phone,
        role,
        first_name,
        last_name,
        organization_name,
        now,
    )
    return result


def make_account(
    operator: Conn,
    owner: Conn,
    *,
    email: str = EMAIL,
    phone: str = PHONE,
    role: str | None = None,
    pin: bool = True,
    trusted: tuple[str, ...] = (TRUSTED,),
) -> Account:
    result = provision(operator, email=email, phone=phone, role=role)
    account = Account(
        user_id=UUID(result["user_id"]),
        organization_id=UUID(result["organization_id"]),
        email=email,
        phone=phone,
    )
    if pin:
        owner.execute(
            "UPDATE identity.users SET pin_hash = %s WHERE id = %s", (PIN_HASH, account.user_id)
        )
    for device in trusted:
        trust(owner, account.user_id, device)
    return account


def trust(
    owner: Conn,
    user_id: UUID,
    device: str,
    *,
    expires_at: datetime | None = None,
    revoked: bool = False,
    token_hash: str | None = None,
    name: str | None = None,
    remembered: bool = True,
    last_used_at: datetime = T0,
) -> None:
    """A trusted-device row: by default trusted by its id alone (v2.11), used at ``T0``."""
    owner.execute(
        "INSERT INTO identity.trusted_devices (user_id, device_id, revoked, trust_expires_at, "
        "token_hash, name, remembered, trusted_at, last_used_at) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (user_id, device_id) DO UPDATE "
        "SET revoked = EXCLUDED.revoked, trust_expires_at = EXCLUDED.trust_expires_at, "
        "token_hash = EXCLUDED.token_hash, name = EXCLUDED.name, "
        "remembered = EXCLUDED.remembered, last_used_at = EXCLUDED.last_used_at",
        (
            user_id,
            device,
            revoked,
            expires_at,
            token_hash,
            name,
            remembered,
            min(last_used_at, T0),
            last_used_at,
        ),
    )


def store_token(
    owner: Conn,
    user_id: UUID,
    device: str,
    *,
    token_hash: str | None = None,
    expires_at: datetime = T0 + timedelta(days=30),
    revoked: bool = False,
) -> str:
    token_hash = token_hash or new_token_hash()
    owner.execute(
        "INSERT INTO identity.refresh_tokens (user_id, device_id, token_hash, expires_at, revoked) "
        "VALUES (%s, %s, %s, %s, %s)",
        (user_id, device, token_hash, expires_at, revoked),
    )
    return token_hash


def store_code(
    owner: Conn,
    user_id: UUID,
    purpose: str,
    device: str,
    *,
    code_hash: str = CODE_HASH,
    created_at: datetime = T0,
    consumed: bool = False,
    withdrawn: bool = False,
    failed_attempts: int = 0,
) -> UUID:
    expires_at = created_at if withdrawn else created_at + timedelta(minutes=10)
    row = owner.execute(
        "INSERT INTO identity.verification_codes "
        "(user_id, purpose, device_id, code_hash, created_at, expires_at, consumed, "
        "failed_attempts) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
        (
            user_id,
            purpose,
            device,
            code_hash,
            created_at,
            expires_at,
            consumed or withdrawn,
            failed_attempts,
        ),
    ).fetchone()
    assert row is not None
    return UUID(str(row["id"]))


def user_row(owner: Conn, user_id: UUID) -> dict[str, Any]:
    row = owner.execute("SELECT * FROM identity.users WHERE id = %s", (user_id,)).fetchone()
    assert row is not None
    return row


def set_user(owner: Conn, user_id: UUID, **values: Any) -> None:
    assignments = ", ".join(f"{name} = %s" for name in values)
    owner.execute(
        f"UPDATE identity.users SET {assignments} WHERE id = %s", (*values.values(), user_id)
    )


def codes(owner: Conn, user_id: UUID) -> list[dict[str, Any]]:
    return owner.execute(
        "SELECT * FROM identity.verification_codes WHERE user_id = %s ORDER BY created_at, id",
        (user_id,),
    ).fetchall()


def tokens(owner: Conn, user_id: UUID) -> list[dict[str, Any]]:
    return owner.execute(
        "SELECT * FROM identity.refresh_tokens WHERE user_id = %s ORDER BY created_at, id",
        (user_id,),
    ).fetchall()


def live_tokens(owner: Conn, user_id: UUID, device: str | None = None) -> int:
    row = owner.execute(
        "SELECT count(*) AS n FROM identity.refresh_tokens "
        "WHERE user_id = %s AND NOT revoked AND (%s::text IS NULL OR device_id = %s)",
        (user_id, device, device),
    ).fetchone()
    assert row is not None
    return int(row["n"])


def device_row(owner: Conn, user_id: UUID, device: str) -> dict[str, Any] | None:
    return owner.execute(
        "SELECT * FROM identity.trusted_devices WHERE user_id = %s AND device_id = %s",
        (user_id, device),
    ).fetchone()


def attempts(owner: Conn) -> list[dict[str, Any]]:
    return owner.execute("SELECT * FROM identity.sign_in_attempts ORDER BY id").fetchall()


def attempt_count(owner: Conn) -> int:
    row = owner.execute("SELECT count(*) AS n FROM identity.sign_in_attempts").fetchone()
    assert row is not None
    return int(row["n"])


def last_attempt(owner: Conn) -> dict[str, Any]:
    rows = attempts(owner)
    assert rows, "no sign-in attempt was recorded"
    return rows[-1]


class Auth:
    """The ``api.auth_*`` routines called as ``xcode_app``, with test defaults."""

    def __init__(self, conn: Conn) -> None:
        self.conn = conn

    def lookup(
        self,
        phone: str = PHONE,
        device: str = TRUSTED,
        now: datetime = T0,
        *,
        token_hash: str | None = None,
        pin_try: bool = True,
    ) -> dict[str, Any] | None:
        return self.conn.execute(
            "SELECT * FROM api.auth_account_lookup(%s, %s, %s, %s, %s, %s)",
            ("req-lookup", phone, device, token_hash, pin_try, now),
        ).fetchone()

    def lookup_user(
        self, user_id: UUID, device: str = TRUSTED, now: datetime = T0
    ) -> dict[str, Any] | None:
        return self.conn.execute(
            "SELECT * FROM api.auth_account_lookup_user(%s, %s, %s, %s)",
            ("req-lookup-user", user_id, device, now),
        ).fetchone()

    def start(
        self,
        *,
        phone: str = PHONE,
        device: str = UNTRUSTED,
        token_hash: str | None = None,
        code_hash: str = CODE_HASH,
        skip_cooldown: bool = False,
        now: datetime = T0,
    ) -> dict[str, Any]:
        result: dict[str, Any] = call(
            self.conn,
            "auth_start",
            "req-start",
            phone,
            device,
            token_hash,
            code_hash,
            skip_cooldown,
            now,
        )
        return result

    def pin(
        self,
        *,
        phone: str = PHONE,
        device: str = UNTRUSTED,
        token_hash: str | None = None,
        pin_ok: bool = True,
        checked_hash: str | None = PIN_HASH,
        code_hash: str = CODE_HASH,
        refresh_hash: str | None = None,
        skip_cooldown: bool = False,
        now: datetime = T0,
    ) -> dict[str, Any]:
        """The PIN step as the service runs it: the lookup (statement one), then the decision."""
        self.lookup(phone, device, now, token_hash="" if token_hash is None else token_hash)
        result: dict[str, Any] = call(
            self.conn,
            "auth_pin",
            "req-pin",
            phone,
            device,
            token_hash,
            pin_ok,
            checked_hash,
            code_hash,
            refresh_hash or new_token_hash(),
            skip_cooldown,
            now,
        )
        return result

    def check_code(
        self,
        purpose: str,
        *,
        phone: str = PHONE,
        device: str = UNTRUSTED,
        code_hash: str = CODE_HASH,
        replacement_hash: str = NEW_CODE_HASH,
        name: str | None = None,
        trust: bool = True,
        token_hash: str | None = None,
        refresh_hash: str | None = None,
        trust_days: int | None = None,
        now: datetime = T0,
    ) -> dict[str, Any]:
        result: dict[str, Any] = call(
            self.conn,
            "auth_check_code",
            "req-code",
            phone,
            device,
            purpose,
            code_hash,
            replacement_hash,
            name,
            trust,
            token_hash,
            refresh_hash or new_token_hash(),
            trust_days,
            now,
        )
        return result

    def resend_code(
        self,
        purpose: str,
        *,
        phone: str = PHONE,
        device: str = UNTRUSTED,
        code_hash: str = NEW_CODE_HASH,
        skip_cooldown: bool = False,
        now: datetime = T0,
    ) -> dict[str, Any]:
        result: dict[str, Any] = call(
            self.conn,
            "auth_resend_code",
            "req-resend",
            phone,
            device,
            purpose,
            code_hash,
            skip_cooldown,
            now,
        )
        return result

    def change_pin(
        self,
        user_id: UUID,
        *,
        device: str = TRUSTED,
        current_ok: bool = True,
        checked_hash: str | None = PIN_HASH,
        pin_hash: str = NEW_PIN_HASH,
        now: datetime = T0,
    ) -> dict[str, Any]:
        result: dict[str, Any] = call(
            self.conn,
            "auth_change_pin",
            "req-change-pin",
            user_id,
            device,
            current_ok,
            checked_hash,
            pin_hash,
            now,
        )
        return result

    def device_list(
        self, user_id: UUID, *, device: str = TRUSTED, now: datetime = T0
    ) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = call(self.conn, "auth_device_list", user_id, device, now)
        return result

    def device_remove(self, user_id: UUID, row_id: UUID, *, now: datetime = T0) -> dict[str, Any]:
        result: dict[str, Any] = call(
            self.conn, "auth_device_remove", "req-device-remove", user_id, row_id, now
        )
        return result

    def sign_in(
        self,
        user_id: UUID | None,
        *,
        device: str = TRUSTED,
        pin_ok: bool = True,
        checked_hash: str | None = PIN_HASH,
        code_hash: str | None = CODE_HASH,
        refresh_hash: str | None = None,
        skip_cooldown: bool = False,
        now: datetime = T0,
    ) -> dict[str, Any]:
        result: dict[str, Any] = call(
            self.conn,
            "auth_sign_in",
            "req-sign-in",
            user_id,
            device,
            pin_ok,
            checked_hash,
            code_hash,
            refresh_hash or new_token_hash(),
            skip_cooldown,
            now,
        )
        return result

    def verify_device(
        self,
        *,
        phone: str = PHONE,
        device: str = UNTRUSTED,
        code_hash: str = CODE_HASH,
        replacement_hash: str = NEW_CODE_HASH,
        refresh_hash: str | None = None,
        trust_days: int | None = None,
        now: datetime = T0,
    ) -> dict[str, Any]:
        result: dict[str, Any] = call(
            self.conn,
            "auth_verify_device",
            "req-verify-device",
            phone,
            device,
            code_hash,
            replacement_hash,
            refresh_hash or new_token_hash(),
            trust_days,
            now,
        )
        return result

    def request_code(
        self,
        purpose: str,
        *,
        phone: str = PHONE,
        device: str = UNTRUSTED,
        code_hash: str = CODE_HASH,
        skip_cooldown: bool = False,
        now: datetime = T0,
    ) -> dict[str, Any]:
        result: dict[str, Any] = call(
            self.conn,
            "auth_request_code",
            "req-request-code",
            phone,
            device,
            purpose,
            code_hash,
            skip_cooldown,
            now,
        )
        return result

    def verify_code(
        self,
        purpose: str,
        *,
        phone: str = PHONE,
        device: str = UNTRUSTED,
        code_hash: str = CODE_HASH,
        replacement_hash: str = NEW_CODE_HASH,
        now: datetime = T0,
    ) -> dict[str, Any]:
        result: dict[str, Any] = call(
            self.conn,
            "auth_verify_code",
            "req-verify-code",
            phone,
            device,
            purpose,
            code_hash,
            replacement_hash,
            now,
        )
        return result

    def complete_pin(
        self,
        purpose: str,
        *,
        phone: str = PHONE,
        device: str = UNTRUSTED,
        code_hash: str = CODE_HASH,
        new_pin_is_current: bool = False,
        checked_hash: str | None = PIN_HASH,
        pin_hash: str = NEW_PIN_HASH,
        name: str | None = None,
        trust: bool = True,
        token_hash: str | None = None,
        refresh_hash: str | None = None,
        trust_days: int | None = None,
        now: datetime = T0,
    ) -> dict[str, Any]:
        """A completion; ``checked_hash`` is ignored on a first PIN (the account has none)."""
        result: dict[str, Any] = call(
            self.conn,
            "auth_complete_pin",
            "req-complete-pin",
            phone,
            device,
            purpose,
            code_hash,
            new_pin_is_current,
            checked_hash if purpose == "pin_reset" else None,
            pin_hash,
            name,
            trust,
            token_hash,
            refresh_hash or new_token_hash(),
            trust_days,
            now,
        )
        return result

    def refresh(
        self,
        token_hash: str,
        *,
        device: str = TRUSTED,
        new_hash: str | None = None,
        now: datetime = T0,
    ) -> dict[str, Any]:
        result: dict[str, Any] = call(
            self.conn,
            "auth_refresh",
            "req-refresh",
            token_hash,
            device,
            new_hash or new_token_hash(),
            now,
        )
        return result

    def sign_out(
        self, token_hash: str, *, device: str = TRUSTED, now: datetime = T0
    ) -> dict[str, Any]:
        result: dict[str, Any] = call(
            self.conn, "auth_sign_out", "req-sign-out", token_hash, device, now
        )
        return result

    def revoke_device(
        self, user_id: UUID, *, device: str = TRUSTED, now: datetime = T0
    ) -> dict[str, Any]:
        result: dict[str, Any] = call(
            self.conn, "auth_revoke_device", "req-revoke-device", user_id, device, now
        )
        return result

    def withdraw(self, code_id: UUID, *, now: datetime = T0) -> None:
        call(self.conn, "auth_withdraw_code", "req-withdraw", code_id, now)

    def resolve(
        self, user_id: UUID, version: int, *, device: str = TRUSTED, now: datetime = T0
    ) -> dict[str, Any]:
        result: dict[str, Any] = call(
            self.conn, "auth_resolve_session", user_id, device, version, now
        )
        return result


@dataclass(frozen=True, slots=True)
class FleetScenario:
    owner: Account
    companies: tuple[UUID, ...]
    vehicles: tuple[UUID, ...]
    items: tuple[UUID, ...]
    first_day: date
    last_day: date


def build_fleet(
    operator: Conn,
    owner: Conn,
    app: Conn,
    *,
    companies: int = 2,
    vehicles_per_company: int = 3,
    days: int = 6,
    now: datetime = T0,
) -> FleetScenario:
    """A small fleet written as ``xcode_app`` does: an Owner provisioned through the operator
    routine, then companies, a catalogue, vehicles with weekly targets, one vehicle away for a
    while and ``days`` days of revenue ending yesterday, all through the ``api.*`` routines."""
    from .setup_rows import split_week
    from .tenancy import REQUEST, write

    account = make_account(operator, owner)
    actor = (account.user_id, account.organization_id, REQUEST)
    today = (now + NAIROBI_OFFSET).date()
    first_day = today - timedelta(days=days)
    last_day = today - timedelta(days=1)

    company_ids = tuple(
        write(app, "setup_company_create", *actor, f"Company {n}", None, now)["id"]
        for n in range(1, companies + 1)
    )
    main = write(app, "setup_expense_main_category_create", *actor, "Running costs", now)["id"]
    category = write(app, "setup_expense_category_create", *actor, "Garage", main, now)["id"]
    items = tuple(
        write(app, "setup_expense_item_create", *actor, category, name, now)["id"]
        for name in ("Spares", "Tyres")
    )
    vehicle_ids: list[UUID] = []
    for index, company in enumerate(company_ids):
        for n in range(vehicles_per_company):
            number = index * vehicles_per_company + n + 1
            created = write(
                app,
                "setup_vehicle_create",
                *actor,
                company,
                f"KDA {number:03d}A",
                f"F-{number}",
                first_day,
                list(split_week(42000 + 7000 * n)),
                None,
                None,
                now,
            )
            vehicle_ids.append(created["id"])
    away = vehicle_ids[0]
    write(app, "setup_vehicle_retire", *actor, away, today - timedelta(days=3), None, now)
    write(app, "setup_vehicle_restore", *actor, away, today - timedelta(days=1), None, now)

    for offset in range(days):
        day = first_day + timedelta(days=offset)
        for number, vehicle in enumerate(vehicle_ids):
            if vehicle == away and today - timedelta(days=3) <= day < last_day:
                continue
            write(
                app,
                "revenue_capture",
                *actor,
                vehicle,
                day,
                5000 + 100 * number + 10 * offset,
                None,
                None,
                None,
                None,
                now,
            )
    return FleetScenario(account, company_ids, tuple(vehicle_ids), items, first_day, last_day)


def seed_10x(owner: Conn, organization_id: UUID, factor: int = 10) -> int:
    """Multiply the organization's fleet ``factor`` times with set-based inserts as
    ``xcode_owner``: every vehicle gets ``factor - 1`` copies with their target sets, away
    periods and revenue records, for the ``EXPLAIN`` runs of ``docs/perf/revenue.md``. The
    copies carry no change-log rows. Returns the number of vehicles afterwards."""
    owner.execute("DROP TABLE IF EXISTS seed_copy")
    owner.execute(
        "CREATE TEMP TABLE seed_copy AS "
        "SELECT f.id AS source, gen_random_uuid() AS copy, k.k, "
        "row_number() OVER (ORDER BY k.k, f.registration) AS n "
        "FROM setup.fleet_vehicles AS f CROSS JOIN generate_series(1, %s) AS k (k) "
        "WHERE f.organization_id = %s",
        (factor - 1, organization_id),
    )
    owner.execute(
        "INSERT INTO setup.fleet_vehicles (organization_id, id, company_id, registration, "
        "fleet_number, joined_on, left_on, initial_investment) "
        "SELECT f.organization_id, c.copy, f.company_id, "
        "'KZ' || chr(65 + ((c.n / 26) %% 26)::int) || ' ' || lpad(c.n::text, 3, '0') "
        "|| chr(65 + (c.n %% 26)::int), 'S' || c.n, f.joined_on, f.left_on, f.initial_investment "
        "FROM seed_copy AS c JOIN setup.fleet_vehicles AS f "
        "ON f.organization_id = %s AND f.id = c.source",
        (organization_id,),
    )
    owner.execute(
        "INSERT INTO setup.vehicle_target_sets (organization_id, vehicle_id, starts_on, monday, "
        "tuesday, wednesday, thursday, friday, saturday, sunday, created_at, created_by) "
        "SELECT t.organization_id, c.copy, t.starts_on, t.monday, t.tuesday, t.wednesday, "
        "t.thursday, t.friday, t.saturday, t.sunday, t.created_at, t.created_by "
        "FROM seed_copy AS c JOIN setup.vehicle_target_sets AS t "
        "ON t.organization_id = %s AND t.vehicle_id = c.source",
        (organization_id,),
    )
    owner.execute(
        "INSERT INTO setup.vehicle_away_periods (organization_id, vehicle_id, left_on, "
        "returned_on, created_at) "
        "SELECT a.organization_id, c.copy, a.left_on, a.returned_on, a.created_at "
        "FROM seed_copy AS c JOIN setup.vehicle_away_periods AS a "
        "ON a.organization_id = %s AND a.vehicle_id = c.source",
        (organization_id,),
    )
    owner.execute(
        "INSERT INTO revenue.records (organization_id, vehicle_id, business_date, amount, reason, "
        "note, captured_at, captured_by, updated_at, updated_by, corrected_after_date, version) "
        "SELECT r.organization_id, c.copy, r.business_date, r.amount, r.reason, r.note, "
        "r.captured_at, r.captured_by, r.updated_at, r.updated_by, r.corrected_after_date, "
        "r.version "
        "FROM seed_copy AS c JOIN revenue.records AS r "
        "ON r.organization_id = %s AND r.vehicle_id = c.source",
        (organization_id,),
    )
    owner.execute("DROP TABLE seed_copy")
    row = owner.execute(
        "SELECT count(*) AS n FROM setup.fleet_vehicles WHERE organization_id = %s",
        (organization_id,),
    ).fetchone()
    assert row is not None
    return int(row["n"])
