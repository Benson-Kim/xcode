import { expect, it } from "vitest";

import type { RevenueCell, RevenueWeek } from "@xcode/shared/revenue";

import {
  captureDayFor,
  dayRows,
  weekStartFor,
} from "../components/revenue/fleetDay";

const cell = (date: string, status: RevenueCell["status"]): RevenueCell => ({
  date,
  status,
  expected: 1000,
  amount: status === "amount" ? 900 : null,
  reason: null,
  note: null,
  canEdit: status === "missing",
  editedAfterCapture: false,
  version: status === "amount" ? 1 : null,
});

const weekOf = (
  weekStart: string,
  businessDate: string,
  statuses: RevenueCell["status"][],
) =>
  ({
    weekStart,
    businessDate,
    vehicles: [
      {
        days: statuses.map((status, index) =>
          cell(
            `${weekStart.slice(0, 8)}${String(Number(weekStart.slice(8)) + index).padStart(2, "0")}`,
            status,
          ),
        ),
      },
    ],
  }) as unknown as RevenueWeek;

it("opens on the latest missing day before the business date, else the business date or a past week's last day", () => {
  // Monday 28 Sep to Sunday 4 Oct 2026; the business date is the Wednesday.
  expect(
    captureDayFor(
      weekOf("2026-09-28", "2026-09-30", [
        "missing",
        "missing",
        "missing",
        "future",
      ]),
    ),
  ).toBe("2026-09-29");
  expect(
    captureDayFor(
      weekOf("2026-09-28", "2026-09-30", ["amount", "amount", "missing"]),
    ),
  ).toBe("2026-09-30");
  expect(
    captureDayFor(weekOf("2026-09-14", "2026-09-30", Array(7).fill("amount"))),
  ).toBe("2026-09-20");
});

it("finds the first day of a date's week from any first day of a week", () => {
  expect(weekStartFor("2026-09-29", "2026-09-28")).toBe("2026-09-28");
  expect(weekStartFor("2026-09-27", "2026-09-28")).toBe("2026-09-21");
  expect(weekStartFor("2026-10-05", "2026-09-28")).toBe("2026-10-05");
});

it("leaves out rows that cannot change, are unchanged or were never typed", () => {
  const day = {
    date: "2026-09-29",
    businessDate: "2026-09-30",
    truncated: false,
    vehicles: [
      {
        id: "a",
        companyId: "c",
        registration: "KDA 482M",
        day: { ...cell("2026-09-29", "amount"), canEdit: false },
        lastWeek: null,
      },
      {
        id: "b",
        companyId: "c",
        registration: "KBZ 110A",
        day: { ...cell("2026-09-29", "amount"), canEdit: true },
        lastWeek: null,
      },
      {
        id: "c",
        companyId: "c",
        registration: "KCC 333C",
        day: cell("2026-09-29", "missing"),
        lastWeek: null,
      },
    ],
  };
  const typed = {
    a: { amount: "1000", reason: "" as const, note: "" },
    b: { amount: " 900 ", reason: "" as const, note: "" },
  };
  expect(dayRows(day, typed, true)).toEqual({ rows: [], problems: [] });
});
