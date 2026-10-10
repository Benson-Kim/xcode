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
import { choose, listboxOf, offered, optionsOf, pick } from "./searchSelect";

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

// Credit notes and cash are recorded from the Cash received view.
const showCash = async () =>
  fireEvent.click(await screen.findByRole("tab", { name: "Cash received" }));

// The live total of an expense, under its amounts.
const totalOf = (dialog: HTMLElement) =>
  within(dialog).getByText("Total amount").nextSibling;

it("shows the four day figures from the overview and the day's expenses and credit notes, but no cash rows", async () => {
  const fetcher = servePettyCash({ entries: [expense(), credit(), cash()] });
  renderInApp(<PettyCashPage />);

  // Cash balance = Opening balance + Cash issued - Expenses - Credit notes.
  const figures = await screen.findByRole("group", { name: "Day figures" });
  const figure = (label: string) =>
    within(figures).getByText(label).nextSibling;
  expect(figure("Cash balance")).toHaveTextContent("KES 13,000");
  expect(figure("Opening balance")).toHaveTextContent(/^12,000$/);
  expect(figure("Cash issued")).toHaveTextContent(/^5,000$/);
  expect(figure("Expenses")).toHaveTextContent(/^3,500$/);
  expect(figure("Credit notes")).toHaveTextContent(/^500$/);

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
  const closing = within(figures).getByText("Cash balance").nextSibling;
  expect(closing).toHaveTextContent(/^KES -750$/);
  expect(closing).toHaveClass("neg");
  expect(
    within(figures).getByText("Cash issued").nextSibling,
  ).toHaveTextContent(/^-200 returned$/);
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
  await showCash();
  const dialog = await openDialog("Credit note", "Credit note");
  const add = () =>
    fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));

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
  fireEvent.change(within(dialog).getByLabelText("Amount, KES"), {
    target: { value: "0" },
  });
  add();
  expect(
    await within(dialog).findByText(PETTY_CASH_AMOUNT_ERROR),
  ).toBeInTheDocument();
  expect(writes(fetcher)).toEqual([]);

  fireEvent.change(within(dialog).getByLabelText("Amount, KES"), {
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
  await showCash();
  const dialog = await openDialog("Credit note", "Credit note");
  await offered(within(dialog).getByLabelText("Manager"), "Peter Otieno");
  pick(within(dialog).getByLabelText("Manager"), "Peter Otieno");
  fireEvent.change(within(dialog).getByLabelText("Paid to"), {
    target: { value: "Fuel station" },
  });
  fireEvent.change(within(dialog).getByLabelText("Reason"), {
    target: { value: "Fuel" },
  });
  fireEvent.change(within(dialog).getByLabelText("Amount, KES"), {
    target: { value: "1,200.50" },
  });
  fireEvent.click(
    within(dialog).getByLabelText("The payee should pay this back"),
  );
  fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));
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
  const dialog = await openDialog("Record spending", "Record spending");
  await offered(
    within(dialog).getByLabelText("Vehicle"),
    "KDA 482M, Rongai Express",
  );
  const item = within(dialog).getByLabelText("Item");
  expect(optionsOf(item)).toEqual(["Tyres", "Brake pads", "Parking"]);
  expect(
    within(listboxOf(item)).getAllByText("Garage and repairs"),
  ).toHaveLength(2);
  expect(within(listboxOf(item)).getByText("Fees")).toBeInTheDocument();

  fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));
  expect(
    await within(dialog).findByText("Choose the vehicle."),
  ).toBeInTheDocument();
  expect(
    within(dialog).getByText("Choose what it was for."),
  ).toBeInTheDocument();
  expect(writes(fetcher)).toEqual([]);

  fireEvent.change(within(dialog).getByLabelText("Qty"), {
    target: { value: "4" },
  });
  fireEvent.change(within(dialog).getByLabelText("Unit cost, KES"), {
    target: { value: "1250" },
  });
  expect(totalOf(dialog)).toHaveTextContent(/^KES 5,000$/);
  pick(within(dialog).getByLabelText("Vehicle"), /^KDA 482M/);
  pick(within(dialog).getByLabelText("Item"), "Tyres");
  fireEvent.change(within(dialog).getByLabelText("Note"), {
    target: { value: "Front left" },
  });
  fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));

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
  await offered(
    within(dialog).getByLabelText("Vehicle"),
    "KDA 482M, Rongai Express",
  );
  fireEvent.change(within(dialog).getByLabelText("Qty"), {
    target: { value: units },
  });
  fireEvent.change(within(dialog).getByLabelText("Unit cost, KES"), {
    target: { value: amount },
  });
  pick(within(dialog).getByLabelText("Vehicle"), /^KDA 482M/);
  pick(within(dialog).getByLabelText("Item"), "Tyres");
}

it("takes part of a unit, shows the exact live total and sends the units as a number", async () => {
  const fetcher = servePettyCash();
  renderInApp(<PettyCashPage />);
  const dialog = await openDialog("Record spending", "Record spending");
  await fillExpense(dialog, "11.875", "182.40");
  expect(within(dialog).getByLabelText("Qty")).toHaveAttribute(
    "inputmode",
    "decimal",
  );
  expect(totalOf(dialog)).toHaveTextContent(/^KES 2,166$/);
  fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));
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
  const dialog = await openDialog("Record spending", "Record spending");
  await fillExpense(dialog, "4.5", "900");
  expect(totalOf(dialog)).toHaveTextContent(/^KES 4,050$/);
  fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));
  await screen.findByText(/recorded on KDA 482M/);
  expect(writes(fetcher)[0].body.units).toBe(4.5);

  fireEvent.click(
    await screen.findByRole("button", { name: "Record spending" }),
  );
  const again = await screen.findByRole("dialog", { name: "Record spending" });
  await fillExpense(again, "1001", "10");
  fireEvent.click(within(again).getByRole("button", { name: "Save" }));
  await waitFor(() => expect(writes(fetcher)).toHaveLength(2));
  expect(writes(fetcher)[1].body.units).toBe(1001);
});

it.each(["0", "1.2345", "", "-2"])(
  "refuses units of %j and sends nothing",
  async (units) => {
    const fetcher = servePettyCash();
    renderInApp(<PettyCashPage />);
    const dialog = await openDialog("Record spending", "Record spending");
    await fillExpense(dialog, units, "10");
    fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));
    expect(
      await within(dialog).findByText(PETTY_CASH_UNITS_ERROR),
    ).toBeInTheDocument();
    expect(writes(fetcher)).toEqual([]);
  },
);

it("refuses a date after the business date", async () => {
  const fetcher = servePettyCash();
  renderInApp(<PettyCashPage />);
  const dialog = await openDialog("Record spending", "Record spending");
  await fillExpense(dialog, "2", "10");
  fireEvent.change(within(dialog).getByLabelText("Date"), {
    target: { value: "2026-10-01" },
  });
  fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));
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
    const dialog = await openDialog("Record spending", "Record spending");
    await fillExpense(dialog, "1", "500");
    fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));
    await screen.findByText(
      "KES 500 recorded on KDA 482M. It waits for approval.",
    );

    await showCash();
    const note = await openDialog("Credit note", "Credit note");
    fireEvent.change(within(note).getByLabelText("Paid to"), {
      target: { value: "Mama Njeri" },
    });
    fireEvent.change(within(note).getByLabelText("Reason"), {
      target: { value: "Double charge" },
    });
    fireEvent.change(within(note).getByLabelText("Amount, KES"), {
      target: { value: "800" },
    });
    fireEvent.click(within(note).getByRole("button", { name: "Save" }));
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
  const dialog = await openDialog("Record spending", "Record spending");
  await offered(
    within(dialog).getByLabelText("Vehicle"),
    "KDA 482M, Rongai Express",
  );
  fireEvent.change(within(dialog).getByLabelText("Unit cost, KES"), {
    target: { value: "300" },
  });
  pick(within(dialog).getByLabelText("Vehicle"), /^KDA 482M/);
  pick(within(dialog).getByLabelText("Item"), "Parking");
  fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));

  const alert = await within(dialog).findByRole("alert");
  expect(alert).toHaveTextContent(
    "This takes the float below zero. Ask for cash first.",
  );
  fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));
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
  const dialog = await openDialog("Record spending", "Record spending");
  await offered(
    within(dialog).getByLabelText("Vehicle"),
    "KDA 482M, Rongai Express",
  );
  fireEvent.change(within(dialog).getByLabelText("Unit cost, KES"), {
    target: { value: "300" },
  });
  pick(within(dialog).getByLabelText("Vehicle"), /^KDA 482M/);
  pick(within(dialog).getByLabelText("Item"), "Parking");
  fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));
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
  const dialog = await screen.findByRole("dialog", { name: "Edit spending" });
  expect(within(dialog).getByLabelText("Unit cost, KES")).toHaveValue("3500");
  fireEvent.change(within(dialog).getByLabelText("Unit cost, KES"), {
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

const trigger = (name: string | RegExp) =>
  screen.findByRole("button", { name });
const openPeriod = async (name: string | RegExp = /^Period, /) =>
  fireEvent.click(await trigger(name));
const choosePreset = async (preset: string) => {
  await openPeriod();
  fireEvent.click(await screen.findByRole("menuitemradio", { name: preset }));
};

it("moves a day at a time and stops at the business date", async () => {
  const fetcher = servePettyCash();
  renderInApp(<PettyCashPage />);
  const next = await screen.findByRole("button", { name: "Next day" });
  await trigger("Period, Wed 30 Sep 2026");
  expect(next).toBeDisabled();

  fireEvent.click(screen.getByRole("button", { name: "Previous day" }));
  await trigger("Period, Tue 29 Sep 2026");
  await waitFor(() =>
    expect(
      entryReads(fetcher).some(
        (path) =>
          path.includes("from=2026-09-29") && path.includes("to=2026-09-29"),
      ),
    ).toBe(true),
  );
  expect(paths(fetcher)).toContain(
    "/api/setup/pettycash/overview?from=2026-09-29&to=2026-09-29",
  );
  expect(screen.getByRole("button", { name: "Next day" })).toBeEnabled();
});

it("opens on the business date, with the same period picker as Central expenses ahead of the other filters", async () => {
  const fetcher = servePettyCash({
    permissions: permissionsOf({ canViewAll: true }),
  });
  renderInApp(<PettyCashPage />);
  const period = await trigger("Period, Wed 30 Sep 2026");
  expect(paths(fetcher)[0]).toBe("/api/setup/pettycash/overview");
  const manager = await screen.findByRole("combobox", { name: "Manager" });
  const status = screen.getByRole("combobox", { name: "Show" });
  const search = screen.getByRole("searchbox", { name: "Search" });
  const approve = await screen.findByRole("button", {
    name: "Record spending",
  });
  const follows = (first: HTMLElement, second: HTMLElement) =>
    Boolean(
      first.compareDocumentPosition(second) & Node.DOCUMENT_POSITION_FOLLOWING,
    );
  // The period and the actions sit on the headline card, ahead of the filters.
  expect(follows(period, approve)).toBe(true);
  expect(follows(approve, manager)).toBe(true);
  expect(follows(manager, status)).toBe(true);
  expect(follows(status, search)).toBe(true);
  expect(
    screen.queryByRole("group", { name: "Period" }),
  ).not.toBeInTheDocument();
});

it("shows several days: asks for the figures and entries of the span, labels them and drops Approve day", async () => {
  const fetcher = servePettyCash({
    permissions: permissionsOf({ canApproveDay: true, canApproveItem: true }),
    entries: [
      expense({ id: "e1", date: "2026-09-28" }),
      expense({ id: "e2", date: "2026-09-30", registration: "KDB 100X" }),
      expense({ id: "e3", date: "2026-09-27", registration: "KDC 200Y" }),
    ],
  });
  renderInApp(<PettyCashPage />);
  await screen.findByRole("row", { name: /KDB 100X/ });
  expect(
    screen.getByRole("button", { name: "Approve day" }),
  ).toBeInTheDocument();
  expect(screen.queryByText("Wed 30 Sep 2026", { selector: "td" })).toBeNull();

  await choosePreset("This week");
  const figures = await screen.findByRole("group", {
    name: "Period figures",
  });
  expect(await trigger("Period, 28 Sep to 4 Oct 2026")).toBeInTheDocument();
  const figure = (label: string) =>
    within(figures).getByText(label).nextSibling;
  expect(figure("Expenses")).toHaveTextContent(/^14,000$/);
  expect(figure("Credit notes")).toHaveTextContent(/^2,000$/);
  expect(figure("Cash issued")).toHaveTextContent(/^21,000$/);
  expect(figure("Opening balance")).toHaveTextContent(/^9,000$/);
  expect(paths(fetcher)).toContain(
    "/api/setup/pettycash/overview?from=2026-09-28&to=2026-10-04",
  );
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
  expect(
    await screen.findByRole("button", { name: "Period, 28 Sep to 4 Oct 2026" }),
  ).toBeInTheDocument();
  await screen.findByRole("row", { name: /KDA 482M/ });
  expect(
    screen.queryByRole("row", { name: /KDC 200Y/ }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "Approve day" }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole("columnheader", { name: "Date" }),
  ).not.toBeInTheDocument();
});

it("groups the entries of several days under a row for each day with that day's total", async () => {
  servePettyCash({
    entries: [
      expense({ id: "e1", date: "2026-09-28", total: 3500 }),
      expense({
        id: "e4",
        date: "2026-09-28",
        registration: "KDD 300Z",
        total: 1000,
        unitAmount: 1000,
      }),
      expense({
        id: "e2",
        date: "2026-09-30",
        registration: "KDB 100X",
        total: 2000,
        unitAmount: 2000,
      }),
    ],
  });
  renderInApp(<PettyCashPage />);
  await screen.findByRole("row", { name: /KDB 100X/ });
  expect(document.querySelector("[data-day]")).toBeNull();

  await choosePreset("This week");
  await screen.findByRole("row", { name: /KDD 300Z/ });
  const days = [...document.querySelectorAll<HTMLElement>("[data-day]")];
  expect(days.map((day) => day.dataset.day)).toEqual([
    "2026-09-28",
    "2026-09-30",
  ]);
  expect(days[0]).toHaveTextContent("Mon 28 Sep 2026");
  expect(days[0]).toHaveTextContent("4,500");
  expect(days[1]).toHaveTextContent("Wed 30 Sep 2026");
  expect(days[1]).toHaveTextContent("2,000");
  const rows = [...document.querySelectorAll("tbody tr")].map((row) =>
    row.getAttribute("data-day") ? "day" : "entry",
  );
  expect(rows).toEqual(["day", "entry", "entry", "day", "entry"]);
  expect(
    screen.getByRole("columnheader", { name: "Total amount" }),
  ).toBeInTheDocument();
});

it("groups cash received by day too, and lists floats as numbers", async () => {
  servePettyCash({
    entries: [
      cash({ id: "k1", date: "2026-09-29", total: 5000 }),
      cash({
        id: "k2",
        date: "2026-09-29",
        total: -300,
        note: "Cash returned",
      }),
    ],
  });
  renderInApp(<PettyCashPage />);
  await choosePreset("This week");
  fireEvent.click(await screen.findByRole("tab", { name: "Cash received" }));
  const day = await waitFor(() => {
    const found = document.querySelector<HTMLElement>("[data-day]");
    if (!found) throw new Error("no day row yet");
    return found;
  });
  expect(day).toHaveTextContent("Tue 29 Sep 2026");
  expect(day).toHaveTextContent("4,700");
});

it("takes any span of days, from the custom dates", async () => {
  const fetcher = servePettyCash();
  renderInApp(<PettyCashPage />);
  await openPeriod("Period, Wed 30 Sep 2026");
  const panel = await screen.findByRole("dialog", { name: "Choose a period" });
  fireEvent.change(within(panel).getByLabelText("From"), {
    target: { value: "2026-09-01" },
  });
  fireEvent.change(within(panel).getByLabelText("To"), {
    target: { value: "2026-09-20" },
  });
  fireEvent.click(
    within(panel).getByRole("button", { name: "Show these dates" }),
  );
  expect(
    await screen.findByRole("group", { name: "Period figures" }),
  ).toBeInTheDocument();
  expect(paths(fetcher)).toContain(
    "/api/setup/pettycash/overview?from=2026-09-01&to=2026-09-20",
  );
  expect(await trigger("Period, 1 to 20 Sep 2026")).toBeInTheDocument();
});

it("labels the figures of a single past day by its date", async () => {
  servePettyCash();
  renderInApp(<PettyCashPage />);
  fireEvent.click(await screen.findByRole("button", { name: "Previous day" }));
  const figures = await screen.findByRole("group", { name: "Day figures" });
  expect(await trigger("Period, Tue 29 Sep 2026")).toBeInTheDocument();
  expect(within(figures).queryByText(/Today/)).not.toBeInTheDocument();
});

it("opens a new entry on the last day of a past period, and on today when the period holds it", async () => {
  servePettyCash();
  renderInApp(<PettyCashPage />);
  await choosePreset("Last week");
  fireEvent.click(
    await screen.findByRole("button", { name: "Record spending" }),
  );
  expect(await screen.findByLabelText("Date")).toHaveValue("2026-09-27");
  fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

  await choosePreset("This week");
  fireEvent.click(
    await screen.findByRole("button", { name: "Record spending" }),
  );
  expect(await screen.findByLabelText("Date")).toHaveValue("2026-09-30");
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
  choose(manager, "Peter Otieno");
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
  await screen.findByRole("button", { name: "Record spending" });
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
  choose(screen.getByRole("combobox", { name: "Show" }), "Waiting");
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
  expect(
    await screen.findByRole("combobox", { name: "Show" }),
  ).toHaveDisplayValue("Waiting");
  await waitFor(() =>
    expect(entryReads(fetcher)[0]).toContain("status=waiting"),
  );
});

it("keeps Record spending, Credit note, Issue cash and Approve day to the permissions the server reports", async () => {
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
    screen.queryByRole("button", { name: "Record spending" }),
  ).not.toBeInTheDocument();
  await showCash();
  expect(
    screen.queryByRole("button", { name: "Credit note" }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "Issue cash" }),
  ).not.toBeInTheDocument();
  first.unmount();
  clearDataCache();

  servePettyCash({
    permissions: permissionsOf({ canSpend: true, canIssue: true }),
  });
  renderInApp(<PettyCashPage />);
  expect(
    await screen.findByRole("button", { name: "Record spending" }),
  ).toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "Approve day" }),
  ).not.toBeInTheDocument();
  await showCash();
  expect(
    await screen.findByRole("button", { name: "Credit note" }),
  ).toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: "Issue cash" }),
  ).toBeInTheDocument();
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
  choose(
    await screen.findByRole("combobox", { name: "Manager" }),
    "Peter Otieno",
  );
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
  expect(screen.getByText("Less 300")).toBeInTheDocument();
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
  expect(within(floats).getByText("12,500")).toBeInTheDocument();
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

it("puts the figure cards above the tabs, as Central expenses does, and moves between the tabs with the left and right arrows", async () => {
  servePettyCash();
  renderInApp(<PettyCashPage />);
  const figures = await screen.findByRole("group", { name: "Day figures" });
  const tabs = screen.getByRole("tablist", { name: "Petty cash" });
  expect(tabs).not.toHaveAttribute("aria-orientation");
  expect(
    figures.compareDocumentPosition(tabs) & Node.DOCUMENT_POSITION_FOLLOWING,
  ).toBeTruthy();
  expect(
    within(screen.getByRole("tabpanel")).queryByRole("group", {
      name: "Day figures",
    }),
  ).not.toBeInTheDocument();
  for (const label of [
    "Cash balance",
    "Opening balance",
    "Cash issued",
    "Expenses",
    "Credit notes",
  ])
    expect(within(figures).getByText(label)).toBeInTheDocument();

  fireEvent.keyDown(screen.getByRole("tab", { name: "Expenses" }), {
    key: "ArrowRight",
  });
  expect(
    await screen.findByRole("tab", { name: "Cash received" }),
  ).toHaveAttribute("aria-selected", "true");
  fireEvent.keyDown(screen.getByRole("tab", { name: "Cash received" }), {
    key: "ArrowLeft",
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
  const names = () =>
    screen
      .getAllByRole("button")
      .map((button) => button.textContent)
      .filter((name) =>
        [
          "Record spending",
          "Issue cash",
          "Credit note",
          "Approve day",
        ].includes(name ?? ""),
      );
  // The actions on the headline card follow the view and end with the main one, then Approve day on the bar.
  expect(names()).toEqual(["Record spending", "Approve day"]);
  await showCash();
  expect(names()).toEqual(["Credit note", "Issue cash", "Approve day"]);
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
  await showCash();
  const dialog = await openDialog("Issue cash", "Issue cash");
  await offered(within(dialog).getByLabelText("Manager"), "Peter Otieno");
  fireEvent.click(within(dialog).getByRole("button", { name: "Issue cash" }));
  expect(
    await within(dialog).findByText("Choose the manager."),
  ).toBeInTheDocument();
  expect(writes(fetcher)).toEqual([]);

  pick(within(dialog).getByLabelText("Manager"), "Peter Otieno");
  fireEvent.change(within(dialog).getByLabelText("Amount, KES"), {
    target: { value: "-300" },
  });
  fireEvent.click(within(dialog).getByRole("button", { name: "Issue cash" }));
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

const manyExpenses = (count: number) =>
  Array.from({ length: count }, (_, index) =>
    expense({
      id: `e${index + 1}`,
      registration: `KDA ${String(index + 1).padStart(3, "0")}M`,
    }),
  );

it("pages the entries on the server, 25 to a page, and goes back to page 1 when the filter changes", async () => {
  const fetcher = servePettyCash({ entries: manyExpenses(230) });
  renderInApp(<PettyCashPage />);
  await screen.findByText("KDA 001M");
  expect(entryReads(fetcher)[0]).toContain("page=1&pageSize=25");
  expect(screen.getByText("Showing 1–25 of 230")).toBeInTheDocument();
  expect(screen.queryByText(/Showing the first/)).not.toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Next page" }));
  expect(await screen.findByText("Showing 26–50 of 230")).toBeInTheDocument();
  expect(entryReads(fetcher).at(-1)).toContain("page=2&pageSize=25");
  expect(screen.getByText("KDA 026M")).toBeInTheDocument();
  expect(screen.queryByText("KDA 001M")).not.toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Page 3" }));
  expect(await screen.findByText("Showing 51–75 of 230")).toBeInTheDocument();

  pick(screen.getByLabelText("Rows per page"), "100");
  expect(await screen.findByText("Showing 1–100 of 230")).toBeInTheDocument();
  expect(entryReads(fetcher).at(-1)).toContain("page=1&pageSize=100");

  fireEvent.click(screen.getByRole("button", { name: "Page 2" }));
  await screen.findByText("Showing 101–200 of 230");
  choose(screen.getByLabelText("Show"), "Waiting");
  await waitFor(() =>
    expect(entryReads(fetcher).at(-1)).toContain("page=1&pageSize=100"),
  );
  expect(entryReads(fetcher).at(-1)).toContain("status=waiting");
});
