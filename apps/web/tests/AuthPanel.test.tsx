import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";

import { AuthError } from "@xcode/shared/auth";

import { AuthPanel } from "../components/AuthPanel";
import { authApi, readDevice } from "../lib/api";
import { readSession, restoreSession } from "../lib/session";
import { appearanceFixture } from "./fixtures";

vi.mock("../lib/api", () => ({ authApi: vi.fn(), readDevice: vi.fn() }));
vi.mock("../lib/session", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../lib/session")>()),
  restoreSession: vi.fn(),
  readSession: vi.fn(),
}));

const session = {
  userId: "me",
  firstName: "Antony",
  lastName: "Maina",
  role: "Owner",
  permissions: [],
};

beforeEach(() => {
  vi.mocked(authApi).mockReset();
  vi.mocked(readDevice).mockReset();
  vi.mocked(readDevice).mockResolvedValue({ trusted: false });
  vi.mocked(restoreSession).mockResolvedValue(false);
  vi.mocked(readSession).mockResolvedValue(session);
  vi.stubGlobal("fetch", stubApp());
});

// The app behind the sign-in: the session, the appearance (with the idle limit given) and empty lists.
function stubApp(idleUnlockSeconds?: number) {
  return vi.fn(async (input: string) => {
    const body = input.includes("/auth/session")
      ? session
      : input.includes("appearance")
        ? { ...appearanceFixture("2026-10-12"), idleUnlockSeconds }
        : input.includes("trusted-devices")
          ? []
          : { items: [], pageNumber: 1, pageSize: 100, total: 0 };
    return new Response(JSON.stringify(body), { status: 200 });
  });
}

async function renderPanel() {
  render(<AuthPanel />);
  await screen.findByRole("heading", { name: "Sign in" });
}

const refused = (status: string, httpStatus: number, extra = {}) =>
  new AuthError({ status, ...extra } as never, httpStatus);

function typeNumber(value = "0733 520 614") {
  fireEvent.change(screen.getByLabelText("Mobile number"), {
    target: { value },
  });
  fireEvent.click(screen.getByRole("button", { name: "Continue" }));
}

it("asks for the mobile number alone, then the PIN, which submits itself on the fourth digit", async () => {
  vi.mocked(authApi)
    .mockResolvedValueOnce({ status: "pin_required" })
    .mockResolvedValueOnce({ status: "authenticated" });
  await renderPanel();
  expect(screen.queryByLabelText("PIN")).not.toBeInTheDocument();
  typeNumber();
  expect(await screen.findByLabelText("PIN")).toBeInTheDocument();
  expect(authApi).toHaveBeenCalledWith("start", { phoneNumber: "0733520614" });
  // On a device that is not trusted the PIN step shows the number only, never a name.
  expect(screen.getByText("0733 520 614")).toBeInTheDocument();
  expect(screen.queryByText("Antony Maina")).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("PIN"), { target: { value: "482" } });
  expect(authApi).toHaveBeenCalledTimes(1);
  fireEvent.change(screen.getByLabelText("PIN"), { target: { value: "4826" } });
  await waitFor(() =>
    expect(authApi).toHaveBeenLastCalledWith("pin", {
      phoneNumber: "0733520614",
      pin: "4826",
    }),
  );
  expect(
    await screen.findByRole("heading", { name: "Dashboard" }),
  ).toBeInTheDocument();
});

it("refuses a number that is not ten digits before asking the server", async () => {
  await renderPanel();
  typeNumber("0733");
  expect(
    await screen.findByText("Enter your 10 digit mobile number."),
  ).toBeInTheDocument();
  expect(authApi).not.toHaveBeenCalled();
});

it("says a wrong PIN with the tries left, then that the PIN is locked, with Reset PIN as the only way on", async () => {
  vi.mocked(authApi)
    .mockResolvedValueOnce({ status: "pin_required" })
    .mockRejectedValueOnce(
      refused("authentication_failed", 401, { triesLeft: 1 }),
    )
    .mockRejectedValueOnce(refused("pin_locked", 423))
    .mockResolvedValueOnce({
      status: "verification_required",
      purpose: "pin_reset",
    });
  await renderPanel();
  typeNumber();
  const pin = await screen.findByLabelText("PIN");
  fireEvent.change(pin, { target: { value: "1111" } });
  expect(await screen.findByText("Wrong PIN. 1 try left.")).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("PIN"), { target: { value: "2222" } });
  expect(
    await screen.findByText("Too many wrong PINs. Reset your PIN to sign in."),
  ).toBeInTheDocument();
  expect(screen.getByLabelText("PIN")).toBeDisabled();
  expect(
    screen.queryByRole("button", { name: "Forgot PIN" }),
  ).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Reset PIN" }));
  expect(
    await screen.findByRole("heading", { name: "Reset PIN" }),
  ).toBeInTheDocument();
  expect(authApi).toHaveBeenLastCalledWith("pin/forgot", {
    phoneNumber: "0733520614",
  });
});

it("confirms a new device with a code, ticks Trust this device by default, and the code submits on the sixth digit", async () => {
  vi.mocked(authApi)
    .mockResolvedValueOnce({ status: "pin_required" })
    .mockResolvedValueOnce({
      status: "verification_required",
      purpose: "new_device",
      maskedEmail: "m•••a@zurigenesis.co.ke",
    })
    .mockResolvedValueOnce({ status: "authenticated" });
  await renderPanel();
  typeNumber();
  fireEvent.change(await screen.findByLabelText("PIN"), {
    target: { value: "4826" },
  });
  expect(
    await screen.findByRole("heading", { name: "Confirm this device" }),
  ).toBeInTheDocument();
  expect(screen.getByText("m•••a@zurigenesis.co.ke")).toBeInTheDocument();
  expect(screen.getByLabelText("Trust this device")).toBeChecked();
  fireEvent.change(screen.getByLabelText("6 digit code"), {
    target: { value: "123456" },
  });
  await waitFor(() =>
    expect(authApi).toHaveBeenLastCalledWith("code", {
      phoneNumber: "0733520614",
      purpose: "new_device",
      code: "123456",
      trustDevice: true,
    }),
  );
  expect(
    await screen.findByRole("heading", { name: "Dashboard" }),
  ).toBeInTheDocument();
});

it("takes a first sign in through a code to choosing a PIN, checked on screen before it is sent", async () => {
  vi.mocked(authApi)
    .mockResolvedValueOnce({
      status: "verification_required",
      purpose: "first_setup",
      maskedEmail: "m•••y@zurigenesis.co.ke",
    })
    .mockResolvedValueOnce({ status: "code_verified" })
    .mockRejectedValueOnce(refused("invalid_pin", 400, { pinProblem: "weak" }))
    .mockResolvedValueOnce({ status: "authenticated" });
  await renderPanel();
  typeNumber("0705337482");
  expect(
    await screen.findByRole("heading", { name: "First sign in" }),
  ).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("6 digit code"), {
    target: { value: "654321" },
  });
  expect(
    await screen.findByRole("heading", { name: "Choose your PIN" }),
  ).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("New PIN"), {
    target: { value: "1234" },
  });
  fireEvent.change(screen.getByLabelText("Repeat PIN"), {
    target: { value: "1235" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Save and sign in" }));
  expect(
    await screen.findByText("The two PINs do not match."),
  ).toBeInTheDocument();
  expect(authApi).toHaveBeenCalledTimes(2);
  fireEvent.change(screen.getByLabelText("Repeat PIN"), {
    target: { value: "1234" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Save and sign in" }));
  expect(
    await screen.findByText("Choose a PIN that is harder to guess."),
  ).toBeInTheDocument();
  expect(authApi).toHaveBeenLastCalledWith("pin/new", {
    phoneNumber: "0705337482",
    purpose: "first_setup",
    code: "654321",
    pin: "1234",
    trustDevice: true,
  });
  fireEvent.change(screen.getByLabelText("New PIN"), {
    target: { value: "4826" },
  });
  fireEvent.change(screen.getByLabelText("Repeat PIN"), {
    target: { value: "4826" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Save and sign in" }));
  expect(
    await screen.findByRole("heading", { name: "Dashboard" }),
  ).toBeInTheDocument();
});

it("says when a wrong code was the last try and a new one has been sent, and sends a new code on request", async () => {
  vi.mocked(authApi)
    .mockResolvedValueOnce({
      status: "verification_required",
      purpose: "first_setup",
    })
    .mockResolvedValueOnce({ status: "code_resent" })
    .mockResolvedValueOnce({ status: "verification_required" });
  await renderPanel();
  typeNumber();
  fireEvent.change(await screen.findByLabelText("6 digit code"), {
    target: { value: "000000" },
  });
  expect(
    await screen.findByText("Wrong code. A new code has been sent."),
  ).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Send a new code" }));
  await waitFor(() =>
    expect(authApi).toHaveBeenLastCalledWith("code/resend", {
      phoneNumber: "0733520614",
      purpose: "first_setup",
    }),
  );
  expect(
    await screen.findByText("A new code has been sent."),
  ).toBeInTheDocument();
});

it("starts at the PIN with the person's name on a trusted device, and returns there after sign out", async () => {
  vi.mocked(readDevice).mockResolvedValue({
    trusted: true,
    phoneNumber: "0733520614",
    firstName: "Antony",
    lastName: "Maina",
    role: "Owner",
  });
  vi.mocked(authApi)
    .mockResolvedValueOnce({ status: "authenticated" })
    .mockResolvedValueOnce({ status: "signed_out" });
  render(<AuthPanel />);
  expect(await screen.findByText("Antony Maina")).toBeInTheDocument();
  expect(screen.queryByLabelText("Mobile number")).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("PIN"), { target: { value: "4826" } });
  expect(
    await screen.findByRole("heading", { name: "Dashboard" }),
  ).toBeInTheDocument();
  expect(authApi).toHaveBeenCalledWith("pin", {
    phoneNumber: "0733520614",
    pin: "4826",
  });
  fireEvent.click(screen.getByRole("button", { name: "Antony Maina" }));
  fireEvent.click(await screen.findByRole("menuitem", { name: "Sign out" }));
  expect(await screen.findByLabelText("PIN")).toBeInTheDocument();
  expect(
    within(document.querySelector(".signin")!).getByText("Antony Maina"),
  ).toBeInTheDocument();
});

it("forgets the name once the server asks a trusted device for a code again", async () => {
  vi.mocked(readDevice).mockResolvedValue({
    trusted: true,
    phoneNumber: "0733520614",
    firstName: "Antony",
    lastName: "Maina",
    role: "Owner",
  });
  vi.mocked(authApi).mockResolvedValueOnce({
    status: "verification_required",
    purpose: "new_device",
    maskedEmail: "m•••a@zurigenesis.co.ke",
  });
  render(<AuthPanel />);
  fireEvent.change(await screen.findByLabelText("PIN"), {
    target: { value: "4826" },
  });
  expect(
    await screen.findByRole("heading", { name: "Confirm this device" }),
  ).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Back" }));
  expect(await screen.findByLabelText("Mobile number")).toBeInTheDocument();
});

it("blocks a refused number at the number step", async () => {
  vi.mocked(authApi).mockRejectedValueOnce(refused("blocked", 403));
  await renderPanel();
  typeNumber();
  expect(
    await screen.findByText("This number is blocked. Speak to the office."),
  ).toBeInTheDocument();
  expect(screen.getByLabelText("Mobile number")).toBeInTheDocument();
});

it("asks for the PIN again after a while without activity, keeping the app underneath", async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  try {
    vi.mocked(restoreSession).mockResolvedValue(true);
    vi.mocked(readDevice).mockResolvedValue({
      trusted: true,
      phoneNumber: "0733520614",
      firstName: "Antony",
      lastName: "Maina",
      role: "Owner",
    });
    vi.stubGlobal("fetch", stubApp(60));
    vi.mocked(authApi).mockResolvedValueOnce({ status: "authenticated" });
    render(<AuthPanel />);
    expect(
      await screen.findByRole("heading", { name: "Dashboard" }),
    ).toBeInTheDocument();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(61_000);
    });
    expect(await screen.findByLabelText("PIN")).toBeInTheDocument();
    expect(
      within(document.querySelector(".signin")!).getByText("Antony Maina"),
    ).toBeInTheDocument();
    // The app is still there, inert, under the PIN screen.
    expect(
      screen.getByRole("heading", { name: "Dashboard", hidden: true }),
    ).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("PIN"), {
      target: { value: "4826" },
    });
    await waitFor(() =>
      expect(screen.queryByLabelText("PIN")).not.toBeInTheDocument(),
    );
    expect(authApi).toHaveBeenLastCalledWith("pin", {
      phoneNumber: "0733520614",
      pin: "4826",
    });
  } finally {
    vi.useRealTimers();
  }
});

it("picks the session back up after a page refresh", async () => {
  vi.mocked(restoreSession).mockResolvedValue(true);
  render(<AuthPanel />);
  expect(
    await screen.findByRole("heading", { name: "Dashboard" }),
  ).toBeInTheDocument();
  expect(authApi).not.toHaveBeenCalled();
});

it("returns to sign-in when the session can no longer be refreshed", async () => {
  vi.mocked(restoreSession).mockResolvedValue(true);
  render(<AuthPanel />);
  await screen.findByRole("heading", { name: "Dashboard" });
  act(() => {
    window.dispatchEvent(new Event("xcode:session-expired"));
  });
  expect(
    await screen.findByText("Your session has ended. Sign in again."),
  ).toBeInTheDocument();
  expect(screen.getByLabelText("Mobile number")).toBeInTheDocument();
});
