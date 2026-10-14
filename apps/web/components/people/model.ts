import { shiftDate } from "@xcode/shared/dates";
import {
  formatPhone,
  normalisePhone,
  phoneError,
  plural,
} from "@xcode/shared/format";

import type { SavePersonRequest } from "../../lib/endpoints/people";
import type {
  BackLimit,
  BackLimitMode,
  Permission,
  Person,
  PersonStatus,
  Role,
  ScopeOptions,
} from "../../lib/types";

export const APPROVALS = [
  "pettycash.approve_item",
  "pettycash.approve_day",
  "bills.approve",
];

// Holding a float is the right to add petty cash expenses (pettycash.is_holder).
export const FLOAT_RIGHT = "pettycash.spend";

// Where a person is with signing in (v2.33), from the API's status or, for an older answer, from the old flags.
export function personStatus(person: Person): PersonStatus {
  if (person.status) return person.status;
  if (!person.active) return "blocked";
  return person.hasPin ? "active" : "not_signed_in";
}

export const STATUS_CHIPS: Record<
  PersonStatus,
  { label: string; tone: "ok" | "wait" | "bad" }
> = {
  active: { label: "Active", tone: "ok" },
  not_signed_in: { label: "Not signed in yet", tone: "wait" },
  pin_reset_due: { label: "PIN reset due", tone: "wait" },
  locked: { label: "Locked", tone: "bad" },
  blocked: { label: "Blocked", tone: "bad" },
};

export function roleDefaults(roles: Role[] | undefined, role: string) {
  return roles?.find((candidate) => candidate.name === role)?.permissions ?? [];
}

export function scopeLabel(person: Person, options?: ScopeOptions) {
  if (person.scopeMode === "all") return "All vehicles";
  if (person.scopeMode === "companies") {
    if (person.otherCompanies > 0) {
      const total = person.companyIds.length + person.otherCompanies;
      return `${plural(total, "company", "companies")} (${person.otherCompanies} hidden)`;
    }
    const names = person.companyIds
      .map(
        (id) => options?.companies.find((company) => company.id === id)?.name,
      )
      .filter(Boolean);
    return names.length === person.companyIds.length && names.length <= 2
      ? names.join(", ")
      : plural(person.companyIds.length, "company", "companies");
  }
  if (person.otherVehicles > 0) {
    const total = person.vehicleIds.length + person.otherVehicles;
    return `${plural(total, "vehicle", "vehicles")} (${person.otherVehicles} hidden)`;
  }
  return plural(person.vehicleIds.length, "vehicle", "vehicles");
}

// Ticking a permission ticks what it needs; unticking one unticks what depends on it.
export function withNeeds(selected: string[], key: string, all: Permission[]) {
  const next = new Set([...selected, key]);
  const pending = [key];
  while (pending.length) {
    // Taken off the list before the search, not inside it: find() would call the test once per permission
    // and pop a fresh key each time, so it only ever matched one that happens to be listed first.
    const current = pending.pop();
    for (const need of all.find((item) => item.key === current)?.needs ?? []) {
      if (next.has(need)) continue;
      next.add(need);
      pending.push(need);
    }
  }
  return [...next];
}

export function withoutDependents(
  selected: string[],
  key: string,
  all: Permission[],
) {
  const removed = new Set([key]);
  let changed = true;
  while (changed) {
    changed = false;
    for (const item of all) {
      if (
        removed.has(item.key) ||
        !selected.includes(item.key) ||
        !item.needs.some((need) => removed.has(need))
      )
        continue;
      removed.add(item.key);
      changed = true;
    }
  }
  return selected.filter((item) => !removed.has(item));
}

type Actor = { role: string; permissions: string[] } | null | undefined;

// Only an Owner may give the Owner role, but an owner's own role is still listed, so the locked picker shows it.
export function assignableRoles(
  roles: Role[] | undefined,
  person: Person | undefined,
  session: Actor,
) {
  return (roles ?? []).filter(
    (role) =>
      role.name === person?.role ||
      session?.role === "Owner" ||
      (role.name !== "Owner" &&
        role.permissions.every((permission) =>
          session?.permissions.includes(permission),
        )),
  );
}

export type ScopeGroup = {
  id: string;
  name: string;
  vehicles: ScopeOptions["vehicles"];
};

export function scopeGroups(options: ScopeOptions): ScopeGroup[] {
  const companiesWithVehicles = options.companies
    .map((company) => ({
      ...company,
      vehicles: options.vehicles.filter(
        (vehicle) => vehicle.companyId === company.id,
      ),
    }))
    .filter((company) => company.vehicles.length);
  const unlistedVehicles = options.vehicles.filter(
    (vehicle) =>
      !options.companies.some((company) => company.id === vehicle.companyId),
  );
  return [
    ...companiesWithVehicles,
    ...(unlistedVehicles.length
      ? [{ id: "", name: "", vehicles: unlistedVehicles }]
      : []),
  ];
}

export type PersonForm = {
  firstName: string;
  lastName: string;
  phoneNumber: string;
  email: string;
  role: string;
  scopeMode: string;
  companyIds: string[];
  vehicleIds: string[];
  // null until the person changes a permission: the role's defaults apply, whenever the roles arrive.
  permissions: string[] | null;
  approvalLimit: string;
  // How far back they may change records (v2.32): the rolling limit and the fixed date.
  backMode: BackLimitMode;
  backCount: string;
  backFromOn: boolean;
  backFrom: string;
};

export function initialForm(person?: Person): PersonForm {
  const limit = person?.backLimit;
  return {
    firstName: person?.firstName ?? "",
    lastName: person?.lastName ?? "",
    phoneNumber: person ? formatPhone(person.phoneNumber) : "",
    email: person?.email ?? "",
    role: person?.role ?? "Revenue clerk",
    scopeMode: person?.scopeMode ?? "vehicles",
    companyIds: person?.companyIds ?? [],
    vehicleIds: person?.vehicleIds ?? [],
    permissions: person?.permissions ?? null,
    approvalLimit: person?.approvalLimit ? String(person.approvalLimit) : "",
    // New people start on 7 days back.
    backMode: limit?.mode ?? (person ? "none" : "days"),
    backCount:
      limit?.count !== undefined && limit?.count !== null
        ? String(limit.count)
        : person
          ? ""
          : "7",
    backFromOn: Boolean(limit?.from),
    backFrom: limit?.from ?? "",
  };
}

export function readBackLimit(form: PersonForm): BackLimit {
  return {
    mode: form.backMode,
    count: form.backMode === "none" ? null : Number(form.backCount) || 0,
    from: form.backFromOn && form.backFrom ? form.backFrom : null,
  };
}

// The limit in words, as the list shows it: "Any date", "2 days back", "1 month back, not before 14 September 2026".
export function backLimitText(
  limit: BackLimit,
  formatDateOnly: (value: string) => string,
) {
  const parts: string[] = [];
  if (limit.mode === "days")
    parts.push(
      limit.count ? plural(limit.count, "day", "days") + " back" : "Today only",
    );
  if (limit.mode === "months")
    parts.push(plural(limit.count ?? 0, "month", "months") + " back");
  if (limit.from)
    parts.push(
      `${parts.length ? "not" : "Not"} before ${formatDateOnly(limit.from)}`,
    );
  return parts.length ? parts.join(", ") : "Any date";
}

// The earliest date the limit allows today, or "" for no limit. Months go back to the same day; when that day does
// not exist, the last day of that month.
export function earliestAllowed(limit: BackLimit, today: string): string {
  let rolling = "";
  if (limit.mode === "days") rolling = shiftDate(today, -(limit.count ?? 0));
  else if (limit.mode === "months") {
    const [year, month, day] = today.split("-").map(Number);
    const target = new Date(Date.UTC(year, month - 1 - (limit.count ?? 0), 1));
    const last = new Date(
      Date.UTC(target.getUTCFullYear(), target.getUTCMonth() + 1, 0),
    ).getUTCDate();
    target.setUTCDate(Math.min(day, last));
    rolling = target.toISOString().slice(0, 10);
  }
  return limit.from && limit.from > rolling ? limit.from : rolling;
}

// What the person's scope holds that is not offered here (archived, out of the fleet, or outside the editor's own
// scope). It cannot be ticked, so it is named instead, and saving keeps it.
export function keptCounts(form: PersonForm, options: ScopeOptions) {
  return {
    companies: form.companyIds.filter(
      (id) => !options.companies.some((company) => company.id === id),
    ).length,
    vehicles: form.vehicleIds.filter(
      (id) => !options.vehicles.some((vehicle) => vehicle.id === id),
    ).length,
  };
}

export type ErrorKey =
  | "firstName"
  | "lastName"
  | "phoneNumber"
  | "email"
  | "role"
  | "scope"
  | "backLimit"
  | "permissions";

export type Errors = Partial<Record<ErrorKey, string>>;

export type Pane = "det" | "lim" | "sig" | "acc";

// The pane that holds the first problem, so a save error opens it.
export function paneFor(errors: Errors): Pane | null {
  if (
    errors.firstName ||
    errors.lastName ||
    errors.phoneNumber ||
    errors.email ||
    errors.role
  )
    return "det";
  if (errors.scope || errors.backLimit) return "lim";
  if (errors.permissions) return "acc";
  return null;
}

export type PersonContext = {
  // False until the roles request answers.
  rolesLoaded: boolean;
  assignableCount: number;
  permissions: string[];
  today: string;
};

export function validatePerson(form: PersonForm, ctx: PersonContext): Errors {
  const next: Errors = {};
  if (!form.firstName.trim()) next.firstName = "Enter a first name.";
  if (!form.lastName.trim()) next.lastName = "Enter a last name.";
  const phoneValidation = phoneError(normalisePhone(form.phoneNumber));
  if (phoneValidation) next.phoneNumber = phoneValidation;
  if (!/^[^\s@]+@[^\s@]+\.[a-z]{2,}$/i.test(form.email.trim()))
    next.email = "Enter the email that receives codes.";
  if (ctx.rolesLoaded && !ctx.assignableCount)
    next.role = "You cannot assign any available role.";
  if (form.scopeMode === "companies" && !form.companyIds.length)
    next.scope = "Pick at least one vehicle this person can see.";
  if (form.scopeMode === "vehicles" && !form.vehicleIds.length)
    next.scope = "Pick at least one vehicle this person can see.";
  if (
    form.backMode !== "none" &&
    (form.backCount.trim() === "" ||
      !/^\d+$/.test(form.backCount.trim()) ||
      (form.backMode === "months" && Number(form.backCount) === 0))
  )
    next.backLimit = `Enter the number of ${form.backMode}.`;
  else if (form.backFromOn && !form.backFrom)
    next.backLimit = "Enter the date.";
  else if (form.backFromOn && ctx.today && form.backFrom > ctx.today)
    next.backLimit = "The date is after today.";
  if (!ctx.permissions.length)
    next.permissions = "Tick at least one permission.";
  return next;
}

export function personPayload(
  form: PersonForm,
  ctx: {
    selectedRole: string;
    permissions: string[];
    needsLimit: boolean;
    version?: number;
  },
): SavePersonRequest {
  return {
    firstName: form.firstName.trim(),
    lastName: form.lastName.trim(),
    email: form.email.trim(),
    phoneNumber: normalisePhone(form.phoneNumber),
    role: ctx.selectedRole,
    scopeMode: form.scopeMode,
    companyIds: form.scopeMode === "companies" ? form.companyIds : [],
    vehicleIds: form.scopeMode === "vehicles" ? form.vehicleIds : [],
    permissions: ctx.permissions,
    approvalLimit:
      ctx.needsLimit && form.approvalLimit ? Number(form.approvalLimit) : null,
    backLimit: readBackLimit(form),
    version: ctx.version,
  };
}
