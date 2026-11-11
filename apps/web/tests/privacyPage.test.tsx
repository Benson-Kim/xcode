import { render, screen } from "@testing-library/react";
import { unstable_doesMiddlewareMatch } from "next/experimental/testing/server";
import { expect, it, vi } from "vitest";

import Privacy, { PRIVACY_CONTACT } from "../app/privacy/page";
import { config } from "../proxy";

vi.mock("next/server", async (original) => ({
  ...(await original<typeof import("next/server")>()),
  connection: vi.fn(async () => undefined),
}));

it("states, without signing in, what is kept, who handles it and how to reach the company", async () => {
  render(await Privacy());
  expect(
    screen.getByRole("heading", { level: 1, name: "XCODE privacy policy" }),
  ).toBeTruthy();
  for (const name of [
    "What XCODE keeps",
    "What XCODE does not do",
    "Who handles it",
    "How long it is kept",
    "Your choices",
    "Contact",
  ])
    expect(screen.getByRole("heading", { level: 2, name })).toBeTruthy();
  expect(
    screen
      .getByRole("link", { name: "Delete your XCODE account" })
      .getAttribute("href"),
  ).toBe("/account-deletion");
  expect(PRIVACY_CONTACT).toMatch(/^[^@\s]+@[^@\s]+\.[a-z]{2,}$/);
});

it("is served with the page policy like every other page", () => {
  expect(
    unstable_doesMiddlewareMatch({ config, nextConfig: {}, url: "/privacy" }),
  ).toBe(true);
});
