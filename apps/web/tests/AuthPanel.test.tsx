import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";

import { AuthError } from "@xcode/shared/auth";

import { AuthPanel } from "../components/AuthPanel";
import { PinInput } from "../components/PinInput";
import { authApi } from "../lib/api";
import { restoreSession } from "../lib/session";


vi.mock("../lib/api", () => ({ authApi: vi.fn() }));
vi.mock("../lib/session", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../lib/session")>()),
  restoreSession: vi.fn(),
}));
beforeEach(() => {
  vi.mocked(authApi).mockReset();
  vi.mocked(restoreSession).mockResolvedValue(false);
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
    ok: true,
    headers: new Headers(),
    json: async () => ({ firstName: "Test", lastName: "User", role: "Owner", permissions: [] }),
  }));
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

// The sign-in form appears once the page has checked for an existing session.
async function renderPanel() {
  render(<AuthPanel />);
  await screen.findByRole("heading", { name: "Sign in" });
}

function fillSignIn() {
  fireEvent.change(screen.getByLabelText("Mobile number"), {
    target: { value: "+254712345678" },
  });
  fireEvent.change(screen.getByLabelText("PIN"), { target: { value: "5826" } });
  fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
}

it("AUTH-13 sends new devices through verification before showing a session", async () => {
  vi.mocked(authApi)
    .mockResolvedValueOnce({ status: "verification_required" })
    .mockResolvedValueOnce({ status: "authenticated" });
  await renderPanel();
  fillSignIn();
  expect(
    await screen.findByRole("heading", { name: "Check your email" }),
  ).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("6 digit code"), {
    target: { value: "123456" },
  });
  fireEvent.click(screen.getByLabelText(/^Remember this device/));
  fireEvent.click(screen.getByRole("button", { name: "Confirm code" }));
  expect(
    await screen.findByRole("heading", { name: "Dashboard" }),
  ).toBeInTheDocument();
  expect(authApi).toHaveBeenLastCalledWith("verify-device", {
    phoneNumber: "+254712345678",
    pin: "",
    code: "123456",
    rememberDevice: true,
  });
});

it("resends a device code by repeating the sign-in that produced it, never with an empty PIN", async () => {
  vi.mocked(authApi).mockResolvedValue({ status: "verification_required" });
  await renderPanel();
  fillSignIn();
  await screen.findByRole("heading", { name: "Check your email" });
  fireEvent.click(screen.getByRole("button", { name: "Send a new code" }));
  await waitFor(() => expect(authApi).toHaveBeenCalledTimes(2));
  expect(authApi).toHaveBeenLastCalledWith(
    "sign-in",
    expect.objectContaining({ phoneNumber: "+254712345678", pin: "5826" }),
  );
});

it("returns to sign-in when the session can no longer be refreshed", async () => {
  vi.mocked(authApi).mockResolvedValueOnce({ status: "authenticated" });
  await renderPanel();
  fillSignIn();
  await screen.findByRole("heading", { name: "Dashboard" });
  window.dispatchEvent(new Event("xcode:session-expired"));
  expect(
    await screen.findByRole("heading", { name: "Sign in" }),
  ).toBeInTheDocument();
  expect(screen.getByRole("alert")).toHaveTextContent(
    "Your session has ended. Sign in again.",
  );
});

it("accepts existing PINs of up to eight digits", () => {
  render(<PinInput value="58264913" onChange={() => {}} />);
  const input = screen.getByLabelText("PIN");
  expect(input).toHaveAttribute("maxLength", "8");
  expect(input).toHaveAttribute("pattern", "[0-9]{4,8}");
});

it("AUTH-03 displays remaining pause time and keeps PIN reset available", async () => {
  vi.mocked(authApi).mockRejectedValue(
    new AuthError({ status: "paused", retryAfterSeconds: 900 }, 423),
  );
  await renderPanel();
  fillSignIn();
  expect(await screen.findByRole("timer")).toHaveTextContent("15:00");
  expect(screen.getByRole("button", { name: "Sign in" })).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "Forgot PIN?" }));
  expect(
    screen.getByRole("button", { name: "Send code" }),
  ).not.toBeDisabled();
});

it.each([
  ["First time here?", "setup-pin"],
  ["Forgot PIN?", "pin-reset"],
])("%s requires code before submitting a new PIN", async (label, operation) => {
  vi.mocked(authApi)
    .mockResolvedValueOnce({ status: "check_email" })
    .mockResolvedValueOnce({ status: "code_verified" })
    .mockResolvedValueOnce({ status: "authenticated" });

  await renderPanel();
  fireEvent.click(screen.getByRole("button", { name: label }));
  fireEvent.change(screen.getByLabelText("Mobile number"), {
    target: { value: "+254712345678" },
  });
  fireEvent.click(
    screen.getByRole("button", { name: "Send code" }),
  );
  expect(await screen.findByLabelText("6 digit code")).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("6 digit code"), {
    target: { value: "123456" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Confirm code" }));
  await waitFor(() => expect(authApi).toHaveBeenCalledTimes(2));
  const pin = await screen.findByLabelText("New PIN");
  fireEvent.change(pin, { target: { value: "6942" } });
  fireEvent.change(screen.getByLabelText("Type it again"), {
    target: { value: "6942" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Save PIN" }));
  expect(
    await screen.findByRole("heading", { name: "Dashboard" }),
  ).toBeInTheDocument();
  expect(authApi).toHaveBeenLastCalledWith(`${operation}/complete`, {
    phoneNumber: "+254712345678",
    pin: "6942",
    code: "123456",
    rememberDevice: false,
  });
});

it("never keeps or shows a PIN someone just chose", async () => {
  // Signed in, the app shell also loads the organization's appearance; this test has none.
  vi.stubGlobal("fetch", vi.fn(async (url: string) =>
    url.includes("/auth/session")
      ? { ok: true, status: 200, headers: new Headers(), json: async () => ({ firstName: "Test", lastName: "User", role: "Owner", permissions: [] }) }
      : { ok: false, status: 404, headers: new Headers(), json: async () => ({}) },
  ));
  vi.mocked(authApi)
    .mockResolvedValueOnce({ status: "check_email" })
    .mockResolvedValueOnce({ status: "code_verified" })
    .mockResolvedValueOnce({ status: "authenticated" })
    .mockResolvedValueOnce({ status: "signed_out" });
  await renderPanel();
  fireEvent.click(screen.getByRole("button", { name: "First time here?" }));
  // One of the demo numbers the sign-in page lists.
  fireEvent.change(screen.getByLabelText("Mobile number"), { target: { value: "0712 345 678" } });
  fireEvent.click(screen.getByRole("button", { name: "Send code" }));
  fireEvent.change(await screen.findByLabelText("6 digit code"), { target: { value: "123456" } });
  fireEvent.click(screen.getByRole("button", { name: "Confirm code" }));
  fireEvent.change(await screen.findByLabelText("New PIN"), { target: { value: "6942" } });
  fireEvent.change(screen.getByLabelText("Type it again"), { target: { value: "6942" } });
  fireEvent.click(screen.getByRole("button", { name: "Save PIN" }));
  await screen.findByRole("heading", { name: "Dashboard" });

  const userMenu = await waitFor(() => document.querySelector<HTMLButtonElement>('[aria-haspopup="menu"]')!);
  fireEvent.click(userMenu);
  fireEvent.click(await screen.findByRole("menuitem", { name: "Sign out" }));
  await screen.findByRole("heading", { name: "Sign in" });
  expect(screen.getByText("Revenue clerk: 0712 345 678")).toBeInTheDocument();
  expect(document.body).not.toHaveTextContent("6942");
});

it("picks the session back up after a page refresh", async () => {
  vi.mocked(restoreSession).mockResolvedValue(true);
  render(<AuthPanel />);
  expect(
    await screen.findByRole("heading", { name: "Dashboard" }),
  ).toBeInTheDocument();
  expect(screen.queryByLabelText("Mobile number")).not.toBeInTheDocument();
  expect(authApi).not.toHaveBeenCalled();
});

it("submits and keeps credentials the browser autofilled without input events", async () => {
  vi.mocked(authApi).mockRejectedValue(
    new AuthError({ status: "authentication_failed" }, 401),
  );
  await renderPanel();
  // Autofill sets the field values directly; React sees no change event.
  const phone = screen.getByLabelText("Mobile number") as HTMLInputElement;
  const pin = screen.getByLabelText("PIN") as HTMLInputElement;
  phone.value = "+254712345678";
  pin.value = "5826";
  fireEvent.click(screen.getByRole("button", { name: "Sign in" }));

  await waitFor(() =>
    expect(authApi).toHaveBeenCalledWith(
      "sign-in",
      expect.objectContaining({ phoneNumber: "+254712345678", pin: "5826" }),
    ),
  );
  await screen.findByRole("alert");
  expect(phone).toHaveValue("+254712345678");
  expect(pin).toHaveValue("5826");
});
