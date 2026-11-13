import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { beforeAll, expect, it, vi } from "vitest";

import { AppShell } from "../components/AppShell";
import { CentralExpensesPage } from "../components/expenses/CentralExpensesPage";
import {
  BUSINESS_DATE,
  ledgerReads,
  manyRows,
  OPTIONS,
  permissionsOf,
  serveExpenses,
} from "./expensesServer";
import {
  overviewOf,
  permissionsOf as pettyPermissions,
} from "./pettyCashServer";
import { appearanceFixture, renderInApp } from "./renderInApp";
import { choose, offered, optionsOf, pick } from "./searchSelect";

// The shell loads Petty cash lazily; a cold first import can outlast findBy's one-second wait.
beforeAll(() => import("../components/pettycash/PettyCashPage"));

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const WEEK = "from=2026-10-05&to=2026-10-11";

function renderPage(
  api = serveExpenses(),
  permissions: string[] = ["expenses.view", "expenses.capture"],
) {
  const onOpenPettyCash = vi.fn();
  renderInApp(
    <CentralExpensesPage onOpenPettyCash={onOpenPettyCash} />,
    { permissions },
    { businessDate: BUSINESS_DATE },
  );
  return { api, onOpenPettyCash };
}

const changeTo = (element: HTMLElement, value: string) =>
  fireEvent.change(element, { target: { value } });

async function openRecord() {
  fireEvent.click(
    await screen.findByRole("button", { name: "Record expense" }),
  );
  const dialog = await screen.findByRole("dialog", { name: "Record expense" });
  await offered(
    within(dialog).getByLabelText("Vehicle"),
    "KDA 482M, Rongai Express",
  );
  return dialog;
}

function fillPurchase(dialog: HTMLElement, units: string, cost: string) {
  pick(within(dialog).getByLabelText("Item"), "Tyres");
  changeTo(within(dialog).getByLabelText("Qty"), units);
  changeTo(within(dialog).getByLabelText("Unit cost, KES"), cost);
}

const save = (dialog: HTMLElement, name = "Save") =>
  within(dialog).getByRole("button", { name });

it("shows the period's four figures and its rows, with the totals of everything matching in the footer", async () => {
  const { api } = renderPage();

  const figures = await screen.findByRole("group", { name: "Period figures" });
  const figure = (label: string) =>
    within(figures).getByText(label).nextSibling;
  expect(figure("Total")).toHaveTextContent("KES 18,000");
  expect(figure("Central")).toHaveTextContent(/^16,500$/);
  expect(figure("Petty cash")).toHaveTextContent(/^300$/);
  expect(figure("Scheduled")).toHaveTextContent(/^1,200$/);

  const tyres = await screen.findByRole("row", { name: /Tyres/ });
  expect(within(tyres).getByText("7 Oct 2026")).toBeInTheDocument();
  expect(within(tyres).queryByText("Garage and repairs")).toBeNull();
  expect(within(tyres).getByText("Front pair")).toBeInTheDocument();
  expect(within(tyres).getByText("Central")).toBeInTheDocument();
  expect(within(tyres).getByText("Brian Mwangi")).toBeInTheDocument();
  expect(within(tyres).getByText("3,500")).toBeInTheDocument();
  expect(within(tyres).getByText("14,000")).toBeInTheDocument();
  expect(within(tyres).queryByText(/KES/)).not.toBeInTheDocument();

  const diesel = screen.getByRole("row", { name: /Diesel/ });
  expect(
    within(diesel).getByText("Shared by 3 vehicles, KES 7,500 in all"),
  ).toBeInTheDocument();
  const parking = screen.getByRole("row", { name: /Parking/ });
  expect(
    within(parking).getByText("Grace Wanjiru's float"),
  ).toBeInTheDocument();
  const insurance = screen.getByRole("row", { name: /Insurance/ });
  expect(within(insurance).getByText("Standing order")).toBeInTheDocument();
  const tag = within(insurance).getByText("Scheduled");
  expect(tag).toHaveClass("chip", "mute");
  expect(tag.className).not.toContain("before:");

  expect(screen.getByText("4 expenses")).toBeInTheDocument();
  expect(screen.getByRole("row", { name: /4 expenses/ })).toHaveTextContent(
    /18,000$/,
  );
  expect(
    screen.getByRole("columnheader", { name: "Total amount" }),
  ).toBeInTheDocument();
  expect(
    screen.getByRole("columnheader", { name: "Unit cost" }),
  ).toBeInTheDocument();
  expect(ledgerReads(api)[0]).toBe(
    `setup/expenses/ledger?${WEEK}&page=1&pageSize=25`,
  );
  expect(screen.getByText("5 to 11 Oct 2026")).toBeInTheDocument();
});

it("asks again for the source, the search and the period that are chosen", async () => {
  const { api } = renderPage();
  await screen.findByRole("row", { name: /Tyres/ });

  choose(screen.getByLabelText("Source"), "Petty cash");
  await screen.findByRole("row", { name: /Parking/ });
  expect(screen.queryByRole("row", { name: /Tyres/ })).not.toBeInTheDocument();
  expect(ledgerReads(api).at(-1)).toContain(`${WEEK}&source=pettycash`);
  expect(screen.getByText("1 expense")).toBeInTheDocument();
  const figures = screen.getByRole("group", { name: "Period figures" });
  expect(within(figures).getByText("Total").nextSibling).toHaveTextContent(
    "KES 18,000",
  );

  choose(screen.getByLabelText("Source"), "All sources");
  changeTo(screen.getByLabelText("Search"), "diesel");
  await waitFor(() => expect(ledgerReads(api).at(-1)).toContain("q=diesel"));
  await waitFor(() =>
    expect(
      screen.queryByRole("row", { name: /Tyres/ }),
    ).not.toBeInTheDocument(),
  );
  expect(screen.getByRole("row", { name: /Diesel/ })).toBeInTheDocument();

  changeTo(screen.getByLabelText("Search"), "");
  fireEvent.click(screen.getByRole("button", { name: "Previous week" }));
  await waitFor(() =>
    expect(ledgerReads(api).at(-1)).toContain("from=2026-09-28&to=2026-10-04"),
  );
  expect(
    await screen.findByText("No expenses in this period."),
  ).toBeInTheDocument();
  expect(screen.getByText("28 Sep to 4 Oct 2026")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: /^Period, / }));
  fireEvent.click(screen.getByRole("menuitemradio", { name: "Last month" }));
  await waitFor(() =>
    expect(ledgerReads(api).at(-1)).toContain("from=2026-09-01&to=2026-09-30"),
  );
});

it("says nothing matches when a filter leaves no rows", async () => {
  renderPage();
  await screen.findByRole("row", { name: /Tyres/ });
  changeTo(screen.getByLabelText("Search"), "zzz");
  expect(await screen.findByText("Nothing matches.")).toBeInTheDocument();
});

it("shows the server's reason when the ledger cannot be loaded, and loads again on request", async () => {
  const api = serveExpenses({
    failures: [[400, { detail: "The period is too long." }]],
  });
  renderPage(api);
  expect(
    await screen.findByText("The period is too long."),
  ).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Try again" }));
  expect(await screen.findByRole("row", { name: /Tyres/ })).toBeInTheDocument();
});

it("offers Record expense only to someone who may record", async () => {
  const { api } = renderPage(
    serveExpenses({ permissions: permissionsOf({ canRecord: false }) }),
  );
  await screen.findByRole("row", { name: /Tyres/ });
  expect(
    screen.queryByRole("button", { name: "Record expense" }),
  ).not.toBeInTheDocument();
  expect(api.unhandled).toEqual([]);
});

it("records one expense on one vehicle with a fresh id and the whole total", async () => {
  const { api } = renderPage();
  const dialog = await openRecord();
  expect(save(dialog)).toBeDisabled();
  // The date comes first and opens on today: no day after it.
  expect(
    within(dialog).getByRole("button", { name: "Next day" }),
  ).toBeDisabled();

  fillPurchase(dialog, "4", "3500");
  expect(within(dialog).getByText("KES 14,000")).toBeInTheDocument();
  expect(save(dialog)).toBeDisabled();
  pick(within(dialog).getByLabelText("Vehicle"), /^KDA 482M/);
  expect(within(dialog).queryByLabelText("Note")).not.toBeInTheDocument();
  expect(save(dialog)).toBeEnabled();
  const before = ledgerReads(api).length;
  fireEvent.click(save(dialog));

  expect(
    await screen.findByText("KES 14,000 recorded on KDA 482M."),
  ).toBeInTheDocument();
  expect(api.sent("POST setup/expenses/entries")).toEqual([
    {
      id: expect.stringMatching(UUID),
      date: BUSINESS_DATE,
      expenseItemId: "i1",
      units: 4,
      unitAmount: 3500,
      note: null,
      allocations: [{ vehicleId: "v1", amount: 14000 }],
    },
  ]);
  await waitFor(() => expect(ledgerReads(api).length).toBeGreaterThan(before));
  expect(
    screen.queryByRole("dialog", { name: "Record expense" }),
  ).not.toBeInTheDocument();
});

it("takes part of a unit and refuses units or a cost that cannot be", async () => {
  const { api } = renderPage();
  const dialog = await openRecord();
  fillPurchase(dialog, "11.875", "182.40");
  expect(within(dialog).getByText("KES 2,166")).toBeInTheDocument();
  expect(within(dialog).getByLabelText("Qty")).toHaveAttribute(
    "inputmode",
    "decimal",
  );
  pick(within(dialog).getByLabelText("Vehicle"), /^KDA 482M/);
  expect(save(dialog)).toBeEnabled();

  changeTo(within(dialog).getByLabelText("Qty"), "1.2345");
  expect(
    within(dialog).getByText(
      "Enter units above zero, with at most three decimals.",
    ),
  ).toBeInTheDocument();
  expect(save(dialog)).toBeDisabled();
  changeTo(within(dialog).getByLabelText("Qty"), "2");
  changeTo(within(dialog).getByLabelText("Unit cost, KES"), "12.345");
  expect(save(dialog)).toBeDisabled();
  changeTo(within(dialog).getByLabelText("Unit cost, KES"), "10");
  // The date never goes past today: the control has no day after it.
  expect(
    within(dialog).getByRole("button", { name: "Next day" }),
  ).toBeDisabled();
  fireEvent.click(within(dialog).getByRole("button", { name: "Previous day" }));
  expect(
    within(dialog).getByRole("button", { name: "Next day" }),
  ).toBeEnabled();
  expect(api.sent("POST setup/expenses/entries")).toEqual([]);
});

it("splits a purchase across three vehicles, saying what is left, over, doubled or balanced", async () => {
  const { api } = renderPage();
  const dialog = await openRecord();
  fillPurchase(dialog, "1", "100");
  fireEvent.click(
    within(dialog).getByRole("button", { name: "Split across vehicles" }),
  );
  fireEvent.click(within(dialog).getByRole("button", { name: "Add vehicle" }));
  expect(within(dialog).queryByLabelText("Vehicle")).not.toBeInTheDocument();
  expect(save(dialog, "Save 3 entries")).toBeDisabled();
  expect(
    within(dialog).getByText("KES 100 left to allocate"),
  ).toBeInTheDocument();

  pick(within(dialog).getByLabelText("Vehicle 1"), /^KDA 482M/);
  pick(within(dialog).getByLabelText("Vehicle 2"), /^KDB 100X/);
  pick(within(dialog).getByLabelText("Vehicle 3"), /^KDC 200Y/);
  fireEvent.click(
    within(dialog).getByRole("button", { name: "Split equally" }),
  );
  expect(within(dialog).getByLabelText("Amount for vehicle 1")).toHaveValue(
    "33.34",
  );
  expect(within(dialog).getByLabelText("Amount for vehicle 2")).toHaveValue(
    "33.33",
  );
  expect(within(dialog).getByLabelText("Amount for vehicle 3")).toHaveValue(
    "33.33",
  );
  expect(
    within(dialog).getByText("Balanced, KES 100 across 3 vehicles"),
  ).toBeInTheDocument();
  expect(save(dialog, "Save 3 entries")).toBeEnabled();

  changeTo(within(dialog).getByLabelText("Amount for vehicle 1"), "40");
  expect(
    within(dialog).getByText("KES 6.66 over the total"),
  ).toBeInTheDocument();
  expect(save(dialog, "Save 3 entries")).toBeDisabled();
  changeTo(within(dialog).getByLabelText("Amount for vehicle 1"), "30");
  expect(
    within(dialog).getByText("KES 3.34 left to allocate"),
  ).toBeInTheDocument();
  changeTo(within(dialog).getByLabelText("Amount for vehicle 1"), "33.34");

  pick(within(dialog).getByLabelText("Vehicle 2"), /^KDA 482M/);
  expect(
    within(dialog).getByText("The same vehicle is picked twice"),
  ).toBeInTheDocument();
  expect(save(dialog, "Save 3 entries")).toBeDisabled();
  pick(within(dialog).getByLabelText("Vehicle 2"), /^KDB 100X/);

  fireEvent.click(save(dialog, "Save 3 entries"));
  expect(
    await screen.findByText("KES 100 recorded across 3 vehicles."),
  ).toBeInTheDocument();
  expect(api.sent("POST setup/expenses/entries")[0]).toMatchObject({
    expenseItemId: "i1",
    units: 1,
    unitAmount: 100,
    allocations: [
      { vehicleId: "v1", amount: 33.34 },
      { vehicleId: "v2", amount: 33.33 },
      { vehicleId: "v3", amount: 33.33 },
    ],
  });
});

it("goes back to one vehicle when only one row is left", async () => {
  renderPage();
  const dialog = await openRecord();
  pick(within(dialog).getByLabelText("Vehicle"), /^KDB 100X/);
  fireEvent.click(
    within(dialog).getByRole("button", { name: "Split across vehicles" }),
  );
  expect(within(dialog).getByLabelText("Vehicle 1")).toHaveValue(
    "KDB 100X, Rongai Express",
  );
  fireEvent.click(
    within(dialog).getByRole("button", { name: "Remove vehicle 2" }),
  );
  expect(within(dialog).getByLabelText("Vehicle")).toHaveValue(
    "KDB 100X, Rongai Express",
  );
  expect(within(dialog).queryByLabelText("Vehicle 1")).not.toBeInTheDocument();
  expect(save(dialog)).toBeInTheDocument();
});

it("keeps one id for a save that is tried again after it failed", async () => {
  const { api } = renderPage();
  api.once("POST setup/expenses/entries", [503, {}]);
  const dialog = await openRecord();
  fillPurchase(dialog, "2", "50");
  pick(within(dialog).getByLabelText("Vehicle"), /^KDA 482M/);
  fireEvent.click(save(dialog));
  expect(
    await within(dialog).findByText("The request could not be completed."),
  ).toBeInTheDocument();
  await waitFor(() => expect(save(dialog)).toBeEnabled());
  fireEvent.click(save(dialog));
  await screen.findByText("KES 100 recorded on KDA 482M.");

  const [first, second] = api.sent("POST setup/expenses/entries");
  expect(first.id).toMatch(UUID);
  expect(second.id).toBe(first.id);
});

it("opens a central row for change with its values, and sends the version it was read at", async () => {
  const { api } = renderPage();
  fireEvent.click(
    await screen.findByRole("button", {
      name: "Edit KDA 482M, Tyres, KES 14,000",
    }),
  );
  const dialog = await screen.findByRole("dialog", { name: "Edit expense" });
  await waitFor(() =>
    expect(within(dialog).getByLabelText("Item")).toHaveValue("Tyres"),
  );
  expect(within(dialog).getByLabelText("Qty")).toHaveValue("4");
  expect(within(dialog).getByLabelText("Unit cost, KES")).toHaveValue("3500");
  expect(within(dialog).getByText("Wed 7 Oct 2026")).toBeInTheDocument();
  expect(within(dialog).getByLabelText("Vehicle")).toHaveValue(
    "KDA 482M, Rongai Express",
  );
  expect(
    within(dialog).queryByRole("button", { name: "Split across vehicles" }),
  ).not.toBeInTheDocument();
  expect(
    within(dialog).queryByText(/takes it out of that purchase/),
  ).not.toBeInTheDocument();

  changeTo(within(dialog).getByLabelText("Unit cost, KES"), "3600");
  expect(within(dialog).getByText("KES 14,400")).toBeInTheDocument();
  fireEvent.click(save(dialog));
  expect(await screen.findByText("Saved.")).toBeInTheDocument();
  expect(api.sent("PUT setup/expenses/entries/r1")).toEqual([
    {
      date: "2026-10-07",
      vehicleId: "v1",
      expenseItemId: "i1",
      units: 4,
      unitAmount: 3600,
      note: null,
      version: 3,
    },
  ]);
});

it("explains a conflict on the page, closes the form and loads the ledger again", async () => {
  const { api } = renderPage();
  const message =
    "Someone else changed this expense first. Check it and try again.";
  api.once("PUT setup/expenses/entries/r1", [409, { detail: message }]);
  fireEvent.click(
    await screen.findByRole("button", {
      name: "Edit KDA 482M, Tyres, KES 14,000",
    }),
  );
  const dialog = await screen.findByRole("dialog", { name: "Edit expense" });
  await waitFor(() =>
    expect(within(dialog).getByLabelText("Item")).toHaveValue("Tyres"),
  );
  const before = ledgerReads(api).length;
  fireEvent.click(save(dialog));

  expect(await screen.findByText(message)).toBeInTheDocument();
  expect(
    screen.queryByRole("dialog", { name: "Edit expense" }),
  ).not.toBeInTheDocument();
  await waitFor(() => expect(ledgerReads(api).length).toBeGreaterThan(before));
});

it("offers Edit and Remove only on the rows the server allows, and Open day on petty cash rows", async () => {
  renderPage(serveExpenses(), ["expenses.view", "pettycash.spend"]);
  await screen.findByRole("row", { name: /Tyres/ });
  expect(
    screen
      .getAllByRole("button", { name: /^Edit / })
      .map((b) => b.getAttribute("aria-label")),
  ).toEqual([
    "Edit KDA 482M, Tyres, KES 14,000",
    "Edit KDB 100X, Diesel, KES 2,500",
  ]);
  expect(
    screen
      .getAllByRole("button", { name: /^Remove / })
      .map((b) => b.getAttribute("aria-label")),
  ).toEqual(["Remove KDA 482M, Tyres, KES 14,000"]);
  expect(
    screen.getAllByRole("button", { name: /Open 6 Oct 2026/ }),
  ).toHaveLength(1);
  expect(
    within(screen.getByRole("row", { name: /Parking/ })).getByRole("button", {
      name: "Open 6 Oct 2026 in Petty cash",
    }),
  ).toBeInTheDocument();
});

it("hides Open day from someone who cannot open Petty cash", async () => {
  renderPage(serveExpenses(), ["expenses.view"]);
  await screen.findByRole("row", { name: /Parking/ });
  expect(screen.queryByText("Open day")).not.toBeInTheDocument();
});

it("hands the row's date to Petty cash when Open day is chosen", async () => {
  const { onOpenPettyCash } = renderPage(serveExpenses(), [
    "expenses.view",
    "pettycash.spend",
  ]);
  fireEvent.click(
    await screen.findByRole("button", {
      name: "Open 6 Oct 2026 in Petty cash",
    }),
  );
  expect(onOpenPettyCash).toHaveBeenCalledWith("2026-10-06");
});

it("needs a reason to remove, then sends it with the version", async () => {
  const { api } = renderPage();
  fireEvent.click(
    await screen.findByRole("button", {
      name: "Remove KDA 482M, Tyres, KES 14,000",
    }),
  );
  const dialog = await screen.findByRole("dialog", {
    name: "Remove this expense",
  });
  fireEvent.click(within(dialog).getByRole("button", { name: "Remove" }));
  expect(
    await within(dialog).findByText("Say why this expense is being removed."),
  ).toBeInTheDocument();
  expect(api.sent("POST setup/expenses/entries/r1/remove")).toEqual([]);

  changeTo(
    within(dialog).getByLabelText("Reason for removing"),
    "Entered twice",
  );
  fireEvent.click(within(dialog).getByRole("button", { name: "Remove" }));
  expect(await screen.findByText("Expense removed.")).toBeInTheDocument();
  expect(api.sent("POST setup/expenses/entries/r1/remove")).toEqual([
    { version: 3, reason: "Entered twice" },
  ]);
});

it("asks the server for page 1 of 25 and shows the whole period's count and amount in the footer", async () => {
  const api = serveExpenses({ rows: manyRows(120) });
  renderPage(api);
  await screen.findByText("Part 1");
  expect(ledgerReads(api)[0]).toBe(
    `setup/expenses/ledger?${WEEK}&page=1&pageSize=25`,
  );
  expect(screen.getAllByText(/^Part \d+$/)).toHaveLength(25);
  expect(screen.getByText("Showing 1–25 of 120")).toBeInTheDocument();
  expect(screen.getByLabelText("Rows per page")).toHaveValue("25");
  expect(screen.getByText("120 expenses")).toBeInTheDocument();
  expect(screen.getByText("120 expenses").closest("tr")).toHaveTextContent(
    /12,000$/,
  );
});

it("moves between pages on the server: next, a numbered page, the last and back to the first", async () => {
  const api = serveExpenses({ rows: manyRows(120) });
  renderPage(api);
  await screen.findByText("Part 1");

  fireEvent.click(screen.getByRole("button", { name: "Next page" }));
  expect(await screen.findByText("Showing 26–50 of 120")).toBeInTheDocument();
  expect(ledgerReads(api).at(-1)).toBe(
    `setup/expenses/ledger?${WEEK}&page=2&pageSize=25`,
  );
  expect(screen.getByText("Part 26")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Page 2" })).toHaveAttribute(
    "aria-current",
    "page",
  );

  fireEvent.click(screen.getByRole("button", { name: "Page 3" }));
  expect(await screen.findByText("Showing 51–75 of 120")).toBeInTheDocument();
  expect(ledgerReads(api).at(-1)).toContain("page=3&pageSize=25");

  fireEvent.click(screen.getByRole("button", { name: "Last page" }));
  expect(await screen.findByText("Showing 101–120 of 120")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Next page" })).toBeDisabled();

  fireEvent.click(screen.getByRole("button", { name: "First page" }));
  expect(await screen.findByText("Showing 1–25 of 120")).toBeInTheDocument();
});

it("returns to page 1 when the page size, the source, the search or the period changes", async () => {
  const api = serveExpenses({ rows: manyRows(120) });
  renderPage(api);
  await screen.findByText("Part 1");

  fireEvent.click(screen.getByRole("button", { name: "Page 3" }));
  await screen.findByText("Showing 51–75 of 120");
  pick(screen.getByLabelText("Rows per page"), "50");
  expect(await screen.findByText("Showing 1–50 of 120")).toBeInTheDocument();
  expect(ledgerReads(api).at(-1)).toContain("page=1&pageSize=50");

  fireEvent.click(screen.getByRole("button", { name: "Page 3" }));
  await screen.findByText("Showing 101–120 of 120");
  choose(screen.getByLabelText("Source"), "Central");
  await waitFor(() =>
    expect(ledgerReads(api).at(-1)).toContain(
      "source=central&page=1&pageSize=50",
    ),
  );

  fireEvent.click(await screen.findByRole("button", { name: "Page 2" }));
  await screen.findByText("Showing 51–100 of 120");
  changeTo(screen.getByLabelText("Search"), "part");
  await waitFor(() =>
    expect(ledgerReads(api).at(-1)).toContain("q=part&page=1&pageSize=50"),
  );

  fireEvent.click(await screen.findByRole("button", { name: "Page 2" }));
  await screen.findByText("Showing 51–100 of 120");
  fireEvent.click(screen.getByRole("button", { name: "Previous week" }));
  await waitFor(() =>
    expect(ledgerReads(api).at(-1)).toContain("page=1&pageSize=50"),
  );
});

it("steps back to the last page that exists when a removal empties the page it was on", async () => {
  const rows = manyRows(51);
  const api = serveExpenses({ rows });
  renderPage(api);
  await screen.findByText("Part 1");
  fireEvent.click(screen.getByRole("button", { name: "Page 3" }));
  expect(await screen.findByText("Showing 51–51 of 51")).toBeInTheDocument();

  rows.pop();
  fireEvent.click(
    await screen.findByLabelText("Remove KDA 482M, Part 51, KES 100"),
  );
  const dialog = await screen.findByRole("dialog", {
    name: "Remove this expense",
  });
  changeTo(
    within(dialog).getByLabelText("Reason for removing"),
    "Entered twice",
  );
  fireEvent.click(within(dialog).getByRole("button", { name: "Remove" }));

  expect(await screen.findByText("Expense removed.")).toBeInTheDocument();
  await waitFor(() =>
    expect(ledgerReads(api).at(-1)).toContain("page=2&pageSize=25"),
  );
  expect(await screen.findByText("Showing 26–50 of 50")).toBeInTheDocument();
  expect(await screen.findByText("Part 26")).toBeInTheDocument();
});

it("keeps the page after a save when it still has rows", async () => {
  const api = serveExpenses({ rows: manyRows(120) });
  renderPage(api);
  await screen.findByText("Part 1");
  fireEvent.click(screen.getByRole("button", { name: "Page 2" }));
  fireEvent.click(
    await screen.findByLabelText("Remove KDA 482M, Part 26, KES 100"),
  );
  const dialog = await screen.findByRole("dialog", {
    name: "Remove this expense",
  });
  changeTo(
    within(dialog).getByLabelText("Reason for removing"),
    "Entered twice",
  );
  fireEvent.click(within(dialog).getByRole("button", { name: "Remove" }));
  await screen.findByText("Expense removed.");
  await waitFor(() =>
    expect(
      ledgerReads(api).filter((path) => path.includes("page=2&pageSize=25"))
        .length,
    ).toBeGreaterThan(1),
  );
  expect(screen.getByRole("button", { name: "Page 2" })).toHaveAttribute(
    "aria-current",
    "page",
  );
});

it("opens Petty cash on the day of a petty cash row from the app shell", async () => {
  const api = serveExpenses();
  api.on("auth/session", [
    200,
    {
      userId: "me",
      firstName: "Test",
      lastName: "User",
      role: "Owner",
      permissions: ["expenses.view", "pettycash.spend"],
    },
  ]);
  api.on("setup/appearance", [200, appearanceFixture(BUSINESS_DATE)]);
  api.on("setup/pettycash/overview*", (sent) => {
    const query = new URL(sent.path, "http://localhost").searchParams;
    const to = query.get("to") ?? BUSINESS_DATE;
    const from = query.get("from") ?? to;
    return [
      200,
      overviewOf(pettyPermissions(), to, {
        from,
        to,
        period: from === to ? "day" : "range",
      }),
    ];
  });
  api.on("setup/pettycash/entries*", [
    200,
    { items: [], pageNumber: 1, pageSize: 100, total: 0 },
  ]);
  render(<AppShell onSignOut={() => {}} />);

  const menu = within(await screen.findByRole("navigation", { name: "Main" }));
  fireEvent.click(
    await menu.findByRole("button", { name: "Central expenses" }),
  );
  expect(
    await screen.findByRole("heading", { name: "Central expenses", level: 1 }),
  ).toBeInTheDocument();
  fireEvent.click(
    await screen.findByRole("button", {
      name: "Open 6 Oct 2026 in Petty cash",
    }),
  );

  expect(
    await screen.findByRole("heading", { name: "Petty cash", level: 1 }),
  ).toBeInTheDocument();
  expect(
    await screen.findByRole("button", { name: "Period, Tue 6 Oct 2026" }),
  ).toBeInTheDocument();
  await waitFor(() =>
    expect(
      api.calls.some((call) =>
        call.path.startsWith(
          "setup/pettycash/overview?from=2026-10-06&to=2026-10-06",
        ),
      ),
    ).toBe(true),
  );
});

const before = (first: Element, second: Element) =>
  Boolean(
    first.compareDocumentPosition(second) & Node.DOCUMENT_POSITION_FOLLOWING,
  );

it("lays the record form out as the design does: the date first, the vehicle, the item, quantity beside unit cost, then the total", async () => {
  renderPage();
  const dialog = await openRecord();
  const field = (label: string) => within(dialog).getByLabelText(label);
  const date = within(dialog)
    .getByRole("button", { name: "Previous day" })
    .closest(".mstep")!;
  expect(date).not.toBeNull();
  const row = field("Qty").closest(".mrow");
  expect(row).not.toBeNull();
  expect(field("Unit cost, KES").closest(".mrow")).toBe(row);
  expect(field("Item").closest(".mrow, .mrow2")).toBeNull();
  const total = within(dialog).getByText("Total amount").parentElement!;
  expect(total).toHaveClass("mtot");
  const order = [
    date,
    field("Vehicle"),
    field("Item"),
    field("Qty"),
    field("Unit cost, KES"),
    total,
  ];
  order.slice(1).forEach((element, index) => {
    expect(before(order[index], element)).toBe(true);
  });
  expect(within(dialog).queryByLabelText("Note")).toBeNull();
  expect(within(dialog).queryByText(/minus sign/)).toBeNull();
  expect(within(dialog).queryByText(/^Recorded by/)).not.toBeInTheDocument();
});

it("turns the vehicle into the split rows under the total, as the design does", async () => {
  renderPage();
  const dialog = await openRecord();
  fireEvent.click(
    within(dialog).getByRole("button", { name: "Split across vehicles" }),
  );
  expect(within(dialog).queryByLabelText("Vehicle")).toBeNull();
  const first = within(dialog).getByLabelText("Vehicle 1");
  expect(before(within(dialog).getByText("Total amount"), first)).toBe(true);
  expect(
    before(first, within(dialog).getByRole("button", { name: /^Save/ })),
  ).toBe(true);
});

it("puts who recorded a row under the title of the form that changes it, not in its body", async () => {
  renderPage();
  fireEvent.click(
    await screen.findByRole("button", {
      name: "Edit KDA 482M, Tyres, KES 14,000",
    }),
  );
  const dialog = await screen.findByRole("dialog", { name: "Edit expense" });
  const subtitle = within(dialog).getByText("Recorded by Brian Mwangi");
  const title = within(dialog).getByRole("heading", { name: "Edit expense" });
  expect(subtitle.previousElementSibling).toBe(title);
  expect(dialog.querySelector("form")).not.toHaveTextContent("Recorded by");
});

it("searches the item by typing, and takes the source from its list", async () => {
  const { api } = renderPage();
  const dialog = await openRecord();
  const item = within(dialog).getByLabelText("Item");
  fireEvent.focus(item);
  fireEvent.change(item, { target: { value: "fuel dies" } });
  fireEvent.keyDown(item, { key: "Enter" });
  expect(item).toHaveValue("Diesel");
  changeTo(within(dialog).getByLabelText("Unit cost, KES"), "100");
  pick(within(dialog).getByLabelText("Vehicle"), /^KDA/);
  fireEvent.click(save(dialog));
  await screen.findByText("KES 100 recorded on KDA 482M.");
  expect(api.sent("POST setup/expenses/entries")[0]).toMatchObject({
    expenseItemId: "i2",
  });

  choose(screen.getByLabelText("Source"), "Petty cash");
  await waitFor(() =>
    expect(ledgerReads(api).at(-1)).toContain("source=pettycash"),
  );
});

it("exports the ledger as listed, with its source and search, to someone with reports.export", async () => {
  URL.createObjectURL = vi.fn(() => "blob:ledger");
  URL.revokeObjectURL = vi.fn();
  const saved: string[] = [];
  const click = vi
    .spyOn(HTMLAnchorElement.prototype, "click")
    .mockImplementation(function (this: HTMLAnchorElement) {
      saved.push(this.download);
    });
  const api = serveExpenses();
  api.on("setup/expenses/export*", [200, {}]);
  renderPage(api, ["expenses.view", "reports.export"]);
  await screen.findByRole("row", { name: /Tyres/ });
  choose(screen.getByLabelText("Source"), "Petty cash");
  changeTo(screen.getByLabelText("Search"), "diesel");
  await waitFor(() => expect(ledgerReads(api).at(-1)).toContain("q=diesel"));

  fireEvent.click(screen.getByRole("button", { name: "Export" }));
  fireEvent.click(screen.getByRole("menuitem", { name: "PDF" }));

  await waitFor(() => expect(saved).toHaveLength(1));
  expect(
    api.calls
      .map((call) => call.path)
      .filter((path) => path.startsWith("setup/expenses/export")),
  ).toEqual([
    `setup/expenses/export?${WEEK}&source=pettycash&q=diesel&format=pdf`,
  ]);
  expect(saved[0]).toBe("Central expenses 5-11 Oct 2026.pdf");
  click.mockRestore();
});

it("offers no Export without reports.export", async () => {
  renderPage();
  await screen.findByRole("row", { name: /Tyres/ });
  expect(
    screen.queryByRole("button", { name: "Export" }),
  ).not.toBeInTheDocument();
});

const category = (
  id: string,
  name: string,
  stoppedOn: string | null = null,
) => ({
  id,
  name,
  bucket: null,
  active: stoppedOn === null,
  stoppedOn,
  mainCategoryId: null,
  mainCategoryName: null,
  items: [],
});

// The catalog the new item form loads: one category in use, any others given, no main categories.
function withCatalog(
  api: ReturnType<typeof serveExpenses>,
  others: ReturnType<typeof category>[] = [],
) {
  const items = [category("g", "Garage and repairs"), ...others];
  api.on("GET setup/expense-categories*", [
    200,
    { items, pageNumber: 1, pageSize: 100, total: items.length },
  ]);
  api.on("GET setup/expense-main-categories*", [
    200,
    { items: [], pageNumber: 1, pageSize: 100, total: 0 },
  ]);
  return api;
}

it("adds a missing item from the expense form, chooses it and keeps what was already filled", async () => {
  const api = withCatalog(serveExpenses());
  api.on("POST setup/expense-categories/g/items", [200, { id: "i9" }]);
  renderPage(api, ["expenses.view", "expenses.capture", "catalog.add"]);
  const dialog = await openRecord();
  pick(within(dialog).getByLabelText("Vehicle"), "KDA 482M, Rongai Express");
  changeTo(within(dialog).getByLabelText("Qty"), "2");
  const item = within(dialog).getByLabelText("Item");
  fireEvent.focus(item);
  changeTo(item, "Towing");
  fireEvent.keyDown(item, { key: "Enter" });

  const added = await screen.findByRole("dialog", { name: "New item" });
  expect(within(added).getByLabelText("Name")).toHaveValue("Towing");
  pick(within(added).getByLabelText("Category"), "Garage and repairs");
  fireEvent.click(within(added).getByRole("button", { name: "Save" }));

  await waitFor(() =>
    expect(api.sent("POST setup/expense-categories/g/items")).toEqual([
      { name: "Towing" },
    ]),
  );
  await waitFor(() =>
    expect(
      screen.queryByRole("dialog", { name: "New item" }),
    ).not.toBeInTheDocument(),
  );
  expect(item).toHaveValue("Towing");
  expect(within(dialog).getByLabelText("Qty")).toHaveValue("2");
  expect(within(dialog).getByLabelText("Vehicle")).toHaveValue(
    "KDA 482M, Rongai Express",
  );
  changeTo(within(dialog).getByLabelText("Unit cost, KES"), "500");
  fireEvent.click(save(dialog));
  await waitFor(() =>
    expect(api.sent("POST setup/expenses/entries")).toEqual([
      expect.objectContaining({ expenseItemId: "i9", units: 2 }),
    ]),
  );
});

it("closes only the new item form on Escape and keeps the expense form as filled", async () => {
  renderPage(withCatalog(serveExpenses()), [
    "expenses.view",
    "expenses.capture",
    "catalog.add",
  ]);
  const dialog = await openRecord();
  changeTo(within(dialog).getByLabelText("Qty"), "2");
  const item = within(dialog).getByLabelText("Item");
  fireEvent.focus(item);
  changeTo(item, "Towing");
  fireEvent.keyDown(item, { key: "Enter" });

  const added = await screen.findByRole("dialog", { name: "New item" });
  fireEvent(added, new Event("close"));
  await waitFor(() =>
    expect(
      screen.queryByRole("dialog", { name: "New item" }),
    ).not.toBeInTheDocument(),
  );
  expect(dialog).toHaveAttribute("open");
  expect(within(dialog).getByLabelText("Qty")).toHaveValue("2");
});

it("offers no + Add new in the item list without a catalog right", async () => {
  renderPage();
  const dialog = await openRecord();
  fireEvent.focus(within(dialog).getByLabelText("Item"));
  expect(
    within(dialog).queryByRole("option", { name: "+ Add new" }),
  ).not.toBeInTheDocument();
});

it("opens the new vehicle form with the registration typed, and cancelling it keeps the expense as filled", async () => {
  const api = serveExpenses();
  api.on("GET setup/vehicles/company-options", [200, []]);
  renderPage(api, ["expenses.view", "expenses.capture", "vehicles.add"]);
  const dialog = await openRecord();
  changeTo(within(dialog).getByLabelText("Qty"), "3");
  const vehicle = within(dialog).getByLabelText("Vehicle");
  fireEvent.focus(vehicle);
  changeTo(vehicle, "kde 300z");
  fireEvent.keyDown(vehicle, { key: "Enter" });

  const added = await screen.findByRole("dialog", { name: "New vehicle" });
  expect(within(added).getByLabelText("Registration")).toHaveValue("KDE 300Z");
  fireEvent.click(within(added).getByRole("button", { name: "Cancel" }));
  await waitFor(() =>
    expect(
      screen.queryByRole("dialog", { name: "New vehicle" }),
    ).not.toBeInTheDocument(),
  );
  expect(within(dialog).getByLabelText("Qty")).toHaveValue("3");
  expect(api.sent("POST setup/vehicles")).toEqual([]);
});

it("offers no + Add new in the vehicle list when the person's scope names vehicles only", async () => {
  const api = serveExpenses();
  api.on("GET setup/access/me", [
    200,
    {
      allCompanies: false,
      placesVehicles: false,
      companies: [],
      vehicles: [],
      canChange: "Any date",
      earliest: null,
    },
  ]);
  renderPage(api, ["expenses.view", "expenses.capture", "vehicles.add"]);
  const dialog = await openRecord();
  const vehicle = within(dialog).getByLabelText("Vehicle");
  fireEvent.focus(vehicle);
  changeTo(vehicle, "kde 300z");
  await waitFor(() =>
    expect(
      within(dialog).queryByRole("option", { name: "+ Add new" }),
    ).not.toBeInTheDocument(),
  );
});

it("puts a vehicle added from a split row on that row and keeps the others", async () => {
  const api = serveExpenses();
  const added = {
    id: "v9",
    companyId: "c1",
    companyName: "Rongai Express",
    registration: "KDE 300Z",
    active: true,
  };
  api.on("setup/expenses/options*", () => [
    200,
    api.sent("POST setup/vehicles").length
      ? { ...OPTIONS, vehicles: [...OPTIONS.vehicles, added] }
      : OPTIONS,
  ]);
  api.on("GET setup/vehicles/company-options", [
    200,
    [{ id: "c1", name: "Rongai Express" }],
  ]);
  api.on("POST setup/vehicles", [200, { id: "v9" }]);
  renderPage(api, ["expenses.view", "expenses.capture", "vehicles.add"]);
  const dialog = await openRecord();
  fillPurchase(dialog, "1", "100");
  fireEvent.click(
    within(dialog).getByRole("button", { name: "Split across vehicles" }),
  );
  pick(within(dialog).getByLabelText("Vehicle 1"), /^KDA 482M/);
  const second = within(dialog).getByLabelText("Vehicle 2");
  fireEvent.focus(second);
  changeTo(second, "kde 300z");
  fireEvent.keyDown(second, { key: "Enter" });

  const form = within(
    await screen.findByRole("dialog", { name: "New vehicle" }),
  );
  expect(form.getByLabelText("Registration")).toHaveValue("KDE 300Z");
  changeTo(form.getByLabelText("Fleet number"), "30");
  await offered(form.getByLabelText("PSV company"), "Rongai Express");
  pick(form.getByLabelText("PSV company"), "Rongai Express");
  changeTo(form.getByLabelText("Target, Monday"), "1800");
  fireEvent.click(form.getByRole("button", { name: "Same every day" }));
  fireEvent.click(form.getByRole("button", { name: "Save" }));

  await waitFor(() =>
    expect(
      screen.queryByRole("dialog", { name: "New vehicle" }),
    ).not.toBeInTheDocument(),
  );
  expect(api.sent("POST setup/vehicles")).toEqual([
    expect.objectContaining({ registration: "KDE 300Z", companyId: "c1" }),
  ]);
  await waitFor(() =>
    expect(within(dialog).getByLabelText("Vehicle 2")).toHaveValue(
      "KDE 300Z, Rongai Express",
    ),
  );
  expect(within(dialog).getByLabelText("Vehicle 1")).toHaveValue(
    "KDA 482M, Rongai Express",
  );
  expect(within(dialog).getByLabelText("Qty")).toHaveValue("1");
});

async function openNewItem(dialog: HTMLElement) {
  const item = within(dialog).getByLabelText("Item");
  fireEvent.focus(item);
  changeTo(item, "Towing");
  fireEvent.keyDown(item, { key: "Enter" });
  return within(await screen.findByRole("dialog", { name: "New item" }));
}

it("offers only the categories in use in the new item form", async () => {
  renderPage(
    withCatalog(serveExpenses(), [category("s", "Old fees", "2026-01-01")]),
    ["expenses.view", "expenses.capture", "catalog.add"],
  );
  const added = await openNewItem(await openRecord());
  const field = added.getByLabelText("Category");
  await offered(field, "Garage and repairs");
  expect(optionsOf(field)).not.toContain("Old fees");
});

it("says in the new item form why its categories did not load", async () => {
  const api = serveExpenses();
  api.on("GET setup/expense-categories*", [
    403,
    { detail: "You need Expense items to do this." },
  ]);
  api.on("GET setup/expense-main-categories*", [
    200,
    { items: [], pageNumber: 1, pageSize: 100, total: 0 },
  ]);
  renderPage(api, ["expenses.view", "expenses.capture", "expenses.setup"]);
  const added = await openNewItem(await openRecord());
  expect(
    await added.findByText("You need Expense items to do this."),
  ).toBeInTheDocument();
});

it("adds a vehicle for an earlier day that joins on that day, and shows it chosen before the list reloads", async () => {
  const api = serveExpenses();
  api.on("GET setup/vehicles/company-options", [
    200,
    [{ id: "c1", name: "Rongai Express" }],
  ]);
  api.on("POST setup/vehicles", [200, { id: "v9" }]);
  renderPage(api, ["expenses.view", "expenses.capture", "vehicles.add"]);
  const dialog = await openRecord();
  fireEvent.click(within(dialog).getByRole("button", { name: "Previous day" }));
  fillPurchase(dialog, "1", "100");
  const vehicle = within(dialog).getByLabelText("Vehicle");
  fireEvent.focus(vehicle);
  changeTo(vehicle, "kde 300z");
  fireEvent.keyDown(vehicle, { key: "Enter" });

  const form = within(
    await screen.findByRole("dialog", { name: "New vehicle" }),
  );
  expect(form.getByText(/the entry's date/)).toBeInTheDocument();
  changeTo(form.getByLabelText("Fleet number"), "30");
  await offered(form.getByLabelText("PSV company"), "Rongai Express");
  pick(form.getByLabelText("PSV company"), "Rongai Express");
  changeTo(form.getByLabelText("Target, Monday"), "1800");
  fireEvent.click(form.getByRole("button", { name: "Same every day" }));
  fireEvent.click(form.getByRole("button", { name: "Save" }));

  await waitFor(() =>
    expect(
      screen.queryByRole("dialog", { name: "New vehicle" }),
    ).not.toBeInTheDocument(),
  );
  expect(api.sent("POST setup/vehicles")).toEqual([
    expect.objectContaining({
      registration: "KDE 300Z",
      joinedOn: "2026-10-08",
    }),
  ]);
  expect(vehicle).toHaveValue("KDE 300Z, Rongai Express");
  fireEvent.click(save(dialog));
  await waitFor(() =>
    expect(api.sent("POST setup/expenses/entries")).toEqual([
      expect.objectContaining({
        date: "2026-10-08",
        allocations: [{ vehicleId: "v9", amount: 100 }],
      }),
    ]),
  );
});

it("stops offering a vehicle added for today once the entry moves to a day before it joins", async () => {
  const api = serveExpenses();
  api.on("GET setup/vehicles/company-options", [
    200,
    [{ id: "c1", name: "Rongai Express" }],
  ]);
  api.on("POST setup/vehicles", [200, { id: "v9" }]);
  renderPage(api, ["expenses.view", "expenses.capture", "vehicles.add"]);
  const dialog = await openRecord();
  const vehicle = within(dialog).getByLabelText("Vehicle");
  fireEvent.focus(vehicle);
  changeTo(vehicle, "kde 300z");
  fireEvent.keyDown(vehicle, { key: "Enter" });
  const form = within(
    await screen.findByRole("dialog", { name: "New vehicle" }),
  );
  changeTo(form.getByLabelText("Fleet number"), "30");
  await offered(form.getByLabelText("PSV company"), "Rongai Express");
  pick(form.getByLabelText("PSV company"), "Rongai Express");
  changeTo(form.getByLabelText("Target, Monday"), "1800");
  fireEvent.click(form.getByRole("button", { name: "Same every day" }));
  fireEvent.click(form.getByRole("button", { name: "Save" }));
  await waitFor(() =>
    expect(
      screen.queryByRole("dialog", { name: "New vehicle" }),
    ).not.toBeInTheDocument(),
  );
  expect(api.sent("POST setup/vehicles")).toEqual([
    expect.objectContaining({
      registration: "KDE 300Z",
      joinedOn: "2026-10-09",
    }),
  ]);
  changeTo(vehicle, "");
  expect(optionsOf(vehicle)).toContain("KDE 300Z, Rongai Express");

  fireEvent.click(within(dialog).getByRole("button", { name: "Previous day" }));

  changeTo(vehicle, "");
  await waitFor(() =>
    expect(optionsOf(vehicle)).not.toContain("KDE 300Z, Rongai Express"),
  );
  expect(optionsOf(vehicle)).toContain("KDA 482M, Rongai Express");
});
