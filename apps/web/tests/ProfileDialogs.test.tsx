import { fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";

import { AuthError } from "@xcode/shared/auth";

import {
  ChangePinDialog,
  TrustedDevicesDialog,
} from "../components/ProfileDialogs";
import { authApi } from "../lib/api";
import { renderInApp } from "./renderInApp";

vi.mock("../lib/api", () => ({ authApi: vi.fn(), readDevice: vi.fn() }));

beforeEach(() => vi.mocked(authApi).mockReset());

const pins = (current: string, next: string, repeat: string) => {
  fireEvent.change(screen.getByLabelText("Current PIN"), {
    target: { value: current },
  });
  fireEvent.change(screen.getByLabelText("New PIN"), {
    target: { value: next },
  });
  fireEvent.change(screen.getByLabelText("Repeat PIN"), {
    target: { value: repeat },
  });
  fireEvent.click(screen.getByRole("button", { name: "Save PIN" }));
};

it("changes the PIN with the current one, checking the two new PINs on screen first", async () => {
  vi.mocked(authApi).mockResolvedValue({ status: "pin_changed" });
  const onClose = vi.fn();
  renderInApp(<ChangePinDialog open onClose={onClose} />);
  pins("4826", "1234", "1235");
  expect(
    await screen.findByText("The two PINs do not match."),
  ).toBeInTheDocument();
  expect(authApi).not.toHaveBeenCalled();
  pins("4826", "1234", "1234");
  await waitFor(() => expect(onClose).toHaveBeenCalled());
  expect(authApi).toHaveBeenCalledWith("pin/change", {
    currentPin: "4826",
    newPin: "1234",
  });
});

it("says when the current PIN is not right, or the new one is the same", async () => {
  vi.mocked(authApi)
    .mockRejectedValueOnce(
      new AuthError({ status: "authentication_failed", triesLeft: 4 }, 401),
    )
    .mockRejectedValueOnce(
      new AuthError({ status: "invalid_pin", pinProblem: "unchanged" }, 400),
    );
  renderInApp(<ChangePinDialog open onClose={() => {}} />);
  pins("0000", "1234", "1234");
  expect(
    await screen.findByText("The current PIN is not right."),
  ).toBeInTheDocument();
  pins("4826", "4826", "4826");
  expect(
    await screen.findByText("Choose a PIN different from the current one."),
  ).toBeInTheDocument();
});

it("lists the trusted devices, marks this one, and forgets this browser when it is removed", async () => {
  vi.mocked(authApi).mockResolvedValue({ status: "device_revoked" });
  const onSignedOut = vi.fn();
  const onChanged = vi.fn();
  renderInApp(
    <TrustedDevicesDialog
      open
      devices={[
        {
          id: "d1",
          name: "Chrome on Windows",
          trustedAt: "2026-09-12T07:52:00Z",
          lastUsedAt: "2026-10-09T07:52:00Z",
          thisDevice: true,
        },
        {
          id: "d2",
          name: "XCODE app on Samsung Galaxy A15",
          trustedAt: "2026-09-14T10:00:00Z",
          lastUsedAt: "2026-10-08T21:10:00Z",
          thisDevice: false,
        },
      ]}
      loading={false}
      error=""
      onChanged={onChanged}
      onClose={() => {}}
      onSignedOut={onSignedOut}
    />,
  );
  expect(screen.getByText("This device")).toBeInTheDocument();
  fireEvent.click(
    screen.getByRole("button", {
      name: "Remove XCODE app on Samsung Galaxy A15",
    }),
  );
  await waitFor(() => expect(onChanged).toHaveBeenCalled());
  expect(authApi).toHaveBeenLastCalledWith("trusted-devices/d2/remove", {
    thisDevice: false,
  });
  fireEvent.click(
    screen.getByRole("button", { name: "Remove Chrome on Windows" }),
  );
  await waitFor(() => expect(onSignedOut).toHaveBeenCalled());
  expect(authApi).toHaveBeenLastCalledWith("trusted-devices/d1/remove", {
    thisDevice: true,
  });
});
