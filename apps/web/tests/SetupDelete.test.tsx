import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { expect, it } from "vitest";

import { CompaniesPage, VehiclesPage } from "../components/setup";
import { fakeApi } from "./fakeApi";
import { renderInApp } from "./renderInApp";

// A vehicle or a company added by mistake can be deleted while nothing uses it. The server decides what "uses" means
// and answers 409 in_use with what to do instead.
const company = {
  id: "company-1",
  name: "North Star",
  vehicleCount: 0,
  active: true,
};
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
const IN_USE = { title: "Conflict", code: "in_use" };

const page = (items: unknown[]) =>
  [200, { items, pageNumber: 1, pageSize: 25, total: items.length }] as const;

function serve() {
  const api = fakeApi();
  api.on("GET setup/vehicles*", page([vehicle]));
  api.on("GET setup/companies*", page([company]));
  api.on("GET setup/vehicles/company-options", [200, [company]]);
  return api;
}

const deletes = (api: ReturnType<typeof serve>) =>
  api.calls.filter((call) => call.method === "DELETE").map((call) => call.path);
const reads = (api: ReturnType<typeof serve>, path: string) =>
  api.calls.filter(
    (call) => call.method === "GET" && call.path.startsWith(path),
  ).length;

it("deletes a vehicle after a confirmation that names it, then reloads the list", async () => {
  const api = serve();
  api.on("DELETE setup/vehicles/vehicle-1", [204]);
  renderInApp(<VehiclesPage />, { permissions: ["vehicles.edit"] });
  await screen.findByText("KDA 482M");

  fireEvent.click(screen.getByRole("button", { name: "Delete KDA 482M" }));
  const dialog = within(screen.getByRole("dialog", { name: "Delete vehicle" }));
  expect(
    dialog.getByText(
      "Delete KDA 482M? This cannot be undone. It can be deleted only while nothing uses it.",
    ),
  ).toBeInTheDocument();
  expect(deletes(api)).toEqual([]);

  fireEvent.click(dialog.getByRole("button", { name: "Delete" }));
  expect(await screen.findByText("KDA 482M deleted.")).toBeInTheDocument();
  expect(deletes(api)).toEqual(["setup/vehicles/vehicle-1"]);
  expect(
    screen.queryByRole("dialog", { name: "Delete vehicle" }),
  ).not.toBeInTheDocument();
  await waitFor(() => expect(reads(api, "setup/vehicles?")).toBe(2));
});

it("keeps the vehicle and says what to do instead when the server finds it in use", async () => {
  const api = serve();
  const detail =
    "KDA 482M has revenue recorded. Retire it instead to keep its history.";
  api.on("DELETE setup/vehicles/vehicle-1", [409, { ...IN_USE, detail }]);
  renderInApp(<VehiclesPage />, { permissions: ["vehicles.edit"] });
  await screen.findByText("KDA 482M");

  fireEvent.click(screen.getByRole("button", { name: "Delete KDA 482M" }));
  const dialog = within(screen.getByRole("dialog", { name: "Delete vehicle" }));
  fireEvent.click(dialog.getByRole("button", { name: "Delete" }));
  expect(await dialog.findByRole("alert")).toHaveTextContent(detail);
  expect(screen.queryByText("KDA 482M deleted.")).not.toBeInTheDocument();
  expect(reads(api, "setup/vehicles?")).toBe(1);
});

it("offers vehicle Delete with vehicles.edit or the released vehicles.manage, never without them", async () => {
  serve();
  const view = renderInApp(<VehiclesPage />, {
    permissions: ["vehicles.view", "vehicles.add", "vehicles.target"],
  });
  await screen.findByText("KDA 482M");
  expect(screen.getByRole("button", { name: "Open KDA 482M" })).toBeVisible();
  expect(
    screen.queryByRole("button", { name: "Delete KDA 482M" }),
  ).not.toBeInTheDocument();
  view.unmount();

  renderInApp(<VehiclesPage />, { permissions: ["vehicles.manage"] });
  expect(
    await screen.findByRole("button", { name: "Delete KDA 482M" }),
  ).toBeVisible();
});

it("deletes a company with companies.edit, and shows the in-use refusal in the dialog", async () => {
  const api = serve();
  const detail = "North Star has vehicles. Archive it instead.";
  api.once("DELETE setup/companies/company-1", [409, { ...IN_USE, detail }]);
  api.on("DELETE setup/companies/company-1", [204]);
  renderInApp(<CompaniesPage />, { permissions: ["companies.edit"] });
  await screen.findByText("North Star");

  fireEvent.click(screen.getByRole("button", { name: "Delete North Star" }));
  const dialog = within(screen.getByRole("dialog", { name: "Delete company" }));
  fireEvent.click(dialog.getByRole("button", { name: "Delete" }));
  expect(await dialog.findByRole("alert")).toHaveTextContent(detail);

  fireEvent.click(dialog.getByRole("button", { name: "Delete" }));
  expect(await screen.findByText("North Star deleted.")).toBeInTheDocument();
  expect(deletes(api)).toEqual([
    "setup/companies/company-1",
    "setup/companies/company-1",
  ]);
  await waitFor(() => expect(reads(api, "setup/companies?")).toBe(2));
});

it("offers company Delete with companies.edit or the released companies.manage, never with companies.view", async () => {
  serve();
  const view = renderInApp(<CompaniesPage />, {
    permissions: ["companies.view"],
  });
  await screen.findByText("North Star");
  expect(
    screen.queryByRole("button", { name: "Delete North Star" }),
  ).not.toBeInTheDocument();
  view.unmount();

  renderInApp(<CompaniesPage />, { permissions: ["companies.manage"] });
  expect(
    await screen.findByRole("button", { name: "Delete North Star" }),
  ).toBeVisible();
});
