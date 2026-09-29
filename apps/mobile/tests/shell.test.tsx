import { fireEvent, screen, waitFor, within } from "@testing-library/react-native";
import { catalog, fakeApi, people, revenueDashboard, revenueWeek, tokens } from "./fakeApi";
import { startApp, storedText, trustPhone, typePin } from "./helpers";

async function unlockAs(person: (typeof people)[keyof typeof people], phone: string) {
  await trustPhone(person, phone);
  const api = fakeApi();
  api.on("auth/unlock", [200, tokens(2)]);
  api.on("auth/session", [200, person]);
  api.on("setup/access/catalog", [200, catalog]);
  api.on("setup/revenue", [200, revenueWeek]);
  api.on("setup/revenue?weekStart=2026-09-28", [200, revenueWeek]);
  api.on("setup/revenue/vehicle-1/2026-09-29", [200, { id: "record-1" }]);
  api.on("setup/revenue/dashboard?period=today", [200, { ...revenueDashboard, period: "today" }]);
  api.on("setup/revenue/dashboard?period=month", [200, { ...revenueDashboard, period: "month" }]);
  api.on("setup/revenue/dashboard?period=week", [200, revenueDashboard]);
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
  for (const title of ["Revenue", "Net contribution", "Costs", "Missing revenue days"]) expect(screen.getByRole("header", { name: title })).toBeTruthy();
  expect(screen.queryByText("Today's revenue")).toBeNull();
  expect(screen.queryByText("Renewals due")).toBeNull();

  await fireEvent.press(screen.getByText("Open revenue"));
  await screen.findByText("Record revenue or explain why no revenue was earned.");
  expect(screen.getByText("No earnings reason")).toBeTruthy();
  expect(screen.getByText("Your access does not include no-earnings reasons.")).toBeTruthy();
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
  await screen.findByText("Record revenue or explain why no revenue was earned.");
  expect(screen.getByText("Capture")).toBeTruthy();
  await fireEvent.press(screen.getByText("Capture"));
  expect(screen.getByText("No earnings reason")).toBeTruthy();
  expect(screen.getByText("Garage")).toBeTruthy();
  await fireEvent.changeText(screen.getByLabelText("Revenue amount"), "1000");
  await fireEvent.press(screen.getByRole("button", { name: "Save revenue" }));
  await waitFor(() => expect(api.sent("setup/revenue/vehicle-1/2026-09-29")).toHaveLength(1));

  await fireEvent.press(screen.getByRole("tab", { name: "More" }));
  await screen.findByText("Wanjiru Kamau");
  expect(screen.queryByText("Setup")).toBeNull();
});

it("shows the Spend tab to people who hold a petty cash permission", async () => {
  await unlockAs(people.manager, "0700111222");
  expect(tabs()).toEqual(["Home", "Revenue", "Spend", "More"]);
  await fireEvent.press(screen.getByRole("tab", { name: "Spend" }));
  await screen.findByText("Petty cash and office bills are not available from the current API yet.");
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
