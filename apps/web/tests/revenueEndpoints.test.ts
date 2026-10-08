import { beforeEach, describe, expect, it } from "vitest";

import {
  revenueApi,
  revenueWeekPagePath,
  revenueWeekPath,
  vehicleWeekPath,
} from "../lib/endpoints/revenue";
import { fakeApi } from "./fakeApi";

let fake: ReturnType<typeof fakeApi>;
beforeEach(() => {
  fake = fakeApi();
  fake.on("GET setup/revenue*", [200, { vehicles: [] }]);
  fake.on("PUT setup/revenue/*", [200, {}]);
});

const lastCall = () => fake.calls[fake.calls.length - 1];

describe("revenue paths", () => {
  it.each([
    [{ weekStart: "", companyId: "" }, "setup/revenue"],
    [
      { weekStart: "2026-09-21", companyId: "" },
      "setup/revenue?weekStart=2026-09-21",
    ],
    [{ weekStart: "", companyId: "c 1" }, "setup/revenue?companyId=c+1"],
    [
      { weekStart: "2026-09-21", companyId: "company-3" },
      "setup/revenue?weekStart=2026-09-21&companyId=company-3",
    ],
  ])("week %j", (query, path) => {
    expect(revenueWeekPath(query)).toBe(path);
  });

  it("builds a page of a week with the company escaped", () => {
    expect(
      revenueWeekPagePath({
        weekStart: "2026-09-21",
        companyId: "",
        page: 2,
        pageSize: 100,
      }),
    ).toBe("setup/revenue?weekStart=2026-09-21&page=2&pageSize=100");
    expect(
      revenueWeekPagePath({
        weekStart: "2026-09-21",
        companyId: "a b/c",
        page: 3,
        pageSize: 50,
      }),
    ).toBe(
      "setup/revenue?weekStart=2026-09-21&companyId=a%20b%2Fc&page=3&pageSize=50",
    );
  });

  it("builds one vehicle's week", () => {
    expect(vehicleWeekPath("v1", "2026-09-30")).toBe(
      "setup/revenue?weekStart=2026-09-30&vehicleId=v1",
    );
  });
});

describe("revenueApi", () => {
  it("reads one vehicle's week with GET", async () => {
    await revenueApi.vehicleWeek("v1", "2026-09-30");
    expect(lastCall()).toMatchObject({
      method: "GET",
      path: "setup/revenue?weekStart=2026-09-30&vehicleId=v1",
      body: {},
    });
  });

  it("saves a day with PUT and the version in the body", async () => {
    await revenueApi.saveDay("v1", "2026-09-30", {
      amount: 850,
      reason: null,
      note: null,
      version: 3,
    });
    expect(lastCall()).toMatchObject({
      method: "PUT",
      path: "setup/revenue/v1/2026-09-30",
      body: { amount: 850, reason: null, note: null, version: 3 },
    });
  });

  it("sends a null version for a first capture", async () => {
    await revenueApi.saveDay("v1", "2026-09-30", {
      amount: null,
      reason: "Other",
      note: "Flat tyre",
      version: null,
    });
    expect(lastCall().body).toEqual({
      amount: null,
      reason: "Other",
      note: "Flat tyre",
      version: null,
    });
  });
});
