import { act, fireEvent, screen } from "@testing-library/react-native";
import { AppState } from "react-native";

import { ServerUnreachableError, apiGet } from "../src/lib/api";
import { saveSession } from "../src/lib/storage";
import { fakeApi, people } from "./fakeApi";
import { startApp, trustPhone, typePin } from "./helpers";

const OFFLINE_BANNER =
  "No internet. You are seeing what this phone saved at your last sign in.";
const UNREACHABLE =
  "Can't reach the XCODE server right now. Try again shortly.";
const ONLINE = { isConnected: true, isInternetReachable: true };
const network = () => require("expo-network");

// Only the clock the app's own timers run on: React's scheduler needs setImmediate and performance to stay real,
// or it stalls in the tests that follow.
function fakeTimers() {
  jest.useFakeTimers({
    doNotFake: [
      "nextTick",
      "queueMicrotask",
      "Date",
      "setImmediate",
      "clearImmediate",
      "performance",
      "hrtime",
    ],
  });
}

async function unlockOffline() {
  await trustPhone();
  const api = fakeApi();
  api.on("auth/unlock", "offline");
  api.on("auth/session", "offline");
  await startApp();
  await screen.findByText("Welcome back, Antony");
  await typePin("4826");
  await screen.findByText("Hi Antony");
  await screen.findByText(OFFLINE_BANNER);
  return api;
}

afterEach(() => {
  jest.useRealTimers();
});

describe("going back online after an offline unlock", () => {
  it("tries again every 30 seconds when the network never reports a change, and skips while the phone has no connection", async () => {
    fakeTimers();
    const api = await unlockOffline();

    await act(async () => jest.advanceTimersByTime(30_000));
    expect(api.sent("auth/session")).toHaveLength(0);
    expect(screen.getByText(OFFLINE_BANNER)).toBeTruthy();

    network().__setState(ONLINE);
    await act(async () => jest.advanceTimersByTime(29_000));
    expect(api.sent("auth/session")).toHaveLength(0);

    await act(async () => jest.advanceTimersByTime(1_000));
    expect(api.sent("auth/session")).toHaveLength(1);
    expect(screen.getByText(OFFLINE_BANNER)).toBeTruthy();

    api.on("auth/session", [200, people.owner]);
    await act(async () => jest.advanceTimersByTime(30_000));
    expect(api.sent("auth/session")).toHaveLength(2);
    await screen.findByText("Hi Antony");
    expect(screen.queryByText(OFFLINE_BANNER)).toBeNull();

    await act(async () => jest.advanceTimersByTime(120_000));
    expect(api.sent("auth/session")).toHaveLength(2);
  });

  it("tries again when the app returns to the foreground", async () => {
    const api = await unlockOffline();
    // The preset's AppState is a jest mock (cleared before each test), so its calls hold the app's listeners.
    const returnToApp = () =>
      jest
        .mocked(AppState.addEventListener)
        .mock.calls.filter(([type]) => type === "change")
        .forEach(([, handler]) => handler("active"));

    await act(async () => returnToApp());
    expect(api.sent("auth/session")).toHaveLength(0);

    network().__setState(ONLINE);
    api.on("auth/session", [200, people.owner]);
    await act(async () => returnToApp());
    expect(api.sent("auth/session")).toHaveLength(1);
    await screen.findByText("Hi Antony");
    expect(screen.queryByText(OFFLINE_BANNER)).toBeNull();
  });

  it("never runs two attempts at once", async () => {
    fakeTimers();
    const api = await unlockOffline();
    network().__setState(ONLINE);
    let answer: () => void = () => {};
    api.on(
      "auth/session",
      () =>
        new Promise<[number, unknown]>((resolve) => {
          answer = () => resolve([200, people.owner]);
        }),
    );

    await act(async () => jest.advanceTimersByTime(30_000));
    await act(async () => jest.advanceTimersByTime(30_000));
    await act(async () => network().__emit(ONLINE));
    expect(api.sent("auth/session")).toHaveLength(1);

    await act(async () => answer());
    await screen.findByText("Hi Antony");
    expect(screen.queryByText(OFFLINE_BANNER)).toBeNull();
  });

  it("locks the app when the session turns out to have ended", async () => {
    fakeTimers();
    const api = await unlockOffline();
    network().__setState(ONLINE);
    api.on("auth/session", [401, {}]);
    api.on("auth/refresh", [401, { status: "authentication_failed" }]);

    await act(async () => jest.advanceTimersByTime(30_000));
    await screen.findByText("Welcome back, Antony");
  });

  it("stops trying once the person locks the app", async () => {
    fakeTimers();
    const api = await unlockOffline();
    network().__setState(ONLINE);
    await fireEvent.press(screen.getByRole("button", { name: "Lock app" }));
    await screen.findByText("Welcome back, Antony");

    await act(async () => jest.advanceTimersByTime(120_000));
    expect(api.sent("auth/session")).toHaveLength(0);
  });
});

describe("what a failed call says", () => {
  async function keepSessionFor(path: string) {
    fakeApi().on(path, "offline");
    await saveSession({
      phoneNumber: "0712345678",
      accessToken: "access-0",
      refreshToken: "refresh-0",
    });
  }

  it("names the server when the phone has a connection but the request fails", async () => {
    network().__setState(ONLINE);
    await keepSessionFor("data");
    const failure = (await apiGet("data").catch(
      (error: Error) => error,
    )) as Error;
    expect(failure).toBeInstanceOf(ServerUnreachableError);
    expect(failure.message).toBe(UNREACHABLE);
  });

  it("still says no internet when the phone reports no connection, or no internet behind its network", async () => {
    await keepSessionFor("data");
    for (const state of [
      { isConnected: false, isInternetReachable: false },
      { isConnected: true, isInternetReachable: false },
    ]) {
      network().__setState(state);
      const failure = (await apiGet("data").catch(
        (error: Error) => error,
      )) as Error;
      expect(failure).not.toBeInstanceOf(ServerUnreachableError);
      expect(failure.message).toBe("No internet connection.");
    }
  });

  async function firstSignIn() {
    await startApp();
    await fireEvent.changeText(
      await screen.findByLabelText("Mobile number"),
      "0733520614",
    );
    await fireEvent.press(screen.getByText("Continue"));
    await screen.findByText("Enter the PIN for this number");
    await typePin("4826");
  }

  it("tells a new phone the server is unreachable when the phone itself is connected", async () => {
    network().__setState(ONLINE);
    fakeApi().on("auth/sign-in", "offline");
    await firstSignIn();
    await screen.findByText(UNREACHABLE);
    expect(screen.queryByText(/No internet/)).toBeNull();
  });

  it("tells a new phone there is no internet when the phone has no connection", async () => {
    fakeApi().on("auth/sign-in", "offline");
    await firstSignIn();
    await screen.findByText(
      "No internet. Signing in on this phone for the first time needs network.",
    );
    expect(screen.queryByText(UNREACHABLE)).toBeNull();
  });

  it("does not blame the internet when sign in meets a server error", async () => {
    network().__setState(ONLINE);
    fakeApi().on("auth/sign-in", [500, { title: "Internal Server Error" }]);
    await firstSignIn();
    await screen.findByText(/Something went wrong|service/i);
    expect(screen.queryByText(/No internet/)).toBeNull();
  });

  it("still unlocks with the phone's own PIN check when the server is unreachable", async () => {
    await trustPhone();
    network().__setState(ONLINE);
    fakeApi().on("auth/unlock", "offline");
    await startApp();
    await screen.findByText("Welcome back, Antony");
    await typePin("4826");
    await screen.findByText("Hi Antony");
    await screen.findByText(
      "Can't reach the XCODE server. You are seeing what this phone saved at your last sign in.",
    );
    expect(screen.queryByText(OFFLINE_BANNER)).toBeNull();
  });
});
