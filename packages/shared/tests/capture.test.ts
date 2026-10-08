import { describe, expect, it } from "vitest";

import {
  canOpen,
  earliestNeeded,
  earliestNeededDay,
  entryText,
  needsRecord,
  nextToCapture,
  openingFor,
} from "@xcode/shared/capture";
import { createFormatter } from "@xcode/shared/format";
import type {
  RevenueCell,
  RevenueStatus,
  RevenueVehicle,
  RevenueWeek,
} from "@xcode/shared/revenue";

const DAYS = [
  "2026-09-28",
  "2026-09-29",
  "2026-09-30",
  "2026-10-01",
  "2026-10-02",
  "2026-10-03",
  "2026-10-04",
];
const BUSINESS_DATE = "2026-09-30";
const TODAY = { businessDate: BUSINESS_DATE };

const cell = (
  date: string,
  status: RevenueStatus,
  more: Partial<RevenueCell> = {},
): RevenueCell => ({
  date,
  status,
  expected: 1000,
  amount: status === "amount" ? 900 : null,
  reason: status === "reason" ? "Garage" : null,
  note: null,
  canEdit: false,
  editedAfterCapture: false,
  ...more,
});

const grid = (recorded: Record<string, RevenueStatus> = {}) =>
  DAYS.map((date) =>
    cell(
      date,
      recorded[date] ?? (date <= BUSINESS_DATE ? "missing" : "future"),
    ),
  );

const vehicle = (
  id: string,
  more: Partial<RevenueVehicle> = {},
): RevenueVehicle => ({
  id,
  companyId: "c1",
  companyName: "Kisumu Cabs",
  registration: `KDA ${id}`,
  joinedOn: "2026-01-01",
  leftOn: null,
  earliestMissing: "2026-09-28",
  days: grid(),
  totalAmount: 0,
  totalExpected: 0,
  percent: null,
  ...more,
});

const week = (
  vehicles: RevenueVehicle[],
  more: Partial<RevenueWeek> = {},
): RevenueWeek => ({
  weekStart: "2026-09-28",
  weekThrough: "2026-10-04",
  currentWeekStart: "2026-09-28",
  businessDate: BUSINESS_DATE,
  companies: [],
  vehicles,
  totalAmount: 0,
  totalExpected: 0,
  percent: null,
  ...more,
});

const handling =
  (...keys: string[]) =>
  (id: string, date: string) =>
    keys.includes(`${id}/${date}`);

// A vehicle looked at from another week: no cells for the day in question.
const elsewhere = (more: Partial<RevenueVehicle> = {}) =>
  vehicle("a", { days: [], ...more });

describe("needsRecord", () => {
  it.each<[string, RevenueStatus, boolean]>([
    ["a missing day", "missing", true],
    ["a recorded amount", "amount", false],
    ["a recorded reason", "reason", false],
    ["a day outside the fleet", "none", false],
    ["a future day", "future", false],
  ])("answers from the cell for %s", (_, status, expected) => {
    expect(
      needsRecord(
        vehicle("a", { days: [cell("2026-09-29", status)] }),
        "2026-09-29",
      ),
    ).toBe(expected);
  });

  it("is false for a day the caller has handled, even when the cell says missing", () => {
    expect(
      needsRecord(vehicle("a"), "2026-09-29", handling("a/2026-09-29")),
    ).toBe(false);
    expect(
      needsRecord(vehicle("a"), "2026-09-29", handling("b/2026-09-29")),
    ).toBe(true);
  });

  it("works out a day with no cell from the earliest gap", () => {
    const gap = elsewhere({ earliestMissing: "2026-09-24" });
    expect(needsRecord(gap, "2026-09-25")).toBe(true);
    expect(needsRecord(gap, "2026-09-24")).toBe(true);
    expect(needsRecord(gap, "2026-09-23")).toBe(false);
    expect(
      needsRecord(elsewhere({ earliestMissing: null }), "2026-09-25"),
    ).toBe(false);
  });

  it("does not count days after the vehicle left or before it joined", () => {
    expect(
      needsRecord(
        elsewhere({ earliestMissing: "2026-09-24", leftOn: "2026-09-25" }),
        "2026-09-26",
      ),
    ).toBe(false);
    expect(
      needsRecord(
        elsewhere({ earliestMissing: "2026-09-24", leftOn: "2026-09-25" }),
        "2026-09-24",
      ),
    ).toBe(true);
    expect(
      needsRecord(
        elsewhere({ earliestMissing: "2026-09-24", joinedOn: "2026-09-26" }),
        "2026-09-25",
      ),
    ).toBe(false);
  });
});

describe("earliestNeeded", () => {
  it("starts at the earliest gap and skips what the caller has handled", () => {
    expect(earliestNeeded(vehicle("a"), TODAY)).toBe("2026-09-28");
    expect(earliestNeeded(vehicle("a"), TODAY, handling("a/2026-09-28"))).toBe(
      "2026-09-29",
    );
    expect(
      earliestNeeded(
        elsewhere({ earliestMissing: "2026-09-24" }),
        TODAY,
        handling("a/2026-09-24", "a/2026-09-25", "a/2026-09-26"),
      ),
    ).toBe("2026-09-27");
  });

  it("is today when nothing earlier is missing and today is still open", () => {
    const only = vehicle("a", {
      earliestMissing: null,
      days: grid({ "2026-09-28": "amount", "2026-09-29": "amount" }),
    });
    expect(earliestNeeded(only, TODAY)).toBe("2026-09-30");
    expect(earliestNeeded(only, TODAY, handling("a/2026-09-30"))).toBeNull();
  });

  it("is null when today is recorded", () => {
    const done = vehicle("a", {
      earliestMissing: null,
      days: grid({
        "2026-09-28": "amount",
        "2026-09-29": "amount",
        "2026-09-30": "reason",
      }),
    });
    expect(earliestNeeded(done, TODAY)).toBeNull();
  });

  it("is null once every day up to today is handled", () => {
    expect(
      earliestNeeded(
        vehicle("a"),
        TODAY,
        handling("a/2026-09-28", "a/2026-09-29", "a/2026-09-30"),
      ),
    ).toBeNull();
  });

  it("does not invent today for a week that does not hold it", () => {
    const old = vehicle("a", {
      earliestMissing: null,
      days: ["2026-09-21", "2026-09-22", "2026-09-23"].map((date) =>
        cell(date, "missing"),
      ),
    });
    expect(earliestNeeded(old, TODAY)).toBeNull();
  });

  it("ignores a gap that starts after the business date", () => {
    expect(
      earliestNeeded(elsewhere({ earliestMissing: "2026-10-02" }), TODAY),
    ).toBeNull();
  });
});

describe("earliestNeededDay", () => {
  it("is the earliest day any vehicle still needs", () => {
    const later = vehicle("b", { earliestMissing: "2026-09-29" });
    const sooner = vehicle("c", { earliestMissing: "2026-09-28" });
    expect(earliestNeededDay(week([later, sooner]))).toBe("2026-09-28");
    expect(
      earliestNeededDay(week([later, sooner]), handling("c/2026-09-28")),
    ).toBe("2026-09-29");
  });

  it("is null for an empty grid or a grid with nothing to capture", () => {
    expect(earliestNeededDay(week([]))).toBeNull();
    const done = vehicle("a", {
      earliestMissing: null,
      days: grid({
        "2026-09-28": "amount",
        "2026-09-29": "amount",
        "2026-09-30": "amount",
      }),
    });
    expect(earliestNeededDay(week([done]))).toBeNull();
  });
});

describe("canOpen", () => {
  it("lets anyone who captures open a missing day, whatever the API says about that day", () => {
    expect(
      canOpen(cell("2026-09-29", "missing", { canEdit: false }), true),
    ).toBe(true);
    expect(
      canOpen(cell("2026-09-29", "missing", { canEdit: true }), false),
    ).toBe(false);
  });

  it("leaves a recorded day to what the API allows", () => {
    expect(
      canOpen(cell("2026-09-29", "amount", { canEdit: true }), false),
    ).toBe(true);
    expect(
      canOpen(cell("2026-09-29", "amount", { canEdit: false }), true),
    ).toBe(false);
    expect(
      canOpen(cell("2026-09-29", "reason", { canEdit: true }), false),
    ).toBe(true);
  });

  it("never opens a future day or a day outside the fleet", () => {
    expect(canOpen(cell("2026-10-01", "future"), true)).toBe(false);
    expect(canOpen(cell("2026-09-28", "none"), true)).toBe(false);
  });
});

describe("openingFor", () => {
  it("opens the earlier gap when a later missing day is tapped", () => {
    expect(openingFor(vehicle("a"), "2026-09-30", TODAY)).toEqual({
      date: "2026-09-28",
      earlier: "2026-09-28",
    });
  });

  it("opens the tapped day when it is the earliest gap", () => {
    expect(openingFor(vehicle("a"), "2026-09-28", TODAY)).toEqual({
      date: "2026-09-28",
      earlier: null,
    });
  });

  it("skips an earlier gap the caller has handled", () => {
    expect(
      openingFor(vehicle("a"), "2026-09-30", TODAY, handling("a/2026-09-28")),
    ).toEqual({
      date: "2026-09-29",
      earlier: "2026-09-29",
    });
    expect(
      openingFor(vehicle("a"), "2026-09-29", TODAY, handling("a/2026-09-28")),
    ).toEqual({
      date: "2026-09-29",
      earlier: null,
    });
  });

  it("opens a recorded day as itself", () => {
    const recorded = vehicle("a", { days: grid({ "2026-09-29": "amount" }) });
    expect(openingFor(recorded, "2026-09-29", TODAY)).toEqual({
      date: "2026-09-29",
      earlier: null,
    });
  });

  it("finds the earlier gap of a day in another week", () => {
    const away = elsewhere({ earliestMissing: "2026-09-24" });
    expect(openingFor(away, "2026-09-26", TODAY)).toEqual({
      date: "2026-09-24",
      earlier: "2026-09-24",
    });
  });
});

describe("nextToCapture", () => {
  const fleet = () => [vehicle("a"), vehicle("b"), vehicle("c")];

  it("goes on from the vehicle it was given, then wraps round", () => {
    expect(
      nextToCapture(
        week(fleet()),
        "b",
        "2026-09-28",
        handling("b/2026-09-28"),
        true,
      )?.vehicle.id,
    ).toBe("c");
    expect(
      nextToCapture(
        week(fleet()),
        "c",
        "2026-09-28",
        handling("c/2026-09-28", "a/2026-09-28"),
        true,
      )?.vehicle.id,
    ).toBe("b");
  });

  it("starts at the vehicle itself when it still needs the day, and at the first one for an unknown id", () => {
    expect(
      nextToCapture(week(fleet()), "b", "2026-09-28", () => false, true)
        ?.vehicle.id,
    ).toBe("b");
    expect(
      nextToCapture(week(fleet()), "nobody", "2026-09-28", () => false, true)
        ?.vehicle.id,
    ).toBe("a");
  });

  it("skips handled days and vehicles that hold a record for the day", () => {
    const recorded = [
      vehicle("a", { days: grid({ "2026-09-29": "amount" }) }),
      vehicle("b", { days: grid({ "2026-09-29": "reason" }) }),
      vehicle("c"),
    ];
    expect(
      nextToCapture(week(recorded), "a", "2026-09-29", () => false, true)
        ?.vehicle.id,
    ).toBe("c");
  });

  it("offers nothing to someone who may not capture, or when nothing is left", () => {
    expect(
      nextToCapture(week(fleet()), "a", "2026-09-28", () => false, false),
    ).toBeNull();
    expect(
      nextToCapture(
        week(fleet()),
        "a",
        "2026-09-28",
        handling("a/2026-09-28", "b/2026-09-28", "c/2026-09-28"),
        true,
      ),
    ).toBeNull();
  });

  it("sends a vehicle with an earlier gap to that gap", () => {
    const behind = vehicle("b", { earliestMissing: "2026-09-26" });
    const next = nextToCapture(
      week([vehicle("a"), behind]),
      "a",
      "2026-09-30",
      handling("a/2026-09-30"),
      true,
    );
    expect(next?.vehicle.id).toBe("b");
    expect(next?.opening).toEqual({
      date: "2026-09-26",
      earlier: "2026-09-26",
    });
  });
});

describe("entryText", () => {
  const formats = createFormatter();

  it("says the amount, else the reason, else nothing", () => {
    expect(entryText(formats, { amount: 1250, reason: null })).toBe(
      "KES 1,250",
    );
    expect(entryText(formats, { amount: null, reason: "Garage" })).toBe(
      "Garage",
    );
    expect(entryText(formats, { amount: null, reason: null })).toBeNull();
  });
});
