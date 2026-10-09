import {
  act,
  fireEvent,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";

import { HistoryPage } from "../components/setup";
import { renderInApp } from "./renderInApp";

const change = (version: number, overrides: Record<string, unknown> = {}) => ({
  version,
  section: "companies",
  entityId: `company-${version}`,
  reason: `Change ${version}`,
  occurredAt: "2026-09-20T13:05:00Z",
  actorId: "me",
  actorName: "Test User",
  before: null,
  after: null,
  ...overrides,
});

// The table's own rows, not the before-and-after rows inside each change.
const changeRows = () =>
  screen
    .getByRole("table", { name: "" })
    .querySelectorAll(":scope > tbody > tr");
// Each before-and-after row as [field, before, after].
const fields = (table: ReturnType<typeof within>) =>
  table
    .getAllByRole("row")
    .slice(1)
    .map((row: HTMLElement) =>
      [...row.querySelectorAll("th, td")].map((cell) => cell.textContent),
    );

const pageOf = (
  items: ReturnType<typeof change>[],
  pageSize: number,
  total: number | null,
  hasMore: boolean,
) => ({
  items,
  pageNumber: 1,
  pageSize,
  total,
  hasMore,
  nextBefore: hasMore ? items[items.length - 1].version : null,
});

function serveHistory(total: number, rows?: ReturnType<typeof change>[]) {
  const fetchMock = vi.fn(async (input: string) => {
    const url = new URL(input, "http://app");
    const pageSize = Number(url.searchParams.get("pageSize"));
    const page = Number(url.searchParams.get("page") ?? 1);
    const all =
      rows ??
      Array.from({ length: total }, (_, index) => change(total - index));
    const items = all.slice((page - 1) * pageSize, page * pageSize);
    return new Response(
      JSON.stringify({
        ...pageOf(items, pageSize, all.length, false),
        pageNumber: page,
      }),
      { status: 200 },
    );
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

beforeEach(() => {
  serveHistory(0);
});

const FIRST = "/api/setup/history?includeTotal=true&page=1&pageSize=25";

it("asks for only the first page on first render, counted, and the next one on request", async () => {
  const fetchMock = serveHistory(60);
  renderInApp(<HistoryPage />);

  expect(
    await screen.findByText("PSV companies: Change 60"),
  ).toBeInTheDocument();
  expect(fetchMock.mock.calls.map(([input]) => input)).toEqual([FIRST]);
  expect(changeRows()).toHaveLength(25);
  expect(screen.getByText("Showing 1–25 of 60")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Next page" }));
  expect(
    await screen.findByText("PSV companies: Change 35"),
  ).toBeInTheDocument();
  expect(fetchMock).toHaveBeenLastCalledWith(
    "/api/setup/history?includeTotal=true&page=2&pageSize=25",
    expect.anything(),
  );
  expect(changeRows()).toHaveLength(25);
  expect(screen.getByText("Showing 26–50 of 60")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Page 3" }));
  expect(
    await screen.findByText("PSV companies: Change 1"),
  ).toBeInTheDocument();
  expect(changeRows()).toHaveLength(10);
  expect(screen.getByText("Showing 51–60 of 60")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Next page" })).toBeDisabled();
  expect(
    screen.queryByRole("button", { name: "Load more" }),
  ).not.toBeInTheDocument();
});

it("pages by number, not by the version of the last change it was given", async () => {
  const fetchMock = serveHistory(40);
  renderInApp(<HistoryPage />);
  await screen.findByText("Showing 1–25 of 40");
  fireEvent.click(screen.getByRole("button", { name: "Last page" }));
  await screen.findByText("Showing 26–40 of 40");
  expect(
    fetchMock.mock.calls.every(([input]) => !String(input).includes("before=")),
  ).toBe(true);
  expect(changeRows()).toHaveLength(15);
});

it("shows each change field by field, with the before and after values side by side", async () => {
  serveHistory(5, [
    change(4, {
      before: JSON.stringify({
        Name: "North Star",
        VehicleCount: 2,
        Active: true,
      }),
      after: JSON.stringify({
        Name: "North Star Sacco",
        VehicleCount: 2,
        Active: true,
      }),
    }),
    change(3, {
      reason: "Added Metro",
      before: "null",
      after: JSON.stringify({ Name: "Metro", Active: true, ArchivedOn: null }),
    }),
    change(2, {
      section: "recurring",
      reason: "Raised the loan",
      before: JSON.stringify({
        StoppedFrom: null,
        Versions: [{ Amount: 1000, Start: "2026-09-01" }],
      }),
      after: JSON.stringify({
        StoppedFrom: null,
        Versions: [
          { Amount: 1000, Start: "2026-09-01" },
          { Amount: 1200, Start: "2026-09-21" },
        ],
      }),
    }),
    change(1, {
      section: "logo",
      reason: "New logo",
      before: "old-logo.png",
      after: "new-logo.png",
    }),
    change(0, {
      section: "investment",
      reason: "Removed the deposit",
      before: JSON.stringify({ Description: "Deposit", Amount: 5000 }),
      after: "null",
    }),
  ]);
  renderInApp(<HistoryPage />);

  const renamed = within(
    await screen.findByRole("table", {
      name: "PSV companies: Change 4, before and after",
    }),
  );
  expect(
    renamed.getAllByRole("columnheader").map((cell) => cell.textContent),
  ).toEqual(["Field", "Before", "After"]);
  expect(fields(renamed)).toEqual([["Name", "North Star", "North Star Sacco"]]);

  const created = within(
    screen.getByRole("table", {
      name: "PSV companies: Added Metro, before and after",
    }),
  );
  expect(fields(created)).toEqual([
    ["Name", "—", "Metro"],
    ["Active", "—", "Yes"],
    ["Archived on", "—", "None"],
  ]);

  const revised = within(
    screen.getByRole("table", {
      name: "Scheduled expenses and savings: Raised the loan, before and after",
    }),
  );
  expect(fields(revised)).toEqual([
    ["Versions 2 › Amount", "—", "1200"],
    ["Versions 2 › Start", "—", "21 Sep 2026"],
  ]);

  // Removed: every field it had, and nothing after.
  expect(
    fields(
      within(
        screen.getByRole("table", {
          name: "Investment: Removed the deposit, before and after",
        }),
      ),
    ),
  ).toEqual([
    ["Description", "Deposit", "—"],
    ["Amount", "5000", "—"],
  ]);

  // Not JSON: the saved values are shown as they are.
  const raw = within(
    screen.getByRole("table", { name: "Logo: New logo, before and after" }),
  );
  expect(fields(raw)).toEqual([
    ["Saved value", "old-logo.png", "new-logo.png"],
  ]);
});

it("says why when another page cannot be loaded, and loads it again on request", async () => {
  let calls = 0;
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => {
      calls += 1;
      if (calls === 2)
        return new Response(
          JSON.stringify({
            title: "Not permitted in this organization or data scope.",
            detail: "Your access to the change log was removed.",
          }),
          { status: 403 },
        );
      return new Response(
        JSON.stringify(
          pageOf(
            Array.from({ length: 25 }, (_, index) => change(30 - index)),
            25,
            30,
            false,
          ),
        ),
        { status: 200 },
      );
    }),
  );
  renderInApp(<HistoryPage />);

  fireEvent.click(await screen.findByRole("button", { name: "Next page" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Your access to the change log was removed.",
  );
  fireEvent.click(screen.getByRole("button", { name: "Page 1" }));
  await waitFor(() => expect(changeRows()).toHaveLength(25));
});

it("leaves out internal ids and shows a list of plain values as one field", async () => {
  serveHistory(1, [
    change(1, {
      section: "people",
      reason: "Changed role for Grace Achieng",
      before: JSON.stringify({
        Id: "p-1",
        Role: "Revenue clerk",
        CompanyIds: ["c-1"],
        Permissions: ["revenue.view", "dash.capture"],
        Versions: [{ VehicleId: "v-1" }],
      }),
      after: JSON.stringify({
        Id: "p-1",
        Role: "Fleet manager",
        CompanyIds: ["c-2"],
        Permissions: ["dash.capture", "revenue.view", "revenue.correct"],
        Versions: [{ VehicleId: "v-2" }],
        UpdatedBy: "10c5de87-afae-417b-98a2-ce4d4f6b8eca",
        Version: 2,
      }),
    }),
  ]);
  renderInApp(<HistoryPage />);

  const changed = within(
    await screen.findByRole("table", {
      name: "People and access: Changed role for Grace Achieng, before and after",
    }),
  );
  expect(fields(changed)).toEqual([
    ["Role", "Revenue clerk", "Fleet manager"],
    [
      "Permissions",
      "dash.capture, revenue.view",
      "dash.capture, revenue.correct, revenue.view",
    ],
  ]);
});

// The server does the narrowing, so the filter bar's job is to ask for exactly what the controls say.
function serveFiltered(rows: ReturnType<typeof change>[]) {
  const fetchMock = vi.fn(async (input: string) => {
    const url = new URL(input, "http://app");
    const [section, text, from, to] = ["section", "text", "from", "to"].map(
      (name) => url.searchParams.get(name),
    );
    const matches = rows.filter(
      (row) =>
        (!section || row.section === section) &&
        (!text ||
          `${row.reason} ${row.actorName}`
            .toLowerCase()
            .includes(text.toLowerCase())) &&
        (!from || row.occurredAt >= from) &&
        (!to || row.occurredAt <= `${to}T23:59:59Z`),
    );
    return new Response(
      JSON.stringify(pageOf(matches, 25, matches.length, false)),
      { status: 200 },
    );
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

it("narrows the log through the server and starts again at the first page", async () => {
  const rows = [
    change(3, {
      section: "vehicles",
      reason: "Added vehicle KDA 123A",
      occurredAt: "2026-09-22T08:00:00Z",
    }),
    change(2, {
      section: "people",
      reason: "Invited someone",
      actorName: "Antony Maina",
      occurredAt: "2026-09-21T08:00:00Z",
    }),
    change(1, {
      section: "companies",
      reason: "Renamed Metro Trans",
      occurredAt: "2026-09-20T08:00:00Z",
    }),
  ];
  const fetchMock = serveFiltered(rows);
  renderInApp(<HistoryPage />);
  expect(
    await screen.findByText("Vehicles: Added vehicle KDA 123A"),
  ).toBeInTheDocument();
  expect(changeRows()).toHaveLength(3);

  fireEvent.change(screen.getByLabelText("Section"), {
    target: { value: "people" },
  });
  await waitFor(() =>
    expect(fetchMock).toHaveBeenLastCalledWith(
      "/api/setup/history?includeTotal=true&section=people&page=1&pageSize=25",
      expect.anything(),
    ),
  );
  expect(
    await screen.findByText("People and access: Invited someone"),
  ).toBeInTheDocument();
  expect(
    screen.queryByText("Vehicles: Added vehicle KDA 123A"),
  ).not.toBeInTheDocument();
  expect(changeRows()).toHaveLength(1);

  // The search box settles before it asks: three keystrokes are one request, and it looks at the name too.
  fireEvent.change(screen.getByLabelText("Section"), {
    target: { value: "all" },
  });
  await waitFor(() => expect(changeRows()).toHaveLength(3));
  const asked = fetchMock.mock.calls.length;
  for (const typed of ["a", "an", "antony"])
    fireEvent.change(screen.getByLabelText("Search"), {
      target: { value: typed },
    });
  await waitFor(() =>
    expect(fetchMock).toHaveBeenLastCalledWith(
      "/api/setup/history?includeTotal=true&text=antony&page=1&pageSize=25",
      expect.anything(),
    ),
  );
  expect(fetchMock.mock.calls.length - asked).toBe(1);
  expect(
    await screen.findByText("People and access: Invited someone"),
  ).toBeInTheDocument();

  // A date range is sent as the two days it names, both included.
  fireEvent.change(screen.getByLabelText("Search"), { target: { value: "" } });
  fireEvent.change(screen.getByLabelText("From"), {
    target: { value: "2026-09-21" },
  });
  fireEvent.change(screen.getByLabelText("To"), {
    target: { value: "2026-09-21" },
  });
  await waitFor(() =>
    expect(fetchMock).toHaveBeenLastCalledWith(
      "/api/setup/history?includeTotal=true&from=2026-09-21&to=2026-09-21&page=1&pageSize=25",
      expect.anything(),
    ),
  );
  expect(
    await screen.findByText("People and access: Invited someone"),
  ).toBeInTheDocument();
  expect(
    screen.queryByText("PSV companies: Renamed Metro Trans"),
  ).not.toBeInTheDocument();
  // The range cannot be set backwards: each input stops where the other one is.
  expect(screen.getByLabelText("From")).toHaveAttribute("max", "2026-09-21");
  expect(screen.getByLabelText("To")).toHaveAttribute("min", "2026-09-21");

  fireEvent.click(screen.getByRole("button", { name: "Clear" }));
  await waitFor(() => expect(changeRows()).toHaveLength(3));
  await waitFor(() => expect(changeRows()).toHaveLength(3));
});

it("names the Central expenses and Reports sections of the change log", async () => {
  serveHistory(2, [
    change(2, { section: "centralexpenses", reason: "Removed an expense" }),
    change(1, { section: "reports", reason: "Exported a report" }),
  ]);
  renderInApp(<HistoryPage />);
  expect(
    await screen.findByText("Central expenses: Removed an expense"),
  ).toBeInTheDocument();
  expect(screen.getByText("Reports: Exported a report")).toBeInTheDocument();
});

it("keeps the newer filter's answer when an older request finishes last", async () => {
  const rows = [
    change(2, { section: "people", reason: "Invited someone" }),
    change(1, { section: "companies", reason: "Renamed Metro Trans" }),
  ];
  let release = () => {};
  const held = new Promise<void>((resolve) => (release = resolve));
  let oldAnswered = false;
  const fetchMock = vi.fn(async (input: string) => {
    const section = new URL(input, "http://app").searchParams.get("section");
    const items = section
      ? rows.filter((row) => row.section === section)
      : rows;
    if (!section) {
      await held;
      oldAnswered = true;
    }
    return new Response(
      JSON.stringify(pageOf(items, 25, items.length, false)),
      { status: 200 },
    );
  });
  vi.stubGlobal("fetch", fetchMock);
  renderInApp(<HistoryPage />);

  fireEvent.change(screen.getByLabelText("Section"), {
    target: { value: "people" },
  });
  expect(
    await screen.findByText("People and access: Invited someone"),
  ).toBeInTheDocument();

  await act(async () => {
    release();
    await new Promise((resolve) => setTimeout(resolve, 50));
  });
  expect(oldAnswered).toBe(true);
  expect(
    screen.getByText("People and access: Invited someone"),
  ).toBeInTheDocument();
  expect(changeRows()).toHaveLength(1);
  expect(
    screen.queryByText("PSV companies: Renamed Metro Trans"),
  ).not.toBeInTheDocument();
});

it("says that nothing matches rather than that there is nothing", async () => {
  serveFiltered([
    change(1, { section: "companies", reason: "Renamed Metro Trans" }),
  ]);
  renderInApp(<HistoryPage />);
  expect(
    await screen.findByText("PSV companies: Renamed Metro Trans"),
  ).toBeInTheDocument();

  fireEvent.change(screen.getByLabelText("Section"), {
    target: { value: "revenue" },
  });
  expect(
    await screen.findByText("No changes match this filter."),
  ).toBeInTheDocument();
});
