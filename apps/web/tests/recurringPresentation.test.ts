import { expect, it } from "vitest";

import { firstOfMonth } from "@xcode/shared/dates";

import * as presentation from "../components/recurringPresentation";
import {
  recurringFrequency,
  recurringMonthlyEstimate,
  recurringNextPostings,
} from "../components/recurringPresentation";

const schedule = {
  day: null,
  lastDay: false,
  start: "2026-01-01",
  end: null,
  stoppedFrom: null,
  month: null,
};

it("labels weekly, monthly, yearly and the legacy daily schedule", () => {
  expect(recurringFrequency({ ...schedule, frequency: 1 })).toBe("Every day");
  expect(recurringFrequency({ ...schedule, frequency: 2, day: 1 })).toBe(
    "Every Monday",
  );
  expect(recurringFrequency({ ...schedule, frequency: 3, day: 22 })).toBe(
    "Every month on the 22nd",
  );
  expect(recurringFrequency({ ...schedule, frequency: 3, lastDay: true })).toBe(
    "Last day of every month",
  );
  expect(
    recurringFrequency({ ...schedule, frequency: 4, month: 3, day: 14 }),
  ).toBe("Every year on 14th March");
  expect(
    recurringFrequency({ ...schedule, frequency: 4, month: 2, lastDay: true }),
  ).toBe("Every year on the last day of February");
});

it("previews yearly postings on their month and day, including the last day of a short month", () => {
  expect(
    recurringNextPostings(
      { ...schedule, frequency: 4, month: 3, day: 14 },
      "2026-09-21",
      2,
    ),
  ).toEqual(["2027-03-14", "2028-03-14"]);
  expect(
    recurringNextPostings(
      { ...schedule, frequency: 4, month: 2, lastDay: true },
      "2026-09-21",
      2,
    ),
  ).toEqual(["2027-02-28", "2028-02-29"]);
  // Due today counts; the end date stops the preview.
  expect(
    recurringNextPostings(
      { ...schedule, frequency: 4, month: 9, day: 21, end: "2027-12-31" },
      "2026-09-21",
      5,
    ),
  ).toEqual(["2026-09-21", "2027-09-21"]);
});

it("estimates a month as a twelfth of a yearly amount", () => {
  expect(recurringMonthlyEstimate(117600, 4)).toBe(9800);
  expect(recurringMonthlyEstimate(1000, 1)).toBe(30400);
  expect(recurringMonthlyEstimate(700, 2)).toBe(3045);
  expect(recurringMonthlyEstimate(3000, 3)).toBe(3000);
});

it("clamps day 31 to the final valid day of shorter months", () => {
  const monthly31 = { ...schedule, frequency: 3, day: 31 };
  const postings = recurringNextPostings(monthly31, "2026-01-01", 6);
  expect(postings).toEqual([
    "2026-01-31",
    "2026-02-28",
    "2026-03-31",
    "2026-04-30",
    "2026-05-31",
    "2026-06-30",
  ]);
});

it("clamps day 31 in a leap year February", () => {
  const monthly31 = { ...schedule, frequency: 3, day: 31 };
  const postings = recurringNextPostings(monthly31, "2028-02-01", 2);
  expect(postings).toEqual(["2028-02-29", "2028-03-31"]);
});

it("clamps day 30 for February", () => {
  const monthly30 = { ...schedule, frequency: 3, day: 30 };
  const postings = recurringNextPostings(monthly30, "2026-02-01", 3);
  expect(postings).toEqual(["2026-02-28", "2026-03-30", "2026-04-30"]);
});

it("clamps yearly day 31 to shorter months", () => {
  const yearly31Feb = { ...schedule, frequency: 4, month: 2, day: 31 };
  expect(recurringNextPostings(yearly31Feb, "2026-01-01", 3)).toEqual([
    "2026-02-28",
    "2027-02-28",
    "2028-02-29",
  ]);
});

it("takes the earliest start from the business date's month, not the computer clock", () => {
  expect(firstOfMonth("2026-09-21")).toBe("2026-09-01");
  expect(firstOfMonth("2027-01-31")).toBe("2027-01-01");
  expect("todayDateOnly" in presentation).toBe(false);
});
