import { act, fireEvent, screen, waitFor } from "@testing-library/react-native";
import { AppState } from "react-native";
import { fakeApi, people, tokens } from "./fakeApi";
import { startApp, storedText, trustPhone, typePin } from "./helpers";

const DEVICE = "stable-test-device";

const appearance = {
  organizationName: "Demo Fleet",
  settingsVersion: 1,
  businessDate: "2026-09-29",
  branding: { displayName: "XCODE", logoAlt: "", primary: "", secondary: "", accent: "", logo: null },
  formats: { locale: "en-GB", timeZone: "Africa/Nairobi", datePattern: "medium", hour12: false, currency: "KES", useGroupping: true, numberDecimals: 2 },
  themeMode: "system",
  reducedMotion: false,
  fontScale: 1,
};

it("signs in on a new phone with the PIN, then a one-time email code", async () => {
  const api = fakeApi();
  api.on("auth/sign-in", [202, { status: "verification_required", maskedEmail: "a***@shamayah.co.ke", developmentCode: "481516" }]);
  api.on("auth/verify-device", [200, tokens()]);
  api.on("auth/session", [200, people.owner]);
  await startApp();

  await fireEvent.changeText(await screen.findByLabelText("Mobile number"), "+254 733 520614");
  expect(screen.getByLabelText("Mobile number")).toHaveProp("value", "0733 520 614");
  await fireEvent.press(screen.getByText("Continue"));
  await screen.findByText("Enter the PIN for this number");
  await typePin("4826");

  await screen.findByText("Check your email");
  expect(screen.getByText("a***@shamayah.co.ke")).toBeTruthy();
  expect(screen.getByText("481 516")).toBeTruthy();
  await fireEvent.changeText(screen.getByLabelText("6 digit code"), "481516");

  await screen.findByText("Hi Antony");
  // Every field the API requires is sent, and the number goes in its local form.
  expect(api.sent("auth/sign-in")).toEqual([{ email: "", phoneNumber: "0733520614", pin: "4826", code: "", deviceId: DEVICE, refreshToken: "" }]);
  expect(api.sent("auth/verify-device")).toEqual([{ email: "", phoneNumber: "0733520614", pin: "", code: "481516", deviceId: DEVICE, refreshToken: "" }]);
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
  expect(api.sent("auth/unlock")).toEqual([{ email: "", phoneNumber: "0733520614", pin: "4826", code: "", deviceId: DEVICE, refreshToken: "refresh-0" }]);
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

  api.on("auth/pin-reset/request", [202, { status: "check_email", developmentCode: "222333" }]);
  api.on("auth/pin-reset/verify", [200, { status: "code_verified" }]);
  await fireEvent.press(screen.getByText("Reset PIN"));
  await fireEvent.changeText(await screen.findByLabelText("6 digit code"), "222333");

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
  expect(api.sent("auth/pin-reset/complete")).toEqual([{ email: "", phoneNumber: "0733520614", pin: "5937", code: "222333", deviceId: DEVICE, refreshToken: "refresh-0" }]);
});

it("shows the server's pause with its remaining time", async () => {
  const api = fakeApi();
  api.on("auth/sign-in", [423, { status: "paused", retryAfterSeconds: 600 }]);
  await startApp();
  await fireEvent.changeText(await screen.findByLabelText("Mobile number"), "0712345678");
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
  expect(screen.getByText("No internet. You are seeing what this phone saved at your last sign in.")).toBeTruthy();
});

// After the person's number changed elsewhere, the server refuses the old number with the PIN they still know.
it("does not count the PIN the phone knows as wrong when the server refuses it", async () => {
  await trustPhone();
  fakeApi().on("auth/unlock", [401, { status: "authentication_failed" }]);
  await startApp();
  await screen.findByText("Welcome back, Antony");

  await typePin("4826");
  await screen.findByText('This phone can no longer unlock with your PIN. If your mobile number changed, choose "Not you? Switch user" and sign in again.');
  await typePin("1111");
  await screen.findByText("Wrong PIN. 4 tries left.");
});

it("follows the organization's wrong-PIN policy offline, as the phone last loaded it", async () => {
  await trustPhone();
  const api = fakeApi();
  api.on("auth/unlock", [200, tokens(2)]);
  api.on("auth/session", [200, people.owner]);
  api.on("setup/access/catalog", [200, []]);
  api.on("setup/appearance", [200, { ...appearance, lockoutThreshold: 3, lockoutMinutes: 60 }]);
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
  api.on("auth/setup-pin/request", [202, { status: "check_email", developmentCode: "123123" }]);
  api.on("auth/setup-pin/verify", [200, { status: "code_verified" }]);
  let completes = 0;
  api.on("auth/setup-pin/complete", () => (++completes === 1 ? [400, { status: "invalid_pin", minimumPinLength: 6 }] : [200, tokens()]));
  api.on("auth/session", [200, people.manager]);
  await startApp();

  await fireEvent.changeText(await screen.findByLabelText("Mobile number"), "0700111222");
  await fireEvent.press(screen.getByText("First time here? Set your PIN"));
  await fireEvent.changeText(await screen.findByLabelText("6 digit code"), "123123");
  await screen.findByText("Choose your PIN");
  await typePin("5937");
  await screen.findByText("Type it again");
  await typePin("5937");

  await screen.findByText("Your organization needs a PIN of at least 6 numbers.");
  expect(screen.getByLabelText("0 of 6 numbers entered")).toBeTruthy();
  await typePin("593718");
  await screen.findByText("Type it again");
  await typePin("593718");
  await screen.findByText("Hi Brian");
  expect(api.sent("auth/setup-pin/complete").map((body) => body.pin)).toEqual(["5937", "593718"]);
});

it("tells the person how many code tries are left", async () => {
  const api = fakeApi();
  api.on("auth/sign-in", [202, { status: "verification_required", maskedEmail: "w***@zurigenesis.co.ke" }]);
  api.on("auth/verify-device", [401, { status: "authentication_failed" }]);
  await startApp();
  await fireEvent.changeText(await screen.findByLabelText("Mobile number"), "0712345678");
  await fireEvent.press(screen.getByText("Continue"));
  await screen.findByText("Enter your PIN");
  await typePin("2580");
  await fireEvent.changeText(await screen.findByLabelText("6 digit code"), "000000");
  await screen.findByText("That code is wrong. 4 tries left.");
  expect(screen.getByLabelText("6 digit code")).toHaveProp("value", "");
});

it("accepts a PIN longer than four numbers on a new phone", async () => {
  const api = fakeApi();
  api.on("auth/sign-in", [200, tokens()]);
  api.on("auth/session", [200, people.clerk]);
  await startApp();
  await fireEvent.changeText(await screen.findByLabelText("Mobile number"), "0712345678");
  await fireEvent.press(screen.getByText("Continue"));
  await fireEvent.press(await screen.findByText("My PIN has more than 4 numbers"));
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
  expect(api.calls.find((call) => call.path.endsWith("/revoke"))?.headers.Authorization).toBe("Bearer access-0");
  expect(storedText()).not.toContain("refresh-0");
  expect(storedText()).not.toContain("Antony");
});

it("locks again when the app goes to the background", async () => {
  let change: (state: "active" | "background") => void = () => {};
  const listener = jest.spyOn(AppState, "addEventListener").mockImplementation((_, handler) => {
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
