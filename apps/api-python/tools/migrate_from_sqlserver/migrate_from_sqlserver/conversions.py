"""The conversions and drop predicates the table map names (``docs/10-data-migration.md`` 3, 3.1).

A conversion takes a table's rows after the column mapping and returns the rows to load,
recording in the ledger every value it changes, every row it drops (with the documented
reason) and every row it makes. A drop predicate says whether a row is not moved by design.
"""

from __future__ import annotations

import re
import uuid
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from . import legacy_catalogue as legacy
from .formats import Instant, duplicate_json_keys, upper_c
from .records import Ledger, Record, TargetCatalogue, ToolError, decimal_of, instant_of
from .tablemap import Table
from .timezones import WINDOWS_TO_IANA

DEVICE_IDLE_DAYS = 90
DEFAULT_REFRESH_DAYS = 30
PIN_TRIES = 5
MAIN_CATEGORY_NAMES = {1: "Repairs and maintenance", 2: "Recurring charges", 3: "Loan repayments"}
DERIVED_IDS = uuid.UUID("0b5e3f7c-6a52-4d1e-9a3c-2f7d8e1b4c60")
"""Namespace of the ids this tool makes (main categories): the same input gives the same id."""

POLICY_BOUNDS = {
    "password_min_length": (12, 128),
    "password_history": (0, 24),
    "pin_length": (4, 8),
    "lockout_threshold": (3, 10),
    "lockout_minutes": (1, 60),
    "access_token_minutes": (1, 15),
    "refresh_token_days": (1, 90),
    "idle_unlock_seconds": (30, 3600),
}
_DAY_COLUMNS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday")
_PHONE_FORMS = (
    re.compile(r"254([17][0-9]{8})"),
    re.compile(r"0([17][0-9]{8})"),
    re.compile(r"([17][0-9]{8})"),
)


@dataclass
class Context:
    extracted_at: datetime
    parsed: dict[str, list[Record]]
    catalogue: TargetCatalogue
    ledger: Ledger
    fleet_numbers: Mapping[str, str] | None = None
    permission_sets: list[dict[str, object]] | None = None
    _members: set[tuple[object, object]] | None = None

    def is_member(self, organization_id: object, user_id: object) -> bool:
        if self._members is None:
            self._members = {
                (r.values["organization_id"], r.values["user_id"])
                for r in self.parsed.get("Memberships", [])
            }
        return (organization_id, user_id) in self._members


type Conversion = Callable[[Table, list[Record], Context], list[Record]]
type Drop = Callable[[Record, Context], bool]


def _instant(value: object) -> datetime | None:
    if isinstance(value, Instant):
        return value.value
    if isinstance(value, datetime):
        return value
    return None


def normalize_phone(text: str) -> str | None:
    """``identity.normalize_phone``: keep the decimal digits; a non-ASCII digit is no number."""
    digits = "".join(ch for ch in text if ch.isdecimal())
    if any(not "0" <= ch <= "9" for ch in digits):
        return None
    for form in _PHONE_FORMS:
        found = form.fullmatch(digits)
        if found:
            return "+254" + found.group(1)
    return None


def user_email(table: Table, rows: list[Record], ctx: Context) -> list[Record]:
    for row in rows:
        email = row.values["email"]
        if isinstance(email, str) and email != email.lower():
            ctx.ledger.change(table.target, row.key, "email", email, email.lower(), "lower-cased")
            row.values["email"] = email.lower()
    return rows


def user_phone(table: Table, rows: list[Record], ctx: Context) -> list[Record]:
    for row in rows:
        phone = row.values["phone_number"]
        if not isinstance(phone, str):
            continue
        normal = normalize_phone(phone)
        if normal is not None and normal != phone:
            ctx.ledger.change(
                table.target, row.key, "phone_number", phone, normal, "normalised phone number"
            )
            row.values["phone_number"] = normal
    return rows


def user_lock(table: Table, rows: list[Record], ctx: Context) -> list[Record]:
    """A pause running at the extraction instant becomes the lock; a lapsed one clears."""
    for row in rows:
        paused = _instant(row.src.get("PausedUntil"))
        failed = int(row.values["failed_attempts"])  # type: ignore[call-overload]
        if paused is not None and paused > ctx.extracted_at:
            new, reason = PIN_TRIES, "a pause running at the extraction instant becomes the lock"
        elif paused is not None:
            new, reason = 0, "a lapsed pause clears the count"
        else:
            new, reason = min(failed, PIN_TRIES), "clamped to the five-try lock"
        if new != failed:
            ctx.ledger.change(table.target, row.key, "failed_attempts", failed, new, reason)
            row.values["failed_attempts"] = new
        untrusted = int(row.values["untrusted_failed_attempts"])  # type: ignore[call-overload]
        if untrusted > PIN_TRIES:
            ctx.ledger.change(
                table.target,
                row.key,
                "untrusted_failed_attempts",
                untrusted,
                PIN_TRIES,
                "clamped to the five-try lock",
            )
            row.values["untrusted_failed_attempts"] = PIN_TRIES
    return rows


def time_zone(table: Table, rows: list[Record], ctx: Context) -> list[Record]:
    kept: list[Record] = []
    for row in rows:
        zone = row.values["time_zone"]
        if zone is None or zone in ctx.catalogue.time_zones:
            kept.append(row)
            continue
        mapped = WINDOWS_TO_IANA.get(str(zone))
        if mapped is not None and mapped in ctx.catalogue.time_zones:
            ctx.ledger.change(
                table.target, row.key, "time_zone", zone, mapped, "Windows id mapped to IANA"
            )
            row.values["time_zone"] = mapped
            kept.append(row)
            continue
        ctx.ledger.reject(
            table.target,
            table.source,
            row.key,
            f"time zone {zone!r} is neither an IANA name nor a mapped Windows id (question 18)",
            constraint="time_zone",
        )
    return kept


def blank_optional_text(table: Table, rows: list[Record], ctx: Context) -> list[Record]:
    optional = (
        "logo_light_url",
        "logo_dark_url",
        "favicon_url",
        "terms_url",
        "privacy_url",
        "domain",
        "support_email",
    )
    for row in rows:
        for column in optional:
            value = row.values.get(column)
            if isinstance(value, str) and not value.strip():
                ctx.ledger.change(table.target, row.key, column, value, None, "blank becomes null")
                row.values[column] = None
    return rows


def policy_bounds(table: Table, rows: list[Record], ctx: Context) -> list[Record]:
    for row in rows:
        for column, (low, high) in POLICY_BOUNDS.items():
            value = int(row.values[column])  # type: ignore[call-overload]
            clamped = max(low, min(high, value))
            if clamped != value:
                ctx.ledger.change(
                    table.target, row.key, column, value, clamped, f"clamped into {low}..{high}"
                )
                row.values[column] = clamped
    return rows


def normalized_name(table: Table, rows: list[Record], ctx: Context) -> list[Record]:
    for row in rows:
        before = row.src.get("NormalizedName")
        after = upper_c(str(row.values["name"]))
        if before != after:
            ctx.ledger.change(
                table.target,
                row.key,
                "normalized_name",
                before,
                after,
                "re-derived by upper() under the C collation (question 17)",
            )
    return rows


def fleet_number(table: Table, rows: list[Record], ctx: Context) -> list[Record]:
    numbers = ctx.fleet_numbers or {}
    registrations = {str(row.values["registration"]) for row in rows}
    unknown = sorted(set(numbers) - registrations)
    if unknown:
        raise ToolError(f"the fleet-number list names registrations not in the fleet: {unknown}")
    taken: dict[tuple[object, object, str], str] = {}
    for row in rows:
        number = numbers.get(str(row.values["registration"]))
        row.values["fleet_number"] = number
        if number is None:
            continue
        slot = (row.values["organization_id"], row.values["company_id"], upper_c(number))
        if slot in taken:
            raise ToolError(
                f"fleet number {number!r} is given to {taken[slot]} and "
                f"{row.values['registration']} in the same PSV company"
            )
        taken[slot] = str(row.values["registration"])
        ctx.ledger.change(table.target, row.key, "fleet_number", None, number, "owner's list")
    return rows


def main_category_id(organization_id: object, bucket: object) -> str:
    return str(uuid.uuid5(DERIVED_IDS, f"expense-main-category:{organization_id}:{bucket}"))


def main_categories(table: Table, rows: list[Record], ctx: Context) -> list[Record]:
    made: list[Record] = []
    seen: set[tuple[object, object]] = set()
    for category in ctx.parsed.get("ExpenseCategory", []):
        organization_id = category.values["organization_id"]
        bucket = category.values["bucket"]
        if bucket is None or (organization_id, bucket) in seen:
            continue
        seen.add((organization_id, bucket))
        key = f"OrganizationId={organization_id}|Bucket={bucket}"
        name = MAIN_CATEGORY_NAMES[int(bucket)]  # type: ignore[call-overload]
        made.append(
            Record(
                key,
                {},
                {
                    "organization_id": organization_id,
                    "id": main_category_id(organization_id, bucket),
                    "name": name,
                },
            )
        )
        ctx.ledger.derive(table.target, key, f"main category {name!r} for bucket {bucket}")
    return sorted(made, key=lambda r: r.key)


def main_category(table: Table, rows: list[Record], ctx: Context) -> list[Record]:
    for row in rows:
        bucket = row.values["bucket"]
        row.values["main_category_id"] = (
            None if bucket is None else main_category_id(row.values["organization_id"], bucket)
        )
    return rows


def split_week(weekly: Decimal) -> tuple[Decimal, Decimal] | None:
    """Monday to Saturday ``weekly / 7`` to the cent, Sunday the rest; None if a day is not
    positive. ``weekly`` has two decimals, so ``weekly / 7`` never ends in an exact half cent
    and the rounding mode cannot matter (``0010_setup`` uses ``round``)."""
    day = (weekly / 7).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    sunday = weekly - 6 * day
    if day <= 0 or sunday <= 0:
        return None
    return day, sunday


def target_sets(table: Table, rows: list[Record], ctx: Context) -> list[Record]:
    """One set per vehicle and date from the highest revision, the week split by day."""
    groups: dict[tuple[object, object, object], list[Record]] = defaultdict(list)
    for row in rows:
        values = row.values
        groups[(values["organization_id"], values["vehicle_id"], values["starts_on"])].append(row)
    kept: list[Record] = []
    for group in groups.values():
        group.sort(key=lambda r: int(r.src["Revision"]))  # type: ignore[call-overload]
        chosen = group[-1]
        for older in group[:-1]:
            ctx.ledger.drop(table.target, table.source, older.key, "superseded_target")
        weekly = decimal_of(chosen.src["WeeklyAmount"], chosen.key)
        split = split_week(weekly)
        if split is None:
            ctx.ledger.drop(table.target, table.source, chosen.key, "target_too_small")
            continue
        day, sunday = split
        for column in _DAY_COLUMNS:
            chosen.values[column] = day
        chosen.values["sunday"] = sunday
        ctx.ledger.derive(
            table.target, chosen.key, f"weekly {weekly} split into 6 x {day} and Sunday {sunday}"
        )
        kept.append(chosen)
    return sorted(kept, key=lambda r: r.key)


def allocation_sums(table: Table, rows: list[Record], ctx: Context) -> list[Record]:
    """A version whose vehicle shares do not add up to its amount fails the deferred trigger
    ``setup.check_allocation_sum`` at commit; name it here instead."""
    shares: dict[tuple[object, object], list[Decimal]] = defaultdict(list)
    for allocation in ctx.parsed.get("RecurringAllocation", []):
        values = allocation.values
        amount = decimal_of(values["amount"], allocation.key)
        shares[(values["organization_id"], values["version_id"])].append(amount)
    kept: list[Record] = []
    for row in rows:
        parts = shares.get((row.values["organization_id"], row.values["id"]), [])
        expected = row.values["amount"]
        if not 1 <= len(parts) <= 500 or sum(parts, Decimal(0)) != expected:
            ctx.ledger.reject(
                table.target,
                table.source,
                row.key,
                f"{len(parts)} vehicle shares add up to {sum(parts, Decimal(0))}, not {expected}",
                constraint="check_allocation_sum",
            )
            continue
        kept.append(row)
    return kept


def _closure(keys: Iterable[str], needs: Mapping[str, Iterable[str]]) -> set[str]:
    found = set(keys)
    stack = list(found)
    while stack:
        for needed in needs.get(stack.pop(), ()):
            if needed not in found:
                found.add(needed)
                stack.append(needed)
    return found


_LEGACY_NEEDS: dict[str, tuple[str, ...]] = defaultdict(tuple)
for _permission, _needs in legacy.DEPENDENCIES:
    _LEGACY_NEEDS[_permission] = (*_LEGACY_NEEDS[_permission], _needs)
_LEGACY_ROLES = {name.lower(): frozenset(keys) for name, keys in legacy.ROLE_DEFAULTS.items()}


def old_set(role: str | None, granted: set[str], denied: set[str]) -> set[str]:
    """What a person held under the .NET resolver (the ``access_old_sets`` query of
    ``0009_access``): role defaults and granted overrides with their dependencies, minus
    denials, minus every key whose dependencies are not all held."""
    starting = set(_LEGACY_ROLES.get((role or "").lower(), frozenset())) | granted
    held = _closure(starting, _LEGACY_NEEDS) - denied
    return {key for key in held if _closure({key}, _LEGACY_NEEDS) <= held}


def new_set(role: str | None, old: set[str], catalogue: TargetCatalogue) -> set[str]:
    """The person's rights in the 59-right catalogue (the ``access_new_sets`` query)."""
    targets = {new for keys in catalogue.translations.values() for new in keys}
    needed = {need for keys in catalogue.dependencies.values() for need in keys}
    defaults = catalogue.role_defaults.get((role or "").lower(), frozenset())
    chosen = {new for key in old for new in catalogue.translations.get(key, ())}
    chosen |= {
        key
        for key in defaults
        if key in catalogue.catalogue and key not in targets and key not in needed
    }
    return _closure(chosen, catalogue.dependencies) & catalogue.catalogue


def permission_translation(table: Table, rows: list[Record], ctx: Context) -> list[Record]:
    """Every person's overrides rewritten through ``tenancy.permission_translations``."""
    catalogue = ctx.catalogue
    roles = {
        (r.values["organization_id"], r.values["id"]): str(r.values["name"])
        for r in ctx.parsed.get("Roles", [])
    }
    person_role = {
        (r.values["organization_id"], r.values["user_id"]): roles.get(
            (r.values["organization_id"], r.values["role_id"])
        )
        for r in ctx.parsed.get("PersonRoles", [])
    }
    granted: dict[tuple[object, object], set[str]] = defaultdict(set)
    denied: dict[tuple[object, object], set[str]] = defaultdict(set)
    for row in rows:
        member = (row.values["organization_id"], row.values["user_id"])
        key = str(row.values["permission"])
        if key not in legacy.KEYS:
            ctx.ledger.drop(table.target, table.source, row.key, "unknown_permission")
            continue
        ctx.ledger.drop(table.target, table.source, row.key, "translated_override")
        (granted if row.values["granted"] else denied)[member].add(key)
    made: list[Record] = []
    sets: list[dict[str, object]] = []
    for membership in sorted(ctx.parsed.get("Memberships", []), key=lambda r: r.key):
        member = (membership.values["organization_id"], membership.values["user_id"])
        role = person_role.get(member)
        old = old_set(role, granted[member], denied[member])
        new = new_set(role, old, catalogue)
        defaults = catalogue.role_defaults.get((role or "").lower(), frozenset())
        role_rights = defaults & catalogue.catalogue
        translated = {n for key in old for n in catalogue.translations.get(key, ())}
        sets.append(
            {
                "organization_id": member[0],
                "user_id": member[1],
                "role": role,
                "old": sorted(old),
                "new": sorted(new),
                "not_carried": sorted(
                    key for key in old if not catalogue.translations.get(key, frozenset()) & new
                ),
                "gained": sorted(new - translated),
            }
        )
        overrides = [(key, True) for key in new - role_rights]
        overrides += [(key, False) for key in role_rights - new]
        for key, grant in sorted(overrides):
            row_key = f"OrganizationId={member[0]}|UserId={member[1]}|Permission={key}"
            made.append(
                Record(
                    row_key,
                    {},
                    {
                        "organization_id": member[0],
                        "user_id": member[1],
                        "permission": key,
                        "granted": grant,
                    },
                )
            )
            ctx.ledger.derive(
                table.target, row_key, ("granted" if grant else "denied") + " by the translation"
            )
    ctx.permission_sets = sets
    return made


def audit_ids(table: Table, rows: list[Record], ctx: Context) -> list[Record]:
    """The identity ``id`` replaces the source GUID, numbered in occurrence order."""

    def order(row: Record) -> tuple[datetime, str, str]:
        moment = instant_of(row.values["occurred_at"], row.key)
        return moment, str(row.values["organization_id"]), str(row.src["Id"])

    for number, row in enumerate(sorted(rows, key=order), start=1):
        row.values["id"] = number
        ctx.ledger.change(
            table.target,
            row.key,
            "id",
            row.src["Id"],
            number,
            "identity id numbered in occurrence order",
        )
    return rows


def json_keys(table: Table, rows: list[Record], ctx: Context) -> list[Record]:
    for row in rows:
        for column in ("before", "after"):
            text = row.values.get(column)
            if isinstance(text, str):
                for name in duplicate_json_keys(text):
                    ctx.ledger.change(
                        table.target,
                        row.key,
                        column,
                        f"key {name!r} twice",
                        "the last value",
                        "jsonb keeps the last of a repeated key",
                    )
    return rows


def device_dates(table: Table, rows: list[Record], ctx: Context) -> list[Record]:
    """``trusted_at`` and ``last_used_at`` from the device's refresh tokens: the source has no
    dates, so each token's issue instant is its expiry minus the refresh lifetime of the
    person's organization; a device with no token gets no evidence of use."""
    days_by_org = {
        r.values["organization_id"]: int(r.values["refresh_token_days"])  # type: ignore[call-overload]
        for r in ctx.parsed.get("SecurityPolicies", [])
    }
    org_of = {
        r.values["user_id"]: r.values["organization_id"]
        for r in ctx.parsed.get("Memberships", [])
        if r.values["active"]
    }
    issued: dict[tuple[object, object], list[datetime]] = defaultdict(list)
    for token in ctx.parsed.get("RefreshTokens", []):
        values = token.values
        expires = instant_of(values["expires_at"], token.key)
        days = days_by_org.get(org_of.get(values["user_id"]), DEFAULT_REFRESH_DAYS)
        issued[(values["user_id"], values["device_id"])].append(expires - timedelta(days=days))
    unused = ctx.extracted_at - timedelta(days=DEVICE_IDLE_DAYS)
    for row in rows:
        moments = issued.get((row.values["user_id"], row.values["device_id"]), [])
        if moments:
            first = min(*moments, ctx.extracted_at)
            last = min(max(moments), ctx.extracted_at)
            reason = "issue instant of the device's first and latest refresh token"
        else:
            first = last = unused
            reason = "no refresh token: no evidence of use, so the device needs a code"
        row.values["trusted_at"] = first
        row.values["last_used_at"] = last
        ctx.ledger.change(table.target, row.key, "trusted_at", None, first, reason)
        ctx.ledger.change(table.target, row.key, "last_used_at", None, last, reason)
    return rows


def petty_cash_review(table: Table, rows: list[Record], ctx: Context) -> list[Record]:
    """Only an expense has a status (DEC-22); a sent-back expense waits with its note."""
    for row in rows:
        values = row.values
        status = row.src.get("Status")
        if values["kind"] != 2:
            for column in ("status", "reviewed_by", "reviewed_at", "sent_back_note"):
                if values[column] is not None:
                    ctx.ledger.change(
                        table.target,
                        row.key,
                        column,
                        values[column],
                        None,
                        "cash given and credit notes carry no review (DEC-22)",
                    )
                    values[column] = None
        elif status == 3:
            ctx.ledger.change(
                table.target,
                row.key,
                "status",
                "sentBack (3)",
                "waiting (1)",
                "a sent-back expense waits with its note (DEC-21)",
            )
    return rows


def computed_total(table: Table, rows: list[Record], ctx: Context) -> list[Record]:
    for row in rows:
        units = decimal_of(row.values["units"], row.key)
        unit_amount = decimal_of(row.values["unit_amount"], row.key)
        total = (units * unit_amount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if total != row.src.get("Total"):
            ctx.ledger.change(
                table.target,
                row.key,
                "total",
                row.src.get("Total"),
                total,
                "recomputed by the generated column round(units * unit_amount, 2)",
            )
    return rows


def trimmed_note(table: Table, rows: list[Record], ctx: Context) -> list[Record]:
    for row in rows:
        note = row.values.get("note")
        if isinstance(note, str):
            trimmed = note.strip() or None
            if trimmed != note:
                ctx.ledger.change(table.target, row.key, "note", note, trimmed, "trimmed")
                row.values["note"] = trimmed
    return rows


def no_membership(row: Record, ctx: Context) -> bool:
    return not ctx.is_member(row.values["organization_id"], row.values["user_id"])


def revoked_token(row: Record, ctx: Context) -> bool:
    return bool(row.values["revoked"])


def expired_token(row: Record, ctx: Context) -> bool:
    expires = _instant(row.values["expires_at"])
    return expires is not None and expires <= ctx.extracted_at


CONVERSIONS: dict[str, Conversion] = {
    "user_email": user_email,
    "user_phone": user_phone,
    "user_lock": user_lock,
    "time_zone": time_zone,
    "blank_optional_text": blank_optional_text,
    "policy_bounds": policy_bounds,
    "normalized_name": normalized_name,
    "fleet_number": fleet_number,
    "main_categories": main_categories,
    "main_category": main_category,
    "target_sets": target_sets,
    "allocation_sums": allocation_sums,
    "permission_translation": permission_translation,
    "audit_ids": audit_ids,
    "json_keys": json_keys,
    "device_dates": device_dates,
    "petty_cash_review": petty_cash_review,
    "computed_total": computed_total,
    "trimmed_note": trimmed_note,
}

DROPS: dict[str, Drop] = {
    "no_membership": no_membership,
    "revoked_token": revoked_token,
    "expired_token": expired_token,
}
