import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { beforeAll, expect, it, vi } from "vitest";

import { DASHBOARD_CARDS, PERMISSION_KEYS } from "@xcode/shared/permissions";

import { AppShell } from "../components/AppShell";
import { appearanceFixture } from "./renderInApp";

// The shell loads each page lazily; a cold first import on a busy machine can outlast findBy's one-second wait.
beforeAll(() => import("../components/setup/RecurringPage"));

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
  "lists Expense items under Setup for %s",
  async (permission) => {
    signIn([permission]);
    const menu = within(screen.getByRole("navigation", { name: "Main" }));
    fireEvent.click(await menu.findByRole("button", { name: "Expense items" }));
    expect(
      await screen.findByRole("heading", {
        name: "Expense items",
        level: 1,
      }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "New item" }) !== null).toBe(
      permission === "expenses.setup",
    );
  },
);

it("hides Expense items and scheduled items without any of their permissions", async () => {
  signIn(["vehicles.manage"]);
  const menu = within(screen.getByRole("navigation", { name: "Main" }));
  expect(
    await menu.findByRole("button", { name: "Vehicles" }),
  ).toBeInTheDocument();
  expect(
    menu.queryByRole("button", { name: "Expense items" }),
  ).not.toBeInTheDocument();
  expect(
    menu.queryByRole("button", { name: "Scheduled expenses" }),
  ).not.toBeInTheDocument();
});

it("names the scheduled items page Scheduled expenses", async () => {
  signIn(["commitments.view"]);
  const menu = within(screen.getByRole("navigation", { name: "Main" }));
  fireEvent.click(
    await menu.findByRole("button", { name: "Scheduled expenses" }),
  );
  expect(
    await screen.findByRole("heading", {
      name: "Scheduled expenses",
      level: 1,
    }),
  ).toBeInTheDocument();
});

const MENU = [
  "Dashboard",
  "Revenue",
  "Central expenses",
  "Petty cash",
  "Scheduled expenses",
  "Reports",
  "PSV companies",
  "Vehicles",
  "Expense items",
  "People and access",
  "Change log",
  "Organization settings",
];

// The menu's entries and group headings, without the button that folds the menu to icons.
const entries = () =>
  within(screen.getByRole("navigation", { name: "Main" }))
    .getAllByRole("button")
    .filter((button) => button.getAttribute("aria-label") === null);

const menuLabels = () =>
  entries()
    .map((button) => button.textContent)
    .filter((label) => label !== "Setup" && label !== "Expenses");

it("shows the whole menu, in order, to someone holding every permission", async () => {
  signIn([...PERMISSION_KEYS]);
  const menu = within(screen.getByRole("navigation", { name: "Main" }));
  await menu.findByRole("button", { name: "Organization settings" });
  expect(menuLabels()).toEqual(MENU);
});

it("groups Expenses and Setup under their own headings, around Reports", async () => {
  signIn([...PERMISSION_KEYS]);
  const menu = within(screen.getByRole("navigation", { name: "Main" }));
  await menu.findByRole("button", { name: "Organization settings" });
  const all = entries().map((button) => button.textContent);
  expect(all).toEqual([
    "Dashboard",
    "Revenue",
    "Expenses",
    "Central expenses",
    "Petty cash",
    "Scheduled expenses",
    "Reports",
    "Setup",
    "PSV companies",
    "Vehicles",
    "Expense items",
    "People and access",
    "Change log",
    "Organization settings",
  ]);
  const group = (name: string) =>
    menu.getByRole("button", { name }).parentElement as HTMLElement;
  expect(
    within(group("Expenses")).getByRole("button", { name: "Petty cash" }),
  ).toBeInTheDocument();
  expect(
    within(group("Expenses")).queryByRole("button", { name: "Reports" }),
  ).not.toBeInTheDocument();
  expect(
    within(group("Expenses")).queryByRole("button", {
      name: "Expense items",
    }),
  ).not.toBeInTheDocument();
  expect(
    within(group("Setup")).getByRole("button", { name: "Expense items" }),
  ).toBeInTheDocument();
  expect(
    within(group("Setup")).getByRole("button", { name: "Vehicles" }),
  ).toBeInTheDocument();
});

it("folds each group on its own, and opens it again", async () => {
  signIn([...PERMISSION_KEYS]);
  const menu = within(screen.getByRole("navigation", { name: "Main" }));
  const expenses = await menu.findByRole("button", { name: "Expenses" });
  const setup = menu.getByRole("button", { name: "Setup" });
  expect(expenses).toHaveAttribute("aria-expanded", "true");
  expect(setup).toHaveAttribute("aria-expanded", "true");

  fireEvent.click(expenses);
  expect(expenses).toHaveAttribute("aria-expanded", "false");
  expect(setup).toHaveAttribute("aria-expanded", "true");
  expect(
    menu.queryByRole("button", { name: "Petty cash" }),
  ).not.toBeInTheDocument();
  expect(menu.getByRole("button", { name: "Vehicles" })).toBeInTheDocument();
  expect(menu.getByRole("button", { name: "Reports" })).toBeInTheDocument();

  fireEvent.click(setup);
  expect(
    menu.queryByRole("button", { name: "Vehicles" }),
  ).not.toBeInTheDocument();
  fireEvent.click(expenses);
  expect(menu.getByRole("button", { name: "Petty cash" })).toBeInTheDocument();
});

it.each([
  ["Central expenses", "expenses.view"],
  ["Petty cash", "pettycash.spend"],
  ["Scheduled expenses", "commitments.view"],
  ["Reports", "reports.view"],
])("shows %s, with its group, for %s alone", async (label, permission) => {
  signIn([permission]);
  const menu = within(screen.getByRole("navigation", { name: "Main" }));
  expect(await menu.findByRole("button", { name: label })).toBeInTheDocument();
  expect(menu.queryByRole("button", { name: "Expenses" }) !== null).toBe(
    label !== "Reports",
  );
});

it("keeps Expense items in Setup, out of the Expenses group, for expenses.setup alone", async () => {
  signIn(["expenses.setup"]);
  const menu = within(screen.getByRole("navigation", { name: "Main" }));
  expect(
    await menu.findByRole("button", { name: "Expense items" }),
  ).toBeInTheDocument();
  expect(
    // The group's entries follow its heading button.
    menu.getByRole("button", { name: "Expense items" }).closest(".kids")
      ?.previousElementSibling,
  ).toHaveTextContent("Setup");
  expect(
    menu.queryByRole("button", { name: "Expenses" }),
  ).not.toBeInTheDocument();
});

it.each([
  ["Central expenses", "expenses.capture"],
  ["Central expenses", "expenses.correct"],
  ["Reports", "reports.export"],
])("does not show %s for %s alone", async (label, permission) => {
  signIn([permission]);
  const menu = within(screen.getByRole("navigation", { name: "Main" }));
  await screen.findByText("Test User");
  expect(menu.queryByRole("button", { name: label })).not.toBeInTheDocument();
});

it("hides the Expenses group from someone with no expense rights, and Reports without reports.view", async () => {
  signIn(["vehicles.manage", "revenue.view"]);
  const menu = within(screen.getByRole("navigation", { name: "Main" }));
  await menu.findByRole("button", { name: "Vehicles" });
  expect(
    menu.queryByRole("button", { name: "Expenses" }),
  ).not.toBeInTheDocument();
  expect(
    menu.queryByRole("button", { name: "Reports" }),
  ).not.toBeInTheDocument();
  expect(menu.getByRole("button", { name: "Setup" })).toBeInTheDocument();
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
  expect(
    menu.queryByRole("button", { name: "Expenses" }),
  ).not.toBeInTheDocument();
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
