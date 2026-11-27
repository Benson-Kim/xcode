import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { expect, it } from "vitest";

import { VehiclesPage } from "../components/setup";
import type { TargetSet, Vehicle } from "../components/setup/shared";
import { fakeApi } from "./fakeApi";
import { renderInApp } from "./renderInApp";
import { offered, pick } from "./searchSelect";

// The business date is Monday 21 Sep 2026; a new set opens on Sunday 27 Sep.
const businessDate = "2026-09-21";
const flat = (figure: number) => Array<number>(7).fill(figure);

const vehicle: Vehicle = {
  id: "v-1",
  companyId: "company-1",
  companyName: "North Star",
  registration: "KDA 482M",
  fleetNumber: "14",
  joinedOn: "2026-01-01",
  leftOn: null,
  active: true,
  weeklyTarget: 14000,
  dayTargets: flat(2000),
  lowBelow: 3500,
  initialInvestment: 1200000,
  nextTarget: {
    startsOn: "2026-10-05",
    dayTargets: flat(2500),
    weeklyTarget: 17500,
    lowBelow: 3000,
  },
  targets: [],
  recurringItems: 0,
};

const sets: TargetSet[] = [
  {
    id: "t-2",
    startsOn: "2026-10-05",
    days: flat(2500),
    lowBelow: 3000,
    weekTotal: 17500,
    inForce: false,
    canRemove: true,
  },
  {
    id: "t-1",
    startsOn: "2026-01-01",
    days: flat(2000),
    lowBelow: 3500,
    weekTotal: 14000,
    inForce: true,
    canRemove: false,
  },
];

function serve() {
  const api = fakeApi();
  api.on("GET setup/vehicles*", [
    200,
    { items: [vehicle], pageNumber: 1, pageSize: 25, total: 1 },
  ]);
  api.on("GET setup/vehicles/company-options", [
    200,
    [{ id: "company-1", name: "North Star" }],
  ]);
  api.on("GET setup/vehicles/v-1/targets", [200, sets]);
  api.on("POST setup/vehicles/v-1/targets", [200, { id: "t-3" }]);
  api.on("POST setup/vehicles", [200, { id: "v-9" }]);
  return api;
}

const writes = (api: ReturnType<typeof serve>) =>
  api.calls
    .filter((call) => call.method !== "GET")
    .map((call) => [call.method, call.path, call.body]);

const headers = (scope: { getAllByRole: typeof screen.getAllByRole }) =>
  scope.getAllByRole("columnheader").map((cell) => cell.textContent);

async function openDialog(targets: boolean) {
  const api = serve();
  renderInApp(
    <VehiclesPage />,
    { permissions: ["vehicles.view", "vehicles.target"] },
    { businessDate, targets },
  );
  const name = targets ? "Targets" : "Low revenue";
  fireEvent.click(
    await screen.findByRole("button", { name: `${name} KDA 482M` }),
  );
  const dialog = within(await screen.findByRole("dialog", { name }));
  await dialog.findByText("Now");
  return { api, dialog };
}

it("with Targets off, lists no Weekly target column, keeps Low below, and names the row action Low revenue", async () => {
  serve();
  renderInApp(
    <VehiclesPage />,
    { permissions: ["vehicles.view", "vehicles.target"] },
    { businessDate, targets: false },
  );

  const row = within(await screen.findByRole("row", { name: /KDA 482M/ }));
  expect(headers(screen)).not.toContain("Weekly target");
  expect(headers(screen)).toContain("Low below");
  expect(row.getByText(/^3,500/)).toHaveAttribute("data-label", "Low below");
  expect(row.queryByText(/^14,000/)).not.toBeInTheDocument();
  expect(
    row.getByRole("button", { name: "Low revenue KDA 482M" }),
  ).toBeVisible();
  expect(
    row.queryByRole("button", { name: "Targets KDA 482M" }),
  ).not.toBeInTheDocument();
  const footer = [
    ...screen.getAllByRole("row").at(-1)!.querySelectorAll("td"),
  ].map((cell) => cell.textContent);
  expect(footer).not.toContain("14,000");
});

it("with Targets on, saves a changed low figure alone with the days typed", async () => {
  const { api, dialog } = await openDialog(true);

  expect(headers(dialog)).toContain("Low");
  expect(headers(dialog)).toContain("Week");
  expect(dialog.getByLabelText("Low revenue below, KES")).toHaveValue("3500");
  fireEvent.change(dialog.getByLabelText("Low revenue below, KES"), {
    target: { value: "3200" },
  });
  fireEvent.click(dialog.getByRole("button", { name: "Save target" }));

  await waitFor(() => expect(writes(api)).toHaveLength(1));
  expect(writes(api)[0]).toEqual([
    "POST",
    "setup/vehicles/v-1/targets",
    { startsOn: "2026-09-27", days: flat(2000), lowBelow: 3200 },
  ]);
});

it("with Targets off, titles the pop up Low revenue, asks no day targets and resends the days in force on the start date", async () => {
  const { api, dialog } = await openDialog(false);

  expect(dialog.getByText("Starts")).toBeVisible();
  expect(dialog.queryByLabelText(/^Target, /)).not.toBeInTheDocument();
  expect(dialog.queryByText("Target for the week")).not.toBeInTheDocument();
  expect(headers(dialog).slice(0, 2)).toEqual(["From", "Low"]);
  expect(headers(dialog)).not.toContain("Week");
  expect(headers(dialog)).not.toContain("Sun");
  const now = within(dialog.getByText("Now").closest("tr")!);
  expect(now.getByText("3,500")).toBeVisible();

  // From Tuesday 6 Oct the set starting 5 Oct is in force, so its days go back unchanged.
  for (let step = 0; step < 9; step += 1)
    fireEvent.click(dialog.getByRole("button", { name: "Next day" }));
  fireEvent.change(dialog.getByLabelText("Low revenue below, KES"), {
    target: { value: "3200" },
  });
  fireEvent.click(dialog.getByRole("button", { name: "Save" }));

  await waitFor(() => expect(writes(api)).toHaveLength(1));
  expect(writes(api)[0]).toEqual([
    "POST",
    "setup/vehicles/v-1/targets",
    { startsOn: "2026-10-06", days: flat(2500), lowBelow: 3200 },
  ]);
  expect(
    await screen.findByText("Low revenue figure saved, from 6 Oct 2026"),
  ).toBeVisible();
});

it("with Targets off, refuses the figure already in force and an empty figure, before sending", async () => {
  const { api, dialog } = await openDialog(false);

  fireEvent.click(dialog.getByRole("button", { name: "Save" }));
  expect(dialog.getByRole("alert")).toHaveTextContent(
    "This is the low revenue figure already set for 27 Sep 2026.",
  );
  fireEvent.change(dialog.getByLabelText("Low revenue below, KES"), {
    target: { value: "" },
  });
  fireEvent.click(dialog.getByRole("button", { name: "Save" }));
  expect(dialog.getByRole("alert")).toHaveTextContent(
    "Enter the low revenue figure.",
  );
  expect(writes(api)).toEqual([]);
});

it("with Targets off, adds a vehicle with no day targets, sending zeros and the low figure, 4,000 to start", async () => {
  const api = serve();
  renderInApp(
    <VehiclesPage />,
    { permissions: ["vehicles.add"] },
    { businessDate, targets: false },
  );

  fireEvent.click(await screen.findByRole("button", { name: "New vehicle" }));
  const dialog = within(screen.getByRole("dialog", { name: "New vehicle" }));
  expect(dialog.queryByLabelText(/^Target, /)).not.toBeInTheDocument();
  expect(dialog.getByLabelText("Low revenue below, KES")).toHaveValue("4000");
  fireEvent.change(dialog.getByLabelText("Registration"), {
    target: { value: "kdn 204b" },
  });
  fireEvent.change(dialog.getByLabelText("Fleet number"), {
    target: { value: "30" },
  });
  await offered(dialog.getByLabelText("PSV company"), "North Star");
  pick(dialog.getByLabelText("PSV company"), "North Star");
  fireEvent.change(dialog.getByLabelText("Low revenue below, KES"), {
    target: { value: "" },
  });
  fireEvent.click(dialog.getByRole("button", { name: "Save" }));
  expect(dialog.getByRole("alert")).toHaveTextContent(
    "Enter the low revenue figure.",
  );
  expect(writes(api)).toEqual([]);

  fireEvent.change(dialog.getByLabelText("Low revenue below, KES"), {
    target: { value: "2,500" },
  });
  expect(dialog.getByLabelText("Low revenue below, KES")).toHaveValue("2500");
  fireEvent.click(dialog.getByRole("button", { name: "Save" }));
  await waitFor(() => expect(writes(api)).toHaveLength(1));
  expect(writes(api)[0]).toEqual([
    "POST",
    "setup/vehicles",
    {
      registration: "KDN 204B",
      companyId: "company-1",
      joinedOn: businessDate,
      fleetNumber: "30",
      dayTargets: flat(0),
      lowBelow: 2500,
      initialInvestment: null,
    },
  ]);
});
