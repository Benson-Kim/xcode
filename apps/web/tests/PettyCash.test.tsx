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
  DAY_FIGURES,
  expense,
  json,
  overviewOf,
  paths,
  permissionsOf,
  REJECTED,
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

// Takes a manager in the dialog's select once the choices have loaded.
async function chooseManager(dialog: HTMLElement, name: string) {
  const select = within(dialog).getByLabelText("Manager");
  await within(select).findByRole("option", { name });
  choose(select, name);
}

// The live total of an expense, under its amounts.
const totalOf = (dialog: HTMLElement) =>
  within(dialog).getByText("Total amount").nextSibling;

it("shows the four day figures from the overview and the day's expenses, with no credit note or cash rows", async () => {
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
  expect(
    screen.queryByRole("row", { name: /Refund for a double charge/ }),
  ).not.toBeInTheDocument();
  expect(
    within(screen.getByRole("tabpanel")).queryByText("Cash issued"),
  ).not.toBeInTheDocument();

  expect(paths(fetcher)[0]).toBe("/api/setup/pettycash/overview");
  const read = entryReads(fetcher)[0];
  expect(read).toContain(`from=${BUSINESS_DATE}`);
  expect(read).toContain(`to=${BUSINESS_DATE}`);
  expect(read).toContain("kind=expense");
  expect(read).not.toContain("credit");
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
      expense({ id: "e1", canReview: true, canSendBack: true }),
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
  expect(within(row).getByText("Sent back")).toHaveClass("chip", "back");
  expect(
    within(row).getByText("Sent back, Attach the receipt"),
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

const REVIEWS = permissionsOf({
  canSpend: false,
  canApproveItem: true,
  canViewAll: true,
  canSendBack: true,
  canReject: true,
  canReopen: true,
  canDelete: true,
  canDeleteApproved: true,
});

const rowOf = (pattern: RegExp) => screen.findByRole("row", { name: pattern });

it("will not send an entry back without a reason, then marks the row Sent back and leaves it out of the ticks", async () => {
  const fetcher = servePettyCash({
    permissions: REVIEWS,
    entries: [expense({ canReview: true, canSendBack: true })],
  });
  renderInApp(<PettyCashPage />);
  expect(
    within(await rowOf(/KDA 482M/)).getByRole("checkbox"),
  ).toBeInTheDocument();
  fireEvent.click(
    await screen.findByRole("button", {
      name: "Send back KDA 482M, KES 3,500",
    }),
  );
  const dialog = await screen.findByRole("dialog", {
    name: "Send back expense",
  });
  expect(
    within(dialog).getByText("Grace Wanjiru · Wednesday 30 Sep 2026"),
  ).toBeInTheDocument();
  expect(within(dialog).getByText("Tyres")).toBeInTheDocument();
  expect(within(dialog).getByText("KES 3,500")).toBeInTheDocument();
  expect(
    within(dialog)
      .getAllByRole("button")
      .map((button) => button.textContent)
      .filter((name) =>
        ["No receipt", "Wrong amount", "Wrong vehicle", "Wrong item"].includes(
          name ?? "",
        ),
      ),
  ).toEqual(["No receipt", "Wrong amount", "Wrong vehicle", "Wrong item"]);

  const send = within(dialog).getByRole("button", { name: "Send back" });
  expect(send).toHaveClass("btn", "warn");
  fireEvent.click(send);
  expect(
    await within(dialog).findByText("Enter the reason."),
  ).toBeInTheDocument();
  expect(writes(fetcher)).toEqual([]);

  fireEvent.click(within(dialog).getByRole("button", { name: "No receipt" }));
  expect(within(dialog).getByLabelText("Reason")).toHaveValue("No receipt");
  fireEvent.change(within(dialog).getByLabelText("Reason"), {
    target: { value: "Attach the receipt" },
  });
  fireEvent.click(within(dialog).getByRole("button", { name: "Send back" }));
  expect(
    await screen.findByText("Sent back to Grace Wanjiru"),
  ).toBeInTheDocument();
  expect(writes(fetcher)).toEqual([
    {
      path: "/api/setup/pettycash/entries/e1/send-back",
      method: "POST",
      body: { version: 3, comment: "Attach the receipt" },
    },
  ]);

  const row = await rowOf(/KDA 482M/);
  await waitFor(() =>
    expect(within(row).getByText("Sent back")).toHaveClass("chip", "back"),
  );
  expect(
    within(row).getByText("Sent back, Attach the receipt"),
  ).toBeInTheDocument();
  expect(within(row).queryByRole("checkbox")).not.toBeInTheDocument();
  expect(
    within(row).queryByRole("button", { name: /^Approve / }),
  ).not.toBeInTheDocument();
  expect(
    within(row).queryByRole("button", { name: /^Send back / }),
  ).not.toBeInTheDocument();
});

it("keeps a sent-back expense out of the ticks and off the Approve button, though the server flags it", async () => {
  const fetcher = servePettyCash({
    permissions: REVIEWS,
    entries: [
      expense({ id: "e1", canReview: true }),
      expense({
        id: "e2",
        registration: "KDB 100X",
        status: "sentBack",
        sentBackNote: "No receipt",
        canReview: true,
        canReject: true,
      }),
    ],
  });
  renderInApp(<PettyCashPage />);
  const waiting = await rowOf(/KDA 482M/);
  const back = screen.getByRole("row", { name: /KDB 100X/ });
  expect(within(waiting).getByRole("checkbox")).toBeInTheDocument();
  expect(within(back).queryByRole("checkbox")).not.toBeInTheDocument();
  expect(
    within(back).queryByRole("button", { name: /^Approve / }),
  ).not.toBeInTheDocument();
  expect(
    within(back).getByRole("button", { name: "Reject KDB 100X, KES 3,500" }),
  ).toBeInTheDocument();
  fireEvent.click(within(waiting).getByRole("checkbox"));
  expect(
    screen.getByRole("button", { name: "Approve 1, KES 3,500" }),
  ).toBeInTheDocument();
  expect(writes(fetcher)).toEqual([]);
});

it("deletes a waiting expense without a reason, after confirming", async () => {
  const fetcher = servePettyCash({
    permissions: REVIEWS,
    entries: [expense({ canRemove: true })],
  });
  renderInApp(<PettyCashPage />);
  fireEvent.click(
    await screen.findByRole("button", { name: "Delete KDA 482M, KES 3,500" }),
  );
  const dialog = await screen.findByRole("dialog", { name: "Delete expense" });
  expect(within(dialog).queryByLabelText("Reason")).not.toBeInTheDocument();
  expect(within(dialog).getByText("KES 3,500")).toBeInTheDocument();
  const remove = within(dialog).getByRole("button", { name: "Delete" });
  expect(remove).toHaveClass("btn", "bad");
  fireEvent.click(remove);
  expect(await screen.findByText("Deleted")).toBeInTheDocument();
  expect(writes(fetcher)).toEqual([
    {
      path: "/api/setup/pettycash/entries/e1/remove",
      method: "POST",
      body: { version: 3 },
    },
  ]);
  await waitFor(() =>
    expect(
      screen.queryByRole("row", { name: /KDA 482M/ }),
    ).not.toBeInTheDocument(),
  );
});

it("will not delete an approved expense without a reason", async () => {
  const fetcher = servePettyCash({
    permissions: REVIEWS,
    entries: [expense({ status: "approved", canRemove: true })],
  });
  renderInApp(<PettyCashPage />);
  fireEvent.click(
    await screen.findByRole("button", { name: "Delete KDA 482M, KES 3,500" }),
  );
  const dialog = await screen.findByRole("dialog", {
    name: "Delete approved expense",
  });

  fireEvent.click(within(dialog).getByRole("button", { name: "Delete" }));
  expect(
    await within(dialog).findByText("Enter the reason."),
  ).toBeInTheDocument();
  expect(writes(fetcher)).toEqual([]);

  fireEvent.click(
    within(dialog).getByRole("button", { name: "Entered twice" }),
  );
  fireEvent.click(within(dialog).getByRole("button", { name: "Delete" }));
  expect(await screen.findByText("Deleted")).toBeInTheDocument();
  expect(writes(fetcher)).toEqual([
    {
      path: "/api/setup/pettycash/entries/e1/remove",
      method: "POST",
      body: { version: 3, reason: "Entered twice" },
    },
  ]);
});

it("rejects a waiting expense with a reason, and the row shows Rejected with it, out of the total", async () => {
  const fetcher = servePettyCash({
    permissions: REVIEWS,
    entries: [
      expense({ id: "e1", canReject: true }),
      expense({
        id: "e2",
        registration: "KDB 100X",
        total: 1000,
        unitAmount: 1000,
      }),
    ],
  });
  renderInApp(<PettyCashPage />);
  fireEvent.click(
    await screen.findByRole("button", { name: "Reject KDA 482M, KES 3,500" }),
  );
  const dialog = await screen.findByRole("dialog", { name: "Reject expense" });
  const reject = within(dialog).getByRole("button", { name: "Reject" });
  expect(reject).toHaveClass("btn", "bad");
  fireEvent.click(reject);
  expect(
    await within(dialog).findByText("Enter the reason."),
  ).toBeInTheDocument();
  expect(writes(fetcher)).toEqual([]);
  fireEvent.click(within(dialog).getByRole("button", { name: "Not agreed" }));
  fireEvent.click(reject);
  expect(await screen.findByText("Rejected")).toBeInTheDocument();
  expect(writes(fetcher)).toEqual([
    {
      path: "/api/setup/pettycash/entries/e1/reject",
      method: "POST",
      body: { version: 3, reason: "Not agreed" },
    },
  ]);
  const row = await rowOf(/KDA 482M/);
  await waitFor(() =>
    expect(within(row).getByText("Rejected")).toHaveClass("chip", "bad"),
  );
  expect(within(row).getByText("Not agreed")).toBeInTheDocument();
  expect(within(row).queryByRole("checkbox")).not.toBeInTheDocument();
  expect(
    screen.getByText("Expenses, 2 entries").closest("tr"),
  ).toHaveTextContent("1,000");
});

it("reopens an approved or rejected expense with a reason, and it waits again with the reason under it", async () => {
  const fetcher = servePettyCash({
    permissions: REVIEWS,
    entries: [
      expense({
        id: "e1",
        status: REJECTED,
        rejectReason: "No receipt",
        canReopen: true,
      }),
      expense({
        id: "e2",
        registration: "KDB 100X",
        status: "approved",
        canReopen: true,
      }),
      expense({ id: "e3", registration: "KDC 200Y" }),
    ],
  });
  renderInApp(<PettyCashPage />);
  const rejected = await rowOf(/KDA 482M/);
  expect(within(rejected).getByText("No receipt")).toBeInTheDocument();
  expect(
    within(screen.getByRole("row", { name: /KDC 200Y/ })).queryByRole(
      "button",
      { name: /^Reopen/ },
    ),
  ).not.toBeInTheDocument();
  const reopen = within(rejected).getByRole("button", {
    name: "Reopen KDA 482M, KES 3,500",
  });
  expect(reopen).toHaveClass("act", "warn");
  fireEvent.click(reopen);
  const dialog = await screen.findByRole("dialog", { name: "Reopen expense" });
  fireEvent.click(within(dialog).getByRole("button", { name: "Reopen" }));
  expect(
    await within(dialog).findByText("Enter the reason."),
  ).toBeInTheDocument();
  expect(
    within(dialog)
      .getAllByRole("button")
      .map((button) => button.textContent)
      .filter((name) => /^(Wrong|Approved)/.test(name ?? "")),
  ).toEqual([
    "Wrong amount",
    "Wrong vehicle",
    "Wrong item",
    "Approved by mistake",
  ]);
  fireEvent.click(
    within(dialog).getByRole("button", { name: "Approved by mistake" }),
  );
  fireEvent.click(within(dialog).getByRole("button", { name: "Reopen" }));
  expect(
    await screen.findByText("Reopened. Waiting for approval."),
  ).toBeInTheDocument();
  expect(writes(fetcher)).toEqual([
    {
      path: "/api/setup/pettycash/entries/e1/reopen",
      method: "POST",
      body: { version: 3, reason: "Approved by mistake" },
    },
  ]);
  const row = await rowOf(/KDA 482M/);
  await waitFor(() =>
    expect(within(row).getByText("Waiting")).toHaveClass("chip", "wait"),
  );
  expect(
    within(row).getByText("Reopened, Approved by mistake"),
  ).toBeInTheDocument();
  expect(within(row).queryByText("No receipt")).not.toBeInTheDocument();
});

it("puts send back, reject and delete under More when two or more apply, and shows one alone as a button", async () => {
  const fetcher = servePettyCash({
    permissions: REVIEWS,
    entries: [
      expense({
        id: "e1",
        canSendBack: true,
        canReject: true,
        canRemove: true,
      }),
      expense({
        id: "e2",
        registration: "KDB 100X",
        canReject: true,
        canRemove: true,
      }),
      expense({ id: "e3", registration: "KDC 200Y", canReject: true }),
      expense({
        id: "e4",
        registration: "KDD 300Z",
        status: "sentBack",
        sentBackNote: "No receipt",
        canSendBack: true,
        canReject: true,
      }),
    ],
  });
  renderInApp(<PettyCashPage />);
  const three = await rowOf(/KDA 482M/);
  expect(
    within(three).queryByRole("button", {
      name: /^(Send back|Reject|Delete) /,
    }),
  ).not.toBeInTheDocument();
  const more = within(three).getByRole("button", { name: /^More / });
  expect(more).toHaveClass("act", "plain", "more");
  expect(more).toHaveAttribute("aria-haspopup", "menu");
  expect(more.querySelector("svg")).not.toBeNull();
  expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  fireEvent.click(more);
  const menu = await screen.findByRole("menu");
  expect(menu).toHaveClass("pop", "row");
  const items = within(menu).getAllByRole("menuitem");
  expect(items.map((item) => item.textContent)).toEqual([
    "Send back",
    "Reject",
    "Delete",
  ]);
  expect(items.map((item) => item.className)).toEqual(["", "bad", "bad"]);

  fireEvent.click(items[1]);
  expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  await screen.findByRole("dialog", { name: "Reject expense" });
  fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

  const two = screen.getByRole("row", { name: /KDB 100X/ });
  fireEvent.click(within(two).getByRole("button", { name: /^More / }));
  expect(
    within(await screen.findByRole("menu"))
      .getAllByRole("menuitem")
      .map((item) => item.textContent),
  ).toEqual(["Reject", "Delete"]);
  fireEvent.keyDown(document, { key: "Escape" });
  await waitFor(() => expect(screen.queryByRole("menu")).toBeNull());

  const one = screen.getByRole("row", { name: /KDC 200Y/ });
  expect(within(one).queryByRole("button", { name: /^More / })).toBeNull();
  const single = within(one).getByRole("button", {
    name: "Reject KDC 200Y, KES 3,500",
  });
  expect(single).toHaveClass("act", "bad");
  expect(single).toHaveTextContent("Reject");

  const sentBack = screen.getByRole("row", { name: /KDD 300Z/ });
  expect(within(sentBack).queryByRole("button", { name: /^More / })).toBeNull();
  expect(
    within(sentBack).queryByRole("button", { name: /^Send back / }),
  ).toBeNull();
  expect(
    within(sentBack).getByRole("button", { name: /^Reject / }),
  ).toBeInTheDocument();
  expect(writes(fetcher)).toEqual([]);
});

it("shows no Edit, Delete, Reopen or More on a row the server has closed to this person, such as one older than their limit", async () => {
  servePettyCash({
    permissions: REVIEWS,
    entries: [
      expense({
        id: "e1",
        date: "2026-09-30",
        canEdit: true,
        canRemove: true,
        canSendBack: true,
        canReject: true,
      }),
      expense({
        id: "e2",
        date: "2026-09-28",
        registration: "KDB 100X",
        canReview: true,
      }),
      expense({
        id: "e3",
        date: "2026-09-28",
        registration: "KDC 200Y",
        status: "approved",
      }),
    ],
  });
  renderInApp(<PettyCashPage />);
  await choosePreset("This week");
  const open = await rowOf(/KDA 482M/);
  expect(
    within(open).getByRole("button", { name: /^Edit / }),
  ).toBeInTheDocument();
  expect(
    within(open).getByRole("button", { name: /^More / }),
  ).toBeInTheDocument();
  for (const pattern of [/KDB 100X/, /KDC 200Y/]) {
    const old = screen.getByRole("row", { name: pattern });
    for (const name of [/^Edit /, /^Delete /, /^Reopen /, /^More /, /^Reject /])
      expect(within(old).queryByRole("button", { name })).toBeNull();
  }
});

const CREDITOR = permissionsOf({ canCredit: true });

it("opens the credit note on the day shown, with the date control, a manager, an amount and a reason only", async () => {
  servePettyCash({ permissions: CREDITOR });
  renderInApp(<PettyCashPage />);
  await showCash();
  const dialog = await openDialog("Credit note", "Credit note");
  expect(within(dialog).getByText("Wed 30 Sep 2026")).toBeInTheDocument();
  expect(
    within(dialog).getByRole("button", { name: "Previous day" }),
  ).toBeEnabled();
  expect(
    within(dialog).getByRole("button", { name: "Next day" }),
  ).toBeDisabled();
  expect(within(dialog).getByLabelText("Manager")).toBeInTheDocument();
  expect(within(dialog).getByLabelText("Amount, KES")).toBeInTheDocument();
  expect(within(dialog).getByLabelText("Reason")).toBeInTheDocument();
  expect(within(dialog).queryByLabelText("Paid to")).not.toBeInTheDocument();
  expect(within(dialog).queryByLabelText("Date")).not.toBeInTheDocument();
  expect(within(dialog).queryByLabelText("Note")).not.toBeInTheDocument();
  expect(
    within(dialog).queryByLabelText("The payee should pay this back"),
  ).not.toBeInTheDocument();
  expect(within(dialog).queryByRole("checkbox")).not.toBeInTheDocument();
  expect(
    within(dialog).queryByText(/Use a minus sign/),
  ).not.toBeInTheDocument();
});

it("takes a credit note without a reason, a negative amount, refuses zero and sends no payee", async () => {
  const fetcher = servePettyCash({ permissions: CREDITOR });
  renderInApp(<PettyCashPage />);
  await showCash();
  const dialog = await openDialog("Credit note", "Credit note");
  const add = () =>
    fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));

  add();
  expect(
    await within(dialog).findAllByText(PETTY_CASH_AMOUNT_ERROR),
  ).not.toHaveLength(0);
  expect(
    within(dialog).queryByText("Say why the money was paid out."),
  ).not.toBeInTheDocument();
  expect(writes(fetcher)).toEqual([]);

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
    await screen.findByText("Credit note of KES -500 recorded."),
  ).toBeInTheDocument();
  const [save] = writes(fetcher);
  expect(save.path).toBe("/api/setup/pettycash/entries");
  expect(save.method).toBe("POST");
  expect(save.body).toEqual({
    id: expect.stringMatching(UUID),
    kind: "credit",
    holderId: "h1",
    date: BUSINESS_DATE,
    unitAmount: -500,
    note: null,
  });
  expect(save.body).not.toHaveProperty("payee");
  expect(save.body).not.toHaveProperty("reimbursable");
});

it("lets an issuer pick the float for a credit note, shows the cash it holds and sends it with the reason", async () => {
  const [grace] = overviewOf(permissionsOf()).floats;
  const fetcher = servePettyCash({
    permissions: permissionsOf({
      canSpend: false,
      canIssue: true,
      canCredit: true,
      holderId: null,
    }),
    answer: (path) =>
      path === "/api/setup/pettycash/overview?holderId=h2"
        ? json(
            overviewOf(permissionsOf({ canIssue: true }), BUSINESS_DATE, {
              floats: [
                {
                  ...grace,
                  holderId: "h2",
                  name: "Peter Otieno",
                  balance: 3800,
                },
              ],
            }),
          )
        : undefined,
  });
  renderInApp(<PettyCashPage />);
  await showCash();
  const dialog = await openDialog("Credit note", "Credit note");
  await chooseManager(dialog, "Grace Wanjiru");
  expect(
    await within(dialog).findByText("Cash on hand 12,500"),
  ).toBeInTheDocument();

  await chooseManager(dialog, "Peter Otieno");
  expect(
    await within(dialog).findByText("Cash on hand 3,800"),
  ).toBeInTheDocument();
  expect(paths(fetcher)).toContain("/api/setup/pettycash/overview?holderId=h2");
  fireEvent.change(within(dialog).getByLabelText("Reason"), {
    target: { value: "Fuel" },
  });
  fireEvent.change(within(dialog).getByLabelText("Amount, KES"), {
    target: { value: "1,200.50" },
  });
  fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));
  await screen.findByText("Credit note of KES 1,200.50 recorded.");
  expect(writes(fetcher)[0].body).toEqual({
    id: expect.stringMatching(UUID),
    kind: "credit",
    holderId: "h2",
    date: BUSINESS_DATE,
    unitAmount: 1200.5,
    note: "Fuel",
  });
});

it("offers no Edit on cash given or a credit note, even when the row says it can be edited", async () => {
  servePettyCash({
    entries: [
      credit({ canEdit: true, canRemove: true }),
      cash({ canEdit: true, canRemove: true }),
    ],
    permissions: permissionsOf({ canDeleteCash: true }),
  });
  renderInApp(<PettyCashPage />);
  await showCash();
  await screen.findByRole("button", {
    name: "Delete credit note to Mama Njeri, KES 800",
  });
  expect(screen.queryByRole("button", { name: /^Edit / })).toBeNull();
});

it("deletes cash given or a credit note with a reason, from the Actions column of someone who may delete cash entries", async () => {
  const fetcher = servePettyCash({
    permissions: permissionsOf({ canDeleteCash: true }),
    entries: [
      credit({ id: "c1", canRemove: true, version: 6 }),
      cash({ id: "k1", canRemove: true, version: 2 }),
      cash({
        id: "k2",
        date: "2026-09-30",
        note: "Old",
        total: 100,
        unitAmount: 100,
      }),
    ],
  });
  renderInApp(<PettyCashPage />);
  await showCash();
  expect(
    (await screen.findAllByRole("columnheader")).map(
      (header) => header.textContent,
    ),
  ).toEqual(["Type", "Manager", "Reason", "In", "Out", "Actions"]);
  const note = await screen.findByRole("row", {
    name: /Refund for a double charge/,
  });
  const remove = within(note).getByRole("button", {
    name: "Delete credit note to Mama Njeri, KES 800",
  });
  expect(remove).toHaveClass("act", "bad");
  expect(
    within(screen.getByRole("row", { name: /Old/ })).queryByRole("button"),
  ).toBeNull();

  fireEvent.click(remove);
  const dialog = await screen.findByRole("dialog", {
    name: "Delete credit note",
  });
  expect(within(dialog).getByText("KES 800")).toBeInTheDocument();
  fireEvent.click(within(dialog).getByRole("button", { name: "Delete" }));
  expect(
    await within(dialog).findByText("Enter the reason."),
  ).toBeInTheDocument();
  expect(writes(fetcher)).toEqual([]);
  expect(
    within(dialog)
      .getAllByRole("button")
      .map((button) => button.textContent)
      .filter((name) =>
        ["Entered twice", "Wrong manager", "Wrong amount"].includes(name ?? ""),
      ),
  ).toEqual(["Entered twice", "Wrong manager", "Wrong amount"]);
  fireEvent.click(
    within(dialog).getByRole("button", { name: "Wrong manager" }),
  );
  fireEvent.click(within(dialog).getByRole("button", { name: "Delete" }));
  expect(await screen.findByText("Deleted")).toBeInTheDocument();
  expect(writes(fetcher)).toEqual([
    {
      path: "/api/setup/pettycash/entries/c1/remove",
      method: "POST",
      body: { version: 6, reason: "Wrong manager" },
    },
  ]);

  fireEvent.click(
    await screen.findByRole("button", {
      name: "Delete cash for Grace Wanjiru, KES 5,000",
    }),
  );
  const cashDialog = await screen.findByRole("dialog", {
    name: "Delete cash issued",
  });
  fireEvent.change(within(cashDialog).getByLabelText("Reason"), {
    target: { value: "Entered twice" },
  });
  fireEvent.click(within(cashDialog).getByRole("button", { name: "Delete" }));
  await waitFor(() => expect(writes(fetcher)).toHaveLength(2));
  expect(writes(fetcher)[1]).toEqual({
    path: "/api/setup/pettycash/entries/k1/remove",
    method: "POST",
    body: { version: 2, reason: "Entered twice" },
  });
});

it("shows the live total of an expense and sends units, amount, vehicle and item with a fresh id", async () => {
  const fetcher = servePettyCash();
  renderInApp(<PettyCashPage />);
  const dialog = await openDialog("Record spending", "Record spending");
  await offered(within(dialog).getByLabelText("Vehicle"), "KDA 482M");
  expect(optionsOf(within(dialog).getByLabelText("Vehicle"))).toEqual([
    "KDA 482M",
    "KDB 100X · 7",
  ]);
  expect(within(dialog).queryByLabelText("Note")).not.toBeInTheDocument();
  expect(
    within(dialog).queryByText(/Use a minus sign/),
  ).not.toBeInTheDocument();
  expect(within(dialog).getByText("Wed 30 Sep 2026")).toBeInTheDocument();
  expect(within(dialog).queryByLabelText("Manager")).not.toBeInTheDocument();
  expect(within(dialog).getByText("Grace Wanjiru")).toHaveClass("msub");
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
    note: null,
  });
});

async function fillExpense(dialog: HTMLElement, units: string, amount: string) {
  await offered(within(dialog).getByLabelText("Vehicle"), "KDA 482M");
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

it("steps the date of a pop up a day at a time, stops at the business date, and records on the day chosen", async () => {
  const fetcher = servePettyCash();
  renderInApp(<PettyCashPage />);
  const dialog = await openDialog("Record spending", "Record spending");
  expect(within(dialog).queryByLabelText("Date")).not.toBeInTheDocument();
  const next = within(dialog).getByRole("button", { name: "Next day" });
  expect(next).toBeDisabled();
  await fillExpense(dialog, "2", "10");

  fireEvent.click(within(dialog).getByRole("button", { name: "Previous day" }));
  expect(within(dialog).getByText("Tue 29 Sep 2026")).toBeInTheDocument();
  expect(next).toBeEnabled();
  await waitFor(() =>
    expect(paths(fetcher)).toContain(
      "/api/setup/pettycash/options?date=2026-09-29",
    ),
  );
  fireEvent.click(within(dialog).getByRole("button", { name: "Next day" }));
  expect(within(dialog).getByText("Wed 30 Sep 2026")).toBeInTheDocument();
  expect(next).toBeDisabled();

  fireEvent.click(within(dialog).getByRole("button", { name: "Previous day" }));
  fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));
  await screen.findByText(/recorded on KDA 482M/);
  expect(writes(fetcher)[0].body.date).toBe("2026-09-29");
});

it("stops the date control at the earliest day the person may change", async () => {
  servePettyCash({
    permissions: permissionsOf({ earliestDate: "2026-09-28" }),
  });
  renderInApp(<PettyCashPage />);
  const dialog = await openDialog("Record spending", "Record spending");
  const previous = within(dialog).getByRole("button", { name: "Previous day" });
  fireEvent.click(previous);
  expect(within(dialog).getByText("Tue 29 Sep 2026")).toBeInTheDocument();
  expect(previous).toBeEnabled();
  fireEvent.click(previous);
  expect(within(dialog).getByText("Mon 28 Sep 2026")).toBeInTheDocument();
  expect(previous).toBeDisabled();
  expect(
    within(dialog).getByRole("button", { name: "Next day" }),
  ).toHaveFocus();
});

it("opens a new entry on the earliest day allowed when the days shown are older than the limit", async () => {
  servePettyCash({
    permissions: permissionsOf({ earliestDate: "2026-09-28", canCredit: true }),
  });
  renderInApp(<PettyCashPage />);
  await choosePreset("Last week");
  fireEvent.click(
    await screen.findByRole("button", { name: "Record spending" }),
  );
  const dialog = await screen.findByRole("dialog", { name: "Record spending" });
  expect(within(dialog).getByText("Mon 28 Sep 2026")).toBeInTheDocument();
  expect(
    within(dialog).getByRole("button", { name: "Previous day" }),
  ).toBeDisabled();
});

it("offers Record spending only to someone with a float of their own or the right to add for another manager", async () => {
  const cases: [Partial<ReturnType<typeof permissionsOf>>, boolean][] = [
    [{ canSpend: true, holderId: "h1" }, true],
    [{ canSpend: true, holderId: null }, false],
    [{ canSpend: true, holderId: null, canSpendOther: true }, true],
    [{ canSpend: false, holderId: "h1", canSpendOther: true }, false],
  ];
  for (const [over, shown] of cases) {
    servePettyCash({ permissions: permissionsOf(over) });
    const view = renderInApp(<PettyCashPage />);
    await screen.findByText("Nothing recorded on this day.");
    expect(
      screen.queryByRole("button", { name: "Record spending" }) !== null,
    ).toBe(shown);
    view.unmount();
    clearDataCache();
  }
});

it("asks which manager's float a new expense goes on when the person has none of their own, and sends it", async () => {
  const fetcher = servePettyCash({
    permissions: permissionsOf({
      holderId: null,
      canSpendOther: true,
    }),
  });
  renderInApp(<PettyCashPage />);
  const dialog = await openDialog("Record spending", "Record spending");
  const manager = within(dialog).getByLabelText("Manager");
  expect(within(dialog).queryByText(/Cash on hand/)).not.toBeInTheDocument();
  await fillExpense(dialog, "1", "500");
  fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));
  expect(
    await within(dialog).findByText("Choose the manager."),
  ).toBeInTheDocument();
  expect(writes(fetcher)).toEqual([]);

  await within(manager).findByRole("option", { name: "Peter Otieno" });
  choose(manager, "Peter Otieno");
  fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));
  await screen.findByText(/recorded on KDA 482M/);
  expect(writes(fetcher)[0].body).toEqual({
    id: expect.stringMatching(UUID),
    kind: "expense",
    holderId: "h2",
    date: BUSINESS_DATE,
    vehicleId: "v1",
    expenseItemId: "i1",
    units: 1,
    unitAmount: 500,
    note: null,
  });
});

it("records on the manager on screen for someone who may add for another manager, without asking", async () => {
  const fetcher = servePettyCash({
    permissions: permissionsOf({
      canViewAll: true,
      canSpendOther: true,
    }),
  });
  renderInApp(<PettyCashPage />);
  choose(
    await screen.findByRole("combobox", { name: "Manager" }),
    "Peter Otieno",
  );
  await waitFor(() =>
    expect(paths(fetcher)).toContain(
      "/api/setup/pettycash/overview?holderId=h2",
    ),
  );
  const dialog = await openDialog("Record spending", "Record spending");
  expect(within(dialog).queryByLabelText("Manager")).not.toBeInTheDocument();
  expect(within(dialog).getByText("Peter Otieno")).toHaveClass("msub");
  await fillExpense(dialog, "1", "500");
  fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));
  await screen.findByText(/recorded on KDA 482M/);
  expect(writes(fetcher)[0].body.holderId).toBe("h2");
});

it.each([0, -300])(
  "sends an expense and a credit note when the float holds %d, with no refusal of its own",
  async (balance) => {
    const [first] = overviewOf(permissionsOf()).floats;
    const fetcher = servePettyCash({
      permissions: CREDITOR,
      floats: [{ ...first, balance }],
    });
    renderInApp(<PettyCashPage />);
    const dialog = await openDialog("Record spending", "Record spending");
    await fillExpense(dialog, "1", "500");
    fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));
    await screen.findByText(
      "KES 500 recorded on KDA 482M. It waits for approval.",
    );

    await showCash();
    const note = await openDialog("Credit note", "Credit note");
    fireEvent.change(within(note).getByLabelText("Reason"), {
      target: { value: "Double charge" },
    });
    fireEvent.change(within(note).getByLabelText("Amount, KES"), {
      target: { value: "800" },
    });
    fireEvent.click(within(note).getByRole("button", { name: "Save" }));
    await screen.findByText(/Credit note of KES 800 recorded/);
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
  await offered(within(dialog).getByLabelText("Vehicle"), "KDA 482M");
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
  await offered(within(dialog).getByLabelText("Vehicle"), "KDA 482M");
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
  const dialog = await screen.findByRole("dialog", { name: "Delete expense" });
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

it("shows several days: asks for the figures and entries of the span, labels them and turns Approve day into Approve all", async () => {
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
    screen.getByRole("button", { name: "Approve day, KES 3,500" }),
  ).toBeInTheDocument();
  expect(
    screen.queryByText("Wednesday 30 Sep 2026", { selector: "td" }),
  ).toBeNull();

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
          path.includes("kind=expense") &&
          !path.includes("credit"),
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
    await screen.findByRole("button", { name: "Approve all, KES 9,000" }),
  ).toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: /^Approve day/ }),
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
  expect(days[0]).toHaveTextContent("Monday 28 Sep 2026");
  expect(days[0]).toHaveTextContent("4,500");
  expect(days[1]).toHaveTextContent("Wednesday 30 Sep 2026");
  expect(days[1]).toHaveTextContent("2,000");
  const rows = [...document.querySelectorAll("tbody tr")].map((row) =>
    row.getAttribute("data-day") ? "day" : "entry",
  );
  expect(rows).toEqual(["day", "entry", "entry", "day", "entry"]);
  expect(
    screen.getByRole("columnheader", { name: "Total amount" }),
  ).toBeInTheDocument();
});

it("groups cash received by day too, with what the day netted", async () => {
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
  expect(day).toHaveTextContent("Tuesday 29 Sep 2026");
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
  expect(
    within(await screen.findByRole("dialog")).getByText("Sun 27 Sep 2026"),
  ).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

  await choosePreset("This week");
  fireEvent.click(
    await screen.findByRole("button", { name: "Record spending" }),
  );
  expect(
    within(await screen.findByRole("dialog")).getByText("Wed 30 Sep 2026"),
  ).toBeInTheDocument();
});

it("draws the four statuses as the design's chips, counts a sent-back expense but not a rejected one, and filters by Rejected", async () => {
  const fetcher = servePettyCash({
    entries: [
      expense({ id: "e1", total: 1000, unitAmount: 1000 }),
      expense({
        id: "e2",
        registration: "KDB 100X",
        total: 2000,
        unitAmount: 2000,
        status: "sentBack",
        sentBackNote: "No receipt",
      }),
      expense({
        id: "e3",
        registration: "KDC 200Y",
        total: 4000,
        unitAmount: 4000,
        status: "approved",
      }),
      expense({
        id: "e4",
        registration: "KDD 300Z",
        total: 8000,
        unitAmount: 8000,
        status: REJECTED,
        rejectReason: "Not agreed",
      }),
    ],
  });
  renderInApp(<PettyCashPage />);
  const chipOf = async (pattern: RegExp, label: string) =>
    within(await rowOf(pattern)).getByText(label);
  expect(await chipOf(/KDA 482M/, "Waiting")).toHaveClass("chip", "wait");
  expect(await chipOf(/KDB 100X/, "Sent back")).toHaveClass("chip", "back");
  expect(await chipOf(/KDC 200Y/, "Approved")).toHaveClass("chip", "ok");
  expect(await chipOf(/KDD 300Z/, "Rejected")).toHaveClass("chip", "bad");
  expect(
    screen.getByText("Expenses, 4 entries").closest("tr"),
  ).toHaveTextContent("7,000");

  choose(screen.getByRole("combobox", { name: "Show" }), "Rejected");
  await waitFor(() =>
    expect(
      entryReads(fetcher).some((path) => path.includes("status=rejected")),
    ).toBe(true),
  );
});

it("leaves a rejected expense out of the total of its day", async () => {
  servePettyCash({
    entries: [
      expense({ id: "e1", date: "2026-09-28", total: 3500 }),
      expense({
        id: "e2",
        date: "2026-09-28",
        registration: "KDB 100X",
        total: 1000,
        unitAmount: 1000,
        status: REJECTED,
      }),
    ],
  });
  renderInApp(<PettyCashPage />);
  await choosePreset("This week");
  await screen.findByRole("row", { name: /KDB 100X/ });
  const day = document.querySelector<HTMLElement>("[data-day]")!;
  expect(day).toHaveTextContent("2 entries, KES 3,500");
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
    await screen.findByRole("button", { name: /^Approve day/ }),
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
    permissions: permissionsOf({
      canSpend: true,
      canIssue: true,
      canCredit: true,
    }),
  });
  renderInApp(<PettyCashPage />);
  expect(
    await screen.findByRole("button", { name: "Record spending" }),
  ).toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: /^Approve day/ }),
  ).not.toBeInTheDocument();
  await showCash();
  expect(
    await screen.findByRole("button", { name: "Credit note" }),
  ).toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: "Issue cash" }),
  ).toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: /^Approve/ }),
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
  fireEvent.click(
    await screen.findByRole("button", { name: "Approve these, KES 3,500" }),
  );
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

it("lists cash and credit notes on the Cash received tab, and moves between tabs with the arrow keys", async () => {
  const fetcher = servePettyCash({
    permissions: permissionsOf({ canIssue: true, canDeleteCash: true }),
    entries: [
      expense(),
      cash({ canRemove: true }),
      cash({ id: "k2", total: -300, unitAmount: -300, note: "Returned" }),
      credit({ status: null }),
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
  const panel = screen.getByRole("tabpanel");
  expect(await within(panel).findByText("Cash issued")).toBeInTheDocument();
  expect(screen.getByText("Cash taken back")).toBeInTheDocument();
  expect(screen.getByText("Returned")).toBeInTheDocument();
  expect(screen.queryByText("KDA 482M")).not.toBeInTheDocument();
  expect(
    screen.getByRole("button", {
      name: "Delete cash for Grace Wanjiru, KES 5,000",
    }),
  ).toBeInTheDocument();
  expect(
    screen.queryByRole("heading", { name: "Floats" }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole("columnheader", { name: "Cash in hand" }),
  ).not.toBeInTheDocument();
  expect(
    entryReads(fetcher).some(
      (path) =>
        path.includes("kind=cash%2Ccredit") && !path.includes("expense"),
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
      canCredit: true,
      canApproveDay: true,
      canApproveItem: true,
    }),
  });
  renderInApp(<PettyCashPage />);
  await screen.findByRole("button", { name: "Approve day, KES 3,500" });
  const names = () =>
    screen
      .getAllByRole("button")
      .map((button) => button.textContent)
      .filter((name) =>
        [
          "Record spending",
          "Issue cash",
          "Credit note",
          "Approve day, KES 3,500",
        ].includes(name ?? ""),
      );
  // The actions on the headline card follow the view and end with the main one, then Approve day on the bar of the Expenses view.
  expect(names()).toEqual(["Record spending", "Approve day, KES 3,500"]);
  await showCash();
  expect(names()).toEqual(["Credit note", "Issue cash"]);
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
  expect(within(dialog).getByText("Wed 30 Sep 2026")).toBeInTheDocument();
  expect(within(dialog).queryByLabelText("Date")).not.toBeInTheDocument();
  expect(within(dialog).queryByLabelText("Note")).not.toBeInTheDocument();
  await within(within(dialog).getByLabelText("Manager")).findByRole("option", {
    name: "Peter Otieno",
  });
  fireEvent.click(within(dialog).getByRole("button", { name: "Issue cash" }));
  expect(
    await within(dialog).findByText("Choose the manager."),
  ).toBeInTheDocument();
  expect(writes(fetcher)).toEqual([]);

  await chooseManager(dialog, "Peter Otieno");
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

const tickable = (
  id: string,
  registration: string,
  total: number,
  version = 3,
) =>
  expense({
    id,
    registration,
    total,
    unitAmount: total,
    version,
    canReview: true,
  });

it("ticks two waiting expenses and approves exactly those with their versions", async () => {
  const fetcher = servePettyCash({
    permissions: REVIEWER,
    entries: [
      tickable("e1", "KDA 482M", 3500, 3),
      tickable("e2", "KDB 100X", 1500, 5),
      expense({
        id: "e3",
        registration: "KDC 200Y",
        total: 9000,
        unitAmount: 9000,
        aboveLimit: true,
      }),
      expense({ id: "e4", registration: "KDD 300Z", status: "approved" }),
    ],
    answer: (path, init) =>
      init?.method === "POST" && path === "/api/setup/pettycash/approve"
        ? json({ approved: 2, total: 5000, skipped: 0 })
        : undefined,
  });
  renderInApp(<PettyCashPage />);
  await screen.findByRole("row", { name: /KDA 482M/ });
  expect(
    screen.getByRole("columnheader", { name: "Select" }),
  ).toBeInTheDocument();
  expect(screen.getAllByRole("checkbox")).toHaveLength(2);
  expect(screen.queryByRole("button", { name: /^Approve \d/ })).toBeNull();

  fireEvent.click(
    screen.getByRole("checkbox", { name: "Select KDA 482M, KES 3,500" }),
  );
  expect(
    screen.getByRole("button", { name: "Approve 1, KES 3,500" }),
  ).toBeInTheDocument();
  fireEvent.click(
    screen.getByRole("checkbox", { name: "Select KDB 100X, KES 1,500" }),
  );
  fireEvent.click(
    await screen.findByRole("button", { name: "Approve 2, KES 5,000" }),
  );

  expect(
    await screen.findByText("Approved 2 entries, KES 5,000."),
  ).toBeInTheDocument();
  expect(writes(fetcher)).toEqual([
    {
      path: "/api/setup/pettycash/approve",
      method: "POST",
      body: {
        entries: [
          { id: "e1", version: 3 },
          { id: "e2", version: 5 },
        ],
      },
    },
  ]);
  await waitFor(() =>
    expect(
      screen.queryByRole("button", { name: /^Approve \d/ }),
    ).not.toBeInTheDocument(),
  );
  for (const box of screen.getAllByRole("checkbox"))
    expect(box).not.toBeChecked();
});

it("offers no checkboxes to someone who cannot approve entries", async () => {
  servePettyCash({ entries: [expense({ canReview: false })] });
  renderInApp(<PettyCashPage />);
  await screen.findByRole("row", { name: /KDA 482M/ });
  expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
  expect(
    screen.queryByRole("columnheader", { name: "Select" }),
  ).not.toBeInTheDocument();
});

it("clears the ticks when the list changes", async () => {
  servePettyCash({
    permissions: REVIEWER,
    entries: [tickable("e1", "KDA 482M", 3500)],
  });
  renderInApp(<PettyCashPage />);
  const box = await screen.findByRole("checkbox", {
    name: "Select KDA 482M, KES 3,500",
  });
  fireEvent.click(box);
  expect(box).toBeChecked();

  choose(screen.getByRole("combobox", { name: "Show" }), "Waiting");
  await waitFor(() =>
    expect(
      screen.getByRole("checkbox", { name: "Select KDA 482M, KES 3,500" }),
    ).not.toBeChecked(),
  );
  expect(
    screen.queryByRole("button", { name: /^Approve \d/ }),
  ).not.toBeInTheDocument();
});

it("approves every day of a period at once, naming what waits", async () => {
  const fetcher = servePettyCash({
    permissions: permissionsOf({ canApproveDay: true }),
    answer: (path, init) =>
      init?.method === "POST" && path === "/api/setup/pettycash/approve-day"
        ? json({ approved: 3, total: 9000, skipped: 0 })
        : undefined,
  });
  renderInApp(<PettyCashPage />);
  await choosePreset("This week");
  fireEvent.click(
    await screen.findByRole("button", { name: "Approve all, KES 9,000" }),
  );
  expect(
    await screen.findByText("Approved 3 entries, KES 9,000."),
  ).toBeInTheDocument();
  expect(writes(fetcher)).toEqual([
    {
      path: "/api/setup/pettycash/approve-day",
      method: "POST",
      body: { date: "2026-09-28", to: "2026-10-04" },
    },
  ]);
});

it("reads the amount waiting from the figures and disables the button when nothing waits", async () => {
  const approver = permissionsOf({ canApproveDay: true });
  servePettyCash({
    permissions: approver,
    answer: (path) =>
      path === "/api/setup/pettycash/overview"
        ? json(
            overviewOf(approver, BUSINESS_DATE, {
              figures: { ...DAY_FIGURES, waiting: 0, waitingCount: 0 },
            }),
          )
        : undefined,
  });
  renderInApp(<PettyCashPage />);
  expect(
    await screen.findByRole("button", { name: "Approve day" }),
  ).toBeDisabled();
});

it("lists a credit note on Cash received with its type, who, why and money out, with no status or payee, and the net below", async () => {
  servePettyCash({
    permissions: permissionsOf({ canDeleteCash: true }),
    entries: [
      cash({ id: "k1", total: 5000, unitAmount: 5000 }),
      cash({ id: "k2", total: -300, unitAmount: -300, note: "Returned" }),
      credit({ status: null, reimbursable: true }),
      credit({
        id: "c2",
        payee: null,
        note: "Fuel",
        total: -200,
        unitAmount: -200,
        status: null,
      }),
    ],
  });
  renderInApp(<PettyCashPage />);
  await showCash();
  const note = await screen.findByRole("row", {
    name: /Refund for a double charge/,
  });
  const cells = within(note).getAllByRole("cell");
  expect(cells[0]).toHaveTextContent(/^Credit note$/);
  expect(within(cells[0]).getByText("Credit note")).toHaveClass("chip", "bad");
  expect(cells[1]).toHaveTextContent("Grace Wanjiru");
  expect(cells[2]).toHaveTextContent(/^Refund for a double charge$/);
  expect(cells[3]).toHaveTextContent(/^$/);
  expect(cells[4]).toHaveTextContent(/^800$/);
  expect(cells[4]).toHaveClass("r", "tot", "neg");
  expect(cells[5]).toHaveClass("r");

  const back = screen.getByRole("row", { name: /Returned/ });
  expect(within(back).getAllByRole("cell")[0]).toHaveTextContent(
    "Cash taken back",
  );
  expect(within(back).getAllByRole("cell")[4]).toHaveTextContent(/^300$/);

  const repaid = screen.getByRole("row", { name: /Fuel/ });
  const repaidCells = within(repaid).getAllByRole("cell");
  expect(repaidCells[3]).toHaveTextContent(/^200$/);
  expect(repaidCells[4]).toHaveTextContent(/^$/);

  expect(
    screen.getAllByRole("columnheader").map((header) => header.textContent),
  ).toEqual(["Type", "Manager", "Reason", "In", "Out", "Actions"]);
  const footer = screen.getByText("Net cash received").closest("tr")!;
  expect(footer).toHaveTextContent("Net cash received4,100");
  expect(footer.querySelectorAll("td")).toHaveLength(3);
});

it("leaves out the Actions column of Cash received for someone who may not delete cash entries, and keeps it, empty on old rows, for someone who may", async () => {
  servePettyCash({
    entries: [cash({ canRemove: true })],
  });
  const view = renderInApp(<PettyCashPage />);
  await showCash();
  await within(screen.getByRole("tabpanel")).findByText("Cash issued");
  expect(
    screen.getAllByRole("columnheader").map((header) => header.textContent),
  ).toEqual(["Type", "Manager", "Reason", "In", "Out"]);
  expect(screen.queryByRole("button", { name: /^Delete / })).toBeNull();
  view.unmount();
  clearDataCache();

  servePettyCash({
    permissions: permissionsOf({ canDeleteCash: true }),
    entries: [cash({ canRemove: false })],
  });
  renderInApp(<PettyCashPage />);
  await showCash();
  await within(screen.getByRole("tabpanel")).findByText("Cash issued");
  expect(
    screen.getAllByRole("columnheader").map((header) => header.textContent),
  ).toEqual(["Type", "Manager", "Reason", "In", "Out", "Actions"]);
  expect(screen.queryByRole("button", { name: /^Delete / })).toBeNull();
});

it("says no cash moved when there is none, and that nothing matches when searching", async () => {
  servePettyCash();
  renderInApp(<PettyCashPage />);
  await showCash();
  expect(await screen.findByText("No cash moved.")).toBeInTheDocument();
  fireEvent.change(screen.getByRole("searchbox", { name: "Search" }), {
    target: { value: "nobody" },
  });
  expect(await screen.findByText("Nothing matches.")).toBeInTheDocument();
});

it("counts both tabs, the other one from a request for a single entry with the same filters", async () => {
  const fetcher = servePettyCash({
    entries: [
      expense(),
      expense({ id: "e2", registration: "KDB 100X" }),
      cash(),
    ],
  });
  renderInApp(<PettyCashPage />);
  const expenses = await screen.findByRole("tab", { name: "Expenses" });
  const received = screen.getByRole("tab", { name: "Cash received" });
  await waitFor(() => {
    expect(expenses).toHaveTextContent("Expenses2");
    expect(received).toHaveTextContent("Cash received1");
  });
  expect(
    entryReads(fetcher).some(
      (path) =>
        path.includes("pageSize=1") && path.includes("kind=cash%2Ccredit"),
    ),
  ).toBe(true);

  await showCash();
  await waitFor(() => {
    expect(expenses).toHaveTextContent("Expenses2");
    expect(received).toHaveTextContent("Cash received1");
  });
  expect(
    entryReads(fetcher).some(
      (path) => path.includes("pageSize=1&") && path.includes("kind=expense"),
    ),
  ).toBe(true);
});

it("exports the view shown, for the period and manager, to someone with reports.export", async () => {
  URL.createObjectURL = vi.fn(() => "blob:petty");
  URL.revokeObjectURL = vi.fn();
  const saved: string[] = [];
  const click = vi
    .spyOn(HTMLAnchorElement.prototype, "click")
    .mockImplementation(function (this: HTMLAnchorElement) {
      saved.push(this.download);
    });
  const fetcher = servePettyCash({ entries: [expense(), cash()] });
  const exported: string[] = [];
  vi.stubGlobal("fetch", (input: RequestInfo, init?: RequestInit) => {
    if (String(input).includes("/export?")) {
      exported.push(String(input));
      return Promise.resolve(new Response("file", { status: 200 }));
    }
    return fetcher(input, init);
  });
  renderInApp(<PettyCashPage />, { permissions: ["reports.export"] });

  fireEvent.click(await screen.findByRole("tab", { name: "Cash received" }));
  fireEvent.click(await screen.findByRole("button", { name: "Export" }));
  fireEvent.click(screen.getByRole("menuitem", { name: "Excel" }));

  await waitFor(() => expect(saved).toHaveLength(1));
  expect(exported).toEqual([
    "/api/setup/pettycash/export?from=2026-09-30&to=2026-09-30&view=cash&format=xlsx",
  ]);
  expect(saved[0]).toBe("Petty cash, cash received 30 Sep 2026.xlsx");
  click.mockRestore();
});

it("offers no Export without reports.export", async () => {
  servePettyCash({ entries: [expense()] });
  renderInApp(<PettyCashPage />);
  await screen.findByRole("row", { name: /KDA 482M/ });
  expect(
    screen.queryByRole("button", { name: "Export" }),
  ).not.toBeInTheDocument();
});
