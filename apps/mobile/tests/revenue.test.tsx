import { act, fireEvent, screen, waitFor } from "@testing-library/react-native";

import { earliestNeededDay } from "@xcode/shared/capture";
import type { RevenueCell } from "@xcode/shared/revenue";

import { shiftDate } from "../src/revenue/dates";
import { catalog, fakeApi, people, tokens } from "./fakeApi";
import { startApp, storedText, trustPhone, typePin } from "./helpers";

// Counts how often the screen works out the earliest missing day.
jest.mock("@xcode/shared/capture", () => {
  const actual = jest.requireActual("@xcode/shared/capture");
  return { ...actual, earliestNeededDay: jest.fn(actual.earliestNeededDay) };
});

type Person = (typeof people)[keyof typeof people];
type Api = ReturnType<typeof fakeApi>;

// A week: days after the business date are future, the rest missing unless given.
function week(
  businessDate: string,
  weekStart: string,
  vehicles: {
    id: string;
    registration: string;
    earliestMissing?: string | null;
    days?: Record<string, Partial<RevenueCell>>;
  }[],
) {
  const dates = Array.from({ length: 7 }, (_, index) =>
    shiftDate(weekStart, index),
  );
  return {
    weekStart,
    weekThrough: dates[6],
    currentWeekStart: weekStart,
    businessDate,
    companies: [{ id: "company-1", name: "North Star" }],
    vehicles: vehicles.map((vehicle) => ({
      id: vehicle.id,
      companyId: "company-1",
      companyName: "North Star",
      registration: vehicle.registration,
      joinedOn: "2020-01-01",
      leftOn: null,
      earliestMissing: vehicle.earliestMissing ?? null,
      days: dates.map((date) => ({
        date,
        status: date > businessDate ? "future" : "missing",
        expected: 1000,
        amount: null,
        reason: null,
        note: null,
        canEdit: date <= businessDate,
        editedAfterCapture: false,
        version: null,
        ...vehicle.days?.[date],
      })),
      totalAmount: 0,
      totalExpected: 2000,
      percent: 0,
    })),
    totalAmount: 0,
    totalExpected: 2000,
    percent: 0,
  };
}

const TODAY = "2026-09-29";
const oneVehicle = week(TODAY, "2026-09-28", [
  {
    id: "v-1",
    registration: "KDA 482M",
    days: {
      "2026-09-28": {
        status: "amount",
        amount: 900,
        canEdit: false,
        version: 1,
      },
    },
  },
]);
const PUT = `setup/revenue/v-1/${TODAY}`;

async function signIn(
  person: Person,
  phone: string,
  routes: (api: Api) => void,
) {
  await trustPhone(person, phone);
  const api = fakeApi();
  api.on("auth/unlock", [200, tokens(2)]);
  api.on("auth/session", [200, person]);
  api.on("setup/access/catalog", [200, catalog]);
  routes(api);
  await startApp();
  await screen.findByText(`Welcome back, ${person.firstName}`);
  await typePin("4826");
  await screen.findByText(`Hi ${person.firstName}`);
  return api;
}

async function openRevenue() {
  await fireEvent.press(screen.getByRole("tab", { name: /^Revenue/ }));
}

async function captureAmount(row: string, amount: string) {
  await fireEvent.press(await screen.findByRole("button", { name: row }));
  await fireEvent.changeText(screen.getByLabelText("Revenue amount"), amount);
  await fireEvent.press(screen.getByRole("button", { name: "Save" }));
}

const tabLabel = () =>
  screen
    .getAllByRole("tab")
    .map((tab) => tab.props.accessibilityLabel as string)
    .find((label) => label.startsWith("Revenue"));

it("keeps a capture on the phone before sending it, then moves on to the next vehicle still missing that day", async () => {
  const api = await signIn(people.clerk, "0712000001", (routes) =>
    routes.on("setup/revenue", [
      200,
      week(
        TODAY,
        "2026-09-28",
        [
          { id: "v-1", registration: "KDA 482M" },
          { id: "v-2", registration: "KCY 117T" },
        ].map((vehicle) => ({
          ...vehicle,
          days: {
            "2026-09-28": {
              status: "amount" as const,
              amount: 900,
              canEdit: false,
              version: 1,
            },
          },
        })),
      ),
    ]),
  );
  let keptWhenSent = "";
  api.on(PUT, () => {
    keptWhenSent = storedText();
    return [200, { id: "r-1", version: 1 }];
  });
  await openRevenue();
  expect(await screen.findByText("Tue 29 Sep 2026")).toBeTruthy();
  expect(screen.getByText("0 of 2 captured")).toBeTruthy();

  await captureAmount("KDA 482M, Enter revenue", "1,500");
  // After saving, the sheet moves to the next vehicle still missing that day.
  expect(await screen.findByRole("header", { name: "KCY 117T" })).toBeTruthy();
  await waitFor(() =>
    expect(api.sent(PUT)).toEqual([
      { amount: 1500, reason: null, note: null, version: null },
    ]),
  );
  // Written to the Keychain before any network call; gone from it once the API accepted it.
  expect(keptWhenSent).toContain('"amount":1500');
  await waitFor(() => expect(storedText()).not.toContain('"amount":1500'));
  expect(tabLabel()).toBe("Revenue");
});

it("keeps a capture made without a connection and sends it when the network returns", async () => {
  const api = await signIn(people.clerk, "0712000002", (routes) =>
    routes.on("setup/revenue", [200, oneVehicle]),
  );
  api.on(PUT, "offline");
  await openRevenue();
  await captureAmount("KDA 482M, Enter revenue", "1000");

  expect(
    await screen.findByLabelText("KDA 482M, KES 1,000, not sent yet"),
  ).toBeTruthy();
  expect(screen.getByText("1 of 1 captured, 1 not sent yet")).toBeTruthy();
  expect(screen.getByText("1 waiting to send")).toBeTruthy();
  await waitFor(() => expect(tabLabel()).toBe("Revenue, 1 waiting to send"));
  expect(storedText()).toContain('"amount":1000');

  api.on(PUT, [200, { id: "r-1", version: 1 }]);
  await act(async () =>
    require("expo-network").__emit({
      isConnected: true,
      isInternetReachable: true,
    }),
  );
  await waitFor(() => expect(tabLabel()).toBe("Revenue"));
  expect(api.sent(PUT)).toHaveLength(2);
  expect(storedText()).not.toContain('"amount":1000');
});

it("keeps waiting captures through an app restart and sends them after the next unlock", async () => {
  const api = await signIn(people.clerk, "0712000003", (routes) =>
    routes.on("setup/revenue", [200, oneVehicle]),
  );
  api.on(PUT, "offline");
  await openRevenue();
  await captureAmount("KDA 482M, Enter revenue", "1000");
  await screen.findByLabelText("KDA 482M, KES 1,000, not sent yet");

  await screen.unmount();
  // Only what is in the Keychain survives the app closing.
  expect(storedText()).toContain('"amount":1000');
  api.on(PUT, [200, { id: "r-1", version: 1 }]);
  await startApp();
  await screen.findByText("Welcome back, Wanjiru");
  await typePin("4826");
  await screen.findByText("Hi Wanjiru");
  await waitFor(() => expect(api.sent(PUT)).toHaveLength(2));
  expect(api.sent(PUT)[1]).toEqual({
    amount: 1000,
    reason: null,
    note: null,
    version: null,
  });
  await waitFor(() => expect(storedText()).not.toContain('"amount":1000'));
});

it("sends captures kept before an admin changed the person's phone number, because the queue belongs to the account", async () => {
  const api = await signIn(people.clerk, "0712000021", (routes) =>
    routes.on("setup/revenue", [200, oneVehicle]),
  );
  api.on(PUT, "offline");
  await openRevenue();
  await captureAmount("KDA 482M, Enter revenue", "1000");
  await screen.findByLabelText("KDA 482M, KES 1,000, not sent yet");
  await screen.unmount();

  // The admin gave this person a new number; the phone signs them in under it.
  await trustPhone(people.clerk, "0712000022");
  api.on(PUT, [200, { id: "r-1", version: 1 }]);
  await startApp();
  await screen.findByText("Welcome back, Wanjiru");
  await typePin("4826");
  await screen.findByText("Hi Wanjiru");
  await waitFor(() => expect(api.sent(PUT)).toHaveLength(2));
  await waitFor(() => expect(storedText()).not.toContain('"amount":1000'));
});

const saved: RevenueCell = {
  date: TODAY,
  status: "amount",
  expected: 1000,
  amount: 900,
  reason: null,
  note: null,
  canEdit: true,
  editedAfterCapture: false,
  version: 3,
};

it("keeps a conflict until the person keeps the saved value", async () => {
  const api = await signIn(people.clerk, "0712000004", (routes) =>
    routes.on("setup/revenue", [200, oneVehicle]),
  );
  api.on(PUT, [
    409,
    {
      title: "This day already has a different record.",
      detail: "This day was changed after you opened it.",
      status: 409,
      current: saved,
    },
  ]);
  await openRevenue();
  await captureAmount("KDA 482M, Enter revenue", "1000");

  expect(await screen.findByText("Saved: KES 900")).toBeTruthy();
  expect(screen.getByText("Yours: KES 1,000")).toBeTruthy();
  await waitFor(() => expect(tabLabel()).toBe("Revenue, 1 conflict"));
  // A conflict is not sent again on its own.
  await act(async () =>
    require("expo-network").__emit({
      isConnected: true,
      isInternetReachable: true,
    }),
  );
  expect(api.sent(PUT)).toHaveLength(1);

  await fireEvent.press(
    screen.getByRole("button", { name: "Keep saved value" }),
  );
  await waitFor(() => expect(tabLabel()).toBe("Revenue"));
  expect(api.sent(PUT)).toHaveLength(1);
  expect(storedText()).not.toContain('"amount":1000');
});

it("offers no Replace with mine when the saved record is not the person's to change, as XCODE Web does", async () => {
  const api = await signIn(people.clerk, "0712000014", (routes) =>
    routes.on("setup/revenue", [200, oneVehicle]),
  );
  // The API says whether this person may change the saved record: a clerk may not change a past day.
  api.on(PUT, [
    409,
    {
      title: "This day already has a different record.",
      detail: "This day was changed after you opened it.",
      status: 409,
      current: { ...saved, canEdit: false },
    },
  ]);
  await openRevenue();
  await captureAmount("KDA 482M, Enter revenue", "1000");

  expect(await screen.findByText("Saved: KES 900")).toBeTruthy();
  expect(
    screen.getByText(
      "Your access does not include changing the saved record for this day.",
    ),
  ).toBeTruthy();
  expect(
    screen.queryByRole("button", { name: "Replace with mine" }),
  ).toBeNull();
  expect(screen.getByRole("button", { name: "Keep saved value" })).toBeTruthy();
});

it("replaces the saved value with mine over the version the API reported, even when a race left it out", async () => {
  const api = await signIn(people.clerk, "0712000005", (routes) =>
    routes.on("setup/revenue", [200, oneVehicle]),
  );
  // Two phones created the record at once: the 409 has no current record, so the phone reads the day again.
  api.on(PUT, (body) =>
    body.version === (2 as unknown as string)
      ? [200, { id: "r-1", version: 3 }]
      : [
          409,
          { title: "This day already has a different record.", status: 409 },
        ],
  );
  api.on(`setup/revenue?weekStart=${shiftDate(TODAY, -6)}&vehicleId=v-1`, [
    200,
    week(TODAY, shiftDate(TODAY, -6), [
      {
        id: "v-1",
        registration: "KDA 482M",
        days: { [TODAY]: { ...saved, amount: 700, version: 2 } },
      },
    ]),
  ]);
  await openRevenue();
  await captureAmount("KDA 482M, Enter revenue", "1000");

  expect(await screen.findByText("Saved: KES 700")).toBeTruthy();
  await fireEvent.press(
    screen.getByRole("button", { name: "Replace with mine" }),
  );
  await waitFor(() => expect(api.sent(PUT)).toHaveLength(2));
  expect(api.sent(PUT)[1]).toEqual({
    amount: 1000,
    reason: null,
    note: null,
    version: 2,
  });
  await waitFor(() => expect(tabLabel()).toBe("Revenue"));
});

it("opens on the earliest missing day and fills earlier days first", async () => {
  const api = await signIn(people.clerk, "0712000006", (routes) =>
    routes.on("setup/revenue", [
      200,
      week(TODAY, "2026-09-28", [
        { id: "v-1", registration: "KDA 482M", earliestMissing: "2026-09-28" },
      ]),
    ]),
  );
  api.on("setup/revenue/v-1/2026-09-28", "offline");
  api.on(PUT, "offline");
  await openRevenue();
  expect(await screen.findByText("Mon 28 Sep 2026")).toBeTruthy();

  // A later missing day opens on the earliest one.
  await fireEvent.press(screen.getByRole("button", { name: "Next day" }));
  expect(
    screen.getByRole("button", {
      name: "Earlier days are missing. Start with Mon 28 Sep 2026",
    }),
  ).toBeTruthy();
  await fireEvent.press(
    screen.getByRole("button", { name: "KDA 482M, Enter revenue" }),
  );
  expect(screen.getByText("Fill Mon 28 Sep 2026 first.")).toBeTruthy();
  expect(screen.getByText("Mon 28 Sep 2026. Expected KES 1,000")).toBeTruthy();
  await fireEvent.press(screen.getByRole("radio", { name: "Garage" }));
  await fireEvent.press(screen.getByRole("button", { name: "Save" }));

  // The same vehicle still misses the 29th, so capture goes straight on to it; the earlier day is waiting on the phone.
  expect(
    await screen.findByText("Tue 29 Sep 2026. Expected KES 1,000"),
  ).toBeTruthy();
  await fireEvent.changeText(screen.getByLabelText("Revenue amount"), "800");
  await fireEvent.press(screen.getByRole("button", { name: "Save" }));
  await waitFor(() => expect(tabLabel()).toBe("Revenue, 2 waiting to send"));
  expect(
    screen.queryByRole("button", { name: /^Earlier days are missing/ }),
  ).toBeNull();
});

it("works out the earliest missing day once per week and queue, not on every render", async () => {
  await signIn(people.clerk, "0712000041", (routes) =>
    routes.on("setup/revenue", [
      200,
      week(TODAY, "2026-09-28", [
        { id: "v-1", registration: "KDA 482M", earliestMissing: "2026-09-28" },
      ]),
    ]),
  );
  await openRevenue();
  expect(await screen.findByText("Mon 28 Sep 2026")).toBeTruthy();
  const worked = jest.mocked(earliestNeededDay).mock.calls.length;
  expect(worked).toBeGreaterThan(0);

  // Moving between days renders the screen again over the same week and queue.
  await fireEvent.press(screen.getByRole("button", { name: "Next day" }));
  expect(await screen.findByText("Tue 29 Sep 2026")).toBeTruthy();
  await fireEvent.press(screen.getByRole("button", { name: "Previous day" }));
  expect(await screen.findByText("Mon 28 Sep 2026")).toBeTruthy();
  expect(jest.mocked(earliestNeededDay).mock.calls.length).toBe(worked);
});

it("offers what the person may do: reasons with the no-earnings permission, Other with a short note, corrections with the cell's version", async () => {
  const api = await signIn(people.clerk, "0712000007", (routes) =>
    routes.on("setup/revenue", [200, oneVehicle]),
  );
  api.on(PUT, [200, { id: "r-1", version: 1 }]);
  await openRevenue();
  await fireEvent.press(
    await screen.findByRole("button", { name: "KDA 482M, Enter revenue" }),
  );
  await fireEvent.press(screen.getByRole("radio", { name: "Other" }));
  await fireEvent.press(screen.getByRole("button", { name: "Save" }));
  expect(screen.getByText("Say what happened.")).toBeTruthy();
  await fireEvent.changeText(
    screen.getByLabelText("What happened"),
    "x".repeat(100),
  );
  expect(screen.getByText("80 of 80 characters")).toBeTruthy();
  await fireEvent.press(screen.getByRole("button", { name: "Save" }));
  await waitFor(() =>
    expect(api.sent(PUT)).toEqual([
      { amount: null, reason: "Other", note: "x".repeat(80), version: null },
    ]),
  );
  await screen.unmount();

  // Capture without the no-earnings permission: an amount only.
  await signIn(
    { ...people.clerk, permissions: ["revenue.view", "revenue.capture"] },
    "0712000008",
    (routes) => routes.on("setup/revenue", [200, oneVehicle]),
  );
  await openRevenue();
  await fireEvent.press(
    await screen.findByRole("button", { name: "KDA 482M, Enter revenue" }),
  );
  expect(screen.queryByRole("radio", { name: "Garage" })).toBeNull();
  await fireEvent.press(screen.getByRole("button", { name: "Close" }));
  await screen.unmount();

  // Correcting without capture: missing days stay shut; a record opens only where the API allows it, and sends its version.
  const owner = await signIn(people.owner, "0733000009", (routes) =>
    routes.on("setup/revenue", [
      200,
      week(TODAY, "2026-09-28", [
        {
          id: "v-1",
          registration: "KDA 482M",
          days: {
            [TODAY]: {
              status: "amount",
              amount: 1000,
              canEdit: true,
              version: 4,
            },
          },
        },
        { id: "v-2", registration: "KCY 117T" },
        {
          id: "v-3",
          registration: "KDE 713L",
          days: {
            [TODAY]: {
              status: "reason",
              reason: "Garage",
              canEdit: false,
              version: 1,
            },
          },
        },
      ]),
    ]),
  );
  owner.on(PUT, [200, { id: "r-1", version: 5 }]);
  await openRevenue();
  expect(await screen.findByLabelText("KCY 117T, Missing")).toBeTruthy();
  expect(
    screen.queryByRole("button", { name: "KCY 117T, Missing" }),
  ).toBeNull();
  expect(screen.queryByRole("button", { name: "KDE 713L, Garage" })).toBeNull();
  await fireEvent.press(
    screen.getByRole("button", { name: "KDA 482M, KES 1,000" }),
  );
  expect(screen.getByLabelText("Revenue amount")).toHaveProp("value", "1000");
  await fireEvent.changeText(screen.getByLabelText("Revenue amount"), "1100");
  await fireEvent.press(screen.getByRole("button", { name: "Save" }));
  await waitFor(() =>
    expect(owner.sent(PUT)).toEqual([
      { amount: 1100, reason: null, note: null, version: 4 },
    ]),
  );
});

it("shows one vehicle's week with expected, actual and the difference for each day", async () => {
  const days = {
    "2026-09-28": {
      status: "amount" as const,
      amount: 1200,
      canEdit: false,
      version: 1,
    },
    [TODAY]: {
      status: "reason" as const,
      reason: "Garage",
      canEdit: true,
      version: 1,
    },
  };
  await signIn(people.clerk, "0712000010", (routes) => {
    routes.on("setup/revenue", [
      200,
      week(TODAY, "2026-09-28", [
        { id: "v-1", registration: "KDA 482M", days },
      ]),
    ]);
    routes.on("setup/revenue?weekStart=2026-09-28&vehicleId=v-1", [
      200,
      week(TODAY, "2026-09-28", [
        { id: "v-1", registration: "KDA 482M", days },
      ]),
    ]);
  });
  await openRevenue();
  await fireEvent.press(await screen.findByRole("button", { name: "Week" }));
  await fireEvent.press(
    await screen.findByRole("button", { name: /^KDA 482M, KES 0/ }),
  );
  expect(
    await screen.findByLabelText(
      "Mon 28: expected KES 1,000, KES 1,200, KES 200 above",
    ),
  ).toBeTruthy();
  expect(
    screen.getByRole("button", {
      name: "Tue 29: expected KES 1,000, Garage, KES 1,000 below",
    }),
  ).toBeTruthy();
  expect(
    screen.getByLabelText("Wed 30: expected KES 1,000, Not yet"),
  ).toBeTruthy();
  await fireEvent.press(
    screen.getByRole("button", { name: "Back to the week" }),
  );
  expect(
    await screen.findByRole("button", { name: "Previous week" }),
  ).toBeTruthy();
});

it("takes today from the organization's business date, never the phone's clock, and keeps it offline", async () => {
  // The phone's clock says July 2031; the organization's business date is 29 Feb 2024.
  jest.useFakeTimers({
    now: new Date("2031-07-04T09:00:00Z"),
    doNotFake: [
      "nextTick",
      "setImmediate",
      "clearImmediate",
      "setInterval",
      "clearInterval",
      "setTimeout",
      "clearTimeout",
      "queueMicrotask",
      "hrtime",
      "performance",
      "requestAnimationFrame",
      "cancelAnimationFrame",
      "requestIdleCallback",
      "cancelIdleCallback",
    ],
  });
  try {
    const leapDay = "2024-02-29";
    const appearance = {
      organizationName: "Demo Fleet",
      settingsVersion: 1,
      businessDate: leapDay,
      branding: {
        displayName: "XCODE",
        logoAlt: "",
        primary: "",
        secondary: "",
        accent: "",
        logo: null,
      },
      formats: {
        locale: "en-GB",
        timeZone: "Africa/Nairobi",
        datePattern: "medium",
        hour12: false,
        currency: "KES",
        useGroupping: true,
        numberDecimals: 2,
      },
      themeMode: "system",
      reducedMotion: false,
      fontScale: 1,
    };
    const api = await signIn(
      {
        ...people.clerk,
        permissions: [...people.clerk.permissions, "dash.revenue"],
      },
      "0712000011",
      (routes) => {
        routes.on("setup/appearance", [200, appearance]);
        routes.on("setup/revenue", [
          200,
          week(leapDay, "2024-02-26", [
            { id: "v-1", registration: "KDA 482M" },
          ]),
        ]);
      },
    );
    expect(await screen.findByText("Today, 29 Feb 2024")).toBeTruthy();
    // Missing revenue days always covers the month so far, up to yesterday: today is not a gap before it is captured.
    expect(
      screen.getByText("1 to 28 Feb 2024. No record and no reason."),
    ).toBeTruthy();
    expect(screen.getByText("Your vehicles, 29 Feb 2024")).toBeTruthy();
    await fireEvent.press(screen.getByRole("button", { name: "This week" }));
    expect(screen.getByText("This week, 26 Feb to 3 Mar 2024")).toBeTruthy();

    await openRevenue();
    expect(await screen.findByText("Thu 29 Feb 2024")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Next day" })).toBeDisabled();

    // Offline, the business date saved with the appearance still applies.
    await fireEvent.press(screen.getByRole("tab", { name: "Home" }));
    await fireEvent.press(screen.getByRole("button", { name: "Lock app" }));
    api.on("auth/unlock", "offline");
    await typePin("4826");
    await screen.findByText(
      "No internet. You are seeing what this phone saved at your last sign in.",
    );
    expect(screen.getByText("Today, 29 Feb 2024")).toBeTruthy();
    // Revenue cards say they need a connection rather than showing zeros.
    expect(
      screen.getAllByText("Connect to the internet to see revenue figures."),
    ).toHaveLength(3);
    expect(screen.queryByText("0 captured")).toBeNull();
  } finally {
    jest.useRealTimers();
  }
});

it("offers Replace with mine only for a day the person may still change", async () => {
  // A clerk captures and changes today only; an earlier day needs "Correct revenue after the day".
  const yesterday = "2026-09-28";
  const api = await signIn(people.clerk, "0712000012", (routes) =>
    routes.on("setup/revenue", [
      200,
      week(TODAY, "2026-09-28", [
        { id: "v-1", registration: "KDA 482M", earliestMissing: yesterday },
      ]),
    ]),
  );
  api.on(`setup/revenue/v-1/${yesterday}`, [
    409,
    {
      title: "This day already has a different record.",
      status: 409,
      current: { ...saved, date: yesterday },
    },
  ]);
  await openRevenue();
  await captureAmount("KDA 482M, Enter revenue", "1000");

  expect(await screen.findByText("Saved: KES 900")).toBeTruthy();
  expect(
    screen.getByText(
      "Changing a day after it has passed needs Correct revenue after the day.",
    ),
  ).toBeTruthy();
  expect(
    screen.queryByRole("button", { name: "Replace with mine" }),
  ).toBeNull();
  await fireEvent.press(
    screen.getByRole("button", { name: "Keep saved value" }),
  );
  await waitFor(() => expect(tabLabel()).toBe("Revenue"));
  expect(api.sent(`setup/revenue/v-1/${yesterday}`)).toHaveLength(1);
});

it("says no vehicle was in service on a day before they joined, rather than that there are none", async () => {
  const joinedToday = week(TODAY, "2026-09-28", [
    { id: "v-1", registration: "KDA 482M" },
  ]);
  joinedToday.vehicles[0].days = joinedToday.vehicles[0].days.filter(
    (cell) => cell.date >= TODAY,
  );
  await signIn(people.clerk, "0712000014", (routes) =>
    routes.on("setup/revenue", [200, joinedToday]),
  );
  await openRevenue();
  expect(
    await screen.findByRole("button", { name: "KDA 482M, Enter revenue" }),
  ).toBeTruthy();
  await fireEvent.press(screen.getByRole("button", { name: "Previous day" }));
  expect(await screen.findByText("No vehicles on this day")).toBeTruthy();
  expect(screen.queryByText("No vehicles in your view")).toBeNull();
});

it("loads the week again with Try again after it failed", async () => {
  const api = await signIn(people.clerk, "0712000013", (routes) =>
    routes.on("setup/revenue", [
      500,
      {
        title: "An error occurred while processing your request.",
        status: 500,
      },
    ]),
  );
  await openRevenue();
  expect(
    await screen.findByText(
      "Something went wrong on the server. Try again in a moment.",
    ),
  ).toBeTruthy();
  api.on("setup/revenue", [200, oneVehicle]);
  await fireEvent.press(screen.getByRole("button", { name: "Try again" }));
  expect(
    await screen.findByRole("button", { name: "KDA 482M, Enter revenue" }),
  ).toBeTruthy();
  expect(
    screen.queryByText(
      "Something went wrong on the server. Try again in a moment.",
    ),
  ).toBeNull();
});

it("goes back online when the connection returns after an offline unlock", async () => {
  const api = await signIn(
    {
      ...people.clerk,
      permissions: [...people.clerk.permissions, "dash.revenue"],
    },
    "0712000014",
    (routes) => {
      routes.on("setup/revenue/dashboard?period=today", [
        200,
        {
          period: "today",
          from: TODAY,
          through: TODAY,
          businessDate: TODAY,
          revenue: 1500,
          expected: 2000,
          percent: 75,
          capturedToday: 1,
          vehiclesToday: 2,
          missingDays: 0,
          missingVehicles: 0,
          editedRecords: 0,
        },
      ]);
      routes.on("setup/revenue/dashboard?period=month", [
        200,
        {
          period: "month",
          from: "2026-09-01",
          through: TODAY,
          businessDate: TODAY,
          revenue: 1500,
          expected: 2000,
          percent: 75,
          capturedToday: 1,
          vehiclesToday: 2,
          missingDays: 0,
          missingVehicles: 0,
          editedRecords: 0,
        },
      ]);
    },
  );
  expect(await screen.findByText("1 of 2 captured")).toBeTruthy();
  await fireEvent.press(screen.getByRole("button", { name: "Lock app" }));
  api.on("auth/unlock", "offline");
  await typePin("4826");
  await screen.findByText(
    "No internet. You are seeing what this phone saved at your last sign in.",
  );
  expect(screen.queryByText("1 of 2 captured")).toBeNull();

  // The connection returns: the API confirms the session and the figures load again, without another unlock.
  await act(async () =>
    require("expo-network").__emit({
      isConnected: true,
      isInternetReachable: true,
    }),
  );
  expect(await screen.findByText("1 of 2 captured")).toBeTruthy();
  expect(
    screen.queryByText(
      "No internet. You are seeing what this phone saved at your last sign in.",
    ),
  ).toBeNull();
});

const SHORT_DAY = "2024-02-29";
const shortDates = {
  organizationName: "Demo Fleet",
  settingsVersion: 1,
  businessDate: SHORT_DAY,
  branding: {
    displayName: "XCODE",
    logoAlt: "",
    primary: "",
    secondary: "",
    accent: "",
    logo: null,
  },
  formats: {
    locale: "en-GB",
    timeZone: "Africa/Nairobi",
    datePattern: "short",
    hour12: false,
    currency: "KES",
    useGroupping: true,
    numberDecimals: 2,
  },
  themeMode: "system",
  reducedMotion: false,
  fontScale: 1,
};

it("shows every revenue date in the organization's date pattern", async () => {
  await signIn(
    {
      ...people.clerk,
      permissions: [...people.clerk.permissions, "dash.revenue"],
    },
    "0712000031",
    (routes) => {
      routes.on("setup/appearance", [200, shortDates]);
      routes.on("setup/revenue", [
        200,
        week(SHORT_DAY, "2024-02-26", [
          {
            id: "v-1",
            registration: "KDA 482M",
            earliestMissing: "2024-02-27",
          },
        ]),
      ]);
    },
  );
  expect(await screen.findByText("Today, 29/02/2024")).toBeTruthy();
  expect(
    screen.getByText("01/02/2024 to 28/02/2024. No record and no reason."),
  ).toBeTruthy();
  expect(screen.getByText("Your vehicles, 29/02/2024")).toBeTruthy();
  await fireEvent.press(screen.getByRole("button", { name: "This week" }));
  expect(screen.getByText("This week, 26/02/2024 to 03/03/2024")).toBeTruthy();

  await openRevenue();
  expect(await screen.findByText("Tue 27/02/2024")).toBeTruthy();
  await fireEvent.press(screen.getByRole("button", { name: "Next day" }));
  expect(
    screen.getByRole("button", {
      name: "Earlier days are missing. Start with Tue 27/02/2024",
    }),
  ).toBeTruthy();
  await fireEvent.press(
    screen.getByRole("button", { name: "KDA 482M, Enter revenue" }),
  );
  expect(screen.getByText("Fill Tue 27/02/2024 first.")).toBeTruthy();
  expect(screen.getByText("Tue 27/02/2024. Expected KES 1,000")).toBeTruthy();
  await fireEvent.press(screen.getByRole("button", { name: "Close" }));

  await fireEvent.press(screen.getByRole("button", { name: "Week" }));
  expect(await screen.findByText("26/02/2024 to 03/03/2024")).toBeTruthy();
});

it("words a blocked capture in the organization's date pattern and keeps the earlier day in storage", async () => {
  const api = await signIn(people.clerk, "0712000032", (routes) => {
    routes.on("setup/appearance", [200, shortDates]);
    routes.on("setup/revenue", [
      200,
      week(SHORT_DAY, "2024-02-26", [{ id: "v-1", registration: "KDA 482M" }]),
    ]);
  });
  api.on(`setup/revenue/v-1/${SHORT_DAY}`, [
    400,
    {
      title: "Invalid setup change",
      detail: "Record 2024-02-20 before this date first.",
      earliestMissing: "2024-02-20",
    },
  ]);
  await openRevenue();
  await captureAmount("KDA 482M, Enter revenue", "1000");
  expect(await screen.findByText("Capture 20/02/2024 first.")).toBeTruthy();
  expect(screen.getByRole("button", { name: "Open 20/02/2024" })).toBeTruthy();
  expect(storedText()).toContain('"earliestMissing":"2024-02-20"');
  expect(storedText()).not.toContain("Capture 20 Feb 2024 first.");
});

it("shows a blocked capture stored with its sentence already written in the organization's pattern", async () => {
  const items = require("expo-secure-store").__items as Map<string, string>;
  const key = `xcode.revenue-queue.${people.clerk.userId}`;
  items.set(key, JSON.stringify({ used: "1" }));
  items.set(
    `${key}.0`,
    JSON.stringify({
      vehicleId: "v-1",
      registration: "KDA 482M",
      date: SHORT_DAY,
      amount: 1000,
      reason: null,
      note: null,
      version: null,
      state: "blocked",
      message: "Capture 20 Feb 2024 first.",
      earliestMissing: "2024-02-20",
      current: null,
      queuedAt: 1,
      attempts: 1,
      lastAttemptAt: 1,
    }),
  );
  await signIn(people.clerk, "0712000033", (routes) => {
    routes.on(`setup/revenue/v-1/${SHORT_DAY}`, "offline");
    routes.on("setup/appearance", [200, shortDates]);
    routes.on("setup/revenue", [
      200,
      week(SHORT_DAY, "2024-02-26", [{ id: "v-1", registration: "KDA 482M" }]),
    ]);
  });
  await openRevenue();
  expect(await screen.findByText("Capture 20/02/2024 first.")).toBeTruthy();
  expect(screen.queryByText("Capture 20 Feb 2024 first.")).toBeNull();
  expect(screen.getByRole("button", { name: "Open 20/02/2024" })).toBeTruthy();
});

it("keeps what a stored blocked capture says when it names no earlier day", async () => {
  const items = require("expo-secure-store").__items as Map<string, string>;
  const key = `xcode.revenue-queue.${people.clerk.userId}`;
  items.set(key, JSON.stringify({ used: "1" }));
  items.set(
    `${key}.0`,
    JSON.stringify({
      vehicleId: "v-1",
      registration: "KDA 482M",
      date: SHORT_DAY,
      amount: 1000,
      reason: null,
      note: null,
      version: null,
      state: "blocked",
      message: "Waiting for an earlier day.",
      earliestMissing: null,
      current: null,
      queuedAt: 1,
      attempts: 1,
      lastAttemptAt: 1,
    }),
  );
  await signIn(people.clerk, "0712000034", (routes) => {
    routes.on(`setup/revenue/v-1/${SHORT_DAY}`, "offline");
    routes.on("setup/appearance", [200, shortDates]);
    routes.on("setup/revenue", [
      200,
      week(SHORT_DAY, "2024-02-26", [{ id: "v-1", registration: "KDA 482M" }]),
    ]);
  });
  await openRevenue();
  expect(await screen.findByText("Waiting for an earlier day.")).toBeTruthy();
});
