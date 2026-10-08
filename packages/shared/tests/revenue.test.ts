import { expect, it } from "vitest";

import { parseRevenueAmount, REVENUE_AMOUNT_ERROR } from "../src/revenue";

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
