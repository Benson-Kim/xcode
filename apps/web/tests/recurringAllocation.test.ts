import { describe, expect, it } from "vitest";

import {
  balanceLabel,
  formatShare,
  isInFleet,
  splitAcrossFleet,
  splitAmountEvenly,
  sumShares,
} from "../components/recurring/allocation";
import type { VehicleOption } from "../components/setup/shared";

const vehicle = (id: string, active?: boolean): VehicleOption => ({
  id,
  companyId: "c1",
  companyName: "Zuri",
  registration: `KA${id}`,
  active,
});

describe("splitAmountEvenly", () => {
  it("gives the remainder cents to the first vehicles", () => {
    expect(splitAmountEvenly(100, ["a", "b", "c"])).toEqual({
      a: "33.34",
      b: "33.33",
      c: "33.33",
    });
  });

  it("splits whole amounts without decimals", () => {
    expect(splitAmountEvenly(90, ["a", "b", "c"])).toEqual({
      a: "30",
      b: "30",
      c: "30",
    });
  });

  it("spreads two spare cents over the first two vehicles", () => {
    expect(splitAmountEvenly(0.05, ["a", "b", "c"])).toEqual({
      a: "0.02",
      b: "0.02",
      c: "0.01",
    });
  });

  it("returns nothing for an empty list", () => {
    expect(splitAmountEvenly(100, [])).toEqual({});
  });
});

describe("splitAcrossFleet", () => {
  const vehicles = [vehicle("a"), vehicle("b"), vehicle("gone", false)];

  it("keeps an out-of-fleet share and splits only the rest", () => {
    expect(
      splitAcrossFleet(vehicles, { gone: "40" }, 100, ["a", "b", "gone"]),
    ).toEqual({ gone: "40", a: "30", b: "30" });
  });

  it("defaults a missing out-of-fleet share to 0", () => {
    expect(splitAcrossFleet(vehicles, {}, 50, ["a", "gone"])).toEqual({
      gone: "0",
      a: "50",
    });
  });

  it("never splits a negative remainder", () => {
    expect(
      splitAcrossFleet(vehicles, { gone: "80" }, 50, ["a", "gone"]),
    ).toEqual({ gone: "80", a: "0" });
  });

  it("returns nothing for an empty list", () => {
    expect(splitAcrossFleet(vehicles, {}, 100, [])).toEqual({});
  });
});

describe("helpers", () => {
  it("treats a vehicle as in the fleet unless it is marked inactive", () => {
    const vehicles = [vehicle("a"), vehicle("b", true), vehicle("c", false)];
    expect(isInFleet(vehicles, "a")).toBe(true);
    expect(isInFleet(vehicles, "b")).toBe(true);
    expect(isInFleet(vehicles, "c")).toBe(false);
  });

  it("sums only the listed shares and treats junk as 0", () => {
    expect(sumShares(["a", "b", "x"], { a: "10.5", b: "abc", c: "99" })).toBe(
      10.5,
    );
  });

  it("formats whole numbers plain and others to two places", () => {
    expect(formatShare(40)).toBe("40");
    expect(formatShare(33.3)).toBe("33.30");
  });

  it("says what is left to allocate", () => {
    const kes = (amount: number) => `K${amount}`;
    const base = {
      selectedCount: 2,
      total: 100,
      difference: 0,
      isBalanced: false,
    };
    expect(balanceLabel({ ...base, selectedCount: 0 }, kes)).toBe(
      "Tick at least one vehicle",
    );
    expect(balanceLabel({ ...base, total: 0 }, kes)).toBe("Enter the amount");
    expect(balanceLabel({ ...base, isBalanced: true }, kes)).toBe("Balanced");
    expect(balanceLabel({ ...base, difference: 250 }, kes)).toBe(
      "K2.5 still to allocate",
    );
    expect(balanceLabel({ ...base, difference: -250 }, kes)).toBe(
      "K2.5 too much",
    );
  });
});
