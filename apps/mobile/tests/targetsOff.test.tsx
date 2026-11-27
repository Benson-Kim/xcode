import { act, fireEvent, screen, waitFor } from "@testing-library/react-native";

import type { Appearance } from "../src/appearance";
import {
  catalog,
  fakeApi,
  people,
  revenueDashboard,
  revenueWeek,
  tokens,
} from "./fakeApi";
import { startApp, trustPhone, typePin } from "./helpers";

const stored = (): Map<string, string> => require("expo-secure-store").__items;

const appearance = (targets: boolean): Appearance => ({
  organizationName: "Demo Fleet",
  settingsVersion: 4,
  businessDate: "2026-09-29",
  branding: {
    displayName: "North Star Sacco",
    logoAlt: "North Star",
    primary: "#0B7A75",
    secondary: "#3B1F5C",
    accent: "#1E6B3A",
    logo: null,
  },
  formats: {
    locale: "en-GB",
    timeZone: "Africa/Nairobi",
    datePattern: "medium",
    hour12: false,
    currency: "KES",
    useGrouping: true,
    numberDecimals: 2,
    firstDayOfWeek: 0,
    weekNumbering: "iso8601",
    direction: "ltr",
  },
  themeMode: "system",
  reducedMotion: false,
  fontScale: 1,
  sundayWeekSince: null,
  targets,
});

// Tuesday has KES 300 with its low revenue reason and a No to the fuel question.
const [monday, tuesday, ...later] = revenueWeek.vehicles[0].days;
const week = {
  ...revenueWeek,
  vehicles: [
    {
      ...revenueWeek.vehicles[0],
      days: [
        monday,
        {
          ...tuesday,
          status: "amount",
          amount: 300,
          reason: "Garage",
          fuel: "no",
          version: 1,
        },
        ...later,
      ],
      totalAmount: 300,
      percent: 15,
    },
  ],
  totalAmount: 300,
  percent: 15,
};

async function signIn(targets: boolean) {
  await trustPhone(people.owner, "0733520614");
  const api = fakeApi();
  api.on("auth/pin", [200, tokens(2)]);
  api.on("auth/session", [200, people.owner]);
  api.on("setup/access/catalog", [200, catalog]);
  api.on("setup/appearance", [200, appearance(targets)]);
  api.on("setup/revenue", [200, week]);
  api.on("setup/revenue?weekStart=2026-09-28", [200, week]);
  api.on("setup/revenue?weekStart=2026-09-28&vehicleId=vehicle-1", [200, week]);
  for (const period of ["today", "week", "month"])
    api.on(`setup/revenue/dashboard?period=${period}`, [
      200,
      { ...revenueDashboard, period, revenue: 300, percent: 15 },
    ]);
  await startApp();
  await typePin("4826");
  await screen.findByText(`Hi ${people.owner.firstName}`);
  await waitFor(() =>
    expect(stored().get("xcode.appearance")).toContain("North Star Sacco"),
  );
  await act(() => new Promise((resolve) => setTimeout(resolve, 50)));
  return api;
}

async function openVehicleWeek(row: RegExp) {
  await fireEvent.press(screen.getByRole("tab", { name: /^Revenue/ }));
  await fireEvent.press(await screen.findByRole("button", { name: "Week" }));
  await fireEvent.press(await screen.findByRole("button", { name: row }));
}

it("with Targets off, shows revenue alone on Home, the week, its rows and the vehicle week, with Not fueled", async () => {
  await signIn(false);

  expect(await screen.findByText("KES 300")).toBeTruthy();
  expect(screen.queryByText(/of target/)).toBeNull();
  expect(screen.queryByText(/weekly target/)).toBeNull();

  await fireEvent.press(screen.getByRole("tab", { name: /^Revenue/ }));
  expect(
    await screen.findByLabelText("KDA 482M, KES 300, Garage, Not fueled"),
  ).toBeTruthy();
  await fireEvent.press(await screen.findByRole("button", { name: "Week" }));
  expect(await screen.findByText("KES 300 so far")).toBeTruthy();
  expect(screen.queryByText(/expected to date/)).toBeNull();
  await fireEvent.press(
    screen.getByRole("button", { name: "KDA 482M, KES 300. Open the week" }),
  );

  expect(await screen.findByLabelText("Mon 28: No record")).toBeTruthy();
  expect(screen.getByLabelText(/^Tue 29: KES 300, Not fueled$/)).toBeTruthy();
  expect(screen.getByLabelText("To date: actual KES 300")).toBeTruthy();
  expect(screen.queryByLabelText(/expected/)).toBeNull();
});

it("with Targets on, the same week keeps its target, share and expected figures", async () => {
  await signIn(true);

  expect(await screen.findByText(/^15% of target KES 2,000/)).toBeTruthy();
  await openVehicleWeek(
    /^KDA 482M, KES 300, 15% of KES 2,000\. Open the week$/,
  );

  expect(
    await screen.findByLabelText(
      "Mon 28: expected KES 1,000, No record, KES 1,000 below",
    ),
  ).toBeTruthy();
  expect(
    screen.getByLabelText(/^Tue 29: expected KES 1,000, KES 300, Not fueled, /),
  ).toBeTruthy();
});
