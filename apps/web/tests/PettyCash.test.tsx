import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import {
  PETTY_CASH_AMOUNT_ERROR,
  PETTY_CASH_UNITS_ERROR,
} from "@xcode/shared/pettyCash";

import { PettyCashPage } from "../components/pettycash/PettyCashPage";
import { clearDataCache } from "../lib/data";
import {
  BUSINESS_DATE,
  cash,
  credit,
  expense,
  json,
  overviewOf,
  paths,
  permissionsOf,
  servePettyCash,
  writes,
} from "./pettyCashServer";
import { renderInApp } from "./renderInApp";

afterEach(() => vi.unstubAllGlobals());

const REVIEWER = permissionsOf({
  canSpend: false,
  canApproveItem: true,
  canViewAll: true,
  approvalLimit: 5000,
});
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;

const entryReads = (fetcher: ReturnType<typeof servePettyCash>) =>
  paths(fetcher).filter((path) =>
    path.startsWith("/api/setup/pettycash/entries"),
  );

async function openDialog(name: string, opener: string) {
  fireEvent.click(await screen.findByRole("button", { name: opener }));
  return screen.findByRole("dialog", { name });
}

it("shows the four day figures from the overview and the day's expenses and credit notes, but no cash rows", async () => {
  const fetcher = servePettyCash({ entries: [expense(), credit(), cash()] });
  renderInApp(<PettyCashPage />);

  const figures = await screen.findByRole("group", { name: "Day figures" });
  expect(
    within(figures).getByText("Opening cash balance").nextSibling,
  ).toHaveTextContent("KES 12,000");
  expect(
    within(figures).getByText("Today, money out").nextSibling,
  ).toHaveTextContent("KES 4,000");
  expect(
    within(figures).getByText("Today, cash received").nextSibling,
  ).toHaveTextContent("KES 5,000");
  expect(
    within(figures).getByText("Closing cash balance").nextSibling,
  ).toHaveTextContent("KES 13,000");

  const tyres = await screen.findByRole("row", { name: /KDA 482M/ });
  expect(within(tyres).getByText("Tyres")).toBeInTheDocument();
  expect(within(tyres).getByText("Waiting")).toBeInTheDocument();
  const note = screen.getByRole("row", { name: /Mama Njeri/ });
  expect(within(note).getByText("Credit note")).toBeInTheDocument();
  expect(
    within(note).getByText("Refund for a double charge"),
  ).toBeInTheDocument();
  expect(screen.queryByText("Cash given")).not.toBeInTheDocument();

  expect(paths(fetcher)[0]).toBe("/api/setup/pettycash/overview");
  const read = entryReads(fetcher)[0];
  expect(read).toContain(`from=${BUSINESS_DATE}`);
  expect(read).toContain(`to=${BUSINESS_DATE}`);
  expect(read).toContain("kind=expense%2Ccredit");
});

it("writes a balance below zero with its minus sign, KES -750, in red", async () => {
  servePettyCash({
    answer: (path) =>
      path === "/api/setup/pettycash/overview"
        ? json({
            ...{
              businessDate: BUSINESS_DATE,
              date: BUSINESS_DATE,
              permissions: permissionsOf(),
              holders: [],
              floats: [],
            },
            period: "day",
            from: BUSINESS_DATE,
            to: BUSINESS_DATE,
            figures: {
              openingBalance: 100,
              cashReceived: -200,
              expenses: 650,
              creditNotes: 0,
              moneyOut: 650,
              closingBalance: -750,
            },
          })
        : undefined,
  });
  renderInApp(<PettyCashPage />);
  const figures = await screen.findByRole("group", { name: "Day figures" });
  const closing = within(figures).getByText("Closing cash balance").nextSibling;
  expect(closing).toHaveTextContent(/^KES -750$/);
  expect(closing).toHaveClass("text-red");
  expect(
    within(figures).getByText("Today, cash received").nextSibling,
  ).toHaveTextContent("KES -200 returned");
});

it("offers Approve and Send back only on entries the server lets this person review, and says so when one is above their limit", async () => {
  servePettyCash({
    permissions: REVIEWER,
    entries: [
      expense({ id: "e1", canReview: true }),
      expense({
        id: "e2",
        registration: "KDB 100X",
        unitAmount: 9000,
        total: 9000,
        aboveLimit: true,
      }),
      expense({ id: "e3", registration: "KDC 200Y", status: "approved" }),
    ],
  });
  renderInApp(<PettyCashPage />);

  const open = await screen.findByRole("row", { name: /KDA 482M/ });
  expect(
    within(open).getByRole("button", { name: "Approve KDA 482M, KES 3,500" }),
  ).toBeInTheDocument();
  expect(
    within(open).getByRole("button", { name: "Send back KDA 482M, KES 3,500" }),
  ).toBeInTheDocument();

  const above = screen.getByRole("row", { name: /KDB 100X/ });
  expect(within(above).getByText("Above your limit")).toBeInTheDocument();
  expect(within(above).queryByRole("button")).not.toBeInTheDocument();

  const approved = screen.getByRole("row", { name: /KDC 200Y/ });
  expect(within(approved).queryByRole("button")).not.toBeInTheDocument();
  expect(
    within(approved).queryByText("Above your limit"),
  ).not.toBeInTheDocument();
  expect(screen.getAllByRole("button", { name: /^Approve / })).toHaveLength(1);
});

it("shows Edit and Delete from the entry's own flags", async () => {
  servePettyCash({
    entries: [
      expense({ id: "e1", canEdit: true, canRemove: true }),
      expense({ id: "e2", registration: "KDB 100X" }),
    ],
  });
  renderInApp(<PettyCashPage />);
  const mine = await screen.findByRole("row", { name: /KDA 482M/ });
  expect(
    within(mine).getByRole("button", { name: "Edit KDA 482M, KES 3,500" }),
  ).toBeInTheDocument();
  expect(
    within(mine).getByRole("button", { name: "Delete KDA 482M, KES 3,500" }),
  ).toBeInTheDocument();
  expect(
    within(screen.getByRole("row", { name: /KDB 100X/ })).queryByRole("button"),
  ).not.toBeInTheDocument();
});

it("shows the comment on a sent-back entry", async () => {
  servePettyCash({
    entries: [
      expense({ status: "sentBack", sentBackNote: "Attach the receipt" }),
    ],
  });
  renderInApp(<PettyCashPage />);
  const row = await screen.findByRole("row", { name: /KDA 482M/ });
  expect(within(row).getByText("Sent back")).toBeInTheDocument();
  expect(
    within(row).getByText("Sent back: Attach the receipt"),
  ).toBeInTheDocument();
});

it("approves one entry with its version", async () => {
  const fetcher = servePettyCash({
    permissions: REVIEWER,
    entries: [expense({ canReview: true })],
  });
  renderInApp(<PettyCashPage />);
  fireEvent.click(
    await screen.findByRole("button", { name: "Approve KDA 482M, KES 3,500" }),
  );
  expect(
    await screen.findByText("Approved KDA 482M, KES 3,500."),
  ).toBeInTheDocument();
  expect(writes(fetcher)).toEqual([
    {
      path: "/api/setup/pettycash/entries/e1/approve",
      method: "POST",
      body: { version: 3 },
    },
  ]);
});

it("will not send an entry back without a comment", async () => {
  const fetcher = servePettyCash({
    permissions: REVIEWER,
    entries: [expense({ canReview: true })],
  });
  renderInApp(<PettyCashPage />);
  fireEvent.click(
    await screen.findByRole("button", {
      name: "Send back KDA 482M, KES 3,500",
    }),
  );
  const dialog = await screen.findByRole("dialog", { name: "Send back" });

  fireEvent.click(within(dialog).getByRole("button", { name: "Send back" }));
  expect(
    await within(dialog).findByText("Say what the manager should fix."),
  ).toBeInTheDocument();
  expect(writes(fetcher)).toEqual([]);

  fireEvent.change(within(dialog).getByLabelText("Comment"), {
    target: { value: "Attach the receipt" },
  });
  fireEvent.click(within(dialog).getByRole("button", { name: "Send back" }));
  expect(
    await screen.findByText("Sent back to Grace Wanjiru."),
  ).toBeInTheDocument();
  expect(writes(fetcher)).toEqual([
    {
      path: "/api/setup/pettycash/entries/e1/send-back",
      method: "POST",
      body: { version: 3, comment: "Attach the receipt" },
    },
  ]);
});

it("will not delete an entry without a reason", async () => {
  const fetcher = servePettyCash({ entries: [expense({ canRemove: true })] });
  renderInApp(<PettyCashPage />);
  fireEvent.click(
    await screen.findByRole("button", { name: "Delete KDA 482M, KES 3,500" }),
  );
  const dialog = await screen.findByRole("dialog", {
    name: "Delete this entry",
  });

  fireEvent.click(within(dialog).getByRole("button", { name: "Delete" }));
  expect(
    await within(dialog).findByText("Say why this entry is being deleted."),
  ).toBeInTheDocument();
  expect(writes(fetcher)).toEqual([]);

  fireEvent.change(within(dialog).getByLabelText("Reason for deleting"), {
    target: { value: "Recorded twice" },
  });
  fireEvent.click(within(dialog).getByRole("button", { name: "Delete" }));
  expect(await screen.findByText("Entry deleted.")).toBeInTheDocument();
  expect(writes(fetcher)).toEqual([
    {
      path: "/api/setup/pettycash/entries/e1/remove",
      method: "POST",
      body: { version: 3, reason: "Recorded twice" },
    },
  ]);
});

it("needs a payee and a reason on a credit note, takes a negative amount and refuses zero", async () => {
  const fetcher = servePettyCash();
  renderInApp(<PettyCashPage />);
  const dialog = await openDialog("Add credit note", "Credit note");
  const add = () =>
    fireEvent.click(within(dialog).getByRole("button", { name: "Add" }));

  add();
  expect(
    await within(dialog).findByText("Enter who was paid."),
  ).toBeInTheDocument();
  expect(
    within(dialog).getByText("Say why the money was paid out."),
  ).toBeInTheDocument();
  expect(
    within(dialog).getAllByText(PETTY_CASH_AMOUNT_ERROR).length,
  ).toBeGreaterThan(0);
  expect(writes(fetcher)).toEqual([]);

  fireEvent.change(within(dialog).getByLabelText("Paid to"), {
    target: { value: "Mama Njeri" },
  });
  fireEvent.change(within(dialog).getByLabelText("Reason"), {
    target: { value: "Double charge" },
  });
  fireEvent.change(within(dialog).getByLabelText("Amount"), {
    target: { value: "0" },
  });
  add();
  expect(
    await within(dialog).findByText(PETTY_CASH_AMOUNT_ERROR),
  ).toBeInTheDocument();
  expect(writes(fetcher)).toEqual([]);

  fireEvent.change(within(dialog).getByLabelText("Amount"), {
    target: { value: "-500" },
  });
  add();
  expect(
    await screen.findByText(
      "Credit note of KES -500 to Mama Njeri recorded. It waits for approval.",
    ),
  ).toBeInTheDocument();
  const [save] = writes(fetcher);
  expect(save.path).toBe("/api/setup/pettycash/entries");
  expect(save.method).toBe("POST");
  expect(save.body).toEqual({
    id: expect.stringMatching(UUID),
    kind: "credit",
    date: BUSINESS_DATE,
    unitAmount: -500,
    payee: "Mama Njeri",
    note: "Double charge",
    reimbursable: false,
  });
});

it("lets an issuer pick the float for a credit note and sends it", async () => {
  const fetcher = servePettyCash({
    permissions: permissionsOf({
      canSpend: false,
      canIssue: true,
      holderId: null,
    }),
  });
  renderInApp(<PettyCashPage />);
  const dialog = await openDialog("Add credit note", "Credit note");
  await within(dialog).findByRole("option", { name: "Peter Otieno" });
  fireEvent.change(within(dialog).getByLabelText("Manager"), {
    target: { value: "h2" },
  });
  fireEvent.change(within(dialog).getByLabelText("Paid to"), {
    target: { value: "Fuel station" },
  });
  fireEvent.change(within(dialog).getByLabelText("Reason"), {
    target: { value: "Fuel" },
  });
  fireEvent.change(within(dialog).getByLabelText("Amount"), {
    target: { value: "1,200.50" },
  });
  fireEvent.click(
    within(dialog).getByLabelText("The payee should pay this back"),
  );
  fireEvent.click(within(dialog).getByRole("button", { name: "Add" }));
  await screen.findByText(
    /Credit note of KES 1,200.50 to Fuel station recorded/,
  );
  expect(writes(fetcher)[0].body).toMatchObject({
    holderId: "h2",
    unitAmount: 1200.5,
    reimbursable: true,
  });
});

it("shows the live total of an expense and sends units, amount, vehicle and item with a fresh id", async () => {
  const fetcher = servePettyCash();
  renderInApp(<PettyCashPage />);
  const dialog = await openDialog("Add expense", "Expense");
  await within(dialog).findByRole("option", {
    name: "KDA 482M, Rongai Express",
  });
  expect(
    within(dialog).getByRole("group", { name: "Garage and repairs" }),
  ).toBeInTheDocument();

  fireEvent.click(within(dialog).getByRole("button", { name: "Add" }));
  expect(
    await within(dialog).findByText("Choose the vehicle."),
  ).toBeInTheDocument();
  expect(
    within(dialog).getByText("Choose what it was for."),
  ).toBeInTheDocument();
  expect(writes(fetcher)).toEqual([]);

  fireEvent.change(within(dialog).getByLabelText("Units"), {
    target: { value: "4" },
  });
  fireEvent.change(within(dialog).getByLabelText("Amount each"), {
    target: { value: "1250" },
  });
  expect(within(dialog).getByText(/Total KES 5,000\./)).toBeInTheDocument();
  fireEvent.change(within(dialog).getByLabelText("Vehicle"), {
    target: { value: "v1" },
  });
  fireEvent.change(within(dialog).getByLabelText("What it was for"), {
    target: { value: "i1" },
  });
  fireEvent.change(within(dialog).getByLabelText("Note"), {
    target: { value: "Front left" },
  });
  fireEvent.click(within(dialog).getByRole("button", { name: "Add" }));

  expect(
    await screen.findByText(
      "KES 5,000 recorded on KDA 482M. It waits for approval.",
    ),
  ).toBeInTheDocument();
  expect(writes(fetcher)[0].body).toEqual({
    id: expect.stringMatching(UUID),
    kind: "expense",
    date: BUSINESS_DATE,
    vehicleId: "v1",
    expenseItemId: "i1",
    units: 4,
    unitAmount: 1250,
    note: "Front left",
  });
});

async function fillExpense(dialog: HTMLElement, units: string, amount: string) {
  await within(dialog).findByRole("option", {
    name: "KDA 482M, Rongai Express",
  });
  fireEvent.change(within(dialog).getByLabelText("Units"), {
    target: { value: units },
  });
  fireEvent.change(within(dialog).getByLabelText("Amount each"), {
    target: { value: amount },
  });
  fireEvent.change(within(dialog).getByLabelText("Vehicle"), {
    target: { value: "v1" },
  });
  fireEvent.change(within(dialog).getByLabelText("What it was for"), {
    target: { value: "i1" },
  });
}

it("takes part of a unit, shows the exact live total and sends the units as a number", async () => {
  const fetcher = servePettyCash();
  renderInApp(<PettyCashPage />);
  const dialog = await openDialog("Add expense", "Expense");
  await fillExpense(dialog, "11.875", "182.40");
  expect(within(dialog).getByLabelText("Units")).toHaveAttribute(
    "inputmode",
    "decimal",
  );
  expect(within(dialog).getByText(/Total KES 2,166\./)).toBeInTheDocument();
  fireEvent.click(within(dialog).getByRole("button", { name: "Add" }));
  expect(
    await screen.findByText(
      "KES 2,166 recorded on KDA 482M. It waits for approval.",
    ),
  ).toBeInTheDocument();
  expect(writes(fetcher)[0].body).toMatchObject({
    kind: "expense",
    units: 11.875,
    unitAmount: 182.4,
  });
});

it("accepts 4.5 units and more than a thousand units", async () => {
  const fetcher = servePettyCash();
  renderInApp(<PettyCashPage />);
  const dialog = await openDialog("Add expense", "Expense");
  await fillExpense(dialog, "4.5", "900");
  expect(within(dialog).getByText(/Total KES 4,050\./)).toBeInTheDocument();
  fireEvent.click(within(dialog).getByRole("button", { name: "Add" }));
  await screen.findByText(/recorded on KDA 482M/);
  expect(writes(fetcher)[0].body.units).toBe(4.5);

  fireEvent.click(await screen.findByRole("button", { name: "Expense" }));
  const again = await screen.findByRole("dialog", { name: "Add expense" });
  await fillExpense(again, "1001", "10");
  fireEvent.click(within(again).getByRole("button", { name: "Add" }));
  await waitFor(() => expect(writes(fetcher)).toHaveLength(2));
  expect(writes(fetcher)[1].body.units).toBe(1001);
});

it.each(["0", "1.2345", "", "-2"])(
  "refuses units of %j and sends nothing",
  async (units) => {
    const fetcher = servePettyCash();
    renderInApp(<PettyCashPage />);
    const dialog = await openDialog("Add expense", "Expense");
    await fillExpense(dialog, units, "10");
    fireEvent.click(within(dialog).getByRole("button", { name: "Add" }));
    expect(
      await within(dialog).findByText(PETTY_CASH_UNITS_ERROR),
    ).toBeInTheDocument();
    expect(writes(fetcher)).toEqual([]);
  },
);

it("refuses a date after the business date", async () => {
  const fetcher = servePettyCash();
  renderInApp(<PettyCashPage />);
  const dialog = await openDialog("Add expense", "Expense");
  await fillExpense(dialog, "2", "10");
  fireEvent.change(within(dialog).getByLabelText("Date"), {
    target: { value: "2026-10-01" },
  });
  fireEvent.click(within(dialog).getByRole("button", { name: "Add" }));
  expect(
    await within(dialog).findByText("The date cannot be after today."),
  ).toBeInTheDocument();
  expect(writes(fetcher)).toEqual([]);
});

it.each([0, -300])(
  "sends an expense and a credit note when the float holds %d, with no refusal of its own",
  async (balance) => {
    const [first] = overviewOf(permissionsOf()).floats;
    const fetcher = servePettyCash({ floats: [{ ...first, balance }] });
    renderInApp(<PettyCashPage />);
    const dialog = await openDialog("Add expense", "Expense");
    await fillExpense(dialog, "1", "500");
    fireEvent.click(within(dialog).getByRole("button", { name: "Add" }));
    await screen.findByText(
      "KES 500 recorded on KDA 482M. It waits for approval.",
    );

    const note = await openDialog("Add credit note", "Credit note");
    fireEvent.change(within(note).getByLabelText("Paid to"), {
      target: { value: "Mama Njeri" },
    });
    fireEvent.change(within(note).getByLabelText("Reason"), {
      target: { value: "Double charge" },
    });
    fireEvent.change(within(note).getByLabelText("Amount"), {
      target: { value: "800" },
    });
    fireEvent.click(within(note).getByRole("button", { name: "Add" }));
    await screen.findByText(/Credit note of KES 800 to Mama Njeri recorded/);
    expect(writes(fetcher).map((write) => write.body.kind)).toEqual([
      "expense",
      "credit",
    ]);
  },
);

it("reports a refused save with role alert and keeps one id for the retry", async () => {
  let refused = true;
  const fetcher = servePettyCash({
    answer: (path, init) => {
      if (
        init?.method === "POST" &&
        path === "/api/setup/pettycash/entries" &&
        refused
      ) {
        refused = false;
        return json(
          {
            title: "Invalid",
            detail: "This takes the float below zero. Ask for cash first.",
            balanceAfter: -300,
          },
          400,
        );
      }
    },
  });
  renderInApp(<PettyCashPage />);
  const dialog = await openDialog("Add expense", "Expense");
  await within(dialog).findByRole("option", {
    name: "KDA 482M, Rongai Express",
  });
  fireEvent.change(within(dialog).getByLabelText("Amount each"), {
    target: { value: "300" },
  });
  fireEvent.change(within(dialog).getByLabelText("Vehicle"), {
    target: { value: "v1" },
  });
  fireEvent.change(within(dialog).getByLabelText("What it was for"), {
    target: { value: "i3" },
  });
  fireEvent.click(within(dialog).getByRole("button", { name: "Add" }));

  const alert = await within(dialog).findByRole("alert");
  expect(alert).toHaveTextContent(
    "This takes the float below zero. Ask for cash first.",
  );
  fireEvent.click(within(dialog).getByRole("button", { name: "Add" }));
  await screen.findByText(/recorded on KDA 482M/);
  const [first, second] = writes(fetcher);
  expect(first.body.id).toMatch(UUID);
  expect(second.body.id).toBe(first.body.id);
});

it("still sends a fresh id from a page opened over plain http, where crypto.randomUUID does not exist", async () => {
  const real = globalThis.crypto;
  vi.stubGlobal("crypto", { getRandomValues: real.getRandomValues.bind(real) });
  const fetcher = servePettyCash();
  renderInApp(<PettyCashPage />);
  const dialog = await openDialog("Add expense", "Expense");
  await within(dialog).findByRole("option", {
    name: "KDA 482M, Rongai Express",
  });
  fireEvent.change(within(dialog).getByLabelText("Amount each"), {
    target: { value: "300" },
  });
  fireEvent.change(within(dialog).getByLabelText("Vehicle"), {
    target: { value: "v1" },
  });
  fireEvent.change(within(dialog).getByLabelText("What it was for"), {
    target: { value: "i3" },
  });
  fireEvent.click(within(dialog).getByRole("button", { name: "Add" }));
  await screen.findByText(/recorded on KDA 482M/);
  expect(writes(fetcher)[0].body.id).toMatch(UUID);
});

it("changes an entry with its version and without a new id", async () => {
  const fetcher = servePettyCash({
    entries: [expense({ canEdit: true, version: 7, unitAmount: 3500 })],
  });
  renderInApp(<PettyCashPage />);
  fireEvent.click(
    await screen.findByRole("button", { name: "Edit KDA 482M, KES 3,500" }),
  );
  const dialog = await screen.findByRole("dialog", { name: "Edit expense" });
  expect(within(dialog).getByLabelText("Amount each")).toHaveValue("3500");
  fireEvent.change(within(dialog).getByLabelText("Amount each"), {
    target: { value: "3000" },
  });
  fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));
  await screen.findByText("Saved. It waits for approval.");
  const [save] = writes(fetcher);
  expect(save.path).toBe("/api/setup/pettycash/entries/e1");
  expect(save.method).toBe("PUT");
  expect(save.body).toEqual({
    version: 7,
    kind: "expense",
    date: BUSINESS_DATE,
    vehicleId: "v1",
    expenseItemId: "i1",
    units: 1,
    unitAmount: 3000,
    note: null,
  });
});

it("says what changed on a 409 and loads the list again", async () => {
  const fetcher = servePettyCash({
    permissions: REVIEWER,
    entries: [expense({ canReview: true })],
    answer: (path, init) =>
      init?.method === "POST" && path.endsWith("/approve")
        ? json(
            {
              title: "Conflict",
              detail:
                "Peter Otieno changed this entry a moment ago. Check it and try again.",
            },
            409,
          )
        : undefined,
  });
  renderInApp(<PettyCashPage />);
  fireEvent.click(
    await screen.findByRole("button", { name: "Approve KDA 482M, KES 3,500" }),
  );

  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Peter Otieno changed this entry a moment ago. Check it and try again.",
  );
  await waitFor(() => expect(entryReads(fetcher).length).toBeGreaterThan(1));
  await waitFor(() =>
    expect(
      paths(fetcher).filter((path) => path === "/api/setup/pettycash/overview")
        .length,
    ).toBeGreaterThan(1),
  );
});

it("closes the dialog on a 409, shows the message on the page and loads the list again", async () => {
  const fetcher = servePettyCash({
    entries: [expense({ canRemove: true })],
    answer: (path, init) =>
      init?.method === "POST" && path.endsWith("/remove")
        ? json(
            {
              title: "Conflict",
              detail: "This entry was changed. Check it and try again.",
            },
            409,
          )
        : undefined,
  });
  renderInApp(<PettyCashPage />);
  fireEvent.click(
    await screen.findByRole("button", { name: "Delete KDA 482M, KES 3,500" }),
  );
  const dialog = await screen.findByRole("dialog", {
    name: "Delete this entry",
  });
  fireEvent.change(within(dialog).getByLabelText("Reason for deleting"), {
    target: { value: "Recorded twice" },
  });
  fireEvent.click(within(dialog).getByRole("button", { name: "Delete" }));

  expect(await screen.findByRole("alert")).toHaveTextContent(
    "This entry was changed. Check it and try again.",
  );
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  await waitFor(() => expect(entryReads(fetcher).length).toBeGreaterThan(1));
});

it("moves a day at a time and stops at the business date", async () => {
  const fetcher = servePettyCash();
  renderInApp(<PettyCashPage />);
  const next = await screen.findByRole("button", { name: "Next day" });
  await screen.findByText("Wed 30 Sep 2026");
  expect(next).toBeDisabled();

  fireEvent.click(screen.getByRole("button", { name: "Previous day" }));
  expect(await screen.findByText("Tue 29 Sep 2026")).toBeInTheDocument();
  await waitFor(() =>
    expect(
      entryReads(fetcher).some(
        (path) =>
          path.includes("from=2026-09-29") && path.includes("to=2026-09-29"),
      ),
    ).toBe(true),
  );
  expect(paths(fetcher)).toContain(
    "/api/setup/pettycash/overview?date=2026-09-29",
  );
  expect(screen.getByRole("button", { name: "Next day" })).toBeEnabled();
});

const showWeek = () =>
  fireEvent.click(
    within(screen.getByRole("group", { name: "Period" })).getByRole("button", {
      name: "Week",
    }),
  );

it("shows a week: asks for the week's figures and entries, labels them, adds a Date column and drops Approve day", async () => {
  const fetcher = servePettyCash({
    permissions: permissionsOf({ canApproveDay: true, canApproveItem: true }),
    entries: [
      expense({ id: "e1", date: "2026-09-28" }),
      expense({ id: "e2", date: "2026-09-30", registration: "KDB 100X" }),
      expense({ id: "e3", date: "2026-09-27", registration: "KDC 200Y" }),
      cash({ id: "k1", date: "2026-09-29" }),
    ],
  });
  renderInApp(<PettyCashPage />);
  await screen.findByRole("row", { name: /KDB 100X/ });
  expect(
    screen.queryByRole("row", { name: /KDA 482M/ }),
  ).not.toBeInTheDocument();
  const period = screen.getByRole("group", { name: "Period" });
  expect(within(period).getByRole("button", { name: "Day" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  expect(
    screen.getByRole("button", { name: "Approve day" }),
  ).toBeInTheDocument();
  expect(
    screen.queryByRole("columnheader", { name: "Date" }),
  ).not.toBeInTheDocument();
  expect(paths(fetcher).some((path) => path.includes("period="))).toBe(false);

  showWeek();
  expect(within(period).getByRole("button", { name: "Week" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  const figures = await screen.findByRole("group", { name: "Week figures" });
  expect(
    within(figures).getByText("This week, money out").nextSibling,
  ).toHaveTextContent("KES 16,000");
  expect(
    within(figures).getByText("This week, cash received").nextSibling,
  ).toHaveTextContent("KES 21,000");
  expect(
    within(figures).getByText("Opening cash balance").nextSibling,
  ).toHaveTextContent("KES 9,000");
  expect(paths(fetcher)).toContain(`/api/setup/pettycash/overview?period=week`);
  await waitFor(() =>
    expect(
      entryReads(fetcher).some(
        (path) =>
          path.includes("from=2026-09-28") &&
          path.includes("to=2026-10-04") &&
          path.includes("kind=expense%2Ccredit"),
      ),
    ).toBe(true),
  );
  expect(await screen.findByText("28 Sep to 4 Oct 2026")).toBeInTheDocument();

  expect(
    await screen.findByRole("columnheader", { name: "Date" }),
  ).toBeInTheDocument();
  expect(
    within(await screen.findByRole("row", { name: /KDA 482M/ })).getByText(
      "28 Sep 2026",
    ),
  ).toBeInTheDocument();
  expect(
    within(screen.getByRole("row", { name: /KDB 100X/ })).getByText(
      "30 Sep 2026",
    ),
  ).toBeInTheDocument();
  expect(
    screen.queryByRole("row", { name: /KDC 200Y/ }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "Approve day" }),
  ).not.toBeInTheDocument();

  fireEvent.click(screen.getByRole("tab", { name: "Cash received" }));
  await waitFor(() =>
    expect(
      entryReads(fetcher).some(
        (path) =>
          path.includes("kind=cash") &&
          path.includes("from=2026-09-28") &&
          path.includes("to=2026-10-04"),
      ),
    ).toBe(true),
  );
  expect(
    within(await screen.findByRole("row", { name: /Cash given/ })).getByText(
      "29 Sep 2026",
    ),
  ).toBeInTheDocument();
  expect(
    screen.getByRole("columnheader", { name: "Date" }),
  ).toBeInTheDocument();
  expect(within(period).getByRole("button", { name: "Week" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );

  fireEvent.click(within(period).getByRole("button", { name: "Day" }));
  expect(
    await screen.findByRole("button", { name: "Approve day" }),
  ).toBeInTheDocument();
  expect(await screen.findByText("Wed 30 Sep 2026")).toBeInTheDocument();
  // Cash received always shows its dates, as in the design; expenses show them only for a week.
  expect(
    screen.getByRole("columnheader", { name: "Date" }),
  ).toBeInTheDocument();
  fireEvent.click(screen.getByRole("tab", { name: "Expenses" }));
  await waitFor(() =>
    expect(
      screen.queryByRole("columnheader", { name: "Date" }),
    ).not.toBeInTheDocument(),
  );
});

it("moves a week at a time, stops at the week of the business date and keeps the week when the date moves", async () => {
  const fetcher = servePettyCash();
  renderInApp(<PettyCashPage />);
  await screen.findByRole("button", { name: "Next day" });
  showWeek();
  const next = await screen.findByRole("button", { name: "Next week" });
  await screen.findByText("28 Sep to 4 Oct 2026");
  expect(next).toBeDisabled();

  fireEvent.click(screen.getByRole("button", { name: "Previous week" }));
  expect(await screen.findByText("21 to 27 Sep 2026")).toBeInTheDocument();
  expect(paths(fetcher)).toContain(
    "/api/setup/pettycash/overview?date=2026-09-21&period=week",
  );
  await waitFor(() =>
    expect(
      entryReads(fetcher).some(
        (path) =>
          path.includes("from=2026-09-21") && path.includes("to=2026-09-27"),
      ),
    ).toBe(true),
  );
  expect(
    await screen.findByRole("group", { name: "Week figures" }),
  ).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Next week" })).toBeEnabled();

  fireEvent.click(await screen.findByRole("button", { name: "Expense" }));
  expect(await screen.findByLabelText("Date")).toHaveValue("2026-09-27");
  fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

  fireEvent.click(screen.getByRole("button", { name: "Next week" }));
  expect(await screen.findByText("28 Sep to 4 Oct 2026")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Next week" })).toBeDisabled();
});

it("labels the figures of a week that is over by its first day", async () => {
  servePettyCash();
  renderInApp(<PettyCashPage />);
  await screen.findByRole("button", { name: "Next day" });
  showWeek();
  fireEvent.click(await screen.findByRole("button", { name: "Previous week" }));
  const figures = await screen.findByRole("group", { name: "Week figures" });
  expect(
    await within(figures).findByText("Week of 21 Sep 2026, money out"),
  ).toBeInTheDocument();
  expect(within(figures).queryByText(/This week/)).not.toBeInTheDocument();
});

it("shows units as entered, with up to three decimals and grouping", async () => {
  servePettyCash({
    entries: [
      expense({ id: "e1", units: 11.875 }),
      expense({ id: "e2", registration: "KDB 100X", units: 4.5 }),
      expense({ id: "e3", registration: "KDC 200Y", units: 1001 }),
    ],
  });
  renderInApp(<PettyCashPage />);
  expect(
    within(await screen.findByRole("row", { name: /KDA 482M/ })).getByText(
      "11.875",
    ),
  ).toBeInTheDocument();
  expect(
    within(screen.getByRole("row", { name: /KDB 100X/ })).getByText("4.5"),
  ).toBeInTheDocument();
  expect(
    within(screen.getByRole("row", { name: /KDC 200Y/ })).getByText("1,001"),
  ).toBeInTheDocument();
});

it("offers the manager filter only to someone who may see every float, and sends it", async () => {
  const fetcher = servePettyCash({ permissions: REVIEWER });
  const first = renderInApp(<PettyCashPage />);
  const manager = await screen.findByRole("combobox", { name: "Manager" });
  fireEvent.change(manager, { target: { value: "h2" } });
  await waitFor(() =>
    expect(paths(fetcher)).toContain(
      "/api/setup/pettycash/overview?holderId=h2",
    ),
  );
  await waitFor(() =>
    expect(
      entryReads(fetcher).some((path) => path.includes("holderId=h2")),
    ).toBe(true),
  );
  first.unmount();
  clearDataCache();

  servePettyCash({ permissions: permissionsOf() });
  renderInApp(<PettyCashPage />);
  await screen.findByRole("button", { name: "Expense" });
  expect(
    screen.queryByRole("combobox", { name: "Manager" }),
  ).not.toBeInTheDocument();
});

it("filters expenses by status and by search", async () => {
  const fetcher = servePettyCash({
    entries: [expense({ status: "approved" })],
  });
  renderInApp(<PettyCashPage />);
  await screen.findByRole("row", { name: /KDA 482M/ });
  fireEvent.change(screen.getByRole("combobox", { name: "Show" }), {
    target: { value: "waiting" },
  });
  await waitFor(() =>
    expect(
      entryReads(fetcher).some((path) => path.includes("status=waiting")),
    ).toBe(true),
  );
  expect(
    await screen.findByText("Nothing recorded on this day."),
  ).toBeInTheDocument();

  fireEvent.change(screen.getByRole("searchbox", { name: "Search" }), {
    target: { value: "tyres" },
  });
  await waitFor(() =>
    expect(entryReads(fetcher).some((path) => path.includes("q=tyres"))).toBe(
      true,
    ),
  );
});

it("opens on the waiting filter when asked to", async () => {
  const fetcher = servePettyCash({ entries: [expense()] });
  renderInApp(<PettyCashPage initialStatus="waiting" />);
  expect(await screen.findByRole("combobox", { name: "Show" })).toHaveValue(
    "waiting",
  );
  await waitFor(() =>
    expect(entryReads(fetcher)[0]).toContain("status=waiting"),
  );
});

it("keeps Expense, Credit note, Cash and Approve day to the permissions the server reports", async () => {
  servePettyCash({
    permissions: permissionsOf({
      canSpend: false,
      canIssue: false,
      canApproveDay: true,
      canApproveItem: true,
    }),
  });
  const first = renderInApp(<PettyCashPage />);
  expect(
    await screen.findByRole("button", { name: "Approve day" }),
  ).toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "Expense" }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "Credit note" }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "Cash" }),
  ).not.toBeInTheDocument();
  first.unmount();
  clearDataCache();

  servePettyCash({
    permissions: permissionsOf({ canSpend: true, canIssue: true }),
  });
  renderInApp(<PettyCashPage />);
  expect(
    await screen.findByRole("button", { name: "Expense" }),
  ).toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: "Credit note" }),
  ).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Cash" })).toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "Approve day" }),
  ).not.toBeInTheDocument();
});

it("approves a day for the chosen manager and reports what was left", async () => {
  const fetcher = servePettyCash({
    permissions: permissionsOf({
      canSpend: false,
      canViewAll: true,
      canApproveItem: true,
      canApproveDay: true,
    }),
    answer: (path, init) =>
      init?.method === "POST" && path === "/api/setup/pettycash/approve-day"
        ? json({ approved: 2, total: 6000, skipped: 1 })
        : undefined,
  });
  renderInApp(<PettyCashPage />);
  fireEvent.change(await screen.findByRole("combobox", { name: "Manager" }), {
    target: { value: "h2" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Approve day" }));
  expect(
    await screen.findByText(
      "Approved 2 entries, KES 6,000. 1 entry was left for someone else to approve.",
    ),
  ).toBeInTheDocument();
  expect(writes(fetcher)).toEqual([
    {
      path: "/api/setup/pettycash/approve-day",
      method: "POST",
      body: { date: BUSINESS_DATE, holderId: "h2" },
    },
  ]);
});

it("lists cash on the Cash received tab with the floats, and moves between tabs with the arrow keys", async () => {
  const fetcher = servePettyCash({
    permissions: permissionsOf({ canIssue: true }),
    entries: [
      expense(),
      cash({ canEdit: true, canRemove: true }),
      cash({ id: "k2", total: -300, unitAmount: -300, note: "Returned" }),
    ],
  });
  renderInApp(<PettyCashPage />);
  const expenses = await screen.findByRole("tab", { name: "Expenses" });
  expect(expenses).toHaveAttribute("aria-selected", "true");
  expenses.focus();
  fireEvent.keyDown(expenses, { key: "ArrowRight" });

  const tab = await screen.findByRole("tab", { name: "Cash received" });
  expect(tab).toHaveAttribute("aria-selected", "true");
  expect(tab).toHaveFocus();
  expect(screen.getByRole("tabpanel")).toHaveAttribute(
    "aria-labelledby",
    tab.id,
  );
  expect(await screen.findByText("Cash given")).toBeInTheDocument();
  expect(screen.getByText("Returned")).toBeInTheDocument();
  expect(screen.getByText("Less KES 300")).toBeInTheDocument();
  expect(screen.queryByText("KDA 482M")).not.toBeInTheDocument();
  expect(
    screen.getByRole("button", {
      name: "Edit cash for Grace Wanjiru, KES 5,000",
    }),
  ).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Floats" })).toBeInTheDocument();
  const floats = screen
    .getByRole("columnheader", { name: "Cash in hand" })
    .closest("table")!;
  expect(within(floats).getByText("KES 12,500")).toBeInTheDocument();
  expect(
    entryReads(fetcher).some(
      (path) => path.includes("kind=cash") && !path.includes("expense"),
    ),
  ).toBe(true);

  fireEvent.keyDown(tab, { key: "ArrowLeft" });
  expect(await screen.findByRole("tab", { name: "Expenses" })).toHaveAttribute(
    "aria-selected",
    "true",
  );
});

it("stacks the tabs beside the figure cards, as in the design, and moves between them with up and down", async () => {
  servePettyCash();
  renderInApp(<PettyCashPage />);
  const figures = await screen.findByRole("group", { name: "Day figures" });
  const tabs = screen.getByRole("tablist", { name: "Petty cash" });
  expect(tabs).toHaveAttribute("aria-orientation", "vertical");
  expect(tabs.parentElement).toBe(figures.parentElement?.parentElement);
  expect(
    within(screen.getByRole("tabpanel")).queryByRole("group", {
      name: "Day figures",
    }),
  ).not.toBeInTheDocument();
  for (const label of [
    "Opening cash balance",
    "Today, money out",
    "Today, cash received",
    "Closing cash balance",
  ])
    expect(within(figures).getByText(label)).toBeInTheDocument();

  const expenses = screen.getByRole("tab", { name: "Expenses" });
  fireEvent.keyDown(expenses, { key: "ArrowDown" });
  expect(
    await screen.findByRole("tab", { name: "Cash received" }),
  ).toHaveAttribute("aria-selected", "true");
  fireEvent.keyDown(screen.getByRole("tab", { name: "Cash received" }), {
    key: "ArrowUp",
  });
  expect(await screen.findByRole("tab", { name: "Expenses" })).toHaveAttribute(
    "aria-selected",
    "true",
  );
});

it("puts the toolbar buttons in the design's order", async () => {
  servePettyCash({
    permissions: permissionsOf({
      canIssue: true,
      canApproveDay: true,
      canApproveItem: true,
    }),
  });
  renderInApp(<PettyCashPage />);
  await screen.findByRole("button", { name: "Approve day" });
  const names = screen
    .getAllByRole("button")
    .map((button) => button.textContent)
    .filter((name) =>
      ["Expense", "Cash", "Credit note", "Approve day"].includes(name ?? ""),
    );
  expect(names).toEqual(["Expense", "Cash", "Credit note", "Approve day"]);
});

it("gives cash to a chosen manager, and takes it back with a minus sign", async () => {
  const fetcher = servePettyCash({
    permissions: permissionsOf({
      canSpend: false,
      canIssue: true,
      holderId: null,
    }),
  });
  renderInApp(<PettyCashPage />);
  const dialog = await openDialog("Add cash", "Cash");
  await within(dialog).findByRole("option", { name: "Peter Otieno" });
  fireEvent.click(within(dialog).getByRole("button", { name: "Add" }));
  expect(
    await within(dialog).findByText("Choose the manager."),
  ).toBeInTheDocument();
  expect(writes(fetcher)).toEqual([]);

  fireEvent.change(within(dialog).getByLabelText("Manager"), {
    target: { value: "h2" },
  });
  fireEvent.change(within(dialog).getByLabelText("Amount"), {
    target: { value: "-300" },
  });
  fireEvent.click(within(dialog).getByRole("button", { name: "Add" }));
  expect(
    await screen.findByText("KES 300 taken back from Peter Otieno."),
  ).toBeInTheDocument();
  expect(writes(fetcher)[0].body).toEqual({
    id: expect.stringMatching(UUID),
    kind: "cash",
    holderId: "h2",
    date: BUSINESS_DATE,
    unitAmount: -300,
    note: null,
  });
});
