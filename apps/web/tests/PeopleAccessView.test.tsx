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
  ],
  "/api/setup/access/scope-options": {
    companies: [{ id: "company-1", name: "North Star" }],
    vehicles: [{ id: "vehicle-1", registration: "KDA 482M", companyId: "company-1" }],
  },
};

beforeEach(() => {
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
    permissions: canManageAccess ? ["people.view", "people.manage", "access.manage"] : ["people.view", "people.manage"],
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
