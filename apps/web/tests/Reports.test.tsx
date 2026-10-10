import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import type {
  ReportColumn,
  ReportTable,
  ReportsAccess,
} from "@xcode/shared/reports";

import { AppShell } from "../components/AppShell";
import { ReportsPage } from "../components/reports/ReportsPage";
import { fakeApi, type Reply } from "./fakeApi";
import { appearanceFixture, renderInApp } from "./renderInApp";
import { optionsOf, pick } from "./searchSelect";

const BUSINESS_DATE = "2026-10-09";
const WEEK = "from=2026-10-05&to=2026-10-11";

const ACCESS: ReportsAccess = {
  businessDate: BUSINESS_DATE,
  firstDayOfWeek: 1,
  fleet: ["net", "target", "investment"],
  pettyCash: ["cashBook", "waiting"],
  holders: [
    { id: "h1", name: "Grace Wanjiru", active: true },
    { id: "h2", name: "Peter Otieno", active: false },
  ],
  canExport: true,
};

const COLUMNS: ReportColumn[] = [
  { key: "vehicle", label: "Vehicle", kind: "vehicle", sum: false },
  { key: "revenue", label: "Revenue", kind: "money", sum: true },
  { key: "out", label: "Money out", kind: "money", sum: true },
  { key: "net", label: "Net", kind: "net", sum: true },
  { key: "days", label: "Days", kind: "count", sum: true },
  { key: "share", label: "Share", kind: "percent", sum: false },
  { key: "last", label: "Last day", kind: "date", sum: false },
  { key: "litres", label: "Litres", kind: "quantity", sum: false },
  { key: "remark", label: "Remark", kind: "text", sum: false },
];

const TABLE: ReportTable = {
  group: "fleet",
  report: "net",
  title: "Net by vehicle",
  from: "2026-10-05",
  to: "2026-10-11",
  businessDate: BUSINESS_DATE,
  headline: { label: "Net contribution", value: 6000, kind: "net" },
  figures: [
    { label: "Revenue", value: 15000, kind: "money" },
    { label: "Worst vehicle", value: -2000, kind: "net" },
    { label: "Vehicles", value: 2, kind: "count" },
    { label: "Best share", value: 66.7, kind: "percent" },
  ],
  columns: COLUMNS,
  rows: [
    ["KDA 482M", 12000, 4000, 8000, 5, 66.7, "2026-10-08", 11.875, "On time"],
    ["KDB 100X", 3000, 5000, -2000, 4, 20, "2026-10-07", 4.5, "Late"],
  ],
  pageNumber: 1,
  pageSize: 50,
  total: 2,
  totals: [null, 15000, 9000, 6000, 9, null, null, null, null],
};

type Row = ReportTable["rows"][number];

// The report endpoints: the rows matching q, one page of them, and the footer over all the matching rows.
function serveReports(
  options: {
    access?: ReportsAccess;
    rows?: Row[];
    table?: Partial<ReportTable>;
    // Answers given to the first report requests instead of the report.
    failures?: Reply[];
  } = {},
) {
  const api = fakeApi();
  const failures = [...(options.failures ?? [])];
  api.on("setup/reports", [200, options.access ?? ACCESS]);
  api.on("setup/reports/*", (sent) => {
    const failure = failures.shift();
    if (failure) return failure;
    const url = new URL(sent.path, "http://localhost");
    const [, , group, report] = url.pathname.split("/");
    const words = (url.searchParams.get("q") ?? "")
      .toLowerCase()
      .split(/\s+/)
      .filter(Boolean);
    const matching = (options.rows ?? TABLE.rows).filter((row) =>
      words.every((word) => row.join(" ").toLowerCase().includes(word)),
    );
    const pageSize = Number(url.searchParams.get("pageSize") ?? 50);
    const pageNumber = Number(url.searchParams.get("page") ?? 1);
    const totals = COLUMNS.map((column, index) =>
      column.sum
        ? matching.reduce((sum, row) => sum + Number(row[index]), 0)
        : null,
    );
    return [
      200,
      {
        ...TABLE,
        group,
        report,
        rows: matching.slice(
          (pageNumber - 1) * pageSize,
          pageNumber * pageSize,
        ),
        pageNumber,
        pageSize,
        total: matching.length,
        totals,
        ...options.table,
      },
    ];
  });
  return api;
}

// The paths asked of the reports endpoints, without the first page of 50 that every request names.
const rawReads = (api: ReturnType<typeof serveReports>) =>
  api.calls
    .filter((call) => call.path.startsWith("setup/reports/"))
    .map((call) => call.path);
const reads = (api: ReturnType<typeof serveReports>) =>
  rawReads(api).map((path) => path.replace(/[?&]page=1&pageSize=25$/, ""));

function renderPage(
  api = serveReports(),
  permissions = ["reports.view", "reports.export"],
) {
  renderInApp(
    <ReportsPage />,
    { permissions },
    { businessDate: BUSINESS_DATE },
  );
  return api;
}

const changeTo = (element: HTMLElement, value: string) =>
  fireEvent.change(element, { target: { value } });

const openPeriod = () =>
  fireEvent.click(screen.getByRole("button", { name: /^Period, / }));

const exportAs = (format: "Excel" | "PDF") => {
  fireEvent.click(screen.getByRole("button", { name: "Export" }));
  fireEvent.click(screen.getByRole("menuitem", { name: format }));
};

const optionNames = optionsOf;

const clicks: { download: string; href: string }[] = [];

beforeEach(() => {
  clicks.length = 0;
  URL.createObjectURL = vi.fn(() => "blob:report");
  URL.revokeObjectURL = vi.fn();
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (
    this: HTMLAnchorElement,
  ) {
    clicks.push({ download: this.download, href: this.href });
  });
});
afterEach(() => vi.restoreAllMocks());

it("lists only the reports the access allows, under the labels of the catalog", async () => {
  renderPage();
  const select = await screen.findByLabelText("Report");
  expect(optionNames(select)).toEqual([
    "Net by vehicle",
    "Revenue against target",
    "Investment",
  ]);
  expect(select).toHaveValue("Net by vehicle");
});

it("opens the first allowed report for this week", async () => {
  const api = renderPage();
  expect(
    await screen.findByRole("row", { name: /KDA 482M/ }),
  ).toBeInTheDocument();
  expect(rawReads(api)).toEqual([
    `setup/reports/fleet/net?${WEEK}&page=1&pageSize=25`,
  ]);
  expect(screen.getByText("5 to 11 Oct 2026")).toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: "Period, 5 to 11 Oct 2026" }),
  ).toBeInTheDocument();
});

it("shows the headline and the figures as cards", async () => {
  renderPage();
  const figures = await screen.findByRole("group", { name: "Report figures" });
  const value = (label: string) => within(figures).getByText(label).nextSibling;
  expect(value("Net contribution")).toHaveTextContent("KES 6,000");
  expect(value("Revenue")).toHaveTextContent("KES 15,000");
  expect(value("Worst vehicle")).toHaveTextContent("KES -2,000");
  // On the headline card a loss takes the card's loss colour.
  expect(value("Worst vehicle")?.parentElement).toHaveClass("neg");
  expect(value("Net contribution")).not.toHaveClass("neg");
  expect(value("Vehicles")).toHaveTextContent(/^2$/);
  expect(value("Best share")).toHaveTextContent("66.7%");
});

it("offers the Fleet and Petty cash switch only to someone with both, and re-asks for the other group", async () => {
  const api = renderPage();
  const group = await screen.findByRole("group", { name: "Report type" });
  expect(within(group).getByRole("button", { name: "Fleet" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  fireEvent.click(within(group).getByRole("button", { name: "Petty cash" }));

  await waitFor(() =>
    expect(reads(api).at(-1)).toBe(`setup/reports/pettycash/cashBook?${WEEK}`),
  );
  expect(optionNames(screen.getByLabelText("Report"))).toEqual([
    "Cash book",
    "Waiting for approval",
  ]);
});

it.each([
  ["fleet only", { fleet: ["net" as const], pettyCash: [] }],
  ["petty cash only", { fleet: [], pettyCash: ["cashBook" as const] }],
])("hides the group switch with %s", async (_name, access) => {
  const api = renderPage(serveReports({ access: { ...ACCESS, ...access } }));
  await screen.findByRole("row", { name: /KDA 482M/ });
  expect(
    screen.queryByRole("group", { name: "Report type" }),
  ).not.toBeInTheDocument();
  expect(reads(api)[0]).toContain(
    access.fleet.length ? "reports/fleet/net" : "reports/pettycash/cashBook",
  );
});

it("says so when no report is allowed", async () => {
  renderPage(serveReports({ access: { ...ACCESS, fleet: [], pettyCash: [] } }));
  expect(
    await screen.findByText("No reports are available to you."),
  ).toBeInTheDocument();
});

it("asks again with the new period when the period changes", async () => {
  const api = renderPage();
  await screen.findByRole("row", { name: /KDA 482M/ });

  fireEvent.click(screen.getByRole("button", { name: "Previous week" }));
  await waitFor(() =>
    expect(reads(api).at(-1)).toBe(
      "setup/reports/fleet/net?from=2026-09-28&to=2026-10-04",
    ),
  );

  openPeriod();
  fireEvent.click(screen.getByRole("button", { name: "Last month" }));
  await waitFor(() =>
    expect(reads(api).at(-1)).toBe(
      "setup/reports/fleet/net?from=2026-09-01&to=2026-09-30",
    ),
  );

  openPeriod();
  changeTo(screen.getByLabelText("From"), "2026-08-01");
  changeTo(screen.getByLabelText("To"), "2026-08-15");
  fireEvent.click(screen.getByRole("button", { name: "Show these dates" }));
  await waitFor(() =>
    expect(reads(api).at(-1)).toBe(
      "setup/reports/fleet/net?from=2026-08-01&to=2026-08-15",
    ),
  );
});

it("keeps a report that takes no period free of the picker and of from and to", async () => {
  const api = renderPage();
  await screen.findByRole("row", { name: /KDA 482M/ });
  pick(screen.getByLabelText("Report"), "Investment");
  await waitFor(() =>
    expect(reads(api).at(-1)).toBe("setup/reports/fleet/investment"),
  );
  expect(
    screen.queryByRole("button", { name: /^Period, / }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "Previous week" }),
  ).not.toBeInTheDocument();

  pick(screen.getByLabelText("Report"), "Net by vehicle");
  expect(
    await screen.findByRole("button", { name: /^Period, / }),
  ).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Petty cash" }));
  pick(await screen.findByLabelText("Report"), "Waiting for approval");
  await waitFor(() =>
    expect(reads(api).at(-1)).toBe("setup/reports/pettycash/waiting"),
  );
  expect(
    screen.queryByRole("button", { name: /^Period, / }),
  ).not.toBeInTheDocument();
});

it("cuts petty cash reports to a manager, and leaves fleet reports uncut", async () => {
  const api = renderPage();
  await screen.findByRole("row", { name: /KDA 482M/ });
  expect(screen.queryByLabelText("Manager")).not.toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Petty cash" }));
  const manager = await screen.findByLabelText("Manager");
  expect(optionNames(manager)).toEqual([
    "All managers",
    "Grace Wanjiru",
    "Peter Otieno (not active)",
  ]);
  await waitFor(() =>
    expect(reads(api).at(-1)).toBe(`setup/reports/pettycash/cashBook?${WEEK}`),
  );

  pick(manager, "Peter Otieno (not active)");
  await waitFor(() =>
    expect(reads(api).at(-1)).toBe(
      `setup/reports/pettycash/cashBook?${WEEK}&holderId=h2`,
    ),
  );

  fireEvent.click(screen.getByRole("button", { name: "Fleet" }));
  expect(await screen.findByLabelText("Report")).toHaveValue("Net by vehicle");
  expect(screen.queryByLabelText("Manager")).not.toBeInTheDocument();
  expect(reads(api).filter((path) => path.includes("/fleet/"))).toEqual([
    `setup/reports/fleet/net?${WEEK}`,
  ]);
});

it("has no manager choice when only one float can be seen", async () => {
  renderPage(
    serveReports({
      access: { ...ACCESS, fleet: [], holders: [ACCESS.holders[0]] },
    }),
  );
  await screen.findByRole("row", { name: /KDA 482M/ });
  expect(screen.queryByLabelText("Manager")).not.toBeInTheDocument();
});

it("shows each cell by its kind", async () => {
  renderPage();
  const late = await screen.findByRole("row", { name: /KDB 100X/ });
  const cell = (label: string) =>
    late.querySelector(`[data-label="${label}"]`) as HTMLElement;
  expect(within(cell("Vehicle")).getByText("KDB 100X").tagName).toBe("STRONG");
  expect(cell("Revenue (KES)")).toHaveTextContent("3,000");
  expect(cell("Money out (KES)")).toHaveTextContent("5,000");
  expect(cell("Net (KES)")).toHaveTextContent("-2,000");
  expect(within(cell("Net (KES)")).getByText("-2,000")).toHaveClass("text-red");
  expect(cell("Days")).toHaveTextContent(/^4$/);
  expect(cell("Share")).toHaveTextContent("20%");
  expect(cell("Last day")).toHaveTextContent("7 Oct 2026");
  expect(cell("Litres")).toHaveTextContent("4.5");
  expect(cell("Remark")).toHaveTextContent("Late");

  const early = screen.getByRole("row", { name: /KDA 482M/ });
  const first = (label: string) =>
    early.querySelector(`[data-label="${label}"]`) as HTMLElement;
  expect(first("Net (KES)")).toHaveTextContent("8,000");
  expect(within(first("Net (KES)")).getByText("8,000")).not.toHaveClass(
    "text-red",
  );
  expect(first("Share")).toHaveTextContent("66.7%");
  expect(first("Litres")).toHaveTextContent("11.875");
});

it("shows the footer the server sent: the count of every matching row and the sums over all of them", async () => {
  renderPage(
    serveReports({
      table: {
        total: 120,
        totals: [null, 120000, 48000, -72000, 240, null, null, null, null],
      },
    }),
  );
  await screen.findByRole("row", { name: /KDA 482M/ });
  const footer = screen.getByText("120 rows").closest("tr")!;
  expect(
    within(footer)
      .getAllByRole("cell")
      .map((c) => c.textContent),
  ).toEqual([
    "120 rows",
    "120,000",
    "48,000",
    "-72,000",
    "240",
    "",
    "",
    "",
    "",
  ]);
});

it("sends the search to the server after a pause, and shows the rows and footer it answers with", async () => {
  const api = renderPage();
  await screen.findByRole("row", { name: /KDA 482M/ });
  expect(rawReads(api)).toHaveLength(1);

  changeTo(screen.getByLabelText("Search"), "kdb");
  changeTo(screen.getByLabelText("Search"), " kdb late ");
  expect(rawReads(api)).toHaveLength(1);
  await waitFor(() =>
    expect(rawReads(api).at(-1)).toBe(
      `setup/reports/fleet/net?${WEEK}&q=kdb+late&page=1&pageSize=25`,
    ),
  );
  expect(rawReads(api)).toHaveLength(2);
  expect(
    await screen.findByRole("row", { name: /KDB 100X/ }),
  ).toBeInTheDocument();
  expect(
    screen.queryByRole("row", { name: /KDA 482M/ }),
  ).not.toBeInTheDocument();
  const footer = screen.getByText("1 row").closest("tr")!;
  expect(
    within(footer)
      .getAllByRole("cell")
      .map((c) => c.textContent),
  ).toEqual(["1 row", "3,000", "5,000", "-2,000", "4", "", "", "", ""]);

  changeTo(screen.getByLabelText("Search"), "nothing like this");
  expect(await screen.findByText("Nothing to show.")).toBeInTheDocument();
});

it("says there is nothing to show for a report with no rows", async () => {
  renderPage(serveReports({ rows: [] }));
  expect(await screen.findByText("Nothing to show.")).toBeInTheDocument();
  expect(screen.queryByText(/0 rows/)).not.toBeInTheDocument();
});

it("hides Export from someone without reports.export", async () => {
  renderPage(serveReports({ access: { ...ACCESS, canExport: false } }));
  await screen.findByRole("row", { name: /KDA 482M/ });
  expect(
    screen.queryByRole("button", { name: "Export" }),
  ).not.toBeInTheDocument();
});

it("exports the report as shown, with the search, and offers the file under a name that says what it is", async () => {
  const api = renderPage();
  await screen.findByRole("row", { name: /KDA 482M/ });
  changeTo(screen.getByLabelText("Search"), " kdb ");
  await waitFor(() => expect(reads(api).at(-1)).toContain("q=kdb"));
  await screen.findByText("1 row");
  exportAs("Excel");

  await waitFor(() => expect(clicks).toHaveLength(1));
  expect(reads(api).at(-1)).toBe(
    `setup/reports/fleet/net/export?${WEEK}&q=kdb&format=xlsx`,
  );
  expect(clicks[0]).toEqual({
    download: "Net by vehicle 5-11 Oct 2026.xlsx",
    href: "blob:report",
  });
  const blob = vi.mocked(URL.createObjectURL).mock.calls[0][0];
  expect((blob as unknown as Blob).size).toBeGreaterThan(0);
});

it("exports a petty cash report for the chosen manager, and an undated one without a period", async () => {
  const api = renderPage();
  await screen.findByRole("row", { name: /KDA 482M/ });
  fireEvent.click(screen.getByRole("button", { name: "Petty cash" }));
  pick(await screen.findByLabelText("Manager"), "Grace Wanjiru");
  await waitFor(() => expect(reads(api).at(-1)).toContain("holderId=h1"));
  await screen.findByRole("row", { name: /KDA 482M/ });
  exportAs("Excel");
  await waitFor(() => expect(clicks).toHaveLength(1));
  expect(reads(api).at(-1)).toBe(
    `setup/reports/pettycash/cashBook/export?${WEEK}&holderId=h1&format=xlsx`,
  );
  expect(clicks[0].download).toBe("Cash book 5-11 Oct 2026.xlsx");

  pick(screen.getByLabelText("Report"), "Waiting for approval");
  await waitFor(() =>
    expect(reads(api).at(-1)).toBe(
      "setup/reports/pettycash/waiting?holderId=h1",
    ),
  );
  await screen.findByRole("row", { name: /KDA 482M/ });
  exportAs("Excel");
  await waitFor(() => expect(clicks).toHaveLength(2));
  expect(reads(api).at(-1)).toBe(
    "setup/reports/pettycash/waiting/export?holderId=h1&format=xlsx",
  );
  expect(clicks[1].download).toBe("Waiting for approval.xlsx");
});

it("shows why an export could not be made", async () => {
  const api = renderPage();
  await screen.findByRole("row", { name: /KDA 482M/ });
  api.on("setup/reports/fleet/net/export*", [
    400,
    { detail: "Too many rows to export." },
  ]);
  exportAs("Excel");
  expect(
    await screen.findByText("Too many rows to export."),
  ).toBeInTheDocument();
  expect(clicks).toEqual([]);
  expect(screen.getByRole("button", { name: "Export" })).toBeEnabled();
});

const manyVehicles = (count: number): Row[] =>
  Array.from({ length: count }, (_, index) => [
    `KDA ${String(index + 1).padStart(3, "0")}M`,
    1000,
    400,
    600,
    2,
    50,
    "2026-10-08",
    1,
    index % 2 ? "Late" : "On time",
  ]);

it("pages on the server, 25 to a page: the pager works from the page, size and total in the answer", async () => {
  const api = renderPage(serveReports({ rows: manyVehicles(120) }));
  await screen.findByText("KDA 001M");
  expect(rawReads(api)[0]).toBe(
    `setup/reports/fleet/net?${WEEK}&page=1&pageSize=25`,
  );
  expect(screen.getAllByText(/^KDA \d{3}M$/)).toHaveLength(25);
  expect(screen.getByText("Showing 1–25 of 120")).toBeInTheDocument();
  expect(screen.getByLabelText("Rows per page")).toHaveValue("25");
  const footer = () =>
    within(screen.getByText(/^\d+ rows$/).closest("tr")!)
      .getAllByRole("cell")
      .map((cell) => cell.textContent)
      .slice(0, 5);
  expect(footer()).toEqual(["120 rows", "120,000", "48,000", "72,000", "240"]);

  fireEvent.click(screen.getByRole("button", { name: "Next page" }));
  expect(await screen.findByText("Showing 26–50 of 120")).toBeInTheDocument();
  expect(rawReads(api).at(-1)).toBe(
    `setup/reports/fleet/net?${WEEK}&page=2&pageSize=25`,
  );
  expect(screen.getByText("KDA 026M")).toBeInTheDocument();
  expect(screen.queryByText("KDA 001M")).not.toBeInTheDocument();
  expect(footer()[1]).toBe("120,000");

  fireEvent.click(screen.getByRole("button", { name: "Page 3" }));
  expect(await screen.findByText("Showing 51–75 of 120")).toBeInTheDocument();
  expect(rawReads(api).at(-1)).toContain("page=3&pageSize=25");

  fireEvent.click(screen.getByRole("button", { name: "Last page" }));
  expect(await screen.findByText("Showing 101–120 of 120")).toBeInTheDocument();
  expect(screen.getAllByText(/^KDA \d{3}M$/)).toHaveLength(20);
});

it("goes back to page 1 when the search, the page size, the report, the period or the manager changes", async () => {
  const api = renderPage(serveReports({ rows: manyVehicles(120) }));
  await screen.findByText("KDA 001M");

  fireEvent.click(screen.getByRole("button", { name: "Page 3" }));
  await screen.findByText("Showing 51–75 of 120");
  changeTo(screen.getByLabelText("Search"), "late");
  await waitFor(() =>
    expect(rawReads(api).at(-1)).toContain("q=late&page=1&pageSize=25"),
  );
  expect(await screen.findByText("Showing 1–25 of 60")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Page 2" }));
  await screen.findByText("Showing 26–50 of 60");
  pick(screen.getByLabelText("Rows per page"), "50");
  await waitFor(() =>
    expect(rawReads(api).at(-1)).toContain("q=late&page=1&pageSize=50"),
  );
  expect(await screen.findByText("Showing 1–50 of 60")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Page 2" }));
  await screen.findByText("Showing 51–60 of 60");
  fireEvent.click(screen.getByRole("button", { name: "Previous week" }));
  await waitFor(() =>
    expect(rawReads(api).at(-1)).toContain("from=2026-09-28"),
  );
  expect(rawReads(api).at(-1)).toContain("page=1&pageSize=50");

  pick(screen.getByLabelText("Report"), "Revenue against target");
  await waitFor(() =>
    expect(rawReads(api).at(-1)).toContain("reports/fleet/target?"),
  );
  expect(rawReads(api).at(-1)).toContain("page=1&pageSize=50");

  fireEvent.click(screen.getByRole("button", { name: "Petty cash" }));
  pick(await screen.findByLabelText("Manager"), "Grace Wanjiru");
  await waitFor(() => expect(rawReads(api).at(-1)).toContain("holderId=h1"));
  expect(rawReads(api).at(-1)).toContain("page=1&pageSize=50");
});

it("exports every matching row, not the page that is shown", async () => {
  const api = renderPage(serveReports({ rows: manyVehicles(120) }));
  await screen.findByText("KDA 001M");
  fireEvent.click(screen.getByRole("button", { name: "Next page" }));
  await screen.findByText("Showing 26–50 of 120");
  changeTo(screen.getByLabelText("Search"), "late");
  await screen.findByText("Showing 1–25 of 60");
  exportAs("Excel");
  await waitFor(() => expect(clicks).toHaveLength(1));
  expect(rawReads(api).at(-1)).toBe(
    `setup/reports/fleet/net/export?${WEEK}&q=late&format=xlsx`,
  );
});

it("shows no pager for a short report", async () => {
  renderPage();
  await screen.findByRole("row", { name: /KDA 482M/ });
  expect(screen.queryByLabelText("Rows per page")).not.toBeInTheDocument();
});

it("shows a report that could not be loaded, and loads it again on request", async () => {
  const api = serveReports({
    failures: [[400, { detail: "That period is too long." }]],
  });
  renderPage(api);
  expect(
    await screen.findByText("That period is too long."),
  ).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Try again" }));
  expect(
    await screen.findByRole("row", { name: /KDA 482M/ }),
  ).toBeInTheDocument();
});

it("shows why the reports could not be listed, and lists them again on request", async () => {
  const api = serveReports();
  api.once("setup/reports", [403, {}]);
  renderPage(api);
  expect(
    await screen.findByText(
      "Your access does not include this. Ask your admin if you need it.",
    ),
  ).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Try again" }));
  expect(await screen.findByLabelText("Report")).toBeInTheDocument();
});

it("opens from the menu for reports.view", async () => {
  const api = serveReports();
  api.on("auth/session", [
    200,
    {
      userId: "me",
      firstName: "Test",
      lastName: "User",
      role: "Clerk",
      permissions: ["reports.view"],
    },
  ]);
  api.on("setup/appearance", [200, appearanceFixture(BUSINESS_DATE)]);
  render(<AppShell onSignOut={() => {}} />);
  const menu = within(await screen.findByRole("navigation", { name: "Main" }));
  fireEvent.click(await menu.findByRole("button", { name: "Reports" }));
  expect(
    await screen.findByRole("heading", { name: "Reports", level: 1 }),
  ).toBeInTheDocument();
  expect(
    await screen.findByRole("row", { name: /KDA 482M/ }),
  ).toBeInTheDocument();
});

it("offers Excel and PDF from the Export button, and asks for nothing until one is chosen", async () => {
  const api = renderPage();
  await screen.findByRole("row", { name: /KDA 482M/ });
  const before = rawReads(api).length;
  fireEvent.click(screen.getByRole("button", { name: "Export" }));
  const menu = screen.getByRole("menu", { name: "Export as" });
  expect(
    within(menu)
      .getAllByRole("menuitem")
      .map((item) => item.textContent),
  ).toEqual(["Excel", "PDF"]);
  expect(rawReads(api)).toHaveLength(before);
  fireEvent.keyDown(document, { key: "Escape" });
  expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Export" })).toHaveFocus();
});

it("exports a PDF with the same filters, and names the file .pdf", async () => {
  const api = renderPage();
  await screen.findByRole("row", { name: /KDA 482M/ });
  changeTo(screen.getByLabelText("Search"), "kdb");
  await screen.findByText("1 row");
  exportAs("PDF");
  await waitFor(() => expect(clicks).toHaveLength(1));
  expect(rawReads(api).at(-1)).toBe(
    `setup/reports/fleet/net/export?${WEEK}&q=kdb&format=pdf`,
  );
  expect(clicks[0].download).toBe("Net by vehicle 5-11 Oct 2026.pdf");
});

it("exports an Excel workbook and names the file .xlsx", async () => {
  const api = renderPage();
  await screen.findByRole("row", { name: /KDA 482M/ });
  exportAs("Excel");
  await waitFor(() => expect(clicks).toHaveLength(1));
  expect(rawReads(api).at(-1)).toBe(
    `setup/reports/fleet/net/export?${WEEK}&format=xlsx`,
  );
  expect(clicks[0].download).toBe("Net by vehicle 5-11 Oct 2026.xlsx");
});

it("searches the report by typing", async () => {
  const api = renderPage();
  await screen.findByRole("row", { name: /KDA 482M/ });
  const report = screen.getByLabelText("Report");
  fireEvent.focus(report);
  fireEvent.change(report, { target: { value: "against" } });
  fireEvent.keyDown(report, { key: "Enter" });
  await waitFor(() =>
    expect(rawReads(api).at(-1)).toContain("reports/fleet/target?"),
  );
});

it("shows amounts as numbers in the table and names the currency in the column headings", async () => {
  renderPage();
  const row = await screen.findByRole("row", { name: /KDB 100X/ });
  expect(within(row).queryByText(/KES/)).not.toBeInTheDocument();
  for (const name of ["Revenue (KES)", "Money out (KES)", "Net (KES)"])
    expect(screen.getByRole("columnheader", { name })).toBeInTheDocument();
  expect(
    screen.getByRole("columnheader", { name: "Days" }),
  ).toBeInTheDocument();
});
