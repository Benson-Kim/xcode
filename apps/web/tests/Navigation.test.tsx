import { fireEvent, render, screen, within } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import { AppShell } from "../components/AppShell";
import { appearanceFixture } from "./renderInApp";

function signIn(permissions: string[]) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: string) => {
      if (input.includes("/auth/session")) return new Response(JSON.stringify({ userId: "me", firstName: "Test", lastName: "User", role: "Clerk", permissions }), { status: 200 });
      if (input.includes("appearance")) return new Response(JSON.stringify(appearanceFixture("2026-09-21")), { status: 200 });
      return new Response(JSON.stringify({ items: [], pageNumber: 1, pageSize: 100, total: 0 }), { status: 200 });
    }),
  );
  render(<AppShell onSignOut={() => {}} />);
}

it.each([["expenses.setup"], ["expenses.view"], ["commitments.view"]])("lists Expense categories under Setup for %s", async (permission) => {
  signIn([permission]);
  const menu = within(screen.getByRole("navigation", { name: "Main" }));
  fireEvent.click(await menu.findByRole("button", { name: "Expense categories" }));
  expect(await screen.findByRole("heading", { name: "Expense categories", level: 1 })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Add item" }) !== null).toBe(permission === "expenses.setup");
});

it("hides Expense categories and scheduled items without any of their permissions", async () => {
  signIn(["vehicles.manage"]);
  const menu = within(screen.getByRole("navigation", { name: "Main" }));
  expect(await menu.findByRole("button", { name: "Vehicles" })).toBeInTheDocument();
  expect(menu.queryByRole("button", { name: "Expense categories" })).not.toBeInTheDocument();
  expect(menu.queryByRole("button", { name: "Scheduled expenses and savings" })).not.toBeInTheDocument();
});

it("names the scheduled items page Scheduled expenses and savings", async () => {
  signIn(["commitments.view"]);
  const menu = within(screen.getByRole("navigation", { name: "Main" }));
  fireEvent.click(await menu.findByRole("button", { name: "Scheduled expenses and savings" }));
  expect(await screen.findByRole("heading", { name: "Scheduled expenses and savings", level: 1 })).toBeInTheDocument();
});
