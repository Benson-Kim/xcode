import {
  act,
  fireEvent,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { canOpen } from "@xcode/shared/capture";
import type {
  RevenueCell,
  RevenueVehicle,
  RevenueWeek,
} from "@xcode/shared/revenue";

import { RevenuePage } from "../components/RevenuePage";
import { useFormats } from "../lib/formats";
import { renderInApp } from "./renderInApp";

// Render counters: every part of the grid reads the formatter once per render, and each day cell asks once whether it
// opens capture.
vi.mock("../lib/formats", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/formats")>();
  return { ...actual, useFormats: vi.fn(actual.useFormats) };
});
vi.mock("@xcode/shared/capture", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@xcode/shared/capture")>();
  return { ...actual, canOpen: vi.fn(actual.canOpen) };
});

// Monday to Sunday; the organization's business date is the Wednesday.
const DATES = [
  "2026-09-28",
  "2026-09-29",
  "2026-09-30",
  "2026-10-01",
  "2026-10-02",
  "2026-10-03",
  "2026-10-04",
];
const TODAY = "2026-09-30";
const CLERK = ["revenue.view", "revenue.capture"];
const OFFICE = ["revenue.view", "revenue.capture", "revenue.correct"];

function cell(date: string, over: Partial<RevenueCell> = {}): RevenueCell {
  const status = date > TODAY ? "future" : "missing";
  return {
    date,
    status,
    expected: 1000,
    amount: null,
    reason: null,
    note: null,
    canEdit: status === "missing",
    editedAfterCapture: false,
    version: null,
    ...over,
  };
}

const recorded = (
  amount: number,
  version = 1,
  over: Partial<RevenueCell> = {},
): Partial<RevenueCell> => ({
  status: "amount",
  amount,
  version,
  canEdit: false,
  ...over,
});

function vehicle(
  id: string,
  registration: string,
  days: Record<string, Partial<RevenueCell>> = {},
  over: Partial<RevenueVehicle> = {},
): RevenueVehicle {
  return {
    id,
    companyId: "company-1",
    companyName: "North Star",
    registration,
    joinedOn: "2026-01-01",
    leftOn: null,
    earliestMissing: null,
    days: DATES.map((date) => cell(date, days[date])),
    totalAmount: 0,
    totalExpected: 0,
    percent: null,
    ...over,
  };
}

// The API works out the day totals and the first gap over the whole grid: a day's recorded amounts, and the earliest
// day a vehicle can be captured (its earliest gap, or today while today has no record), the first vehicle on a tie.
function wholeGrid(
  vehicles: RevenueVehicle[],
): Pick<RevenueWeek, "dayTotals" | "firstGap" | "totalVehicles"> {
  let firstGap: RevenueWeek["firstGap"] = null;
  for (const item of vehicles) {
    const date =
      item.earliestMissing ??
      (item.days.find((day) => day.date === TODAY)?.status === "missing"
        ? TODAY
        : null);
    if (date && (!firstGap || date < firstGap.date))
      firstGap = { vehicleId: item.id, date };
  }
  const dayTotals = DATES.map((date) => ({
    date,
    amount: vehicles.reduce(
      (sum, item) =>
        sum +
        (item.days.find((day) => day.date === date && day.status === "amount")
          ?.amount ?? 0),
      0,
    ),
    expected: 0,
  }));
  return { dayTotals, firstGap, totalVehicles: vehicles.length };
}

function week(
  vehicles: RevenueVehicle[],
  over: Partial<RevenueWeek> = {},
): RevenueWeek {
  return {
    weekStart: DATES[0],
    weekThrough: DATES[6],
    currentWeekStart: DATES[0],
    businessDate: TODAY,
    companies: [
      { id: "company-1", name: "North Star" },
      { id: "company-2", name: "Metro Link" },
    ],
    vehicles,
    totalAmount: 0,
    totalExpected: 0,
    percent: null,
    pageNumber: 1,
    pageSize: 500,
    truncated: false,
    lowDayThreshold: 4000,
    gapAmberPercent: 10,
    ...wholeGrid(vehicles),
    ...over,
  };
}

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });

type Handler = (
  path: string,
  init?: RequestInit,
) => Response | Promise<Response> | undefined;

// A fake API: every call is recorded, and anything the handler does not answer is a 404.
function serve(handler: Handler) {
  const fetcher = vi.fn(
    async (input: RequestInfo | URL, init?: RequestInit) =>
      (await handler(String(input), init)) ?? json({}, 404),
  );
  vi.stubGlobal("fetch", fetcher);
  return fetcher;
}

const puts = (fetcher: ReturnType<typeof serve>) =>
  fetcher.mock.calls
    .filter(([, init]) => init?.method === "PUT")
    .map(([input, init]) => ({
      path: String(input),
      body: JSON.parse(String(init?.body)),
    }));
const gets = (fetcher: ReturnType<typeof serve>, fragment: string) =>
  fetcher.mock.calls
    .filter(
      ([input, init]) => !init?.method && String(input).includes(fragment),
    )
    .map(([input]) => String(input));

// The grid answers the plain week request; a vehicle's own week (vehicleId) is answered by `vehicleWeek`. The
// person's own scope says how far back they may change records.
function serveWeek(
  grid: () => RevenueWeek,
  options: {
    save?: Handler;
    vehicleWeek?: (path: string) => RevenueWeek | undefined;
    earliest?: string | null;
  } = {},
) {
  return serve((path, init) => {
    if (init?.method === "PUT")
      return options.save?.(path, init) ?? json({ id: "record-1", version: 1 });
    if (path.startsWith("/api/setup/access/me"))
      return json({
        allCompanies: true,
        companies: [],
        vehicles: [],
        canChange: "Any date",
        earliest: options.earliest ?? null,
      });
    if (path.includes("vehicleId=")) {
      const found = options.vehicleWeek?.(path);
      return found ? json(found) : undefined;
    }
    if (path.startsWith("/api/setup/revenue")) return json(grid());
  });
}

const amountField = (dialog: HTMLElement) =>
  within(dialog).getByLabelText("Revenue, KES");

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

it("renders the week grid from one request, with the gap to target, the headline bar, today and a company filter", async () => {
  const fetcher = serveWeek(() =>
    week(
      [
        vehicle(
          "vehicle-1",
          "KDA 482M",
          {
            [DATES[0]]: recorded(8500),
            [DATES[1]]: {
              status: "reason",
              reason: "Garage",
              version: 1,
              canEdit: false,
            },
          },
          {
            totalAmount: 8500,
            totalExpected: 20000,
            percent: 43,
            gap: -11500,
            gapBand: "neg",
            belowThresholdDays: 1,
          },
        ),
        vehicle(
          "vehicle-2",
          "KBZ 110A",
          {
            [DATES[0]]: recorded(12000),
            [DATES[1]]: recorded(2600, 1, { reason: "No Crew" }),
          },
          {
            companyId: "company-2",
            companyName: "Metro Link",
            fleetNumber: "14",
            totalAmount: 14600,
            totalExpected: 20000,
            percent: 73,
            gap: 600,
            gapBand: "pos",
            belowThresholdDays: 1,
          },
        ),
      ],
      {
        totalAmount: 23100,
        totalExpected: 40000,
        percent: 58,
        gap: -10900,
        gapBand: "amb",
        belowThresholdDays: 2,
        missingDays: 2,
      },
    ),
  );
  renderInApp(<RevenuePage />, { permissions: CLERK });

  const grid = await screen.findByRole("table", {
    name: /Revenue by vehicle and day/,
  });
  expect(
    within(grid).getByRole("columnheader", { name: "Vehicle" }),
  ).toBeInTheDocument();
  expect(
    within(grid).getByRole("columnheader", { name: "Mon 28" }),
  ).toBeInTheDocument();
  expect(
    within(grid).getByRole("columnheader", { name: "Sun 4" }),
  ).toBeInTheDocument();
  expect(
    within(grid).getByRole("columnheader", { name: "Week total" }),
  ).toBeInTheDocument();
  expect(
    within(grid).getByRole("columnheader", { name: "Gap to target" }),
  ).toBeInTheDocument();
  expect(
    within(grid).queryByRole("columnheader", { name: "vs expected" }),
  ).not.toBeInTheDocument();
  expect(
    within(grid).getByRole("columnheader", { name: /Wed 30/ }),
  ).toHaveAttribute("aria-current", "date");

  const row = within(grid).getByRole("row", { name: /KDA 482M/ });
  expect(within(row).getByRole("rowheader")).toHaveTextContent("KDA 482M");
  // Monday's amount sits in its own day cell, apart from the week total.
  expect(within(row).getAllByRole("cell")[0]).toHaveTextContent(/^8,500$/);
  expect(within(row).getByText("Garage")).toBeInTheDocument();
  // The gap is a signed figure with no words, coloured by its band.
  expect(within(row).getByText("−11,500")).toHaveClass("gap", "neg");
  // Missing days say so in words, not only by colour; today's is due.
  expect(
    within(row).getByRole("button", {
      name: "KDA 482M, Wed 30 Sep 2026: Missing",
    }),
  ).toHaveTextContent(/^Due$/);

  // A low day shows the amount with its reason in small type under it.
  const low = within(grid).getByRole("row", { name: /KBZ 110A/ });
  const tuesday = within(low).getAllByRole("cell")[1];
  expect(tuesday).toHaveTextContent("2,600");
  expect(within(tuesday).getByText("No Crew")).toHaveClass("rwhy");
  expect(within(low).getByText("+600")).toHaveClass("gap", "pos");

  const totals = within(grid).getByRole("row", { name: /^2 vehicles/ });
  expect(within(totals).getByText("20,500")).toBeInTheDocument();
  expect(within(totals).getByText("23,100")).toBeInTheDocument();
  expect(within(totals).getByText("−10,900")).toHaveClass("gap", "amb");

  expect(screen.getByText("28 Sep to 4 Oct 2026")).toBeInTheDocument();
  const stat = (label: string, selector = "*") =>
    screen.getByText(label, { selector }).nextSibling;
  expect(stat("Revenue", ".lab")).toHaveTextContent(/^KES 23,100$/);
  expect(stat("Gap to target so far")).toHaveTextContent(/^−10,900$/);
  expect(stat("Below 4,000")).toHaveTextContent(/^2$/);
  expect(stat("Missing days")).toHaveTextContent(/^2$/);
  expect(screen.queryByText("Expected")).not.toBeInTheDocument();
  expect(screen.queryByText("Reached")).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Next week" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Previous week" })).toBeEnabled();
  expect(gets(fetcher, "/api/setup/revenue")).toEqual(["/api/setup/revenue"]);

  fireEvent.change(screen.getByRole("combobox", { name: "Company" }), {
    target: { value: "company-2" },
  });
  await waitFor(() =>
    expect(gets(fetcher, "companyId=company-2")).toHaveLength(1),
  );
  fireEvent.click(await screen.findByRole("button", { name: "Previous week" }));
  await waitFor(() =>
    expect(gets(fetcher, "weekStart=2026-09-21")).toHaveLength(1),
  );
});

it("says Gap to target for a finished week, and counts the days itself when the API does not", async () => {
  serveWeek(() =>
    week(
      [
        vehicle("vehicle-1", "KDA 482M", {
          [DATES[0]]: recorded(2000, 1, { reason: "Arrest" }),
          [DATES[1]]: { status: "reason", reason: "Garage", canEdit: false },
        }),
      ],
      {
        weekStart: "2026-09-21",
        weekThrough: "2026-09-27",
        currentWeekStart: DATES[0],
        gap: 0,
        gapBand: "pos",
        lowDayThreshold: 5000,
      },
    ),
  );
  renderInApp(<RevenuePage />, { permissions: CLERK });
  await screen.findByRole("table", { name: /Revenue by vehicle and day/ });
  const stat = (label: string) =>
    screen.getByText(label, { selector: ".side span" }).nextSibling;
  expect(stat("Gap to target")).toHaveTextContent(/^0$/);
  // The threshold is the fleet's setting, not a constant.
  expect(stat("Below 5,000")).toHaveTextContent(/^2$/);
  expect(stat("Missing days")).toHaveTextContent(/^1$/);
});

it("searches the week by registration or fleet number on the server once typing pauses", async () => {
  const fetcher = serveWeek(() =>
    week([vehicle("vehicle-2", "KBZ 110A", {}, { fleetNumber: "14" })]),
  );
  renderInApp(<RevenuePage />, { permissions: CLERK });
  await screen.findByRole("table", { name: /Revenue by vehicle and day/ });
  fireEvent.change(screen.getByRole("searchbox", { name: "Search vehicle" }), {
    target: { value: "14" },
  });
  await waitFor(() => expect(gets(fetcher, "q=14")).toHaveLength(1));
  expect(gets(fetcher, "q=14")).toEqual(["/api/setup/revenue?q=14"]);
});

it("makes no button of a cell the person cannot change, as the server says", async () => {
  serveWeek(() =>
    week([
      vehicle("vehicle-1", "KDA 482M", {
        [DATES[0]]: { canEdit: false },
        [DATES[1]]: recorded(8500, 2, { canEdit: true }),
      }),
    ]),
  );
  renderInApp(<RevenuePage />, { permissions: CLERK });
  const grid = await screen.findByRole("table", {
    name: /Revenue by vehicle and day/,
  });
  const row = within(grid).getByRole("row", { name: /KDA 482M/ });
  expect(
    within(row).queryByRole("button", { name: /Mon 28 Sep 2026/ }),
  ).not.toBeInTheDocument();
  expect(within(row).getAllByRole("cell")[0]).toHaveTextContent("Missing");
  expect(
    within(row).getByRole("button", {
      name: "KDA 482M, Tue 29 Sep 2026: KES 8,500",
    }),
  ).toBeInTheDocument();
});

// This week lists North Star only; last week also lists Old Fleet, archived since, which had a vehicle running then.
function serveCompanies() {
  return serve((path) => {
    if (path.startsWith("/api/setup/access/me"))
      return json({ allCompanies: true, companies: [], vehicles: [] });
    if (!path.startsWith("/api/setup/revenue")) return undefined;
    const query = new URL(path, "http://xcode.test").searchParams;
    const start = query.get("weekStart") ?? DATES[0];
    const company = query.get("companyId");
    const past = start < DATES[0];
    const companies = past
      ? [
          { id: "company-3", name: "Old Fleet" },
          { id: "company-1", name: "North Star" },
        ]
      : [{ id: "company-1", name: "North Star" }];
    const vehicles = [
      vehicle("vehicle-1", "KDA 482M"),
      ...(past
        ? [
            vehicle(
              "vehicle-3",
              "KAA 100A",
              {},
              { companyId: "company-3", companyName: "Old Fleet" },
            ),
          ]
        : []),
    ];
    const through = past ? "2026-09-27" : DATES[6];
    return json(
      week(
        vehicles.filter((item) => !company || item.companyId === company),
        { weekStart: start, weekThrough: through, companies },
      ),
    );
  });
}

it("drops a company filter the next week does not list, instead of leaving an empty grid with no way back", async () => {
  const fetcher = serveCompanies();
  renderInApp(<RevenuePage />, { permissions: CLERK });

  await screen.findByRole("row", { name: /KDA 482M/ });
  // One company this week: nothing to choose.
  expect(
    screen.queryByRole("combobox", { name: "Company" }),
  ).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Previous week" }));
  fireEvent.change(await screen.findByRole("combobox", { name: "Company" }), {
    target: { value: "company-3" },
  });
  await screen.findByRole("row", { name: /KAA 100A/ });
  expect(
    screen.queryByRole("row", { name: /KDA 482M/ }),
  ).not.toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Next week" }));
  await waitFor(() =>
    expect(
      gets(fetcher, "weekStart=2026-09-28&companyId=company-3"),
    ).toHaveLength(1),
  );
  // Old Fleet is not an option this week, so the grid goes back to every company.
  expect(
    await screen.findByRole("row", { name: /KDA 482M/ }),
  ).toBeInTheDocument();
  expect(
    gets(fetcher, "weekStart=2026-09-28&companyId=company-3"),
  ).toHaveLength(1);
  expect(
    gets(fetcher, "/api/setup/revenue?weekStart=2026-09-28").filter(
      (path) => !path.includes("companyId"),
    ),
  ).toHaveLength(1);
  expect(screen.queryByText("No vehicles.")).not.toBeInTheDocument();
  expect(
    screen.queryByRole("combobox", { name: "Company" }),
  ).not.toBeInTheDocument();
});

it("keeps the company control, with All companies, for as long as a filter is set", async () => {
  const fetcher = serveCompanies();
  renderInApp(<RevenuePage />, { permissions: CLERK });

  await screen.findByRole("row", { name: /KDA 482M/ });
  fireEvent.click(screen.getByRole("button", { name: "Previous week" }));
  fireEvent.change(await screen.findByRole("combobox", { name: "Company" }), {
    target: { value: "company-1" },
  });
  await waitFor(() =>
    expect(
      screen.queryByRole("row", { name: /KAA 100A/ }),
    ).not.toBeInTheDocument(),
  );

  // North Star is this week's only company, and the filter on it stays visible and can be cleared.
  fireEvent.click(screen.getByRole("button", { name: "Next week" }));
  await screen.findByRole("table", {
    name: "Revenue by vehicle and day, 28 Sep to 4 Oct 2026",
  });
  const company = screen.getByRole("combobox", { name: "Company" });
  expect(company).toHaveValue("company-1");
  expect(
    within(company).getByRole("option", { name: "All companies" }),
  ).toBeInTheDocument();
  fireEvent.change(company, { target: { value: "" } });
  await waitFor(() =>
    expect(
      gets(fetcher, "/api/setup/revenue?weekStart=2026-09-28").filter(
        (path) => !path.includes("companyId"),
      ),
    ).toHaveLength(1),
  );
  await waitFor(() =>
    expect(
      screen.queryByRole("combobox", { name: "Company" }),
    ).not.toBeInTheDocument(),
  );
});

it("opens the day that was tapped, with the date first and the day's own target, and steps a day at a time", async () => {
  const fetcher = serveWeek(() =>
    week([
      vehicle(
        "vehicle-1",
        "KDA 482M",
        { [DATES[1]]: { expected: 1250 } },
        { fleetNumber: "7" },
      ),
    ]),
  );
  renderInApp(<RevenuePage />, { permissions: CLERK });

  fireEvent.click(
    await screen.findByRole("button", {
      name: "KDA 482M, Wed 30 Sep 2026: Missing",
    }),
  );
  const dialog = await screen.findByRole("dialog", { name: "KDA 482M · 7" });
  expect(within(dialog).getByText("Wed 30 Sep 2026")).toBeInTheDocument();
  expect(within(dialog).getByText("Day target")).toBeInTheDocument();
  expect(within(dialog).getByText("KES 1,000")).toBeInTheDocument();
  expect(
    within(dialog).getByRole("button", { name: "Next day" }),
  ).toBeDisabled();
  expect(within(dialog).queryByText(/No record yet/)).not.toBeInTheDocument();
  expect(within(dialog).queryByText(/Expected/)).not.toBeInTheDocument();

  fireEvent.click(within(dialog).getByRole("button", { name: "Previous day" }));
  expect(
    await within(dialog).findByText("Tue 29 Sep 2026"),
  ).toBeInTheDocument();
  expect(within(dialog).getByText("KES 1,250")).toBeInTheDocument();
  expect(gets(fetcher, "vehicleId=vehicle-1")).toEqual([]);

  fireEvent.change(amountField(dialog), { target: { value: "11000" } });
  fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));
  await waitFor(() =>
    expect(puts(fetcher)[0]?.path).toBe(
      "/api/setup/revenue/vehicle-1/2026-09-29",
    ),
  );
  expect(puts(fetcher)).toHaveLength(1);
});

it("steps into last week through the vehicle's own week, and stops at the earliest day the person may change", async () => {
  const fetcher = serveWeek(() => week([vehicle("vehicle-1", "KDA 482M")]), {
    vehicleWeek: () =>
      week(
        [
          vehicle(
            "vehicle-1",
            "KDA 482M",
            {},
            { days: [cell("2026-09-27", { expected: 1200 })] },
          ),
        ],
        { weekStart: "2026-09-21" },
      ),
    earliest: "2026-09-27",
  });
  renderInApp(<RevenuePage />, { permissions: CLERK });

  fireEvent.click(
    await screen.findByRole("button", {
      name: "KDA 482M, Mon 28 Sep 2026: Missing",
    }),
  );
  const dialog = await screen.findByRole("dialog", { name: "KDA 482M" });
  fireEvent.click(within(dialog).getByRole("button", { name: "Previous day" }));
  expect(
    await within(dialog).findByText("Sun 27 Sep 2026"),
  ).toBeInTheDocument();
  expect(within(dialog).getByText("KES 1,200")).toBeInTheDocument();
  expect(gets(fetcher, "vehicleId=vehicle-1")).toEqual([
    "/api/setup/revenue?weekStart=2026-09-27&vehicleId=vehicle-1",
  ]);
  // 27 September is the earliest day allowed: no day before it.
  expect(
    within(dialog).getByRole("button", { name: "Previous day" }),
  ).toBeDisabled();
});

it("moves to the next vehicle still missing that day after a new capture, then closes", async () => {
  const fetcher = serveWeek(() =>
    week([
      vehicle("vehicle-1", "KDA 482M", {
        [DATES[0]]: recorded(9000),
        [DATES[1]]: recorded(9000),
      }),
      vehicle("vehicle-2", "KBZ 110A", {
        [DATES[0]]: recorded(9000),
        [DATES[1]]: recorded(9000),
        [DATES[2]]: recorded(7000),
      }),
      vehicle("vehicle-3", "KCE 301B", {
        [DATES[0]]: recorded(9000),
        [DATES[1]]: recorded(9000),
      }),
    ]),
  );
  renderInApp(<RevenuePage />, { permissions: CLERK });

  fireEvent.click(
    await screen.findByRole("button", {
      name: "KDA 482M, Wed 30 Sep 2026: Missing",
    }),
  );
  let dialog = await screen.findByRole("dialog", { name: "KDA 482M" });
  fireEvent.change(amountField(dialog), { target: { value: "10000" } });
  fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));

  // KBZ 110A already has Wednesday, so the next one missing it is KCE 301B.
  dialog = await screen.findByRole("dialog", { name: "KCE 301B" });
  expect(within(dialog).getByText("Wed 30 Sep 2026")).toBeInTheDocument();
  expect(amountField(dialog)).toHaveValue("");
  fireEvent.change(amountField(dialog), { target: { value: "8000" } });
  fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));

  await waitFor(() =>
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
  );
  expect(puts(fetcher).map((call) => call.path)).toEqual([
    "/api/setup/revenue/vehicle-1/2026-09-30",
    "/api/setup/revenue/vehicle-3/2026-09-30",
  ]);
});

it("closes after a correction instead of moving on", async () => {
  const fetcher = serveWeek(() =>
    week([
      vehicle("vehicle-1", "KDA 482M", {
        [DATES[0]]: recorded(8500, 3, { canEdit: true }),
      }),
      vehicle("vehicle-2", "KBZ 110A"),
    ]),
  );
  renderInApp(<RevenuePage />, { permissions: OFFICE });

  fireEvent.click(
    await screen.findByRole("button", {
      name: "KDA 482M, Mon 28 Sep 2026: KES 8,500",
    }),
  );
  const dialog = await screen.findByRole("dialog", { name: "KDA 482M" });
  fireEvent.change(amountField(dialog), { target: { value: "9000" } });
  fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));
  await waitFor(() =>
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
  );
  expect(puts(fetcher)).toHaveLength(1);
});

it("sends the version the day was opened at, even when the grid reloads underneath the dialog", async () => {
  let reads = 0;
  const fetcher = serveWeek(() =>
    week([
      vehicle("vehicle-1", "KDA 482M", {
        [DATES[0]]: recorded(9000),
        [DATES[1]]: recorded(9000),
      }),
      // Someone else captures KBZ 110A's Wednesday while this person is still on KDA 482M.
      vehicle("vehicle-2", "KBZ 110A", {
        [DATES[0]]: recorded(9000),
        [DATES[1]]: recorded(9000),
        ...(++reads > 1
          ? { [DATES[2]]: recorded(6500, 7, { canEdit: true }) }
          : {}),
      }),
    ]),
  );
  renderInApp(<RevenuePage />, { permissions: CLERK });

  fireEvent.click(
    await screen.findByRole("button", {
      name: "KDA 482M, Wed 30 Sep 2026: Missing",
    }),
  );
  let dialog = await screen.findByRole("dialog", { name: "KDA 482M" });
  fireEvent.change(amountField(dialog), { target: { value: "10000" } });
  fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));

  dialog = await screen.findByRole("dialog", { name: "KBZ 110A" });
  await waitFor(() =>
    expect(gets(fetcher, "/api/setup/revenue")).toHaveLength(2),
  );
  fireEvent.change(amountField(dialog), { target: { value: "8000" } });
  fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));

  // It opened as a missing day, so it must not overwrite the record saved meanwhile: the server answers 409 instead.
  await waitFor(() => expect(puts(fetcher)).toHaveLength(2));
  expect(puts(fetcher)[1].body).toEqual({
    amount: 8000,
    reason: null,
    note: null,
    version: null,
  });
});

it("sends the record's version when correcting a past day", async () => {
  const fetcher = serveWeek(() =>
    week([
      vehicle("vehicle-1", "KDA 482M", {
        [DATES[0]]: recorded(8500, 3, { canEdit: true }),
      }),
    ]),
  );
  renderInApp(<RevenuePage />, { permissions: OFFICE });

  fireEvent.click(
    await screen.findByRole("button", {
      name: "KDA 482M, Mon 28 Sep 2026: KES 8,500",
    }),
  );
  const dialog = await screen.findByRole("dialog", { name: "KDA 482M" });
  expect(amountField(dialog)).toHaveValue("8,500");
  fireEvent.change(amountField(dialog), { target: { value: "9000" } });
  fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));

  await waitFor(() => expect(puts(fetcher)).toHaveLength(1));
  expect(puts(fetcher)[0]).toEqual({
    path: "/api/setup/revenue/vehicle-1/2026-09-28",
    body: { amount: 9000, reason: null, note: null, version: 3 },
  });
});

const conflict = (current?: Partial<RevenueCell>) =>
  json(
    {
      title: "This day already has a different record.",
      detail:
        "This day was changed after you opened it. Check the current record and save again.",
      status: 409,
      ...(current ? { current: cell(DATES[0], current) } : {}),
    },
    409,
  );

it("on a conflict shows the saved value against yours and replaces it with the saved version", async () => {
  let attempt = 0;
  const fetcher = serveWeek(
    () =>
      week([
        vehicle("vehicle-1", "KDA 482M", {
          [DATES[0]]: recorded(8500, 3, { canEdit: true }),
        }),
      ]),
    {
      save: () =>
        ++attempt === 1
          ? conflict(recorded(9500, 4, { canEdit: true }))
          : json({ id: "record-1", version: 5 }),
    },
  );
  renderInApp(<RevenuePage />, { permissions: OFFICE });

  fireEvent.click(
    await screen.findByRole("button", {
      name: "KDA 482M, Mon 28 Sep 2026: KES 8,500",
    }),
  );
  const dialog = await screen.findByRole("dialog", { name: "KDA 482M" });
  fireEvent.change(amountField(dialog), { target: { value: "9000" } });
  fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));

  expect(
    await within(dialog).findByText(
      "This day was changed after you opened it. Check the current record and save again.",
    ),
  ).toBeInTheDocument();
  expect(
    within(dialog).getByText("Saved value").nextElementSibling,
  ).toHaveTextContent("KES 9,500");
  expect(
    within(dialog).getByText("Yours").nextElementSibling,
  ).toHaveTextContent("KES 9,000");
  fireEvent.click(
    within(dialog).getByRole("button", { name: "Replace with mine" }),
  );

  await waitFor(() =>
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
  );
  expect(puts(fetcher).map((call) => call.body)).toEqual([
    { amount: 9000, reason: null, note: null, version: 3 },
    { amount: 9000, reason: null, note: null, version: 4 },
  ]);
});

it("on a conflict can keep the saved record, and offers no replace to someone who may not change it", async () => {
  const fetcher = serveWeek(() => week([vehicle("vehicle-1", "KDA 482M")]), {
    save: () => conflict(recorded(9500, 1, { canEdit: false })),
  });
  renderInApp(<RevenuePage />, { permissions: CLERK });

  fireEvent.click(
    await screen.findByRole("button", {
      name: "KDA 482M, Mon 28 Sep 2026: Missing",
    }),
  );
  const dialog = await screen.findByRole("dialog", { name: "KDA 482M" });
  fireEvent.change(amountField(dialog), { target: { value: "9000" } });
  fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));

  expect(await within(dialog).findByText("Saved value")).toBeInTheDocument();
  expect(
    within(dialog).queryByRole("button", { name: "Replace with mine" }),
  ).not.toBeInTheDocument();
  const reads = gets(fetcher, "/api/setup/revenue").length;
  fireEvent.click(within(dialog).getByRole("button", { name: "Keep saved" }));

  await waitFor(() =>
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
  );
  expect(puts(fetcher)).toHaveLength(1);
  await waitFor(() =>
    expect(gets(fetcher, "/api/setup/revenue").length).toBeGreaterThan(reads),
  );
});

it("on a conflict without the saved record (an insert race) refetches the day, then offers the same choice", async () => {
  let attempt = 0;
  const fetcher = serveWeek(() => week([vehicle("vehicle-1", "KDA 482M")]), {
    save: () =>
      ++attempt === 1 ? conflict() : json({ id: "record-1", version: 2 }),
    vehicleWeek: () =>
      week([
        vehicle("vehicle-1", "KDA 482M", {
          [DATES[0]]: recorded(7000, 1, { canEdit: true }),
        }),
      ]),
  });
  renderInApp(<RevenuePage />, { permissions: CLERK });

  fireEvent.click(
    await screen.findByRole("button", {
      name: "KDA 482M, Mon 28 Sep 2026: Missing",
    }),
  );
  const dialog = await screen.findByRole("dialog", { name: "KDA 482M" });
  fireEvent.change(amountField(dialog), { target: { value: "9000" } });
  fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));

  expect(await within(dialog).findByText("Saved value")).toBeInTheDocument();
  expect(
    within(dialog).getByText("Saved value").nextElementSibling,
  ).toHaveTextContent("KES 7,000");
  expect(gets(fetcher, "vehicleId=vehicle-1")).toEqual([
    "/api/setup/revenue?weekStart=2026-09-28&vehicleId=vehicle-1",
  ]);
  fireEvent.click(
    within(dialog).getByRole("button", { name: "Replace with mine" }),
  );

  await waitFor(() => expect(puts(fetcher)).toHaveLength(2));
  expect(puts(fetcher)[1].body).toEqual({
    amount: 9000,
    reason: null,
    note: null,
    version: 1,
  });
});

it("needs a reason below the threshold, shows the reasons only while the amount is below it, and sends both", async () => {
  const fetcher = serveWeek(() => week([vehicle("vehicle-1", "KDA 482M")]));
  renderInApp(<RevenuePage />, { permissions: CLERK });

  fireEvent.click(
    await screen.findByRole("button", {
      name: "KDA 482M, Mon 28 Sep 2026: Missing",
    }),
  );
  const dialog = await screen.findByRole("dialog", { name: "KDA 482M" });
  const reasons = within(dialog).getByRole("group", { name: "Reason" });
  expect(
    within(reasons)
      .getAllByRole("button")
      .map((button) => button.textContent),
  ).toEqual(["Garage", "Arrest", "No Crew", "Other"]);
  expect(
    within(dialog).queryByLabelText("What happened"),
  ).not.toBeInTheDocument();

  fireEvent.change(amountField(dialog), { target: { value: "2500" } });
  fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));
  expect(await within(dialog).findByRole("alert")).toHaveTextContent(
    "Choose the reason. Revenue is below KES 4,000.",
  );
  expect(puts(fetcher)).toHaveLength(0);

  // At the threshold the reasons go, and a reason picked before is not sent.
  fireEvent.click(within(reasons).getByRole("button", { name: "Garage" }));
  fireEvent.change(amountField(dialog), { target: { value: "4000" } });
  expect(
    within(dialog).queryByRole("group", { name: "Reason" }),
  ).not.toBeInTheDocument();
  fireEvent.change(amountField(dialog), { target: { value: "2500" } });
  expect(
    within(within(dialog).getByRole("group", { name: "Reason" })).getByRole(
      "button",
      { name: "Garage" },
    ),
  ).toHaveAttribute("aria-pressed", "true");
  fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));
  await waitFor(() => expect(puts(fetcher)).toHaveLength(1));
  expect(puts(fetcher)[0].body).toEqual({
    amount: 2500,
    reason: "Garage",
    note: null,
    version: null,
  });
});

it("takes a reason alone as a no revenue day, and Other needs no note", async () => {
  const fetcher = serveWeek(() => week([vehicle("vehicle-1", "KDA 482M")]));
  renderInApp(<RevenuePage />, { permissions: CLERK });

  fireEvent.click(
    await screen.findByRole("button", {
      name: "KDA 482M, Mon 28 Sep 2026: Missing",
    }),
  );
  const dialog = await screen.findByRole("dialog", { name: "KDA 482M" });
  fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));
  expect(await within(dialog).findByRole("alert")).toHaveTextContent(
    "Enter the revenue, or choose the reason for no revenue.",
  );
  fireEvent.click(within(dialog).getByRole("button", { name: "Other" }));
  fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));
  await waitFor(() => expect(puts(fetcher)).toHaveLength(1));
  expect(puts(fetcher)[0].body).toEqual({
    amount: null,
    reason: "Other",
    note: null,
    version: null,
  });
});

it("takes today from the business date, never the computer clock", async () => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date("2027-03-10T09:00:00Z"));
  serveWeek(() =>
    week([
      vehicle("vehicle-1", "KDA 482M", {
        [DATES[0]]: recorded(9000),
        [DATES[1]]: recorded(9000),
      }),
    ]),
  );
  renderInApp(<RevenuePage />, { permissions: CLERK });

  const grid = await screen.findByRole("table", {
    name: /Revenue by vehicle and day/,
  });
  const current = within(grid)
    .getAllByRole("columnheader")
    .filter((header) => header.getAttribute("aria-current") === "date");
  expect(current.map((header) => header.textContent)).toEqual([
    "Wed 30, today",
  ]);
  fireEvent.click(screen.getByRole("button", { name: "Capture revenue" }));
  const dialog = await screen.findByRole("dialog", { name: "KDA 482M" });
  expect(within(dialog).getByText("Wed 30 Sep 2026")).toBeInTheDocument();
  expect(
    within(dialog).getByRole("button", { name: "Next day" }),
  ).toBeDisabled();
});

it("saves once however often Save or Enter is pressed while a save is on its way", async () => {
  let finish: (response: Response) => void = () => {};
  const fetcher = serveWeek(() => week([vehicle("vehicle-1", "KDA 482M")]), {
    save: () =>
      new Promise<Response>(
        (resolve) => (finish = resolve),
      ) as unknown as Response,
  });
  renderInApp(<RevenuePage />, { permissions: CLERK });

  fireEvent.click(
    await screen.findByRole("button", {
      name: "KDA 482M, Mon 28 Sep 2026: Missing",
    }),
  );
  const dialog = await screen.findByRole("dialog", { name: "KDA 482M" });
  const amount = amountField(dialog);
  fireEvent.change(amount, { target: { value: "9000" } });
  const form = amount.closest("form")!;
  fireEvent.submit(form);
  fireEvent.submit(form);
  fireEvent.click(within(dialog).getByRole("button", { name: /Sav/ }));
  expect(
    within(dialog).getByRole("button", { name: "Saving…" }),
  ).toBeDisabled();
  expect(puts(fetcher)).toHaveLength(1);

  await act(async () => finish(json({ id: "record-1", version: 1 })));
  await waitFor(() =>
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
  );
  expect(puts(fetcher)).toHaveLength(1);
});

it("returns focus to the day that opened the dialog when it closes", async () => {
  serveWeek(() => week([vehicle("vehicle-1", "KDA 482M")]));
  renderInApp(<RevenuePage />, { permissions: CLERK });

  const day = await screen.findByRole("button", {
    name: "KDA 482M, Mon 28 Sep 2026: Missing",
  });
  day.focus();
  fireEvent.click(day);
  const dialog = await screen.findByRole("dialog", { name: "KDA 482M" });
  await waitFor(() => expect(amountField(dialog)).toHaveFocus());
  fireEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));

  await waitFor(() =>
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
  );
  expect(day).toHaveFocus();
});

// D3: cents are kept, so the web takes exactly what the API and the phone take.
it("refuses an amount with more than two decimals, or of zero, and keeps the cents it accepts", async () => {
  const fetcher = serveWeek(() =>
    week([vehicle("vehicle-1", "KDA 482M", {}, { earliestMissing: DATES[0] })]),
  );
  renderInApp(<RevenuePage />, { permissions: CLERK });

  fireEvent.click(
    await screen.findByRole("button", {
      name: "KDA 482M, Mon 28 Sep 2026: Missing",
    }),
  );
  await screen.findByRole("dialog", { name: "KDA 482M" });

  for (const refused of ["1500.567", "12.3456", "0", "0.00"]) {
    fireEvent.change(screen.getByLabelText("Revenue, KES"), {
      target: { value: refused },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Enter the revenue as a positive amount with at most two decimals.",
    );
    expect(puts(fetcher)).toHaveLength(0);
  }

  // The field itself never takes a negative, so a minus is dropped rather than refused on save.
  fireEvent.change(screen.getByLabelText("Revenue, KES"), {
    target: { value: "-20" },
  });
  expect(screen.getByLabelText("Revenue, KES")).toHaveValue("20");

  fireEvent.change(screen.getByLabelText("Revenue, KES"), {
    target: { value: "4,500.50" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() => expect(puts(fetcher)).toHaveLength(1));
  expect(puts(fetcher)[0].body).toMatchObject({ amount: 4500.5, reason: null });
});

it("shows the day totals the API works out for the whole grid, and opens Capture revenue on the oldest missing day", async () => {
  // A grid larger than this page: the figures cover vehicles the page does not list.
  serveWeek(() =>
    week(
      [
        vehicle(
          "vehicle-1",
          "KDA 482M",
          { [DATES[0]]: recorded(8500) },
          { earliestMissing: DATES[1] },
        ),
        vehicle("vehicle-2", "KBZ 110A", {}, { earliestMissing: DATES[0] }),
      ],
      {
        dayTotals: DATES.map((date, index) => ({
          date,
          amount: index === 0 ? 91500 : 0,
          expected: 0,
        })),
        firstGap: { vehicleId: "vehicle-2", date: DATES[0] },
      },
    ),
  );
  renderInApp(<RevenuePage />, { permissions: CLERK });

  const grid = await screen.findByRole("table", {
    name: /Revenue by vehicle and day/,
  });
  expect(
    within(within(grid).getByRole("row", { name: /^2 vehicles/ })).getByText(
      "91,500",
    ),
  ).toBeInTheDocument();
  // KBZ 110A still misses Monday, the oldest day without a record.
  fireEvent.click(screen.getByRole("button", { name: "Capture revenue" }));
  const dialog = await screen.findByRole("dialog", { name: "KBZ 110A" });
  expect(within(dialog).getByText("Mon 28 Sep 2026")).toBeInTheDocument();
});

it("loads a fleet beyond the API's whole-grid limit in pages of the same week, and shows it once all are in", async () => {
  const fleet = Array.from({ length: 730 }, (_, index) =>
    vehicle(
      `vehicle-${index}`,
      `KDA ${String(index).padStart(3, "0")}A`,
      {},
      { earliestMissing: null },
    ),
  );
  const last = fleet[729];
  const fetcher = serve((path) => {
    const url = new URL(path, "http://web");
    if (!url.pathname.startsWith("/api/setup/revenue")) return undefined;
    const page = Number(url.searchParams.get("page") ?? 0);
    if (!page)
      return json(
        week(fleet.slice(0, 500), {
          truncated: true,
          totalVehicles: 730,
          firstGap: { vehicleId: last.id, date: DATES[0] },
        }),
      );
    return json(
      week(fleet.slice((page - 1) * 100, page * 100), {
        pageNumber: page,
        pageSize: 100,
        totalVehicles: 730,
      }),
    );
  });
  renderInApp(<RevenuePage />, { permissions: CLERK });

  const grid = await screen.findByRole("table", {
    name: /Revenue by vehicle and day/,
  });
  expect(gets(fetcher, "/api/setup/revenue")).toEqual([
    "/api/setup/revenue",
    "/api/setup/revenue?weekStart=2026-09-28&page=6&pageSize=100",
    "/api/setup/revenue?weekStart=2026-09-28&page=7&pageSize=100",
    "/api/setup/revenue?weekStart=2026-09-28&page=8&pageSize=100",
  ]);
  // Every vehicle, the last page's included, is a row of the grid (plus its two header rows).
  expect(grid).toHaveAttribute("aria-rowcount", String(fleet.length + 2));
}, 30_000);

it("loads the week again when the fleet changed between its pages, so no vehicle is skipped", async () => {
  const before = Array.from({ length: 730 }, (_, index) =>
    vehicle(
      `vehicle-${index}`,
      `KDA ${String(index).padStart(3, "0")}A`,
      {},
      { earliestMissing: null },
    ),
  );
  // vehicle-10 left after the first answer, so every later page starts one vehicle further on.
  const after = before.filter((item) => item.id !== "vehicle-10");
  let firstAnswers = 0;
  const fetcher = serve((path) => {
    const url = new URL(path, "http://web");
    if (!url.pathname.startsWith("/api/setup/revenue")) return undefined;
    const page = Number(url.searchParams.get("page") ?? 0);
    if (!page) {
      const fleet = firstAnswers++ === 0 ? before : after;
      return json(
        week(fleet.slice(0, 500), {
          truncated: true,
          totalVehicles: fleet.length,
        }),
      );
    }
    return json(
      week(after.slice((page - 1) * 100, page * 100), {
        pageNumber: page,
        pageSize: 100,
        totalVehicles: after.length,
      }),
    );
  });
  renderInApp(<RevenuePage />, { permissions: CLERK });

  const grid = await screen.findByRole("table", {
    name: /Revenue by vehicle and day/,
  });
  const pages = [
    "/api/setup/revenue",
    "/api/setup/revenue?weekStart=2026-09-28&page=6&pageSize=100",
    "/api/setup/revenue?weekStart=2026-09-28&page=7&pageSize=100",
    "/api/setup/revenue?weekStart=2026-09-28&page=8&pageSize=100",
  ];
  expect(gets(fetcher, "/api/setup/revenue")).toEqual([...pages, ...pages]);
  expect(grid).toHaveAttribute("aria-rowcount", String(after.length + 2));
}, 30_000);

const fleetOf = (count: number) =>
  Array.from({ length: count }, (_, index) =>
    vehicle(
      `vehicle-${index}`,
      `KDA ${String(index).padStart(3, "0")}A`,
      { [DATES[0]]: recorded(100 + index) },
      { totalAmount: 100 + index },
    ),
  );

// jsdom lays nothing out: the grid's body reports where it would sit on the screen, and the page "scrolls" to it.
function scrollGridTo(top: number) {
  vi.spyOn(
    HTMLTableSectionElement.prototype,
    "getBoundingClientRect",
  ).mockReturnValue({ top } as DOMRect);
  fireEvent.scroll(window);
}

// A vehicle's row in the grid, found by its registration. Role queries work out every row's name, which is slow on
// a large grid.
const rowOf = (grid: HTMLElement, registration: string) =>
  within(grid).queryByText(registration)?.closest("tr") ?? null;

it("renders only the rows near the screen for a large fleet, numbered for screen readers as the whole grid", async () => {
  serveWeek(() =>
    week(fleetOf(200), {
      dayTotals: DATES.map((date, index) => ({
        date,
        amount: index === 0 ? 39900 : 0,
        expected: 0,
      })),
    }),
  );
  renderInApp(<RevenuePage />, { permissions: CLERK });

  const grid = await screen.findByRole("table", {
    name: /Revenue by vehicle and day/,
  });
  expect(grid).toHaveAttribute("aria-rowcount", "202");
  const rendered = () => within(grid).getAllByText(/^KDA \d{3}A$/);
  expect(rendered().length).toBeLessThan(60);
  expect(rowOf(grid, "KDA 000A")).toHaveAttribute("aria-rowindex", "2");
  expect(rowOf(grid, "KDA 150A")).toBeNull();
  // The totals are the API's, for every vehicle, whichever rows are rendered.
  const totals = within(grid).getByText("200 vehicles").closest("tr")!;
  expect(totals).toHaveAttribute("aria-rowindex", "202");
  expect(within(totals).getByText("39,900")).toBeInTheDocument();

  scrollGridTo(-150 * 57);
  await waitFor(() =>
    expect(rowOf(grid, "KDA 150A")).toHaveAttribute("aria-rowindex", "152"),
  );
  expect(rowOf(grid, "KDA 000A")).toBeNull();
  expect(rendered().length).toBeLessThan(60);
});

it("gives focus back to the day that opened capture after the grid scrolled it away", async () => {
  serveWeek(() => week(fleetOf(200)));
  renderInApp(<RevenuePage />, { permissions: CLERK });

  const grid = await screen.findByRole("table", {
    name: /Revenue by vehicle and day/,
  });
  const day = "KDA 000A, Wed 30 Sep 2026: Missing";
  fireEvent.click(
    within(rowOf(grid, "KDA 000A")!).getByRole("button", { name: day }),
  );
  const dialog = await screen.findByRole("dialog", { name: "KDA 000A" });
  scrollGridTo(-150 * 57);
  await waitFor(() => expect(rowOf(grid, "KDA 000A")).toBeNull());

  fireEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
  await waitFor(() =>
    expect(
      within(rowOf(grid, "KDA 000A")!).getByRole("button", { name: day }),
    ).toHaveFocus(),
  );
});

it("re-renders no vehicle row when capture opens", async () => {
  serveWeek(() => week(fleetOf(40)));
  renderInApp(<RevenuePage />, { permissions: CLERK });

  const grid = await screen.findByRole("table", {
    name: /Revenue by vehicle and day/,
  });
  // The counters see every row and cell of the first render.
  expect(vi.mocked(useFormats).mock.calls.length).toBeGreaterThanOrEqual(
    40 + 40 * 7,
  );
  expect(vi.mocked(canOpen).mock.calls.length).toBeGreaterThanOrEqual(40 * 7);
  vi.mocked(useFormats).mockClear();
  vi.mocked(canOpen).mockClear();
  fireEvent.click(
    within(rowOf(grid, "KDA 000A")!).getByRole("button", {
      name: "KDA 000A, Wed 30 Sep 2026: Missing",
    }),
  );
  const dialog = await screen.findByRole("dialog", { name: "KDA 000A" });
  fireEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
  // The page and the capture form render; no row does.
  expect(vi.mocked(useFormats).mock.calls.length).toBeLessThan(40);
  expect(vi.mocked(canOpen)).not.toHaveBeenCalled();
});

it("exports the week shown to someone with revenue.export, and offers it to no one else", async () => {
  URL.createObjectURL = vi.fn(() => "blob:week");
  URL.revokeObjectURL = vi.fn();
  const saved: string[] = [];
  const click = vi
    .spyOn(HTMLAnchorElement.prototype, "click")
    .mockImplementation(function (this: HTMLAnchorElement) {
      saved.push(this.download);
    });
  const fetcher = serveWeek(() => week([vehicle("vehicle-1", "KDA 482M")]));
  const { unmount } = renderInApp(<RevenuePage />, {
    permissions: [...CLERK, "revenue.export"],
  });
  await screen.findByRole("table", { name: /Revenue by vehicle and day/ });

  fireEvent.click(screen.getByRole("button", { name: "Export" }));
  fireEvent.click(screen.getByRole("menuitem", { name: "Excel" }));

  await waitFor(() => expect(saved).toHaveLength(1));
  expect(gets(fetcher, "/api/setup/revenue/export")).toEqual([
    "/api/setup/revenue/export?weekStart=2026-09-28&format=xlsx",
  ]);
  expect(saved[0]).toBe("Revenue 28 Sep-4 Oct 2026.xlsx");
  click.mockRestore();
  unmount();

  renderInApp(<RevenuePage />, { permissions: CLERK });
  await screen.findByRole("table", { name: /Revenue by vehicle and day/ });
  expect(
    screen.queryByRole("button", { name: "Export" }),
  ).not.toBeInTheDocument();
});
