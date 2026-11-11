import { fireEvent, screen } from "@testing-library/react-native";

import { appVersion } from "../src/lib/appVersion";
import { fakeApi, people, tokens } from "./fakeApi";
import { startApp, trustPhone, typePin } from "./helpers";

const tooOld = [
  426,
  { status: "update_required", minimumVersion: "2.0.0" },
] as [number, unknown];

it("names its version on every request", async () => {
  await trustPhone();
  const api = fakeApi();
  api.on("auth/pin", [200, tokens(1)]);
  api.on("auth/session", [200, people.owner]);
  await startApp();
  await screen.findByText("Welcome back, Antony");
  await typePin("4826");
  await screen.findByText("Hi Antony");
  expect(api.calls.map(({ path }) => path)).toEqual(
    expect.arrayContaining(["auth/pin", "auth/session"]),
  );
  for (const { headers } of api.calls)
    expect(headers["X-XCODE-Client"]).toBe(`mobile/${appVersion}`);
});

it("asks for an update when the API refuses this version at sign in", async () => {
  fakeApi().on("auth/start", tooOld);
  await startApp();
  await fireEvent.changeText(
    await screen.findByLabelText("Mobile number"),
    "0733520614",
  );
  await fireEvent.press(screen.getByText("Continue"));
  await screen.findByText("Update XCODE");
  expect(
    screen.getByText(
      `This version of XCODE (${appVersion}) is no longer supported. Install version 2.0.0 or newer to carry on. Anything waiting to be sent stays on this phone.`,
    ),
  ).toBeTruthy();
  expect(screen.queryByLabelText("Mobile number")).toBeNull();
});

it("does not unlock offline when the API refuses this version", async () => {
  await trustPhone();
  fakeApi().on("auth/pin", tooOld);
  await startApp();
  await screen.findByText("Welcome back, Antony");
  await typePin("4826");
  await screen.findByText("Update XCODE");
  expect(screen.queryByText("Hi Antony")).toBeNull();
});

it("asks for an update when a signed-in request is refused", async () => {
  await trustPhone();
  const api = fakeApi();
  api.on("auth/pin", [200, tokens(1)]);
  api.on("auth/session", [426, { status: "update_required" }]);
  await startApp();
  await screen.findByText("Welcome back, Antony");
  await typePin("4826");
  await screen.findByText("Update XCODE");
  expect(
    screen.getByText(/Install the latest version to carry on\./),
  ).toBeTruthy();
});
