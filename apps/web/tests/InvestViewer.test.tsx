import { fireEvent, render, screen, within } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import { AppShell } from "../components/AppShell";
import { VehiclesPage } from "../components/setup";
import { appearanceFixture, renderInApp } from "./renderInApp";

// Someone who may see what was invested in vehicles, but not manage vehicles, reaches the Investment tab read-only.
const vehicle = {
  id: "vehicle-1",
  companyId: "company-1",
  companyName: "North Star",
  registration: "KDA 482M",
  joinedOn: "2026-01-01",
  leftOn: null,
  active: true,
  weeklyTarget: 15000,
  targets: [],
  recurringItems: 0,
};
const investment = { vehicleId: vehicle.id, totalInvested: 1280000, returned: null, percentPaidOff: null, entries: [] };

function serve(permissions: string[]) {
  const fetchMock = vi.fn(async (input: string) => {
    if (input.includes("/auth/session")) return new Response(JSON.stringify({ userId: "me", firstName: "Test", lastName: "User", role: "Investor", permissions }), { status: 200 });
    if (input.includes("appearance")) return new Response(JSON.stringify(appearanceFixture("2026-09-21")), { status: 200 });
    if (input.includes("/investment")) return new Response(JSON.stringify(investment), { status: 200 });
    return new Response(JSON.stringify({ items: [vehicle], pageNumber: 1, pageSize: 25, total: 1 }), { status: 200 });
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

const requested = (fetchMock: ReturnType<typeof serve>) => fetchMock.mock.calls.map(([url]) => url);

it("shows Vehicles in the menu for invest.view", async () => {
  serve(["invest.view"]);
  render(<AppShell onSignOut={() => {}} />);
  fireEvent.click(await within(screen.getByRole("navigation", { name: "Main" })).findByRole("button", { name: "Vehicles" }));
  expect(await screen.findByRole("button", { name: "KDA 482M" }, { timeout: 6000 })).toBeInTheDocument();
});

it("lists vehicles read-only and opens only the Investment tab", async () => {
  const fetchMock = serve(["invest.view"]);
  renderInApp(<VehiclesPage />, { permissions: ["invest.view"] }, { businessDate: "2026-09-21" });

  fireEvent.click(await screen.findByRole("button", { name: "KDA 482M" }));
  expect(screen.queryByRole("button", { name: "Add vehicle" })).not.toBeInTheDocument();
  expect(screen.getAllByRole("tab").map((tab) => tab.textContent)).toEqual(["Investment"]);
  expect(screen.getByRole("tab", { name: "Investment" })).toHaveAttribute("aria-selected", "true");
  expect(await screen.findByText("KES 1,280,000")).toBeInTheDocument();
  expect(screen.queryByLabelText("Weekly performance target")).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /Save changes|Retire vehicle|Add investment/ })).not.toBeInTheDocument();
  // Nothing it may not read: no company options, no vehicle report.
  expect(requested(fetchMock).filter((url) => /company-options|companies|report/.test(url))).toEqual([]);
});

it("adds the scheduled items tab when commitments.view is also given", async () => {
  serve(["invest.view", "commitments.view"]);
  renderInApp(<VehiclesPage />, { permissions: ["invest.view", "commitments.view"] }, { businessDate: "2026-09-21" });

  fireEvent.click(await screen.findByRole("button", { name: "KDA 482M" }));
  expect(screen.getAllByRole("tab").map((tab) => tab.textContent)).toEqual(["Scheduled items", "Investment"]);
});

it("lists the vehicles without the targets and scheduled items the server leaves out", async () => {
  // Without vehicles.manage the server sends no weekly target, target history or scheduled item count.
  const listed = { ...vehicle, weeklyTarget: null, targets: [], recurringItems: null };
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ items: [listed], pageNumber: 1, pageSize: 25, total: 1 }), { status: 200 })));
  renderInApp(<VehiclesPage />, { permissions: ["invest.view"] }, { businessDate: "2026-09-21" });

  const table = await screen.findByRole("table");
  expect(await within(table).findByRole("button", { name: "KDA 482M" })).toBeInTheDocument();
  expect(within(table).queryByRole("columnheader", { name: "Weekly target" })).not.toBeInTheDocument();
  expect(within(table).queryByRole("columnheader", { name: "Scheduled items" })).not.toBeInTheDocument();
  expect(table).not.toHaveTextContent(/KES|a day|null|NaN/);
});
