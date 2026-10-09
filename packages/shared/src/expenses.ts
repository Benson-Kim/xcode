// Central expenses: the ledger of record for money out against vehicles. Every row holds exactly one vehicle, and
// three sources land in it:
// - central: recorded straight onto vehicles by someone with expenses.capture; the only rows edited in the ledger.
// - pettycash: a petty cash expense, present only while it is approved.
// - scheduled: a scheduled cost posted in full on its run date, never before, one row per vehicle.
// A purchase shared by several vehicles is recorded once and saved as one row per vehicle. Each row keeps the
// purchase (group) so price reports use the true unit cost and quantity.

import { pettyCashTotal } from "./pettyCash";
import { withQuery } from "./query";

export type ExpenseSource = "central" | "pettycash" | "scheduled";
export type ExpenseBucket = 1 | 2 | 3;

export const EXPENSE_SOURCES: readonly ExpenseSource[] = [
  "central",
  "pettycash",
  "scheduled",
];

export const EXPENSE_SOURCE_LABELS: Record<ExpenseSource, string> = {
  central: "Central",
  pettycash: "Petty cash",
  scheduled: "Scheduled",
};

export const EXPENSE_NOTE_LIMIT = 80;
export const EXPENSE_REASON_LIMIT = 500;
export const EXPENSE_MAX_VEHICLES = 50;
export const EXPENSE_PAGE_SIZE = 100;
// The longest period one ledger or report request covers, in days.
export const EXPENSE_MAX_DAYS = 367;

// What the signed-in person may do on the ledger. canRecord is expenses.capture. Each central row also carries its
// own canEdit and canRemove: expenses.correct changes any central row, and expenses.capture changes the person's
// own rows dated on the business date.
export interface ExpensePermissions {
  canRecord: boolean;
  canCorrect: boolean;
}

// The whole period, every source, whatever the source filter and search. total = central + pettyCash + scheduled.
export interface ExpenseFigures {
  total: number;
  central: number;
  pettyCash: number;
  scheduled: number;
}

// The purchase a central row came from when it was shared by several vehicles: size rows, total in all, and the
// units and unit amount as bought.
export interface ExpenseGroup {
  id: string;
  size: number;
  total: number;
  units: number;
  unitAmount: number;
}

export interface ExpenseLedgerRow {
  // The entry's id; for a scheduled row "{scheduleId}:{date}:{vehicleId}".
  id: string;
  source: ExpenseSource;
  date: string;
  vehicleId: string;
  registration: string;
  expenseItemId: string | null;
  // The item's name, or the schedule's name for a scheduled row.
  itemName: string;
  categoryName: string | null;
  bucket: ExpenseBucket;
  units: number;
  unitAmount: number;
  total: number;
  note: string | null;
  // Null for a scheduled row, which is a standing order.
  recordedByName: string | null;
  // Petty cash: whose float it came from.
  holderName: string | null;
  // Scheduled: the scheduled item that posted it.
  scheduleId: string | null;
  group: ExpenseGroup | null;
  // Central rows only.
  version: number | null;
  canEdit: boolean;
  canRemove: boolean;
}

// Newest first. total and amount count every row matching source and q, not only this page.
export interface ExpenseLedger {
  businessDate: string;
  from: string;
  to: string;
  permissions: ExpensePermissions;
  figures: ExpenseFigures;
  items: ExpenseLedgerRow[];
  pageNumber: number;
  pageSize: number;
  total: number;
  amount: number;
}

export interface ExpenseLedgerQuery {
  from: string;
  to: string;
  source?: ExpenseSource;
  q?: string;
  page?: number;
  pageSize?: number;
}

export interface ExpenseVehicleOption {
  id: string;
  companyId: string;
  companyName: string;
  registration: string;
  active: boolean;
}

export interface ExpenseItemOption {
  id: string;
  name: string;
  categoryId: string;
  categoryName: string;
  bucket: ExpenseBucket;
}

// What the form picks from on a date: vehicles in the person's scope and items in use.
export interface ExpenseOptions {
  vehicles: ExpenseVehicleOption[];
  items: ExpenseItemOption[];
}

export interface ExpenseAllocation {
  vehicleId: string;
  amount: number;
}

// POST setup/expenses/entries: one purchase, saved as one row per vehicle. id is a client-made UUID, so a retried
// save is answered with the rows it already made. The allocations add up to units x unitAmount exactly; one
// allocation takes the whole total.
export interface RecordExpense {
  id?: string;
  date: string;
  expenseItemId: string;
  units: number;
  unitAmount: number;
  note?: string | null;
  allocations: ExpenseAllocation[];
}

export interface ExpenseRecorded {
  ids: string[];
  total: number;
}

// PUT setup/expenses/entries/{id}: one central row. Changing its item, units or unit amount takes it out of its
// purchase group.
export interface ChangeExpense {
  date: string;
  vehicleId: string;
  expenseItemId: string;
  units: number;
  unitAmount: number;
  note?: string | null;
  version: number;
}

export interface ExpenseSaved {
  id: string;
  version: number;
}

// POST setup/expenses/entries/{id}/remove. Removing is soft: the row leaves every list and total.
export interface RemoveExpense {
  version: number;
  reason: string;
}

// The same rule as petty cash: units times the unit amount, rounded to the cent with halves away from zero.
export const expenseTotal = pettyCashTotal;

// total split over count rows in whole cents, the odd cents going to the first rows: 100 over 3 is 33.34, 33.33, 33.33.
export function splitEvenly(total: number, count: number): number[] {
  if (!Number.isInteger(count) || count < 1) return [];
  const cents = Math.round(total * 100);
  const sign = cents < 0 ? -1 : 1;
  const size = Math.abs(cents);
  const base = Math.floor(size / count);
  const extra = size - base * count;
  return Array.from(
    { length: count },
    // "|| 0" turns the -0 of a zero share of a negative total into 0.
    (_, index) => (sign * (base + (index < extra ? 1 : 0))) / 100 || 0,
  );
}

// What is left to allocate (positive) or allocated over the total (negative), in whole cents.
export function unallocated(
  total: number,
  allocations: readonly { amount: number }[],
): number {
  const given = allocations.reduce(
    (sum, allocation) => sum + Math.round(allocation.amount * 100),
    0,
  );
  return (Math.round(total * 100) - given) / 100;
}

export const expenseLedgerPath = (query: ExpenseLedgerQuery) =>
  withQuery("setup/expenses/ledger", query);

export const expenseOptionsPath = (date?: string) =>
  withQuery("setup/expenses/options", { date });

export const EXPENSE_ENTRIES_PATH = "setup/expenses/entries";

export const expenseEntryPath = (id: string, action?: "remove") =>
  `${EXPENSE_ENTRIES_PATH}/${encodeURIComponent(id)}${action ? `/${action}` : ""}`;
