import { expect, expectTypeOf, it, vi } from "vitest";

import {
  awaitsCapture,
  isRecorded,
  loadWholeWeek,
  mergeWeekPages,
  parseRevenueAmount,
  remainingWeekPages,
  REVENUE_AMOUNT_ERROR,
  revenuePeriodLabel,
  REVENUE_STATUSES,
  STATUS_META,
  type RevenueStatus,
  type RevenueVehicle,
  type RevenueWeek,
  type StatusMeta,
  WeekChangedError,
} from "@xcode/shared/revenue";

it("parses positive revenue amounts up to twelve digits and two decimals", () => {
  expect(parseRevenueAmount("1")).toEqual({ ok: true, amount: 1 });
  expect(parseRevenueAmount("1500.50")).toEqual({
    ok: true,
    amount: 1500.5,
  });
  expect(parseRevenueAmount("1,500.50")).toEqual({
    ok: true,
    amount: 1500.5,
  });
  expect(parseRevenueAmount("999999999999.99")).toEqual({
    ok: true,
    amount: 999999999999.99,
  });
});

it("treats blank input as no amount", () => {
  expect(parseRevenueAmount("")).toEqual({ ok: true, amount: null });
  expect(parseRevenueAmount(" , ")).toEqual({ ok: true, amount: null });
});

it("rejects zero, negatives, excessive digits, and excess decimal places", () => {
  for (const value of ["0", "0.00", "-1", "1000000000000", "1.234", "1e3"]) {
    expect(parseRevenueAmount(value)).toEqual({
      ok: false,
      error: REVENUE_AMOUNT_ERROR,
    });
  }
});

it("rejects malformed grouping that would silently change the value", () => {
  for (const value of ["1,25", "12,34", "1,2345", "1,23,456", ",500"]) {
    expect(parseRevenueAmount(value)).toEqual({
      ok: false,
      error: REVENUE_AMOUNT_ERROR,
    });
  }
});

it("accepts properly grouped amounts", () => {
  expect(parseRevenueAmount("1,500")).toEqual({ ok: true, amount: 1500 });
  expect(parseRevenueAmount("1,000,000")).toEqual({
    ok: true,
    amount: 1000000,
  });
  expect(parseRevenueAmount("1,500.50")).toEqual({ ok: true, amount: 1500.5 });
  expect(parseRevenueAmount("49,000")).toEqual({ ok: true, amount: 49000 });
});

it("names each revenue period and passes an unknown one through", () => {
  expect(revenuePeriodLabel("today")).toBe("Today");
  expect(revenuePeriodLabel("week")).toBe("This week");
  expect(revenuePeriodLabel("month")).toBe("This month");
  expect(revenuePeriodLabel("toString" as never)).toBe("toString");
});

const vehicle = (id: string) => ({ id }) as RevenueVehicle;
const week = (ids: string[], more: Partial<RevenueWeek> = {}) =>
  ({
    weekStart: "2026-09-28",
    vehicles: ids.map(vehicle),
    ...more,
  }) as RevenueWeek;
const fleet = (from: number, count: number) =>
  Array.from({ length: count }, (_, index) => `v${from + index}`);

it("asks for the pages after a whole-grid week that stopped at its limit", () => {
  expect(remainingWeekPages(week(fleet(0, 3)))).toEqual([]);
  expect(
    remainingWeekPages(
      week(fleet(0, 500), { truncated: false, totalVehicles: 500 }),
    ),
  ).toEqual([]);
  expect(
    remainingWeekPages(
      week(fleet(0, 500), { truncated: true, totalVehicles: 501 }),
    ),
  ).toEqual([6]);
  expect(
    remainingWeekPages(
      week(fleet(0, 500), { truncated: true, totalVehicles: 730 }),
    ),
  ).toEqual([6, 7, 8]);
  // A limit between page boundaries starts at the page holding the last vehicle listed; the overlap is merged away.
  expect(
    remainingWeekPages(
      week(fleet(0, 450), { truncated: true, totalVehicles: 730 }),
    ),
  ).toEqual([5, 6, 7, 8]);
});

it("merges the pages in order, once per vehicle, and keeps the first page's figures", () => {
  const first = week(fleet(0, 500), {
    truncated: true,
    totalVehicles: 650,
    totalAmount: 99,
    companies: [],
  });
  const merged = mergeWeekPages(first, [
    week(["v499", ...fleet(500, 100)]),
    week(fleet(600, 50)),
  ]);
  expect(merged.vehicles.map((item) => item.id)).toEqual(fleet(0, 650));
  expect(merged.truncated).toBe(false);
  expect(merged.totalAmount).toBe(99);
  expect(mergeWeekPages(first, [])).toBe(first);
  // Without counts there is nothing to check the pages against.
  expect(
    mergeWeekPages(week(fleet(0, 2)), [week(fleet(2, 1))]).vehicles,
  ).toHaveLength(3);
});

it("refuses pages that do not add up to one fleet", () => {
  const first = week(fleet(0, 500), { truncated: true, totalVehicles: 650 });
  // A vehicle added between requests: the later page counts a different fleet.
  expect(() =>
    mergeWeekPages(first, [
      week(fleet(500, 100), { totalVehicles: 651 }),
      week(fleet(600, 50), { totalVehicles: 651 }),
    ]),
  ).toThrow(WeekChangedError);
  // A rename moved v499 onto page 6 and pushed v600 onto a page already fetched: same count, one vehicle missing.
  expect(() =>
    mergeWeekPages(first, [
      week(["v499", ...fleet(500, 99)], { totalVehicles: 650 }),
      week(fleet(601, 50), { totalVehicles: 650 }),
    ]),
  ).toThrow(WeekChangedError);
});

it("loads the week again from its first answer when the fleet changed between pages", async () => {
  const stale = week(fleet(0, 500), { truncated: true, totalVehicles: 650 });
  const fresh = week(fleet(0, 500), { truncated: true, totalVehicles: 651 });
  const seen: number[] = [];
  const loadPages = async (first: RevenueWeek) => {
    seen.push(first.totalVehicles!);
    return [
      week(fleet(500, 100), { totalVehicles: 651 }),
      week(fleet(600, 51), { totalVehicles: 651 }),
    ];
  };
  const reloadFirst = vi.fn(async () => fresh);

  const whole = await loadWholeWeek(stale, loadPages, reloadFirst);

  expect(reloadFirst).toHaveBeenCalledTimes(1);
  expect(seen).toEqual([650, 651]);
  expect(whole.vehicles.map((item) => item.id)).toEqual(fleet(0, 651));
});

it("stops after the last attempt and passes any other failure straight on", async () => {
  const first = week(fleet(0, 500), { truncated: true, totalVehicles: 650 });
  const moving = async () => [week(fleet(500, 100), { totalVehicles: 651 })];
  const reloadFirst = vi.fn(async () => first);
  await expect(loadWholeWeek(first, moving, reloadFirst, 2)).rejects.toThrow(
    WeekChangedError,
  );
  expect(reloadFirst).toHaveBeenCalledTimes(1);

  const failing = vi.fn(async () => {
    throw new Error("offline");
  });
  await expect(loadWholeWeek(first, failing, reloadFirst)).rejects.toThrow(
    "offline",
  );
  expect(failing).toHaveBeenCalledTimes(1);
});

it("describes every revenue status, so a new one fails typechecking until it is described", () => {
  expect(Object.keys(STATUS_META).sort()).toEqual([...REVENUE_STATUSES].sort());
  expectTypeOf(STATUS_META).toEqualTypeOf<Record<RevenueStatus, StatusMeta>>();
});

it.each([
  ["none", { inFleet: false, recorded: false, awaitsCapture: false }],
  ["future", { inFleet: true, recorded: false, awaitsCapture: false }],
  ["missing", { inFleet: true, recorded: false, awaitsCapture: true }],
  ["amount", { inFleet: true, recorded: true, awaitsCapture: false }],
  ["reason", { inFleet: true, recorded: true, awaitsCapture: false }],
] as const)("flags a %s day as %j", (status, flags) => {
  const { inFleet, recorded, awaitsCapture: awaits } = STATUS_META[status];
  expect({ inFleet, recorded, awaitsCapture: awaits }).toEqual(flags);
  expect(isRecorded({ status })).toBe(flags.recorded);
  expect(awaitsCapture({ status })).toBe(flags.awaitsCapture);
});

it("labels the days that have nothing else to show", () => {
  expect(STATUS_META.none).toMatchObject({
    label: "Not counted",
    tone: "muted",
  });
  expect(STATUS_META.future).toMatchObject({ label: "Not yet", tone: "muted" });
  expect(STATUS_META.missing).toMatchObject({
    label: "Missing",
    tone: "alert",
  });
});

it("treats a day with no cell as neither recorded nor waiting", () => {
  expect(isRecorded(undefined)).toBe(false);
  expect(awaitsCapture(undefined)).toBe(false);
});
