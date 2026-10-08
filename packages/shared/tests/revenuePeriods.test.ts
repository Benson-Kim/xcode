import { describe, expect, it } from "vitest";

import {
  REVENUE_PERIODS,
  REVENUE_REPORT_PERIODS,
  type RevenuePeriod,
  revenuePeriodLabel,
} from "@xcode/shared/revenue";

describe("revenue periods", () => {
  it.each([
    ["today", "Today"],
    ["week", "This week"],
    ["month", "This month"],
    ["unknown", "unknown"],
    ["", ""],
    ["toString", "toString"],
  ])("labels %j as %j", (period, expected) => {
    expect(revenuePeriodLabel(period as RevenuePeriod)).toBe(expected);
  });

  it("reports by week and month only", () => {
    expect(REVENUE_REPORT_PERIODS.map((period) => period.value)).toEqual([
      "week",
      "month",
    ]);
  });

  it("labels every period", () => {
    for (const period of REVENUE_PERIODS)
      expect(revenuePeriodLabel(period.value)).toBe(period.label);
  });
});
