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
    vehicles: [
      {
        id: "vehicle-1",
        registration: "KDA 482M",
        companyName: "North Star",
        days: ["2026-09-28", "2026-09-29"],
      },
    ],
  });
  const written = JSON.stringify(list);
  for (const figure of [
    "expected",
    "amount",
    "totalAmount",
    "totalExpected",
    "percent",
    "1000",
    "2000",
  ])
    expect(written).not.toContain(figure);
});

it("lets a phone that started offline capture against the list it saved", async () => {
  await trustPhone();
  const api = fakeApi();
  api.on("setup/revenue", [200, revenueWeek]);
  await (
    await freshLoadWeek()
  )(OWNER);

  // A cold start: nothing in memory, and no connection.
  api.on("setup/revenue", "offline");
  const result = await (await freshLoadWeek())(OWNER);

  expect(result.saved).toBe(true);
  expect(result.minimal).toBe(true);
  expect(result.week.vehicles.map((vehicle) => vehicle.registration)).toEqual([
    "KDA 482M",
  ]);
  expect(result.week.vehicles[0].days.map((day) => day.date)).toEqual([
    "2026-09-28",
    "2026-09-29",
  ]);
  // Open to capture, with nothing claimed about what was earned or expected.
  expect(
    result.week.vehicles[0].days.every(
      (day) => day.canEdit && day.amount === null && day.expected === 0,
    ),
  ).toBe(true);
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
    vehicles: [
      {
        id: "vehicle-1",
        registration: "KDA 482M",
        companyName: "North Star",
        days: ["2026-09-28"],
      },
    ],
    savedAt: Date.now() - 73 * HOURS,
  });
  fakeApi().on("setup/revenue", "offline");

  await expect((await freshLoadWeek())(OWNER)).rejects.toThrow(
    "No internet connection.",
  );
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
    vehicles: [
      {
        id: "vehicle-9",
        registration: "KZZ 999Z",
        companyName: "Other Fleet",
        days: ["2026-09-28"],
      },
    ],
    savedAt: Date.now(),
  });
  fakeApi().on("setup/revenue", "offline");

  await expect((await freshLoadWeek())(OWNER)).rejects.toThrow(
    "No internet connection.",
  );
});

// A fleet past the API's whole-grid limit: the first answer stops at 500 vehicles and the rest come 100 a page.
function largeFleet(api: ReturnType<typeof fakeApi>, total: number) {
  const template = revenueWeek.vehicles[0];
  const fleet = Array.from({ length: total }, (_, index) => ({
    ...template,
    id: `vehicle-${index}`,
    registration: `KDA ${String(index).padStart(3, "0")}A`,
  }));
  const page = (vehicles: typeof fleet) => ({
    ...revenueWeek,
    vehicles,
    totalVehicles: total,
  });
  api.on("setup/revenue", [
    200,
    {
      ...page(fleet.slice(0, 500)),
      pageNumber: 1,
      pageSize: 500,
      truncated: true,
    },
  ]);
  for (let number = 6; number <= Math.ceil(total / 100); number++)
    api.on(`setup/revenue?weekStart=2026-09-28&page=${number}&pageSize=100`, [
      200,
      {
        ...page(fleet.slice((number - 1) * 100, number * 100)),
        pageNumber: number,
        pageSize: 100,
        truncated: false,
      },
    ]);
  return fleet;
}

it("loads every page of a fleet past the API's whole-grid limit, and writes all of it down", async () => {
  await trustPhone();
  const api = fakeApi();
  const fleet = largeFleet(api, 730);

  const result = await (await freshLoadWeek())(OWNER);

  expect(api.calls.map((call) => call.path)).toEqual([
    "setup/revenue",
    "setup/revenue?weekStart=2026-09-28&page=6&pageSize=100",
    "setup/revenue?weekStart=2026-09-28&page=7&pageSize=100",
    "setup/revenue?weekStart=2026-09-28&page=8&pageSize=100",
  ]);
  expect(result.week.vehicles.map((vehicle) => vehicle.id)).toEqual(
    fleet.map((vehicle) => vehicle.id),
  );
  expect(result.week.truncated).toBe(false);
  const list = await stored();
  expect(list?.vehicles).toHaveLength(730);
  expect(list?.vehicles[729]).toMatchObject({
    id: "vehicle-729",
    registration: "KDA 729A",
  });
});

it("never writes down part of a fleet when a later page cannot be fetched", async () => {
  await trustPhone();
  const api = fakeApi();
  largeFleet(api, 730);
  api.on("setup/revenue?weekStart=2026-09-28&page=7&pageSize=100", "offline");

  await expect((await freshLoadWeek())(OWNER)).rejects.toThrow(
    "No internet connection.",
  );
  expect(await stored()).toBeNull();
});

it("does not answer a single vehicle's week, or another week, from the list", async () => {
  await trustPhone();
  const api = fakeApi();
  api.on("setup/revenue", [200, revenueWeek]);
  await (
    await freshLoadWeek()
  )(OWNER);
  expect(await stored()).not.toBeNull();

  api.on("setup/revenue", "offline");
  api.on("setup/revenue?weekStart=2026-09-28&vehicleId=vehicle-1", "offline");
  api.on("setup/revenue?weekStart=2026-09-21", "offline");
  const loadWeek = await freshLoadWeek();
  // One vehicle's week is not what the list holds, and the list only ever covers the current week.
  await expect(loadWeek(OWNER, "2026-09-28", "vehicle-1")).rejects.toThrow(
    "No internet connection.",
  );
  await expect(loadWeek(OWNER, "2026-09-21")).rejects.toThrow(
    "No internet connection.",
  );
});
