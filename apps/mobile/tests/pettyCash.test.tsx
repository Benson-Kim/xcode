import {
  fireEvent,
  screen,
  waitFor,
  within,
} from "@testing-library/react-native";

import {
  PETTY_CASH_AMOUNT_ERROR,
  PETTY_CASH_UNITS_ERROR,
} from "@xcode/shared/pettyCash";

import {
  catalog,
  fakeApi,
  pettyEntry,
  pettyOptions,
  pettyOverview,
  pettyPage,
  pettyPermissions,
  people,
  tokens,
} from "./fakeApi";
import { startApp, trustPhone, typePin } from "./helpers";

const DAY = "2026-09-29";
const ENTRIES = `setup/pettycash/entries?from=${DAY}&to=${DAY}&holderId=u-brian`;
const OWN = `setup/pettycash/overview?date=${DAY}&period=day&holderId=u-brian`;
const WAITING = "setup/pettycash/entries?status=waiting";
const OPTIONS = `setup/pettycash/options?date=${DAY}`;

const randomUUID = jest.spyOn(require("expo-crypto"), "randomUUID");

async function signIn(
  permissions: string[],
  setup: (api: ReturnType<typeof fakeApi>) => void,
  tab = "Spend",
) {
  const who = { ...people.manager, permissions };
  await trustPhone(who, "0700111555");
  const api = fakeApi();
  api.on("auth/unlock", [200, tokens(2)]);
  api.on("auth/session", [200, who]);
  api.on("setup/access/catalog", [200, catalog]);
  setup(api);
  await startApp();
  await screen.findByText(`Welcome back, ${who.firstName}`);
  await typePin("4826");
  await screen.findByText(`Hi ${who.firstName}`);
  if (tab !== "Home")
    await fireEvent.press(screen.getByRole("tab", { name: tab }));
  return api;
}

const spender = (
  api: ReturnType<typeof fakeApi>,
  entries: unknown[] = [pettyEntry()],
  overview = pettyOverview(),
) => {
  api.on("setup/pettycash/overview", [200, overview]);
  api.on(OWN, [200, overview]);
  api.on(ENTRIES, [200, pettyPage(entries)]);
  api.on(OPTIONS, [200, pettyOptions]);
};

const bodies = (
  api: ReturnType<typeof fakeApi>,
  path: string,
  method: string,
) =>
  api.calls
    .filter((call) => call.path === path && call.method === method)
    .map((call) => call.body);

const tabs = () =>
  screen.getAllByRole("tab").map((tab) => tab.props.accessibilityLabel);

describe("Spend tab", () => {
  it.each([
    ["pettycash.spend", { canSpend: true }, "Entries"],
    [
      "pettycash.view_all",
      { canSpend: false, holderId: null, canViewAll: true },
      "No floats yet.",
    ],
    [
      "pettycash.approve_item",
      { canSpend: false, holderId: null, canApproveItem: true },
      "Nothing is waiting for approval.",
    ],
    [
      "pettycash.issue",
      { canSpend: false, holderId: null, canIssue: true },
      "Give cash",
    ],
  ])(
    "shows Petty cash to someone holding %s",
    async (permission, flags, expected) => {
      const api = await signIn([permission], (setup) => {
        setup.on("setup/pettycash/overview", [
          200,
          pettyOverview({ permissions: pettyPermissions(flags), floats: [] }),
        ]);
        setup.on(OWN, [
          200,
          pettyOverview({ permissions: pettyPermissions(flags), floats: [] }),
        ]);
        setup.on(ENTRIES, [200, pettyPage([])]);
        setup.on(WAITING, [200, pettyPage([])]);
        setup.on(OPTIONS, [200, pettyOptions]);
      });
      expect(tabs()).toEqual(["Home", "Spend", "More"]);
      expect(
        await screen.findByRole("header", { name: "Petty cash" }),
      ).toBeTruthy();
      expect((await screen.findAllByText(expected)).length).toBeGreaterThan(0);
      expect(api.sent("setup/pettycash/overview")).toHaveLength(1);
    },
  );

  it("hides Petty cash from someone with no petty cash permission", async () => {
    await signIn(["revenue.view"], () => {}, "Home");
    expect(tabs()).toEqual(["Home", "Revenue", "More"]);
    expect(screen.queryByRole("tab", { name: "Spend" })).toBeNull();
  });
});

describe("My float", () => {
  it("shows the balance, the day's four figures and the day's entries", async () => {
    await signIn(["pettycash.spend"], (api) =>
      spender(api, [
        pettyEntry(),
        pettyEntry({
          id: "entry-2",
          expenseItemName: "Diesel",
          units: 1,
          unitAmount: 800,
          total: 800,
          status: "sentBack",
          sentBackNote: "Photo of receipt missing",
        }),
      ]),
    );
    expect((await screen.findAllByText("KES 4,500")).length).toBe(2);
    expect(
      screen.getByText("1 entry, KES 1,500, waiting for approval"),
    ).toBeTruthy();
    for (const label of [
      "Opening cash balance, KES 5,000",
      "Money out, KES 1,500",
      "Cash received, KES 1,000",
      "Closing cash balance, KES 4,500",
    ])
      expect(screen.getByLabelText(label)).toBeTruthy();

    expect(screen.getByText("KDA 482M, Tyre repair")).toBeTruthy();
    expect(screen.getByText("2 x KES 750")).toBeTruthy();
    expect(screen.getAllByText("KES 1,500").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("Waiting")).toBeTruthy();
    expect(screen.getByText("KDA 482M, Diesel")).toBeTruthy();
    expect(screen.getByText("Sent back")).toBeTruthy();
    expect(
      screen.getByText("Sent back: Photo of receipt missing"),
    ).toBeTruthy();
  });

  it("says a float is negative", async () => {
    await signIn(["pettycash.spend"], (api) =>
      spender(
        api,
        [],
        pettyOverview({
          figures: {
            openingBalance: 200,
            cashReceived: 0,
            expenses: 500,
            creditNotes: 0,
            moneyOut: 500,
            closingBalance: -300,
          },
          floats: [{ ...pettyOverview().floats[0], balance: -300 }],
        }),
      ),
    );
    expect((await screen.findAllByText("KES -300")).length).toBe(2);
    expect(
      screen.getByLabelText("Closing cash balance, KES -300"),
    ).toBeTruthy();
  });

  it("steps back a day and forward again, never past the business date", async () => {
    const api = await signIn(["pettycash.spend"], (setup) => {
      spender(setup);
      setup.on(
        "setup/pettycash/overview?date=2026-09-28&period=day&holderId=u-brian",
        [
          200,
          pettyOverview({
            date: "2026-09-28",
            from: "2026-09-28",
            to: "2026-09-28",
            figures: { ...pettyOverview().figures, openingBalance: 3000 },
          }),
        ],
      );
      setup.on(
        "setup/pettycash/entries?from=2026-09-28&to=2026-09-28&holderId=u-brian",
        [200, pettyPage([])],
      );
    });
    await screen.findAllByText("KES 4,500");
    expect(screen.getByRole("button", { name: "Next day" })).toBeDisabled();

    await fireEvent.press(screen.getByRole("button", { name: "Previous day" }));
    await screen.findByLabelText("Opening cash balance, KES 3,000");
    await screen.findByText("Nothing recorded on this day.");
    expect(
      api.sent(
        "setup/pettycash/overview?date=2026-09-28&period=day&holderId=u-brian",
      ),
    ).toHaveLength(1);
    expect(screen.getByRole("button", { name: "Next day" })).not.toBeDisabled();

    await fireEvent.press(screen.getByRole("button", { name: "Next day" }));
    await screen.findByLabelText("Opening cash balance, KES 5,000");
    expect(screen.getByRole("button", { name: "Next day" })).toBeDisabled();
  });

  it("offers Edit and Remove only where the entry's flags allow", async () => {
    await signIn(["pettycash.spend"], (api) =>
      spender(api, [
        pettyEntry(),
        pettyEntry({
          id: "entry-2",
          expenseItemName: "Diesel",
          status: "approved",
          canEdit: false,
          canRemove: false,
        }),
      ]),
    );
    await screen.findByText("KDA 482M, Tyre repair");
    expect(
      screen.getByRole("button", { name: "Edit KDA 482M, Tyre repair" }),
    ).toBeTruthy();
    expect(
      screen.getByRole("button", { name: "Remove KDA 482M, Tyre repair" }),
    ).toBeTruthy();
    expect(
      screen.queryByRole("button", { name: "Edit KDA 482M, Diesel" }),
    ).toBeNull();
    expect(
      screen.queryByRole("button", { name: "Remove KDA 482M, Diesel" }),
    ).toBeNull();
    expect(screen.queryByRole("button", { name: /^Approve/ })).toBeNull();
  });
});

describe("My float by week", () => {
  const WEEK_OWN = `setup/pettycash/overview?date=${DAY}&period=week&holderId=u-brian`;
  const WEEK_ENTRIES =
    "setup/pettycash/entries?from=2026-09-28&to=2026-10-04&holderId=u-brian";
  const weekOverview = (over: Record<string, unknown> = {}) =>
    pettyOverview({
      period: "week",
      from: "2026-09-28",
      to: "2026-10-04",
      figures: {
        openingBalance: 3000,
        cashReceived: 2000,
        expenses: 1100,
        creditNotes: 400,
        moneyOut: 1500,
        closingBalance: 3500,
      },
      ...over,
    });
  const weekSetup = (api: ReturnType<typeof fakeApi>) => {
    spender(api);
    api.on(WEEK_OWN, [200, weekOverview()]);
    api.on(WEEK_ENTRIES, [
      200,
      pettyPage([
        pettyEntry({ id: "entry-1", date: "2026-09-29" }),
        pettyEntry({
          id: "entry-2",
          expenseItemName: "Diesel",
          date: "2026-09-30",
        }),
      ]),
    ]);
  };

  it("asks for the week and its entries, and says the figures cover this week", async () => {
    const api = await signIn(["pettycash.spend"], weekSetup);
    await screen.findByLabelText("Opening cash balance, KES 5,000");
    expect(
      screen.getByRole("button", { name: "Day", selected: true }),
    ).toBeTruthy();
    expect(
      screen.getByRole("button", { name: "Week", selected: false }),
    ).toBeTruthy();

    await fireEvent.press(screen.getByRole("button", { name: "Week" }));
    await screen.findByLabelText("Money out in the week, KES 1,500");
    expect(
      screen.getByRole("button", { name: "Week", selected: true }),
    ).toBeTruthy();
    expect(
      screen.getByLabelText("Cash received in the week, KES 2,000"),
    ).toBeTruthy();
    expect(
      screen.getByLabelText("Opening cash balance, start of week, KES 3,000"),
    ).toBeTruthy();
    expect(
      screen.getByLabelText("Closing cash balance, end of week, KES 3,500"),
    ).toBeTruthy();
    expect(screen.queryByLabelText(/Today/)).toBeNull();
    expect(screen.getByText("28 Sep to 4 Oct 2026")).toBeTruthy();
    expect(api.sent(WEEK_OWN)).toHaveLength(1);
    expect(api.sent(WEEK_ENTRIES)).toHaveLength(1);

    await fireEvent.press(screen.getByRole("button", { name: "Day" }));
    await screen.findByLabelText("Money out, KES 1,500");
    expect(screen.getByRole("button", { name: "Next day" })).toBeDisabled();
  });

  it("moves a week at a time and closes next once the next week would start after the business date", async () => {
    const api = await signIn(["pettycash.spend"], (setup) => {
      weekSetup(setup);
      setup.on(
        "setup/pettycash/overview?date=2026-09-22&period=week&holderId=u-brian",
        [
          200,
          weekOverview({
            date: "2026-09-22",
            from: "2026-09-21",
            to: "2026-09-27",
          }),
        ],
      );
      setup.on(
        "setup/pettycash/entries?from=2026-09-21&to=2026-09-27&holderId=u-brian",
        [200, pettyPage([])],
      );
    });
    await screen.findByLabelText("Opening cash balance, KES 5,000");
    await fireEvent.press(screen.getByRole("button", { name: "Week" }));
    await screen.findByText("28 Sep to 4 Oct 2026");
    expect(screen.getByRole("button", { name: "Next week" })).toBeDisabled();

    await fireEvent.press(
      screen.getByRole("button", { name: "Previous week" }),
    );
    await screen.findByText("21 to 27 Sep 2026");
    await screen.findByText("Nothing recorded in this week.");
    expect(
      api.sent(
        "setup/pettycash/overview?date=2026-09-22&period=week&holderId=u-brian",
      ),
    ).toHaveLength(1);
    expect(
      api.sent(
        "setup/pettycash/entries?from=2026-09-21&to=2026-09-27&holderId=u-brian",
      ),
    ).toHaveLength(1);
    expect(
      screen.getByRole("button", { name: "Next week" }),
    ).not.toBeDisabled();

    await fireEvent.press(screen.getByRole("button", { name: "Next week" }));
    await screen.findByText("28 Sep to 4 Oct 2026");
    expect(screen.getByRole("button", { name: "Next week" })).toBeDisabled();
  });

  it("starts the week on the organization's first day of the week", async () => {
    const sunday = {
      organizationName: "Demo Fleet",
      settingsVersion: 4,
      branding: {
        displayName: "Demo Fleet",
        logoAlt: "Demo Fleet",
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
      },
      themeMode: "system",
      reducedMotion: true,
      fontScale: 1,
    };
    const api = await signIn(["pettycash.spend"], (setup) => {
      spender(setup);
      setup.on("setup/appearance", [200, { ...sunday, businessDate: DAY }]);
      setup.on(WEEK_OWN, [
        200,
        weekOverview({ from: "2026-09-27", to: "2026-10-03" }),
      ]);
      setup.on(
        "setup/pettycash/entries?from=2026-09-27&to=2026-10-03&holderId=u-brian",
        [200, pettyPage([])],
      );
    });
    await screen.findByLabelText("Opening cash balance, KES 5,000");
    await fireEvent.press(screen.getByRole("button", { name: "Week" }));
    expect(await screen.findByText("27 Sep to 3 Oct 2026")).toBeTruthy();
    await waitFor(() =>
      expect(
        api.sent(
          "setup/pettycash/entries?from=2026-09-27&to=2026-10-03&holderId=u-brian",
        ),
      ).toHaveLength(1),
    );
  });

  it("shows each entry's date in week view only", async () => {
    await signIn(["pettycash.spend"], weekSetup);
    await screen.findByText("KDA 482M, Tyre repair");
    expect(screen.getAllByText("29 Sep 2026")).toHaveLength(1);

    await fireEvent.press(screen.getByRole("button", { name: "Week" }));
    await screen.findByText("30 Sep 2026");
    expect(screen.getAllByText("29 Sep 2026")).toHaveLength(1);
    expect(screen.getByText("28 Sep to 4 Oct 2026")).toBeTruthy();
  });

  it("does not offer Approve day in week view and keeps the period when the date moves", async () => {
    const approver = pettyOverview({
      permissions: pettyPermissions({
        canApproveItem: true,
        canApproveDay: true,
      }),
    });
    const api = await signIn(
      ["pettycash.spend", "pettycash.approve_item", "pettycash.approve_day"],
      (setup) => {
        weekSetup(setup);
        setup.on("setup/pettycash/overview", [200, approver]);
        setup.on(WEEK_OWN, [
          200,
          weekOverview({ permissions: approver.permissions }),
        ]);
        setup.on(
          "setup/pettycash/overview?date=2026-09-22&period=week&holderId=u-brian",
          [
            200,
            weekOverview({
              date: "2026-09-22",
              from: "2026-09-21",
              to: "2026-09-27",
            }),
          ],
        );
        setup.on(
          "setup/pettycash/entries?from=2026-09-21&to=2026-09-27&holderId=u-brian",
          [200, pettyPage([])],
        );
        setup.on(WAITING, [200, pettyPage([pettyEntry({ canReview: true })])]);
      },
    );
    await screen.findByLabelText("Opening cash balance, KES 5,000");
    await fireEvent.press(screen.getByRole("button", { name: "Week" }));
    await screen.findByLabelText("Money out in the week, KES 1,500");
    expect(screen.queryByRole("button", { name: /^Approve day/ })).toBeNull();

    await fireEvent.press(
      screen.getByRole("button", { name: "Previous week" }),
    );
    await screen.findByLabelText("Money out in the week, KES 1,500");
    expect(
      screen.getByRole("button", { name: "Week", selected: true }),
    ).toBeTruthy();
    expect(
      api.sent(
        "setup/pettycash/overview?date=2026-09-22&period=week&holderId=u-brian",
      ),
    ).toHaveLength(1);
    expect(screen.queryByRole("button", { name: /^Approve day/ })).toBeNull();
  });
});

describe("Entry units", () => {
  it("shows units as entered, with up to three decimals and grouping", async () => {
    await signIn(["pettycash.spend"], (api) =>
      spender(api, [
        pettyEntry({ id: "e1", units: 11.875, unitAmount: 182.4, total: 2166 }),
        pettyEntry({
          id: "e2",
          expenseItemName: "Oil",
          units: 4.5,
          unitAmount: 100,
          total: 450,
        }),
        pettyEntry({
          id: "e3",
          expenseItemName: "Washers",
          units: 1001,
          unitAmount: 2,
          total: 2002,
        }),
      ]),
    );
    expect(await screen.findByText("11.875 x KES 182.40")).toBeTruthy();
    expect(screen.getByText("4.5 x KES 100")).toBeTruthy();
    expect(screen.getByText("1,001 x KES 2")).toBeTruthy();
  });
});

async function pick(label: string, option: string) {
  await fireEvent.press(
    await screen.findByRole("button", { name: new RegExp(`^${label}, `) }),
  );
  await fireEvent.press(await screen.findByRole("radio", { name: option }));
}

describe("My float with every float visible", () => {
  it("asks for the person's own float and shows its figures, not the total of all floats", async () => {
    const others = {
      ...pettyOverview().floats[0],
      holderId: "u-grace",
      name: "Grace Njeri",
      balance: 99000,
    };
    const both = [pettyOverview().floats[0], others];
    const everyone = pettyOverview({
      permissions: pettyPermissions({ canViewAll: true }),
      figures: {
        ...pettyOverview().figures,
        openingBalance: 77000,
        closingBalance: 88000,
      },
      floats: both,
    });
    const api = await signIn(
      ["pettycash.spend", "pettycash.view_all"],
      (setup) => {
        setup.on("setup/pettycash/overview", [200, everyone]);
        setup.on(OWN, [
          200,
          pettyOverview({
            permissions: pettyPermissions({ canViewAll: true }),
            floats: both,
          }),
        ]);
        setup.on(ENTRIES, [200, pettyPage([pettyEntry()])]);
      },
    );
    expect((await screen.findAllByText("KES 4,500")).length).toBe(2);
    expect(
      screen.getByLabelText("Opening cash balance, KES 5,000"),
    ).toBeTruthy();
    expect(screen.queryByText(/99,000|77,000|88,000/)).toBeNull();
    expect(api.sent(OWN)).toHaveLength(1);
    expect(api.sent(ENTRIES)).toHaveLength(1);
    expect(
      api.calls.filter(
        (call) =>
          call.path.startsWith("setup/pettycash/overview?") &&
          !call.path.includes("holderId=u-brian"),
      ),
    ).toHaveLength(0);

    await fireEvent.press(screen.getByRole("button", { name: "All floats" }));
    expect(await screen.findByText("KES 99,000")).toBeTruthy();
  });
});

describe("Record expense", () => {
  async function openForm(api: ReturnType<typeof fakeApi>) {
    await fireEvent.press(
      await screen.findByRole("button", { name: "Record expense" }),
    );
    await screen.findByRole("header", { name: "Record expense" });
    await screen.findByRole("button", { name: "Vehicle, not chosen" });
    expect(api.sent(OPTIONS)).toHaveLength(1);
  }

  it("rejects an empty form, a zero amount and bad units, and sends nothing", async () => {
    const api = await signIn(["pettycash.spend"], spender);
    await openForm(api);

    await fireEvent.press(screen.getByRole("button", { name: "Save expense" }));
    expect(await screen.findByText("Choose a vehicle.")).toBeTruthy();
    expect(screen.getByText("Choose an item.")).toBeTruthy();
    expect(screen.getByText(PETTY_CASH_AMOUNT_ERROR)).toBeTruthy();

    await pick("Vehicle", "KDA 482M, North Star");
    await pick("Item", "Tyre repair, Repairs");
    await fireEvent.changeText(screen.getByLabelText("Amount each"), "0");
    await fireEvent.changeText(screen.getByLabelText("Units"), "0");
    await fireEvent.press(screen.getByRole("button", { name: "Save expense" }));
    expect(await screen.findByText(PETTY_CASH_UNITS_ERROR)).toBeTruthy();
    expect(screen.getByText(PETTY_CASH_AMOUNT_ERROR)).toBeTruthy();
    expect(screen.queryByText("Choose a vehicle.")).toBeNull();

    await fireEvent.changeText(screen.getByLabelText("Units"), "1.2345");
    await fireEvent.press(screen.getByRole("button", { name: "Save expense" }));
    expect(await screen.findByText(PETTY_CASH_UNITS_ERROR)).toBeTruthy();
    expect(bodies(api, "setup/pettycash/entries", "POST")).toHaveLength(0);
  });

  it("uses a keyboard with a decimal point for units", async () => {
    const api = await signIn(["pettycash.spend"], spender);
    await openForm(api);
    expect(screen.getByLabelText("Units").props.keyboardType).toBe(
      "decimal-pad",
    );
  });

  it.each([
    ["4.5", 4.5],
    ["11.875", 11.875],
    ["1001", 1001],
  ])("accepts %s units and sends %s as a number", async (typed, sent) => {
    const api = await signIn(["pettycash.spend"], spender);
    api.on("setup/pettycash/entries", [
      200,
      { id: "x", version: 1, status: "waiting", balance: 1 },
    ]);
    await openForm(api);
    await pick("Vehicle", "KDA 482M, North Star");
    await pick("Item", "Tyre repair, Repairs");
    await fireEvent.changeText(screen.getByLabelText("Units"), typed);
    await fireEvent.changeText(screen.getByLabelText("Amount each"), "100");
    await fireEvent.press(screen.getByRole("button", { name: "Save expense" }));
    await waitFor(() =>
      expect(bodies(api, "setup/pettycash/entries", "POST")).toHaveLength(1),
    );
    expect(bodies(api, "setup/pettycash/entries", "POST")[0].units).toBe(sent);
    expect(screen.queryByText(PETTY_CASH_UNITS_ERROR)).toBeNull();
  });

  it("shows the exact live total for fractional units", async () => {
    const api = await signIn(["pettycash.spend"], spender);
    await openForm(api);
    await fireEvent.changeText(screen.getByLabelText("Units"), "11.875");
    await fireEvent.changeText(screen.getByLabelText("Amount each"), "182.40");
    expect(await screen.findByText("Total KES 2,166")).toBeTruthy();
  });

  it.each([
    ["zero", 0],
    ["below zero", -300],
  ])("sends an expense when the float is %s", async (_name, balance) => {
    const overview = pettyOverview({
      floats: [{ ...pettyOverview().floats[0], balance }],
    });
    const api = await signIn(["pettycash.spend"], (setup) =>
      spender(setup, [], overview),
    );
    api.on("setup/pettycash/entries", [
      200,
      { id: "x", version: 1, status: "waiting", balance },
    ]);
    await openForm(api);
    await pick("Vehicle", "KDA 482M, North Star");
    await pick("Item", "Diesel, Running");
    await fireEvent.changeText(screen.getByLabelText("Amount each"), "900");
    await fireEvent.press(screen.getByRole("button", { name: "Save expense" }));
    await waitFor(() =>
      expect(bodies(api, "setup/pettycash/entries", "POST")).toHaveLength(1),
    );
    expect(
      await screen.findByText("Expense saved. It waits for approval."),
    ).toBeTruthy();
  });

  it("accepts a leading minus, shows the live total and sends the client id", async () => {
    randomUUID.mockReturnValueOnce("7d1f5f0e-9f1c-4f6e-8a55-0b7a4c8e2a11");
    const api = await signIn(["pettycash.spend"], spender);
    api.on("setup/pettycash/entries", [
      200,
      {
        id: "7d1f5f0e-9f1c-4f6e-8a55-0b7a4c8e2a11",
        version: 1,
        status: "waiting",
        balance: 5000,
      },
    ]);
    await openForm(api);

    await pick("Vehicle", "KDA 482M, North Star");
    await pick("Item", "Tyre repair, Repairs");
    await fireEvent.changeText(screen.getByLabelText("Units"), "2");
    await fireEvent.changeText(screen.getByLabelText("Amount each"), "-250");
    expect(await screen.findByText(/^Total KES [-−]500$/)).toBeTruthy();
    await fireEvent.changeText(
      screen.getByLabelText("Note (optional)"),
      "Refund",
    );
    await fireEvent.press(screen.getByRole("button", { name: "Save expense" }));

    await waitFor(() =>
      expect(bodies(api, "setup/pettycash/entries", "POST")).toEqual([
        {
          id: "7d1f5f0e-9f1c-4f6e-8a55-0b7a4c8e2a11",
          kind: "expense",
          date: DAY,
          vehicleId: "vehicle-1",
          expenseItemId: "item-1",
          units: 2,
          unitAmount: -250,
          note: "Refund",
        },
      ]),
    );
    expect(
      await screen.findByText("Expense saved. It waits for approval."),
    ).toBeTruthy();
    expect(screen.queryByRole("header", { name: "Record expense" })).toBeNull();
    await waitFor(() =>
      expect(api.sent("setup/pettycash/overview").length).toBeGreaterThan(1),
    );
  });

  it("retries a failed save with the same id", async () => {
    randomUUID.mockReturnValueOnce("retry-id-0001");
    const api = await signIn(["pettycash.spend"], spender);
    let calls = 0;
    api.on("setup/pettycash/entries", () =>
      ++calls === 1
        ? [503, {}]
        : [
            200,
            { id: "retry-id-0001", version: 1, status: "waiting", balance: 1 },
          ],
    );
    await openForm(api);
    await pick("Vehicle", "KDA 482M, North Star");
    await pick("Item", "Diesel, Running");
    await fireEvent.changeText(screen.getByLabelText("Amount each"), "400");

    await fireEvent.press(screen.getByRole("button", { name: "Save expense" }));
    expect(
      await screen.findByText(
        "Something went wrong on the server. Try again in a moment.",
      ),
    ).toBeTruthy();
    await fireEvent.press(screen.getByRole("button", { name: "Save expense" }));
    await screen.findByText("Expense saved. It waits for approval.");
    const sent = bodies(api, "setup/pettycash/entries", "POST");
    expect(sent).toHaveLength(2);
    expect(sent[0].id).toBe("retry-id-0001");
    expect(sent[1].id).toBe("retry-id-0001");
  });

  it("shows the server's sentence inline on a 400 and keeps the form", async () => {
    const api = await signIn(["pettycash.spend"], spender);
    api.on("setup/pettycash/entries", [
      400,
      {
        detail: "This takes the float below zero. Ask for cash first.",
        balanceAfter: -100,
      },
    ]);
    await openForm(api);
    await pick("Vehicle", "KDA 482M, North Star");
    await pick("Item", "Diesel, Running");
    await fireEvent.changeText(screen.getByLabelText("Amount each"), "9000");
    await fireEvent.press(screen.getByRole("button", { name: "Save expense" }));
    expect(
      await screen.findByText(
        "This takes the float below zero. Ask for cash first.",
      ),
    ).toBeTruthy();
    expect(screen.getByRole("button", { name: "Save expense" })).toBeTruthy();
  });

  it("changes an entry with its version and without a new id", async () => {
    const api = await signIn(["pettycash.spend"], (setup) =>
      spender(setup, [pettyEntry({ version: 4 })]),
    );
    api.on("setup/pettycash/entries/entry-1", [
      200,
      { id: "entry-1", version: 5, status: "waiting", balance: 1 },
    ]);
    await fireEvent.press(
      await screen.findByRole("button", { name: "Edit KDA 482M, Tyre repair" }),
    );
    await screen.findByRole("header", { name: "Edit expense" });
    expect(screen.getByLabelText("Units").props.value).toBe("2");
    expect(screen.getByLabelText("Amount each").props.value).toBe("750");
    await fireEvent.changeText(screen.getByLabelText("Amount each"), "800");
    await fireEvent.press(screen.getByRole("button", { name: "Save expense" }));
    await waitFor(() =>
      expect(bodies(api, "setup/pettycash/entries/entry-1", "PUT")).toEqual([
        {
          version: 4,
          kind: "expense",
          date: DAY,
          vehicleId: "vehicle-1",
          expenseItemId: "item-1",
          units: 2,
          unitAmount: 800,
          note: null,
        },
      ]),
    );
    expect(
      await screen.findByText("Expense changed. It waits for approval again."),
    ).toBeTruthy();
  });
});

describe("Credit note", () => {
  it("needs a payee and a reason, and sends who was paid and why", async () => {
    randomUUID.mockReturnValueOnce("credit-id-0001");
    const api = await signIn(["pettycash.spend"], spender);
    api.on("setup/pettycash/entries", [
      200,
      { id: "credit-id-0001", version: 1, status: "waiting", balance: 1 },
    ]);
    await fireEvent.press(
      await screen.findByRole("button", { name: "Credit note" }),
    );
    await screen.findByRole("header", { name: "Credit note" });
    expect(screen.queryByRole("button", { name: /^Manager, / })).toBeNull();

    await fireEvent.press(
      screen.getByRole("button", { name: "Save credit note" }),
    );
    expect(await screen.findByText("Enter who was paid.")).toBeTruthy();
    expect(screen.getByText("Enter the reason.")).toBeTruthy();
    expect(screen.getByText(PETTY_CASH_AMOUNT_ERROR)).toBeTruthy();

    await fireEvent.changeText(screen.getByLabelText("Paid to"), "Mama Fua");
    await fireEvent.changeText(screen.getByLabelText("Amount"), "300");
    await fireEvent.press(
      screen.getByRole("button", { name: "Save credit note" }),
    );
    expect(await screen.findByText("Enter the reason.")).toBeTruthy();
    expect(bodies(api, "setup/pettycash/entries", "POST")).toHaveLength(0);

    await fireEvent.changeText(
      screen.getByLabelText("Reason"),
      "Washing the bus",
    );
    await fireEvent.press(
      screen.getByRole("switch", { name: "Money to be paid back" }),
    );
    await fireEvent.press(
      screen.getByRole("button", { name: "Save credit note" }),
    );
    await waitFor(() =>
      expect(bodies(api, "setup/pettycash/entries", "POST")).toEqual([
        {
          id: "credit-id-0001",
          kind: "credit",
          date: DAY,
          payee: "Mama Fua",
          note: "Washing the bus",
          unitAmount: 300,
          reimbursable: true,
        },
      ]),
    );
    expect(
      await screen.findByText("Credit note saved. It waits for approval."),
    ).toBeTruthy();
  });

  it("lets an issuer pick the manager the note is recorded against", async () => {
    const api = await signIn(["pettycash.spend", "pettycash.issue"], (setup) =>
      spender(
        setup,
        [],
        pettyOverview({ permissions: pettyPermissions({ canIssue: true }) }),
      ),
    );
    api.on("setup/pettycash/entries", [
      200,
      { id: "x", version: 1, status: "waiting", balance: 1 },
    ]);
    await fireEvent.press(
      await screen.findByRole("button", { name: "Credit note" }),
    );
    await screen.findByRole("button", { name: "Manager, Brian Mwangi" });
    await pick("Manager", "Grace Njeri");
    await fireEvent.changeText(screen.getByLabelText("Paid to"), "Mama Fua");
    await fireEvent.changeText(screen.getByLabelText("Reason"), "Water");
    await fireEvent.changeText(screen.getByLabelText("Amount"), "-50");
    await fireEvent.press(
      screen.getByRole("button", { name: "Save credit note" }),
    );
    await waitFor(() =>
      expect(bodies(api, "setup/pettycash/entries", "POST")).toHaveLength(1),
    );
    expect(bodies(api, "setup/pettycash/entries", "POST")[0]).toMatchObject({
      kind: "credit",
      holderId: "u-grace",
      unitAmount: -50,
      reimbursable: false,
    });
  });
});

describe("Give cash", () => {
  it("needs a manager and a non-zero amount, then sends cash, which may be negative", async () => {
    randomUUID.mockReturnValueOnce("cash-id-0001");
    const api = await signIn(["pettycash.issue"], (setup) => {
      setup.on("setup/pettycash/overview", [
        200,
        pettyOverview({
          permissions: pettyPermissions({
            canSpend: false,
            holderId: null,
            canIssue: true,
          }),
          floats: [],
        }),
      ]);
      setup.on(OPTIONS, [200, pettyOptions]);
      setup.on("setup/pettycash/options?date=2026-09-28", [200, pettyOptions]);
      setup.on("setup/pettycash/entries", [
        200,
        { id: "cash-id-0001", version: 1, status: null, balance: 1 },
      ]);
    });
    await screen.findByRole("header", { name: "Give cash" });
    await screen.findByRole("button", { name: "Manager, not chosen" });

    await fireEvent.press(screen.getByRole("button", { name: "Save cash" }));
    expect(await screen.findByText("Choose a manager.")).toBeTruthy();
    expect(screen.getByText(PETTY_CASH_AMOUNT_ERROR)).toBeTruthy();

    await pick("Manager", "Grace Njeri");
    await fireEvent.changeText(screen.getByLabelText("Amount"), "0");
    await fireEvent.press(screen.getByRole("button", { name: "Save cash" }));
    expect(await screen.findByText(PETTY_CASH_AMOUNT_ERROR)).toBeTruthy();
    expect(bodies(api, "setup/pettycash/entries", "POST")).toHaveLength(0);

    await fireEvent.changeText(screen.getByLabelText("Amount"), "-200");
    await fireEvent.press(
      screen.getByRole("button", { name: "Previous date" }),
    );
    await fireEvent.changeText(
      screen.getByLabelText("Note (optional)"),
      "Taken back",
    );
    await fireEvent.press(screen.getByRole("button", { name: "Save cash" }));
    await waitFor(() =>
      expect(bodies(api, "setup/pettycash/entries", "POST")).toEqual([
        {
          id: "cash-id-0001",
          kind: "cash",
          holderId: "u-grace",
          date: "2026-09-28",
          unitAmount: -200,
          note: "Taken back",
        },
      ]),
    );
    expect(await screen.findByText("Cash recorded.")).toBeTruthy();
  });
});

describe("Approvals", () => {
  const approver = pettyOverview({
    permissions: pettyPermissions({
      canSpend: false,
      holderId: null,
      canApproveItem: true,
      canApproveDay: true,
      approvalLimit: 2000,
    }),
    floats: [],
  });
  const grace = { holderId: "u-grace", holderName: "Grace Njeri" };
  const waitingEntries = () => [
    pettyEntry({
      id: "entry-1",
      ...grace,
      date: "2026-09-28",
      canReview: true,
      version: 3,
    }),
    pettyEntry({
      id: "entry-2",
      ...grace,
      expenseItemName: "Engine overhaul",
      units: 1,
      unitAmount: 5000,
      total: 5000,
      aboveLimit: true,
      canEdit: false,
      canRemove: false,
    }),
    pettyEntry({ id: "entry-3", expenseItemName: "Diesel" }),
  ];

  it("shows Approve and Send back only where canReview is set and says when an entry is above the limit", async () => {
    await signIn(["pettycash.approve_item", "pettycash.approve_day"], (api) => {
      api.on("setup/pettycash/overview", [200, approver]);
      api.on(WAITING, [200, pettyPage(waitingEntries())]);
    });
    await screen.findByText("KDA 482M, Tyre repair");
    expect(
      screen.getByText(/You can approve entries up to KES 2,000/),
    ).toBeTruthy();
    expect(
      screen.getAllByRole("button", { name: /^Approve KDA/ }),
    ).toHaveLength(1);
    expect(
      screen.getByRole("button", { name: "Approve KDA 482M, Tyre repair" }),
    ).toBeTruthy();
    expect(
      screen.getAllByRole("button", { name: /^Send back KDA/ }),
    ).toHaveLength(1);
    expect(screen.getByText("Above your limit")).toBeTruthy();
    expect(
      screen.getAllByRole("button", { name: /^Approve day / }),
    ).toHaveLength(2);
  });

  it("hides Approve day without the permission", async () => {
    await signIn(["pettycash.approve_item"], (api) => {
      api.on("setup/pettycash/overview", [
        200,
        pettyOverview({
          ...approver,
          permissions: pettyPermissions({
            ...approver.permissions,
            canApproveDay: false,
          }),
        }),
      ]);
      api.on(WAITING, [200, pettyPage(waitingEntries())]);
    });
    await screen.findByText("KDA 482M, Tyre repair");
    expect(screen.queryByRole("button", { name: /^Approve day / })).toBeNull();
  });

  it("approves with the entry's version and reloads the list", async () => {
    let approved = false;
    const api = await signIn(["pettycash.approve_item"], (setup) => {
      setup.on("setup/pettycash/overview", [200, approver]);
      setup.on(WAITING, () => [
        200,
        pettyPage(approved ? waitingEntries().slice(1) : waitingEntries()),
      ]);
      setup.on("setup/pettycash/entries/entry-1/approve", () => {
        approved = true;
        return [
          200,
          { id: "entry-1", version: 4, status: "approved", balance: 1 },
        ];
      });
    });
    await fireEvent.press(
      await screen.findByRole("button", {
        name: "Approve KDA 482M, Tyre repair",
      }),
    );
    expect(await screen.findByText("Entry approved.")).toBeTruthy();
    expect(api.sent("setup/pettycash/entries/entry-1/approve")).toEqual([
      { version: 3 },
    ]);
    await waitFor(() =>
      expect(
        screen.queryByRole("button", { name: "Approve KDA 482M, Tyre repair" }),
      ).toBeNull(),
    );
    expect(api.sent(WAITING).length).toBeGreaterThan(1);
  });

  it("needs a comment to send back", async () => {
    const api = await signIn(["pettycash.approve_item"], (setup) => {
      setup.on("setup/pettycash/overview", [200, approver]);
      setup.on(WAITING, [200, pettyPage(waitingEntries())]);
      setup.on("setup/pettycash/entries/entry-1/send-back", [
        200,
        { id: "entry-1", version: 4, status: "sentBack", balance: 1 },
      ]);
    });
    await fireEvent.press(
      await screen.findByRole("button", {
        name: "Send back KDA 482M, Tyre repair",
      }),
    );
    await screen.findByRole("header", { name: "Send back" });
    await fireEvent.press(screen.getByRole("button", { name: "Send back" }));
    expect(
      await screen.findByText(
        "Enter a comment for the person who recorded it.",
      ),
    ).toBeTruthy();
    expect(api.sent("setup/pettycash/entries/entry-1/send-back")).toHaveLength(
      0,
    );

    await fireEvent.changeText(
      screen.getByLabelText("Comment"),
      "Receipt is unclear",
    );
    await fireEvent.press(screen.getByRole("button", { name: "Send back" }));
    expect(await screen.findByText("Entry sent back.")).toBeTruthy();
    expect(api.sent("setup/pettycash/entries/entry-1/send-back")).toEqual([
      { version: 3, comment: "Receipt is unclear" },
    ]);
  });

  it("approves a day and says what was left for someone else", async () => {
    const api = await signIn(
      ["pettycash.approve_item", "pettycash.approve_day"],
      (setup) => {
        setup.on("setup/pettycash/overview", [200, approver]);
        setup.on(WAITING, [200, pettyPage(waitingEntries())]);
        setup.on("setup/pettycash/approve-day", [
          200,
          { approved: 2, total: 3000, skipped: 1 },
        ]);
      },
    );
    const [first] = await screen.findAllByRole("button", {
      name: /^Approve day /,
    });
    await fireEvent.press(first);
    expect(
      await screen.findByText(
        "Approved 2 entries, KES 3,000. 1 entry was left for someone else.",
      ),
    ).toBeTruthy();
    expect(api.sent("setup/pettycash/approve-day")).toEqual([
      { date: "2026-09-28" },
    ]);
  });

  it("shows the server's message on a 409 and reloads", async () => {
    let changed = false;
    const api = await signIn(["pettycash.approve_item"], (setup) => {
      setup.on("setup/pettycash/overview", [200, approver]);
      setup.on(WAITING, () => [
        200,
        pettyPage(changed ? [] : waitingEntries()),
      ]);
      setup.on("setup/pettycash/entries/entry-1/approve", () => {
        changed = true;
        return [
          409,
          {
            detail:
              "Someone else already changed this entry. Check it and try again.",
            current: pettyEntry(),
          },
        ];
      });
    });
    await fireEvent.press(
      await screen.findByRole("button", {
        name: "Approve KDA 482M, Tyre repair",
      }),
    );
    expect(
      await screen.findByText(
        "Someone else already changed this entry. Check it and try again.",
      ),
    ).toBeTruthy();
    expect(
      await screen.findByText("Nothing is waiting for approval."),
    ).toBeTruthy();
    expect(api.sent(WAITING).length).toBeGreaterThan(1);
    expect(api.sent("setup/pettycash/overview").length).toBeGreaterThan(1);
  });

  it("shows the permission message on a 403", async () => {
    const api = await signIn(["pettycash.approve_item"], (setup) => {
      setup.on("setup/pettycash/overview", [200, approver]);
      setup.on(WAITING, [200, pettyPage(waitingEntries())]);
      setup.on("setup/pettycash/entries/entry-1/approve", [
        403,
        { detail: "You need Approve single entries to do this." },
      ]);
    });
    await fireEvent.press(
      await screen.findByRole("button", {
        name: "Approve KDA 482M, Tyre repair",
      }),
    );
    expect(
      await screen.findByText("You need Approve single entries to do this."),
    ).toBeTruthy();
    expect(api.sent(WAITING)).toHaveLength(1);
  });
});

describe("Removing an entry", () => {
  it("asks for a reason and sends it with the version", async () => {
    const api = await signIn(["pettycash.spend"], (setup) => {
      spender(setup, [pettyEntry({ version: 2 })]);
      setup.on("setup/pettycash/entries/entry-1/remove", [
        200,
        { id: "entry-1", version: 3, status: "waiting", balance: 1 },
      ]);
    });
    await fireEvent.press(
      await screen.findByRole("button", {
        name: "Remove KDA 482M, Tyre repair",
      }),
    );
    await screen.findByRole("header", { name: "Remove entry" });
    await fireEvent.press(screen.getByRole("button", { name: "Remove entry" }));
    expect(
      await screen.findByText("Enter the reason for removing it."),
    ).toBeTruthy();
    expect(api.sent("setup/pettycash/entries/entry-1/remove")).toHaveLength(0);

    await fireEvent.changeText(
      screen.getByLabelText("Reason for removing"),
      "Entered twice",
    );
    await fireEvent.press(screen.getByRole("button", { name: "Remove entry" }));
    expect(await screen.findByText("Entry removed.")).toBeTruthy();
    expect(api.sent("setup/pettycash/entries/entry-1/remove")).toEqual([
      { version: 2, reason: "Entered twice" },
    ]);
  });
});

describe("Home cards", () => {
  const dashboard = {
    float: {
      balance: -300,
      waitingCount: 1,
      waitingTotal: 1500,
      sentBackCount: 2,
      approvedThisMonth: 800,
    },
    approvals: {
      count: 3,
      total: 4500,
      approvalLimit: 2000,
      aboveLimit: 1,
      holders: [
        {
          holderId: "u-grace",
          name: "Grace Njeri",
          count: 2,
          total: 3000,
          oldest: "2026-09-27",
        },
      ],
    },
  };
  const perms = [
    "dash.float",
    "dash.pettycash",
    "pettycash.spend",
    "pettycash.approve_item",
  ];
  const cardOf = (title: string) =>
    screen.getByRole("header", { name: title }).parent!.parent!;

  it("shows the float and the approvals from the dashboard payload", async () => {
    await signIn(
      perms,
      (api) => api.on("setup/pettycash/dashboard", [200, dashboard]),
      "Home",
    );
    const float = cardOf("My petty cash float");
    expect(await within(float).findByText("KES -300")).toBeTruthy();
    expect(within(float).getByText("Balance now")).toBeTruthy();
    expect(
      within(float).getByText(
        "1 entry, KES 1,500, waiting for approval. 2 entries were sent back to you. KES 800 approved this month",
      ),
    ).toBeTruthy();
    expect(
      within(float).getByRole("button", { name: "Record spending" }),
    ).toBeTruthy();

    const approvals = cardOf("Petty cash to approve");
    expect(await within(approvals).findByText("3 entries")).toBeTruthy();
    expect(
      within(approvals).getByText(
        "KES 4,500 in total. You can approve entries up to KES 2,000. 1 entry is above your limit.",
      ),
    ).toBeTruthy();
    expect(
      within(approvals).getByText(
        /^Grace Njeri: 2 entries, KES 3,000, oldest /,
      ),
    ).toBeTruthy();
    expect(
      within(approvals).getByRole("button", { name: "Review entries" }),
    ).toBeTruthy();
    expect(screen.queryByText("Petty cash is not connected yet.")).toBeNull();
    expect(screen.queryByText("Not available yet")).toBeNull();
  });

  it("opens Approvals from Review entries", async () => {
    await signIn(
      perms,
      (api) => {
        api.on("setup/pettycash/dashboard", [200, dashboard]);
        api.on("setup/pettycash/overview", [
          200,
          pettyOverview({
            permissions: pettyPermissions({ canApproveItem: true }),
          }),
        ]);
        api.on(OWN, [200, pettyOverview()]);
        api.on(ENTRIES, [200, pettyPage([])]);
        api.on(WAITING, [200, pettyPage([])]);
      },
      "Home",
    );
    await fireEvent.press(
      await screen.findByRole("button", { name: "Review entries" }),
    );
    expect(
      await screen.findByText(/Entries waiting for approval, oldest day first/),
    ).toBeTruthy();
    expect(
      screen.getByRole("button", { name: "Approvals", selected: true }),
    ).toBeTruthy();
  });

  it("says so for a part the API leaves out and for a failed load", async () => {
    await signIn(
      perms,
      (api) =>
        api.on("setup/pettycash/dashboard", [
          200,
          { float: null, approvals: dashboard.approvals },
        ]),
      "Home",
    );
    expect(
      await within(cardOf("My petty cash float")).findByText(
        "Not shown with your access.",
      ),
    ).toBeTruthy();
    expect(
      await within(cardOf("Petty cash to approve")).findByText("3 entries"),
    ).toBeTruthy();
  });

  it("shows the error when the dashboard cannot load", async () => {
    await signIn(
      perms,
      (api) =>
        api.on("setup/pettycash/dashboard", [
          403,
          { detail: "You need See my petty cash float to do this." },
        ]),
      "Home",
    );
    expect(
      await within(cardOf("My petty cash float")).findByText(
        "You need See my petty cash float to do this.",
      ),
    ).toBeTruthy();
  });
});
