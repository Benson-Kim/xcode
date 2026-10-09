import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { RecurringEditor } from "../components/RecurringEditor";
import { RecurringPage } from "../components/setup";
import type { ExpenseItemOption } from "../lib/types";
import { renderInApp } from "./renderInApp";

// The organization's business date in these tests; where it matters, the computer clock is set well past it.
const businessDate = "2026-09-21";

const vehicle = {
  id: "vehicle-1",
  companyId: "company-1",
  companyName: "North Star",
  registration: "KDA 482M",
  joinedOn: "2026-01-01",
  weeklyTarget: 15000,
};

const expenseItems: ExpenseItemOption[] = [
  {
    id: "insurance",
    name: "Insurance",
    categoryId: "charges",
    categoryName: "Charges",
    bucket: 2,
  },
  {
    id: "loan",
    name: "Loan repayment",
    categoryId: "loans",
    categoryName: "Loans",
    bucket: 3,
  },
];

const item = {
  id: "item-1",
  name: "Loan repayment",
  kind: 1,
  category: null,
  amount: 1200,
  frequency: 2,
  day: 6,
  lastDay: false,
  start: "2026-10-01",
  end: null,
  stoppedFrom: null,
  allocations: [{ vehicleId: vehicle.id, amount: 1200 }],
  expenseItemId: "loan",
  expenseItemName: "Loan repayment",
  bucket: 3 as const,
  note: null,
  month: null,
};

// Saved before expense items: an old cost type and a daily schedule.
const legacy = {
  ...item,
  id: "legacy-1",
  name: "Stage fees",
  frequency: 1,
  day: null,
  expenseItemId: null,
  expenseItemName: null,
  bucket: null,
};

function mockFetch(
  handler: (
    input: RequestInfo | URL,
    init?: RequestInit,
  ) => Response | Promise<Response>,
) {
  const fetchMock = vi.fn(handler);
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

const listResponse = (rows: unknown[]) =>
  new Response(
    JSON.stringify({
      items: rows,
      pageNumber: 1,
      pageSize: 25,
      total: rows.length,
    }),
    { status: 200 },
  );

function renderEditor(
  props: Partial<Parameters<typeof RecurringEditor>[0]> = {},
) {
  const onSaved = vi.fn(async () => undefined);
  renderInApp(
    <RecurringEditor
      vehicles={[vehicle]}
      expenseItems={expenseItems}
      onCancel={vi.fn()}
      onSaved={onSaved}
      {...props}
    />,
    {},
    { businessDate },
  );
  return onSaved;
}

const sentBody = (fetchMock: ReturnType<typeof mockFetch>) =>
  JSON.parse(fetchMock.mock.calls[0][1]?.body as string);

beforeEach(() => {
  mockFetch(
    async () => new Response(JSON.stringify({ id: item.id }), { status: 200 }),
  );
});

afterEach(() => vi.useRealTimers());

it("reads recurring items with the reference summary and hides Add without manage permission", async () => {
  // A view-only user has no vehicle access: every vehicle endpoint is forbidden.
  const fetchMock = mockFetch(async (input) => {
    if (String(input).endsWith("/recurring?page=1&pageSize=25"))
      return listResponse([
        {
          ...legacy,
          name: "Loan repayment",
          amount: 1000,
          start: "2026-09-27",
          allocations: [
            {
              vehicleId: vehicle.id,
              amount: 1000,
              registration: vehicle.registration,
            },
          ],
        },
      ]);
    return new Response(
      JSON.stringify({
        title: "Not permitted in this organization or data scope.",
      }),
      { status: 403 },
    );
  });

  renderInApp(
    <RecurringPage canManage={false} />,
    {},
    { businessDate: "2026-09-27" },
  );

  expect(
    await screen.findByRole("button", { name: "Loan repayment" }),
  ).toBeInTheDocument();
  expect(screen.getByText("About KES 30,400 a month")).toBeInTheDocument();
  expect(screen.getByText("Every day")).toBeInTheDocument();
  // A cost saved without a bucket counts as a recurring charge, and nothing shows the retired cost types.
  expect(screen.getByText("Recurring charges")).toBeInTheDocument();
  expect(screen.queryByText("Fixed commitments")).not.toBeInTheDocument();
  expect(screen.getByText("1 vehicle")).toBeInTheDocument();
  expect(screen.getByText("KDA 482M")).toBeInTheDocument();
  const row = screen.getByRole("row", { name: /Loan repayment/ });
  expect(
    within(row).getByText("27 Sep 2026", {
      selector: "td[data-label='Next posting']",
    }),
  ).toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "Add scheduled expense or saving" }),
  ).not.toBeInTheDocument();
  // Without commitments.manage there are no vehicle options to tell companies apart, so only the status filter shows.
  expect(
    screen.queryByRole("combobox", { name: "Company" }),
  ).not.toBeInTheDocument();
  expect(screen.getByRole("combobox", { name: "Show" })).toHaveValue("all");
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  expect(fetchMock.mock.calls.map(([input]) => String(input))).toEqual([
    "/api/setup/recurring?page=1&pageSize=25",
  ]);
});

it("counts due dates from the business date, never the computer clock", async () => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date("2026-12-01T10:00:00Z"));
  mockFetch(async () =>
    listResponse([
      {
        ...item,
        frequency: 3,
        day: 1,
        start: "2026-09-01",
        allocations: [
          {
            vehicleId: vehicle.id,
            amount: 1200,
            registration: vehicle.registration,
          },
        ],
      },
    ]),
  );

  // The appearance, and with it the business date, has not arrived yet: the next posting waits for it.
  const { unmount } = renderInApp(<RecurringPage canManage={false} />);
  const row = await screen.findByRole("row", { name: /Loan repayment/ });
  expect(
    within(row).getByText("—", { selector: "td[data-label='Next posting']" }),
  ).toBeInTheDocument();
  expect(within(row).queryByText("1 Dec 2026")).not.toBeInTheDocument();
  unmount();

  renderInApp(<RecurringPage canManage={false} />, {}, { businessDate });
  const dated = await screen.findByRole("row", { name: /Loan repayment/ });
  expect(
    within(dated).getByText("1 Oct 2026", {
      selector: "td[data-label='Next posting']",
    }),
  ).toBeInTheDocument();
});

it("shows the item's note and bucket and a yearly schedule's monthly share", async () => {
  mockFetch(async () =>
    listResponse([
      {
        ...item,
        name: "Insurance",
        expenseItemId: "insurance",
        bucket: 2,
        frequency: 4,
        month: 3,
        day: 14,
        amount: 117600,
        note: "Zuri Genesis",
      },
    ]),
  );
  renderInApp(<RecurringPage canManage={false} />, {}, { businessDate });

  expect(
    await screen.findByText("Zuri Genesis. Recurring charges"),
  ).toBeInTheDocument();
  expect(screen.getByText("Every year on 14th March")).toBeInTheDocument();
  expect(screen.getByText("About KES 9,800 a month")).toBeInTheDocument();
  expect(
    screen.getByText("14 Mar 2027", {
      selector: "td[data-label='Next posting']",
    }),
  ).toBeInTheDocument();
});

it("creates a yearly cost for an expense item, starting on the business date", async () => {
  const fetchMock = mockFetch(
    async () => new Response(JSON.stringify({ id: item.id }), { status: 200 }),
  );
  const onSaved = renderEditor();

  // Only stopping asks for a typed reason (C7); the server writes one for adding and changing.
  expect(screen.queryByLabelText(/Reason/)).not.toBeInTheDocument();
  expect(screen.getByLabelText("Starts")).toHaveValue(businessDate);
  expect(screen.getByLabelText("Starts")).toHaveAttribute("min", "2026-09-01");
  fireEvent.change(screen.getByLabelText("Expense item"), {
    target: { value: "insurance" },
  });
  expect(
    screen.getByText("Charges. Counts as Recurring charges."),
  ).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Note"), {
    target: { value: "Zuri Genesis fleet" },
  });
  fireEvent.change(screen.getByLabelText("Amount each time"), {
    target: { value: "117600" },
  });
  fireEvent.click(screen.getByRole("radio", { name: "Every year" }));
  fireEvent.change(screen.getByLabelText("Month"), { target: { value: "3" } });
  fireEvent.change(screen.getByLabelText("On"), { target: { value: "14" } });
  fireEvent.click(screen.getByLabelText("KDA 482M"));
  expect(screen.getByText("Balanced")).toBeInTheDocument();
  expect(
    screen.getByText("14 Mar 2027: KES 117,600 across 1 vehicle"),
  ).toBeInTheDocument();
  expect(
    screen.getByText(
      /About KES 9,800 a month. Counted under Recurring charges/,
    ),
  ).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Add" }));

  await waitFor(() =>
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/setup/recurring",
      expect.objectContaining({ method: "POST" }),
    ),
  );
  expect(sentBody(fetchMock)).toEqual({
    name: "Insurance",
    kind: 1,
    amount: 117600,
    frequency: 4,
    day: 14,
    lastDay: false,
    start: businessDate,
    end: null,
    allocations: [{ vehicleId: vehicle.id, amount: 117600 }],
    expenseItemId: "insurance",
    note: "Zuri Genesis fleet",
    month: 3,
  });
  expect(onSaved).toHaveBeenCalledOnce();
});

it("keeps savings to a free name, weekly or monthly", async () => {
  const fetchMock = mockFetch(
    async () => new Response(JSON.stringify({ id: item.id }), { status: 200 }),
  );
  renderEditor();

  fireEvent.click(screen.getByRole("radio", { name: "Every year" }));
  fireEvent.click(screen.getByRole("radio", { name: "Savings" }));
  expect(screen.queryByLabelText("Expense item")).not.toBeInTheDocument();
  expect(
    screen.queryByRole("radio", { name: "Every year" }),
  ).not.toBeInTheDocument();
  expect(screen.getByRole("radio", { name: "Every month" })).toBeChecked();
  fireEvent.change(screen.getByLabelText("Name"), {
    target: { value: "Owner savings" },
  });
  fireEvent.change(screen.getByLabelText("Amount each time"), {
    target: { value: "5000" },
  });
  fireEvent.click(screen.getByLabelText("KDA 482M"));
  fireEvent.click(screen.getByRole("button", { name: "Add" }));

  await waitFor(() => expect(fetchMock).toHaveBeenCalled());
  expect(sentBody(fetchMock)).toMatchObject({
    name: "Owner savings",
    kind: 2,
    expenseItemId: null,
    frequency: 3,
    month: null,
    note: null,
  });
});

it("refuses a start before the first of the business date's month, and a note over 200 characters", async () => {
  const fetchMock = mockFetch(
    async () => new Response(JSON.stringify({ id: item.id }), { status: 200 }),
  );
  renderEditor();

  fireEvent.change(screen.getByLabelText("Expense item"), {
    target: { value: "loan" },
  });
  fireEvent.change(screen.getByLabelText("Amount each time"), {
    target: { value: "1200" },
  });
  fireEvent.change(screen.getByLabelText("Starts"), {
    target: { value: "2026-08-31" },
  });
  fireEvent.change(screen.getByLabelText("Note"), {
    target: { value: "x".repeat(201) },
  });
  fireEvent.click(screen.getByLabelText("KDA 482M"));
  fireEvent.click(screen.getByRole("button", { name: "Add" }));

  expect(
    screen.getByText(
      "Start on or after 1 Sep 2026. Anything earlier is a one-off expense, not a schedule.",
    ),
  ).toBeInTheDocument();
  expect(
    screen.getByText("Keep the note to 200 characters."),
  ).toBeInTheDocument();
  expect(fetchMock).not.toHaveBeenCalled();

  fireEvent.change(screen.getByLabelText("Starts"), {
    target: { value: "2026-09-01" },
  });
  fireEvent.change(screen.getByLabelText("Note"), { target: { value: "" } });
  fireEvent.click(screen.getByRole("button", { name: "Add" }));
  await waitFor(() => expect(fetchMock).toHaveBeenCalled());
  expect(sentBody(fetchMock)).toMatchObject({
    start: "2026-09-01",
    expenseItemId: "loan",
    frequency: 3,
    day: 1,
  });
});

it("updates a scheduled item using its edited allocations and schedule", async () => {
  const fetchMock = mockFetch(
    async () => new Response(JSON.stringify({ id: item.id }), { status: 200 }),
  );
  const onSaved = renderEditor({ item });

  expect(screen.getByLabelText("Expense item")).toHaveValue("loan");
  fireEvent.change(screen.getByLabelText("Expense item"), {
    target: { value: "insurance" },
  });
  fireEvent.change(screen.getByLabelText("Amount each time"), {
    target: { value: "1350" },
  });
  fireEvent.change(screen.getByLabelText("Share for KDA 482M"), {
    target: { value: "1350" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Save changes" }));

  await waitFor(() =>
    expect(fetchMock).toHaveBeenCalledWith(
      `/api/setup/recurring/${item.id}`,
      expect.objectContaining({ method: "PUT" }),
    ),
  );
  expect(sentBody(fetchMock)).toMatchObject({
    name: "Insurance",
    expenseItemId: "insurance",
    amount: 1350,
    frequency: 2,
    day: 6,
    month: null,
    allocations: [{ vehicleId: vehicle.id, amount: 1350 }],
  });
  expect(sentBody(fetchMock)).not.toHaveProperty("reason");
  expect(onSaved).toHaveBeenCalledOnce();
});

it("shows a legacy daily cost read-only and asks for an item and a new frequency before saving", async () => {
  const fetchMock = mockFetch(
    async () =>
      new Response(JSON.stringify({ id: legacy.id }), { status: 200 }),
  );
  renderEditor({ item: legacy });

  expect(
    screen.getByText(
      /Saved before the rules it would follow today.*To save a change, choose an expense item and how often it posts\./,
    ),
  ).toBeInTheDocument();
  expect(
    screen.getByText("Now every day, which is no longer offered."),
  ).toBeInTheDocument();
  expect(
    screen.getByText(/Counted under Recurring charges in each vehicle report/),
  ).toBeInTheDocument();
  expect(screen.getByLabelText("Expense item")).toHaveValue("");
  expect(
    screen.queryByRole("radio", { name: "Every day" }),
  ).not.toBeInTheDocument();
  for (const option of ["Every week", "Every month", "Every year"])
    expect(screen.getByRole("radio", { name: option })).not.toBeChecked();

  fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
  expect(screen.getByText("Choose the expense item.")).toBeInTheDocument();
  expect(
    screen.getByText(
      "Every day is no longer offered. Choose how often it posts.",
    ),
  ).toBeInTheDocument();
  expect(fetchMock).not.toHaveBeenCalled();

  fireEvent.change(screen.getByLabelText("Expense item"), {
    target: { value: "loan" },
  });
  fireEvent.click(screen.getByRole("radio", { name: "Every month" }));
  fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
  await waitFor(() =>
    expect(fetchMock).toHaveBeenCalledWith(
      `/api/setup/recurring/${legacy.id}`,
      expect.objectContaining({ method: "PUT" }),
    ),
  );
  expect(sentBody(fetchMock)).toMatchObject({
    expenseItemId: "loan",
    frequency: 3,
    day: 1,
    lastDay: false,
  });
});

it("requires a second click and a typed reason before stopping a scheduled item", async () => {
  const fetchMock = mockFetch(
    async () => new Response(JSON.stringify({ id: item.id }), { status: 200 }),
  );
  const onSaved = renderEditor({ item });

  fireEvent.click(screen.getByRole("button", { name: "Stop from today" }));
  expect(
    screen.getByRole("button", { name: "Tap again to stop from today" }),
  ).toBeInTheDocument();
  expect(fetchMock).not.toHaveBeenCalled();
  fireEvent.click(
    screen.getByRole("button", { name: "Tap again to stop from today" }),
  );
  expect(screen.getByRole("alert")).toHaveTextContent(
    "Give a reason for stopping this item.",
  );
  expect(fetchMock).not.toHaveBeenCalled();
  fireEvent.change(screen.getByLabelText("Reason for stopping"), {
    target: { value: "Stop item" },
  });
  fireEvent.click(
    screen.getByRole("button", { name: "Tap again to stop from today" }),
  );

  await waitFor(() =>
    expect(fetchMock).toHaveBeenCalledWith(
      `/api/setup/recurring/${item.id}/stop`,
      expect.objectContaining({ method: "POST" }),
    ),
  );
  expect(sentBody(fetchMock)).toMatchObject({
    confirmed: true,
    reason: "Stop item",
  });
  expect(onSaved).toHaveBeenCalledOnce();
});

it("keeps an item editable before its future stop date, and offers to cancel the stop", () => {
  renderEditor({ item: { ...item, stoppedFrom: "2026-09-25" } });

  expect(
    screen.getByText(
      "Scheduled to stop on 25 Sep 2026. You can still change the schedule, or cancel the stop, before then.",
    ),
  ).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Save changes" })).toBeEnabled();
  // The server refuses a second stop on another date (D16), so the only stop action offered is cancelling it.
  expect(screen.getByRole("button", { name: "Cancel stop" })).toBeEnabled();
  expect(
    screen.queryByRole("button", { name: "Stop from today" }),
  ).not.toBeInTheDocument();
});

it("cancelling a future stop posts to restore and reloads", async () => {
  const fetchMock = mockFetch(
    async () => new Response(JSON.stringify({ id: item.id }), { status: 200 }),
  );
  const onSaved = renderEditor({
    item: { ...item, stoppedFrom: "2026-09-25" },
  });

  fireEvent.click(screen.getByRole("button", { name: "Cancel stop" }));

  await waitFor(() => expect(onSaved).toHaveBeenCalled());
  expect(fetchMock.mock.calls.map(([input]) => String(input))).toContain(
    `/api/setup/recurring/${item.id}/restore`,
  );
});

it("loads expense item options only once the editor opens", async () => {
  const fetchMock = mockFetch(async (input) => {
    const url = String(input);
    if (url.includes("/expense-items/options"))
      return new Response(JSON.stringify(expenseItems), { status: 200 });
    if (url.includes("/vehicle-options"))
      return new Response(JSON.stringify([vehicle]), { status: 200 });
    return listResponse([]);
  });
  renderInApp(
    <RecurringPage canManage />,
    { permissions: ["commitments.view", "commitments.manage"] },
    { businessDate },
  );

  fireEvent.click(
    await screen.findByRole("button", {
      name: "Add scheduled expense or saving",
    }),
  );
  expect(
    await screen.findByRole("option", { name: "Loan repayment" }),
  ).toBeInTheDocument();
  expect(
    within(screen.getByRole("group", { name: "Loans" })).getByRole("option", {
      name: "Loan repayment",
    }),
  ).toBeInTheDocument();
  const urls = fetchMock.mock.calls.map(([input]) => String(input));
  expect(urls.filter((url) => url.includes("expense-items"))).toEqual([
    "/api/setup/expense-items/options",
  ]);
});

it("filters the list by company and by running or stopped, as the design does", async () => {
  const metro = {
    id: "vehicle-2",
    companyId: "company-2",
    companyName: "Metro Trans",
    registration: "KBZ 640Q",
  };
  const share = (target: { id: string; registration: string }) => [
    { vehicleId: target.id, amount: 1200, registration: target.registration },
  ];
  const all = [
    { ...item, id: "parking", name: "Parking", allocations: share(vehicle) },
    {
      ...item,
      id: "sacco",
      name: "SACCO fee",
      stoppedFrom: "2026-09-15",
      allocations: share(metro),
    },
    {
      ...item,
      id: "licence",
      name: "Licence",
      start: "2026-01-01",
      end: "2026-06-30",
      allocations: share(metro),
    },
  ];
  // The server filters: a company by the vehicles shared to, running while not stopped or ended.
  const companyOf = new Map([
    [vehicle.id, vehicle.companyId],
    [metro.id, metro.companyId],
  ]);
  const running = (row: (typeof all)[number]) =>
    !(row.stoppedFrom && row.stoppedFrom <= businessDate) &&
    !(row.end && row.end < businessDate);
  const fetcher = mockFetch(async (input) => {
    const url = new URL(String(input), "http://localhost");
    if (url.pathname.includes("/vehicle-options"))
      return new Response(JSON.stringify([vehicle, metro]), { status: 200 });
    const companyId = url.searchParams.get("companyId");
    const status = url.searchParams.get("status");
    return listResponse(
      all.filter(
        (row) =>
          (!companyId ||
            row.allocations.some(
              (share) => companyOf.get(share.vehicleId) === companyId,
            )) &&
          (!status || running(row) === (status === "running")),
      ),
    );
  });
  const lastList = () =>
    fetcher.mock.calls
      .map(([input]) => String(input))
      .filter((url) => url.startsWith("/api/setup/recurring?"))
      .at(-1);

  renderInApp(
    <RecurringPage canManage />,
    { permissions: ["commitments.view", "commitments.manage"] },
    { businessDate },
  );
  const names = () =>
    screen
      .getAllByRole("row")
      .slice(1)
      .map((row) => within(row).getAllByRole("button")[0].textContent);

  await screen.findByRole("button", { name: "Parking" });
  const company = await screen.findByRole("combobox", { name: "Company" });
  expect(
    [...company.querySelectorAll("option")].map((option) => option.textContent),
  ).toEqual(["All companies", "Metro Trans", "North Star"]);
  const status = screen.getByRole("combobox", { name: "Show" });
  expect(
    [...status.querySelectorAll("option")].map((option) => option.textContent),
  ).toEqual(["All", "Running", "Stopped"]);

  fireEvent.change(company, { target: { value: "company-1" } });
  await waitFor(() => expect(names()).toEqual(["Parking"]));
  expect(lastList()).toBe(
    "/api/setup/recurring?companyId=company-1&page=1&pageSize=25",
  );
  fireEvent.change(company, { target: { value: "all" } });
  fireEvent.change(status, { target: { value: "stopped" } });
  await waitFor(() => expect(names()).toEqual(["Licence", "SACCO fee"]));
  expect(lastList()).toBe(
    "/api/setup/recurring?status=stopped&page=1&pageSize=25",
  );
  fireEvent.change(status, { target: { value: "running" } });
  await waitFor(() => expect(names()).toEqual(["Parking"]));
  fireEvent.change(company, { target: { value: "company-2" } });
  expect(await screen.findByText("Nothing here yet.")).toBeInTheDocument();
  expect(lastList()).toBe(
    "/api/setup/recurring?companyId=company-2&status=running&page=1&pageSize=25",
  );
});

it("shows a future stop separately while listing its next posting as running", async () => {
  // The server counts an item that stops after the business date as running.
  const fetcher = mockFetch(async (input) =>
    listResponse(
      String(input).includes("status=stopped")
        ? []
        : [
            {
              ...item,
              stoppedFrom: "2026-09-25",
              start: "2026-09-01",
              frequency: 1,
              day: null,
            },
          ],
    ),
  );
  renderInApp(
    <RecurringPage canManage={false} />,
    {},
    { businessDate: "2026-09-21" },
  );

  const row = await screen.findByRole("row", { name: /Loan repayment/ });
  expect(
    within(row).getByText("21 Sep 2026", {
      selector: "td[data-label='Next posting']",
    }),
  ).toBeInTheDocument();
  expect(within(row).getByText("Stops 25 Sep 2026")).toBeInTheDocument();

  fireEvent.change(screen.getByRole("combobox", { name: "Show" }), {
    target: { value: "stopped" },
  });
  expect(await screen.findByText("Nothing here yet.")).toBeInTheDocument();
  fireEvent.change(screen.getByRole("combobox", { name: "Show" }), {
    target: { value: "running" },
  });
  expect(
    await screen.findByRole("row", { name: /Loan repayment/ }),
  ).toBeInTheDocument();
  expect(String(fetcher.mock.calls.at(-1)?.[0])).toContain("status=running");
});
