import { describe, expect, it } from "vitest";

import { createFormatter } from "@xcode/shared/format";
import type {
  RevenueCell,
  RevenueVehicle,
  RevenueWeek,
} from "@xcode/shared/revenue";

import {
  captureAt,
  captureStart,
  cellState,
  entryLabel,
  isReason,
  readEntry,
} from "../components/revenue/capture";

const formats = createFormatter();
const MON = "2026-09-28";
const TUE = "2026-09-29";
const WED = "2026-09-30";

const cell = (patch: Partial<RevenueCell>): RevenueCell =>
  ({
    date: MON,
    status: "missing",
    amount: null,
    reason: null,
    note: null,
    editedAfterCapture: false,
    ...patch,
  }) as RevenueCell;

const vehicle = (
  id: string,
  days: Partial<RevenueCell>[],
  earliestMissing: string | null = null,
): RevenueVehicle =>
  ({
    id,
    joinedOn: "2026-01-01",
    leftOn: null,
    earliestMissing,
    days: days.map(cell),
  }) as unknown as RevenueVehicle;

const week = (
  vehicles: RevenueVehicle[],
  over: Partial<RevenueWeek> = {},
): RevenueWeek =>
  ({ businessDate: WED, vehicles, firstGap: null, ...over }) as RevenueWeek;

describe("isReason", () => {
  it.each([
    ["Garage", true],
    ["Other", true],
    ["garage", false],
    ["", false],
    [null, false],
  ])("%s -> %s", (value, expected) => {
    expect(isReason(value)).toBe(expected);
  });
});

describe("captureAt", () => {
  it("opens the day as tapped and carries the vehicles already done", () => {
    expect(captureAt(vehicle("v1", []), WED)).toEqual({
      vehicleId: "v1",
      date: WED,
      done: [],
    });
    expect(captureAt(vehicle("v1", []), WED, ["v0"]).done).toEqual(["v0"]);
  });
});

describe("entryLabel", () => {
  it.each([
    [{ amount: 8500, reason: null, note: null }, "KES 8,500"],
    [{ amount: 2500, reason: "Garage", note: null }, "KES 2,500, Garage"],
    [{ amount: null, reason: "Garage", note: null }, "Garage"],
    [{ amount: null, reason: "Other", note: "Flat tyre" }, "Other: Flat tyre"],
    [{ amount: null, reason: null, note: null }, "No record"],
  ])("%j -> %s", (entry, expected) => {
    expect(entryLabel(formats, entry)).toBe(expected);
  });
});

describe("cellState", () => {
  it.each([
    [{ status: "missing" }, "Missing"],
    [{ status: "amount", amount: 8500 }, "KES 8,500"],
    [
      { status: "amount", amount: 1800, reason: "No Crew" },
      "KES 1,800, No Crew",
    ],
    [{ status: "reason", reason: "Arrest" }, "Arrest"],
    [
      { status: "amount", amount: 8500, editedAfterCapture: true },
      "KES 8,500, edited after capture",
    ],
  ] as const)("%j -> %s", (patch, expected) => {
    expect(cellState(formats, cell(patch))).toBe(expected);
  });
});

describe("readEntry", () => {
  const typed = { amount: "", reason: "" as const, threshold: 4000, formats };

  it("keeps an amount at or above the threshold without a reason, whatever was picked", () => {
    expect(readEntry({ ...typed, amount: "4,000", reason: "Garage" })).toEqual({
      amount: 4000,
      reason: null,
      note: null,
    });
    expect(readEntry({ ...typed, amount: "12,500.50" })).toEqual({
      amount: 12500.5,
      reason: null,
      note: null,
    });
  });

  it("refuses a malformed amount with the amount message", () => {
    expect(readEntry({ ...typed, amount: "12x" })).toMatch(/positive amount/);
  });

  it("asks for the reason when the amount is below the threshold", () => {
    expect(readEntry({ ...typed, amount: "3,999" })).toBe(
      "Choose the reason. Revenue is below KES 4,000.",
    );
    expect(readEntry({ ...typed, amount: "3999", reason: "Garage" })).toEqual({
      amount: 3999,
      reason: "Garage",
      note: null,
    });
  });

  it("asks for the revenue or a reason when nothing is entered, and takes a reason alone as a no revenue day", () => {
    expect(readEntry(typed)).toBe(
      "Enter the revenue, or choose the reason for no revenue.",
    );
    expect(readEntry({ ...typed, reason: "Other" })).toEqual({
      amount: null,
      reason: "Other",
      note: null,
    });
  });

  it("uses the fleet's own threshold", () => {
    expect(readEntry({ ...typed, amount: "4,500", threshold: 5000 })).toBe(
      "Choose the reason. Revenue is below KES 5,000.",
    );
  });
});

describe("captureStart", () => {
  it("opens the oldest missing day on the vehicle that misses it", () => {
    expect(
      captureStart(
        week([vehicle("v1", []), vehicle("v2", [])], {
          firstGap: { vehicleId: "v2", date: MON },
        }),
        null,
      ),
    ).toEqual({ vehicleId: "v2", date: MON });
  });

  it("opens today on the first vehicle with no record for it when nothing is missing", () => {
    expect(
      captureStart(
        week([
          vehicle("v1", [{ date: WED, status: "amount", amount: 9000 }]),
          vehicle("v2", [{ date: WED, status: "missing" }]),
        ]),
        null,
      ),
    ).toEqual({ vehicleId: "v2", date: WED });
  });

  it("never opens before the earliest day the person may change", () => {
    expect(
      captureStart(
        week([vehicle("v1", [{ date: TUE, status: "missing" }])], {
          firstGap: { vehicleId: "v1", date: MON },
        }),
        TUE,
      ),
    ).toEqual({ vehicleId: "v1", date: TUE });
  });

  it("has nowhere to open without a vehicle", () => {
    expect(captureStart(week([]), null)).toBeNull();
  });
});
