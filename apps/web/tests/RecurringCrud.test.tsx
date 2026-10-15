import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { RecurringEditor } from "../components/RecurringEditor";
import type { ExpenseItemOption } from "../lib/types";
import { renderInApp } from "./renderInApp";
import { choose, pick } from "./searchSelect";

// The organization's business date in these tests; where it matters, the computer clock is set well past it.
const businessDate = "2026-09-21";

const vehicle = {
  id: "vehicle-1",
  companyId: "company-1",
  companyName: "North Star",
  registration: "KDA 482M",
  fleetNumber: "14",
};
const second = {
  id: "vehicle-2",
  companyId: "company-1",
  companyName: "North Star",
  registration: "KBZ 640Q",
  fleetNumber: null,
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
  amount: 2400,
  frequency: 2,
  day: 6,
  lastDay: false,
  start: "2026-08-01",
  end: null,
  stoppedFrom: null,
  allocations: [
    { vehicleId: vehicle.id, amount: 1200, registration: "KDA 482M" },
    { vehicleId: second.id, amount: 1200, registration: "KBZ 640Q" },
  ],
  expenseItemId: "loan",
  expenseItemName: "Loan repayment",
  bucket: 3 as const,
  note: null,
  month: null,
};

function mockFetch() {
  const fetchMock = vi.fn<
    (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>
  >(
    async () => new Response(JSON.stringify({ id: "item-1" }), { status: 200 }),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function renderEditor(
  props: Partial<Parameters<typeof RecurringEditor>[0]> = {},
) {
  const onSaved = vi.fn(async () => undefined);
  renderInApp(
    <RecurringEditor
      vehicles={[vehicle, second]}
      expenseItems={expenseItems}
      fullScope
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

let fetchMock: ReturnType<typeof mockFetch>;
beforeEach(() => {
  fetchMock = mockFetch();
});
afterEach(() => vi.useRealTimers());

it("creates a yearly scheduled expense for an item, an amount per vehicle, on the ticked vehicles, from today", async () => {
  const onSaved = renderEditor();
  expect(
    screen.getByRole("dialog", { name: "New scheduled expense" }),
  ).toBeInTheDocument();
  // No start, end or note; no sentence under any field.
  expect(screen.queryByLabelText(/start/i)).not.toBeInTheDocument();
  expect(screen.queryByLabelText(/note/i)).not.toBeInTheDocument();
  expect(
    screen.queryByText(/It posts to the vehicles/),
  ).not.toBeInTheDocument();
  expect(
    within(screen.getByLabelText("Runs"))
      .getAllByRole("option")
      .map((option) => option.textContent),
  ).toEqual(["Every week", "Every month", "Every year"]);

  pick(screen.getByLabelText("Item"), "Insurance");
  fireEvent.change(screen.getByLabelText("Amount per vehicle, KES"), {
    target: { value: "3000" },
  });
  choose(screen.getByLabelText("Runs"), "Every year");
  choose(screen.getByLabelText("Date"), "15th");
  choose(screen.getByLabelText("Month"), "March");
  // All vehicles is ticked for someone who sees every vehicle; untick it and pick one.
  expect(screen.getByLabelText("All vehicles")).toBeChecked();
  fireEvent.click(screen.getByLabelText("All vehicles"));
  fireEvent.click(screen.getByLabelText("KDA 482M · 14"));
  expect(
    screen.getByText("First run 15 Mar 2027, 1 vehicle"),
  ).toBeInTheDocument();
  expect(screen.getByText("KES 3,000")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() => expect(onSaved).toHaveBeenCalled());
  expect(sentBody(fetchMock)).toEqual({
    name: "Insurance",
    kind: 1,
    amount: 3000,
    frequency: 4,
    day: 15,
    lastDay: false,
    month: 3,
    start: businessDate,
    end: null,
    allocations: [{ vehicleId: "vehicle-1", amount: 3000 }],
    expenseItemId: "insurance",
    note: null,
  });
});

it("creates a saving with a revenue rule and an opening balance on every vehicle", async () => {
  const onSaved = renderEditor({ kind: 2 });
  expect(
    screen.getByRole("dialog", { name: "New saving" }),
  ).toBeInTheDocument();
  expect(
    within(screen.getByLabelText("Runs"))
      .getAllByRole("option")
      .map((option) => option.textContent),
  ).toEqual(["Every day", "Every week", "Every month", "Every year"]);
  fireEvent.change(screen.getByLabelText("Name"), {
    target: { value: "Engine fund" },
  });
  fireEvent.change(screen.getByLabelText("Amount per vehicle, KES"), {
    target: { value: "2000" },
  });
  choose(screen.getByLabelText("Runs"), "Every week");
  choose(screen.getByLabelText("Day"), "Saturday");
  choose(screen.getByLabelText("Save"), "Only when revenue reaches a target");
  fireEvent.change(screen.getByLabelText("Revenue per vehicle, KES"), {
    target: { value: "60000" },
  });
  expect(screen.getByLabelText("Measured")).toHaveValue("7");
  fireEvent.click(screen.getByLabelText("Opening balance"));
  fireEvent.change(screen.getByLabelText("Opening balance date"), {
    target: { value: "2026-08-31" },
  });
  fireEvent.change(screen.getByLabelText("Opening balance, KDA 482M"), {
    target: { value: "15000" },
  });
  expect(
    screen.getByText("Opening balance KES 15,000 across 1 vehicle"),
  ).toBeInTheDocument();
  expect(
    screen.getByText("First run 26 Sep 2026, 2 vehicles"),
  ).toBeInTheDocument();
  expect(screen.getByText("KES 4,000")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() => expect(onSaved).toHaveBeenCalled());
  expect(sentBody(fetchMock)).toMatchObject({
    name: "Engine fund",
    kind: 2,
    amount: 4000,
    frequency: 2,
    day: 6,
    start: businessDate,
    end: null,
    allocations: [
      { vehicleId: "vehicle-1", amount: 2000 },
      { vehicleId: "vehicle-2", amount: 2000 },
    ],
    expenseItemId: null,
    condition: { min: 60000, days: 7 },
    opening: {
      date: "2026-08-31",
      amounts: [{ vehicleId: "vehicle-1", amount: 15000 }],
    },
  });
});

it("says what is missing, one thing at a time, as the design does", async () => {
  renderEditor({ kind: 2, fullScope: false });
  const save = () =>
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
  save();
  expect(await screen.findByRole("alert")).toHaveTextContent("Enter the name.");
  fireEvent.change(screen.getByLabelText("Name"), {
    target: { value: "Engine fund" },
  });
  save();
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Enter the amount.",
  );
  fireEvent.change(screen.getByLabelText("Amount per vehicle, KES"), {
    target: { value: "500" },
  });
  choose(screen.getByLabelText("Save"), "Only when revenue reaches a target");
  save();
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Enter the revenue target.",
  );
  fireEvent.change(screen.getByLabelText("Revenue per vehicle, KES"), {
    target: { value: "9000" },
  });
  save();
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Pick at least one vehicle.",
  );
  // Without the whole fleet in view there is no "All vehicles": the ticks alone.
  expect(screen.queryByLabelText("All vehicles")).not.toBeInTheDocument();
  fireEvent.click(screen.getByLabelText("KBZ 640Q"));
  fireEvent.click(screen.getByLabelText("Opening balance"));
  fireEvent.change(screen.getByLabelText("Opening balance date"), {
    target: { value: "2026-09-22" },
  });
  save();
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "The opening balance date is after today.",
  );
  expect(fetchMock).not.toHaveBeenCalled();
});

it("edits a scheduled expense keeping its start, with the amount per vehicle and the vehicles it had", async () => {
  const onSaved = renderEditor({ item });
  expect(
    screen.getByRole("dialog", { name: "Edit scheduled expense" }),
  ).toBeInTheDocument();
  expect(screen.getByLabelText("Amount per vehicle, KES")).toHaveValue("1,200");
  expect(screen.getByLabelText("Runs")).toHaveValue("2");
  expect(screen.getByLabelText("Day")).toHaveValue("6");
  expect(screen.getByLabelText("All vehicles")).toBeChecked();
  expect(screen.getByText(/^Next run /)).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Amount per vehicle, KES"), {
    target: { value: "1500" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() => expect(onSaved).toHaveBeenCalled());
  expect(String(fetchMock.mock.calls[0][0])).toBe(
    "/api/setup/recurring/item-1",
  );
  expect(sentBody(fetchMock)).toMatchObject({
    amount: 3000,
    start: "2026-08-01",
    end: null,
    allocations: [
      { vehicleId: "vehicle-1", amount: 1500 },
      { vehicleId: "vehicle-2", amount: 1500 },
    ],
  });
});

it("opens an item shared with vehicles outside your scope read-only", () => {
  renderEditor({ item: { ...item, partial: true }, canEdit: false });
  expect(
    screen.queryByRole("button", { name: "Save" }),
  ).not.toBeInTheDocument();
  expect(screen.getByLabelText("Amount per vehicle, KES")).toBeDisabled();
  expect(screen.getByLabelText("Runs")).toBeDisabled();
});

it("says the server's reason when a save is refused", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(
      async () =>
        new Response(
          JSON.stringify({
            title: "Invalid setup change",
            detail: "Only a saving has a revenue rule.",
          }),
          { status: 400 },
        ),
    ),
  );
  renderEditor({ item });
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Only a saving has a revenue rule.",
  );
});
