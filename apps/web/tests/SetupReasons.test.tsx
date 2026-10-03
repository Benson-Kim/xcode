import { fireEvent, screen, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { CompaniesPage, VehiclesPage } from "../components/setup";
import { renderInApp } from "./renderInApp";

// C7: only stopping a scheduled item and removing access ask for a typed reason. Companies and vehicles are saved
// without one, and the server writes the reason for the change log.
const businessDate = "2026-09-21";
const company = { id: "company-1", name: "North Star", vehicleCount: 1, active: true };
const archived = { id: "company-2", name: "Metro Trans", vehicleCount: 0, active: false };
const vehicle = {
  id: "vehicle-1",
  companyId: company.id,
  companyName: company.name,
  registration: "KDA 482M",
  joinedOn: "2026-01-01",
  leftOn: null,
  active: true,
  weeklyTarget: 15000,
  targets: [],
  recurringItems: 0,
};

function serve(rows: Record<string, unknown[]>) {
  const fetchMock = vi.fn(async (input: string, init?: RequestInit) => {
    // Writes answer with the id of what they saved, as the API does.
    if (init?.method) return new Response(JSON.stringify({ id: input.match(/(vehicle|company)-\d/)?.[0] ?? "new-id" }), { status: 200 });
    const list = Object.entries(rows).find(([path]) => input.startsWith(`/api/setup/${path}?`))?.[1] ?? [];
    return new Response(JSON.stringify({ items: list, pageNumber: 1, pageSize: 25, total: list.length }), { status: 200 });
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

const writes = (fetchMock: ReturnType<typeof serve>) =>
  fetchMock.mock.calls.filter(([, init]) => init?.method).map(([url, init]) => [url, init!.method, JSON.parse(String(init!.body))]);

it("adds, renames, archives and restores a company without a typed reason", async () => {
  const fetchMock = serve({ companies: [company, archived] });
  renderInApp(<CompaniesPage />, { permissions: ["companies.manage"] });
  await screen.findByText("North Star");
  expect(screen.queryByLabelText(/Reason/)).not.toBeInTheDocument();

  fireEvent.change(screen.getByLabelText("New PSV company"), { target: { value: "Rongai Express" } });
  fireEvent.click(screen.getByRole("button", { name: "Add company" }));
  await waitFor(() => expect(writes(fetchMock)).toHaveLength(1));

  fireEvent.click(screen.getByRole("button", { name: "Rename North Star" }));
  expect(screen.queryByLabelText(/Reason/)).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("New name"), { target: { value: "North Star Sacco" } });
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() => expect(writes(fetchMock)).toHaveLength(2));

  fireEvent.click(screen.getByRole("button", { name: "Archive North Star" }));
  await waitFor(() => expect(writes(fetchMock)).toHaveLength(3));
  fireEvent.click(screen.getByRole("button", { name: "Restore Metro Trans" }));
  await waitFor(() => expect(writes(fetchMock)).toHaveLength(4));

  expect(writes(fetchMock)).toEqual([
    ["/api/setup/companies", "POST", { name: "Rongai Express" }],
    ["/api/setup/companies/company-1", "PUT", { name: "North Star Sacco" }],
    ["/api/setup/companies/company-1/archive", "POST", {}],
    ["/api/setup/companies/company-2/restore", "POST", {}],
  ]);
});

it("adds, edits, retires and restores a vehicle without a typed reason", async () => {
  const fetchMock = serve({ vehicles: [vehicle, { ...vehicle, id: "vehicle-2", registration: "KCY 117T", active: false, leftOn: "2026-09-10" }], companies: [company] });
  renderInApp(<VehiclesPage />, { permissions: ["vehicles.manage", "companies.manage"] }, { businessDate });

  fireEvent.click(await screen.findByRole("button", { name: "Add vehicle" }));
  expect(screen.queryByLabelText(/Reason/)).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Registration number"), { target: { value: "kdg905b" } });
  fireEvent.change(screen.getByLabelText("PSV company"), { target: { value: company.id } });
  fireEvent.change(screen.getByLabelText("Weekly performance target"), { target: { value: "14000" } });
  fireEvent.click(screen.getByRole("button", { name: "Add vehicle" }));
  await waitFor(() => expect(writes(fetchMock)).toHaveLength(1));
  // A new vehicle stays open once added; Cancel goes back to the list.
  fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

  fireEvent.click(await screen.findByRole("button", { name: "KDA 482M" }));
  expect(screen.queryByLabelText(/Reason/)).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Weekly performance target"), { target: { value: "16000" } });
  fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
  await waitFor(() => expect(writes(fetchMock)).toHaveLength(2));
  fireEvent.change(screen.getByLabelText("Leaves the fleet"), { target: { value: "2026-09-20" } });
  fireEvent.click(screen.getByRole("button", { name: "Retire vehicle" }));
  await waitFor(() => expect(writes(fetchMock)).toHaveLength(3));
  fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

  fireEvent.click(await screen.findByRole("button", { name: "KCY 117T" }));
  expect(screen.queryByLabelText(/Reason/)).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Restore to active fleet" }));
  await waitFor(() => expect(writes(fetchMock)).toHaveLength(4));

  expect(writes(fetchMock)).toEqual([
    ["/api/setup/vehicles", "POST", { registration: "KDG 905B", companyId: company.id, weeklyTarget: 14000, joinedOn: businessDate }],
    ["/api/setup/vehicles/vehicle-1", "PUT", { registration: "KDA 482M", companyId: company.id, weeklyTarget: 16000, joinedOn: "2026-01-01" }],
    ["/api/setup/vehicles/vehicle-1/retire", "POST", { leftOn: "2026-09-20" }],
    ["/api/setup/vehicles/vehicle-2/restore", "POST", {}],
  ]);
});

it("cancels an archive dated ahead of the business date with Restore instead of archiving again", async () => {
  const scheduled = { id: "company-3", name: "Future Line", vehicleCount: 0, active: true, archivedOn: "2026-09-25" };
  const fetchMock = serve({ companies: [scheduled] });
  renderInApp(<CompaniesPage />, { permissions: ["companies.manage"] });
  expect(await screen.findByText(/Archives on/)).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Restore Future Line" }));
  await waitFor(() => expect(writes(fetchMock)).toEqual([["/api/setup/companies/company-3/restore", "POST", {}]]));
});
