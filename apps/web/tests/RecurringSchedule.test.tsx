import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { expect, it } from "vitest";

import { RecurringPage } from "../components/setup";
import { fakeApi } from "./fakeApi";
import { renderInApp } from "./renderInApp";

const businessDate = "2026-10-10";
const manager = { permissions: ["commitments.view", "commitments.manage"] };

const summary = {
  from: "2026-10-01",
  to: "2026-10-31",
  costsDue: 91000,
  saved: 38000,
  savingsBalance: 1340000,
};

const base = {
  kind: 1,
  amount: 6000,
  frequency: 3,
  day: 28,
  lastDay: false,
  start: "2026-01-01",
  end: null,
  stoppedFrom: null,
  pausedFrom: null,
  expenseItemId: "insurance",
  expenseItemName: "Insurance",
  bucket: 2,
  note: null,
  month: null,
  allocations: [
    { vehicleId: "v1", amount: 3000, registration: "KDA 482M", active: true },
    { vehicleId: "v2", amount: 3000, registration: "KBZ 640Q", active: true },
  ],
};

const insurance = { ...base, id: "cost-1", name: "Insurance" };
const engine = {
  ...base,
  id: "sav-1",
  name: "Engine fund",
  kind: 2,
  expenseItemId: null,
  expenseItemName: null,
  bucket: null,
  lastRun: "2026-09-28",
  lastRunVehicles: 2,
  balance: 150000,
};
const tyres = {
  ...engine,
  id: "sav-2",
  name: "Tyre fund",
  end: "2026-12-31",
  lastRun: null,
  lastRunVehicles: 0,
  balance: 250000,
};

const page = (rows: unknown[]) =>
  [
    200,
    { items: rows, pageNumber: 1, pageSize: 25, total: rows.length },
  ] as const;

function serve(rows: { cost: unknown[]; savings: unknown[] }) {
  const api = fakeApi();
  api.on("setup/recurring/summary", [200, summary]);
  api.on("setup/recurring/vehicle-options", [200, []]);
  api.on("setup/recurring?kind=cost*", () => page(rows.cost));
  api.on("setup/recurring?kind=savings*", () => page(rows.savings));
  return api;
}

const cells = (row: HTMLElement) =>
  [...row.querySelectorAll("td")].map((cell) => cell.textContent);

it("reads the month's totals into the tab names", async () => {
  serve({ cost: [insurance], savings: [engine] });
  renderInApp(<RecurringPage canManage />, manager, { businessDate });

  await screen.findByRole("tab", { name: /KES 91,000 in October 2026/ });
  const [expenses, savings] = screen.getAllByRole("tab");
  expect(expenses.querySelector("span")).toHaveTextContent(
    "Scheduled expenses",
  );
  expect(expenses.querySelector("small")).toHaveTextContent(
    "KES 91,000 in October 2026",
  );
  expect(savings.querySelector("small")).toHaveTextContent(
    "KES 38,000 saved in October 2026 · balance KES 1,340,000",
  );
});

it("shows the expense columns, a note on runs only when it ends, and a blank next run while paused", async () => {
  serve({
    cost: [
      insurance,
      {
        ...base,
        id: "cost-2",
        name: "Parking",
        end: "2026-12-31",
        pausedFrom: "2026-10-05",
      },
    ],
    savings: [],
  });
  renderInApp(<RecurringPage canManage />, manager, { businessDate });

  await screen.findByRole("button", { name: "Edit Insurance" });
  expect(
    screen.getAllByRole("columnheader").map((header) => header.textContent),
  ).toEqual([
    "Item",
    "Vehicles",
    "Amount per vehicle",
    "Each run",
    "Runs",
    "Next run",
    "Status",
    "Actions",
  ]);
  const running = screen.getByRole("row", { name: /Insurance/ });
  expect(cells(running)).toEqual([
    "Insurance",
    "KDA 482MKBZ 640Q",
    "3,000",
    "6,000",
    "Every month on the 28th",
    "28 Oct 2026",
    "Running",
    "EditPause",
  ]);
  expect(within(running).getByText("Running")).toHaveClass("chip", "ok");
  expect(
    within(running).getByRole("button", { name: "Pause Insurance" }),
  ).toHaveClass("act", "warn");

  const paused = screen.getByRole("row", { name: /Parking/ });
  expect(within(paused).getByText("Until 31 Dec 2026")).toHaveClass("note");
  expect(within(paused).getByText("Paused")).toHaveClass("chip", "wait");
  expect(cells(paused)[5]).toBe("");
  expect(
    within(paused).getByRole("button", { name: "Resume Parking" }),
  ).toHaveClass("act", "ok");
});

it("shows the savings columns with last run, balance and a totals footer", async () => {
  serve({ cost: [], savings: [tyres, engine] });
  renderInApp(<RecurringPage canManage />, manager, { businessDate });

  fireEvent.click(await screen.findByRole("tab", { name: /^Savings/ }));
  await screen.findByRole("button", { name: "Edit Engine fund" });
  expect(
    screen.getAllByRole("columnheader").map((header) => header.textContent),
  ).toEqual([
    "Saving",
    "Vehicles",
    "Per vehicle",
    "Runs",
    "Last run",
    "Balance",
    "Status",
    "Actions",
  ]);
  const row = screen.getByRole("row", { name: /Engine fund/ });
  const lastRun = row.querySelector("td[data-label='Last run']") as HTMLElement;
  expect(lastRun).toHaveTextContent("28 Sep 20262 saved");
  expect(within(lastRun).getByText("2 saved")).toHaveClass("note");
  const balance = row.querySelector("td[data-label='Balance']");
  expect(balance).toHaveTextContent("150,000");
  expect(balance).toHaveClass("r", "tot");
  const never = screen.getByRole("row", { name: /Tyre fund/ });
  expect(
    never.querySelector("td[data-label='Last run']"),
  ).toBeEmptyDOMElement();
  expect(
    within(row)
      .getAllByRole("button")
      .map((button) => button.textContent),
  ).toEqual(["Runs", "Edit", "Pause"]);

  const footer = document.querySelector("tfoot tr") as HTMLElement;
  expect(footer.children).toHaveLength(3);
  expect(footer.children[0]).toHaveTextContent("2 savings");
  expect(footer.children[0]).toHaveAttribute("colspan", "5");
  expect(footer.children[1]).toHaveTextContent("400,000");
  expect(footer.children[1]).toHaveClass("r");
  expect(footer.children[2]).toHaveAttribute("colspan", "2");
});

it("pauses an item, shows it Paused with Resume, then resumes it", async () => {
  let pausedFrom: string | null = null;
  const api = serve({ cost: [], savings: [] });
  api.on("setup/recurring?kind=cost*", () =>
    page([{ ...insurance, pausedFrom }]),
  );
  api.on("POST setup/recurring/cost-1/pause", () => {
    pausedFrom = businessDate;
    return [200, { id: "cost-1" }];
  });
  api.on("POST setup/recurring/cost-1/resume", () => {
    pausedFrom = null;
    return [200, { id: "cost-1" }];
  });
  renderInApp(<RecurringPage canManage />, manager, { businessDate });

  fireEvent.click(
    await screen.findByRole("button", { name: "Pause Insurance" }),
  );
  expect(
    await screen.findByRole("button", { name: "Resume Insurance" }),
  ).toBeInTheDocument();
  expect(api.sent("POST setup/recurring/cost-1/pause")).toHaveLength(1);
  const row = screen.getByRole("row", { name: /Insurance/ });
  expect(within(row).getByText("Paused")).toHaveClass("chip", "wait");
  expect(screen.getByRole("status")).toHaveTextContent("Insurance paused");

  fireEvent.click(screen.getByRole("button", { name: "Resume Insurance" }));
  expect(
    await screen.findByRole("button", { name: "Pause Insurance" }),
  ).toBeInTheDocument();
  expect(api.sent("POST setup/recurring/cost-1/resume")).toHaveLength(1);
  expect(screen.getByRole("status")).toHaveTextContent("Insurance running");
  expect(
    within(screen.getByRole("row", { name: /Insurance/ })).getByText("Running"),
  ).toBeInTheDocument();
});

it("reloads the tab totals after a pause", async () => {
  const api = serve({ cost: [insurance], savings: [] });
  api.on("POST setup/recurring/cost-1/pause", [200, { id: "cost-1" }]);
  renderInApp(<RecurringPage canManage />, manager, { businessDate });
  await screen.findByRole("tab", { name: /KES 91,000 in October 2026/ });

  api.on("setup/recurring/summary", [200, { ...summary, costsDue: 45500 }]);
  fireEvent.click(
    await screen.findByRole("button", { name: "Pause Insurance" }),
  );
  expect(
    await screen.findByRole("tab", { name: /KES 45,500 in October 2026/ }),
  ).toBeInTheDocument();
});

it("says why a pause was refused and keeps the item as it was", async () => {
  const api = serve({ cost: [insurance], savings: [] });
  api.on("POST setup/recurring/cost-1/pause", [
    400,
    { title: "Invalid", detail: "The item is already stopped." },
  ]);
  renderInApp(<RecurringPage canManage />, manager, { businessDate });

  fireEvent.click(
    await screen.findByRole("button", { name: "Pause Insurance" }),
  );
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "The item is already stopped.",
  );
  expect(screen.getByRole("button", { name: "Pause Insurance" })).toBeEnabled();
});

it("offers no Pause or Resume for a stopped or partial item", async () => {
  serve({
    cost: [
      { ...insurance, id: "a", name: "Stopped one", stoppedFrom: "2026-10-01" },
      { ...insurance, id: "b", name: "Partial one", partial: true },
    ],
    savings: [],
  });
  renderInApp(<RecurringPage canManage />, manager, { businessDate });

  await screen.findByRole("button", { name: "Open Partial one" });
  expect(
    screen.getByRole("button", { name: "Edit Stopped one" }),
  ).toBeVisible();
  expect(
    screen.queryByRole("button", { name: /^(Pause|Resume) / }),
  ).not.toBeInTheDocument();
});

it("opens a saving's runs by day with the vehicles saved for", async () => {
  const api = serve({ cost: [], savings: [engine] });
  api.on("setup/recurring/sav-1/runs", [
    200,
    {
      id: "sav-1",
      name: "Engine fund",
      kind: 2,
      start: "2026-01-01",
      total: 150000,
      runCount: 12,
      runs: [
        {
          date: "2026-09-28",
          amount: 6000,
          shares: [
            { vehicleId: "v1", registration: "KDA 482M", amount: 3000 },
            { vehicleId: "v2", registration: "KBZ 640Q", amount: 3000 },
          ],
        },
        {
          date: "2026-08-28",
          amount: 3000,
          shares: [{ vehicleId: "v1", registration: "KDA 482M", amount: 3000 }],
        },
      ],
    },
  ]);
  renderInApp(<RecurringPage canManage />, manager, { businessDate });

  fireEvent.click(await screen.findByRole("tab", { name: /^Savings/ }));
  fireEvent.click(
    await screen.findByRole("button", { name: "Runs Engine fund" }),
  );

  const dialog = await screen.findByRole("dialog", { name: "Engine fund" });
  await within(dialog).findByText("Every month on the 28th.");
  expect(dialog).toHaveClass("md");
  const strip = dialog.querySelector(".msum");
  expect(strip).toHaveTextContent("Runs12");
  expect(strip).toHaveTextContent("BalanceKES 150,000");
  expect(
    [...dialog.querySelectorAll("th")].map((header) => header.textContent),
  ).toEqual(["Vehicle", "Outcome", "Saved"]);
  const groups = [...dialog.querySelectorAll("tr.grp")];
  expect(groups.map((row) => row.textContent)).toEqual([
    "Monday 28 Sep 20262 saved",
    "Friday 28 Aug 20261 saved",
  ]);
  const rows = [...dialog.querySelectorAll("tbody tr:not(.grp)")];
  expect(rows).toHaveLength(3);
  expect(rows[0]).toHaveTextContent("KDA 482MSaved3,000");
  expect(rows[0].querySelector(".chip")).toHaveClass("ok");
  expect(rows[0].querySelector("td:last-child")).toHaveClass("r", "tot");

  fireEvent.click(within(dialog).getAllByRole("button", { name: "Close" })[1]);
  await waitFor(() =>
    expect(screen.queryByRole("dialog", { name: "Engine fund" })).toBeNull(),
  );
});

it("says there are no runs yet, and why the runs could not load", async () => {
  const api = serve({ cost: [], savings: [engine, tyres] });
  api.on("setup/recurring/sav-1/runs", [
    200,
    {
      id: "sav-1",
      name: "Engine fund",
      kind: 2,
      start: "2026-01-01",
      total: 0,
      runCount: 0,
      runs: [],
    },
  ]);
  api.on("setup/recurring/sav-2/runs", [
    400,
    { title: "Invalid", detail: "No such saving." },
  ]);
  renderInApp(<RecurringPage canManage />, manager, { businessDate });

  fireEvent.click(await screen.findByRole("tab", { name: /^Savings/ }));
  fireEvent.click(
    await screen.findByRole("button", { name: "Runs Engine fund" }),
  );
  expect(await screen.findByText("No runs yet.")).toBeInTheDocument();
  fireEvent.click(
    within(screen.getByRole("dialog", { name: "Engine fund" })).getAllByRole(
      "button",
      { name: "Close" },
    )[1],
  );

  fireEvent.click(
    await screen.findByRole("button", { name: "Runs Tyre fund" }),
  );
  expect(await screen.findByText("No such saving.")).toBeInTheDocument();
});
