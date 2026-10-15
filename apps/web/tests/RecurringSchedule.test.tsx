import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { expect, it } from "vitest";

import { RecurringPage } from "../components/setup";
import { fakeApi } from "./fakeApi";
import { renderInApp } from "./renderInApp";

const businessDate = "2026-10-10";
const expenses = {
  permissions: [
    "scheduled.view",
    "scheduled.add",
    "scheduled.edit",
    "scheduled.pause",
  ],
};
const savers = {
  permissions: ["savings.view", "savings.add", "savings.edit", "savings.pause"],
};

const summary = {
  from: "2026-10-01",
  to: "2026-10-31",
  costsDue: 91000,
  saved: 38000,
  savingsBalance: 1340000,
  runningCosts: 3,
  pausedCosts: 1,
  runningSavings: 2,
  pausedSavings: 0,
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
  frequency: 2,
  day: 6,
  expenseItemId: null,
  expenseItemName: null,
  bucket: null,
  lastRun: "2026-10-03",
  lastRunVehicles: 1,
  lastRunStates: { saved: 1, skipped: 0, held: 1 },
  balance: 150000,
  condition: { min: 60000, days: 7 },
  opening: { date: "2026-08-31", total: 100000 },
};
const tyres = {
  ...engine,
  id: "sav-2",
  name: "Tyre fund",
  pausedFrom: "2026-10-01",
  lastRun: null,
  lastRunVehicles: 0,
  lastRunStates: null,
  balance: 250000,
  condition: null,
  opening: null,
};

const page = (rows: unknown[]) =>
  [
    200,
    { items: rows, pageNumber: 1, pageSize: 25, total: rows.length },
  ] as const;

function serve(rows: { cost: unknown[]; savings: unknown[] }) {
  const api = fakeApi();
  api.on("setup/recurring/summary", [200, summary]);
  api.on("setup/recurring/vehicle-options", [
    200,
    [
      {
        id: "v1",
        companyId: "c1",
        companyName: "North Star",
        registration: "KDA 482M",
        active: true,
      },
      {
        id: "v2",
        companyId: "c1",
        companyName: "North Star",
        registration: "KBZ 640Q",
        active: true,
      },
    ],
  ]);
  api.on("setup/access/me", [
    200,
    { allCompanies: true, companies: [], vehicles: [] },
  ]);
  api.on("setup/recurring?kind=cost*", () => page(rows.cost));
  api.on("setup/recurring?kind=savings*", () => page(rows.savings));
  return api;
}

const cells = (row: HTMLElement) =>
  [...row.querySelectorAll("td")].map((cell) => cell.textContent);

const stat = (label: string) =>
  screen.getByText(label, { selector: ".side span" }).nextSibling;

it("gives Scheduled expenses its own page with a headline bar: due this month, running and paused", async () => {
  const api = serve({ cost: [insurance], savings: [engine] });
  renderInApp(<RecurringPage kind="expense" />, expenses, { businessDate });
  expect(
    await screen.findByRole("heading", {
      name: "Scheduled expenses",
      level: 1,
    }),
  ).toBeInTheDocument();
  expect(screen.getByText("Due in October 2026")).toBeInTheDocument();
  expect(screen.getByText("Due in October 2026").nextSibling).toHaveTextContent(
    "KES 91,000",
  );
  expect(stat("Running")).toHaveTextContent("3");
  expect(stat("Paused")).toHaveTextContent("1");
  expect(screen.queryByRole("tab")).not.toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: "New scheduled expense" }),
  ).toBeInTheDocument();
  const row = await screen.findByRole("row", { name: /Insurance/ });
  expect(cells(row).slice(0, 6)).toEqual([
    "Insurance",
    "All vehicles",
    "3,000",
    "6,000",
    "Every month on the 28th",
    "28 Oct 2026",
  ]);
  expect(within(row).getByText("Running")).toBeInTheDocument();
  expect(
    api.calls.some((call) =>
      call.path.startsWith("setup/recurring?kind=savings"),
    ),
  ).toBe(false);
});

it("gives Savings its own page with the balance, this month's saving, the rule and the last run's outcomes", async () => {
  serve({ cost: [insurance], savings: [engine, tyres] });
  renderInApp(<RecurringPage kind="saving" />, savers, { businessDate });
  expect(
    await screen.findByRole("heading", { name: "Savings", level: 1 }),
  ).toBeInTheDocument();
  expect(screen.getByText("Savings balance").nextSibling).toHaveTextContent(
    "KES 1,340,000",
  );
  expect(stat("Saved in October 2026")).toHaveTextContent("38,000");
  expect(stat("Running")).toHaveTextContent("2");
  expect(stat("Paused")).toHaveTextContent("0");
  expect(
    screen.getByRole("button", { name: "New saving" }),
  ).toBeInTheDocument();
  const row = await screen.findByRole("row", { name: /Engine fund/ });
  expect(cells(row).slice(0, 6)).toEqual([
    "Engine fund",
    "All vehicles",
    "3,000",
    "Every SaturdayRevenue KES 60,000 or more over the 7 days to the run",
    "3 Oct 20261 saved, 1 waiting for revenue",
    "150,000",
  ]);
  expect(
    within(row).getByRole("button", { name: "Runs Engine fund" }),
  ).toBeInTheDocument();
  const paused = screen.getByRole("row", { name: /Tyre fund/ });
  expect(within(paused).getByText("Paused")).toBeInTheDocument();
  expect(
    within(paused).getByRole("button", { name: "Resume Tyre fund" }),
  ).toBeInTheDocument();
  expect(screen.getByText("2 savings").closest("tr")).toHaveTextContent(
    "400,000",
  );
});

it("offers no New, Edit or Pause without the rights of the page's kind", async () => {
  serve({ cost: [insurance], savings: [engine] });
  renderInApp(
    <RecurringPage kind="saving" />,
    {
      permissions: [
        "savings.view",
        "scheduled.add",
        "scheduled.edit",
        "scheduled.pause",
      ],
    },
    { businessDate },
  );
  const row = await screen.findByRole("row", { name: /Engine fund/ });
  expect(
    screen.queryByRole("button", { name: "New saving" }),
  ).not.toBeInTheDocument();
  expect(
    within(row).getByRole("button", { name: "Open Engine fund" }),
  ).toBeInTheDocument();
  expect(
    within(row).queryByRole("button", { name: /Pause/ }),
  ).not.toBeInTheDocument();
});

it("pauses an item, shows it Paused with Resume, then resumes it, reloading the bar", async () => {
  const api = serve({ cost: [insurance], savings: [] });
  api.on("POST setup/recurring/cost-1/pause", [200, { id: "cost-1" }]);
  api.on("POST setup/recurring/cost-1/resume", [200, { id: "cost-1" }]);
  renderInApp(<RecurringPage kind="expense" />, expenses, { businessDate });
  const row = await screen.findByRole("row", { name: /Insurance/ });
  api.on("setup/recurring?kind=cost*", () =>
    page([{ ...insurance, pausedFrom: "2026-10-10" }]),
  );
  fireEvent.click(within(row).getByRole("button", { name: "Pause Insurance" }));
  expect(
    await screen.findByRole("button", { name: "Resume Insurance" }),
  ).toBeInTheDocument();
  expect(api.sent("POST setup/recurring/cost-1/pause")).toHaveLength(1);
  expect(
    api.calls.filter((call) => call.path === "setup/recurring/summary"),
  ).toHaveLength(2);
  api.on("setup/recurring?kind=cost*", () => page([insurance]));
  fireEvent.click(screen.getByRole("button", { name: "Resume Insurance" }));
  expect(
    await screen.findByRole("button", { name: "Pause Insurance" }),
  ).toBeInTheDocument();
  expect(api.sent("POST setup/recurring/cost-1/resume")).toHaveLength(1);
});

it("says why a pause was refused and keeps the item as it was", async () => {
  const api = serve({ cost: [insurance], savings: [] });
  api.on("POST setup/recurring/cost-1/pause", [
    400,
    { title: "Invalid setup change", detail: "This item has already stopped." },
  ]);
  renderInApp(<RecurringPage kind="expense" />, expenses, { businessDate });
  const row = await screen.findByRole("row", { name: /Insurance/ });
  fireEvent.click(within(row).getByRole("button", { name: "Pause Insurance" }));
  expect(
    await screen.findByText("This item has already stopped."),
  ).toBeInTheDocument();
  expect(
    within(row).getByRole("button", { name: "Pause Insurance" }),
  ).toBeInTheDocument();
});

it("opens a saving's runs: each vehicle, the revenue measured and what happened, over the opening balance", async () => {
  const api = serve({ cost: [], savings: [engine] });
  api.on("setup/recurring/sav-1/runs", [
    200,
    {
      id: "sav-1",
      name: "Engine fund",
      kind: 2,
      start: "2026-01-01",
      total: 150000,
      runCount: 4,
      runs: [
        {
          date: "2026-10-03",
          amount: 3000,
          shares: [
            {
              vehicleId: "v1",
              registration: "KDA 482M",
              amount: 3000,
              state: "saved",
              revenue: 72000,
            },
            {
              vehicleId: "v2",
              registration: "KBZ 640Q",
              amount: 0,
              state: "held",
              revenue: 41000,
            },
          ],
        },
        {
          date: "2026-09-26",
          amount: 0,
          shares: [
            {
              vehicleId: "v1",
              registration: "KDA 482M",
              amount: 0,
              state: "skipped",
              revenue: 52000,
            },
          ],
        },
      ],
    },
  ]);
  renderInApp(<RecurringPage kind="saving" />, savers, { businessDate });
  fireEvent.click(
    await screen.findByRole("button", { name: "Runs Engine fund" }),
  );
  const dialog = await screen.findByRole("dialog", { name: "Engine fund" });
  expect(
    within(dialog).getByText(
      "Every Saturday. Revenue KES 60,000 or more over the 7 days to the run.",
    ),
  ).toBeInTheDocument();
  expect(
    within(dialog).getByText("Opening balance, 31 Aug 2026").nextSibling,
  ).toHaveTextContent("100,000");
  expect(within(dialog).getByText("Saved since").nextSibling).toHaveTextContent(
    "50,000",
  );
  expect(within(dialog).getByText("Balance").nextSibling).toHaveTextContent(
    "150,000",
  );
  expect(
    await within(dialog).findByText("1 saved, 1 waiting for revenue"),
  ).toBeInTheDocument();
  expect(within(dialog).getByText("41,000 so far")).toBeInTheDocument();
  expect(within(dialog).getByText("Waiting for revenue")).toHaveClass(
    "chip",
    "wait",
  );
  expect(within(dialog).getByText("Skipped, below 60,000")).toHaveClass(
    "chip",
    "mute",
  );
  expect(within(dialog).getByText("Saved", { selector: ".chip" })).toHaveClass(
    "chip",
    "ok",
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
    {
      title: "Invalid request",
      detail: "The runs of this saving cannot be read.",
    },
  ]);
  renderInApp(<RecurringPage kind="saving" />, savers, { businessDate });
  fireEvent.click(
    await screen.findByRole("button", { name: "Runs Engine fund" }),
  );
  const dialog = await screen.findByRole("dialog", { name: "Engine fund" });
  expect(await within(dialog).findByText("No runs yet.")).toBeInTheDocument();
  fireEvent.click(
    within(dialog).getAllByRole("button", { name: "Close" }).at(-1)!,
  );
  await waitFor(() =>
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
  );
  fireEvent.click(screen.getByRole("button", { name: "Runs Tyre fund" }));
  expect(
    await screen.findByText("The runs of this saving cannot be read."),
  ).toBeInTheDocument();
});
