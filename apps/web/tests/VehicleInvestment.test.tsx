import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { VehiclesPage } from "../components/setup";
import type { VehicleInvestment } from "../lib/types";
import { renderInApp } from "./renderInApp";

const businessDate = "2026-09-21";

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

const investment: VehicleInvestment = {
  vehicleId: vehicle.id,
  totalInvested: 1690000,
  returned: null,
  percentPaidOff: null,
  entries: [
    { id: "entry-2", date: "2025-05-20", description: "Body, seats and refit", amount: 410000, recordedBy: "me", recordedAt: "2025-05-20T08:00:00Z" },
    { id: "entry-1", date: "2025-05-05", description: "Deposit on the unit", amount: 1280000, recordedBy: "me", recordedAt: "2025-05-05T08:00:00Z" },
  ],
};

function serve() {
  const fetchMock = vi.fn(async (input: string, init?: RequestInit) => {
    if (init?.method) return new Response(JSON.stringify({ id: "entry-3" }), { status: 200 });
    if (input.includes("/investment")) return new Response(JSON.stringify(investment), { status: 200 });
    if (input.includes("company-options")) return new Response(JSON.stringify([{ id: "company-1", name: "North Star" }]), { status: 200 });
    return new Response(JSON.stringify({ items: [vehicle], pageNumber: 1, pageSize: 25, total: 1 }), { status: 200 });
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

const writes = (fetchMock: ReturnType<typeof serve>) =>
  fetchMock.mock.calls.filter(([, init]) => init?.method).map(([url, init]) => [url, init!.method, init!.body ? JSON.parse(String(init!.body)) : undefined]);

async function openVehicle(permissions: string[], businessDateShown: string | undefined = businessDate) {
  renderInApp(<VehiclesPage />, { permissions: ["vehicles.manage", ...permissions] }, { businessDate: businessDateShown });
  fireEvent.click(await screen.findByRole("button", { name: "KDA 482M" }));
}

afterEach(() => vi.useRealTimers());

it("hides the Investment tab without invest.view", async () => {
  const fetchMock = serve();
  await openVehicle([]);

  expect(screen.getByRole("tab", { name: "Details" })).toHaveAttribute("aria-selected", "true");
  expect(screen.getByRole("tab", { name: "Report" })).toBeInTheDocument();
  expect(screen.queryByRole("tab", { name: "Investment" })).not.toBeInTheDocument();
  expect(fetchMock.mock.calls.some(([url]) => url.includes("investment"))).toBe(false);
});

it("shows what went in, with what has come back left blank until it can be worked out", async () => {
  const fetchMock = serve();
  await openVehicle(["invest.view"]);
  fireEvent.click(screen.getByRole("tab", { name: "Investment" }));

  expect(await screen.findByText("Deposit on the unit")).toBeInTheDocument();
  expect(fetchMock).toHaveBeenCalledWith("/api/setup/vehicles/vehicle-1/investment", expect.anything());
  expect(screen.getByText("Money put in before and around buying it. It is not counted as money out.")).toBeInTheDocument();
  const stat = (label: string) => screen.getByText(label, { selector: "small" }).nextElementSibling;
  expect(stat("Invested")).toHaveTextContent("KES 1,690,000");
  expect(stat("Back so far")).toHaveTextContent("—");
  expect(stat("Paid back")).toHaveTextContent("—");
  // Oldest first.
  const dates = [...screen.getAllByRole("row")].slice(1).map((row) => row.querySelector("td")?.textContent);
  expect(dates).toEqual(["5 May 2025", "20 May 2025"]);
  expect(screen.getByText("2 entries")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /Add investment|Edit|Remove/ })).not.toBeInTheDocument();
});

it("shows what has come back once the server works it out", async () => {
  serve();
  investment.returned = 845000;
  investment.percentPaidOff = 50;
  try {
    await openVehicle(["invest.view"]);
    fireEvent.click(screen.getByRole("tab", { name: "Investment" }));
    expect(await screen.findByText("KES 845,000")).toBeInTheDocument();
    expect(screen.getByText("50%")).toBeInTheDocument();
  } finally {
    investment.returned = null;
    investment.percentPaidOff = null;
  }
});

it("adds, edits and removes entries with invest.manage", async () => {
  const fetchMock = serve();
  await openVehicle(["invest.view", "invest.manage"]);
  fireEvent.click(screen.getByRole("tab", { name: "Investment" }));
  await screen.findByText("Deposit on the unit");

  fireEvent.click(screen.getByRole("button", { name: "Add investment" }));
  const dialog = within(screen.getByRole("dialog", { name: "Add investment" }));
  expect(dialog.getByLabelText("Date")).toHaveValue(businessDate);
  // The API refuses an entry dated after the business date.
  expect(dialog.getByLabelText("Date")).toHaveAttribute("max", businessDate);
  fireEvent.click(dialog.getByRole("button", { name: "Add" }));
  expect(dialog.getByRole("alert")).toHaveTextContent("Say what it was.");
  fireEvent.change(dialog.getByLabelText("What it was"), { target: { value: "Speed governor" } });
  fireEvent.change(dialog.getByLabelText("Amount"), { target: { value: "35000" } });
  fireEvent.click(dialog.getByRole("button", { name: "Add" }));
  await waitFor(() =>
    expect(writes(fetchMock)).toEqual([["/api/setup/vehicles/vehicle-1/investment", "POST", { date: businessDate, description: "Speed governor", amount: 35000 }]]),
  );

  fireEvent.click(screen.getByRole("button", { name: "Edit Deposit on the unit" }));
  expect(screen.getByLabelText("Date")).toHaveAttribute("max", businessDate);
  fireEvent.change(screen.getByLabelText("Amount"), { target: { value: "1300000" } });
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() => expect(writes(fetchMock)[1]).toEqual(["/api/setup/investment/entry-1", "PUT", { date: "2025-05-05", description: "Deposit on the unit", amount: 1300000 }]));

  fireEvent.click(screen.getByRole("button", { name: "Remove Body, seats and refit" }));
  expect(writes(fetchMock)).toHaveLength(2);
  fireEvent.click(screen.getByRole("button", { name: "Tap again to remove Body, seats and refit" }));
  await waitFor(() => expect(writes(fetchMock)[2]).toEqual(["/api/setup/investment/entry-2", "DELETE", undefined]));
});

it("dates a new vehicle from the business date, never the computer clock", async () => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date("2026-12-01T10:00:00Z"));
  serve();

  const { unmount } = renderInApp(<VehiclesPage />, { permissions: ["vehicles.manage"] });
  fireEvent.click(await screen.findByRole("button", { name: "Add vehicle" }));
  expect(screen.getByLabelText("In the fleet from")).toHaveValue("");
  unmount();

  renderInApp(<VehiclesPage />, { permissions: ["vehicles.manage"] }, { businessDate });
  fireEvent.click(await screen.findByRole("button", { name: "Add vehicle" }));
  expect(screen.getByLabelText("In the fleet from")).toHaveValue(businessDate);
  expect(screen.getByLabelText("In the fleet from")).toHaveAttribute("max", businessDate);
});
