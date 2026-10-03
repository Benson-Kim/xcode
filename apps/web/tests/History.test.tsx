import { fireEvent, screen, waitFor, within } from "@testing-library/react";
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
const changeRows = () => screen.getByRole("table", { name: "" }).querySelectorAll(":scope > tbody > tr");
// Each before-and-after row as [field, before, after].
const fields = (table: ReturnType<typeof within>) =>
  table.getAllByRole("row").slice(1).map((row: HTMLElement) => [...row.querySelectorAll("th, td")].map((cell) => cell.textContent));

function serveHistory(total: number, rows?: ReturnType<typeof change>[]) {
  const fetchMock = vi.fn(async (input: string) => {
    const url = new URL(input, "http://app");
    const page = Number(url.searchParams.get("page"));
    const pageSize = Number(url.searchParams.get("pageSize"));
    const all = rows ?? Array.from({ length: total }, (_, index) => change(total - index));
    return new Response(JSON.stringify({ items: all.slice((page - 1) * pageSize, page * pageSize), pageNumber: page, pageSize, total: all.length }), { status: 200 });
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

beforeEach(() => {
  serveHistory(0);
});

it("asks for only the first page on first render and the next one on Load more", async () => {
  const fetchMock = serveHistory(60);
  renderInApp(<HistoryPage />);

  expect(await screen.findByText("PSV companies: Change 60")).toBeInTheDocument();
  expect(fetchMock.mock.calls.map(([input]) => input)).toEqual(["/api/setup/history?page=1&pageSize=25"]);
  expect(changeRows()).toHaveLength(25);
  expect(screen.getByText("Showing 25 of 60 changes")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Load more" }));
  expect(await screen.findByText("PSV companies: Change 11")).toBeInTheDocument();
  expect(fetchMock).toHaveBeenLastCalledWith("/api/setup/history?page=2&pageSize=25", expect.anything());
  expect(changeRows()).toHaveLength(50);

  fireEvent.click(screen.getByRole("button", { name: "Load more" }));
  expect(await screen.findByText("PSV companies: Change 1")).toBeInTheDocument();
  expect(changeRows()).toHaveLength(60);
  expect(fetchMock).toHaveBeenCalledTimes(3);
  expect(screen.queryByRole("button", { name: "Load more" })).not.toBeInTheDocument();
  expect(screen.getByText("Showing all 60 changes")).toBeInTheDocument();
});

it("shows each change field by field, with the before and after values side by side", async () => {
  serveHistory(5, [
    change(4, {
      before: JSON.stringify({ Name: "North Star", VehicleCount: 2, Active: true }),
      after: JSON.stringify({ Name: "North Star Sacco", VehicleCount: 2, Active: true }),
    }),
    change(3, { reason: "Added Metro", before: "null", after: JSON.stringify({ Name: "Metro", Active: true, ArchivedOn: null }) }),
    change(2, {
      section: "recurring",
      reason: "Raised the loan",
      before: JSON.stringify({ StoppedFrom: null, Versions: [{ Amount: 1000, Start: "2026-09-01" }] }),
      after: JSON.stringify({ StoppedFrom: null, Versions: [{ Amount: 1000, Start: "2026-09-01" }, { Amount: 1200, Start: "2026-09-21" }] }),
    }),
    change(1, { section: "logo", reason: "New logo", before: "old-logo.png", after: "new-logo.png" }),
    change(0, { section: "investment", reason: "Removed the deposit", before: JSON.stringify({ Description: "Deposit", Amount: 5000 }), after: "null" }),
  ]);
  renderInApp(<HistoryPage />);

  const renamed = within(await screen.findByRole("table", { name: "PSV companies: Change 4, before and after" }));
  expect(renamed.getAllByRole("columnheader").map((cell) => cell.textContent)).toEqual(["Field", "Before", "After"]);
  expect(fields(renamed)).toEqual([
    ["Name", "North Star", "North Star Sacco"],
  ]);

  const created = within(screen.getByRole("table", { name: "PSV companies: Added Metro, before and after" }));
  expect(fields(created)).toEqual([
    ["Name", "—", "Metro"],
    ["Active", "—", "Yes"],
    ["Archived on", "—", "None"],
  ]);

  const revised = within(screen.getByRole("table", { name: "Scheduled expenses and savings: Raised the loan, before and after" }));
  expect(fields(revised)).toEqual([
    ["Versions 2 › Amount", "—", "1200"],
    ["Versions 2 › Start", "—", "21 Sep 2026"],
  ]);

  // Removed: every field it had, and nothing after.
  expect(fields(within(screen.getByRole("table", { name: "Investment: Removed the deposit, before and after" })))).toEqual([
    ["Description", "Deposit", "—"],
    ["Amount", "5000", "—"],
  ]);

  // Not JSON: the saved values are shown as they are.
  const raw = within(screen.getByRole("table", { name: "Logo: New logo, before and after" }));
  expect(fields(raw)).toEqual([
    ["Saved value", "old-logo.png", "new-logo.png"],
  ]);
});

it("keeps the rows it has and says why when the next page fails", async () => {
  let calls = 0;
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => {
      calls += 1;
      if (calls > 1) return new Response(JSON.stringify({ title: "Not permitted in this organization or data scope.", detail: "Your access to the change log was removed." }), { status: 403 });
      return new Response(JSON.stringify({ items: Array.from({ length: 25 }, (_, index) => change(30 - index)), pageNumber: 1, pageSize: 25, total: 30 }), { status: 200 });
    }),
  );
  renderInApp(<HistoryPage />);

  fireEvent.click(await screen.findByRole("button", { name: "Load more" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Your access to the change log was removed.");
  await waitFor(() => expect(changeRows()).toHaveLength(25));
  expect(screen.getByRole("button", { name: "Load more" })).toBeEnabled();
});

it("leaves out internal ids and shows a list of plain values as one field", async () => {
  serveHistory(1, [
    change(1, {
      section: "people",
      reason: "Changed role for Grace Achieng",
      before: JSON.stringify({ Id: "p-1", Role: "Revenue clerk", CompanyIds: ["c-1"], Permissions: ["revenue.view", "dash.capture"], Versions: [{ VehicleId: "v-1" }] }),
      after: JSON.stringify({
        Id: "p-1", Role: "Fleet manager", CompanyIds: ["c-2"], Permissions: ["dash.capture", "revenue.view", "revenue.correct"], Versions: [{ VehicleId: "v-2" }],
        UpdatedBy: "10c5de87-afae-417b-98a2-ce4d4f6b8eca", Version: 2,
      }),
    }),
  ]);
  renderInApp(<HistoryPage />);

  const changed = within(await screen.findByRole("table", { name: "People and access: Changed role for Grace Achieng, before and after" }));
  expect(fields(changed)).toEqual([
    ["Role", "Revenue clerk", "Fleet manager"],
    ["Permissions", "dash.capture, revenue.view", "dash.capture, revenue.correct, revenue.view"],
  ]);
});
