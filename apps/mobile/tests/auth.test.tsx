import { act, fireEvent, screen, waitFor } from "@testing-library/react-native";
import { AppState } from "react-native";

import {
  OfflineError,
  SessionEndedError,
  apiGet,
  authApi,
  keepSession,
} from "../src/lib/api";
import {
  loadSession,
  matchesPinCheck,
  saveDeviceToken,
  saveOfflineTries,
  savePinCheck,
  saveSession,
} from "../src/lib/storage";
import { accessToken, fakeApi, people, tokens } from "./fakeApi";
import { startApp, storedText, trustPhone, typePin } from "./helpers";

const DEVICE = "stable-test-device";

const appearance = {
  organizationName: "Demo Fleet",
  settingsVersion: 1,
  businessDate: "2026-09-29",
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
    useGrouping: true,
    numberDecimals: 2,
  },
  themeMode: "system",
  reducedMotion: false,
  fontScale: 1,
};

it("signs in on a new phone with the PIN, then a one-time email code", async () => {
  const api = fakeApi();
  api.on("auth/start", [200, { status: "pin_required" }]);
  api.on("auth/pin", [
    202,
    {
      status: "verification_required",
      purpose: "new_device",
      maskedEmail: "a***@shamayah.co.ke",
      developmentCode: "481516",
    },
  ]);
  api.on("auth/code", [200, { ...tokens(), deviceToken: "device-token-1" }]);
  api.on("auth/session", [200, people.owner]);
  await startApp();

  await fireEvent.changeText(
    await screen.findByLabelText("Mobile number"),
    "+254 733 520614",
  );
  expect(screen.getByLabelText("Mobile number")).toHaveProp(
    "value",
    "0733 520 614",
  );
  await fireEvent.press(screen.getByText("Continue"));
  await screen.findByText("Enter the PIN for this number");
  await typePin("4826");

  await screen.findByText("Check your email");
  expect(screen.getByText("a***@shamayah.co.ke")).toBeTruthy();
  expect(screen.getByText("481 516")).toBeTruthy();
  await fireEvent.changeText(screen.getByLabelText("6 digit code"), "481516");

  await screen.findByText("Hi Antony");
  // Each step sends only its own fields, with no bearer, and the number goes in its local form.
  const device = { deviceId: DEVICE, deviceName: expect.any(String) };
  expect(api.sent("auth/start")).toEqual([
    { phoneNumber: "0733520614", ...device },
  ]);
  expect(api.sent("auth/pin")).toEqual([
    { phoneNumber: "0733520614", pin: "4826", ...device },
  ]);
  expect(api.sent("auth/code")).toEqual([
    {
      phoneNumber: "0733520614",
      purpose: "new_device",
      code: "481516",
      trustDevice: true,
      ...device,
    },
  ]);
  expect(
    api.calls.filter(
      ({ path }) => path.startsWith("auth/") && path !== "auth/session",
    ),
  ).not.toContainEqual(
    expect.objectContaining({
      headers: expect.objectContaining({ Authorization: expect.anything() }),
    }),
  );
  expect(storedText()).toContain("refresh-1");
  expect(storedText()).toContain("device-token-1");
  expect(storedText()).not.toContain("4826");
});

it("opens a trusted phone on its unlock pad and unlocks through the API", async () => {
  await trustPhone();
  const api = fakeApi();
  api.on("auth/pin", [200, tokens(2)]);
  api.on("auth/session", [200, people.owner]);
  await startApp();

  await screen.findByText("Welcome back, Antony");
  expect(screen.getByText("0733 ••• 614")).toBeTruthy();
  expect(screen.getByText("PIN unlock works without internet.")).toBeTruthy();
  await typePin("4826");

  await screen.findByText("Hi Antony");
  // The unlock signs in afresh: no start step, no refresh token and no bearer.
  expect(api.sent("auth/start")).toEqual([]);
  expect(api.sent("auth/pin")).toEqual([
    {
      phoneNumber: "0733520614",
      pin: "4826",
      deviceId: DEVICE,
      deviceName: expect.any(String),
    },
  ]);
  expect(storedText()).toContain("access-2");
});

it("counts wrong PINs, pauses after five, and resets the PIN with an email code", async () => {
  await trustPhone();
  const api = fakeApi();
  api.on("auth/pin", [401, { status: "authentication_failed" }]);
  await startApp();
  await screen.findByText("Welcome back, Antony");

  await typePin("1111");
  await screen.findByText("Wrong PIN. 4 tries left.");
  // Each attempt is checked before the keypad takes the next one.
  for (const left of ["3 tries", "2 tries", "1 try"]) {
    await typePin("1111");
    await screen.findByText(`Wrong PIN. ${left} left.`);
  }
  await typePin("1111");
  await screen.findByText("Sign in paused");
  expect(screen.getByText("15:00")).toBeTruthy();

  api.on("auth/pin/forgot", [
    202,
    {
      status: "verification_required",
      purpose: "pin_reset",
      developmentCode: "222333",
    },
  ]);
  api.on("auth/code", [200, { status: "code_verified" }]);
  await fireEvent.press(screen.getByText("Reset PIN"));
  await fireEvent.changeText(
    await screen.findByLabelText("6 digit code"),
    "222333",
  );

  await screen.findByText("Choose a new PIN");
  await typePin("1234");
  await screen.findByText("Too easy to guess. Choose different numbers.");
  // The server is the one that knows the old PIN.
  api.on("auth/pin/new", [
    400,
    { status: "invalid_pin", pinProblem: "unchanged" },
  ]);
  await typePin("4826");
  await screen.findByText("Type it again");
  await typePin("4826");
  await screen.findByText("Choose a PIN different from the old one.");
  await typePin("5937");
  await screen.findByText("Type it again");
  await typePin("5938");
  await screen.findByText("The two PINs did not match. Choose your PIN again.");

  api.on("auth/pin/new", [200, tokens(3)]);
  api.on("auth/session", [200, people.owner]);
  await typePin("5937");
  await screen.findByText("Type it again");
  await typePin("5937");
  await screen.findByText("Hi Antony");
  expect(api.sent("auth/pin/forgot")).toEqual([
    {
      phoneNumber: "0733520614",
      deviceId: DEVICE,
      deviceName: expect.any(String),
    },
  ]);
  expect(api.sent("auth/code")).toEqual([
    expect.objectContaining({
      purpose: "pin_reset",
      code: "222333",
      trustDevice: true,
    }),
  ]);
  expect(api.sent("auth/pin/new")).toEqual([
    expect.objectContaining({ pin: "4826" }),
    {
      phoneNumber: "0733520614",
      purpose: "pin_reset",
      code: "222333",
      pin: "5937",
      trustDevice: true,
      deviceId: DEVICE,
      deviceName: expect.any(String),
    },
  ]);
});

it("shows the server's pause with its remaining time", async () => {
  const api = fakeApi();
  api.on("auth/start", [200, { status: "pin_required" }]);
  api.on("auth/pin", [423, { status: "paused", retryAfterSeconds: 600 }]);
  await startApp();
  await fireEvent.changeText(
    await screen.findByLabelText("Mobile number"),
    "0712345678",
  );
  await fireEvent.press(screen.getByText("Continue"));
  await typePin(await screen.findByText("Enter your PIN").then(() => "2580"));
  await screen.findByText("Sign in paused");
  expect(screen.getByText("10:00")).toBeTruthy();
  expect(screen.getByText("Sign in as someone else")).toBeTruthy();
});

it("unlocks without internet against the PIN check the phone kept", async () => {
  await trustPhone();
  const api = fakeApi();
  api.on("auth/pin", "offline");
  await startApp();
  await screen.findByText("Welcome back, Antony");

  await typePin("9999");
  await screen.findByText("Wrong PIN. 4 tries left.");
  await typePin("4826");
  await screen.findByText("Hi Antony");
  expect(
    screen.getByText(
      "No internet. You are seeing what this phone saved at your last sign in.",
    ),
  ).toBeTruthy();
});

it.each([500, 503])(
  "unlocks offline when the server answers %i, as it does without internet",
  async (status) => {
    await trustPhone();
    const api = fakeApi();
    api.on("auth/pin", [status, { title: "Server error" }]);
    await startApp();
    await screen.findByText("Welcome back, Antony");

    await typePin("4826");
    await screen.findByText("Hi Antony");
    expect(
      screen.getByText(
        "No internet. You are seeing what this phone saved at your last sign in.",
      ),
    ).toBeTruthy();
    expect(
      screen.queryByText(
        "The service is not available right now. Try again shortly.",
      ),
    ).toBeNull();
  },
);

it("counts a wrong PIN as an offline try when the server answers 503 to an unlock", async () => {
  await trustPhone();
  fakeApi().on("auth/pin", [503, { title: "Service Unavailable" }]);
  await startApp();
  await screen.findByText("Welcome back, Antony");

  await typePin("9999");
  await screen.findByText("Wrong PIN. 4 tries left.");
  await typePin("9999");
  await screen.findByText("Wrong PIN. 3 tries left.");
  await typePin("4826");
  await screen.findByText("Hi Antony");
});

it("still says the service is unavailable when a first sign-in meets a server error", async () => {
  const api = fakeApi();
  api.on("auth/start", [200, { status: "pin_required" }]);
  api.on("auth/pin", [503, { title: "Service Unavailable" }]);
  await startApp();
  await fireEvent.changeText(
    await screen.findByLabelText("Mobile number"),
    "0733520614",
  );
  await fireEvent.press(screen.getByText("Continue"));
  await screen.findByText("Enter the PIN for this number");
  await typePin("4826");

  await screen.findByText(
    "The service is not available right now. Try again shortly.",
  );
  expect(screen.queryByText("Hi Antony")).toBeNull();
});

// After the person's number changed elsewhere, the server refuses the old number with the PIN they still know.
it("does not count the PIN the phone knows as wrong when the server refuses it", async () => {
  await trustPhone();
  fakeApi().on("auth/pin", [401, { status: "authentication_failed" }]);
  await startApp();
  await screen.findByText("Welcome back, Antony");

  await typePin("4826");
  await screen.findByText(
    'This phone can no longer unlock with your PIN. If your mobile number changed, choose "Not you? Switch user" and sign in again.',
  );
  await typePin("1111");
  await screen.findByText("Wrong PIN. 4 tries left.");
});

it("follows the organization's wrong-PIN policy offline, as the phone last loaded it", async () => {
  await trustPhone();
  const api = fakeApi();
  api.on("auth/pin", [200, tokens(2)]);
  api.on("auth/session", [200, people.owner]);
  api.on("setup/access/catalog", [200, []]);
  api.on("setup/appearance", [
    200,
    { ...appearance, lockoutThreshold: 3, lockoutMinutes: 60 },
  ]);
  await startApp();
  await screen.findByText("Welcome back, Antony");
  await typePin("4826");
  await screen.findByText("Hi Antony");
  await waitFor(() => expect(storedText()).toContain('"lockoutThreshold":3'));

  await fireEvent.press(screen.getByRole("button", { name: "Lock app" }));
  api.on("auth/pin", "offline");
  await typePin("1111");
  await screen.findByText("Wrong PIN. 2 tries left.");
  await typePin("1111");
  await screen.findByText("Wrong PIN. 1 try left.");
  await typePin("1111");
  await screen.findByText("Sign in paused");
  expect(screen.getByText("60:00")).toBeTruthy();
});

it("pauses offline after five wrong PINs for 15 minutes when the phone has no policy saved", async () => {
  await trustPhone();
  fakeApi().on("auth/pin", "offline");
  await startApp();
  await screen.findByText("Welcome back, Antony");
  for (const left of ["4 tries", "3 tries", "2 tries", "1 try"]) {
    await typePin("1111");
    await screen.findByText(`Wrong PIN. ${left} left.`);
  }
  await typePin("1111");
  await screen.findByText("Sign in paused");
  expect(screen.getByText("15:00")).toBeTruthy();
});

it("deletes the phone's PIN check at the offline limit, so only an online unlock opens it again", async () => {
  await trustPhone();
  fakeApi().on("auth/pin", "offline");
  await startApp();
  await screen.findByText("Welcome back, Antony");
  for (const left of ["4 tries", "3 tries", "2 tries", "1 try"]) {
    await typePin("1111");
    await screen.findByText(`Wrong PIN. ${left} left.`);
  }
  expect(storedText()).toContain('"salt"');
  await typePin("1111");
  await screen.findByText("Sign in paused");
  await waitFor(() => expect(storedText()).not.toContain('"salt"'));
});

it("sets a first PIN with an email code and meets the organization's minimum length", async () => {
  const api = fakeApi();
  api.on("auth/start", [
    202,
    {
      status: "verification_required",
      purpose: "first_setup",
      developmentCode: "123123",
    },
  ]);
  api.on("auth/code", [200, { status: "code_verified" }]);
  let completes = 0;
  api.on("auth/pin/new", () =>
    ++completes === 1
      ? [400, { status: "invalid_pin", minimumPinLength: 6 }]
      : [200, tokens()],
  );
  api.on("auth/session", [200, people.manager]);
  await startApp();

  await fireEvent.changeText(
    await screen.findByLabelText("Mobile number"),
    "0700111222",
  );
  await fireEvent.press(screen.getByText("Continue"));
  await fireEvent.changeText(
    await screen.findByLabelText("6 digit code"),
    "123123",
  );
  await screen.findByText("Choose your PIN");
  await typePin("5937");
  await screen.findByText("Type it again");
  await typePin("5937");

  await screen.findByText(
    "Your organization needs a PIN of at least 6 numbers.",
  );
  expect(screen.getByLabelText("0 of 6 numbers entered")).toBeTruthy();
  await typePin("593718");
  await screen.findByText("Type it again");
  await typePin("593718");
  await screen.findByText("Hi Brian");
  expect(api.sent("auth/pin/new").map((body) => body.pin)).toEqual([
    "5937",
    "593718",
  ]);
});

it("holds the keypad while a new PIN is being saved, so a second entry sends no second request", async () => {
  const api = fakeApi();
  api.on("auth/start", [
    202,
    {
      status: "verification_required",
      purpose: "first_setup",
      developmentCode: "123123",
    },
  ]);
  api.on("auth/code", [200, { status: "code_verified" }]);
  let saved = () => {};
  api.on(
    "auth/pin/new",
    () =>
      new Promise<[number, unknown]>((resolve) => {
        saved = () => resolve([200, tokens()]);
      }),
  );
  api.on("auth/session", [200, people.manager]);
  await startApp();

  await fireEvent.changeText(
    await screen.findByLabelText("Mobile number"),
    "0700111222",
  );
  await fireEvent.press(screen.getByText("Continue"));
  await fireEvent.changeText(
    await screen.findByLabelText("6 digit code"),
    "123123",
  );
  await screen.findByText("Choose your PIN");
  await typePin("5937");
  await screen.findByText("Type it again");
  await typePin("5937");
  await waitFor(() => expect(api.sent("auth/pin/new")).toHaveLength(1));

  expect(screen.getByRole("button", { name: "1" })).toBeDisabled();
  await typePin("5937");
  await act(() => new Promise((resolve) => setTimeout(resolve, 300)));
  expect(screen.getByLabelText("0 of 4 numbers entered")).toBeTruthy();
  expect(api.sent("auth/pin/new")).toHaveLength(1);

  await act(async () => saved());
  await screen.findByText("Hi Brian");
  expect(api.sent("auth/pin/new")).toHaveLength(1);
});

it("holds the keypad while an offline unlock is being checked", async () => {
  await trustPhone();
  fakeApi().on("auth/pin", "offline");
  await startApp();
  await screen.findByText("Welcome back, Antony");

  let matched: (match: boolean) => void = () => {};
  const check = jest
    .spyOn(require("../src/lib/storage"), "matchesPinCheck")
    .mockImplementation(
      () =>
        new Promise<boolean>((resolve) => {
          matched = resolve;
        }),
    );
  try {
    await typePin("4826");
    await waitFor(() => expect(check).toHaveBeenCalledTimes(1));
    expect(screen.getByRole("button", { name: "1" })).toBeDisabled();
    await act(async () => matched(true));
    await screen.findByText("Hi Antony");
  } finally {
    check.mockRestore();
  }
});

it("wakes the server when the first digit of a PIN is typed", async () => {
  await trustPhone();
  fakeApi().on("auth/pin", [200, tokens()]);
  await startApp();
  await screen.findByText("Welcome back, Antony");
  const wake = jest.spyOn(require("../src/lib/api"), "wakeServer");
  try {
    await typePin("4");
    expect(wake).toHaveBeenCalledTimes(1);
    await typePin("82");
    expect(wake).toHaveBeenCalledTimes(1);
  } finally {
    wake.mockRestore();
  }
});

it("shows at once that the PIN is being checked", async () => {
  await trustPhone();
  const api = fakeApi();
  let answer = () => {};
  api.on(
    "auth/pin",
    () =>
      new Promise<[number, unknown]>((resolve) => {
        answer = () => resolve([200, tokens()]);
      }),
  );
  api.on("auth/session", [200, people.owner]);
  await startApp();
  await screen.findByText("Welcome back, Antony");

  await typePin("4826");
  expect(
    await screen.findByRole("progressbar", { name: "Checking your PIN…" }),
  ).toBeTruthy();
  expect(screen.getByRole("button", { name: "1" })).toBeDisabled();
  await act(async () => answer());
  await screen.findByText("Hi Antony");
  expect(screen.queryByText("Checking your PIN…")).toBeNull();
});

it("replaces a check from an earlier version at the next online unlock, so the phone unlocks offline again", async () => {
  await trustPhone();
  const items = require("expo-secure-store").__items as Map<string, string>;
  items.set(
    "xcode.pin-check",
    JSON.stringify({
      version: 2,
      salt: "07".repeat(16),
      hash: "ab".repeat(32),
    }),
  );
  const api = fakeApi();
  api.on("auth/pin", [200, tokens()]);
  api.on("auth/session", [200, people.owner]);
  await startApp();
  await screen.findByText("Welcome back, Antony");
  await typePin("4826");
  await screen.findByText("Hi Antony");
  expect(await matchesPinCheck("4826")).toBe(true);
  expect(await matchesPinCheck("4827")).toBe(false);
});

it("does not compute the PIN check again when an unlock shows the PIN has not changed", async () => {
  const token = accessToken(people.owner.userId, 7);
  await trustPhone();
  await savePinCheck("4826", token);
  const api = fakeApi();
  api.on("auth/pin", [200, { ...tokens(), accessToken: token }]);
  api.on("auth/session", [200, people.owner]);
  const digest = jest.spyOn(require("expo-crypto"), "digest");
  try {
    await startApp();
    await screen.findByText("Welcome back, Antony");
    await typePin("4826");
    await screen.findByText("Hi Antony");
    expect(digest).not.toHaveBeenCalled();
    expect(await matchesPinCheck("4826")).toBe(true);
  } finally {
    digest.mockRestore();
  }
});

it("tells the person how many code tries are left", async () => {
  const api = fakeApi();
  api.on("auth/start", [200, { status: "pin_required" }]);
  api.on("auth/pin", [
    202,
    {
      status: "verification_required",
      purpose: "new_device",
      maskedEmail: "w***@zurigenesis.co.ke",
    },
  ]);
  api.on("auth/code", [401, { status: "authentication_failed", triesLeft: 2 }]);
  await startApp();
  await fireEvent.changeText(
    await screen.findByLabelText("Mobile number"),
    "0712345678",
  );
  await fireEvent.press(screen.getByText("Continue"));
  await screen.findByText("Enter your PIN");
  await typePin("2580");
  await fireEvent.changeText(
    await screen.findByLabelText("6 digit code"),
    "000000",
  );
  await screen.findByText("That code is wrong. 2 tries left.");
  expect(screen.getByLabelText("6 digit code")).toHaveProp("value", "");

  // The server voided the code at the third wrong try and emailed a new one.
  api.on("auth/code", [200, { status: "code_resent" }]);
  await fireEvent.changeText(screen.getByLabelText("6 digit code"), "000001");
  await screen.findByText(
    "That code was wrong 3 times, so we emailed you a new one.",
  );
  expect(screen.getByText("w***@zurigenesis.co.ke")).toBeTruthy();

  // An expired or replaced code leaves no tries: only a new one helps.
  api.on("auth/code", [
    401,
    { status: "authentication_failed", triesLeft: null },
  ]);
  await fireEvent.changeText(screen.getByLabelText("6 digit code"), "000002");
  await screen.findByText("This code no longer works. Tap Send a new code.");
});

it("accepts a PIN longer than four numbers on a new phone", async () => {
  const api = fakeApi();
  api.on("auth/start", [200, { status: "pin_required" }]);
  api.on("auth/pin", [200, tokens()]);
  api.on("auth/session", [200, people.clerk]);
  await startApp();
  await fireEvent.changeText(
    await screen.findByLabelText("Mobile number"),
    "0712345678",
  );
  await fireEvent.press(screen.getByText("Continue"));
  await fireEvent.press(
    await screen.findByText("My PIN has more than 4 numbers"),
  );
  await typePin("258036");
  await fireEvent.press(screen.getByText("Continue"));
  await screen.findByText("Hi Wanjiru");
  expect(api.sent("auth/pin")[0].pin).toBe("258036");
});

it("switch user stops trusting the phone and returns to sign in", async () => {
  await trustPhone();
  await saveDeviceToken("device-token-7");
  const api = fakeApi();
  api.on(`auth/devices/${DEVICE}/revoke`, [200, { status: "device_revoked" }]);
  await startApp();
  await fireEvent.press(await screen.findByText("Not you? Switch user"));
  await screen.findByText("Sign in");
  expect(storedText()).not.toContain("device-token-7");
  expect(
    api.calls.find((call) => call.path.endsWith("/revoke"))?.headers
      .Authorization,
  ).toBe("Bearer access-0");
  expect(storedText()).not.toContain("refresh-0");
  expect(storedText()).not.toContain("Antony");
});

// D7: a trusted phone opens on its PIN alone only while it has been online in the last 72 hours.
const HOURS = 60 * 60 * 1000;

it("stops unlocking offline after 72 hours away from the server, and says to connect", async () => {
  await trustPhone(people.owner, "0733520614", "4826", Date.now() - 73 * HOURS);
  fakeApi().on("auth/pin", "offline");
  await startApp();
  await screen.findByText("Welcome back, Antony");

  await typePin("4826");
  await screen.findByText(
    "This phone has been offline for more than 72 hours. Connect to the internet and unlock once to carry on. Anything waiting to be sent is kept.",
  );
  // Refused for being stale, not for a wrong PIN: no try is counted against the person.
  expect(screen.queryByText("Wrong PIN. 4 tries left.")).toBeNull();
  expect(screen.queryByText("Hi Antony")).toBeNull();
});

it("still unlocks offline inside the 72 hours", async () => {
  await trustPhone(people.owner, "0733520614", "4826", Date.now() - 71 * HOURS);
  fakeApi().on("auth/pin", "offline");
  await startApp();
  await screen.findByText("Welcome back, Antony");

  await typePin("4826");
  await screen.findByText("Hi Antony");
});

it("starts the 72 hours from now for a phone that signed in before the rule shipped", async () => {
  // A Phase 1 session has no record of when the phone was last online; it must not lock anyone out at once.
  await trustPhone();
  fakeApi().on("auth/pin", "offline");
  await startApp();
  await screen.findByText("Welcome back, Antony");

  await typePin("4826");
  await screen.findByText("Hi Antony");
});

it("puts the offline window back on the clock after signing in online", async () => {
  await trustPhone(people.owner, "0733520614", "4826", Date.now() - 80 * HOURS);
  const api = fakeApi();
  api.on("auth/pin", [200, tokens()]);
  api.on("auth/session", [200, people.owner]);
  await startApp();
  await screen.findByText("Welcome back, Antony");

  await typePin("4826");
  await screen.findByText("Hi Antony");
  const saved = JSON.parse(
    (require("expo-secure-store").__items as Map<string, string>).get(
      "xcode.session",
    )!,
  );
  expect(Date.now() - saved.lastOnlineAt).toBeLessThan(5 * 60 * 1000);
});

it("stays on the auth screen when fetching the person fails after sign-in", async () => {
  const api = fakeApi();
  api.on("auth/start", [200, { status: "pin_required" }]);
  api.on("auth/pin", [200, tokens()]);
  api.on("auth/session", [500, { title: "Internal Server Error" }]);
  await startApp();
  await fireEvent.changeText(
    await screen.findByLabelText("Mobile number"),
    "0712345678",
  );
  await fireEvent.press(screen.getByText("Continue"));
  await typePin("2580");
  await screen.findByText(
    "Signed in, but your profile could not be loaded. Check your connection and try again.",
  );
  expect(screen.queryByText("Hi Wanjiru")).toBeNull();
});

const PROFILE_ERROR =
  "Signed in, but your profile could not be loaded. Check your connection and try again.";
const PROFILE_ERROR_AFTER_CODE =
  "Signed in, but your profile could not be loaded. Enter your PIN to try again.";
const UNEXPECTED =
  "The service answered in a way this app does not understand. Try again shortly.";

// The first person fetch fails, the next ones succeed.
const failsOnce = (person: unknown) => {
  let fetches = 0;
  return () =>
    ++fetches === 1
      ? ([500, { title: "Internal Server Error" }] as [number, unknown])
      : ([200, person] as [number, unknown]);
};

it("asks for the PIN again when fetching the person fails after a new phone's code is confirmed", async () => {
  const api = fakeApi();
  let signIns = 0;
  api.on("auth/start", [200, { status: "pin_required" }]);
  api.on("auth/pin", () =>
    ++signIns === 1
      ? [
          202,
          {
            status: "verification_required",
            purpose: "new_device",
            maskedEmail: "w***@zurigenesis.co.ke",
          },
        ]
      : [200, tokens(2)],
  );
  api.on("auth/code", [200, tokens()]);
  api.on("auth/session", failsOnce(people.clerk));
  await startApp();
  await fireEvent.changeText(
    await screen.findByLabelText("Mobile number"),
    "0712345678",
  );
  await fireEvent.press(screen.getByText("Continue"));
  await typePin("2580");
  await fireEvent.changeText(
    await screen.findByLabelText("6 digit code"),
    "481516",
  );

  await screen.findByText(PROFILE_ERROR_AFTER_CODE);
  expect(screen.queryByText("Check your email")).toBeNull();
  expect(screen.getByText("Enter the PIN for this number")).toBeTruthy();
  expect(screen.queryByText("Hi Wanjiru")).toBeNull();

  await typePin("2580");
  await screen.findByText("Hi Wanjiru");
  expect(api.sent("auth/code")).toHaveLength(1);
  expect(api.sent("auth/pin")).toHaveLength(2);
  expect(storedText()).toContain("access-2");
});

it("signs in with the new PIN when fetching the person fails after a first PIN is saved", async () => {
  const api = fakeApi();
  api.on("auth/start", [
    202,
    {
      status: "verification_required",
      purpose: "first_setup",
      developmentCode: "123123",
    },
  ]);
  api.on("auth/code", [200, { status: "code_verified" }]);
  api.on("auth/pin/new", [200, { ...tokens(), deviceToken: "device-token-1" }]);
  api.on("auth/session", failsOnce(people.manager));
  api.on("auth/pin", [200, tokens(2)]);
  await startApp();
  await fireEvent.changeText(
    await screen.findByLabelText("Mobile number"),
    "0700111222",
  );
  await fireEvent.press(screen.getByText("Continue"));
  await fireEvent.changeText(
    await screen.findByLabelText("6 digit code"),
    "123123",
  );
  await screen.findByText("Choose your PIN");
  await typePin("5937");
  await screen.findByText("Type it again");
  await typePin("5937");

  await screen.findByText(PROFILE_ERROR_AFTER_CODE);
  expect(screen.getByText("Enter the PIN for this number")).toBeTruthy();
  expect(
    screen.queryByText("This code no longer works. Tap Send a new code."),
  ).toBeNull();
  await typePin("5937");
  await screen.findByText("Hi Brian");
  expect(api.sent("auth/code")).toHaveLength(1);
  expect(api.sent("auth/pin/new")).toHaveLength(1);
  expect(api.sent("auth/pin/new")[0]).toMatchObject({
    purpose: "first_setup",
    code: "123123",
    trustDevice: true,
  });
  expect(api.sent("auth/pin")).toEqual([
    {
      phoneNumber: "0700111222",
      pin: "5937",
      deviceId: DEVICE,
      deviceName: expect.any(String),
      deviceToken: "device-token-1",
    },
  ]);
});

it("unlocks with the new PIN when fetching the person fails after a PIN reset", async () => {
  await trustPhone();
  const api = fakeApi();
  api.on("auth/pin/forgot", [
    202,
    {
      status: "verification_required",
      purpose: "pin_reset",
      developmentCode: "222333",
    },
  ]);
  api.on("auth/code", [200, { status: "code_verified" }]);
  api.on("auth/pin/new", [200, tokens(3)]);
  api.on("auth/session", failsOnce(people.owner));
  api.on("auth/pin", [200, tokens(4)]);
  await startApp();
  await fireEvent.press(await screen.findByText("Forgot PIN?"));
  await fireEvent.changeText(
    await screen.findByLabelText("6 digit code"),
    "222333",
  );
  await screen.findByText("Choose a new PIN");
  await typePin("5937");
  await screen.findByText("Type it again");
  await typePin("5937");

  await screen.findByText(PROFILE_ERROR_AFTER_CODE);
  await screen.findByText("Welcome back, Antony");
  await typePin("5937");
  await screen.findByText("Hi Antony");
  expect(api.sent("auth/code")).toHaveLength(1);
  expect(api.sent("auth/pin/new")).toHaveLength(1);
  expect(api.sent("auth/pin")).toHaveLength(1);
  expect(api.sent("auth/pin")[0]).toMatchObject({ pin: "5937" });
  expect(api.sent("auth/pin")[0]).not.toHaveProperty("code");
  expect(storedText()).toContain("access-4");
});

describe("an answer the app does not expect", () => {
  async function toThePad(api: ReturnType<typeof fakeApi>) {
    api.on("auth/start", [200, { status: "pin_required" }]);
    await startApp();
    await fireEvent.changeText(
      await screen.findByLabelText("Mobile number"),
      "0712345678",
    );
    await fireEvent.press(screen.getByText("Continue"));
    await screen.findByText("Enter the PIN for this number");
  }

  async function toTheCode(api: ReturnType<typeof fakeApi>) {
    api.on("auth/start", [
      202,
      { status: "verification_required", purpose: "first_setup" },
    ]);
    await startApp();
    await fireEvent.changeText(
      await screen.findByLabelText("Mobile number"),
      "0700111222",
    );
    await fireEvent.press(screen.getByText("Continue"));
    return screen.findByLabelText("6 digit code");
  }

  it("says so on the pad when a sign-in is answered with another status, and counts no wrong PIN", async () => {
    const api = fakeApi();
    api.on("auth/pin", [200, { status: "check_email" }]);
    await toThePad(api);
    await typePin("2580");
    await screen.findByText(UNEXPECTED);
    expect(screen.getByLabelText("0 of 4 numbers entered")).toBeTruthy();

    api.on("auth/pin", [401, { status: "authentication_failed" }]);
    await typePin("1111");
    await screen.findByText("Wrong PIN. 4 tries left.");
  });

  it("says so on the pad when an unlock is answered with another status, and counts no wrong PIN", async () => {
    await trustPhone();
    const api = fakeApi();
    api.on("auth/pin", [200, { status: "check_email" }]);
    await startApp();
    await screen.findByText("Welcome back, Antony");
    await typePin("4826");
    await screen.findByText(UNEXPECTED);
    expect(screen.queryByText("Hi Antony")).toBeNull();
    expect(screen.getByLabelText("0 of 4 numbers entered")).toBeTruthy();

    api.on("auth/pin", [401, { status: "authentication_failed" }]);
    await typePin("1111");
    await screen.findByText("Wrong PIN. 4 tries left.");
  });

  it("says so on the number step when a request for a code is answered with another status", async () => {
    const api = fakeApi();
    api.on("auth/start", [200, { status: "authenticated" }]);
    await startApp();
    await fireEvent.changeText(
      await screen.findByLabelText("Mobile number"),
      "0700111222",
    );
    await fireEvent.press(screen.getByText("Continue"));
    await screen.findByText(UNEXPECTED);
    expect(screen.queryByText("Check your email")).toBeNull();
    expect(screen.getByLabelText("Mobile number")).toBeTruthy();
  });

  it.each([
    [{ status: "verification_required", purpose: "new_device" }],
    [{ status: "verification_required" }],
  ])(
    "says so on the number step when the number is answered with %j",
    async (answer) => {
      const api = fakeApi();
      api.on("auth/start", [202, answer]);
      await startApp();
      await fireEvent.changeText(
        await screen.findByLabelText("Mobile number"),
        "0700111222",
      );
      await fireEvent.press(screen.getByText("Continue"));
      await screen.findByText(UNEXPECTED);
      expect(screen.queryByText("Check your email")).toBeNull();
    },
  );

  it("says so on the code step when a code is verified with another status, and counts no wrong code", async () => {
    const api = fakeApi();
    api.on("auth/code", [200, { status: "check_email" }]);
    await fireEvent.changeText(await toTheCode(api), "123123");
    await screen.findByText(UNEXPECTED);
    expect(screen.queryByText("Choose your PIN")).toBeNull();

    api.on("auth/code", [
      401,
      { status: "authentication_failed", triesLeft: 4 },
    ]);
    await fireEvent.changeText(screen.getByLabelText("6 digit code"), "000000");
    await screen.findByText("That code is wrong. 4 tries left.");
  });

  it("says so on the pad when a new PIN is saved with another status", async () => {
    const api = fakeApi();
    api.on("auth/code", [200, { status: "code_verified" }]);
    api.on("auth/pin/new", [200, { status: "code_verified" }]);
    await fireEvent.changeText(await toTheCode(api), "123123");
    await screen.findByText("Choose your PIN");
    await typePin("5937");
    await screen.findByText("Type it again");
    await typePin("5937");
    await screen.findByText(UNEXPECTED);
    expect(screen.getByLabelText("0 of 4 numbers entered")).toBeTruthy();
    expect(
      screen.queryByText("This code no longer works. Tap Send a new code."),
    ).toBeNull();
  });

  it("says so on the code step when a new phone's code is confirmed with another status", async () => {
    const api = fakeApi();
    api.on("auth/pin", [
      202,
      { status: "verification_required", purpose: "new_device" },
    ]);
    api.on("auth/code", [200, { status: "check_email" }]);
    await toThePad(api);
    await typePin("2580");
    await fireEvent.changeText(
      await screen.findByLabelText("6 digit code"),
      "481516",
    );
    await screen.findByText(UNEXPECTED);
    expect(screen.getByText("Check your email")).toBeTruthy();
    expect(api.sent("auth/code")).toHaveLength(1);
  });

  it("says so when the sign-in is accepted but carries no tokens", async () => {
    const api = fakeApi();
    api.on("auth/pin", [200, { status: "authenticated" }]);
    api.on("auth/session", [200, people.clerk]);
    await toThePad(api);
    await typePin("2580");
    await screen.findByText(PROFILE_ERROR);
    expect(screen.queryByText("Hi Wanjiru")).toBeNull();
    expect(await loadSession()).toBeNull();
  });
});

it("refuses to keep a session that has no tokens", async () => {
  await expect(
    keepSession("0712345678", { status: "authenticated", accessToken: "a" }),
  ).rejects.toMatchObject({
    response: { status: "unexpected_response" },
  });
  await expect(
    keepSession("0712345678", { status: "authenticated", refreshToken: "r" }),
  ).rejects.toMatchObject({
    response: { status: "unexpected_response" },
  });
  expect(await loadSession()).toBeNull();
});

it("shows why a reset could not start on the paused screen", async () => {
  await trustPhone();
  const api = fakeApi();
  api.on("auth/pin", [423, { status: "paused", retryAfterSeconds: 600 }]);
  api.on("auth/pin/forgot", "offline");
  await startApp();
  await screen.findByText("Welcome back, Antony");
  await typePin("1111");
  await screen.findByText("Sign in paused");

  await fireEvent.press(screen.getByText("Reset PIN"));
  await screen.findByText("No internet. Sending a code needs network.");
  expect(screen.getByText("Sign in paused")).toBeTruthy();

  api.on("auth/pin/forgot", [429, {}]);
  await fireEvent.press(screen.getByText("Reset PIN"));
  await screen.findByText("Too many requests. Please wait a minute.");
});

it("shows the pause again when a trusted phone starts inside one it kept", async () => {
  await trustPhone();
  await saveOfflineTries({
    count: 0,
    pausedUntil: Date.now() + 10 * 60 * 1000,
  });
  fakeApi();
  await startApp();
  await screen.findByText("Sign in paused");
});

it("does not leave the app busy when switching user fails", async () => {
  await trustPhone();
  const api = fakeApi();
  api.on(`auth/devices/${DEVICE}/revoke`, [200, { status: "device_revoked" }]);
  const forget = jest
    .spyOn(require("../src/lib/storage"), "forgetPerson")
    .mockRejectedValueOnce(new Error("keychain unavailable"));
  try {
    await startApp();
    await fireEvent.press(await screen.findByText("Not you? Switch user"));
    await screen.findByText("Something went wrong. Please try again.");
    expect(screen.getByRole("button", { name: "1" })).not.toBeDisabled();
    expect(screen.getByText("Welcome back, Antony")).toBeTruthy();

    await fireEvent.press(screen.getByText("Not you? Switch user"));
    await screen.findByText("Sign in");
  } finally {
    forget.mockRestore();
  }
});

it("holds the keypad while a code is requested from the pad", async () => {
  await trustPhone();
  const api = fakeApi();
  let sent = () => {};
  api.on(
    "auth/pin/forgot",
    () =>
      new Promise<[number, unknown]>((resolve) => {
        sent = () =>
          resolve([
            202,
            { status: "verification_required", purpose: "pin_reset" },
          ]);
      }),
  );
  await startApp();
  await fireEvent.press(await screen.findByText("Forgot PIN?"));
  await waitFor(() => expect(api.sent("auth/pin/forgot")).toHaveLength(1));
  expect(screen.getByRole("button", { name: "1" })).toBeDisabled();
  await fireEvent.press(screen.getByText("Forgot PIN?"));
  expect(api.sent("auth/pin/forgot")).toHaveLength(1);
  await act(async () => sent());
  await screen.findByText("Check your email");
});

it("locks again when the app goes to the background", async () => {
  // Every listener hears the change, as AppState tells them all.
  const handlers: ((state: "active" | "background") => void)[] = [];
  const change = (state: "active" | "background") =>
    handlers.forEach((handler) => handler(state));
  // jest-expo's addEventListener is already a mock: restoring a spy on it would leave it answering undefined for
  // every later test, so the original is put back instead.
  const original = AppState.addEventListener;
  AppState.addEventListener = ((
    _: string,
    handler: (state: "active" | "background") => void,
  ) => {
    handlers.push(handler);
    return { remove: jest.fn() };
  }) as unknown as typeof AppState.addEventListener;
  try {
    await trustPhone();
    const api = fakeApi();
    api.on("auth/pin", [200, tokens(2)]);
    api.on("auth/session", [200, people.owner]);
    await startApp();
    await screen.findByText("Welcome back, Antony");
    await typePin("4826");
    await screen.findByText("Hi Antony");
    await act(() => change("background"));
    await screen.findByText("Welcome back, Antony");
    expect(screen.getByLabelText("0 of 4 numbers entered")).toBeTruthy();
  } finally {
    AppState.addEventListener = original;
  }
});

async function expiredAccess(
  refresh: Parameters<ReturnType<typeof fakeApi>["on"]>[1],
) {
  await saveSession({
    phoneNumber: "0712345678",
    accessToken: "access-0",
    refreshToken: "refresh-0",
  });
  const api = fakeApi();
  api.on("data", [401, {}]);
  api.on("auth/refresh", refresh);
  return api;
}

it("sends every request with a timeout signal", async () => {
  const api = fakeApi();
  api.on("auth/pin", [200, tokens()]);
  await saveSession({
    phoneNumber: "0712345678",
    accessToken: "access-0",
    refreshToken: "refresh-0",
  });
  await authApi("pin", { phoneNumber: "0712345678", pin: "2580" });
  const init = (globalThis.fetch as jest.Mock).mock.calls[0][1] as RequestInit;
  expect(init.signal).toBeInstanceOf(AbortSignal);
});

it("keeps the session when the server fails while renewing the access token", async () => {
  await expiredAccess([500, { title: "Internal Server Error" }]);
  await expect(apiGet("data")).rejects.toBeInstanceOf(OfflineError);
  expect((await loadSession())?.refreshToken).toBe("refresh-0");
});

it("keeps the session when renewing the access token is rate limited", async () => {
  await expiredAccess([429, {}]);
  await expect(apiGet("data")).rejects.toBeInstanceOf(OfflineError);
  expect(await loadSession()).not.toBeNull();
});

it("ends the session when renewing the access token is refused", async () => {
  await expiredAccess([401, { status: "authentication_failed" }]);
  await expect(apiGet("data")).rejects.toBeInstanceOf(SessionEndedError);
});

it("carries on with the session another request renewed when the refresh token was just rotated", async () => {
  const api = await expiredAccess(async () => {
    await saveSession({
      phoneNumber: "0712345678",
      accessToken: "access-9",
      refreshToken: "refresh-9",
    });
    return [401, { status: "refresh_superseded" }];
  });
  api.on("data", (_body, headers) =>
    headers.Authorization === "Bearer access-9"
      ? [200, { ok: true }]
      : [401, {}],
  );
  await expect(apiGet("data")).resolves.toEqual({ ok: true });
  expect((await loadSession())?.refreshToken).toBe("refresh-9");
});

it("ends the session when the refresh token was rotated and no newer one is stored", async () => {
  await expiredAccess([401, { status: "refresh_superseded" }]);
  await expect(apiGet("data")).rejects.toBeInstanceOf(SessionEndedError);
});

it("sends the trusted-device token only with the steps that take a PIN", async () => {
  await saveDeviceToken("device-token-7");
  const api = fakeApi();
  for (const step of [
    "start",
    "pin",
    "code",
    "code/resend",
    "pin/forgot",
    "pin/new",
  ] as const)
    await authApi(step, { phoneNumber: "0712345678" }).catch(() => undefined);
  expect(api.sent("auth/start")[0]).toMatchObject({
    deviceToken: "device-token-7",
  });
  expect(api.sent("auth/pin")[0]).toMatchObject({
    deviceToken: "device-token-7",
  });
  for (const path of [
    "auth/code",
    "auth/code/resend",
    "auth/pin/forgot",
    "auth/pin/new",
  ])
    expect(api.sent(path)[0]).not.toHaveProperty("deviceToken");
});

it("asks for the code from the invitation email when the number has one, and offers no first-time link", async () => {
  const api = fakeApi();
  api.on("auth/start", [
    202,
    {
      status: "verification_required",
      purpose: "first_setup",
      maskedEmail: "b***@example.com",
      invitation: true,
    },
  ]);
  api.on("auth/code", [200, { status: "code_verified" }]);
  await startApp();
  await screen.findByLabelText("Mobile number");
  expect(screen.queryByText("First time here? Set your PIN")).toBeNull();
  await fireEvent.changeText(
    screen.getByLabelText("Mobile number"),
    "0700111222",
  );
  await fireEvent.press(screen.getByText("Continue"));

  await screen.findByText(/Type the code from your XCODE invitation email/);
  expect(screen.queryByText(/We sent a code/)).toBeNull();
  await fireEvent.changeText(screen.getByLabelText("6 digit code"), "246810");
  await screen.findByText("Choose your PIN");
  expect(api.sent("auth/code")).toEqual([
    expect.objectContaining({ purpose: "first_setup", code: "246810" }),
  ]);
});

it("opens the pad with the lock message when the number's PIN is locked, so the PIN can be reset", async () => {
  const api = fakeApi();
  api.on("auth/start", [423, { status: "pin_locked" }]);
  await startApp();
  await fireEvent.changeText(
    await screen.findByLabelText("Mobile number"),
    "0712345678",
  );
  await fireEvent.press(screen.getByText("Continue"));
  await screen.findByText("Too many wrong PINs. Reset your PIN to sign in.");
  expect(screen.getByText("Forgot PIN?")).toBeTruthy();
});

it("shows the tries the server counts, and its words for a locked PIN or a blocked number", async () => {
  await trustPhone();
  const api = fakeApi();
  api.on("auth/pin", [401, { status: "authentication_failed", triesLeft: 2 }]);
  await startApp();
  await screen.findByText("Welcome back, Antony");
  await typePin("1111");
  await screen.findByText("Wrong PIN. 2 tries left.");

  api.on("auth/pin", [423, { status: "pin_locked" }]);
  await typePin("1111");
  await screen.findByText("Too many wrong PINs. Reset your PIN to sign in.");

  api.on("auth/pin", [403, { status: "blocked" }]);
  await typePin("1111");
  await screen.findByText("This number is blocked. Speak to the office.");
  expect(screen.queryByText("Hi Antony")).toBeNull();
});

it("shows the server's reason when it refuses a new PIN", async () => {
  const api = fakeApi();
  api.on("auth/start", [
    202,
    { status: "verification_required", purpose: "first_setup" },
  ]);
  api.on("auth/code", [200, { status: "code_verified" }]);
  api.on("auth/pin/new", [400, { status: "invalid_pin", pinProblem: "weak" }]);
  await startApp();
  await fireEvent.changeText(
    await screen.findByLabelText("Mobile number"),
    "0700111222",
  );
  await fireEvent.press(screen.getByText("Continue"));
  await fireEvent.changeText(
    await screen.findByLabelText("6 digit code"),
    "123123",
  );
  await screen.findByText("Choose your PIN");
  await typePin("5937");
  await screen.findByText("Type it again");
  await typePin("5937");
  await screen.findByText("Choose a PIN that is harder to guess.");
  expect(screen.getByText("Choose your PIN")).toBeTruthy();
});
