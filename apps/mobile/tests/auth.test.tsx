import { act, fireEvent, screen, waitFor } from "@testing-library/react-native";
import { AppState } from "react-native";

import {
  OfflineError,
  SessionEndedError,
  apiGet,
  keepSession,
} from "../src/lib/api";
import { loadSession, saveOfflineTries, saveSession } from "../src/lib/storage";
import { fakeApi, people, tokens } from "./fakeApi";
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
  api.on("auth/sign-in", [
    202,
    {
      status: "verification_required",
      maskedEmail: "a***@shamayah.co.ke",
      developmentCode: "481516",
    },
  ]);
  api.on("auth/verify-device", [200, tokens()]);
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
  // Every field the API requires is sent, and the number goes in its local form.
  expect(api.sent("auth/sign-in")).toEqual([
    {
      email: "",
      phoneNumber: "0733520614",
      pin: "4826",
      code: "",
      deviceId: DEVICE,
      refreshToken: "",
    },
  ]);
  expect(api.sent("auth/verify-device")).toEqual([
    {
      email: "",
      phoneNumber: "0733520614",
      pin: "",
      code: "481516",
      deviceId: DEVICE,
      refreshToken: "",
    },
  ]);
  expect(storedText()).toContain("refresh-1");
  expect(storedText()).not.toContain("4826");
});

it("opens a trusted phone on its unlock pad and unlocks through the API", async () => {
  await trustPhone();
  const api = fakeApi();
  api.on("auth/unlock", [200, tokens(2)]);
  api.on("auth/session", [200, people.owner]);
  await startApp();

  await screen.findByText("Welcome back, Antony");
  expect(screen.getByText("0733 ••• 614")).toBeTruthy();
  expect(screen.getByText("PIN unlock works without internet.")).toBeTruthy();
  await typePin("4826");

  await screen.findByText("Hi Antony");
  expect(api.sent("auth/unlock")).toEqual([
    {
      email: "",
      phoneNumber: "0733520614",
      pin: "4826",
      code: "",
      deviceId: DEVICE,
      refreshToken: "refresh-0",
    },
  ]);
  expect(storedText()).toContain("access-2");
});

it("counts wrong PINs, pauses after five, and resets the PIN with an email code", async () => {
  await trustPhone();
  const api = fakeApi();
  api.on("auth/unlock", [401, { status: "authentication_failed" }]);
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

  api.on("auth/pin-reset/request", [
    202,
    { status: "check_email", developmentCode: "222333" },
  ]);
  api.on("auth/pin-reset/verify", [200, { status: "code_verified" }]);
  await fireEvent.press(screen.getByText("Reset PIN"));
  await fireEvent.changeText(
    await screen.findByLabelText("6 digit code"),
    "222333",
  );

  await screen.findByText("Choose a new PIN");
  await typePin("1234");
  await screen.findByText("Too easy to guess. Choose different numbers.");
  await typePin("4826");
  await screen.findByText("Pick a PIN different from your old one.");
  await typePin("5937");
  await screen.findByText("Type it again");
  await typePin("5938");
  await screen.findByText("The two PINs did not match. Choose your PIN again.");

  api.on("auth/pin-reset/complete", [200, tokens(3)]);
  api.on("auth/session", [200, people.owner]);
  await typePin("5937");
  await screen.findByText("Type it again");
  await typePin("5937");
  await screen.findByText("Hi Antony");
  expect(api.sent("auth/pin-reset/complete")).toEqual([
    {
      email: "",
      phoneNumber: "0733520614",
      pin: "5937",
      code: "222333",
      deviceId: DEVICE,
      refreshToken: "refresh-0",
    },
  ]);
});

it("shows the server's pause with its remaining time", async () => {
  const api = fakeApi();
  api.on("auth/sign-in", [423, { status: "paused", retryAfterSeconds: 600 }]);
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
  api.on("auth/unlock", "offline");
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
    api.on("auth/unlock", [status, { title: "Server error" }]);
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
  fakeApi().on("auth/unlock", [503, { title: "Service Unavailable" }]);
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
  api.on("auth/sign-in", [503, { title: "Service Unavailable" }]);
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
  expect(api.sent("auth/unlock")).toEqual([]);
});

// After the person's number changed elsewhere, the server refuses the old number with the PIN they still know.
it("does not count the PIN the phone knows as wrong when the server refuses it", async () => {
  await trustPhone();
  fakeApi().on("auth/unlock", [401, { status: "authentication_failed" }]);
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
  api.on("auth/unlock", [200, tokens(2)]);
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
  api.on("auth/unlock", "offline");
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
  fakeApi().on("auth/unlock", "offline");
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

it("sets a first PIN with an email code and meets the organization's minimum length", async () => {
  const api = fakeApi();
  api.on("auth/setup-pin/request", [
    202,
    { status: "check_email", developmentCode: "123123" },
  ]);
  api.on("auth/setup-pin/verify", [200, { status: "code_verified" }]);
  let completes = 0;
  api.on("auth/setup-pin/complete", () =>
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
  await fireEvent.press(screen.getByText("First time here? Set your PIN"));
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
  expect(api.sent("auth/setup-pin/complete").map((body) => body.pin)).toEqual([
    "5937",
    "593718",
  ]);
});

it("holds the keypad while a new PIN is being saved, so a second entry sends no second request", async () => {
  const api = fakeApi();
  api.on("auth/setup-pin/request", [
    202,
    { status: "check_email", developmentCode: "123123" },
  ]);
  api.on("auth/setup-pin/verify", [200, { status: "code_verified" }]);
  let saved = () => {};
  api.on(
    "auth/setup-pin/complete",
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
  await fireEvent.press(screen.getByText("First time here? Set your PIN"));
  await fireEvent.changeText(
    await screen.findByLabelText("6 digit code"),
    "123123",
  );
  await screen.findByText("Choose your PIN");
  await typePin("5937");
  await screen.findByText("Type it again");
  await typePin("5937");
  await waitFor(() =>
    expect(api.sent("auth/setup-pin/complete")).toHaveLength(1),
  );

  expect(screen.getByRole("button", { name: "1" })).toBeDisabled();
  await typePin("5937");
  await act(() => new Promise((resolve) => setTimeout(resolve, 300)));
  expect(screen.getByLabelText("0 of 4 numbers entered")).toBeTruthy();
  expect(api.sent("auth/setup-pin/complete")).toHaveLength(1);

  await act(async () => saved());
  await screen.findByText("Hi Brian");
  expect(api.sent("auth/setup-pin/complete")).toHaveLength(1);
});

it("holds the keypad while an offline unlock is being checked", async () => {
  await trustPhone();
  fakeApi().on("auth/unlock", "offline");
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

it("tells the person how many code tries are left", async () => {
  const api = fakeApi();
  api.on("auth/sign-in", [
    202,
    { status: "verification_required", maskedEmail: "w***@zurigenesis.co.ke" },
  ]);
  api.on("auth/verify-device", [401, { status: "authentication_failed" }]);
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
  await screen.findByText("That code is wrong. 4 tries left.");
  expect(screen.getByLabelText("6 digit code")).toHaveProp("value", "");
});

it("accepts a PIN longer than four numbers on a new phone", async () => {
  const api = fakeApi();
  api.on("auth/sign-in", [200, tokens()]);
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
  expect(api.sent("auth/sign-in")[0].pin).toBe("258036");
});

it("switch user stops trusting the phone and returns to sign in", async () => {
  await trustPhone();
  const api = fakeApi();
  api.on(`auth/devices/${DEVICE}/revoke`, [200, { status: "device_revoked" }]);
  await startApp();
  await fireEvent.press(await screen.findByText("Not you? Switch user"));
  await screen.findByText("Sign in");
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
  fakeApi().on("auth/unlock", "offline");
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
  fakeApi().on("auth/unlock", "offline");
  await startApp();
  await screen.findByText("Welcome back, Antony");

  await typePin("4826");
  await screen.findByText("Hi Antony");
});

it("starts the 72 hours from now for a phone that signed in before the rule shipped", async () => {
  // A Phase 1 session has no record of when the phone was last online; it must not lock anyone out at once.
  await trustPhone();
  fakeApi().on("auth/unlock", "offline");
  await startApp();
  await screen.findByText("Welcome back, Antony");

  await typePin("4826");
  await screen.findByText("Hi Antony");
});

it("puts the offline window back on the clock after signing in online", async () => {
  await trustPhone(people.owner, "0733520614", "4826", Date.now() - 80 * HOURS);
  const api = fakeApi();
  api.on("auth/unlock", [200, tokens()]);
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
  api.on("auth/sign-in", [200, tokens()]);
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
  api.on("auth/sign-in", () =>
    ++signIns === 1
      ? [
          202,
          {
            status: "verification_required",
            maskedEmail: "w***@zurigenesis.co.ke",
          },
        ]
      : [200, tokens(2)],
  );
  api.on("auth/verify-device", [200, tokens()]);
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
  expect(api.sent("auth/verify-device")).toHaveLength(1);
  expect(api.sent("auth/sign-in")).toHaveLength(2);
  expect(storedText()).toContain("access-2");
});

it("signs in with the new PIN when fetching the person fails after a first PIN is saved", async () => {
  const api = fakeApi();
  api.on("auth/setup-pin/request", [
    202,
    { status: "check_email", developmentCode: "123123" },
  ]);
  api.on("auth/setup-pin/verify", [200, { status: "code_verified" }]);
  api.on("auth/setup-pin/complete", [200, tokens()]);
  api.on("auth/session", failsOnce(people.manager));
  api.on("auth/sign-in", [200, tokens(2)]);
  await startApp();
  await fireEvent.changeText(
    await screen.findByLabelText("Mobile number"),
    "0700111222",
  );
  await fireEvent.press(screen.getByText("First time here? Set your PIN"));
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
  expect(api.sent("auth/setup-pin/verify")).toHaveLength(1);
  expect(api.sent("auth/setup-pin/complete")).toHaveLength(1);
  expect(api.sent("auth/sign-in")).toEqual([
    {
      email: "",
      phoneNumber: "0700111222",
      pin: "5937",
      code: "",
      deviceId: DEVICE,
      refreshToken: "refresh-1",
    },
  ]);
});

it("unlocks with the new PIN when fetching the person fails after a PIN reset", async () => {
  await trustPhone();
  const api = fakeApi();
  api.on("auth/pin-reset/request", [
    202,
    { status: "check_email", developmentCode: "222333" },
  ]);
  api.on("auth/pin-reset/verify", [200, { status: "code_verified" }]);
  api.on("auth/pin-reset/complete", [200, tokens(3)]);
  api.on("auth/session", failsOnce(people.owner));
  api.on("auth/unlock", [200, tokens(4)]);
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
  expect(api.sent("auth/pin-reset/verify")).toHaveLength(1);
  expect(api.sent("auth/pin-reset/complete")).toHaveLength(1);
  expect(api.sent("auth/unlock")).toHaveLength(1);
  expect(api.sent("auth/unlock")[0]).toMatchObject({ pin: "5937", code: "" });
  expect(storedText()).toContain("access-4");
});

describe("an answer the app does not expect", () => {
  async function toThePad() {
    await startApp();
    await fireEvent.changeText(
      await screen.findByLabelText("Mobile number"),
      "0712345678",
    );
    await fireEvent.press(screen.getByText("Continue"));
    await screen.findByText("Enter the PIN for this number");
  }

  async function toTheCode(api: ReturnType<typeof fakeApi>) {
    api.on("auth/setup-pin/request", [202, { status: "check_email" }]);
    await startApp();
    await fireEvent.changeText(
      await screen.findByLabelText("Mobile number"),
      "0700111222",
    );
    await fireEvent.press(screen.getByText("First time here? Set your PIN"));
    return screen.findByLabelText("6 digit code");
  }

  it("says so on the pad when a sign-in is answered with another status, and counts no wrong PIN", async () => {
    const api = fakeApi();
    api.on("auth/sign-in", [200, { status: "check_email" }]);
    await toThePad();
    await typePin("2580");
    await screen.findByText(UNEXPECTED);
    expect(screen.getByLabelText("0 of 4 numbers entered")).toBeTruthy();

    api.on("auth/sign-in", [401, { status: "authentication_failed" }]);
    await typePin("1111");
    await screen.findByText("Wrong PIN. 4 tries left.");
  });

  it("says so on the pad when an unlock is answered with another status, and counts no wrong PIN", async () => {
    await trustPhone();
    const api = fakeApi();
    api.on("auth/unlock", [200, { status: "check_email" }]);
    await startApp();
    await screen.findByText("Welcome back, Antony");
    await typePin("4826");
    await screen.findByText(UNEXPECTED);
    expect(screen.queryByText("Hi Antony")).toBeNull();
    expect(screen.getByLabelText("0 of 4 numbers entered")).toBeTruthy();

    api.on("auth/unlock", [401, { status: "authentication_failed" }]);
    await typePin("1111");
    await screen.findByText("Wrong PIN. 4 tries left.");
  });

  it("says so on the number step when a request for a code is answered with another status", async () => {
    const api = fakeApi();
    api.on("auth/setup-pin/request", [200, { status: "authenticated" }]);
    await startApp();
    await fireEvent.changeText(
      await screen.findByLabelText("Mobile number"),
      "0700111222",
    );
    await fireEvent.press(screen.getByText("First time here? Set your PIN"));
    await screen.findByText(UNEXPECTED);
    expect(screen.queryByText("Check your email")).toBeNull();
    expect(screen.getByLabelText("Mobile number")).toBeTruthy();
  });

  it("says so on the code step when a code is verified with another status, and counts no wrong code", async () => {
    const api = fakeApi();
    api.on("auth/setup-pin/verify", [200, { status: "check_email" }]);
    await fireEvent.changeText(await toTheCode(api), "123123");
    await screen.findByText(UNEXPECTED);
    expect(screen.queryByText("Choose your PIN")).toBeNull();

    api.on("auth/setup-pin/verify", [401, { status: "authentication_failed" }]);
    await fireEvent.changeText(screen.getByLabelText("6 digit code"), "000000");
    await screen.findByText("That code is wrong. 4 tries left.");
  });

  it("says so on the pad when a new PIN is saved with another status", async () => {
    const api = fakeApi();
    api.on("auth/setup-pin/verify", [200, { status: "code_verified" }]);
    api.on("auth/setup-pin/complete", [200, { status: "code_verified" }]);
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
    api.on("auth/sign-in", [202, { status: "verification_required" }]);
    api.on("auth/verify-device", [200, { status: "check_email" }]);
    await toThePad();
    await typePin("2580");
    await fireEvent.changeText(
      await screen.findByLabelText("6 digit code"),
      "481516",
    );
    await screen.findByText(UNEXPECTED);
    expect(screen.getByText("Check your email")).toBeTruthy();
    expect(api.sent("auth/verify-device")).toHaveLength(1);
  });

  it("says so when the sign-in is accepted but carries no tokens", async () => {
    const api = fakeApi();
    api.on("auth/sign-in", [200, { status: "authenticated" }]);
    api.on("auth/session", [200, people.clerk]);
    await toThePad();
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
  api.on("auth/unlock", [423, { status: "paused", retryAfterSeconds: 600 }]);
  api.on("auth/pin-reset/request", "offline");
  await startApp();
  await screen.findByText("Welcome back, Antony");
  await typePin("1111");
  await screen.findByText("Sign in paused");

  await fireEvent.press(screen.getByText("Reset PIN"));
  await screen.findByText("No internet. Sending a code needs network.");
  expect(screen.getByText("Sign in paused")).toBeTruthy();

  api.on("auth/pin-reset/request", [429, {}]);
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
    "auth/pin-reset/request",
    () =>
      new Promise<[number, unknown]>((resolve) => {
        sent = () => resolve([202, { status: "check_email" }]);
      }),
  );
  await startApp();
  await fireEvent.press(await screen.findByText("Forgot PIN?"));
  await waitFor(() =>
    expect(api.sent("auth/pin-reset/request")).toHaveLength(1),
  );
  expect(screen.getByRole("button", { name: "1" })).toBeDisabled();
  await fireEvent.press(screen.getByText("Forgot PIN?"));
  expect(api.sent("auth/pin-reset/request")).toHaveLength(1);
  await act(async () => sent());
  await screen.findByText("Check your email");
});

it("locks again when the app goes to the background", async () => {
  let change: (state: "active" | "background") => void = () => {};
  const listener = jest
    .spyOn(AppState, "addEventListener")
    .mockImplementation((_, handler) => {
      change = handler;
      return { remove: jest.fn() };
    });
  await trustPhone();
  const api = fakeApi();
  api.on("auth/unlock", [200, tokens(2)]);
  api.on("auth/session", [200, people.owner]);
  await startApp();
  await screen.findByText("Welcome back, Antony");
  await typePin("4826");
  await screen.findByText("Hi Antony");
  await act(() => change("background"));
  await screen.findByText("Welcome back, Antony");
  expect(screen.getByLabelText("0 of 4 numbers entered")).toBeTruthy();
  listener.mockRestore();
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
  api.on("auth/sign-in", [200, tokens()]);
  await saveSession({
    phoneNumber: "0712345678",
    accessToken: "access-0",
    refreshToken: "refresh-0",
  });
  const { authApi } = require("../src/lib/api");
  await authApi("sign-in", { phoneNumber: "0712345678", pin: "2580" });
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
