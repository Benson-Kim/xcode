import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { AuthError } from "@xcode/shared/auth";

import { InvitePanel } from "../components/InvitePanel";
import { authApi } from "../lib/api";

vi.mock("../lib/api", () => ({ authApi: vi.fn(), readDevice: vi.fn() }));

const token = () => {
  const bytes = crypto.getRandomValues(new Uint8Array(32));
  return btoa(String.fromCharCode(...bytes))
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");
};

const desktop = window.navigator.userAgent;
const userAgent = (value: string) =>
  Object.defineProperty(window.navigator, "userAgent", {
    value,
    configurable: true,
  });

beforeEach(() => {
  vi.mocked(authApi).mockReset();
});
afterEach(() => {
  userAgent(desktop);
  window.history.replaceState(null, "", "/");
});

const typeNumber = (value: string) => {
  fireEvent.change(screen.getByLabelText("Mobile number"), {
    target: { value },
  });
  fireEvent.click(screen.getByRole("button", { name: "Continue" }));
};

it("takes the token off the address bar before anything is sent, then confirms the number and sets the first PIN", async () => {
  const link = token();
  window.history.replaceState(null, "", `/invite#${link}`);
  vi.mocked(authApi)
    .mockResolvedValueOnce({
      status: "verification_required",
      purpose: "first_setup",
    })
    .mockResolvedValueOnce({ status: "authenticated" });
  const signedIn = vi.fn();
  render(<InvitePanel stores={{}} onSignedIn={signedIn} />);

  await screen.findByLabelText("Mobile number");
  expect(window.location.hash).toBe("");
  expect(window.location.href).not.toContain(link);
  expect(window.location.pathname).toBe("/invite");
  expect(authApi).not.toHaveBeenCalled();

  typeNumber("0733 520 614");
  await screen.findByRole("heading", { name: "Choose your PIN" });
  expect(authApi).toHaveBeenCalledWith("invite/redeem", {
    token: link,
    phoneNumber: "0733520614",
  });

  fireEvent.change(screen.getByLabelText("New PIN"), {
    target: { value: "5826" },
  });
  fireEvent.change(screen.getByLabelText("Repeat PIN"), {
    target: { value: "5826" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Save and sign in" }));
  await waitFor(() => expect(signedIn).toHaveBeenCalled());
  // The code the link minted stays in the proxy's cookie: the page sends none.
  expect(authApi).toHaveBeenLastCalledWith("pin/new", {
    phoneNumber: "0733520614",
    purpose: "first_setup",
    code: "",
    pin: "5826",
    trustDevice: true,
  });
});

it("says a link without a usable token is incomplete, and sends nothing", async () => {
  for (const hash of ["", "#short", `#${token().slice(2)}!!`]) {
    window.history.replaceState(null, "", `/invite${hash}`);
    const { unmount } = render(<InvitePanel stores={{}} />);
    expect(
      await screen.findByText(/This link is incomplete/),
    ).toBeInTheDocument();
    expect(window.location.hash).toBe("");
    unmount();
  }
  expect(authApi).not.toHaveBeenCalled();
});

it("never puts the fragment on the page: markup in it is an incomplete link, and a real token is not shown", async () => {
  for (const hash of [
    "#<img src=x onerror=alert(1)>",
    "#javascript:alert(document.domain)",
    `#${token()}"><svg onload=alert(1)>`,
  ]) {
    window.history.replaceState(null, "", `/invite${hash}`);
    const { container, unmount } = render(<InvitePanel stores={{}} />);
    expect(
      await screen.findByText(/This link is incomplete/),
    ).toBeInTheDocument();
    expect(container.querySelector("[onerror], [onload]")).toBeNull();
    expect(container.innerHTML).not.toMatch(/alert\(|onerror|onload/);
    expect(window.location.hash).toBe("");
    unmount();
  }
  expect(authApi).not.toHaveBeenCalled();

  const link = token();
  window.history.replaceState(null, "", `/invite#${link}`);
  render(<InvitePanel stores={{}} />);
  await screen.findByLabelText("Mobile number");
  expect(document.documentElement.innerHTML).not.toContain(link);
  expect(window.location.href).not.toContain(link);
});

it("tells a refused number apart only when the API says why", async () => {
  window.history.replaceState(null, "", `/invite#${token()}`);
  vi.mocked(authApi)
    .mockRejectedValueOnce(
      new AuthError({ status: "authentication_failed" }, 401),
    )
    .mockRejectedValueOnce(
      new AuthError(
        { status: "authentication_failed", inviteProblem: "expired" },
        401,
      ),
    );
  render(<InvitePanel stores={{}} />);
  await screen.findByLabelText("Mobile number");

  typeNumber("0733520614");
  expect(
    await screen.findByText(/This number does not match the invitation/),
  ).toBeInTheDocument();
  expect(screen.queryByRole("link", { name: "Go to sign in" })).toBeNull();
  typeNumber("0733520614");
  expect(
    await screen.findByText(
      "This invitation has expired. Ask the office to send it again.",
    ),
  ).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Go to sign in" })).toHaveAttribute(
    "href",
    "/",
  );
  expect(screen.queryByRole("button", { name: "Continue" })).toBeNull();
});

it("goes back to the number when the minted code ran out while the PIN was chosen", async () => {
  window.history.replaceState(null, "", `/invite#${token()}`);
  vi.mocked(authApi)
    .mockResolvedValueOnce({
      status: "verification_required",
      purpose: "first_setup",
    })
    .mockRejectedValueOnce(
      new AuthError({ status: "authentication_failed" }, 401),
    );
  render(<InvitePanel stores={{}} />);
  await screen.findByLabelText("Mobile number");
  typeNumber("0733520614");
  fireEvent.change(await screen.findByLabelText("New PIN"), {
    target: { value: "5826" },
  });
  fireEvent.change(screen.getByLabelText("Repeat PIN"), {
    target: { value: "5826" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Save and sign in" }));
  expect(
    await screen.findByText("That took too long. Confirm your number again."),
  ).toBeInTheDocument();
  expect(screen.getByLabelText("Mobile number")).toBeInTheDocument();
});

it("shows the store links on a phone only", async () => {
  const stores = {
    appStore: "https://apps.apple.com/app/id1",
    playStore:
      "https://play.google.com/store/apps/details?id=ke.co.priori.xcode",
  };
  window.history.replaceState(null, "", `/invite#${token()}`);
  const { unmount } = render(<InvitePanel stores={stores} />);
  await screen.findByLabelText("Mobile number");
  expect(screen.queryByText("Get the app")).not.toBeInTheDocument();
  unmount();

  userAgent(
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 Chrome/130.0 Mobile Safari/537.36",
  );
  window.history.replaceState(null, "", `/invite#${token()}`);
  render(<InvitePanel stores={stores} />);
  expect(await screen.findByText("Get the app")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Google Play" })).toHaveAttribute(
    "href",
    stores.playStore,
  );
});

const pasteLink = (link: string) =>
  act(() => {
    window.history.replaceState(null, "", `/invite#${link}`);
    window.dispatchEvent(new HashChangeEvent("hashchange"));
  });

it("takes a link pasted into the same tab, clears it and redeems that token instead of the first one", async () => {
  window.history.replaceState(null, "", `/invite#${token()}`);
  vi.mocked(authApi).mockResolvedValueOnce({
    status: "verification_required",
    purpose: "first_setup",
  });
  render(<InvitePanel stores={{}} />);
  await screen.findByLabelText("Mobile number");

  const latest = token();
  pasteLink(latest);
  expect(window.location.hash).toBe("");
  typeNumber("0733 520 614");
  await screen.findByRole("heading", { name: "Choose your PIN" });

  expect(authApi).toHaveBeenCalledTimes(1);
  expect(authApi).toHaveBeenCalledWith("invite/redeem", {
    token: latest,
    phoneNumber: "0733520614",
  });
});

it("moves from an incomplete link to the number step when the whole link is pasted into the same tab", async () => {
  window.history.replaceState(null, "", "/invite");
  render(<InvitePanel stores={{}} />);
  expect(screen.queryByLabelText("Mobile number")).toBeNull();

  pasteLink(token());

  await screen.findByLabelText("Mobile number");
  expect(window.location.hash).toBe("");
});
