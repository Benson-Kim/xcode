import { fireEvent, screen, waitFor, within } from "@testing-library/react-native";
import { catalog, fakeApi, people, revenueDashboard, revenueWeek, tokens } from "./fakeApi";
import { startApp, storedText, trustPhone, typePin } from "./helpers";

async function unlockAs(person: (typeof people)[keyof typeof people], phone: string, figures: Partial<typeof revenueDashboard> = {}) {
  await trustPhone(person, phone);
  const api = fakeApi();
  api.on("auth/unlock", [200, tokens(2)]);
  api.on("auth/session", [200, person]);
  api.on("setup/access/catalog", [200, catalog]);
  api.on("setup/revenue", [200, revenueWeek]);
  api.on("setup/revenue?weekStart=2026-09-28", [200, revenueWeek]);
  api.on("setup/revenue/vehicle-1/2026-09-28", [200, { id: "record-1", version: 1 }]);
  api.on("setup/revenue/dashboard?period=today", [200, { ...revenueDashboard, ...figures, period: "today" }]);
  api.on("setup/revenue/dashboard?period=month", [200, { ...revenueDashboard, ...figures, period: "month" }]);
  api.on("setup/revenue/dashboard?period=week", [200, { ...revenueDashboard, ...figures }]);
  await startApp();
  await screen.findByText(`Welcome back, ${person.firstName}`);
  await typePin("4826");
  await screen.findByText(`Hi ${person.firstName}`);
  return api;
}

const tabs = () => screen.getAllByRole("tab").map((tab) => tab.props.accessibilityLabel);

it("shows an owner the tabs, cards and setup links their permissions allow", async () => {
  await unlockAs(people.owner, "0733520614");

  expect(tabs()).toEqual(["Home", "Revenue", "More"]);
  // No capture or float permission: the dashboard opens on the month so far.
  expect(screen.getByRole("button", { name: "This month", selected: true })).toBeTruthy();
  for (const title of ["Revenue", "Net contribution", "Money out", "Missing revenue days"]) expect(screen.getByRole("header", { name: title })).toBeTruthy();
  expect(screen.queryByText("Today's revenue")).toBeNull();
  expect(screen.queryByText("Yearly items due")).toBeNull();
  // Figures the API does not serve yet say so, never a screen of zeros. The revenue card shows its real figure (nothing
  // captured against a KES 2,000 target) once the dashboard has loaded, so wait for it rather than race it.
  expect(await screen.findByText(/^0% of target KES 2,000/)).toBeTruthy();
  expect(screen.getAllByText("Not available yet")).toHaveLength(2);
  expect(screen.getAllByText("KES 0")).toHaveLength(1);

  await fireEvent.press(screen.getByText("Fill the gaps"));
  // Viewing and correcting without capture: a missing day shows as missing and does not open.
  expect(await screen.findByLabelText("KDA 482M, Missing")).toBeTruthy();
  expect(screen.queryByRole("button", { name: "KDA 482M, Enter revenue" })).toBeNull();
  expect(screen.queryByText("What you can do here")).toBeNull();

  await fireEvent.press(screen.getByRole("tab", { name: "More" }));
  await screen.findByText("Antony Maina");
  for (const link of ["PSV companies", "People and access", "Change log"]) expect(screen.getByLabelText(`${link}, on XCODE Web`)).toBeTruthy();
  expect(screen.queryByLabelText("Vehicles, on XCODE Web")).toBeNull();
  expect(screen.getByText("Set up PSV companies")).toBeTruthy();
  expect(screen.getByText("View people")).toBeTruthy();
});

it("starts a revenue clerk on today with capture first", async () => {
  const api = await unlockAs(people.clerk, "0712345678");

  expect(tabs()).toEqual(["Home", "Revenue", "More"]);
  expect(screen.getByRole("button", { name: "Today", selected: true })).toBeTruthy();
  const capture = screen.getByRole("header", { name: "Today's revenue" });
  expect(capture).toBeTruthy();
  await fireEvent.press(screen.getByText("Capture revenue"));
  // The screen opens on the earliest missing day, one tap from capture.
  await fireEvent.press(await screen.findByRole("button", { name: "KDA 482M, Enter revenue" }));
  expect(screen.getByText("Mon 28 Sep 2026. Expected KES 1,000")).toBeTruthy();
  expect(screen.getByRole("radio", { name: "Garage" })).toBeTruthy();
  await fireEvent.changeText(screen.getByLabelText("Revenue amount"), "1000");
  await fireEvent.press(screen.getByRole("button", { name: "Save" }));
  await waitFor(() => expect(api.sent("setup/revenue/vehicle-1/2026-09-28")).toEqual([{ amount: 1000, reason: null, note: null, version: null }]));

  await fireEvent.press(screen.getByRole("tab", { name: "More" }));
  await screen.findByText("Wanjiru Kamau");
  expect(screen.queryByText("Setup")).toBeNull();
});

const cardOf = (title: string) => screen.getByRole("header", { name: title }).parent!.parent!;

it("shows each home card from its own figures only", async () => {
  // What the API sends a revenue clerk (dash.capture and dash.gaps): no revenue totals and no edits count.
  await unlockAs(people.clerk, "0712345678", { revenue: null, expected: null, percent: null, editedRecords: null } as never);
  expect(await within(cardOf("Today's revenue")).findByText("0 of 1 captured")).toBeTruthy();
  expect(within(cardOf("Missing revenue days")).getByText("1 day")).toBeTruthy();
  expect(screen.queryByRole("header", { name: "Revenue" })).toBeNull();
  expect(screen.queryByRole("header", { name: "Edited after capture" })).toBeNull();
});

it("shows nothing for a figure the API leaves out", async () => {
  // No "no missing days" beside a count of missing days, and no "no target" when the target was left out.
  await unlockAs(people.owner, "0733520614", { revenue: 5000, expected: null, percent: null, missingDays: 2, missingVehicles: null } as never);
  expect(await within(cardOf("Revenue")).findByText("KES 5,000")).toBeTruthy();
  expect(within(cardOf("Revenue")).queryByText("No dated target is available.")).toBeNull();
  expect(within(cardOf("Missing revenue days")).getByText("2 days")).toBeTruthy();
  expect(within(cardOf("Missing revenue days")).queryByText("No missing days so far this month.")).toBeNull();
  expect(screen.queryByText(/null|undefined|NaN/)).toBeNull();
});

it("shows the Spend tab to people who hold a petty cash permission", async () => {
  await unlockAs(people.manager, "0700111222");
  expect(tabs()).toEqual(["Home", "Revenue", "Spend", "More"]);
  await fireEvent.press(screen.getByRole("tab", { name: "Spend" }));
  await screen.findByText("Petty cash and office bills are not available from the current API yet.");
});

it("names scheduled expenses and savings as XCODE Web does", async () => {
  await unlockAs({ ...people.manager, permissions: ["commitments.view"] }, "0700111333");
  await fireEvent.press(screen.getByRole("tab", { name: "More" }));
  expect(await screen.findByLabelText("Scheduled expenses and savings, on XCODE Web")).toBeTruthy();
  expect(screen.queryByText("Recurring costs and savings")).toBeNull();
});

it("says so when the person has nothing to see yet", async () => {
  await unlockAs({ ...people.clerk, permissions: [] }, "0712345678");
  expect(tabs()).toEqual(["Home", "More"]);
  expect(screen.getByText("Nothing to show yet")).toBeTruthy();
  expect(screen.getByText("Your admin decides what you can see here.")).toBeTruthy();
});

it("locks from Home and switches user from More", async () => {
  const api = await unlockAs(people.owner, "0733520614");
  await fireEvent.press(screen.getByRole("button", { name: "Lock app" }));
  await screen.findByText("Welcome back, Antony");

  api.on("auth/unlock", [200, tokens(3)]);
  await typePin("4826");
  await screen.findByText("Hi Antony");
  api.on("auth/devices/stable-test-device/revoke", [200, { status: "device_revoked" }]);
  await fireEvent.press(screen.getByRole("tab", { name: "More" }));
  await fireEvent.press(await screen.findByText("Switch user"));
  await screen.findByText("Sign in");
  expect(api.sent("auth/devices/stable-test-device/revoke")).toHaveLength(1);
  expect(storedText()).not.toContain("Antony");
});

it("returns to the unlock pad when the session can no longer be renewed", async () => {
  await trustPhone(people.owner, "0733520614");
  const api = fakeApi();
  api.on("auth/unlock", [200, tokens(2)]);
  api.on("auth/session", [200, people.owner]);
  api.on("setup/access/catalog", [401, {}]);
  api.on("auth/refresh", [401, { status: "authentication_failed" }]);
  await startApp();
  await screen.findByText("Welcome back, Antony");
  await typePin("4826");
  // Signed in, the first request finds the session gone: the app locks again rather than showing stale screens.
  await waitFor(() => expect(api.sent("auth/refresh")).toHaveLength(1));
  await screen.findByText("Welcome back, Antony");
  expect(screen.queryByText("Hi Antony")).toBeNull();
});

it("renews an expired access token once and retries", async () => {
  await trustPhone(people.owner, "0733520614");
  const api = fakeApi();
  api.on("auth/unlock", [200, tokens(2)]);
  api.on("auth/session", [200, people.owner]);
  api.on("auth/refresh", [200, tokens(4)]);
  api.on("setup/access/catalog", (_, headers) => (headers.Authorization === "Bearer access-4" ? [200, catalog] : [401, {}]));
  await startApp();
  await screen.findByText("Welcome back, Antony");
  await typePin("4826");
  await fireEvent.press(await screen.findByRole("tab", { name: "More" }));
  const access = await screen.findByText("Set up PSV companies");
  expect(within(access.parent!.parent!).queryByText("Loading")).toBeNull();
  expect(storedText()).toContain("refresh-4");
});
