"""The rules of ``docs/10-data-migration.md`` 7.3 and 7.4 for the legacy database.

``prepare`` runs once every extract file is parsed: it checks each petty-cash copy against
its original, makes the organization's ids, works out every person's move from ``--people``
(e-mail, number, role, names, rights), the merged and held-back items, the vehicles'
registrations, companies and first days, and the exceptions that do not depend on the target.
The conversions then fill each target table in load order. ``finish`` adds to
``transform.json`` what ``load`` checks and ``report`` prints: the people (by role and legacy
creation date, never by name), the parts of each source figure that did not move, the ledger
of every legacy table, and the exceptions list.

Personal details (names, e-mails, numbers, payees) reach only the load files: every ledger
entry about a person carries the legacy id, never a value.
"""

from __future__ import annotations

import json
import re
import uuid
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from . import legacy_tablemap as m
from .database import Connection, read_catalogue
from .formats import Instant, upper_c
from .profile import LEGACY, Manifest, Options, Profile, SourceFile, TableResult
from .records import Ledger, Record, TargetCatalogue, ToolError, plain
from .tablemap import Table

NAIROBI = ZoneInfo(m.TIME_ZONE)
CENT = Decimal("0.01")
NOT_MOVED = "(not moved)"
_SLUG = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")
_REGISTRATION = re.compile(r"(K[A-Z]{2})([0-9]{3}[A-Z])")
BLOCKING = frozenset(
    {
        "identity.users",
        "tenancy.organizations",
        "tenancy.memberships",
        "tenancy.person_roles",
        "tenancy.data_scopes",
    }
)
"""A refused person or organization stops the load: everything else hangs on them."""


@dataclass
class Plan:
    """Where one legacy user moves; personal values stay in memory and in the load files."""

    user_id: str
    created_on: date
    created_at: str
    legacy_role: str | None
    role: str
    legacy: list[str]
    translated: set[str] = field(default_factory=set)
    not_carried: list[str] = field(default_factory=list)
    email: str | None = None
    phone: str | None = None
    first_name: str = ""
    last_name: str = ""
    one_word: bool = False
    email_changed: bool = False
    phone_changed: bool = False
    refusal: str | None = None

    @property
    def label(self) -> str:
        return f"{self.role} (legacy {self.legacy_role or 'no role'}, created {self.created_at})"


@dataclass
class LegacyContext:
    extracted_at: datetime
    ledger: Ledger
    options: Options
    catalogue: TargetCatalogue
    figures: dict[str, Any]
    counts: dict[str, int]
    parsed: dict[str, list[Record]] = field(default_factory=dict)
    organization_id: str = ""
    organization_name: str = ""
    slug: str = ""
    role_ids: dict[str, str] = field(default_factory=dict)
    plans: dict[str, Plan] = field(default_factory=dict)
    accepted: list[Record] = field(default_factory=list)
    migrated_by: str = ""
    holder: str = ""
    item_of: dict[str, str] = field(default_factory=dict)
    merged: dict[str, str] = field(default_factory=dict)
    uncategorised: set[str] = field(default_factory=set)
    plus_items: set[str] = field(default_factory=set)
    item_names: dict[str, str] = field(default_factory=dict)
    registration: dict[str, str] = field(default_factory=dict)
    company_of: dict[str, str | None] = field(default_factory=dict)
    companies: dict[str, str] = field(default_factory=dict)
    first_day: dict[str, date] = field(default_factory=dict)
    balance_days: list[dict[str, Any]] = field(default_factory=list)

    def rows(self, name: str) -> list[Record]:
        return self.parsed.get(name, [])

    def made_id(self, *parts: object) -> str:
        return str(uuid.uuid5(m.LEGACY_IDS, ":".join(str(p) for p in parts)))


def _text(value: object) -> str | None:
    return None if value is None else str(value)


def _money(value: object) -> Decimal | None:
    if value is None:
        return None
    if not isinstance(value, Decimal):
        raise ToolError(f"not a number: {value!r}")
    return value


def _moment(value: object) -> datetime:
    moment = value.value if isinstance(value, Instant) else value
    if not isinstance(moment, datetime):
        raise ToolError(f"not an instant: {value!r}")
    return moment


def local_day(value: object) -> date:
    return _moment(value).astimezone(NAIROBI).date()


def money_text(value: Decimal) -> str:
    """An amount as the owner reads it: to the cent, or with every digit it has beyond."""
    cents = value.quantize(Decimal("0.01"))
    return format(cents if cents == value else value, "f")


def _local_time(value: object) -> str:
    return _moment(value).astimezone(NAIROBI).strftime("%Y-%m-%d %H:%M")


def _closure(keys: Iterable[str], needs: Mapping[str, Iterable[str]]) -> set[str]:
    found = set(keys)
    stack = list(found)
    while stack:
        for needed in needs.get(stack.pop(), ()):
            if needed not in found:
                found.add(needed)
                stack.append(needed)
    return found


def translate(legacy: Iterable[str], catalogue: TargetCatalogue) -> tuple[set[str], list[str]]:
    """The rights a set of legacy permission names gives (7.4), with every right's needs,
    and the names that give none."""
    rights: set[str] = set()
    not_carried: list[str] = []
    for name in sorted(set(legacy)):
        given = m.RIGHTS.get(name)
        if not given:
            not_carried.append(name)
            continue
        rights.update(given)
    return _closure(rights, catalogue.dependencies) & catalogue.catalogue, not_carried


def begin(conn: Connection, manifest: Manifest, ledger: Ledger, options: Options) -> LegacyContext:
    if options.people is None or not options.migrated_by:
        raise ToolError(
            "an extract of the legacy database needs --people (legacy_email,email,phone,role) "
            "and --migrated-by (docs/10 7.2)"
        )
    return LegacyContext(
        extracted_at=manifest.extracted_at,
        ledger=ledger,
        options=options,
        catalogue=read_catalogue(conn),
        figures=dict(manifest.data.get("figures") or {}),
        counts={e.name: int((manifest.table(e.name) or {}).get("rows", 0)) for e in m.EXTRACTS},
    )


def prepare(conn: Connection, ctx: LegacyContext) -> None:
    _check_copies(ctx)
    _organization(ctx)
    _people(conn, ctx)
    _items(ctx)
    _vehicles(ctx)
    _balance_days(ctx)
    for extract in m.EXTRACTS:
        if extract.fate == m.DROPPED:
            for row in ctx.rows(extract.name):
                ctx.ledger.drop(NOT_MOVED, extract.name, row.key, extract.rule)


def _check_copies(ctx: LegacyContext) -> None:
    """Each record copied from a petty-cash expense matches its original (amount, day,
    vehicle, item), and each committed expense the old trigger copies has its copy."""
    originals = {str(r.src["id"]): r for r in ctx.rows("petty_cash")}
    copied: dict[str, str] = {}
    for copy in ctx.rows("records_copies"):
        original_id = str(copy.src["petty_cash_id"])
        original = originals.get(original_id)
        if original is None:
            raise ToolError(
                f"records {copy.key} copies petty_cash id={original_id}, which does not exist"
            )
        differs = [
            name
            for name, ours, theirs in (
                ("amount", copy.src["minus"], original.src["minus"]),
                ("day", copy.src["date"], original.src["date"]),
                ("vehicle", copy.src["vehicle_id"], original.src["vehicle_id"]),
                ("item", copy.src["entry_id"], original.src["entry_id"]),
            )
            if ours != theirs
        ]
        if differs:
            raise ToolError(
                f"records {copy.key} copies petty_cash id={original_id} but differs in "
                f"{', '.join(differs)}: the old application's copy disagrees with its original; "
                "fix it there and extract again (docs/10 7.3)"
            )
        if original_id in copied:
            raise ToolError(f"petty_cash id={original_id} has two copies in records")
        copied[original_id] = copy.key
    for original_id, row in originals.items():
        committed_expense = (
            row.src["committed"]
            and not row.src["credit_note"]
            and row.src["plus"] is None
            and row.src["minus"] is not None
            and row.src["entry_id"] is not None
            and row.src["vehicle_id"] is not None
        )
        if committed_expense and original_id not in copied:
            raise ToolError(
                f"petty_cash {row.key} is a committed expense without its copy in records: the "
                "old application's trigger did not run, and the vehicle costs would not add up"
            )


def _organization(ctx: LegacyContext) -> None:
    name = (ctx.options.organization_name or m.ORGANIZATION_NAME).strip()
    slug = ctx.options.organization_slug or m.ORGANIZATION_SLUG
    if not 1 <= len(name) <= 200:
        raise ToolError("--organization-name must be 1 to 200 characters")
    if len(slug) > 100 or not _SLUG.fullmatch(slug):
        raise ToolError("--organization-slug must be lower-case words joined by hyphens")
    ctx.organization_name, ctx.slug = name, slug
    ctx.organization_id = str(uuid.uuid5(m.LEGACY_IDS, f"organization:{slug}"))
    ctx.role_ids = {role: ctx.made_id("role", ctx.organization_id, role) for role in m.ROLES}


def _people(conn: Connection, ctx: LegacyContext) -> None:
    people = ctx.options.people or {}
    users = ctx.rows("users")
    legacy_emails = {str(u.src["email"]).strip().lower() for u in users if u.src["email"]}
    for person in people.values():
        if person.legacy_email not in legacy_emails:
            raise ToolError(
                f"--people line {person.line}: its legacy_email is not a user of the source"
            )
    lines = sorted(people.values(), key=lambda p: p.line)
    normal: dict[int, tuple[str | None, str | None]] = {}
    if lines:
        for row in conn.execute(
            "SELECT t.n, identity.normalize_email(t.e) AS email, "
            "identity.normalize_phone(t.p) AS phone "
            "FROM unnest(%s::int[], %s::text[], %s::text[]) AS t (n, e, p)",
            ([p.line for p in lines], [p.email for p in lines], [p.phone for p in lines]),
        ):
            normal[int(row["n"])] = (row["email"], row["phone"])
    old_phones: dict[str, str | None] = {}
    old = [str(u.src["phone"]) for u in users if u.src["phone"] is not None]
    if old:
        for row in conn.execute(
            "SELECT t.p AS raw, identity.normalize_phone(t.p) AS phone "
            "FROM unnest(%s::text[]) AS t (p)",
            (old,),
        ):
            old_phones[row["raw"]] = row["phone"]

    for user in users:
        user_id = str(user.src["id"])
        legacy_role = _text(user.src["role"])
        legacy = sorted(_legacy_permissions(user))
        given = people.get(str(user.src["email"] or "").strip().lower())
        derived = m.OWNER if legacy_role == m.ADMINISTRATOR else m.FLEET_MANAGER
        role = given.role if given is not None and given.role else derived
        plan = Plan(
            user_id,
            local_day(user.src["created_at"]),
            _local_time(user.src["created_at"]),
            legacy_role,
            role,
            legacy,
        )
        plan.translated, plan.not_carried = translate(legacy, ctx.catalogue)
        name = str(user.src["name"] or "").strip()
        cut = name.rfind(" ")
        if cut < 0:
            plan.first_name = plan.last_name = name
            plan.one_word = True
        else:
            plan.first_name, plan.last_name = name[:cut].strip(), name[cut + 1 :].strip()
        if given is None:
            plan.refusal = "no_person"
        else:
            email, phone = normal[given.line]
            if not given.phone.strip():
                plan.refusal = "no_number"
            elif phone is None:
                plan.refusal = "bad_number"
            elif email is None:
                plan.refusal = "bad_email"
            plan.email, plan.phone = email, phone
            plan.email_changed = email != str(user.src["email"] or "").strip().lower()
            raw_phone = user.src["phone"]
            plan.phone_changed = phone != (old_phones.get(str(raw_phone)) if raw_phone else None)
        ctx.plans[user_id] = plan

    wanted = (ctx.options.migrated_by or "").strip().lower()
    matches = [
        plan
        for user in users
        for plan in [ctx.plans[str(user.src["id"])]]
        if wanted in {plan.email, str(user.src["email"] or "").strip().lower()}
    ]
    if len(matches) != 1:
        raise ToolError("--migrated-by must name exactly one legacy user (old or new e-mail)")
    if matches[0].role != m.OWNER or matches[0].refusal is not None:
        raise ToolError("--migrated-by must name a person who moves as an Owner (question 91)")
    ctx.migrated_by = matches[0].user_id
    holders = [str(u.src["id"]) for u in users if u.src["is_default_petty_cash_manager"]]
    if len(holders) != 1:
        raise ToolError(
            f"the legacy database marks {len(holders)} default petty-cash managers; the one "
            "float needs exactly one holder (docs/10 7.3 row 14)"
        )
    ctx.holder = holders[0]


def _legacy_permissions(user: Record) -> list[str]:
    raw = user.src["permissions"]
    names = json.loads(str(raw)) if raw is not None else []
    if not isinstance(names, list) or not all(isinstance(n, str) for n in names):
        raise ToolError(f"users {user.key}: permissions is not a list of names")
    return [str(n) for n in names]


def _items(ctx: LegacyContext) -> None:
    for entry in ctx.rows("entries"):
        entry_id = str(entry.src["id"])
        ctx.item_names[entry_id] = str(entry.src["title"]).strip()
        if entry.src["factor"] == "plus":
            ctx.plus_items.add(entry_id)
        elif entry.src["category_id"] is None:
            ctx.uncategorised.add(entry_id)
    kept: dict[tuple[str, str], str] = {}
    candidates = [
        e
        for e in ctx.rows("entries")
        if str(e.src["id"]) not in ctx.plus_items and str(e.src["id"]) not in ctx.uncategorised
    ]
    candidates.sort(key=lambda e: (_moment(e.src["created_at"]), str(e.src["id"])))
    for entry in candidates:
        entry_id = str(entry.src["id"])
        slot = (str(entry.src["category_id"]), upper_c(str(entry.src["title"]).strip()))
        first = kept.setdefault(slot, entry_id)
        ctx.item_of[entry_id] = first
        if first != entry_id:
            ctx.merged[entry_id] = first


def _vehicles(ctx: LegacyContext) -> None:
    vehicles = sorted(
        ctx.rows("vehicles"), key=lambda v: (_moment(v.src["created_at"]), str(v.src["id"]))
    )
    names: dict[str, str] = {}
    for vehicle in vehicles:
        vehicle_id = str(vehicle.src["id"])
        raw = str(vehicle.src["registration"])
        compact = re.sub(r"\s+", "", raw).upper()
        found = _REGISTRATION.fullmatch(compact)
        ctx.registration[vehicle_id] = f"{found.group(1)} {found.group(2)}" if found else raw
        sacco = (str(vehicle.src["sacco"]).strip() if vehicle.src["sacco"] else "") or None
        if sacco is None:
            ctx.company_of[vehicle_id] = None
            continue
        folded = upper_c(sacco)
        company_id = ctx.made_id("psv-company", ctx.organization_id, folded)
        ctx.company_of[vehicle_id] = company_id
        ctx.companies[company_id] = names.setdefault(folded, sacco)
    days: dict[str, date] = {}
    sources = ("records_revenue", "records_expenses", "records_copies", "petty_cash", "provisions")
    for source in sources:
        for row in ctx.rows(source):
            owner = row.src.get("vehicle_id")
            when = row.src.get("date")
            if owner is None or not isinstance(when, date):
                continue
            key = str(owner)
            days[key] = min(days.get(key, when), when)
    ctx.first_day = days


def _balance_days(ctx: LegacyContext) -> None:
    """The days the stored daily balance moves by another amount than the day's entries
    (the old trigger's carry-forward): listed for the owner to trace (letter point 10). Both are
    compared to the cent: below it is the noise of ``double precision``, not a balance."""
    net: dict[date, Decimal] = defaultdict(Decimal)
    for row in ctx.rows("petty_cash"):
        when = row.src["date"]
        if isinstance(when, date):
            net[when] += (_money(row.src["plus"]) or Decimal(0)) - (
                _money(row.src["minus"]) or Decimal(0)
            )
    balances = sorted(ctx.rows("petty_cash_daily_balances"), key=lambda r: str(r.src["date"]))
    days = sorted(net)
    running, index = Decimal(0), 0
    stored_before = entries_before = Decimal(0)
    for balance in balances:
        when = balance.src["date"]
        if not isinstance(when, date):
            raise ToolError(f"petty_cash_daily_balances {balance.key} has no day")
        while index < len(days) and days[index] <= when:
            running += net[days[index]]
            index += 1
        stored = _money(balance.src["closing_balance"]) or Decimal(0)
        step = stored - stored_before
        entries_step = running - entries_before
        difference = (step - entries_step).quantize(CENT)
        if difference != 0:
            ctx.balance_days.append(
                {
                    "day": when,
                    "difference": difference,
                    "stored": stored,
                    "entries": running,
                    "key": balance.key,
                }
            )
        stored_before, entries_before = stored, running


def _reject(
    ctx: LegacyContext, table: Table, row: Record, reason: str, blocking: bool = False
) -> None:
    ctx.ledger.reject(table.target, table.source, row.key, m.HELD_BACK[reason], None, blocking)


def _person_change(ctx: LegacyContext, table: Table, key: str, column: str, reason: str) -> None:
    ctx.ledger.change(table.target, key, column, None, None, reason)


def people(table: Table, rows: list[Record], ctx: LegacyContext) -> list[Record]:
    kept: list[Record] = []
    for row in rows:
        plan = ctx.plans[str(row.values["id"])]
        if plan.refusal is not None:
            _reject(ctx, table, row, plan.refusal, blocking=True)
            continue
        row.values["email"] = plan.email
        row.values["phone_number"] = plan.phone
        if plan.email_changed:
            _person_change(ctx, table, row.key, "email", "e-mail from --people (question 90)")
        if plan.phone_changed:
            _person_change(
                ctx, table, row.key, "phone_number", "number from --people (question 90)"
            )
        kept.append(row)
    ctx.accepted = kept
    return kept


def _made(
    ctx: LegacyContext, table: Table, key: str, values: dict[str, object], note: str
) -> Record:
    ctx.ledger.derive(table.target, key, note)
    return Record(key, {}, values)


def organization(table: Table, rows: list[Record], ctx: LegacyContext) -> list[Record]:
    values: dict[str, object] = {
        "id": ctx.organization_id,
        "slug": ctx.slug,
        "name": ctx.organization_name,
    }
    return [_made(ctx, table, f"organization={ctx.slug}", values, "the one organization")]


def organization_settings(table: Table, rows: list[Record], ctx: LegacyContext) -> list[Record]:
    values: dict[str, object] = {"organization_id": ctx.organization_id}
    return [_made(ctx, table, f"organization={ctx.slug}", values, "defaults (docs/04 4.3)")]


def roles(table: Table, rows: list[Record], ctx: LegacyContext) -> list[Record]:
    return [
        _made(
            ctx,
            table,
            f"role={name}",
            {"organization_id": ctx.organization_id, "id": ctx.role_ids[name], "name": name},
            "catalogue role (tenancy.seed_roles)",
        )
        for name in m.ROLES
    ]


def _people_rows(table: Table, ctx: LegacyContext, values: Any, note: str) -> list[Record]:
    made = []
    for user in ctx.accepted:
        plan = ctx.plans[str(user.values["id"])]
        made.append(_made(ctx, table, f"id={plan.user_id}", values(user, plan), note))
    return made


def memberships(table: Table, rows: list[Record], ctx: LegacyContext) -> list[Record]:
    def values(user: Record, plan: Plan) -> dict[str, object]:
        if plan.one_word:
            _person_change(
                ctx,
                table,
                f"id={plan.user_id}",
                "last_name",
                "a one-word name fills first and last name (7.3 row 3)",
            )
        return {
            "organization_id": ctx.organization_id,
            "user_id": plan.user_id,
            "first_name": plan.first_name,
            "last_name": plan.last_name,
            "created_at": user.values["created_at"],
            "updated_at": user.values["updated_at"],
        }

    return _people_rows(table, ctx, values, "membership of a legacy user")


def person_roles(table: Table, rows: list[Record], ctx: LegacyContext) -> list[Record]:
    def values(user: Record, plan: Plan) -> dict[str, object]:
        return {
            "organization_id": ctx.organization_id,
            "user_id": plan.user_id,
            "role_id": ctx.role_ids[plan.role],
        }

    return _people_rows(table, ctx, values, "role from --people or the legacy role (7.3 row 4)")


def overrides(table: Table, rows: list[Record], ctx: LegacyContext) -> list[Record]:
    made: list[Record] = []
    for user in ctx.accepted:
        plan = ctx.plans[str(user.values["id"])]
        if plan.role == m.OWNER:
            continue
        defaults = ctx.catalogue.role_defaults.get(plan.role.lower(), frozenset())
        defaults = frozenset(defaults & ctx.catalogue.catalogue)
        changes = [(key, True) for key in plan.translated - defaults]
        changes += [(key, False) for key in defaults - plan.translated]
        for key, grant in sorted(changes):
            made.append(
                _made(
                    ctx,
                    table,
                    f"id={plan.user_id}|permission={key}",
                    {
                        "organization_id": ctx.organization_id,
                        "user_id": plan.user_id,
                        "permission": key,
                        "granted": grant,
                    },
                    ("granted" if grant else "denied") + " by the translation (7.4)",
                )
            )
    return made


def data_scopes(table: Table, rows: list[Record], ctx: LegacyContext) -> list[Record]:
    def values(user: Record, plan: Plan) -> dict[str, object]:
        return {"organization_id": ctx.organization_id, "user_id": plan.user_id}

    return _people_rows(
        table, ctx, values, "all companies: everybody saw every vehicle (7.3 row 6)"
    )


def companies(table: Table, rows: list[Record], ctx: LegacyContext) -> list[Record]:
    return [
        _made(
            ctx,
            table,
            f"sacco={name}",
            {"organization_id": ctx.organization_id, "id": company_id, "name": name},
            "one company per sacco name (7.3 row 7)",
        )
        for company_id, name in sorted(ctx.companies.items(), key=lambda c: upper_c(c[1]))
    ]


def vehicles(table: Table, rows: list[Record], ctx: LegacyContext) -> list[Record]:
    numbers = {
        _compact(registration): number
        for registration, number in (ctx.options.fleet_numbers or {}).items()
    }
    known = {_compact(str(r.values["registration"])) for r in rows}
    unknown = sorted(set(numbers) - known)
    if unknown:
        raise ToolError(f"the fleet-number list names registrations not in the fleet: {unknown}")
    taken: dict[tuple[object, str], str] = {}
    for row in rows:
        vehicle_id = str(row.values["id"])
        row.values["organization_id"] = ctx.organization_id
        row.values["company_id"] = company = ctx.company_of.get(vehicle_id)
        sacco = str(row.src["sacco"] or "")
        if company is not None and ctx.companies[company] != sacco:
            ctx.ledger.change(
                table.target,
                row.key,
                "company_id",
                sacco,
                ctx.companies[company],
                "one company per sacco name, spelled as on its earliest vehicle (7.3 row 7)",
            )
        old = str(row.values["registration"])
        new = ctx.registration[vehicle_id]
        if new != old:
            ctx.ledger.change(
                table.target,
                row.key,
                "registration",
                old,
                new,
                "upper case with its space (7.3 row 8)",
            )
            row.values["registration"] = new
        created_on = local_day(row.values["created_at"])
        first = ctx.first_day.get(vehicle_id)
        joined = min(created_on, first) if first is not None else created_on
        if joined != created_on:
            ctx.ledger.change(
                table.target,
                row.key,
                "joined_on",
                created_on,
                joined,
                "the vehicle's history starts before it was created in the source (7.3 row 8)",
            )
        row.values["joined_on"] = joined
        number = numbers.get(_compact(old))
        row.values["fleet_number"] = number
        if number is not None:
            slot = (row.values["company_id"], upper_c(number))
            if slot in taken:
                raise ToolError(f"fleet number {number!r} is given twice in one PSV company")
            taken[slot] = new
            ctx.ledger.change(table.target, row.key, "fleet_number", None, number, "owner's list")
    return rows


def _compact(registration: str) -> str:
    return re.sub(r"\s+", "", registration).upper()


def trimmed_name(table: Table, rows: list[Record], ctx: LegacyContext) -> list[Record]:
    for row in rows:
        row.values["organization_id"] = ctx.organization_id
        name = str(row.values["name"])
        if name.strip() != name:
            ctx.ledger.change(table.target, row.key, "name", name, name.strip(), "trimmed")
            row.values["name"] = name.strip()
    return rows


def revenue_days(table: Table, rows: list[Record], ctx: LegacyContext) -> list[Record]:
    days: dict[tuple[str, object], list[Record]] = defaultdict(list)
    for row in rows:
        days[(str(row.values["vehicle_id"]), row.values["business_date"])].append(row)
    kept: list[Record] = []
    for day_rows in days.values():
        day_rows.sort(key=lambda r: (_moment(r.values["captured_at"]), str(r.values["id"])))
        if len({_money(r.src["plus"]) for r in day_rows}) > 1:
            for row in day_rows:
                _reject(ctx, table, row, "differing_day")
            continue
        first, *doubles = day_rows
        for row in doubles:
            ctx.ledger.drop(table.target, table.source, row.key, "double_entry")
        amount = _money(first.src["plus"])
        first.values.update(
            organization_id=ctx.organization_id,
            amount=amount,
            reason=None,
            note=None,
            captured_by=ctx.migrated_by,
            updated_by=ctx.migrated_by,
        )
        if amount == 0:
            first.values.update(amount=None, reason=m.OTHER_REASON, note=m.ZERO_NOTE)
            ctx.ledger.change(
                table.target,
                first.key,
                "amount",
                amount,
                None,
                "0 becomes no revenue, reason Other, note '0 in the old system' (question 93)",
            )
        kept.append(first)
    return sorted(kept, key=lambda r: r.key)


def _unit(total: Decimal, units: Decimal) -> Decimal | None:
    """``total / units`` when it is exact to the cent, else None."""
    unit = total / units
    exact = unit.quantize(Decimal("0.01"))
    return exact if exact * units == total else None


def central_expenses(table: Table, rows: list[Record], ctx: LegacyContext) -> list[Record]:
    kept: list[Record] = []
    for row in rows:
        entry = _text(row.src["entry_id"])
        if entry in ctx.uncategorised:
            _reject(ctx, table, row, "uncategorised")
            continue
        minus = _money(row.src["minus"])
        units = _money(row.src["quantity"])
        unit = minus
        if minus is not None and units is not None and units > 0:
            unit = _unit(minus, units)
            if unit is None:
                _reject(ctx, table, row, "inexact_unit")
                continue
        row.values.update(
            organization_id=ctx.organization_id,
            expense_item_id=ctx.item_of.get(entry, entry) if entry else None,
            units=units,
            unit_amount=unit,
            group_id=row.values["id"],
            group_size=1,
            group_total=minus,
            group_units=units,
            group_unit_amount=unit,
            recorded_by=ctx.migrated_by,
            updated_by=ctx.migrated_by,
        )
        kept.append(row)
    return kept


def petty_cash(table: Table, rows: list[Record], ctx: LegacyContext) -> list[Record]:
    kept: list[Record] = []
    for row in rows:
        src = row.src
        holder = ctx.holder
        manager = _text(src["manager_id"])
        if manager != holder:
            ctx.ledger.change(
                table.target,
                row.key,
                "holder_id",
                manager,
                holder,
                "the one float holder (7.3 row 14)",
            )
        values: dict[str, object] = {
            "organization_id": ctx.organization_id,
            "holder_id": holder,
            "expense_item_id": None,
            "payee": None,
            "note": None,
            "status": None,
            "reviewed_by": None,
            "reviewed_at": None,
        }
        if src["credit_note"]:
            payee = _label(src["source"])
            if payee is not None and payee.lower() == m.CREDIT_NOTE_LABEL:
                payee = None
            values.update(
                kind=m.CREDIT,
                units=Decimal(1),
                unit_amount=_money(src["minus"]),
                payee=payee,
                note=_label(src["description"]),
                recorded_by=holder,
                updated_by=holder,
            )
        elif src["plus"] is not None:
            values.update(
                kind=m.CASH,
                units=Decimal(1),
                unit_amount=_money(src["plus"]),
                note=_label(src["name"]),
                recorded_by=ctx.migrated_by,
                updated_by=ctx.migrated_by,
            )
        else:
            entry = _text(src["entry_id"])
            if row.values["vehicle_id"] is None:
                _reject(ctx, table, row, "no_vehicle")
                continue
            if entry in ctx.uncategorised:
                _reject(ctx, table, row, "uncategorised")
                continue
            units = _money(src["quantity"])
            price = _money(src["unit_price"])
            minus = _money(src["minus"])
            if units is not None and price is not None and not _exact_total(units, price, minus):
                _reject(ctx, table, row, "total_differs")
                continue
            approved = bool(src["committed"])
            values.update(
                kind=m.EXPENSE,
                expense_item_id=ctx.item_of.get(entry, entry) if entry else None,
                units=units,
                unit_amount=price,
                note=_label(src["description"]),
                status=m.APPROVED if approved else m.WAITING,
                reviewed_by=ctx.migrated_by if approved else None,
                reviewed_at=row.values["updated_at"] if approved else None,
                recorded_by=holder,
                updated_by=ctx.migrated_by if approved else holder,
            )
            if src["source"] is not None:
                ctx.ledger.change(
                    table.target,
                    row.key,
                    "payee",
                    None,
                    None,
                    "an expense's label has no place in the target",
                )
        row.values.update(values)
        kept.append(row)
    return kept


def _exact_total(units: Decimal, price: Decimal, total: Decimal | None) -> bool:
    """``units * price`` gives the amount exactly, and the amount is whole cents: the target
    stores ``round(units * unit_amount, 2)``, so anything else would move another amount."""
    return total is not None and units * price == total and total == total.quantize(CENT)


def _label(value: object) -> str | None:
    if value is None:
        return None
    return str(value).strip() or None


def income_category(row: Record, ctx: LegacyContext) -> bool:
    return row.src["factor"] == "plus"


def revenue_item(row: Record, ctx: LegacyContext) -> bool:
    return str(row.values["id"]) in ctx.plus_items


def uncategorised_item(row: Record, ctx: LegacyContext) -> bool:
    return str(row.values["id"]) in ctx.uncategorised


def merged_item_drop(row: Record, ctx: LegacyContext) -> bool:
    return str(row.values["id"]) in ctx.merged


def zero_amount(row: Record, ctx: LegacyContext) -> bool:
    amount = row.src["plus"] if row.src["plus"] is not None else row.src["minus"]
    return amount is not None and amount == 0


CONVERSIONS = {
    "people": people,
    "organization": organization,
    "organization_settings": organization_settings,
    "roles": roles,
    "memberships": memberships,
    "person_roles": person_roles,
    "overrides": overrides,
    "data_scopes": data_scopes,
    "companies": companies,
    "vehicles": vehicles,
    "trimmed_name": trimmed_name,
    "revenue_days": revenue_days,
    "central_expenses": central_expenses,
    "petty_cash": petty_cash,
}
DROPS = {
    "income_category": income_category,
    "revenue_item": revenue_item,
    "uncategorised_item": uncategorised_item,
    "merged_item": merged_item_drop,
    "zero_amount": zero_amount,
}


def _month(value: object) -> str:
    return str(value)[:7]


def _bucket(src: Mapping[str, object]) -> str:
    if src["credit_note"]:
        return "credit note"
    if src["plus"] is not None:
        return "cash"
    return "expense approved" if src["committed"] else "expense waiting"


def finish(ctx: LegacyContext, results: list[TableResult], output_dir: Path) -> dict[str, Any]:
    loaded = {
        str(result.table.source): {r.key for r in result.rows}
        for result in results
        if result.table.source is not None
    }
    people_loaded = loaded.get("users", set())
    return {
        "legacy": {
            "organization_id": ctx.organization_id,
            "organization": ctx.organization_name,
            "migrated_by": ctx.migrated_by,
            "holder": ctx.holder,
            "last_full_month": _last_full_month(ctx.extracted_at),
            "vehicles": dict(sorted(ctx.registration.items())),
        },
        "people": [
            {
                "user_id": plan.user_id,
                "label": plan.label,
                "created_on": plan.created_on.isoformat(),
                "legacy_role": plan.legacy_role,
                "role": plan.role,
                "moved": f"id={plan.user_id}" in people_loaded,
                "legacy": plan.legacy,
                "translated": sorted(plan.translated),
                "not_carried": plan.not_carried,
                "migrated_by": plan.user_id == ctx.migrated_by,
                "holder": plan.user_id == ctx.holder,
            }
            for plan in sorted(ctx.plans.values(), key=lambda p: (p.created_on, p.user_id))
        ],
        "excluded": _excluded(ctx, loaded),
        "sources": _sources(ctx, results, loaded),
        "exceptions": _exceptions(ctx, loaded),
        "listed": _listed(ctx),
    }


def _last_full_month(at: datetime) -> str:
    today = at.astimezone(NAIROBI).date()
    year, month = (today.year, today.month - 1) if today.month > 1 else (today.year - 1, 12)
    return f"{year:04d}-{month:02d}"


def _excluded(ctx: LegacyContext, loaded: Mapping[str, set[str]]) -> dict[str, Any]:
    """The part of each source figure that did not move (dropped or refused rows)."""
    revenue: dict[str, dict[str, dict[str, Decimal]]] = defaultdict(
        lambda: defaultdict(lambda: {"days": Decimal(0), "amount": Decimal(0)})
    )
    moved_days = {
        (str(r.src["vehicle_id"]), r.src["date"])
        for r in ctx.rows("records_revenue")
        if r.key in loaded.get("records_revenue", set())
    }
    seen_days: set[tuple[str, object]] = set()
    for row in ctx.rows("records_revenue"):
        if row.key in loaded.get("records_revenue", set()):
            continue
        vehicle, when = str(row.src["vehicle_id"]), row.src["date"]
        cell = revenue[vehicle][_month(when)]
        cell["amount"] += _money(row.src["plus"]) or Decimal(0)
        if (vehicle, when) not in moved_days and (vehicle, when) not in seen_days:
            cell["days"] += 1
            seen_days.add((vehicle, when))
    costs: dict[str, dict[str, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    for row in ctx.rows("records_expenses"):
        if row.key not in loaded.get("records_expenses", set()):
            costs[str(row.src["vehicle_id"])][_month(row.src["date"])] += _money(
                row.src["minus"]
            ) or Decimal(0)
    moved_cash = {
        str(r.src["id"]) for r in ctx.rows("petty_cash") if r.key in loaded.get("petty_cash", set())
    }
    for copy in ctx.rows("records_copies"):
        if str(copy.src["petty_cash_id"]) not in moved_cash:
            costs[str(copy.src["vehicle_id"])][_month(copy.src["date"])] += _money(
                copy.src["minus"]
            ) or Decimal(0)
    buckets: dict[str, dict[str, Decimal]] = defaultdict(
        lambda: {"count": Decimal(0), "amount": Decimal(0)}
    )
    float_excluded = Decimal(0)
    for row in ctx.rows("petty_cash"):
        if row.key in loaded.get("petty_cash", set()):
            continue
        plus = _money(row.src["plus"]) or Decimal(0)
        minus = _money(row.src["minus"]) or Decimal(0)
        bucket = buckets[_bucket(row.src)]
        bucket["count"] += 1
        bucket["amount"] += plus if row.src["plus"] is not None else minus
        float_excluded += plus - minus
    result: dict[str, Any] = plain_tree(
        {"revenue": revenue, "vehicle_costs": costs, "petty_cash": buckets, "float": float_excluded}
    )
    return result


def plain_tree(value: object) -> Any:
    if isinstance(value, Mapping):
        return {str(k): plain_tree(v) for k, v in sorted(value.items())}
    return plain(value)


def _sources(
    ctx: LegacyContext, results: list[TableResult], loaded: Mapping[str, set[str]]
) -> list[dict[str, Any]]:
    """Every legacy row loaded, dropped by a named rule, refused, or replaced, per file."""
    dropped: dict[str, int] = defaultdict(int)
    refused: dict[str, int] = defaultdict(int)
    for entry in ctx.ledger.dropped:
        dropped[str(entry["source"])] += 1
    for entry in ctx.ledger.rejected:
        refused[str(entry["source"])] += 1
    out = []
    for extract in m.EXTRACTS:
        rows = ctx.counts[extract.name]
        out.append(
            {
                "file": extract.name,
                "legacy_table": extract.table,
                "rows": rows,
                "loaded": len(loaded.get(extract.name, set())),
                "dropped": dropped[extract.name],
                "refused": refused[extract.name],
                "replaced": rows if extract.fate == m.REPLACED else 0,
                "rule": extract.rule,
            }
        )
    return out


EXCEPTION_KINDS = (
    "held back",
    "left out",
    "double entry dropped",
    "possible double, moved",
    "petty-cash balance day",
)


def _exceptions(ctx: LegacyContext, loaded: Mapping[str, set[str]]) -> list[dict[str, Any]]:
    by_key = {
        (name, row.key): row
        for name in ("records_revenue", "records_expenses", "petty_cash")
        for row in ctx.rows(name)
    }
    rows: list[dict[str, Any]] = []
    for entry in ctx.ledger.rejected:
        source = by_key.get((str(entry["source"]), str(entry["key"])))
        if source is None or entry["blocking"]:
            continue
        rows.append(_exception(ctx, "held back", str(entry["source"]), source, entry["problem"]))
    for entry in ctx.ledger.dropped:
        source = by_key.get((str(entry["source"]), str(entry["key"])))
        if source is None:
            continue
        kind = "left out" if entry["reason"] == "zero_amount" else "double entry dropped"
        rows.append(_exception(ctx, kind, str(entry["source"]), source, m.RULES[entry["reason"]]))
    rows.extend(_possible_doubles(ctx, loaded))
    for day in ctx.balance_days:
        rows.append(
            {
                "kind": "petty-cash balance day",
                "day": day["day"].isoformat(),
                "vehicle": "",
                "item": "Daily balance",
                "amount": money_text(day["difference"]),
                "entered": "",
                "reason": (
                    f"the old daily balance's gap to its own entries changes by "
                    f"{money_text(day['difference'])} here (stored {money_text(day['stored'])}, "
                    f"entries {money_text(day['entries'])}); the new system shows the entries' "
                    "balance (letter point 10)"
                ),
                "legacy_table": "petty_cash_daily_balances",
                "legacy_id": day["key"].removeprefix("id="),
            }
        )
    order = {kind: n for n, kind in enumerate(EXCEPTION_KINDS)}
    rows.sort(key=lambda r: (order[r["kind"]], r["day"], r["vehicle"], r["legacy_id"]))
    return rows


def _item(ctx: LegacyContext, name: str, row: Record) -> str:
    src = row.src
    if name == "petty_cash" and src["credit_note"]:
        return "Credit note"
    if name == "petty_cash" and src["plus"] is not None:
        label = _label(src["name"])
        return f"Cash received: {label}" if label else "Cash received"
    entry = _text(src.get("entry_id"))
    return ctx.item_names.get(entry or "", "(no item)")


def _amount(name: str, row: Record) -> Decimal | None:
    src = row.src
    if name == "records_revenue" or (name == "petty_cash" and src["plus"] is not None):
        return _money(src["plus"])
    return _money(src["minus"])


def _exception(
    ctx: LegacyContext, kind: str, name: str, row: Record, reason: str
) -> dict[str, Any]:
    vehicle = _text(row.src.get("vehicle_id"))
    amount = _amount(name, row)
    return {
        "kind": kind,
        "day": str(row.src["date"]),
        "vehicle": ctx.registration.get(vehicle or "", "") if vehicle else "",
        "item": _item(ctx, name, row),
        "amount": "" if amount is None else money_text(amount),
        "entered": _local_time(row.src["created_at"]),
        "reason": reason,
        "legacy_table": "records" if name.startswith("records") else name,
        "legacy_id": str(row.src["id"]),
    }


def _possible_doubles(ctx: LegacyContext, loaded: Mapping[str, set[str]]) -> list[dict[str, Any]]:
    """Moved petty-cash rows that repeat an earlier one of the same day exactly (expense:
    vehicle, item, quantity and amount; cash: amount and label), for the owner to confirm."""
    groups: dict[tuple[object, ...], list[Record]] = defaultdict(list)
    for row in ctx.rows("petty_cash"):
        src = row.src
        if src["credit_note"]:
            continue
        if src["plus"] is not None:
            slot: tuple[object, ...] = ("cash", src["date"], src["plus"], src["name"])
        else:
            slot = (
                "expense",
                src["date"],
                src["vehicle_id"],
                src["entry_id"],
                src["quantity"],
                src["minus"],
            )
        groups[slot].append(row)
    moved = loaded.get("petty_cash", set())
    out = []
    for group in groups.values():
        group.sort(key=lambda r: (_moment(r.src["created_at"]), str(r.src["id"])))
        first = group[0]
        for row in group[1:]:
            if row.key not in moved:
                continue
            reason = (
                f"repeats the entry of {_local_time(first.src['created_at'])} exactly; moved as "
                "it is: please confirm it, and delete it if it is a double (question 100)"
            )
            out.append(_exception(ctx, "possible double, moved", "petty_cash", row, reason))
    return out


def _listed(ctx: LegacyContext) -> dict[str, Any]:
    """What the owner sees listed beside the exceptions: items held back or merged, the
    provision balances and the budgets that do not move (question 97)."""
    records: dict[str, int] = defaultdict(int)
    for row in ctx.rows("records_expenses"):
        records[_text(row.src["entry_id"]) or ""] += 1
    categories = {str(c.src["id"]): str(c.src["title"]).strip() for c in ctx.rows("categories")}
    provisions: dict[str, Decimal] = defaultdict(Decimal)
    for row in ctx.rows("provisions"):
        amount = _money(row.src["amount"]) or Decimal(0)
        sign = -1 if str(row.src["entry_type"]).upper() == "WITHDRAWAL" else 1
        provisions[str(row.src["vehicle_id"])] += sign * amount
    return {
        "uncategorised_items": [
            {"item": ctx.item_names[i], "records": records[i]} for i in sorted(ctx.uncategorised)
        ],
        "merged_items": [
            {
                "item": ctx.item_names[i],
                "into": ctx.item_names[kept],
                "id": i,
                "kept_id": kept,
            }
            for i, kept in sorted(ctx.merged.items())
        ],
        "provisions": [
            {"vehicle": ctx.registration.get(v, v), "balance": format(b, "f")}
            for v, b in sorted(provisions.items())
        ],
        "budgets": [
            {
                "vehicle": ctx.registration.get(str(r.src["vehicle_id"]), str(r.src["vehicle_id"])),
                "category": categories.get(str(r.src["category_id"]), ""),
                "month": f"{r.src['year']}-{int(str(r.src['month'])):02d}",
                "budget": format(_money(r.src["budget"]) or Decimal(0), "f"),
            }
            for r in sorted(ctx.rows("budgets"), key=lambda r: r.key)
            if (_money(r.src["budget"]) or Decimal(0)) != 0
        ],
    }


def _files() -> tuple[SourceFile, ...]:
    targets = {t.source: t.target for t in m.TABLES if t.source is not None}
    return tuple(
        SourceFile(
            e.name, targets.get(e.name, NOT_MOVED), e.key, e.columns, read_only=e.fate != m.LOADED
        )
        for e in m.EXTRACTS
    )


PROFILE = Profile(
    kind=LEGACY,
    tables=m.TABLES,
    files=_files(),
    not_migrated=m.COUNTED,
    conversions=CONVERSIONS,
    drops=DROPS,
    blocking=BLOCKING,
    begin=begin,
    prepare=prepare,
    finish=finish,
    details=False,
)
