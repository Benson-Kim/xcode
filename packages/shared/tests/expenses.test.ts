import { describe, expect, it } from "vitest";

import { pettyCashTotal } from "../src/pettyCash";
import {
  EXPENSE_ENTRIES_PATH,
  EXPENSE_MAX_DAYS,
  EXPENSE_MAX_VEHICLES,
  EXPENSE_NOTE_LIMIT,
  EXPENSE_PAGE_SIZE,
  EXPENSE_REASON_LIMIT,
  EXPENSE_SOURCES,
  EXPENSE_SOURCE_LABELS,
  expenseEntryPath,
  expenseLedgerPath,
  expenseOptionsPath,
  expenseTotal,
  splitEvenly,
  unallocated,
} from "../src/expenses";

const sum = (values: number[]) =>
  values.reduce((total, value) => total + Math.round(value * 100), 0) / 100;

describe("sources and limits", () => {
  it("labels every source once", () => {
    expect(EXPENSE_SOURCES).toEqual(["central", "pettycash", "scheduled"]);
    expect(
      EXPENSE_SOURCES.map((source) => EXPENSE_SOURCE_LABELS[source]),
    ).toEqual(["Central", "Petty cash", "Scheduled"]);
  });

  it("keeps the limits the forms and the server share", () => {
    expect(EXPENSE_NOTE_LIMIT).toBe(80);
    expect(EXPENSE_REASON_LIMIT).toBe(500);
    expect(EXPENSE_MAX_VEHICLES).toBe(50);
    expect(EXPENSE_PAGE_SIZE).toBe(100);
    expect(EXPENSE_MAX_DAYS).toBe(367);
  });
});

describe("expenseTotal", () => {
  it("is the petty cash rule, halves away from zero", () => {
    expect(expenseTotal).toBe(pettyCashTotal);
    expect(expenseTotal(11.875, 182.4)).toBe(2166);
    expect(expenseTotal(0.5, 0.01)).toBe(0.01);
    expect(expenseTotal(0.5, -0.01)).toBe(-0.01);
    expect(expenseTotal(0.4, 0.01)).toBe(0);
    expect(expenseTotal(3, 33.34)).toBe(100.02);
  });
});

describe("splitEvenly", () => {
  it("gives the odd cents to the first rows", () => {
    expect(splitEvenly(100, 3)).toEqual([33.34, 33.33, 33.33]);
    expect(splitEvenly(100.01, 3)).toEqual([33.34, 33.34, 33.33]);
    expect(splitEvenly(0.01, 3)).toEqual([0.01, 0, 0]);
  });

  it("splits what divides exactly into equal shares", () => {
    expect(splitEvenly(900, 3)).toEqual([300, 300, 300]);
    expect(splitEvenly(500, 1)).toEqual([500]);
  });

  it("splits a negative total the same way, keeping the sign", () => {
    expect(splitEvenly(-100, 3)).toEqual([-33.34, -33.33, -33.33]);
    expect(splitEvenly(-0.01, 2)).toEqual([-0.01, 0]);
  });

  it("works in whole cents, so float noise does not leak", () => {
    expect(splitEvenly(0.1 + 0.2, 2)).toEqual([0.15, 0.15]);
  });

  it("always adds back to the total", () => {
    for (const [total, count] of [
      [100, 3],
      [999.99, 7],
      [-250.5, 4],
      [1, 50],
    ] as const)
      expect(sum(splitEvenly(total, count))).toBe(total);
  });

  it("returns nothing for a count that is not a whole number above zero", () => {
    expect(splitEvenly(100, 0)).toEqual([]);
    expect(splitEvenly(100, -2)).toEqual([]);
    expect(splitEvenly(100, 1.5)).toEqual([]);
    expect(splitEvenly(100, Number.NaN)).toEqual([]);
  });
});

describe("unallocated", () => {
  it("is what is left, positive, or the excess, negative", () => {
    expect(unallocated(100, [{ amount: 60 }, { amount: 30 }])).toBe(10);
    expect(unallocated(100, [{ amount: 60 }, { amount: 50 }])).toBe(-10);
    expect(unallocated(100, [{ amount: 60 }, { amount: 40 }])).toBe(0);
  });

  it("is the whole total with nothing allocated", () => {
    expect(unallocated(100, [])).toBe(100);
  });

  it("counts in whole cents", () => {
    expect(unallocated(0.3, [{ amount: 0.1 }, { amount: 0.2 }])).toBe(0);
    expect(unallocated(100, [{ amount: 33.34 }, { amount: 33.33 }])).toBe(
      33.33,
    );
  });

  it("works for a refund", () => {
    expect(unallocated(-100, [{ amount: -40 }])).toBe(-60);
  });
});

describe("paths", () => {
  it("builds the ledger path, skipping what is empty", () => {
    expect(expenseLedgerPath({ from: "2026-10-05", to: "2026-10-11" })).toBe(
      "setup/expenses/ledger?from=2026-10-05&to=2026-10-11",
    );
    expect(
      expenseLedgerPath({
        from: "2026-10-05",
        to: "2026-10-11",
        source: "pettycash",
        q: "oil filter",
        page: 2,
        pageSize: 100,
      }),
    ).toBe(
      "setup/expenses/ledger?from=2026-10-05&to=2026-10-11&source=pettycash&q=oil+filter&page=2&pageSize=100",
    );
    expect(
      expenseLedgerPath({ from: "a", to: "b", source: undefined, q: "" }),
    ).toBe("setup/expenses/ledger?from=a&to=b");
  });

  it("builds the options path with or without a date", () => {
    expect(expenseOptionsPath()).toBe("setup/expenses/options");
    expect(expenseOptionsPath("2026-10-09")).toBe(
      "setup/expenses/options?date=2026-10-09",
    );
  });

  it("builds the entry paths, encoding the id", () => {
    expect(EXPENSE_ENTRIES_PATH).toBe("setup/expenses/entries");
    expect(expenseEntryPath("e-1")).toBe("setup/expenses/entries/e-1");
    expect(expenseEntryPath("e-1", "remove")).toBe(
      "setup/expenses/entries/e-1/remove",
    );
    expect(expenseEntryPath("a/b c")).toBe("setup/expenses/entries/a%2Fb%20c");
  });
});
