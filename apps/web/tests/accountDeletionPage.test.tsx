import { render, screen } from "@testing-library/react";
import { unstable_doesMiddlewareMatch } from "next/experimental/testing/server";
import { expect, it, vi } from "vitest";

import AccountDeletion from "../app/account-deletion/page";
import { config } from "../proxy";

vi.mock("next/server", async (original) => ({
  ...(await original<typeof import("next/server")>()),
  connection: vi.fn(async () => undefined),
}));

it("explains, without signing in, how to delete an account from the app or through an administrator", async () => {
  render(await AccountDeletion());
  expect(
    screen.getByRole("heading", {
      level: 1,
      name: "Delete your XCODE account",
    }),
  ).toBeTruthy();
  expect(
    screen.getAllByRole("listitem").map((item) => item.textContent),
  ).toEqual([
    "Open Profile.",
    "Choose Delete my account.",
    "Confirm with your PIN.",
  ]);
  for (const name of ["Without the app", "What is deleted", "What is kept"])
    expect(screen.getByRole("heading", { level: 2, name })).toBeTruthy();
});

it("is served with the page policy like every other page", () => {
  expect(
    unstable_doesMiddlewareMatch({
      config,
      nextConfig: {},
      url: "/account-deletion",
    }),
  ).toBe(true);
});
