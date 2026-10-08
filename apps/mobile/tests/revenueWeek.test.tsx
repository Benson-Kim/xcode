import { fireEvent, screen, waitFor } from "@testing-library/react-native";
import { StyleSheet } from "react-native";

import { alpha, palette } from "../src/ui";
import { catalog, fakeApi, people, revenueWeek, tokens } from "./fakeApi";
import { startApp, trustPhone, typePin } from "./helpers";

const VEHICLE_WEEK = "setup/revenue?weekStart=2026-09-28&vehicleId=vehicle-1";
const SERVER_ERROR = {
  title: "An error occurred while processing your request.",
  status: 500,
};
const SERVER_MESSAGE =
  "Something went wrong on the server. Try again in a moment.";

let network: jest.SpyInstance;
const setNetwork = (connected: boolean) =>
  network.mockReturnValue({
    isConnected: connected,
    isInternetReachable: connected,
  });

beforeEach(() => {
  network = jest.spyOn(require("expo-network"), "useNetworkState");
});
afterEach(() => network.mockRestore());

// One clerk per test: the screen keeps loaded weeks in memory per person.
let next = 0;
async function signIn(routes: (api: ReturnType<typeof fakeApi>) => void) {
  next += 1;
  const clerk = { ...people.clerk, userId: `u-week-${next}` };
  await trustPhone(clerk, `07120001${next}0`);
  const api = fakeApi();
  api.on("auth/unlock", [200, tokens(2)]);
  api.on("auth/session", [200, clerk]);
  api.on("setup/access/catalog", [200, catalog]);
  routes(api);
  await startApp();
  await screen.findByText(`Welcome back, ${clerk.firstName}`);
  await typePin("4826");
  await screen.findByText(`Hi ${clerk.firstName}`);
  return api;
}

const openRevenue = () =>
  fireEvent.press(screen.getByRole("tab", { name: /^Revenue/ }));
const openWeek = () =>
  fireEvent.press(screen.getByRole("button", { name: "Week" }));
const openDay = () =>
  fireEvent.press(screen.getByRole("button", { name: "Day" }));

it("loads the week again when the connection returns after a failed load", async () => {
  const api = await signIn((routes) => routes.on("setup/revenue", "offline"));
  setNetwork(false);
  await openRevenue();
  expect(
    await screen.findByText(/^No internet\. Revenue needs a connection/),
  ).toBeTruthy();
  expect(api.sent("setup/revenue")).toHaveLength(1);

  api.on("setup/revenue", [200, revenueWeek]);
  setNetwork(true);
  // Any state change draws the screen again, which reads the connection afresh.
  await openWeek();
  expect(
    await screen.findByRole("button", { name: /^KDA 482M, KES 0/ }),
  ).toBeTruthy();
  expect(api.sent("setup/revenue")).toHaveLength(2);
  expect(screen.queryByText(/^No internet/)).toBeNull();
});

it("does not load again on its own while online after a failure", async () => {
  const api = await signIn((routes) =>
    routes.on("setup/revenue", [500, SERVER_ERROR]),
  );
  setNetwork(true);
  await openRevenue();
  expect(await screen.findByText(SERVER_MESSAGE)).toBeTruthy();
  await openWeek();
  await openDay();
  await openWeek();
  await new Promise((resolve) => setTimeout(resolve, 150));
  expect(api.sent("setup/revenue")).toHaveLength(1);
  expect(screen.getByRole("button", { name: "Try again" })).toBeTruthy();
});

it.each([
  ["offline", "offline" as const],
  ["a server failure", [500, SERVER_ERROR] as [number, unknown]],
])(
  "keeps the week list's copy of a vehicle when its own week cannot load (%s)",
  async (_name, reply) => {
    const api = await signIn((routes) => {
      routes.on("setup/revenue", [200, revenueWeek]);
      routes.on(VEHICLE_WEEK, reply);
    });
    await openRevenue();
    await openWeek();
    await fireEvent.press(
      await screen.findByRole("button", { name: /^KDA 482M, KES 0/ }),
    );
    await waitFor(() => expect(api.sent(VEHICLE_WEEK)).toHaveLength(1));
    expect(
      await screen.findByLabelText(/^Mon 28: expected KES 1,000/),
    ).toBeTruthy();
    expect(screen.queryByText(SERVER_MESSAGE)).toBeNull();
    expect(screen.queryByText(/^No internet/)).toBeNull();
  },
);

it("says why a vehicle's week did not load when the API refuses it", async () => {
  await signIn((routes) => {
    routes.on("setup/revenue", [200, revenueWeek]);
    routes.on(VEHICLE_WEEK, [
      403,
      { title: "Forbidden", detail: "You may not view this vehicle's week." },
    ]);
  });
  await openRevenue();
  await openWeek();
  await fireEvent.press(
    await screen.findByRole("button", { name: /^KDA 482M, KES 0/ }),
  );
  expect(
    await screen.findByText("You may not view this vehicle's week."),
  ).toBeTruthy();
  expect(screen.getByLabelText(/^Mon 28: expected KES 1,000/)).toBeTruthy();
});

it("rings the focused capture field in the design's soft blue", async () => {
  await signIn((routes) => routes.on("setup/revenue", [200, revenueWeek]));
  await openRevenue();
  await fireEvent.press(
    await screen.findByRole("button", { name: "KDA 482M, Enter revenue" }),
  );
  const amount = await screen.findByLabelText("Revenue amount");
  expect(StyleSheet.flatten(amount.props.style).outlineWidth).toBe(0);
  await fireEvent(amount, "focus");
  const ring = StyleSheet.flatten(
    screen.getByLabelText("Revenue amount").props.style,
  );
  expect(ring.outlineColor).toBe(alpha(palette.blue, 0.35));
  expect(ring.outlineColor).toMatch(/^rgba\(/);
  expect(ring.borderColor).toBe(palette.blue);
  await fireEvent(screen.getByLabelText("Revenue amount"), "blur");
  expect(
    StyleSheet.flatten(screen.getByLabelText("Revenue amount").props.style)
      .outlineWidth,
  ).toBe(0);
});
