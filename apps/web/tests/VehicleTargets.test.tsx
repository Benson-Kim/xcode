import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { expect, it } from "vitest";

import { VehiclesPage } from "../components/setup";
import type { TargetSet, Vehicle } from "../components/setup/shared";
import { TargetsDialog } from "../components/setup/TargetsDialog";
import { ToastProvider } from "../components/ui";
import { fakeApi } from "./fakeApi";
import { renderInApp } from "./renderInApp";

// The business date is Monday 21 Sep 2026.
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
  initialInvestment: 1200000,
  nextTarget: {
    startsOn: "2026-10-05",
    dayTargets: flat(2500),
    weeklyTarget: 17500,
  },
  targets: [],
  recurringItems: 3,
};

const sets: TargetSet[] = [
  {
    id: "t-2",
    startsOn: "2026-10-05",
    days: flat(2500),
    weekTotal: 17500,
    inForce: false,
    canRemove: true,
  },
  {
    id: "t-1",
    startsOn: "2026-01-01",
    days: flat(2000),
    weekTotal: 14000,
    inForce: true,
    canRemove: false,
  },
];

function serve(vehicles: Vehicle[] = [vehicle]) {
  const api = fakeApi();
  api.on("GET setup/vehicles*", [
    200,
    { items: vehicles, pageNumber: 1, pageSize: 25, total: vehicles.length },
  ]);
  api.on("GET setup/vehicles/company-options", [
    200,
    [{ id: "company-1", name: "North Star" }],
  ]);
  api.on("GET setup/vehicles/v-1/targets", [200, sets]);
  api.on("POST setup/vehicles/v-1/targets", [200, { id: "t-3" }]);
  api.on("POST setup/vehicle-targets/t-2/remove", [200, { id: "t-2" }]);
  api.on("POST setup/vehicles", [200, { id: "v-9" }]);
  return api;
}

const writes = (api: ReturnType<typeof serve>) =>
  api.calls
    .filter((call) => call.method !== "GET")
    .map((call) => [call.method, call.path, call.body]);

const reads = (api: ReturnType<typeof serve>, path: string) =>
  api.calls.filter((call) => call.method === "GET" && call.path === path)
    .length;

const open = async (permissions: string[]) => {
  const api = serve();
  renderInApp(<VehiclesPage />, { permissions }, { businessDate });
  fireEvent.click(
    await screen.findByRole("button", { name: "Targets KDA 482M" }),
  );
  const dialog = await screen.findByRole("dialog", { name: "Targets" });
  await within(dialog).findByText("Now");
  return { api, dialog: within(dialog), element: dialog };
};

it("shows the fleet number, the next target, the investment and the totals in the table", async () => {
  serve();
  renderInApp(
    <VehiclesPage />,
    { permissions: ["vehicles.view", "vehicles.target", "vehicles.edit"] },
    { businessDate },
  );

  const row = within(await screen.findByRole("row", { name: /KDA 482M/ }));
  expect(row.getByText("14")).toHaveAttribute("data-label", "Fleet number");
  const weekly = row.getByText(/^14,000/);
  expect(weekly).toHaveAttribute("data-label", "Weekly target");
  expect(weekly.querySelector(".note.wrap")).toHaveTextContent(
    "17,500 from 5 Oct 2026",
  );
  expect(row.getByText("1,200,000")).toHaveAttribute(
    "data-label",
    "Initial investment",
  );
  expect(row.getByText("3")).toHaveAttribute(
    "data-label",
    "Scheduled, September 2026",
  );
  expect(row.getByRole("button", { name: "Targets KDA 482M" })).toBeVisible();
  expect(row.getByRole("button", { name: "Edit KDA 482M" })).toBeVisible();
  const footer = [
    ...screen.getAllByRole("row").at(-1)!.querySelectorAll("td"),
  ].map((cell) => cell.textContent);
  expect(footer).toEqual(["1 vehicle", "14,000", "1,200,000", "", ""]);
});

it("hides the Targets button without a targets right, and treats vehicles.manage as all three", async () => {
  serve();
  const first = renderInApp(
    <VehiclesPage />,
    { permissions: ["vehicles.view", "vehicles.edit"] },
    { businessDate },
  );
  expect(
    await screen.findByRole("button", { name: "Edit KDA 482M" }),
  ).toBeVisible();
  expect(
    screen.queryByRole("button", { name: /^Targets/ }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "New vehicle" }),
  ).not.toBeInTheDocument();
  first.unmount();

  renderInApp(
    <VehiclesPage />,
    { permissions: ["vehicles.manage"] },
    { businessDate },
  );
  expect(
    await screen.findByRole("button", { name: "Targets KDA 482M" }),
  ).toBeVisible();
  expect(screen.getByRole("button", { name: "New vehicle" })).toBeVisible();
});

it("refuses a new vehicle without a registration, a fleet number or every day target, and sends nothing", async () => {
  const api = serve();
  renderInApp(
    <VehiclesPage />,
    { permissions: ["vehicles.add"] },
    { businessDate },
  );

  fireEvent.click(await screen.findByRole("button", { name: "New vehicle" }));
  const dialog = within(screen.getByRole("dialog", { name: "New vehicle" }));
  expect(dialog.getAllByLabelText(/^Target, /)).toHaveLength(7);
  fireEvent.click(dialog.getByRole("button", { name: "Same every day" }));
  expect(dialog.getByLabelText("Target, Monday")).toHaveFocus();

  fireEvent.click(dialog.getByRole("button", { name: "Save" }));
  expect(dialog.getByRole("alert")).toHaveTextContent(
    "Enter the registration like KDN 204B.",
  );
  fireEvent.change(dialog.getByLabelText("Registration"), {
    target: { value: "kdn 204b" },
  });
  fireEvent.click(dialog.getByRole("button", { name: "Save" }));
  expect(dialog.getByRole("alert")).toHaveTextContent(
    "Enter the fleet number.",
  );
  fireEvent.change(dialog.getByLabelText("Fleet number"), {
    target: { value: "30" },
  });
  await dialog.findByRole("option", { name: "North Star" });
  fireEvent.change(dialog.getByLabelText("PSV company"), {
    target: { value: "company-1" },
  });
  fireEvent.change(dialog.getByLabelText("Target, Monday"), {
    target: { value: "1800" },
  });
  fireEvent.click(dialog.getByRole("button", { name: "Save" }));
  expect(dialog.getByRole("alert")).toHaveTextContent(
    "Enter the target for every day.",
  );
  expect(writes(api)).toEqual([]);

  fireEvent.click(dialog.getByRole("button", { name: "Same every day" }));
  fireEvent.change(dialog.getByLabelText("Initial investment, KES"), {
    target: { value: "2500000" },
  });
  expect(dialog.getByText("Target for the week").nextSibling).toHaveTextContent(
    "12,600",
  );
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
      dayTargets: flat(1800),
      initialInvestment: 2500000,
    },
  ]);
});

it("opens the targets pop up on the next Monday with the set in force and the history, newest first", async () => {
  const { dialog, element } = await open(["vehicles.target", "vehicles.view"]);

  expect(element).toHaveClass("tg");
  expect(dialog.getByText("KDA 482M · 14")).toBeVisible();
  expect(dialog.getByText("New target starts")).toBeVisible();
  expect(dialog.getByText("Mon 28 Sep 2026")).toBeVisible();
  expect(dialog.getByRole("button", { name: "Previous day" })).toBeEnabled();
  for (const day of [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
  ])
    expect(dialog.getByLabelText(`Target, ${day}`)).toHaveValue("2000");
  expect(dialog.getByText("Target for the week").nextSibling).toHaveTextContent(
    "14,000",
  );

  const rows = dialog.getAllByRole("row").slice(1);
  expect(rows).toHaveLength(2);
  expect(rows[0]).toHaveTextContent("5 Oct 2026");
  expect(rows[0]).toHaveTextContent("17,500");
  expect(within(rows[0]).getByRole("button", { name: /Remove/ })).toBeVisible();
  expect(rows[1]).toHaveTextContent("1 Jan 2026");
  expect(within(rows[1]).getByText("Now")).toHaveClass("chip", "ok");
  expect(within(rows[1]).queryByRole("button")).not.toBeInTheDocument();
});

it("steps the start date but never to a day before today", async () => {
  const { dialog } = await open(["vehicles.target"]);

  const previous = dialog.getByRole("button", { name: "Previous day" });
  for (let step = 0; step < 7; step++) fireEvent.click(previous);
  expect(dialog.getByText("Mon 21 Sep 2026")).toBeVisible();
  expect(previous).toBeDisabled();
  fireEvent.click(dialog.getByRole("button", { name: "Next day" }));
  expect(dialog.getByText("Tue 22 Sep 2026")).toBeVisible();
  expect(previous).toBeEnabled();
});

it("saves a new target from the chosen date, reloads the list and closes", async () => {
  const { api, dialog } = await open(["vehicles.target"]);

  fireEvent.change(dialog.getByLabelText("Target, Tuesday"), {
    target: { value: "2500" },
  });
  fireEvent.click(dialog.getByRole("button", { name: "Save target" }));

  await waitFor(() => expect(writes(api)).toHaveLength(1));
  expect(writes(api)[0]).toEqual([
    "POST",
    "setup/vehicles/v-1/targets",
    {
      startsOn: "2026-09-28",
      days: [2000, 2500, 2000, 2000, 2000, 2000, 2000],
    },
  ]);
  expect(
    await screen.findByText("Target saved, from 28 Sep 2026"),
  ).toBeVisible();
  await waitFor(() =>
    expect(
      screen.queryByRole("dialog", { name: "Targets" }),
    ).not.toBeInTheDocument(),
  );
  await waitFor(() =>
    expect(reads(api, "setup/vehicles?page=1&pageSize=25")).toBe(2),
  );
});

it("fills every day from the first figure typed with Same every day", async () => {
  const { api, dialog } = await open(["vehicles.target"]);

  fireEvent.change(dialog.getByLabelText("Target, Monday"), {
    target: { value: "3000" },
  });
  fireEvent.click(dialog.getByRole("button", { name: "Same every day" }));
  expect(dialog.getByLabelText("Target, Sunday")).toHaveValue("3000");
  fireEvent.click(dialog.getByRole("button", { name: "Save target" }));
  await waitFor(() => expect(writes(api)).toHaveLength(1));
  expect(writes(api)[0][2]).toEqual({
    startsOn: "2026-09-28",
    days: flat(3000),
  });
});

it("refuses an empty day and the target already set for the date, before sending", async () => {
  const { api, dialog } = await open(["vehicles.target"]);

  fireEvent.click(dialog.getByRole("button", { name: "Save target" }));
  expect(dialog.getByRole("alert")).toHaveTextContent(
    "This is the target already set for 28 Sep 2026.",
  );
  fireEvent.change(dialog.getByLabelText("Target, Friday"), {
    target: { value: "" },
  });
  fireEvent.click(dialog.getByRole("button", { name: "Save target" }));
  expect(dialog.getByRole("alert")).toHaveTextContent(
    "Enter the target for every day.",
  );
  expect(writes(api)).toEqual([]);
});

it("refuses a start before today when the business date has moved past the chosen day", async () => {
  const api = serve();
  api.on("GET setup/vehicles/v-1/targets", [200, sets]);
  const element = (today: string) => (
    <ToastProvider>
      <TargetsDialog
        vehicle={vehicle}
        today={today}
        onClose={() => {}}
        onChanged={() => {}}
      />
    </ToastProvider>
  );
  const view = render(element(businessDate));
  await screen.findByText("Now");
  fireEvent.change(screen.getByLabelText("Target, Monday"), {
    target: { value: "2100" },
  });
  view.rerender(element("2026-09-30"));
  fireEvent.click(screen.getByRole("button", { name: "Save target" }));
  expect(screen.getByRole("alert")).toHaveTextContent(
    "A target cannot start before today.",
  );
  expect(writes(api)).toEqual([]);
});

it("shows the server's refusal and keeps the pop up open", async () => {
  const { api, dialog } = await open(["vehicles.target"]);
  api.on("POST setup/vehicles/v-1/targets", [
    409,
    {
      title: "Conflict",
      detail: "A target set that already started cannot be changed.",
    },
  ]);

  fireEvent.change(dialog.getByLabelText("Target, Monday"), {
    target: { value: "2100" },
  });
  fireEvent.click(dialog.getByRole("button", { name: "Save target" }));

  expect(await dialog.findByRole("alert")).toHaveTextContent(
    "A target set that already started cannot be changed.",
  );
  expect(screen.getByRole("dialog", { name: "Targets" })).toBeVisible();
});

it("removes a target that has not started, then reloads the history and the vehicles", async () => {
  const { api, dialog } = await open(["vehicles.target"]);
  api.on("GET setup/vehicles/v-1/targets", [200, [sets[1]]]);

  fireEvent.click(dialog.getByRole("button", { name: /Remove/ }));

  await waitFor(() => expect(writes(api)).toHaveLength(1));
  expect(writes(api)[0]).toEqual([
    "POST",
    "setup/vehicle-targets/t-2/remove",
    {},
  ]);
  await waitFor(() =>
    expect(
      dialog.queryByRole("button", { name: /Remove/ }),
    ).not.toBeInTheDocument(),
  );
  expect(dialog.getAllByRole("row").slice(1)).toHaveLength(1);
  expect(reads(api, "setup/vehicles?page=1&pageSize=25")).toBe(2);
});
