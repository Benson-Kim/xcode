import { loadCaptureList, saveCaptureList } from "../src/lib/storage";
import { fakeApi, revenueWeek } from "./fakeApi";
import { trustPhone } from "./helpers";

const HOURS = 60 * 60 * 1000;
const OWNER = "u-antony";

// Each case starts with the week loader's in-memory cache empty, the way a cold start does.
async function freshLoadWeek() {
  let loadWeek!: typeof import("../src/revenue/week").loadWeek;
  await jest.isolateModulesAsync(async () => {
    loadWeek = require("../src/revenue/week").loadWeek;
  });
  return loadWeek;
}

const stored = () => loadCaptureList(OWNER);

it("writes down only what capture needs: no amounts, no targets, no totals", async () => {
  await trustPhone();
  fakeApi().on("setup/revenue", [200, revenueWeek]);
  const loadWeek = await freshLoadWeek();

  await loadWeek(OWNER);

  const list = await stored();
  expect(list).toMatchObject({
    owner: OWNER,
    weekStart: "2026-09-28",
    currentWeekStart: "2026-09-28",
    businessDate: "2026-09-29",
    // Only the days still open to capture; the five future days are left out.
    vehicles: [{ id: "vehicle-1", registration: "KDA 482M", companyName: "North Star", days: ["2026-09-28", "2026-09-29"] }],
  });
  const written = JSON.stringify(list);
  for (const figure of ["expected", "amount", "totalAmount", "totalExpected", "percent", "1000", "2000"])
    expect(written).not.toContain(figure);
});

it("lets a phone that started offline capture against the list it saved", async () => {
  await trustPhone();
  const api = fakeApi();
  api.on("setup/revenue", [200, revenueWeek]);
  await (await freshLoadWeek())(OWNER);

  // A cold start: nothing in memory, and no connection.
  api.on("setup/revenue", "offline");
  const result = await (await freshLoadWeek())(OWNER);

  expect(result.saved).toBe(true);
  expect(result.minimal).toBe(true);
  expect(result.week.vehicles.map((vehicle) => vehicle.registration)).toEqual(["KDA 482M"]);
  expect(result.week.vehicles[0].days.map((day) => day.date)).toEqual(["2026-09-28", "2026-09-29"]);
  // Open to capture, with nothing claimed about what was earned or expected.
  expect(result.week.vehicles[0].days.every((day) => day.canEdit && day.amount === null && day.expected === 0)).toBe(true);
  expect(result.week.vehicles[0].earliestMissing).toBe("2026-09-28");
});

it("drops a list older than the 72 hours offline unlock allows", async () => {
  await trustPhone();
  await saveCaptureList({
    owner: OWNER,
    weekStart: "2026-09-28",
    weekThrough: "2026-10-04",
    currentWeekStart: "2026-09-28",
    businessDate: "2026-09-29",
    vehicles: [{ id: "vehicle-1", registration: "KDA 482M", companyName: "North Star", days: ["2026-09-28"] }],
    savedAt: Date.now() - 73 * HOURS,
  });
  fakeApi().on("setup/revenue", "offline");

  await expect((await freshLoadWeek())(OWNER)).rejects.toThrow("No internet connection.");
  expect(await stored()).toBeNull();
});

it("never hands one person's list to another", async () => {
  await trustPhone();
  await saveCaptureList({
    owner: "u-someone-else",
    weekStart: "2026-09-28",
    weekThrough: "2026-10-04",
    currentWeekStart: "2026-09-28",
    businessDate: "2026-09-29",
    vehicles: [{ id: "vehicle-9", registration: "KZZ 999Z", companyName: "Other Fleet", days: ["2026-09-28"] }],
    savedAt: Date.now(),
  });
  fakeApi().on("setup/revenue", "offline");

  await expect((await freshLoadWeek())(OWNER)).rejects.toThrow("No internet connection.");
});

it("does not answer a single vehicle's week, or another week, from the list", async () => {
  await trustPhone();
  const api = fakeApi();
  api.on("setup/revenue", [200, revenueWeek]);
  await (await freshLoadWeek())(OWNER);
  expect(await stored()).not.toBeNull();

  api.on("setup/revenue", "offline");
  api.on("setup/revenue?weekStart=2026-09-28&vehicleId=vehicle-1", "offline");
  api.on("setup/revenue?weekStart=2026-09-21", "offline");
  const loadWeek = await freshLoadWeek();
  // One vehicle's week is not what the list holds, and the list only ever covers the current week.
  await expect(loadWeek(OWNER, "2026-09-28", "vehicle-1")).rejects.toThrow("No internet connection.");
  await expect(loadWeek(OWNER, "2026-09-21")).rejects.toThrow("No internet connection.");
});
