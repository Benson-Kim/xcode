import { describe, expect, it } from "vitest";

import { createFormatter } from "@xcode/shared/format";

import type { ItemChoice } from "../components/recurring/itemChoices";
import {
  type RecurringInput,
  validateRecurring,
} from "../components/recurring/validate";
import type { RecurringItem } from "../components/setup/shared";

const formats = createFormatter();

const choice: ItemChoice = {
  id: "e1",
  name: "Insurance",
  categoryId: "k1",
  categoryName: "Cover",
  bucket: 2,
  off: false,
};

const valid: RecurringInput = {
  kind: 1,
  picked: choice,
  name: "",
  note: "",
  total: 100,
  frequency: 3,
  start: "2026-09-10",
  end: "",
  noEnd: true,
  earliestStart: "2026-09-01",
  selectedCount: 2,
  allocationTotal: 100,
  difference: 0,
};

const saved = {
  id: "r1",
  start: "2026-08-15",
} as RecurringItem;

const cases: [string, Partial<RecurringInput>, Record<string, string>][] = [
  ["a valid cost has no errors", {}, {}],
  [
    "a cost with no item chosen",
    { picked: undefined },
    { expenseItem: "Choose the expense item." },
  ],
  [
    "a cost whose item was turned off",
    { picked: { ...choice, off: true } },
    {
      expenseItem: "This item is turned off. Choose another expense item.",
    },
  ],
  [
    "savings need a name",
    { kind: 2, picked: undefined, name: "  " },
    { name: "Enter a name." },
  ],
  [
    "a note past the limit",
    { note: "x".repeat(201) },
    { note: "Keep the note to 200 characters." },
  ],
  ["a note at the limit is fine", { note: "x".repeat(200) }, {}],
  ["no amount", { total: 0 }, { amount: "Enter the amount in KES." }],
  [
    "the retired daily schedule",
    { frequency: 1 },
    {
      frequency: "Every day is no longer offered. Choose how often it posts.",
    },
  ],
  ["no start date", { start: "" }, { start: "Enter the start date." }],
  [
    "a new item starting before the earliest start",
    { start: "2026-08-31" },
    {
      start: `Start on or after ${formats.formatDateOnly("2026-09-01")}. Anything earlier is a one-off expense, not a schedule.`,
    },
  ],
  [
    "an existing item keeps its old start",
    { item: saved, start: "2026-08-15" },
    {},
  ],
  [
    "an existing item moved to another early start",
    { item: saved, start: "2026-08-20" },
    {
      start: `Start on or after ${formats.formatDateOnly("2026-09-01")}. Anything earlier is a one-off expense, not a schedule.`,
    },
  ],
  [
    "an end date is required unless there is no end",
    { noEnd: false, end: "" },
    { end: "The end date must be on or after the start date." },
  ],
  [
    "an end before the start",
    { noEnd: false, end: "2026-09-09" },
    { end: "The end date must be on or after the start date." },
  ],
  ["an end on the start is fine", { noEnd: false, end: "2026-09-10" }, {}],
  [
    "no vehicle ticked",
    { selectedCount: 0, allocationTotal: 0, difference: 10000 },
    { allocations: "Tick at least one vehicle." },
  ],
  [
    "a split that does not add up",
    { allocationTotal: 60, difference: 4000 },
    {
      allocations: `The split must add up to ${formats.kes(100)}. It is ${formats.kes(60)}.`,
    },
  ],
];

describe("validateRecurring", () => {
  it.each(cases)("%s", (_name, change, expected) => {
    expect(validateRecurring({ ...valid, ...change }, formats)).toEqual(
      expected,
    );
  });

  it("reports every failing rule together", () => {
    const errors = validateRecurring(
      {
        ...valid,
        picked: undefined,
        total: 0,
        start: "",
        selectedCount: 0,
        difference: 0,
      },
      formats,
    );
    expect(Object.keys(errors).sort()).toEqual([
      "allocations",
      "amount",
      "expenseItem",
      "start",
    ]);
  });
});
