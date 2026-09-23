import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  configure,
} from "@testing-library/react-native";
// Native host components are lazily transformed during the first query on a cold CI run.
configure({ asyncUtilTimeout: 10000 });
import { AppState } from "react-native";
import { AuthError } from "@xcode/shared";
import App from "../App";
import { authApi } from "../src/api";
import { loadSession, saveSession } from "../src/storage";
jest.mock("../src/api", () => ({ authApi: jest.fn() }));
jest.mock("../src/storage", () => ({
  loadSession: jest.fn(),
  saveSession: jest.fn().mockResolvedValue(undefined),
  clearSession: jest.fn().mockResolvedValue(undefined),
}));
const tokens = {
  accessToken: "access",
  refreshToken: "refresh",
  email: "person@example.com",
};
beforeEach(() => {
  jest.mocked(authApi).mockReset();
  jest.mocked(loadSession).mockResolvedValue(null);
});

it("AUTH-15 restored sessions start locked and unlock through the API without email verification", async () => {
  jest.mocked(loadSession).mockResolvedValue(tokens);
  jest
    .mocked(authApi)
    .mockResolvedValue({ status: "authenticated", ...tokens });
  await render(<App />);
  await screen.findByText("Unlock your phone");
  await fireEvent.changeText(screen.getByLabelText("PIN"), "5826");
  await fireEvent.press(screen.getByText("Unlock"));
  await screen.findByText("You’re signed in");
  expect(authApi).toHaveBeenCalledWith("unlock", {
    email: tokens.email,
    pin: "5826",
    code: "",
  });
  expect(saveSession).toHaveBeenCalledWith(tokens);
});
it("AUTH-13 revoked or unknown phones must verify before getting a session", async () => {
  jest.mocked(loadSession).mockResolvedValue(tokens);
  jest
    .mocked(authApi)
    .mockResolvedValueOnce({ status: "verification_required" })
    .mockResolvedValueOnce({ status: "authenticated", ...tokens });
  await render(<App />);
  await screen.findByText("Unlock your phone");
  await fireEvent.changeText(screen.getByLabelText("PIN"), "5826");
  await fireEvent.press(screen.getByText("Unlock"));
  await screen.findByText("Verify this device");
  expect(saveSession).not.toHaveBeenCalled();
  await fireEvent.changeText(
    screen.getByLabelText("Email verification code"),
    "123456",
  );
  await fireEvent.press(screen.getByText("Verify and continue"));
  await screen.findByText("You’re signed in");
  expect(authApi).toHaveBeenLastCalledWith("verify-device", {
    email: tokens.email,
    pin: "",
    code: "123456",
  });
});
it("OPEN-03 paused unlock shows remaining time and offers PIN reset", async () => {
  jest.mocked(loadSession).mockResolvedValue(tokens);
  jest
    .mocked(authApi)
    .mockRejectedValue(
      new AuthError({ status: "paused", retryAfterSeconds: 900 }, 423),
    );
  await render(<App />);
  await screen.findByText("Unlock your phone");
  await fireEvent.changeText(screen.getByLabelText("PIN"), "5826");
  await fireEvent.press(screen.getByText("Unlock"));
  await screen.findByText(/Try again in 15:00/);
  expect(screen.getByText("Unlock")).toBeDisabled();
  await fireEvent.press(screen.getByText("Forgot PIN?"));
  expect(screen.getByText("Send verification code")).not.toBeDisabled();
});
it.each([
  ["First time? Set up PIN", "setup-pin"],
  ["Forgot PIN?", "pin-reset"],
])(
  "%s validates the shared rules before completing",
  async (label, operation) => {
    jest
      .mocked(authApi)
      .mockResolvedValueOnce({ status: "check_email" })
      .mockResolvedValueOnce({ status: "authenticated", ...tokens });
    await render(<App />);
    await waitFor(() => expect(screen.getByText(label)).not.toBeDisabled());
    await fireEvent.press(screen.getByText(label));
    await fireEvent.changeText(screen.getByLabelText("Email"), tokens.email);
    await fireEvent.press(screen.getByText("Send verification code"));
    const pin = await screen.findByLabelText("New PIN");
    await fireEvent.changeText(pin, "4321");
    await fireEvent.changeText(
      screen.getByLabelText("Email verification code"),
      "123456",
    );
    expect(screen.getByText("Verify and continue")).toBeDisabled();
    await fireEvent.changeText(pin, "6942");
    await fireEvent.press(screen.getByText("Verify and continue"));
    await screen.findByText("You’re signed in");
    expect(authApi).toHaveBeenLastCalledWith(`${operation}/complete`, {
      email: tokens.email,
      pin: "6942",
      code: "123456",
    });
  },
);
it("backgrounding an authenticated app locks it again", async () => {
  let change: (state: "active" | "background") => void = () => {};
  const listener = jest
    .spyOn(AppState, "addEventListener")
    .mockImplementation((_, handler) => {
      change = handler;
      return { remove: jest.fn() };
    });
  jest.mocked(loadSession).mockResolvedValue(tokens);
  jest
    .mocked(authApi)
    .mockResolvedValue({ status: "authenticated", ...tokens });
  await render(<App />);
  await screen.findByText("Unlock your phone");
  await fireEvent.changeText(screen.getByLabelText("PIN"), "5826");
  await fireEvent.press(screen.getByText("Unlock"));
  await screen.findByText("You’re signed in");
  await act(() => change("background"));
  await screen.findByText("Unlock your phone");
  expect(screen.getByLabelText("PIN")).toHaveProp("value", "");
  listener.mockRestore();
});
