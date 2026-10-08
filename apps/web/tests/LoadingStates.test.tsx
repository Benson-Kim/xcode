import { act, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, expect, it, vi } from "vitest";

import { OrganizationSettingsView } from "../components/OrganizationSettingsView";
import { PeopleAccessView } from "../components/PeopleAccessView";
import { PreferencesView } from "../components/PreferencesView";
import {
  CompaniesPage,
  ExpenseCategoriesPage,
  HistoryPage,
  RecurringPage,
  VehiclesPage,
} from "../components/setup";
import { renderInApp } from "./renderInApp";

// Every request waits until the test releases it, so the loading state can be inspected.
let release: () => void;
beforeEach(() => {
  let open: () => void = () => {};
  const gate = new Promise<void>((resolve) => (open = resolve));
  release = () => act(async () => open());
  const emptyPage = { items: [], pageNumber: 1, pageSize: 100, total: 0 };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: string) => {
      await gate;
      const body =
        input.includes("access/roles") ||
        input.includes("access/catalog") ||
        input.includes("vehicle-options")
          ? []
          : emptyPage;
      return new Response(JSON.stringify(body), { status: 200 });
    }),
  );
});

const lists: [string, ReactNode, string, string][] = [
  [
    "PSV companies",
    <CompaniesPage key="companies" />,
    "Loading companies",
    "No PSV companies yet. Add the first one above.",
  ],
  [
    "vehicles",
    <VehiclesPage key="vehicles" />,
    "Loading vehicles",
    "No vehicles yet. Add the first one above.",
  ],
  [
    "expense items",
    <ExpenseCategoriesPage key="expenses" canManage />,
    "Loading expense items",
    "No items here yet.",
  ],
  [
    "scheduled items",
    <RecurringPage key="recurring" canManage />,
    "Loading scheduled expenses and savings",
    "Nothing here yet.",
  ],
  [
    "the change log",
    <HistoryPage key="history" />,
    "Loading the change log",
    "No setup changes yet.",
  ],
  [
    "people",
    <PeopleAccessView key="people" />,
    "Loading people",
    "Nobody in your scope yet.",
  ],
];

it.each(lists)(
  "shows placeholder rows, not the empty message, while %s load",
  async (_, page, loading, empty) => {
    renderInApp(page, {
      permissions: [
        "people.view",
        "vehicles.manage",
        "companies.manage",
        "commitments.manage",
      ],
    });

    expect(screen.getByRole("table", { name: loading })).toHaveAttribute(
      "aria-busy",
      "true",
    );
    expect(screen.queryByText(empty)).not.toBeInTheDocument();

    await release();
    expect(await screen.findByText(empty)).toBeInTheDocument();
    expect(screen.getByRole("table")).not.toHaveAttribute("aria-busy");
  },
);

it.each([
  [
    "organization settings",
    <OrganizationSettingsView key="settings" />,
    "Loading organization settings",
  ],
  [
    "preferences",
    <PreferencesView key="preferences" />,
    "Loading your preferences",
  ],
])("shows a form placeholder while %s load", (_, page, loading) => {
  renderInApp(page);
  expect(screen.getByRole("status")).toHaveTextContent(loading);
  expect(
    screen.queryByRole("button", { name: /Save/ }),
  ).not.toBeInTheDocument();
});
