// Petty cash: one float per holder (usually a fleet manager). Cash given raises it; expenses (always against a
// vehicle) and credit notes (money paid out that belongs to no vehicle) lower it. Expenses and credit notes wait
// for approval; only an approved expense reaches its vehicle's costs. Every amount is signed and never zero:
// a negative expense is a refund, negative cash is cash taken back, a negative credit note is money repaid.
// A float can go below zero when its holder spends their own money before cash reaches them.

import { withQuery } from "./query";

export type PettyCashKind = "cash" | "expense" | "credit";
export type PettyCashStatus = "waiting" | "approved" | "sentBack";
export type PettyCashBucket = 1 | 2 | 3;
// "range" is any span asked for with from and to; "week" is what the phone still sends with date and period.
export type PettyCashPeriod = "day" | "week" | "range";

export const PETTY_CASH_KINDS: readonly PettyCashKind[] = [
  "expense",
  "credit",
  "cash",
];
export const PETTY_CASH_STATUSES: readonly PettyCashStatus[] = [
  "waiting",
  "approved",
  "sentBack",
];

export const PETTY_CASH_KIND_LABELS: Record<PettyCashKind, string> = {
  cash: "Cash given",
  expense: "Expense",
  credit: "Credit note",
};

export const PETTY_CASH_STATUS_LABELS: Record<PettyCashStatus, string> = {
  waiting: "Waiting",
  approved: "Approved",
  sentBack: "Sent back",
};

export const PETTY_CASH_NOTE_LIMIT = 80;
export const PETTY_CASH_PAYEE_LIMIT = 80;
export const PETTY_CASH_COMMENT_LIMIT = 200;
export const PETTY_CASH_REASON_LIMIT = 500;
export const PETTY_CASH_MAX_UNITS = 999_999_999.999;
export const PETTY_CASH_PAGE_SIZE = 100;

// Any of these opens the Petty cash menu item.
export const PETTY_CASH_PERMISSIONS = [
  "pettycash.spend",
  "pettycash.view_all",
  "pettycash.approve_item",
  "pettycash.issue",
] as const;

export function canOpenPettyCash(permissions: readonly string[]): boolean {
  return PETTY_CASH_PERMISSIONS.some((key) => permissions.includes(key));
}

// What the signed-in person may do here. holderId is their own float, null when they hold none.
// approvalLimit is set per person in People and access; null (the default) means no limit. Entries whose total
// (ignoring sign) is above it cannot be approved by them. canIssueNegative lets cash taken back leave a float below zero.
export interface PettyCashPermissions {
  holderId: string | null;
  canSpend: boolean;
  canViewAll: boolean;
  canIssue: boolean;
  canIssueNegative: boolean;
  canApproveItem: boolean;
  canApproveDay: boolean;
  approvalLimit: number | null;
}

// A person with a float: anyone who may record spending, plus anyone with entries. active is false once they lost
// the permission or left; their float still shows until it is settled.
export interface PettyCashHolder {
  id: string;
  name: string;
  active: boolean;
}

// The figures for a day or a week. moneyOut = expenses + creditNotes; closing = opening + cashReceived - moneyOut.
export interface PettyCashFigures {
  openingBalance: number;
  cashReceived: number;
  expenses: number;
  creditNotes: number;
  moneyOut: number;
  closingBalance: number;
}

// One float to date. balance = cashReceived - creditNotes - expenses, whatever their approval status.
// waiting, approved and sentBack split expenses + creditNotes by status.
export interface PettyCashFloat {
  holderId: string;
  name: string;
  active: boolean;
  cashReceived: number;
  creditNotes: number;
  expenses: number;
  waiting: number;
  waitingCount: number;
  approved: number;
  sentBack: number;
  balance: number;
  lastCashOn: string | null;
}

// A week starts on the organization's first day of the week; from and to are the days the figures cover.
export interface PettyCashOverview {
  businessDate: string;
  date: string;
  period: PettyCashPeriod;
  from: string;
  to: string;
  permissions: PettyCashPermissions;
  holders: PettyCashHolder[];
  figures: PettyCashFigures;
  floats: PettyCashFloat[];
}

// from and to go together (at most 367 days, from not after the business date). With them the server ignores date and
// period, answers period "day" when they are the same day and "range" otherwise, echoes from and to, and sets date to to.
// The figures open at the start of from and close at the end of to; floats stay to date.
export interface PettyCashOverviewQuery {
  date?: string;
  period?: PettyCashPeriod;
  from?: string;
  to?: string;
  holderId?: string;
}

export interface PettyCashEntry {
  id: string;
  kind: PettyCashKind;
  holderId: string;
  holderName: string;
  date: string;
  vehicleId: string | null;
  registration: string | null;
  expenseItemId: string | null;
  expenseItemName: string | null;
  bucket: PettyCashBucket | null;
  units: number;
  unitAmount: number;
  total: number;
  payee: string | null;
  note: string | null;
  reimbursable: boolean;
  // Null for cash given, which is never reviewed.
  status: PettyCashStatus | null;
  sentBackNote: string | null;
  reviewedByName: string | null;
  reviewedAt: string | null;
  recordedByName: string;
  recordedAt: string;
  updatedAt: string;
  version: number;
  canEdit: boolean;
  canRemove: boolean;
  // Approve and send back are open to this person for this entry.
  canReview: boolean;
  // Waiting, and above this person's approval limit.
  aboveLimit: boolean;
}

export interface PettyCashEntryPage {
  items: PettyCashEntry[];
  pageNumber: number;
  pageSize: number;
  total: number;
}

export interface PettyCashEntryQuery {
  from?: string;
  to?: string;
  holderId?: string;
  // Several kinds are sent as "expense,credit".
  kind?: PettyCashKind | readonly PettyCashKind[];
  status?: PettyCashStatus;
  q?: string;
  page?: number;
  pageSize?: number;
}

export interface PettyCashVehicleOption {
  id: string;
  companyId: string;
  companyName: string;
  registration: string;
  active: boolean;
}

export interface PettyCashItemOption {
  id: string;
  name: string;
  categoryId: string;
  categoryName: string;
  bucket: PettyCashBucket;
}

// What the forms pick from on a date: vehicles in the person's scope, items in use, and floats cash can go to.
export interface PettyCashOptions {
  vehicles: PettyCashVehicleOption[];
  items: PettyCashItemOption[];
  holders: PettyCashHolder[];
}

// Create (POST /entries) and change (PUT /entries/{id}). id on a create is a client-made UUID, so a retried create
// is answered with the entry it already made. version is required on a change.
// cash: holderId, date, unitAmount, note?            (units is 1)
// expense: date, vehicleId, expenseItemId, units (above zero, up to three decimals), unitAmount, note?
//          (always on the person's own float)
// credit: date, payee, note (the reason, required), unitAmount, reimbursable?, holderId? (issuers only)
export interface SavePettyCashEntry {
  id?: string;
  kind: PettyCashKind;
  holderId?: string | null;
  date: string;
  vehicleId?: string | null;
  expenseItemId?: string | null;
  units?: number;
  unitAmount: number;
  payee?: string | null;
  note?: string | null;
  reimbursable?: boolean;
  version?: number;
}

export interface PettyCashSaved {
  id: string;
  version: number;
  status: PettyCashStatus | null;
  balance: number;
}

export interface ReviewPettyCashEntry {
  version: number;
}

export interface SendBackPettyCashEntry {
  version: number;
  comment: string;
}

export interface RemovePettyCashEntry {
  version: number;
  reason: string;
}

export interface ApprovePettyCashDay {
  date: string;
  holderId?: string | null;
}

// skipped counts the waiting entries of that day this person could not approve (own, above limit, out of scope).
export interface PettyCashDayApproved {
  approved: number;
  total: number;
  skipped: number;
}

export interface PettyCashDashboardFloat {
  balance: number;
  waitingCount: number;
  waitingTotal: number;
  sentBackCount: number;
  approvedThisMonth: number;
}

export interface PettyCashDashboardHolder {
  holderId: string;
  name: string;
  count: number;
  total: number;
  oldest: string;
}

export interface PettyCashDashboardApprovals {
  count: number;
  total: number;
  approvalLimit: number | null;
  aboveLimit: number;
  holders: PettyCashDashboardHolder[];
}

// Each card is null unless the person holds its permission (dash.float, dash.pettycash).
export interface PettyCashDashboard {
  float: PettyCashDashboardFloat | null;
  approvals: PettyCashDashboardApprovals | null;
}

export const PETTY_CASH_AMOUNT_ERROR =
  "Enter an amount other than zero, with at most two decimals. Use a minus sign for money coming back.";
export const PETTY_CASH_UNITS_ERROR =
  "Enter units above zero, with at most three decimals.";

export type PettyCashAmountResult =
  | { ok: true; amount: number }
  | { ok: false; error: typeof PETTY_CASH_AMOUNT_ERROR };

const PLAIN_AMOUNT = /^-?\d{1,12}(\.\d{1,2})?$/;
const GROUPED_AMOUNT = /^-?\d{1,3}(,\d{3})+(\.\d{1,2})?$/;

export function parsePettyCashAmount(value: string): PettyCashAmountResult {
  const trimmed = value.replace(/\s/g, "");
  if (!PLAIN_AMOUNT.test(trimmed) && !GROUPED_AMOUNT.test(trimmed))
    return { ok: false, error: PETTY_CASH_AMOUNT_ERROR };
  const amount = Number(trimmed.replace(/,/g, ""));
  if (amount === 0) return { ok: false, error: PETTY_CASH_AMOUNT_ERROR };
  return { ok: true, amount };
}

const PLAIN_UNITS = /^\d{1,9}(\.\d{1,3})?$/;
const GROUPED_UNITS = /^\d{1,3}(,\d{3}){1,2}(\.\d{1,3})?$/;

// Units can be part of one, such as 4.5 litres of oil or 11.875 litres of fuel.
export function parsePettyCashUnits(value: string): number | null {
  const trimmed = value.replace(/\s/g, "");
  if (!PLAIN_UNITS.test(trimmed) && !GROUPED_UNITS.test(trimmed)) return null;
  const units = Number(trimmed.replace(/,/g, ""));
  return units > 0 ? units : null;
}

// The server's rule for a line's total: units times the amount each, rounded to the cent with halves away from zero.
// Worked in whole thousandths of a unit and whole cents, so 11.875 x 182.40 is exactly 2,166.00.
export function pettyCashTotal(units: number, unitAmount: number): number {
  const product =
    BigInt(Math.round(units * 1000)) * BigInt(Math.round(unitAmount * 100));
  const negative = product < BigInt(0);
  const size = negative ? -product : product;
  const thousand = BigInt(1000);
  const cents =
    size / thousand + (size % thousand >= BigInt(500) ? BigInt(1) : BigInt(0));
  return (negative ? -Number(cents) : Number(cents)) / 100;
}

export const pettyCashEntriesPath = (query: PettyCashEntryQuery = {}) =>
  withQuery("setup/pettycash/entries", query);

export const pettyCashOverviewPath = (query: PettyCashOverviewQuery = {}) =>
  withQuery("setup/pettycash/overview", query);
