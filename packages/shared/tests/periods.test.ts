import { describe, expect, it } from "vitest";

import {
  PERIOD_PRESETS,
  canMoveNext,
  customPeriod,
  matchingPreset,
  periodDays,
  presetPeriod,
  shiftPeriod,
  type Period,
} from "../src/periods";

// A Friday. Weeks start on Monday (1) unless a test says otherwise.
const FRIDAY = "2026-10-09";

describe("PERIOD_PRESETS", () => {
  it("lists the presets in the order the picker shows them", () => {
    expect(PERIOD_PRESETS.map((preset) => preset.label)).toEqual([
      "Today",
      "Yesterday",
      "This week",
      "Last week",
      "Last 4 weeks",
      "This month",
      "Last month",
    ]);
  });
});

describe("presetPeriod", () => {
  it.each([
    ["today", "2026-10-09", "2026-10-09", "day"],
    ["yesterday", "2026-10-08", "2026-10-08", "day"],
    ["thisWeek", "2026-10-05", "2026-10-11", "week"],
    ["lastWeek", "2026-09-28", "2026-10-04", "week"],
    ["lastFourWeeks", "2026-09-07", "2026-10-04", "fourWeeks"],
    ["thisMonth", "2026-10-01", "2026-10-31", "month"],
    ["lastMonth", "2026-09-01", "2026-09-30", "month"],
  ] as const)("%s counts from the business date", (id, from, to, unit) => {
    expect(presetPeriod(id, FRIDAY, 1)).toEqual({ from, to, unit });
  });

  it("starts the week on the organization's first day", () => {
    expect(presetPeriod("thisWeek", FRIDAY, 0)).toEqual({
      from: "2026-10-04",
      to: "2026-10-10",
      unit: "week",
    });
    expect(presetPeriod("thisWeek", "2026-10-04", 0).from).toBe("2026-10-04");
    expect(presetPeriod("thisWeek", "2026-10-04", 1).from).toBe("2026-09-28");
  });

  it("crosses the year for last month and for yesterday", () => {
    expect(presetPeriod("lastMonth", "2026-01-15", 1)).toEqual({
      from: "2025-12-01",
      to: "2025-12-31",
      unit: "month",
    });
    expect(presetPeriod("yesterday", "2026-01-01", 1).from).toBe("2025-12-31");
    expect(presetPeriod("thisMonth", "2026-12-20", 1).to).toBe("2026-12-31");
  });

  it("ends February on the 28th or, in a leap year, the 29th", () => {
    expect(presetPeriod("lastMonth", "2026-03-10", 1).to).toBe("2026-02-28");
    expect(presetPeriod("lastMonth", "2024-03-10", 1).to).toBe("2024-02-29");
  });
});

describe("matchingPreset", () => {
  it("names the preset a period is", () => {
    for (const { id } of PERIOD_PRESETS)
      expect(matchingPreset(presetPeriod(id, FRIDAY, 1), FRIDAY, 1)).toBe(id);
  });

  it("names none for another period", () => {
    expect(
      matchingPreset({ from: "2026-10-01", to: "2026-10-09" }, FRIDAY, 1),
    ).toBeNull();
    expect(
      matchingPreset({ from: "2026-10-07", to: "2026-10-07" }, FRIDAY, 1),
    ).toBeNull();
  });

  it("depends on the first day of the week", () => {
    expect(
      matchingPreset({ from: "2026-10-04", to: "2026-10-10" }, FRIDAY, 0),
    ).toBe("thisWeek");
    expect(
      matchingPreset({ from: "2026-10-04", to: "2026-10-10" }, FRIDAY, 1),
    ).toBeNull();
  });
});

describe("shiftPeriod", () => {
  it("moves a day by a day", () => {
    const day: Period = { from: "2026-10-09", to: "2026-10-09", unit: "day" };
    expect(shiftPeriod(day, -1)).toEqual({
      from: "2026-10-08",
      to: "2026-10-08",
      unit: "day",
    });
    expect(shiftPeriod(day, 1).from).toBe("2026-10-10");
  });

  it("moves a week, and four weeks one week at a time", () => {
    expect(shiftPeriod(presetPeriod("thisWeek", FRIDAY, 1), -1)).toEqual({
      from: "2026-09-28",
      to: "2026-10-04",
      unit: "week",
    });
    expect(shiftPeriod(presetPeriod("lastFourWeeks", FRIDAY, 1), 1)).toEqual({
      from: "2026-09-14",
      to: "2026-10-11",
      unit: "fourWeeks",
    });
  });

  it("moves a calendar month to the whole month before or after, across years", () => {
    const january = presetPeriod("thisMonth", "2026-01-20", 1);
    expect(shiftPeriod(january, -1)).toEqual({
      from: "2025-12-01",
      to: "2025-12-31",
      unit: "month",
    });
    const december = presetPeriod("thisMonth", "2025-12-20", 1);
    expect(shiftPeriod(december, 1)).toEqual({
      from: "2026-01-01",
      to: "2026-01-31",
      unit: "month",
    });
    expect(shiftPeriod(presetPeriod("thisMonth", "2026-03-31", 1), -1).to).toBe(
      "2026-02-28",
    );
  });

  it("moves a custom span by its own length", () => {
    const span: Period = {
      from: "2026-10-01",
      to: "2026-10-03",
      unit: "custom",
    };
    expect(shiftPeriod(span, 1)).toEqual({
      from: "2026-10-04",
      to: "2026-10-06",
      unit: "custom",
    });
    expect(shiftPeriod(span, -1)).toEqual({
      from: "2026-09-28",
      to: "2026-09-30",
      unit: "custom",
    });
  });
});

describe("customPeriod", () => {
  it("puts the earlier day first", () => {
    expect(customPeriod("2026-10-09", "2026-10-01")).toEqual({
      from: "2026-10-01",
      to: "2026-10-09",
      unit: "custom",
    });
  });

  it("is a day when both days are the same", () => {
    expect(customPeriod("2026-10-09", "2026-10-09")).toEqual({
      from: "2026-10-09",
      to: "2026-10-09",
      unit: "day",
    });
  });
});

describe("canMoveNext", () => {
  it("allows next only while the next period starts on or before the business date", () => {
    expect(canMoveNext(presetPeriod("thisWeek", FRIDAY, 1), FRIDAY)).toBe(
      false,
    );
    expect(canMoveNext(presetPeriod("lastWeek", FRIDAY, 1), FRIDAY)).toBe(true);
    expect(canMoveNext(presetPeriod("today", FRIDAY, 1), FRIDAY)).toBe(false);
    expect(canMoveNext(presetPeriod("yesterday", FRIDAY, 1), FRIDAY)).toBe(
      true,
    );
    expect(canMoveNext(presetPeriod("thisMonth", FRIDAY, 1), FRIDAY)).toBe(
      false,
    );
    expect(canMoveNext(presetPeriod("lastMonth", FRIDAY, 1), FRIDAY)).toBe(
      true,
    );
  });

  it("allows next when the next week starts on the business date", () => {
    expect(
      canMoveNext(presetPeriod("lastWeek", "2026-10-05", 1), "2026-10-05"),
    ).toBe(true);
  });
});

describe("periodDays", () => {
  it("counts both days", () => {
    expect(periodDays({ from: "2026-10-09", to: "2026-10-09" })).toBe(1);
    expect(periodDays({ from: "2026-10-05", to: "2026-10-11" })).toBe(7);
    expect(periodDays({ from: "2026-02-27", to: "2026-03-02" })).toBe(4);
    expect(periodDays({ from: "2024-02-27", to: "2024-03-02" })).toBe(5);
    expect(periodDays({ from: "2025-12-31", to: "2026-01-01" })).toBe(2);
  });
});
