import { describe, expect, it } from "vitest";

import { PETTY_CASH_PERMISSIONS } from "@xcode/shared/pettyCash";
import {
  DASHBOARD_CARDS,
  EXPENSES_NAV,
  MIDDLE_NAV,
  NAV,
  NAV_SECTIONS,
  PERMISSION_KEYS,
  PRIMARY_NAV,
  RIGHTS,
  SETUP_NAV,
  canSee,
  permissionChecker,
  startsOnToday,
  type PermissionKey,
} from "@xcode/shared/permissions";

describe("PERMISSION_KEYS", () => {
  it("lists every released key once", () => {
    expect(PERMISSION_KEYS).toHaveLength(40);
    expect(new Set(PERMISSION_KEYS).size).toBe(PERMISSION_KEYS.length);
  });
});

describe("RIGHTS", () => {
  it("lists the 59 rights of v2.33 once, in catalogue order", () => {
    expect(RIGHTS).toHaveLength(59);
    expect(new Set(RIGHTS).size).toBe(RIGHTS.length);
    expect(RIGHTS[0]).toBe("dash.net");
    expect(RIGHTS.at(-1)).toBe("audit.view");
  });

  it("holds the 20 petty cash rights and the four of each of scheduled expenses and savings", () => {
    expect(RIGHTS.filter((key) => key.startsWith("pettycash."))).toHaveLength(
      20,
    );
    expect(RIGHTS.filter((key) => key.startsWith("scheduled."))).toEqual([
      "scheduled.view",
      "scheduled.add",
      "scheduled.edit",
      "scheduled.pause",
    ]);
    expect(RIGHTS.filter((key) => key.startsWith("savings."))).toEqual([
      "savings.view",
      "savings.add",
      "savings.edit",
      "savings.pause",
    ]);
    expect(RIGHTS).toContain("vehicles.target");
    expect(RIGHTS).toContain("people.sign_in");
  });
});

describe("canSee", () => {
  const holding = (...keys: PermissionKey[]) => permissionChecker(keys);

  it.each([
    ["no rule shows the item to everyone", {}, holding(), true],
    [
      "an empty list shows it to nobody",
      { any: [] },
      holding("revenue.view"),
      false,
    ],
    [
      "holding one listed key shows it",
      { any: ["vehicles.manage", "invest.view"] },
      holding("invest.view"),
      true,
    ],
    [
      "holding none of the listed keys hides it",
      { any: ["vehicles.manage", "invest.view"] },
      holding("revenue.view"),
      false,
    ],
  ] as const)("%s", (_name, rule, can, expected) => {
    expect(canSee(rule, can)).toBe(expected);
  });

  it("ignores permissions this build does not know", () => {
    const can = permissionChecker(["x.unknown", "revenue.view"]);
    expect(can("revenue.view")).toBe(true);
    expect(can("revenue.capture")).toBe(false);
  });

  it("rejects a key that is not in the catalog at compile time", () => {
    // @ts-expect-error revenue.veiw is not a permission
    canSee({ any: ["revenue.veiw"] }, () => true);
    // @ts-expect-error nope is not a permission
    permissionChecker([])("nope");
    expect(true).toBe(true);
  });
});

describe("NAV", () => {
  it("names only rights or released keys", () => {
    const keys: string[] = Object.values(NAV).flatMap((item) =>
      "any" in item ? [...item.any] : [],
    );
    expect(keys.length).toBeGreaterThan(0);
    const catalog: readonly string[] = [...PERMISSION_KEYS, ...RIGHTS];
    for (const key of keys) expect(catalog).toContain(key);
  });

  it("orders the menu as XCODE Web does", () => {
    expect(PRIMARY_NAV.map((id) => NAV[id].label)).toEqual([
      "Dashboard",
      "Revenue",
    ]);
    expect(EXPENSES_NAV.map((id) => NAV[id].label)).toEqual([
      "Central expenses",
      "Petty cash",
      "Scheduled expenses and savings",
    ]);
    expect(MIDDLE_NAV.map((id) => NAV[id].label)).toEqual([
      "Savings",
      "Reports",
    ]);
    expect(SETUP_NAV.map((id) => NAV[id].label)).toEqual([
      "PSV companies",
      "Vehicles",
      "Expense categories",
      "People and access",
      "Change log",
      "Organization settings",
    ]);
  });

  it("lays the sections out as items, the Expenses group, Savings and Reports, then the Setup group", () => {
    expect(
      NAV_SECTIONS.map((section) =>
        section.kind === "group"
          ? [section.id, section.label, section.items]
          : [section.kind, section.items],
      ),
    ).toEqual([
      ["items", PRIMARY_NAV],
      ["expenses", "Expenses", EXPENSES_NAV],
      ["items", MIDDLE_NAV],
      ["setup", "Setup", SETUP_NAV],
    ]);
  });

  it("places every menu entry in exactly one section", () => {
    const placed = NAV_SECTIONS.flatMap((section) => [...section.items]);
    expect([...placed].sort()).toEqual(Object.keys(NAV).sort());
  });

  it("opens Central expenses for expenses.view and Reports for reports.view", () => {
    expect(NAV.centralexpenses.any).toEqual(["expenses.view"]);
    expect(NAV.reports.any).toEqual(["reports.view"]);
    expect(
      canSee(NAV.centralexpenses, permissionChecker(["expenses.capture"])),
    ).toBe(false);
    expect(
      canSee(NAV.centralexpenses, permissionChecker(["expenses.view"])),
    ).toBe(true);
    expect(canSee(NAV.reports, permissionChecker(["reports.export"]))).toBe(
      false,
    );
    expect(canSee(NAV.reports, permissionChecker(["reports.view"]))).toBe(true);
  });

  it("opens Petty cash on its view right, Vehicles on its view right or for investment viewers", () => {
    expect(NAV.pettycash.any).toEqual(PETTY_CASH_PERMISSIONS);
    expect(canSee(NAV.pettycash, permissionChecker(["pettycash.view"]))).toBe(
      true,
    );
    expect(canSee(NAV.vehicles, permissionChecker(["vehicles.view"]))).toBe(
      true,
    );
    expect(canSee(NAV.vehicles, permissionChecker(["invest.view"]))).toBe(true);
    expect(canSee(NAV.expenses, permissionChecker(["catalog.view"]))).toBe(
      true,
    );
    expect(canSee(NAV.expenses, permissionChecker(["revenue.view"]))).toBe(
      false,
    );
  });

  it("keeps Scheduled expenses and Savings apart, each on its own view right", () => {
    expect(canSee(NAV.recurring, permissionChecker(["scheduled.view"]))).toBe(
      true,
    );
    expect(canSee(NAV.recurring, permissionChecker(["savings.view"]))).toBe(
      false,
    );
    expect(canSee(NAV.savings, permissionChecker(["savings.view"]))).toBe(true);
    expect(canSee(NAV.savings, permissionChecker(["scheduled.view"]))).toBe(
      false,
    );
  });

  it("keeps the released keys opening their menu entries for a v2.11 phone", () => {
    expect(canSee(NAV.vehicles, permissionChecker(["vehicles.manage"]))).toBe(
      true,
    );
    expect(canSee(NAV.companies, permissionChecker(["companies.manage"]))).toBe(
      true,
    );
    expect(canSee(NAV.recurring, permissionChecker(["commitments.view"]))).toBe(
      true,
    );
    expect(canSee(NAV.pettycash, permissionChecker(["pettycash.spend"]))).toBe(
      true,
    );
  });

  it("shows the dashboard to everyone", () => {
    expect(canSee(NAV.dashboard, permissionChecker([]))).toBe(true);
  });
});

describe("DASHBOARD_CARDS", () => {
  it("keeps the order and titles both apps show", () => {
    expect(
      DASHBOARD_CARDS.map((card) => [card.permission, card.title]),
    ).toEqual([
      ["dash.capture", "Today's revenue"],
      ["dash.float", "My petty cash float"],
      ["dash.revenue", "Revenue"],
      ["dash.net", "Net contribution"],
      ["dash.costs", "Money out"],
      ["dash.gaps", "Missing revenue days"],
      ["dash.pettycash", "Petty cash to approve"],
      ["dash.commitments", "Yearly items due"],
      ["dash.investment", "Money invested"],
      ["dash.edits", "Edited after capture"],
    ]);
  });

  it("covers every dashboard permission in the catalog", () => {
    const dash = PERMISSION_KEYS.filter((key) => key.startsWith("dash."));
    expect(DASHBOARD_CARDS.map((card) => card.permission)).toEqual(dash);
  });
});

describe("startsOnToday", () => {
  it.each([
    [["dash.capture"], true],
    [["dash.float"], true],
    [["dash.revenue", "dash.gaps"], false],
    [[], false],
  ] as const)("%j starts on today: %s", (held, expected) => {
    expect(startsOnToday(permissionChecker(held))).toBe(expected);
  });
});
