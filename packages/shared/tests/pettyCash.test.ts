import { expect, it } from "vitest";

import {
  canOpenPettyCash,
  parsePettyCashAmount,
  parsePettyCashUnits,
  PETTY_CASH_AMOUNT_ERROR,
  pettyCashEntriesPath,
  pettyCashOverviewPath,
  pettyCashTotal,
} from "../src/pettyCash";

it("takes signed amounts with at most two decimals and never zero", () => {
  expect(parsePettyCashAmount("3500")).toEqual({ ok: true, amount: 3500 });
  expect(parsePettyCashAmount("1,250.50")).toEqual({
    ok: true,
    amount: 1250.5,
  });
  expect(parsePettyCashAmount(" -500 ")).toEqual({ ok: true, amount: -500 });
  expect(parsePettyCashAmount("-1,000")).toEqual({ ok: true, amount: -1000 });
  for (const bad of [
    "",
    "0",
    "-0",
    "0.00",
    "12.345",
    "abc",
    "--5",
    "5-",
    "1,00",
  ])
    expect(parsePettyCashAmount(bad)).toEqual({
      ok: false,
      error: PETTY_CASH_AMOUNT_ERROR,
    });
});

it("takes units above zero with up to three decimals and no upper limit of 1000", () => {
  expect(parsePettyCashUnits("1")).toBe(1);
  expect(parsePettyCashUnits("4.5")).toBe(4.5);
  expect(parsePettyCashUnits(" 11.875 ")).toBe(11.875);
  expect(parsePettyCashUnits("1001")).toBe(1001);
  expect(parsePettyCashUnits("1,001.5")).toBe(1001.5);
  for (const bad of ["0", "0.000", "1.2345", "-2", "", "two", "1,00", "1.5.2"])
    expect(parsePettyCashUnits(bad)).toBeNull();
});

it("totals a line to the cent with halves away from zero, as the server does", () => {
  expect(pettyCashTotal(3, 0.1)).toBe(0.3);
  expect(pettyCashTotal(2, -1500)).toBe(-3000);
  expect(pettyCashTotal(11.875, 182.4)).toBe(2166);
  expect(pettyCashTotal(4.5, 1250.5)).toBe(5627.25);
  expect(pettyCashTotal(0.125, 0.1)).toBe(0.01);
  expect(pettyCashTotal(0.125, -0.1)).toBe(-0.01);
  expect(pettyCashTotal(1.005, 1)).toBe(1.01);
  expect(pettyCashTotal(999_999_999.999, 999.99)).toBe(999_989_999_999);
});

it("builds the entries path, leaving out what is not set and joining several kinds", () => {
  expect(pettyCashEntriesPath()).toBe("setup/pettycash/entries");
  expect(
    pettyCashEntriesPath({
      from: "2026-10-01",
      to: "2026-10-01",
      kind: ["expense", "credit"],
      q: "",
      page: 2,
    }),
  ).toBe(
    "setup/pettycash/entries?from=2026-10-01&to=2026-10-01&kind=expense%2Ccredit&page=2",
  );
  expect(pettyCashEntriesPath({ status: "waiting", q: "KDA 482M" })).toBe(
    "setup/pettycash/entries?status=waiting&q=KDA+482M",
  );
});

it("builds the overview path for a day or a week", () => {
  expect(pettyCashOverviewPath()).toBe("setup/pettycash/overview");
  expect(
    pettyCashOverviewPath({
      date: "2026-10-07",
      period: "week",
      holderId: "h1",
    }),
  ).toBe("setup/pettycash/overview?date=2026-10-07&period=week&holderId=h1");
});

it("builds the overview path for any span with from and to", () => {
  expect(
    pettyCashOverviewPath({
      from: "2026-10-01",
      to: "2026-10-09",
      holderId: "h1",
    }),
  ).toBe("setup/pettycash/overview?from=2026-10-01&to=2026-10-09&holderId=h1");
});

it("opens petty cash for any of its four permissions only", () => {
  for (const key of [
    "pettycash.spend",
    "pettycash.view_all",
    "pettycash.approve_item",
    "pettycash.issue",
  ])
    expect(canOpenPettyCash([key])).toBe(true);
  expect(
    canOpenPettyCash(["pettycash.approve_day", "dash.float", "revenue.view"]),
  ).toBe(false);
});
