import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { OrganizationSettingsView } from "../components/OrganizationSettingsView";
import { PeopleAccessView } from "../components/PeopleAccessView";
import { VehiclesPage } from "../components/setup";
import type { Person } from "../lib/types";
import { renderInApp } from "./renderInApp";

// A selection must always be one of the options on screen, or say what it holds: never a value the control
// cannot show, which reads as something else and is saved as it is.

const json = (body: unknown) => new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });

function serve(routes: Record<string, unknown>) {
  const fetcher = vi.fn(async (input: RequestInfo | URL) => {
    const path = String(input);
    const key = Object.keys(routes).find((route) => path.startsWith(route));
    return key ? json(routes[key]) : new Response("{}", { status: 404 });
  });
  vi.stubGlobal("fetch", fetcher);
  return fetcher;
}

afterEach(() => vi.unstubAllGlobals());

const vehicleRow = (id: string, registration: string, companyId: string, companyName: string, active = true) => ({
  id,
  companyId,
  companyName,
  registration,
  joinedOn: "2026-01-01",
  leftOn: active ? null : "2026-06-01",
  active,
  weeklyTarget: active ? 7000 : 0,
  targets: [],
  recurringItems: 0,
});

it("never starts a new vehicle on an archived company the list is filtered by, or offers one", async () => {
  // A vehicle manager without companies.manage: the server offers active companies only. Old Fleet is archived and
  // known here only through its retired vehicle.
  serve({
    "/api/setup/vehicles/company-options": [{ id: "company-1", name: "North Star" }],
    "/api/setup/vehicles": {
      items: [vehicleRow("vehicle-1", "KDA 482M", "company-1", "North Star"), vehicleRow("vehicle-3", "KAA 100A", "company-3", "Old Fleet", false)],
      pageNumber: 1,
      pageSize: 25,
      total: 2,
    },
  });
  renderInApp(<VehiclesPage />, { permissions: ["vehicles.manage"] }, { businessDate: "2026-09-30" });

  await screen.findByRole("button", { name: "KAA 100A" });
  fireEvent.change(screen.getByLabelText("Company"), { target: { value: "company-3" } });
  expect(screen.queryByRole("button", { name: "KDA 482M" })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Add vehicle" }));

  const company = screen.getByLabelText("PSV company");
  expect(company).toHaveValue("");
  expect(within(company).queryByRole("option", { name: "Old Fleet" })).not.toBeInTheDocument();
  expect(within(company).getByRole("option", { name: "North Star" })).toBeInTheDocument();
});

it("still starts a new vehicle on the company the list is filtered by when it is active", async () => {
  serve({
    "/api/setup/vehicles/company-options": [{ id: "company-1", name: "North Star" }, { id: "company-2", name: "Metro Link" }],
    "/api/setup/vehicles": { items: [vehicleRow("vehicle-1", "KDA 482M", "company-1", "North Star")], pageNumber: 1, pageSize: 25, total: 1 },
  });
  renderInApp(<VehiclesPage />, { permissions: ["vehicles.manage"] }, { businessDate: "2026-09-30" });

  await screen.findByRole("button", { name: "KDA 482M" });
  fireEvent.change(screen.getByLabelText("Company"), { target: { value: "company-2" } });
  fireEvent.click(screen.getByRole("button", { name: "Add vehicle" }));
  expect(screen.getByLabelText("PSV company")).toHaveValue("company-2");
});

const person = (over: Partial<Person>): Person => ({
  id: "person-1",
  firstName: "Jane",
  lastName: "Njeri",
  email: "jane@example.com",
  phoneNumber: "0711000001",
  role: "Revenue clerk",
  active: true,
  scopeMode: "companies",
  companyIds: [],
  vehicleIds: [],
  // Nothing outside this viewer's reach, unless a test says otherwise.
  otherCompanies: 0,
  otherVehicles: 0,
  permissions: ["revenue.view"],
  hasPin: true,
  version: 1,
  ...over,
});

function servePeople(people: Person[]) {
  return serve({
    "/api/setup/people": { items: people, pageNumber: 1, pageSize: 25, total: people.length },
    "/api/setup/access/catalog": [{ name: "Revenue", items: [{ key: "revenue.view", label: "View revenue records", needs: [] }] }],
    "/api/setup/access/roles": [
      { id: "role-0", name: "Owner", permissions: ["revenue.view"] },
      { id: "role-1", name: "Revenue clerk", permissions: ["revenue.view"] },
      { id: "role-2", name: "Office admin", permissions: ["revenue.view"] },
    ],
    "/api/setup/access/scope-options": {
      companies: [{ id: "company-1", name: "North Star" }],
      vehicles: [{ id: "vehicle-1", registration: "KDA 482M", companyId: "company-1" }],
    },
  });
}

it("shows an owner's role as Owner to someone who may not give that role", async () => {
  servePeople([person({ id: "owner-1", firstName: "Antony", lastName: "Maina", role: "Owner", scopeMode: "all" })]);
  renderInApp(<PeopleAccessView />, { role: "Office admin", permissions: ["people.view", "people.manage"] });

  fireEvent.click(await screen.findByRole("button", { name: "Antony Maina" }));
  const role = await screen.findByLabelText("Role");
  expect(role).toBeDisabled();
  expect(role).toHaveValue("Owner");
  expect(within(role).getByRole("option", { name: "Owner" })).toBeInTheDocument();
});

it("says what a person's scope holds beyond the companies and vehicles listed", async () => {
  // company-9 is archived or outside the editor's own scope; vehicle-9 has left the fleet.
  servePeople([
    person({ id: "person-1", firstName: "Jane", lastName: "Njeri", scopeMode: "companies", companyIds: ["company-1", "company-9"] }),
    person({ id: "person-2", firstName: "Peter", lastName: "Otieno", scopeMode: "vehicles", vehicleIds: ["vehicle-9"] }),
  ]);
  const { unmount } = renderInApp(<PeopleAccessView />, { role: "Office admin", permissions: ["people.view", "people.manage"] });

  fireEvent.click(await screen.findByRole("button", { name: "Jane Njeri" }));
  expect(await screen.findByLabelText("North Star")).toBeChecked();
  expect(screen.getByText("Also 1 company that is not listed here: archived, or outside what you can see. It is kept as it is.")).toBeInTheDocument();
  unmount();

  renderInApp(<PeopleAccessView />, { role: "Office admin", permissions: ["people.view", "people.manage"] });
  fireEvent.click(await screen.findByRole("button", { name: "Peter Otieno" }));
  expect(await screen.findByLabelText("KDA 482M")).not.toBeChecked();
  expect(screen.getByText("Also 1 vehicle that is not listed here: out of the fleet, or outside what you can see. It is kept as it is.")).toBeInTheDocument();
});

it("shows a first day of the week the server holds even when it is not one of the usual three", async () => {
  // The API accepts any day (0 to 6); the picker offers Monday, Sunday and Saturday.
  serve({
    "/api/setup/organization/settings": {
      organization: { name: "Demo Fleet", slug: "demo-fleet" },
      localization: { locale: "en-GB", timeZone: "Africa/Nairobi", currency: "KES", datePattern: "medium", hour12: false, firstDayOfWeek: 2, weekNumbering: "iso8601", useGroupping: true, numberDecimals: 2 },
      branding: { displayName: "XCODE", legalName: "XCODE", logoAlt: "XCODE", primary: "#1647A6", secondary: "#14213D", accent: "#1E6B3A" },
      securityPolicy: { passwordMinLength: 12, pinLength: 4, lockoutThreshold: 5, lockoutMinutes: 15, accessTokenMinutes: 10, refreshTokenDays: 30, idleUnlockSeconds: 300, allowPinSignIn: true },
      effective: {},
    },
  });
  render(<OrganizationSettingsView />);

  const firstDay = await screen.findByLabelText("First day of week");
  expect(firstDay).toHaveValue("2");
  expect(within(firstDay).getByRole("option", { name: "Tuesday" })).toBeInTheDocument();
  expect(within(firstDay).getByRole("option", { name: "Monday" })).toBeInTheDocument();
});
