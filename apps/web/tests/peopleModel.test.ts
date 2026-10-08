import { describe, expect, it } from "vitest";

import {
  assignableRoles,
  initialForm,
  keptCounts,
  personPayload,
  scopeGroups,
  scopeLabel,
  signInState,
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

  it("says all companies", () => {
    expect(scopeLabel(person({ scopeMode: "all" }))).toBe("All companies");
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

describe("signInState", () => {
  it("is none without access, waiting without a PIN, otherwise active", () => {
    expect(signInState(person({ active: false }))).toBe("none");
    expect(signInState(person({ hasPin: false }))).toBe("waiting");
    expect(signInState(person())).toBe("active");
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
  const ctx = { rolesLoaded: true, assignableCount: 1, permissions: ["a"] };

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
        { email: "Enter an email address like name@company.co.ke" },
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
        { scope: "Tick at least one company." },
      ],
      [
        "vehicles scope with none ticked",
        { vehicleIds: [] },
        {},
        { scope: "Tick at least one vehicle." },
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
