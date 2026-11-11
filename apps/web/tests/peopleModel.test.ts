import { describe, expect, it } from "vitest";

import { createFormatter } from "@xcode/shared/format";

import {
  assignableRoles,
  initialForm,
  invitationText,
  keptCounts,
  personPayload,
  scopeGroups,
  scopeLabel,
  personStatus,
  signInActions,
  statusChip,
  validatePerson,
  withNeeds,
  withoutDependents,
} from "../components/people/model";
import type { Permission, Person, Role, ScopeOptions } from "../lib/types";

const permission = (key: string, needs: string[] = []): Permission => ({
  key,
  label: key,
  needs,
});

const catalogue: Permission[] = [
  permission("c", ["b"]),
  permission("b", ["a"]),
  permission("a"),
  permission("d", ["c"]),
  permission("e"),
];

const role = (name: string, permissions: string[]): Role =>
  ({ id: name, name, permissions }) as Role;

const person = (change: Partial<Person> = {}): Person =>
  ({
    id: "p1",
    firstName: "Amina",
    lastName: "Otieno",
    email: "amina@example.co.ke",
    phoneNumber: "0712345678",
    role: "Revenue clerk",
    active: true,
    hasPin: true,
    scopeMode: "vehicles",
    companyIds: [],
    vehicleIds: [],
    otherCompanies: 0,
    otherVehicles: 0,
    permissions: ["revenue.view"],
    version: 3,
    ...change,
  }) as Person;

describe("withNeeds", () => {
  it("ticks what the permission needs, including a need declared later in the catalogue", () => {
    expect(withNeeds([], "c", catalogue).sort()).toEqual(["a", "b", "c"]);
  });

  it("keeps what is already ticked and adds nothing twice", () => {
    expect(withNeeds(["a", "e"], "b", catalogue).sort()).toEqual([
      "a",
      "b",
      "e",
    ]);
  });
});

describe("withoutDependents", () => {
  it("unticks everything that depends on it, transitively", () => {
    expect(
      withoutDependents(["a", "b", "c", "d", "e"], "a", catalogue),
    ).toEqual(["e"]);
  });

  it("leaves unticked dependents and unrelated permissions alone", () => {
    expect(withoutDependents(["a", "b", "e"], "b", catalogue)).toEqual([
      "a",
      "e",
    ]);
  });
});

describe("assignableRoles", () => {
  const roles = [
    role("Owner", ["x", "y"]),
    role("Manager", ["x", "y"]),
    role("Clerk", ["x"]),
  ];

  it("hides Owner from someone who is not an Owner", () => {
    const names = assignableRoles(roles, undefined, {
      role: "Manager",
      permissions: ["x", "y"],
    }).map((candidate) => candidate.name);
    expect(names).toEqual(["Manager", "Clerk"]);
  });

  it("hides roles holding a permission the editor lacks", () => {
    const names = assignableRoles(roles, undefined, {
      role: "Office admin",
      permissions: ["x"],
    }).map((candidate) => candidate.name);
    expect(names).toEqual(["Clerk"]);
  });

  it("keeps the person's own role", () => {
    const names = assignableRoles(roles, person({ role: "Owner" }), {
      role: "Office admin",
      permissions: ["x"],
    }).map((candidate) => candidate.name);
    expect(names).toEqual(["Owner", "Clerk"]);
  });

  it("lets an Owner give any role", () => {
    expect(
      assignableRoles(roles, undefined, { role: "Owner", permissions: [] }),
    ).toHaveLength(3);
  });

  it("is empty before the roles arrive", () => {
    expect(assignableRoles(undefined, undefined, null)).toEqual([]);
  });
});

describe("scopeLabel", () => {
  const options: ScopeOptions = {
    companies: [
      { id: "c1", name: "Zuri" },
      { id: "c2", name: "Kito" },
      { id: "c3", name: "Mara" },
    ],
    vehicles: [],
  } as ScopeOptions;

  it("says all vehicles", () => {
    expect(scopeLabel(person({ scopeMode: "all" }))).toBe("All vehicles");
  });

  it("names up to two companies and counts more", () => {
    const some = (companyIds: string[]) =>
      scopeLabel(person({ scopeMode: "companies", companyIds }), options);
    expect(some(["c1", "c2"])).toBe("Zuri, Kito");
    expect(some(["c1", "c2", "c3"])).toBe("3 companies");
    expect(some(["c1", "gone"])).toBe("2 companies");
  });

  it("adds the hidden count to the visible one", () => {
    expect(
      scopeLabel(
        person({
          scopeMode: "companies",
          companyIds: ["c1"],
          otherCompanies: 2,
        }),
        options,
      ),
    ).toBe("3 companies (2 hidden)");
    expect(
      scopeLabel(person({ vehicleIds: ["v1"], otherVehicles: 1 }), options),
    ).toBe("2 vehicles (1 hidden)");
  });

  it("counts vehicles", () => {
    expect(scopeLabel(person({ vehicleIds: ["v1"] }))).toBe("1 vehicle");
  });
});

describe("personStatus", () => {
  it("takes the API's status, else blocked without access, not signed in without a PIN, otherwise active", () => {
    expect(personStatus(person({ status: "locked" }))).toBe("locked");
    expect(personStatus(person({ active: false }))).toBe("blocked");
    expect(personStatus(person({ hasPin: false }))).toBe("not_signed_in");
    expect(personStatus(person())).toBe("active");
  });
});

describe("statusChip", () => {
  it("names a known status and never shows an unknown one as a known status", () => {
    expect(statusChip("locked")).toEqual({ label: "Locked", tone: "bad" });
    for (const status of ["suspended", "toString", ""])
      expect(statusChip(status)).toEqual({
        label: "Status unknown",
        tone: "wait",
      });
  });
});

describe("scopeGroups and keptCounts", () => {
  const options = {
    companies: [
      { id: "c1", name: "Zuri" },
      { id: "c2", name: "Empty" },
    ],
    vehicles: [
      { id: "v1", companyId: "c1", registration: "KA1" },
      { id: "v2", companyId: "other", registration: "KA2" },
    ],
  } as ScopeOptions;

  it("groups vehicles by company, drops empty companies and lists the rest unnamed", () => {
    expect(scopeGroups(options).map((group) => [group.id, group.name])).toEqual(
      [
        ["c1", "Zuri"],
        ["", ""],
      ],
    );
  });

  it("counts scope the editor cannot see", () => {
    const form = {
      ...initialForm(),
      companyIds: ["c1", "archived"],
      vehicleIds: ["v1", "v9", "v8"],
    };
    expect(keptCounts(form, options)).toEqual({ companies: 1, vehicles: 2 });
  });
});

describe("validatePerson", () => {
  const ready = {
    ...initialForm(),
    firstName: "Amina",
    lastName: "Otieno",
    phoneNumber: "0712 345 678",
    email: "amina@example.co.ke",
    vehicleIds: ["v1"],
  };
  const ctx = {
    rolesLoaded: true,
    assignableCount: 1,
    permissions: ["a"],
    today: "2026-10-12",
    fullScope: true,
  };

  const cases: [string, Partial<typeof ready>, Partial<typeof ctx>, object][] =
    [
      ["a complete form", {}, {}, {}],
      [
        "no first name",
        { firstName: " " },
        {},
        { firstName: "Enter a first name." },
      ],
      [
        "no last name",
        { lastName: "" },
        {},
        { lastName: "Enter a last name." },
      ],
      [
        "an email without a domain",
        { email: "amina@example" },
        {},
        { email: "Enter the email that receives codes." },
      ],
      [
        "no role to assign once roles are loaded",
        {},
        { assignableCount: 0 },
        { role: "You cannot assign any available role." },
      ],
      [
        "no role check before roles load",
        {},
        { rolesLoaded: false, assignableCount: 0 },
        {},
      ],
      [
        "companies scope with none ticked",
        { scopeMode: "companies", companyIds: [] },
        {},
        { scope: "Pick at least one vehicle this person can see." },
      ],
      [
        "vehicles scope with none ticked by an editor who sees every company, so the person sees none yet",
        { vehicleIds: [] },
        {},
        {},
      ],
      [
        "vehicles scope with none ticked by an editor limited to some companies",
        { vehicleIds: [] },
        { fullScope: false },
        { scope: "Pick at least one vehicle this person can see." },
      ],
      [
        "vehicles scope with one ticked by an editor limited to some companies",
        {},
        { fullScope: false },
        {},
      ],
      [
        "all scope needs no ticks",
        { scopeMode: "all", vehicleIds: [] },
        {},
        {},
      ],
      [
        "no permissions",
        {},
        { permissions: [] },
        { permissions: "Tick at least one permission." },
      ],
    ];

  it.each(cases)("%s", (_name, formChange, ctxChange, expected) => {
    expect(
      validatePerson({ ...ready, ...formChange }, { ...ctx, ...ctxChange }),
    ).toEqual(expected);
  });

  it("flags a bad mobile number with the shared phone message", () => {
    const errors = validatePerson({ ...ready, phoneNumber: "12" }, ctx);
    expect(Object.keys(errors)).toEqual(["phoneNumber"]);
    expect(errors.phoneNumber).toBeTruthy();
  });
});

describe("personPayload", () => {
  const form = {
    ...initialForm(),
    firstName: " Amina ",
    lastName: " Otieno ",
    email: " amina@example.co.ke ",
    phoneNumber: "0712 345 678",
    scopeMode: "companies",
    companyIds: ["c1"],
    vehicleIds: ["v1"],
    approvalLimit: "5000",
  };

  it("trims, normalises the phone and keeps only the chosen scope list", () => {
    const body = personPayload(form, {
      selectedRole: "Manager",
      permissions: ["a"],
      needsLimit: true,
      version: 3,
    });
    expect(body).toEqual({
      firstName: "Amina",
      lastName: "Otieno",
      email: "amina@example.co.ke",
      phoneNumber: "0712345678",
      role: "Manager",
      scopeMode: "companies",
      companyIds: ["c1"],
      vehicleIds: [],
      permissions: ["a"],
      approvalLimit: 5000,
      backLimit: { mode: "days", count: 7, from: null },
      version: 3,
    });
  });

  it("drops the approval limit when no approval permission is ticked or it is empty", () => {
    const send = (needsLimit: boolean, approvalLimit: string) =>
      personPayload(
        { ...form, approvalLimit },
        { selectedRole: "Manager", permissions: [], needsLimit },
      ).approvalLimit;
    expect(send(false, "5000")).toBeNull();
    expect(send(true, "")).toBeNull();
  });
});

describe("the Sign in pane's invitation", () => {
  const formats = createFormatter();
  it("offers another invitation only to someone whose invitation is unused, and never a PIN reset to them", () => {
    expect(signInActions("invited", true)).toEqual({
      canInvite: true,
      canReset: false,
    });
    expect(signInActions("invite_expired", true).canInvite).toBe(true);
    expect(signInActions("not_signed_in", true).canInvite).toBe(false);
    expect(signInActions("active", true)).toEqual({
      canInvite: false,
      canReset: true,
    });
    expect(signInActions("invited", false).canInvite).toBe(false);
  });
  it("offers a PIN reset only to someone known to hold a PIN that is not already due for one", () => {
    expect(signInActions("active", true).canReset).toBe(true);
    expect(signInActions("locked", true).canReset).toBe(true);
    expect(signInActions("blocked", true)).toEqual({
      canInvite: false,
      canReset: false,
    });
    expect(signInActions("not_signed_in", true).canReset).toBe(false);
    expect(signInActions("pin_reset_due", true).canReset).toBe(false);
    expect(signInActions("invite_expired", true).canReset).toBe(false);
    expect(signInActions("active", false).canReset).toBe(false);
  });
  it("says when it went out and when it expires, or that it was not delivered", () => {
    const expiresAt = "2026-10-16T08:40:00Z";
    expect(
      invitationText(
        { state: "sent", sentAt: "2026-10-09T08:40:00Z", expiresAt },
        formats,
      ),
    ).toMatch(/^Invitation sent .+ · expires .+$/);
    expect(
      invitationText({ state: "failed", sentAt: null, expiresAt }, formats),
    ).toBe("Not delivered");
    expect(
      invitationText({ state: "expired", sentAt: null, expiresAt }, formats),
    ).toMatch(/^Invitation expired /);
    expect(
      invitationText({ state: "pending", sentAt: null, expiresAt }, formats),
    ).toMatch(/^Invitation being sent · expires /);
  });
});
