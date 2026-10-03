import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import type { RevenueCell, RevenueVehicle, RevenueWeek } from "@xcode/shared";
import { RevenuePage } from "../components/RevenuePage";
import { renderInApp } from "./renderInApp";

// Monday to Sunday; the organization's business date is the Wednesday.
const DATES = ["2026-09-28", "2026-09-29", "2026-09-30", "2026-10-01", "2026-10-02", "2026-10-03", "2026-10-04"];
const TODAY = "2026-09-30";
const CLERK = ["revenue.view", "revenue.capture", "revenue.no_earnings"];
const OFFICE = ["revenue.view", "revenue.capture", "revenue.no_earnings", "revenue.correct"];

function cell(date: string, over: Partial<RevenueCell> = {}): RevenueCell {
  const status = date > TODAY ? "future" : "missing";
  return { date, status, expected: 1000, amount: null, reason: null, note: null, canEdit: status === "missing", editedAfterCapture: false, version: null, ...over };
}

const recorded = (amount: number, version = 1, over: Partial<RevenueCell> = {}): Partial<RevenueCell> => ({ status: "amount", amount, version, canEdit: false, ...over });

function vehicle(id: string, registration: string, days: Record<string, Partial<RevenueCell>> = {}, over: Partial<RevenueVehicle> = {}): RevenueVehicle {
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

function week(vehicles: RevenueVehicle[], over: Partial<RevenueWeek> = {}): RevenueWeek {
  return {
    weekStart: DATES[0],
    weekThrough: DATES[6],
    currentWeekStart: DATES[0],
    businessDate: TODAY,
    companies: [{ id: "company-1", name: "North Star" }, { id: "company-2", name: "Metro Link" }],
    vehicles,
    totalAmount: 0,
    totalExpected: 0,
    percent: null,
    ...over,
  };
}

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

type Handler = (path: string, init?: RequestInit) => Response | Promise<Response> | undefined;

// A fake API: every call is recorded, and anything the handler does not answer is a 404.
function serve(handler: Handler) {
  const fetcher = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => (await handler(String(input), init)) ?? json({}, 404));
  vi.stubGlobal("fetch", fetcher);
  return fetcher;
}

const puts = (fetcher: ReturnType<typeof serve>) =>
  fetcher.mock.calls.filter(([, init]) => init?.method === "PUT").map(([input, init]) => ({ path: String(input), body: JSON.parse(String(init?.body)) }));
const gets = (fetcher: ReturnType<typeof serve>, fragment: string) =>
  fetcher.mock.calls.filter(([input, init]) => !init?.method && String(input).includes(fragment)).map(([input]) => String(input));

// The grid answers the plain week request; a vehicle's own week (vehicleId) is answered by `vehicleWeek`.
function serveWeek(grid: () => RevenueWeek, options: { save?: Handler; vehicleWeek?: (path: string) => RevenueWeek | undefined } = {}) {
  return serve((path, init) => {
    if (init?.method === "PUT") return options.save?.(path, init) ?? json({ id: "record-1", version: 1 });
    if (path.includes("vehicleId=")) {
      const found = options.vehicleWeek?.(path);
      return found ? json(found) : undefined;
    }
    if (path.startsWith("/api/setup/revenue")) return json(grid());
  });
}

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

it("renders the week grid from one request, with totals, today and a company filter", async () => {
  const fetcher = serveWeek(() =>
    week(
      [
        vehicle("vehicle-1", "KDA 482M", { [DATES[0]]: recorded(850), [DATES[1]]: { status: "reason", reason: "Garage", version: 1, canEdit: false } }, {
          totalAmount: 850,
          totalExpected: 2000,
          percent: 43,
        }),
        vehicle("vehicle-2", "KBZ 110A", { [DATES[0]]: recorded(1200), [DATES[1]]: recorded(1000) }, { companyId: "company-2", companyName: "Metro Link", totalAmount: 2200, totalExpected: 2000, percent: 110 }),
      ],
      { totalAmount: 3050, totalExpected: 4000, percent: 76 },
    ),
  );
  renderInApp(<RevenuePage />, { permissions: CLERK });

  const grid = await screen.findByRole("table", { name: /Revenue by vehicle and day/ });
  expect(within(grid).getByRole("columnheader", { name: "Vehicle" })).toBeInTheDocument();
  expect(within(grid).getByRole("columnheader", { name: "Mon 28" })).toBeInTheDocument();
  expect(within(grid).getByRole("columnheader", { name: "Sun 4" })).toBeInTheDocument();
  expect(within(grid).getByRole("columnheader", { name: "Week" })).toBeInTheDocument();
  expect(within(grid).getByRole("columnheader", { name: "vs expected" })).toBeInTheDocument();
  expect(within(grid).getByRole("columnheader", { name: /Wed 30/ })).toHaveAttribute("aria-current", "date");

  const row = within(grid).getByRole("row", { name: /KDA 482M/ });
  expect(within(row).getByRole("rowheader")).toHaveTextContent("KDA 482M");
  expect(within(row).getByText("North Star")).toBeInTheDocument();
  expect(within(row).getByText("850", { selector: "span" })).toBeInTheDocument();
  expect(within(row).getByText("Garage")).toBeInTheDocument();
  expect(within(row).getByText("43%")).toBeInTheDocument();
  // Missing days say so in words, not only by colour.
  expect(within(row).getByRole("button", { name: "KDA 482M, Wed 30 Sep 2026: Missing" })).toHaveTextContent("Enter");

  const totals = within(grid).getByRole("row", { name: /All vehicles/ });
  expect(within(totals).getByText("2,050")).toBeInTheDocument();
  expect(within(totals).getByText("3,050")).toBeInTheDocument();
  expect(within(totals).getByText("76%")).toBeInTheDocument();

  expect(screen.getByText("28 Sep to 4 Oct 2026")).toBeInTheDocument();
  expect(screen.getByText("Week to date")).toBeInTheDocument();
  expect(screen.getByText("of KES 4,000 expected, 76%")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Next week" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Previous week" })).toBeEnabled();
  expect(gets(fetcher, "/api/setup/revenue")).toEqual(["/api/setup/revenue"]);

  fireEvent.change(screen.getByRole("combobox", { name: "Company" }), { target: { value: "company-2" } });
  await waitFor(() => expect(gets(fetcher, "companyId=company-2")).toHaveLength(1));
  fireEvent.click(await screen.findByRole("button", { name: "Previous week" }));
  await waitFor(() => expect(gets(fetcher, "weekStart=2026-09-21")).toHaveLength(1));
});

// This week lists North Star only; last week also lists Old Fleet, archived since, which had a vehicle running then.
function serveCompanies() {
  return serve((path) => {
    if (!path.startsWith("/api/setup/revenue")) return undefined;
    const query = new URL(path, "http://xcode.test").searchParams;
    const start = query.get("weekStart") ?? DATES[0];
    const company = query.get("companyId");
    const past = start < DATES[0];
    const companies = past ? [{ id: "company-3", name: "Old Fleet" }, { id: "company-1", name: "North Star" }] : [{ id: "company-1", name: "North Star" }];
    const vehicles = [
      vehicle("vehicle-1", "KDA 482M"),
      ...(past ? [vehicle("vehicle-3", "KAA 100A", {}, { companyId: "company-3", companyName: "Old Fleet" })] : []),
    ];
    const through = past ? "2026-09-27" : DATES[6];
    return json(week(vehicles.filter((item) => !company || item.companyId === company), { weekStart: start, weekThrough: through, companies }));
  });
}

it("drops a company filter the next week does not list, instead of leaving an empty grid with no way back", async () => {
  const fetcher = serveCompanies();
  renderInApp(<RevenuePage />, { permissions: CLERK });

  await screen.findByRole("row", { name: /KDA 482M/ });
  // One company this week: nothing to choose.
  expect(screen.queryByRole("combobox", { name: "Company" })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Previous week" }));
  fireEvent.change(await screen.findByRole("combobox", { name: "Company" }), { target: { value: "company-3" } });
  await screen.findByRole("row", { name: /KAA 100A/ });
  expect(screen.queryByRole("row", { name: /KDA 482M/ })).not.toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Next week" }));
  await waitFor(() => expect(gets(fetcher, "weekStart=2026-09-28&companyId=company-3")).toHaveLength(1));
  // Old Fleet is not an option this week, so the grid goes back to every company.
  expect(await screen.findByRole("row", { name: /KDA 482M/ })).toBeInTheDocument();
  expect(gets(fetcher, "weekStart=2026-09-28&companyId=company-3")).toHaveLength(1);
  expect(gets(fetcher, "/api/setup/revenue?weekStart=2026-09-28").filter((path) => !path.includes("companyId"))).toHaveLength(1);
  expect(screen.queryByText("No vehicles.")).not.toBeInTheDocument();
  expect(screen.queryByRole("combobox", { name: "Company" })).not.toBeInTheDocument();
});

it("keeps the company control, with All companies, for as long as a filter is set", async () => {
  const fetcher = serveCompanies();
  renderInApp(<RevenuePage />, { permissions: CLERK });

  await screen.findByRole("row", { name: /KDA 482M/ });
  fireEvent.click(screen.getByRole("button", { name: "Previous week" }));
  fireEvent.change(await screen.findByRole("combobox", { name: "Company" }), { target: { value: "company-1" } });
  await waitFor(() => expect(screen.queryByRole("row", { name: /KAA 100A/ })).not.toBeInTheDocument());

  // North Star is this week's only company, and the filter on it stays visible and can be cleared.
  fireEvent.click(screen.getByRole("button", { name: "Next week" }));
  await screen.findByRole("table", { name: "Revenue by vehicle and day, 28 Sep to 4 Oct 2026" });
  const company = screen.getByRole("combobox", { name: "Company" });
  expect(company).toHaveValue("company-1");
  expect(within(company).getByRole("option", { name: "All companies" })).toBeInTheDocument();
  fireEvent.change(company, { target: { value: "" } });
  await waitFor(() => expect(gets(fetcher, "/api/setup/revenue?weekStart=2026-09-28").filter((path) => !path.includes("companyId"))).toHaveLength(1));
  await waitFor(() => expect(screen.queryByRole("combobox", { name: "Company" })).not.toBeInTheDocument());
});

it("shows a vehicle's week detail with expected, actual, difference and a bar for each recorded day", async () => {
  serveWeek(() =>
    week([
      vehicle("vehicle-1", "KDA 482M", { [DATES[0]]: recorded(850), [DATES[1]]: recorded(1350) }, { totalAmount: 2200, totalExpected: 2000, percent: 110 }),
    ]),
  );
  renderInApp(<RevenuePage />, { permissions: CLERK });

  const toggle = await screen.findByRole("button", { name: "KDA 482M" });
  expect(toggle).toHaveAttribute("aria-expanded", "false");
  fireEvent.click(toggle);
  expect(toggle).toHaveAttribute("aria-expanded", "true");

  const detail = screen.getByRole("table", { name: "KDA 482M week detail" });
  for (const name of ["Day", "Expected", "Revenue", "Difference"]) expect(within(detail).getByRole("columnheader", { name })).toBeInTheDocument();
  expect(within(within(detail).getByRole("row", { name: /Mon 28/ })).getByText("KES 150 below")).toBeInTheDocument();
  expect(within(within(detail).getByRole("row", { name: /Tue 29/ })).getByText("KES 350 above")).toBeInTheDocument();
  expect(within(within(detail).getByRole("row", { name: /Wed 30/ })).getByText("Not yet")).toBeInTheDocument();
  expect(within(within(detail).getByRole("row", { name: /To date/ })).getByText("KES 200 above")).toBeInTheDocument();
  expect(detail.querySelectorAll("[data-bar]")).toHaveLength(2);
});

it("opens a vehicle's earliest missing day first, loading it when it falls in another week", async () => {
  const fetcher = serveWeek(
    () => week([vehicle("vehicle-1", "KDA 482M", { [DATES[0]]: { canEdit: false }, [DATES[1]]: { canEdit: false }, [DATES[2]]: { canEdit: false } }, { earliestMissing: "2026-09-24" })]),
    {
      vehicleWeek: () =>
        week(
          [
            vehicle("vehicle-1", "KDA 482M", {}, {
              earliestMissing: "2026-09-24",
              days: ["2026-09-21", "2026-09-22", "2026-09-23", "2026-09-24"].map((date, index) => cell(date, index < 3 ? recorded(900) : { expected: 1100 })),
            }),
          ],
          { weekStart: "2026-09-21" },
        ),
    },
  );
  renderInApp(<RevenuePage />, { permissions: CLERK });

  // A later missing day stays shut on the server, but the grid still offers it and opens the earliest gap instead.
  fireEvent.click(await screen.findByRole("button", { name: "KDA 482M, Wed 30 Sep 2026: Missing" }));
  const dialog = await screen.findByRole("dialog", { name: "KDA 482M" });
  expect(await within(dialog).findByText("Thu 24 Sep 2026. Expected KES 1,100")).toBeInTheDocument();
  expect(within(dialog).getByText("Fill Thu 24 Sep 2026 first.")).toBeInTheDocument();
  expect(gets(fetcher, "vehicleId=vehicle-1")).toEqual(["/api/setup/revenue?weekStart=2026-09-24&vehicleId=vehicle-1"]);

  fireEvent.change(within(dialog).getByLabelText("Revenue"), { target: { value: "1100" } });
  fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));
  await waitFor(() => expect(puts(fetcher)[0]?.path).toBe("/api/setup/revenue/vehicle-1/2026-09-24"));
});

it("starts capture from the grid's primary action at the earliest missing vehicle and day", async () => {
  const fetcher = serveWeek(() =>
    week([
      vehicle("vehicle-1", "KDA 482M", { [DATES[0]]: recorded(900), [DATES[2]]: { canEdit: false } }, { earliestMissing: DATES[1] }),
      vehicle("vehicle-2", "KBZ 110A", { [DATES[1]]: { canEdit: false }, [DATES[2]]: { canEdit: false } }, { earliestMissing: DATES[0] }),
    ]),
  );
  renderInApp(<RevenuePage />, { permissions: CLERK });

  fireEvent.click(await screen.findByRole("button", { name: "Capture revenue" }));
  const dialog = await screen.findByRole("dialog", { name: "KBZ 110A" });
  expect(within(dialog).getByText("Mon 28 Sep 2026. Expected KES 1,000")).toBeInTheDocument();
  expect(gets(fetcher, "vehicleId=")).toHaveLength(0);
});

it("moves to the next vehicle still missing that day after a save, then closes", async () => {
  const fetcher = serveWeek(() =>
    week([
      vehicle("vehicle-1", "KDA 482M", { [DATES[0]]: recorded(900), [DATES[1]]: recorded(900) }),
      vehicle("vehicle-2", "KBZ 110A", { [DATES[0]]: recorded(900), [DATES[1]]: recorded(900), [DATES[2]]: recorded(700) }),
      vehicle("vehicle-3", "KCE 301B", { [DATES[0]]: recorded(900), [DATES[1]]: recorded(900) }),
    ]),
  );
  renderInApp(<RevenuePage />, { permissions: CLERK });

  fireEvent.click(await screen.findByRole("button", { name: "KDA 482M, Wed 30 Sep 2026: Missing" }));
  let dialog = await screen.findByRole("dialog", { name: "KDA 482M" });
  fireEvent.change(within(dialog).getByLabelText("Revenue"), { target: { value: "1000" } });
  fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));

  // KBZ 110A already has Wednesday, so the next one missing it is KCE 301B.
  dialog = await screen.findByRole("dialog", { name: "KCE 301B" });
  expect(within(dialog).getByText("Wed 30 Sep 2026. Expected KES 1,000")).toBeInTheDocument();
  expect(within(dialog).getByLabelText("Revenue")).toHaveValue("");
  fireEvent.change(within(dialog).getByLabelText("Revenue"), { target: { value: "800" } });
  fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));

  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  expect(puts(fetcher).map((call) => call.path)).toEqual(["/api/setup/revenue/vehicle-1/2026-09-30", "/api/setup/revenue/vehicle-3/2026-09-30"]);
});

it("after filling an earlier gap, returns to the same vehicle's next gap before moving on", async () => {
  let saved = false;
  const fetcher = serveWeek(
    () => week([vehicle("vehicle-1", "KDA 482M", { [DATES[1]]: { canEdit: false }, [DATES[2]]: { canEdit: false } }, { earliestMissing: DATES[0] })]),
    {
      save: () => {
        saved = true;
        return json({ id: "record-1", version: 1 });
      },
      vehicleWeek: () => (saved ? week([vehicle("vehicle-1", "KDA 482M", { [DATES[0]]: recorded(900), [DATES[2]]: { canEdit: false } }, { earliestMissing: DATES[1] })]) : undefined),
    },
  );
  renderInApp(<RevenuePage />, { permissions: CLERK });

  fireEvent.click(await screen.findByRole("button", { name: "KDA 482M, Wed 30 Sep 2026: Missing" }));
  let dialog = await screen.findByRole("dialog", { name: "KDA 482M" });
  expect(within(dialog).getByText("Fill Mon 28 Sep 2026 first.")).toBeInTheDocument();
  fireEvent.change(within(dialog).getByLabelText("Revenue"), { target: { value: "900" } });
  fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));

  dialog = await screen.findByRole("dialog", { name: "KDA 482M" });
  expect(await within(dialog).findByText("Fill Tue 29 Sep 2026 first.")).toBeInTheDocument();
  expect(gets(fetcher, "vehicleId=vehicle-1")).toEqual(["/api/setup/revenue?weekStart=2026-09-30&vehicleId=vehicle-1"]);
});

it("sends the version the day was opened at, even when the grid reloads underneath the dialog", async () => {
  let reads = 0;
  const fetcher = serveWeek(() =>
    week([
      vehicle("vehicle-1", "KDA 482M", { [DATES[0]]: recorded(900), [DATES[1]]: recorded(900) }),
      // Someone else captures KBZ 110A's Wednesday while this person is still on KDA 482M.
      vehicle("vehicle-2", "KBZ 110A", { [DATES[0]]: recorded(900), [DATES[1]]: recorded(900), ...(++reads > 1 ? { [DATES[2]]: recorded(650, 7, { canEdit: true }) } : {}) }),
    ]),
  );
  renderInApp(<RevenuePage />, { permissions: CLERK });

  fireEvent.click(await screen.findByRole("button", { name: "KDA 482M, Wed 30 Sep 2026: Missing" }));
  let dialog = await screen.findByRole("dialog", { name: "KDA 482M" });
  fireEvent.change(within(dialog).getByLabelText("Revenue"), { target: { value: "1000" } });
  fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));

  dialog = await screen.findByRole("dialog", { name: "KBZ 110A" });
  await waitFor(() => expect(gets(fetcher, "/api/setup/revenue")).toHaveLength(2));
  fireEvent.change(within(dialog).getByLabelText("Revenue"), { target: { value: "800" } });
  fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));

  // It opened as a missing day, so it must not overwrite the record saved meanwhile: the server answers 409 instead.
  await waitFor(() => expect(puts(fetcher)).toHaveLength(2));
  expect(puts(fetcher)[1].body).toEqual({ amount: 800, reason: null, note: null, version: null });
});

it("sends the record's version when correcting a past day", async () => {
  const fetcher = serveWeek(() => week([vehicle("vehicle-1", "KDA 482M", { [DATES[0]]: recorded(850, 3, { canEdit: true }) })]));
  renderInApp(<RevenuePage />, { permissions: OFFICE });

  fireEvent.click(await screen.findByRole("button", { name: "KDA 482M, Mon 28 Sep 2026: KES 850" }));
  const dialog = await screen.findByRole("dialog", { name: "KDA 482M" });
  expect(within(dialog).getByLabelText("Revenue")).toHaveValue("850");
  fireEvent.change(within(dialog).getByLabelText("Revenue"), { target: { value: "900" } });
  fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));

  await waitFor(() => expect(puts(fetcher)).toHaveLength(1));
  expect(puts(fetcher)[0]).toEqual({ path: "/api/setup/revenue/vehicle-1/2026-09-28", body: { amount: 900, reason: null, note: null, version: 3 } });
});

const conflict = (current?: Partial<RevenueCell>) =>
  json(
    {
      title: "This day already has a different record.",
      detail: "This day was changed after you opened it. Check the current record and save again.",
      status: 409,
      ...(current ? { current: cell(DATES[0], current) } : {}),
    },
    409,
  );

it("on a conflict shows the saved value against yours and replaces it with the saved version", async () => {
  let attempt = 0;
  const fetcher = serveWeek(() => week([vehicle("vehicle-1", "KDA 482M", { [DATES[0]]: recorded(850, 3, { canEdit: true }) })]), {
    save: () => (++attempt === 1 ? conflict(recorded(950, 4, { canEdit: true })) : json({ id: "record-1", version: 5 })),
  });
  renderInApp(<RevenuePage />, { permissions: OFFICE });

  fireEvent.click(await screen.findByRole("button", { name: "KDA 482M, Mon 28 Sep 2026: KES 850" }));
  const dialog = await screen.findByRole("dialog", { name: "KDA 482M" });
  fireEvent.change(within(dialog).getByLabelText("Revenue"), { target: { value: "900" } });
  fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));

  expect(await within(dialog).findByText("This day was changed after you opened it. Check the current record and save again.")).toBeInTheDocument();
  expect(within(dialog).getByText("Saved value").nextElementSibling).toHaveTextContent("KES 950");
  expect(within(dialog).getByText("Yours").nextElementSibling).toHaveTextContent("KES 900");
  fireEvent.click(within(dialog).getByRole("button", { name: "Replace with mine" }));

  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  expect(puts(fetcher).map((call) => call.body)).toEqual([
    { amount: 900, reason: null, note: null, version: 3 },
    { amount: 900, reason: null, note: null, version: 4 },
  ]);
});

it("on a conflict can keep the saved record, and offers no replace to someone who may not change it", async () => {
  const fetcher = serveWeek(() => week([vehicle("vehicle-1", "KDA 482M")]), { save: () => conflict(recorded(950, 1, { canEdit: false })) });
  renderInApp(<RevenuePage />, { permissions: CLERK });

  fireEvent.click(await screen.findByRole("button", { name: "KDA 482M, Mon 28 Sep 2026: Missing" }));
  const dialog = await screen.findByRole("dialog", { name: "KDA 482M" });
  fireEvent.change(within(dialog).getByLabelText("Revenue"), { target: { value: "900" } });
  fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));

  expect(await within(dialog).findByText("Saved value")).toBeInTheDocument();
  expect(within(dialog).queryByRole("button", { name: "Replace with mine" })).not.toBeInTheDocument();
  const reads = gets(fetcher, "/api/setup/revenue").length;
  fireEvent.click(within(dialog).getByRole("button", { name: "Keep saved" }));

  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  expect(puts(fetcher)).toHaveLength(1);
  await waitFor(() => expect(gets(fetcher, "/api/setup/revenue").length).toBeGreaterThan(reads));
});

it("on a conflict without the saved record (an insert race) refetches the day, then offers the same choice", async () => {
  let attempt = 0;
  const fetcher = serveWeek(() => week([vehicle("vehicle-1", "KDA 482M")]), {
    save: () => (++attempt === 1 ? conflict() : json({ id: "record-1", version: 2 })),
    vehicleWeek: () => week([vehicle("vehicle-1", "KDA 482M", { [DATES[0]]: recorded(700, 1, { canEdit: true }) })]),
  });
  renderInApp(<RevenuePage />, { permissions: CLERK });

  fireEvent.click(await screen.findByRole("button", { name: "KDA 482M, Mon 28 Sep 2026: Missing" }));
  const dialog = await screen.findByRole("dialog", { name: "KDA 482M" });
  fireEvent.change(within(dialog).getByLabelText("Revenue"), { target: { value: "900" } });
  fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));

  expect(await within(dialog).findByText("Saved value")).toBeInTheDocument();
  expect(within(dialog).getByText("Saved value").nextElementSibling).toHaveTextContent("KES 700");
  expect(gets(fetcher, "vehicleId=vehicle-1")).toEqual(["/api/setup/revenue?weekStart=2026-09-28&vehicleId=vehicle-1"]);
  fireEvent.click(within(dialog).getByRole("button", { name: "Replace with mine" }));

  await waitFor(() => expect(puts(fetcher)).toHaveLength(2));
  expect(puts(fetcher)[1].body).toEqual({ amount: 900, reason: null, note: null, version: 1 });
});

it("when an earlier day is missing, says so and opens that day", async () => {
  const fetcher = serveWeek(() => week([vehicle("vehicle-1", "KDA 482M")]), {
    save: () => json({ title: "Invalid setup change", detail: "Record 2026-09-25 before this date first.", status: 400, earliestMissing: "2026-09-25" }, 400),
    vehicleWeek: () =>
      week([vehicle("vehicle-1", "KDA 482M", {}, { earliestMissing: "2026-09-25", days: [cell("2026-09-25", { expected: 1200 })] })], { weekStart: "2026-09-21" }),
  });
  renderInApp(<RevenuePage />, { permissions: CLERK });

  fireEvent.click(await screen.findByRole("button", { name: "KDA 482M, Mon 28 Sep 2026: Missing" }));
  const dialog = await screen.findByRole("dialog", { name: "KDA 482M" });
  fireEvent.change(within(dialog).getByLabelText("Revenue"), { target: { value: "900" } });
  fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));

  expect(await within(dialog).findByText("Record Fri 25 Sep 2026 first.")).toBeInTheDocument();
  fireEvent.click(within(dialog).getByRole("button", { name: "Open Fri 25 Sep 2026" }));
  expect(await within(dialog).findByText("Fri 25 Sep 2026. Expected KES 1,200")).toBeInTheDocument();
  expect(gets(fetcher, "vehicleId=vehicle-1")).toEqual(["/api/setup/revenue?weekStart=2026-09-25&vehicleId=vehicle-1"]);
});

it("offers no-revenue reasons only with the no-earnings permission, and Other needs a short note", async () => {
  const fetcher = serveWeek(() => week([vehicle("vehicle-1", "KDA 482M")]));
  const view = renderInApp(<RevenuePage />, { permissions: ["revenue.view", "revenue.capture"] });

  fireEvent.click(await screen.findByRole("button", { name: "KDA 482M, Mon 28 Sep 2026: Missing" }));
  let dialog = await screen.findByRole("dialog", { name: "KDA 482M" });
  expect(within(dialog).queryByRole("group", { name: "No revenue reason" })).not.toBeInTheDocument();
  expect(within(dialog).queryByRole("button", { name: "Garage" })).not.toBeInTheDocument();
  view.unmount();

  renderInApp(<RevenuePage />, { permissions: CLERK });
  fireEvent.click(await screen.findByRole("button", { name: "KDA 482M, Mon 28 Sep 2026: Missing" }));
  dialog = await screen.findByRole("dialog", { name: "KDA 482M" });
  const reasons = within(dialog).getByRole("group", { name: "No revenue reason" });
  expect(within(reasons).getAllByRole("button").map((button) => button.textContent)).toEqual(["Garage", "Arrest", "No Crew", "Other"]);

  fireEvent.change(within(dialog).getByLabelText("Revenue"), { target: { value: "500" } });
  fireEvent.click(within(reasons).getByRole("button", { name: "Other" }));
  expect(within(reasons).getByRole("button", { name: "Other" })).toHaveAttribute("aria-pressed", "true");
  expect(within(dialog).getByLabelText("Revenue")).toHaveValue("");
  fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));
  expect(await within(dialog).findByRole("alert")).toHaveTextContent("Say what happened.");
  expect(puts(fetcher)).toHaveLength(0);

  const note = within(dialog).getByLabelText("What happened");
  expect(note).toHaveAttribute("maxLength", "80");
  fireEvent.change(note, { target: { value: "  Flat tyre  " } });
  fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));
  await waitFor(() => expect(puts(fetcher)).toHaveLength(1));
  expect(puts(fetcher)[0].body).toEqual({ amount: null, reason: "Other", note: "Flat tyre", version: null });
});

it("without the no-earnings permission, a no-revenue day can only be replaced by an amount", async () => {
  const fetcher = serveWeek(() => week([vehicle("vehicle-1", "KDA 482M", { [DATES[0]]: { status: "reason", reason: "Garage", version: 2, canEdit: true } })]));
  renderInApp(<RevenuePage />, { permissions: ["revenue.view", "revenue.capture", "revenue.correct"] });

  fireEvent.click(await screen.findByRole("button", { name: "KDA 482M, Mon 28 Sep 2026: Garage" }));
  const dialog = await screen.findByRole("dialog", { name: "KDA 482M" });
  expect(within(dialog).getByText("Recorded as Garage. Enter the revenue to replace it.")).toBeInTheDocument();
  fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));
  expect(await within(dialog).findByRole("alert")).toHaveTextContent("Enter the revenue.");
  expect(puts(fetcher)).toHaveLength(0);
});

it("takes today from the business date, never the computer clock", async () => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date("2027-03-10T09:00:00Z"));
  serveWeek(() => week([vehicle("vehicle-1", "KDA 482M", { [DATES[0]]: recorded(900), [DATES[1]]: recorded(900) })]));
  renderInApp(<RevenuePage />, { permissions: CLERK });

  const grid = await screen.findByRole("table", { name: /Revenue by vehicle and day/ });
  const current = within(grid).getAllByRole("columnheader").filter((header) => header.getAttribute("aria-current") === "date");
  expect(current.map((header) => header.textContent)).toEqual(["Wed 30, today"]);
  fireEvent.click(screen.getByRole("button", { name: "Capture revenue" }));
  const dialog = await screen.findByRole("dialog", { name: "KDA 482M" });
  expect(within(dialog).getByText("Wed 30 Sep 2026. Expected KES 1,000")).toBeInTheDocument();
});

it("saves once however often Save or Enter is pressed while a save is on its way", async () => {
  let finish: (response: Response) => void = () => {};
  const fetcher = serveWeek(() => week([vehicle("vehicle-1", "KDA 482M")]), {
    save: () => new Promise<Response>((resolve) => (finish = resolve)) as unknown as Response,
  });
  renderInApp(<RevenuePage />, { permissions: CLERK });

  fireEvent.click(await screen.findByRole("button", { name: "KDA 482M, Mon 28 Sep 2026: Missing" }));
  const dialog = await screen.findByRole("dialog", { name: "KDA 482M" });
  const amount = within(dialog).getByLabelText("Revenue");
  fireEvent.change(amount, { target: { value: "900" } });
  const form = amount.closest("form")!;
  fireEvent.submit(form);
  fireEvent.submit(form);
  fireEvent.click(within(dialog).getByRole("button", { name: /Sav/ }));
  expect(within(dialog).getByRole("button", { name: "Saving…" })).toBeDisabled();
  expect(puts(fetcher)).toHaveLength(1);

  await act(async () => finish(json({ id: "record-1", version: 1 })));
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  expect(puts(fetcher)).toHaveLength(1);
});

it("returns focus to the day that opened the dialog when it closes", async () => {
  serveWeek(() => week([vehicle("vehicle-1", "KDA 482M")]));
  renderInApp(<RevenuePage />, { permissions: CLERK });

  const day = await screen.findByRole("button", { name: "KDA 482M, Mon 28 Sep 2026: Missing" });
  day.focus();
  fireEvent.click(day);
  const dialog = await screen.findByRole("dialog", { name: "KDA 482M" });
  await waitFor(() => expect(within(dialog).getByLabelText("Revenue")).toHaveFocus());
  fireEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));

  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  expect(day).toHaveFocus();
});

// D3: cents are kept, so the web takes exactly what the API and the phone take.
it("refuses an amount with more than two decimals, or of zero, and keeps the cents it accepts", async () => {
  const fetcher = serveWeek(() => week([vehicle("vehicle-1", "KDA 482M", {}, { earliestMissing: DATES[0] })]));
  renderInApp(<RevenuePage />, { permissions: CLERK });

  fireEvent.click(await screen.findByRole("button", { name: "Capture revenue" }));
  await screen.findByRole("dialog", { name: "KDA 482M" });

  for (const refused of ["1500.567", "12.3456", "0", "0.00"]) {
    fireEvent.change(screen.getByLabelText("Revenue"), { target: { value: refused } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Enter the revenue as a positive amount with at most two decimals.",
    );
    expect(puts(fetcher)).toHaveLength(0);
  }

  // The field itself never takes a negative, so a minus is dropped rather than refused on save.
  fireEvent.change(screen.getByLabelText("Revenue"), { target: { value: "-20" } });
  expect(screen.getByLabelText("Revenue")).toHaveValue("20");

  fireEvent.change(screen.getByLabelText("Revenue"), { target: { value: "1,500.50" } });
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() => expect(puts(fetcher)).toHaveLength(1));
  expect(puts(fetcher)[0].body).toMatchObject({ amount: 1500.5, reason: null });
});
