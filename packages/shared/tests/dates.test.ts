import { expect, it, vi } from "vitest";

import {
  calendarDate,
  compactDateRange,
  dayOfMonth,
  daysBetween,
  firstOfMonth,
  formatTimestamp,
  isDate,
  mediumDateLabel,
  shiftDate,
  shortMonthName,
  startOfWeek,
  weekDays,
  WEEKDAYS,
  weekdayName,
  weekdayIndex,
  weekdayShortName,
} from "@xcode/shared/dates";

it("works with date-only values in UTC across leap days", () => {
  expect(isDate("2024-02-29")).toBe(true);
  expect(isDate("2024-02-30")).toBe(false);
  expect(isDate("2024-2-09")).toBe(false);
  expect(isDate(null)).toBe(false);
  expect(shiftDate("2024-02-28", 1)).toBe("2024-02-29");
  expect(shiftDate("2024-02-29", 1)).toBe("2024-03-01");
  expect(shiftDate("2024-03-01", -1)).toBe("2024-02-29");
  expect(daysBetween("2024-02-28", "2024-03-01")).toBe(2);
});

it("rejects impossible calendar dates", () => {
  expect(isDate("2024-02-30")).toBe(false);
  expect(isDate("2023-02-29")).toBe(false);
  expect(isDate("2024-04-31")).toBe(false);
  expect(isDate("2024-13-01")).toBe(false);
  expect(isDate("2024-00-01")).toBe(false);
  expect(isDate("2024-01-32")).toBe(false);
  expect(isDate("2024-06-31")).toBe(false);
});

it("guards shiftDate and formatTimestamp against invalid input", () => {
  expect(shiftDate("not-a-date", 1)).toBe("not-a-date");
  expect(shiftDate("2024-02-30", 1)).toBe("2024-02-30");
  const settings = {
    locale: "en-GB",
    datePattern: "medium" as const,
    hour12: false,
  };
  expect(formatTimestamp("garbage", settings)).toBe("garbage");
});

it("gets calendar components and week starts from UTC dates", () => {
  expect(calendarDate("2026-09-27").toISOString()).toBe(
    "2026-09-27T00:00:00.000Z",
  );
  expect(weekdayIndex("2026-09-27")).toBe(0);
  expect(WEEKDAYS.map(({ value }) => value)).toEqual([0, 1, 2, 3, 4, 5, 6]);
  expect(weekdayShortName("2026-09-27")).toBe("Sun");
  expect(weekdayName(0)).toBe("Sunday");
  expect(shortMonthName(8)).toBe("Sep");
  expect(mediumDateLabel(27, 8, 2026)).toBe("27 Sep 2026");
  expect(dayOfMonth("2026-09-27")).toBe(27);
  expect(startOfWeek("2026-09-30", 1)).toBe("2026-09-28");
  expect(startOfWeek("2026-09-30", 0)).toBe("2026-09-27");
  expect(firstOfMonth("2026-09-30")).toBe("2026-09-01");
});

it("compacts a date range without hiding a month or year boundary", () => {
  const labels = new Map([
    ["2026-09-21", "21 Sep 2026"],
    ["2026-09-27", "27 Sep 2026"],
    ["2026-09-28", "28 Sep 2026"],
    ["2026-10-04", "4 Oct 2026"],
    ["2025-12-29", "29 Dec 2025"],
    ["2026-01-04", "4 Jan 2026"],
  ]);
  const label = (value: string) => {
    const result = labels.get(value);
    if (!result) throw new Error(`Missing test label for ${value}`);
    return result;
  };

  expect(compactDateRange("2026-09-21", "2026-09-27", label)).toBe(
    "21 to 27 Sep 2026",
  );
  expect(compactDateRange("2026-09-28", "2026-10-04", label)).toBe(
    "28 Sep to 4 Oct 2026",
  );
  expect(compactDateRange("2025-12-29", "2026-01-04", label)).toBe(
    "29 Dec 2025 to 4 Jan 2026",
  );
});

it("does its date arithmetic without Date objects and agrees with Date", () => {
  const dateConstructed = vi.spyOn(globalThis, "Date");
  let day = "2000-01-01";
  for (let i = 0; i < 5000; i++) {
    day = shiftDate(day, 1);
    startOfWeek(day, 1);
    weekdayShortName(day);
    dayOfMonth(day);
    daysBetween("2000-01-01", day);
    isDate(day);
  }
  expect(dateConstructed).not.toHaveBeenCalled();
  dateConstructed.mockRestore();

  for (let offset = -800; offset < 800; offset += 3) {
    const reference = new Date(Date.UTC(2024, 1, 29 + offset));
    const iso = reference.toISOString().slice(0, 10);
    expect(shiftDate("2024-02-29", offset)).toBe(iso);
    expect(weekdayIndex(iso)).toBe(reference.getUTCDay());
    expect(dayOfMonth(iso)).toBe(reference.getUTCDate());
    expect(daysBetween("2024-02-29", iso)).toBe(offset);
    expect(isDate(iso)).toBe(true);
  }
  expect(shiftDate("0001-01-01", 365)).toBe("0002-01-01");
  expect(shiftDate("1999-12-31", 1)).toBe("2000-01-01");
  expect(shiftDate("2100-02-28", 1)).toBe("2100-03-01");
  expect(shiftDate("2000-02-28", 1)).toBe("2000-02-29");
});

it("keeps the Date-compatible answers for impossible or malformed dates", () => {
  expect(dayOfMonth("2024-02-30")).toBe(1);
  expect(weekdayIndex("2024-02-30")).toBe(
    calendarDate("2024-02-30").getUTCDay(),
  );
  expect(dayOfMonth("2024-13-01")).toBeNaN();
  expect(weekdayIndex("garbage")).toBeNaN();
  expect(daysBetween("garbage", "2024-01-01")).toBeNaN();
  expect(startOfWeek("garbage", 1)).toBe("garbage");
});

it("describes a week as primitives for screens to precompute once", () => {
  const week = weekDays("2026-09-28");
  expect(week.map(({ date }) => date)).toEqual([
    "2026-09-28",
    "2026-09-29",
    "2026-09-30",
    "2026-10-01",
    "2026-10-02",
    "2026-10-03",
    "2026-10-04",
  ]);
  expect(week.map(({ shortName }) => shortName)).toEqual([
    "Mon",
    "Tue",
    "Wed",
    "Thu",
    "Fri",
    "Sat",
    "Sun",
  ]);
  expect(week.map(({ weekday }) => weekday)).toEqual([1, 2, 3, 4, 5, 6, 0]);
  expect(week.map(({ dayOfMonth: day }) => day)).toEqual([
    28, 29, 30, 1, 2, 3, 4,
  ]);
  for (const day of week) {
    expect(day.weekday).toBe(weekdayIndex(day.date));
    expect(day.shortName).toBe(weekdayShortName(day.date));
    expect(day.dayOfMonth).toBe(dayOfMonth(day.date));
  }
  expect(weekDays("2026-09-28", 3)).toHaveLength(3);
  expect(weekDays("2026-09-28")).not.toBe(weekDays("2026-09-28"));
  expect(weekDays("nope")).toEqual([]);
});
