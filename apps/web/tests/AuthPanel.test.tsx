import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";

import { AuthError } from "@xcode/shared";
import { AuthPanel } from "../components/AuthPanel";
import { PinInput } from "../components/PinInput";
import { authApi } from "../lib/api";


vi.mock("../lib/api", () => ({ authApi: vi.fn() }));
beforeEach(() => {
  vi.mocked(authApi).mockReset();
});

it("PIN input validates repeated and sequential new PINs without rejecting existing sign-in PINs", () => {
  const { rerender } = render(
    <PinInput value="1111" onChange={() => {}} newPin />,
  );
  expect(screen.getByLabelText("New PIN")).toHaveAttribute(
    "aria-invalid",
    "true",
  );
  rerender(<PinInput value="4321" onChange={() => {}} newPin />);
  expect(screen.getByLabelText("New PIN")).toHaveAttribute(
    "aria-invalid",
    "true",
  );
  rerender(<PinInput value="5826" onChange={() => {}} newPin />);
  expect(screen.getByLabelText("New PIN")).toHaveAttribute(
    "aria-invalid",
    "false",
  );
});

function fillSignIn() {
  fireEvent.change(screen.getByLabelText("Email"), {
    target: { value: "person@example.com" },
  });
  fireEvent.change(screen.getByLabelText("PIN"), { target: { value: "5826" } });
  fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
}

it("AUTH-13 sends new devices through verification before showing a session", async () => {
  vi.mocked(authApi)
    .mockResolvedValueOnce({ status: "verification_required" })
    .mockResolvedValueOnce({ status: "authenticated" });
  render(<AuthPanel />);
  fillSignIn();
  expect(
    await screen.findByRole("heading", { name: "Verify this device" }),
  ).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Email verification code"), {
    target: { value: "123456" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Verify and continue" }));
  expect(
    await screen.findByRole("heading", { name: "You’re signed in" }),
  ).toBeInTheDocument();
  expect(authApi).toHaveBeenLastCalledWith("verify-device", {
    email: "person@example.com",
    pin: "",
    code: "123456",
  });
});

it("AUTH-03 displays remaining pause time and keeps PIN reset available", async () => {
  vi.mocked(authApi).mockRejectedValue(
    new AuthError({ status: "paused", retryAfterSeconds: 900 }, 423),
  );
  render(<AuthPanel />);
  fillSignIn();
  expect(await screen.findByRole("timer")).toHaveTextContent("15:00");
  expect(screen.getByRole("button", { name: "Sign in" })).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "Forgot PIN?" }));
  expect(
    screen.getByRole("button", { name: "Send verification code" }),
  ).not.toBeDisabled();
});

it.each([
  ["First time? Set up PIN", "setup-pin"],
  ["Forgot PIN?", "pin-reset"],
])("%s requires code before submitting a new PIN", async (label, operation) => {
  vi.mocked(authApi)
    .mockResolvedValueOnce({ status: "check_email" })
    .mockResolvedValueOnce({ status: "authenticated" });

  render(<AuthPanel />);
  fireEvent.click(screen.getByRole("button", { name: label }));
  fireEvent.change(screen.getByLabelText("Email"), {
    target: { value: "person@example.com" },
  });
  fireEvent.click(
    screen.getByRole("button", { name: "Send verification code" }),
  );
  const pin = await screen.findByLabelText("New PIN");
  fireEvent.change(pin, { target: { value: "1111" } });
  fireEvent.change(screen.getByLabelText("Email verification code"), {
    target: { value: "123456" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Verify and continue" }));
  await waitFor(() => expect(authApi).toHaveBeenCalledTimes(1));
  fireEvent.change(pin, { target: { value: "6942" } });
  fireEvent.click(screen.getByRole("button", { name: "Verify and continue" }));
  expect(
    await screen.findByRole("heading", { name: "You’re signed in" }),
  ).toBeInTheDocument();
  expect(authApi).toHaveBeenLastCalledWith(`${operation}/complete`, {
    email: "person@example.com",
    pin: "6942",
    code: "123456",
  });
});
