import { act, screen, waitFor } from "@testing-library/react-native";
import { AppState } from "react-native";

import { catalog, fakeApi, people, tokens } from "./fakeApi";
import { startApp, trustPhone, typePin } from "./helpers";

const comeBack = () =>
  act(async () => {
    jest
      .mocked(AppState.addEventListener)
      .mock.calls.filter(([type]) => type === "change")
      .forEach(([, handler]) => handler("active"));
  });

async function signedIn() {
  await trustPhone(people.owner, "0733520614");
  const api = fakeApi();
  api.on("auth/pin", [200, tokens(2)]);
  api.on("auth/session", [200, people.owner]);
  api.on("setup/access/catalog", [200, catalog]);
  await startApp();
  await screen.findByText("Welcome back, Antony");
  await typePin("4826");
  await screen.findByText("Hi Antony");
  return api;
}

let now = 1_000_000;
beforeEach(() => {
  now = 1_000_000;
  jest.spyOn(Date, "now").mockImplementation(() => now);
});
afterEach(() => jest.restoreAllMocks());

it("returns to the unlock pad when the app comes back and the server has ended the session", async () => {
  const api = await signedIn();
  const before = api.sent("auth/session").length;
  api.on("auth/session", [401, {}]);
  api.on("auth/refresh", [401, { status: "authentication_failed" }]);

  await comeBack();

  await waitFor(() => expect(api.sent("auth/refresh")).toHaveLength(1));
  expect(api.sent("auth/session").length).toBe(before + 1);
  await screen.findByText("Welcome back, Antony");
  expect(screen.queryByText("Hi Antony")).toBeNull();
});

it("stays signed in when the check answers 200, and asks at most once every 30 seconds", async () => {
  const api = await signedIn();
  const before = api.sent("auth/session").length;

  await comeBack();
  await waitFor(() =>
    expect(api.sent("auth/session")).toHaveLength(before + 1),
  );
  now += 29_000;
  await comeBack();
  expect(api.sent("auth/session")).toHaveLength(before + 1);
  now += 1_000;
  await comeBack();
  await waitFor(() =>
    expect(api.sent("auth/session")).toHaveLength(before + 2),
  );
  expect(screen.getByText("Hi Antony")).toBeTruthy();
});

it("stays signed in when the check cannot reach the server", async () => {
  const api = await signedIn();
  const before = api.sent("auth/session").length;
  api.on("auth/session", "offline");

  await comeBack();

  await waitFor(() =>
    expect(api.sent("auth/session")).toHaveLength(before + 1),
  );
  expect(api.sent("auth/refresh")).toHaveLength(0);
  expect(screen.getByText("Hi Antony")).toBeTruthy();
});
