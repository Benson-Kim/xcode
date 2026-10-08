import { describe, expect, it } from "vitest";

import { createFormatter } from "@xcode/shared/format";
import type { RevenueCell, RevenueVehicle } from "@xcode/shared/revenue";

import {
  captureAt,
  cellState,
  entryLabel,
  isReason,
  openAt,
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
  days: Partial<RevenueCell>[],
  earliestMissing: string | null,
): RevenueVehicle =>
  ({
    id: "v1",
    joinedOn: "2026-01-01",
    leftOn: null,
    earliestMissing,
    days: days.map(cell),
  }) as unknown as RevenueVehicle;

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
  const v = vehicle([], null);

  it("says nothing when the day opens as tapped", () => {
    expect(captureAt(formats, v, WED, { date: WED, earlier: null })).toEqual({
      vehicleId: "v1",
      date: WED,
      target: WED,
      info: "",
      done: [],
    });
  });

  it("names the earlier gap that opens first and keeps the done list", () => {
    expect(
      captureAt(formats, v, WED, { date: MON, earlier: MON }, ["v0"]),
    ).toEqual({
      vehicleId: "v1",
      date: MON,
      target: WED,
      info: "Fill Mon 28 Sep 2026 first.",
      done: ["v0"],
    });
  });
});

describe("openAt", () => {
  const gaps = vehicle(
    [
      { date: MON, status: "missing" },
      { date: TUE, status: "missing" },
      { date: WED, status: "missing" },
    ],
    MON,
  );

  it("sends a tap on a later gap to the earliest one", () => {
    expect(openAt(formats, gaps, WED, WED)).toEqual({
      vehicleId: "v1",
      date: MON,
      target: WED,
      info: "Fill Mon 28 Sep 2026 first.",
      done: [],
    });
  });

  it("opens the earliest gap as tapped", () => {
    expect(openAt(formats, gaps, MON, WED).info).toBe("");
    expect(openAt(formats, gaps, MON, WED).date).toBe(MON);
  });

  it("opens a recorded day as tapped, whatever is missing before it", () => {
    const recorded = vehicle(
      [
        { date: MON, status: "missing" },
        { date: TUE, status: "amount", amount: 900 },
      ],
      MON,
    );
    expect(openAt(formats, recorded, TUE, WED)).toMatchObject({
      date: TUE,
      target: TUE,
      info: "",
    });
  });

  it("carries the vehicles already done", () => {
    expect(openAt(formats, gaps, MON, WED, ["v9"]).done).toEqual(["v9"]);
  });
});

describe("entryLabel", () => {
  it.each([
    [{ amount: 850, reason: null, note: null }, "KES 850"],
    [{ amount: 850, reason: null, note: "ignored" }, "KES 850"],
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
    [{ status: "amount", amount: 850 }, "KES 850"],
    [{ status: "reason", reason: "Arrest" }, "Arrest"],
    [
      { status: "amount", amount: 850, editedAfterCapture: true },
      "KES 850, edited after capture",
    ],
    [
      { status: "missing", editedAfterCapture: true },
      "Missing, edited after capture",
    ],
  ] as const)("%j -> %s", (patch, expected) => {
    expect(cellState(formats, cell(patch))).toBe(expected);
  });
});

describe("readEntry", () => {
  const typed = { amount: "", reason: "" as const, note: "" };

  it("reads an amount whatever the reason", () => {
    expect(
      readEntry({ ...typed, amount: "1,200", canChooseReason: false }),
    ).toEqual({ amount: 1200, reason: null, note: null });
  });

  it("refuses a malformed amount with the amount message", () => {
    expect(
      readEntry({ ...typed, amount: "12x", canChooseReason: true }),
    ).toMatch(/positive amount/);
  });

  it("asks for revenue when the person cannot pick a reason", () => {
    expect(readEntry({ ...typed, canChooseReason: false })).toBe(
      "Enter the revenue.",
    );
  });

  it("asks for a reason when nothing is entered", () => {
    expect(readEntry({ ...typed, canChooseReason: true })).toBe(
      "Enter the revenue or pick a reason.",
    );
  });

  it("wants a note for Other and trims it", () => {
    const other = { ...typed, reason: "Other" as const, canChooseReason: true };
    expect(readEntry(other)).toBe("Say what happened.");
    expect(readEntry({ ...other, note: "  Flat tyre " })).toEqual({
      amount: null,
      reason: "Other",
      note: "Flat tyre",
    });
  });

  it("drops the note for any other reason", () => {
    expect(
      readEntry({
        amount: "",
        reason: "Garage",
        note: "left over",
        canChooseReason: true,
      }),
    ).toEqual({ amount: null, reason: "Garage", note: null });
  });
});
