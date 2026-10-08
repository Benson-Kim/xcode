import {
  formatPhone,
  normalisePhone,
  phoneError,
  plural,
} from "@xcode/shared/format";

import type { SavePersonRequest } from "../../lib/endpoints/people";
import type { Permission, Person, Role, ScopeOptions } from "../../lib/types";

export const APPROVALS = [
  "pettycash.approve_item",
  "pettycash.approve_day",
  "bills.approve",
];

export type SignInState = "active" | "waiting" | "none";

export function signInState(person: Person): SignInState {
  if (!person.active) return "none";
  return person.hasPin ? "active" : "waiting";
}

export function roleDefaults(roles: Role[] | undefined, role: string) {
  return roles?.find((candidate) => candidate.name === role)?.permissions ?? [];
}

export function changesFromRole(permissions: string[], defaults: string[]) {
  return (
    permissions.filter((key) => !defaults.includes(key)).length +
    defaults.filter((key) => !permissions.includes(key)).length
  );
}

export function scopeLabel(person: Person, options?: ScopeOptions) {
  if (person.scopeMode === "all") return "All companies";
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
};

export function initialForm(person?: Person): PersonForm {
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
  };
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

export type Errors = Partial<
  Record<
    | "firstName"
    | "lastName"
    | "phoneNumber"
    | "email"
    | "role"
    | "scope"
    | "permissions",
    string
  >
>;

export type PersonContext = {
  // False until the roles request answers.
  rolesLoaded: boolean;
  assignableCount: number;
  permissions: string[];
};

export function validatePerson(form: PersonForm, ctx: PersonContext): Errors {
  const next: Errors = {};
  if (!form.firstName.trim()) next.firstName = "Enter a first name.";
  if (!form.lastName.trim()) next.lastName = "Enter a last name.";
  const phoneValidation = phoneError(normalisePhone(form.phoneNumber));
  if (phoneValidation) next.phoneNumber = phoneValidation;
  if (!/^[^\s@]+@[^\s@]+\.[a-z]{2,}$/i.test(form.email.trim()))
    next.email = "Enter an email address like name@company.co.ke";
  if (ctx.rolesLoaded && !ctx.assignableCount)
    next.role = "You cannot assign any available role.";
  if (form.scopeMode === "companies" && !form.companyIds.length)
    next.scope = "Tick at least one company.";
  if (form.scopeMode === "vehicles" && !form.vehicleIds.length)
    next.scope = "Tick at least one vehicle.";
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
    version: ctx.version,
  };
}
