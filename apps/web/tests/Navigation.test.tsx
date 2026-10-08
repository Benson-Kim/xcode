import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { expect, it, vi } from "vitest";

import { DASHBOARD_CARDS, PERMISSION_KEYS } from "@xcode/shared/permissions";

import { AppShell } from "../components/AppShell";
import { appearanceFixture } from "./renderInApp";

function signIn(permissions: string[]) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: string) => {
      if (input.includes("/auth/session"))
        return new Response(
          JSON.stringify({
            userId: "me",
            firstName: "Test",
            lastName: "User",
            role: "Clerk",
            permissions,
          }),
          { status: 200 },
        );
      if (input.includes("appearance"))
        return new Response(JSON.stringify(appearanceFixture("2026-09-21")), {
          status: 200,
        });
      return new Response(
        JSON.stringify({ items: [], pageNumber: 1, pageSize: 100, total: 0 }),
        { status: 200 },
      );
    }),
  );
  render(<AppShell onSignOut={() => {}} />);
}

it.each([["expenses.setup"], ["expenses.view"], ["commitments.view"]])(
  "lists Expense categories under Setup for %s",
  async (permission) => {
    signIn([permission]);
    const menu = within(screen.getByRole("navigation", { name: "Main" }));
    fireEvent.click(
      await menu.findByRole("button", { name: "Expense categories" }),
    );
    expect(
      await screen.findByRole("heading", {
        name: "Expense categories",
        level: 1,
      }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Add item" }) !== null).toBe(
      permission === "expenses.setup",
    );
  },
);

it("hides Expense categories and scheduled items without any of their permissions", async () => {
  signIn(["vehicles.manage"]);
  const menu = within(screen.getByRole("navigation", { name: "Main" }));
  expect(
    await menu.findByRole("button", { name: "Vehicles" }),
  ).toBeInTheDocument();
  expect(
    menu.queryByRole("button", { name: "Expense categories" }),
  ).not.toBeInTheDocument();
  expect(
    menu.queryByRole("button", { name: "Scheduled expenses and savings" }),
  ).not.toBeInTheDocument();
});

it("names the scheduled items page Scheduled expenses and savings", async () => {
  signIn(["commitments.view"]);
  const menu = within(screen.getByRole("navigation", { name: "Main" }));
  fireEvent.click(
    await menu.findByRole("button", { name: "Scheduled expenses and savings" }),
  );
  expect(
    await screen.findByRole("heading", {
      name: "Scheduled expenses and savings",
      level: 1,
    }),
  ).toBeInTheDocument();
});

const MENU = [
  "Dashboard",
  "Revenue",
  "Petty cash",
  "PSV companies",
  "Vehicles",
  "Expense categories",
  "Scheduled expenses and savings",
  "People and access",
  "Change log",
  "Organization settings",
];

const menuLabels = () =>
  within(screen.getByRole("navigation", { name: "Main" }))
    .getAllByRole("button")
    .map((button) => button.textContent)
    .filter((label) => label !== "Setup");

it("shows the whole menu, in order, to someone holding every permission", async () => {
  signIn([...PERMISSION_KEYS]);
  const menu = within(screen.getByRole("navigation", { name: "Main" }));
  await menu.findByRole("button", { name: "Organization settings" });
  expect(menuLabels()).toEqual(MENU);
});

it("shows only the Dashboard to someone holding no permissions", async () => {
  signIn([]);
  const menu = within(screen.getByRole("navigation", { name: "Main" }));
  await menu.findByRole("button", { name: "Dashboard" });
  await waitFor(() =>
    expect(screen.queryByText(/Loading/)).not.toBeInTheDocument(),
  );
  expect(menuLabels()).toEqual(["Dashboard"]);
  expect(menu.queryByRole("button", { name: "Setup" })).not.toBeInTheDocument();
});

it.each([
  ["Vehicles", "invest.view"],
  ["Vehicles", "vehicles.manage"],
  ["Petty cash", "pettycash.issue"],
  ["Organization settings", "organization.manage"],
])("shows %s for %s alone", async (label, permission) => {
  signIn([permission]);
  const menu = within(screen.getByRole("navigation", { name: "Main" }));
  expect(await menu.findByRole("button", { name: label })).toBeInTheDocument();
});

it("titles the dashboard cards, in order, as the shared list does", async () => {
  signIn([...PERMISSION_KEYS]);
  const expected: string[] = DASHBOARD_CARDS.map((card) => card.title);
  const titles = () =>
    screen
      .queryAllByRole("heading")
      .map((heading) => heading.textContent ?? "")
      .filter((text) => expected.includes(text));
  await waitFor(() => expect(titles()).toEqual(expected));
});
