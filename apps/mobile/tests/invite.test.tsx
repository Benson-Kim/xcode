import { act, fireEvent, screen, waitFor } from "@testing-library/react-native";
import { randomBytes } from "crypto";
import { Linking } from "react-native";

import { fakeApi, people, tokens } from "./fakeApi";
import { startApp, storedText, trustPhone, typePin } from "./helpers";

jest.mock("../src/lib/webUrl", () => ({ webUrl: "https://xcode.example.com" }));

const DEVICE = "stable-test-device";
const token = randomBytes(32).toString("base64url");
const LINK = `https://xcode.example.com/invite#${token}`;

function openedBy(url: string) {
  jest.spyOn(Linking, "getInitialURL").mockResolvedValue(url);
}

const redeemed = [
  202,
  { status: "verification_required", purpose: "first_setup", code: "135792" },
] as [number, unknown];

afterEach(() => jest.restoreAllMocks());

it("sets up access from an invitation link once the person confirms their number", async () => {
  openedBy(LINK);
  const api = fakeApi();
  api.on("auth/invite/redeem", redeemed);
  api.on("auth/pin/new", [200, tokens()]);
  api.on("auth/session", [200, people.manager]);
  await startApp();

  await screen.findByText("Set up XCODE");
  // Opening the link sends nothing: a mail scanner that follows it changes nothing.
  expect(api.calls.filter(({ path }) => path.startsWith("auth/"))).toEqual([]);
  await fireEvent.changeText(
    screen.getByLabelText("Mobile number"),
    "0700 111 222",
  );
  await fireEvent.press(screen.getByText("Continue"));

  await screen.findByText("Choose your PIN");
  await typePin("5937");
  await screen.findByText("Type it again");
  await typePin("5937");
  await screen.findByText("Hi Brian");
  expect(api.sent("auth/invite/redeem")).toEqual([
    {
      token,
      phoneNumber: "0700111222",
      deviceId: DEVICE,
      deviceName: expect.any(String),
    },
  ]);
  expect(api.sent("auth/pin/new")).toEqual([
    expect.objectContaining({
      phoneNumber: "0700111222",
      purpose: "first_setup",
      code: "135792",
      pin: "5937",
      trustDevice: true,
    }),
  ]);
  expect(storedText()).not.toContain(token);
  expect(storedText()).not.toContain("135792");
});

it.each([
  [
    { status: "authentication_failed" },
    "This number does not match the invitation. Check it, or open the link in your latest invitation email.",
  ],
  [
    { status: "authentication_failed", inviteProblem: "expired" },
    "This invitation has expired. Ask the office to send it again.",
  ],
  [
    { status: "authentication_failed", inviteProblem: "used" },
    "This invitation has been used. Sign in with your number and PIN.",
  ],
])("says why the invitation was refused for %j", async (body, message) => {
  openedBy(LINK);
  fakeApi().on("auth/invite/redeem", [401, body]);
  await startApp();
  await fireEvent.changeText(
    await screen.findByLabelText("Mobile number"),
    "0700111222",
  );
  await fireEvent.press(screen.getByText("Continue"));
  await screen.findByText(message);
  expect(screen.getByText("Set up XCODE")).toBeTruthy();
});

it("checks the number on the phone before sending anything", async () => {
  openedBy(LINK);
  const api = fakeApi();
  await startApp();
  await screen.findByText("Set up XCODE");
  await fireEvent.press(screen.getByText("Continue"));
  expect(api.sent("auth/invite/redeem")).toEqual([]);
  expect(screen.getByText("Set up XCODE")).toBeTruthy();
});

it("returns to sign in when the invitation is cancelled", async () => {
  openedBy(LINK);
  fakeApi();
  await startApp();
  await fireEvent.press(await screen.findByText("Cancel"));
  await screen.findByText("Sign in");
});

it("ignores a link from any other address", async () => {
  openedBy(`https://evil.test/invite#${token}`);
  fakeApi();
  await startApp();
  await screen.findByText("Sign in");
  expect(screen.queryByText("Set up XCODE")).toBeNull();
});

it("signs the trusted person out of the phone only once the invitation matched", async () => {
  await trustPhone();
  openedBy(LINK);
  const api = fakeApi();
  api.on(`auth/devices/${DEVICE}/revoke`, [200, { status: "device_revoked" }]);
  api.on("auth/invite/redeem", [401, { status: "authentication_failed" }]);
  await startApp();

  await screen.findByText(
    "This phone is set up for Antony. Setting up your access signs Antony out of it.",
  );
  await fireEvent.changeText(
    screen.getByLabelText("Mobile number"),
    "0700111222",
  );
  await fireEvent.press(screen.getByText("Continue"));
  await screen.findByText(/does not match the invitation/);
  expect(api.sent(`auth/devices/${DEVICE}/revoke`)).toEqual([]);
  expect(storedText()).toContain("refresh-0");

  api.on("auth/invite/redeem", redeemed);
  await fireEvent.press(screen.getByText("Continue"));
  await screen.findByText("Choose your PIN");
  expect(api.sent(`auth/devices/${DEVICE}/revoke`)).toHaveLength(1);
  expect(storedText()).not.toContain("refresh-0");
  expect(storedText()).not.toContain("Antony");
});

it("keeps a link that comes during a sign-in step and opens it once the step ends", async () => {
  let deliver: (event: { url: string }) => void = () => undefined;
  jest.spyOn(Linking, "getInitialURL").mockResolvedValue(null);
  jest
    .spyOn(Linking, "addEventListener")
    .mockImplementation((_type, handler) => {
      deliver = handler as typeof deliver;
      return { remove: () => undefined } as ReturnType<
        typeof Linking.addEventListener
      >;
    });
  let answer: (reply: "offline") => void = () => undefined;
  const api = fakeApi();
  api.on("auth/start", () => new Promise((resolve) => (answer = resolve)));
  await startApp();
  await fireEvent.changeText(
    await screen.findByLabelText("Mobile number"),
    "0700111222",
  );
  await fireEvent.press(screen.getByText("Continue"));
  await waitFor(() => expect(api.sent("auth/start")).toHaveLength(1));
  await act(async () => deliver({ url: LINK }));
  await act(async () => answer("offline"));
  await screen.findByText("Set up XCODE");
});
