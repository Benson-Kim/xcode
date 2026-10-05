import { fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { PeopleAccessView } from "../components/PeopleAccessView";
import { renderInApp } from "./renderInApp";

const responses: Record<string, unknown> = {
  "/api/setup/people?page=1&pageSize=25": { items: [], pageNumber: 1, pageSize: 25, total: 0 },
  "/api/setup/access/catalog": [
    {
      name: "Revenue",
      items: [
        { key: "revenue.view", label: "View revenue records", needs: [] },
        { key: "revenue.capture", label: "Capture revenue", needs: ["revenue.view"] },
        { key: "reports.view", label: "View reports", needs: [] },
      ],
    },
  ],
  "/api/setup/access/roles": [
    { id: "role-1", name: "Revenue clerk", permissions: ["revenue.view", "revenue.capture"] },
    { id: "role-2", name: "Fleet manager", permissions: ["fleet.view", "fleet.manage"] },
  ],
  "/api/setup/access/scope-options": {
    companies: [{ id: "company-1", name: "North Star" }],
    vehicles: [{ id: "vehicle-1", registration: "KDA 482M", companyId: "company-1" }],
  },
};

beforeEach(() => {
  responses["/api/setup/people?page=1&pageSize=25"] = {
    items: [],
    pageNumber: 1,
    pageSize: 25,
    total: 0,
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: string, init?: RequestInit) =>
      init?.method === "POST"
        ? new Response(JSON.stringify({ id: "person-1" }), { status: 200 })
        : new Response(JSON.stringify(responses[input]), { status: 200 }),
    ),
  );
});

async function openNewPerson(canManageAccess: boolean) {
  renderInApp(<PeopleAccessView canManageAccess={canManageAccess} />, {
    role: "Office admin",
    permissions: canManageAccess
      ? ["people.view", "people.manage", "access.manage", "revenue.view", "revenue.capture"]
      : ["people.view", "people.manage", "revenue.view", "revenue.capture"],
  });
  fireEvent.click(await screen.findByRole("button", { name: "Add person" }));
  fireEvent.change(screen.getByLabelText("First name"), { target: { value: "Jane" } });
  fireEvent.change(screen.getByLabelText("Last name"), { target: { value: "Njeri" } });
  fireEvent.change(screen.getByLabelText("Email"), { target: { value: "jane@example.com" } });
  fireEvent.change(screen.getByLabelText("Mobile number"), { target: { value: "0711000001" } });
}

it("limits a person to chosen vehicles and sends the role's own defaults", async () => {
  await openNewPerson(false);

  expect(screen.getByLabelText("Capture revenue")).toBeChecked();
  expect(screen.getByLabelText("View reports")).not.toBeChecked();
  expect(screen.getByLabelText("View reports")).toBeDisabled();

  fireEvent.click(screen.getByRole("button", { name: "Save person" }));
  expect(screen.getByRole("alert")).toHaveTextContent("Fix the highlighted field to save.");
  expect(screen.getByText("Tick at least one vehicle.")).toBeInTheDocument();
  expect(fetch).not.toHaveBeenCalledWith("/api/setup/people", expect.objectContaining({ method: "POST" }));

  fireEvent.click(await screen.findByLabelText("KDA 482M"));
  fireEvent.click(screen.getByRole("button", { name: "Save person" }));

  await waitFor(() => expect(fetch).toHaveBeenCalledWith("/api/setup/people", expect.objectContaining({ method: "POST" })));
  const post = vi.mocked(fetch).mock.calls.find(([, init]) => init?.method === "POST")!;
  expect(JSON.parse(String(post[1]!.body))).toMatchObject({
    scopeMode: "vehicles",
    vehicleIds: ["vehicle-1"],
    companyIds: [],
    permissions: ["revenue.view", "revenue.capture"],
  });
});

it("ticking a permission ticks what it needs, wherever it sits in the catalogue", async () => {
  await openNewPerson(true);

  // Unticking the one it needs takes the dependent with it, and says so.
  fireEvent.click(screen.getByLabelText("View revenue records"));
  expect(screen.getByLabelText("Capture revenue")).not.toBeChecked();
  expect(screen.getByText(/Also unticked, because it needs this: Capture revenue/)).toBeInTheDocument();

  // Ticking the dependent again brings back what it needs. "Capture revenue" is not the first permission in
  // the catalogue, which is the case that used to be missed.
  fireEvent.click(screen.getByLabelText("Capture revenue"));
  expect(screen.getByLabelText("View revenue records")).toBeChecked();
  expect(screen.getByText(/Also ticked, because it is needed: View revenue records/)).toBeInTheDocument();

  fireEvent.click(await screen.findByLabelText("KDA 482M"));
  fireEvent.click(screen.getByRole("button", { name: "Save person" }));
  await waitFor(() => expect(fetch).toHaveBeenCalledWith("/api/setup/people", expect.objectContaining({ method: "POST" })));
  const post = vi.mocked(fetch).mock.calls.find(([, init]) => init?.method === "POST")!;
  expect(JSON.parse(String(post[1]!.body)).permissions).toEqual(expect.arrayContaining(["revenue.view", "revenue.capture"]));
});

it("offers companies when the scope is chosen companies", async () => {
  await openNewPerson(true);
  fireEvent.click(screen.getByRole("radio", { name: "Chosen companies" }));
  fireEvent.click(await screen.findByLabelText("North Star"));
  fireEvent.click(screen.getByLabelText("View reports"));
  fireEvent.click(screen.getByRole("button", { name: "Save person" }));

  await waitFor(() => expect(fetch).toHaveBeenCalledWith("/api/setup/people", expect.objectContaining({ method: "POST" })));
  const post = vi.mocked(fetch).mock.calls.find(([, init]) => init?.method === "POST")!;
  expect(JSON.parse(String(post[1]!.body))).toMatchObject({
    scopeMode: "companies",
    companyIds: ["company-1"],
    vehicleIds: [],
    permissions: expect.arrayContaining(["reports.view"]),
  });
});

it("says why the server refused to save a person", async () => {
  const detail = "You can only give access to the companies you can see yourself.";
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: string, init?: RequestInit) =>
      init?.method === "POST"
        ? new Response(JSON.stringify({ title: "Not permitted in this organization or data scope.", status: 403, detail }), { status: 403 })
        : new Response(JSON.stringify(responses[input]), { status: 200 }),
    ),
  );
  await openNewPerson(false);
  fireEvent.click(await screen.findByLabelText("KDA 482M"));
  fireEvent.click(screen.getByRole("button", { name: "Save person" }));

  expect(await screen.findByRole("alert")).toHaveTextContent(detail);
  expect(screen.queryByText("Not permitted in this organization or data scope.")).not.toBeInTheDocument();
});

it("asks for the reason beside its field before removing someone's access", async () => {
  const grace = {
    id: "person-2", firstName: "Grace", lastName: "Achieng", email: "grace@example.com", phoneNumber: "+254711222333", role: "Revenue clerk",
    active: true, scopeMode: "companies", companyIds: ["company-1"], vehicleIds: [], permissions: ["revenue.view", "revenue.capture"], hasPin: true, version: 3,
  };
  const fetcher = vi.fn(async (input: string, init?: RequestInit) =>
    init?.method === "POST"
      ? new Response(JSON.stringify({ ok: true }), { status: 200 })
      : new Response(JSON.stringify(input.startsWith("/api/setup/people?") ? { items: [grace], pageNumber: 1, pageSize: 25, total: 1 } : responses[input]), { status: 200 }),
  );
  vi.stubGlobal("fetch", fetcher);
  renderInApp(<PeopleAccessView canManageAccess />, { role: "Owner", permissions: ["people.view", "people.manage", "access.manage"] });
  fireEvent.click(await screen.findByRole("button", { name: "Grace Achieng" }));
  fireEvent.click(screen.getByRole("button", { name: "Remove access" }));
  fireEvent.click(screen.getByRole("button", { name: "Confirm removal" }));

  expect(screen.getByRole("alert")).toHaveTextContent("Give a reason for removing access.");
  expect(screen.getByLabelText("Reason")).toHaveAttribute("aria-invalid", "true");
  expect(fetcher).not.toHaveBeenCalledWith("/api/setup/people/person-2/deactivate", expect.anything());

  fireEvent.change(screen.getByLabelText("Reason"), { target: { value: "Left the SACCO" } });
  fireEvent.click(screen.getByRole("button", { name: "Confirm removal" }));
  await waitFor(() =>
    expect(fetcher).toHaveBeenCalledWith(
      "/api/setup/people/person-2/deactivate",
      expect.objectContaining({ method: "POST", body: JSON.stringify({ version: 3, reason: "Left the SACCO" }) }),
    ),
  );
});

it("filters the list by role and by where each person is with signing in", async () => {
  const person = (id: string, firstName: string, role: string, extra: object) => ({
    id, firstName, lastName: "Test", email: `${id}@example.com`, phoneNumber: "+254711000000", role, active: true, scopeMode: "all",
    companyIds: [], vehicleIds: [], permissions: [], hasPin: true, version: 1, ...extra,
  });
  const people = [person("a", "Amina", "Revenue clerk", {}), person("b", "Baraka", "Owner", { hasPin: false }), person("c", "Chebet", "Revenue clerk", { active: false })];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: string) =>
      new Response(JSON.stringify(input.startsWith("/api/setup/people?") ? { items: people, pageNumber: 1, pageSize: 25, total: 3 } : responses[input]), { status: 200 }),
    ),
  );
  renderInApp(<PeopleAccessView />, { permissions: ["people.view"] });
  expect(await screen.findByText("3 people")).toBeInTheDocument();

  fireEvent.change(screen.getByLabelText("Sign in"), { target: { value: "waiting" } });
  expect(screen.getByText("1 person")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Baraka Test" })).toBeInTheDocument();

  fireEvent.change(screen.getByLabelText("Sign in"), { target: { value: "all" } });
  fireEvent.change(screen.getByLabelText("Role"), { target: { value: "Revenue clerk" } });
  expect(screen.getByText("2 people")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Baraka Test" })).not.toBeInTheDocument();

  fireEvent.change(screen.getByLabelText("Sign in"), { target: { value: "none" } });
  expect(screen.getByRole("button", { name: "Chebet Test" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Amina Test" })).not.toBeInTheDocument();
});

it("offers only roles whose defaults the editor can grant", async () => {
  responses["/api/setup/access/roles"] = [
    { id: "role-1", name: "Revenue clerk", permissions: ["revenue.view", "revenue.capture"] },
    { id: "role-2", name: "Fleet manager", permissions: ["fleet.view", "fleet.manage"] },
    { id: "role-3", name: "People viewer", permissions: ["people.view"] },
  ];
  renderInApp(<PeopleAccessView canManageAccess />, {
    role: "Office admin",
    permissions: ["people.view", "people.manage", "access.manage"],
  });
  fireEvent.click(await screen.findByRole("button", { name: "Add person" }));

  const rolePicker = await screen.findByRole("combobox", { name: "Role" });
  await waitFor(() => expect(rolePicker).toHaveValue("People viewer"));
  expect(screen.queryByRole("option", { name: "Revenue clerk" })).not.toBeInTheDocument();
  expect(screen.queryByRole("option", { name: "Fleet manager" })).not.toBeInTheDocument();
  expect(screen.getByRole("option", { name: "People viewer" })).toBeInTheDocument();
});

it("includes hidden companies and vehicles in each person's scope summary", async () => {
  responses["/api/setup/people?page=1&pageSize=25"] = {
    items: [
      {
        id: "person-1",
        firstName: "Alex",
        lastName: "Kim",
        email: "alex@example.com",
        phoneNumber: "0711000001",
        role: "Revenue clerk",
        active: true,
        scopeMode: "companies",
        companyIds: [],
        vehicleIds: [],
        otherCompanies: 2,
        otherVehicles: 0,
        permissions: [],
        hasPin: true,
        version: 1,
      },
      {
        id: "person-2",
        firstName: "Sam",
        lastName: "Lee",
        email: "sam@example.com",
        phoneNumber: "0711000002",
        role: "Revenue clerk",
        active: true,
        scopeMode: "vehicles",
        companyIds: [],
        vehicleIds: ["vehicle-1"],
        otherCompanies: 0,
        otherVehicles: 1,
        permissions: [],
        hasPin: true,
        version: 1,
      },
    ],
    pageNumber: 1,
    pageSize: 25,
    total: 2,
  };

  renderInApp(<PeopleAccessView />, {
    permissions: ["people.view"],
  });

  expect(await screen.findByText("2 companies (2 hidden)")).toBeInTheDocument();
  expect(screen.getByText("2 vehicles (1 hidden)")).toBeInTheDocument();
});
