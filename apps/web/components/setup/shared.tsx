import type { ExpenseBucket } from "../../lib/types";

export type Company = {
  id: string;
  name: string;
  vehicleCount: number;
  active?: boolean;
  archivedOn?: string | null;
};

export type Vehicle = {
  id: string;
  companyId: string;
  companyName: string;
  registration: string;
  joinedOn: string;
  leftOn?: string | null;
  active?: boolean;
  // null, with no targets and no count, for someone who lists vehicles only to reach their investment.
  weeklyTarget: number | null;
  targets?: { effectiveFrom: string; weeklyAmount: number; revision: number }[];
  recurringItems?: number | null;
  // Each stretch the vehicle was out of the fleet: away from leftOn through the day before returnedOn (D4).
  away?: { leftOn: string; returnedOn: string }[];
};

// What the scheduled-item editor needs to pick vehicles (GET recurring/vehicle-options).
export type VehicleOption = Pick<
  Vehicle,
  "id" | "companyId" | "companyName" | "registration"
> & { active?: boolean };

export type HistoryRow = {
  version: number;
  section: string;
  entityId: string;
  reason: string;
  occurredAt: string;
  actorId: string;
  actorName: string;
  before?: string | null;
  after?: string | null;
};

// A scheduled expense or saving. Frequency: 1 every day (legacy, read only), 2 weekly, 3 monthly, 4 yearly on `month`.
// A cost picks an expense item, and its bucket comes from that item's category.
export type RecurringItem = {
  id: string;
  name: string;
  kind: number;
  // The saved total of every share, including vehicles not in the fleet today; activeAmount is what posts now.
  amount: number;
  activeAmount?: number;
  frequency: number;
  day?: number | null;
  lastDay: boolean;
  start: string;
  end?: string | null;
  stoppedFrom?: string | null;
  // Paused since that day: it does not run until resumed.
  pausedFrom?: string | null;
  // Savings only: the last day it ran, the vehicles it saved for that day, and all it has set aside on the viewer's
  // vehicles.
  lastRun?: string | null;
  lastRunVehicles?: number;
  balance?: number | null;
  allocations: {
    vehicleId: string;
    amount: number;
    registration?: string | null;
    active?: boolean;
  }[];
  // Also posts to vehicles outside the viewer's scope: amount and allocations are only their share, and it is read-only.
  partial?: boolean;
  expenseItemId?: string | null;
  expenseItemName?: string | null;
  bucket?: ExpenseBucket | null;
  note?: string | null;
  month?: number | null;
};

// GET setup/recurring/summary: the business date's month, with what scheduled expenses post in it, what savings set
// aside in it so far and the savings balance to date.
export type RecurringSummary = {
  from: string;
  to: string;
  costsDue: number;
  saved: number;
  savingsBalance: number;
};

// GET setup/recurring/{id}/runs: the last ten run dates, newest first; total and runCount cover every run to date.
export type RecurringRuns = {
  id: string;
  name: string;
  kind: number;
  start: string;
  total: number;
  runCount: number;
  runs: {
    date: string;
    amount: number;
    shares: { vehicleId: string; registration: string; amount: number }[];
  }[];
};

// One due date of a scheduled item on a vehicle. A cost carries its bucket; a saving has none.
export type Posting = {
  itemId: string;
  versionId: string;
  date: string;
  name: string;
  kind: number;
  amount: number;
  bucket?: ExpenseBucket | null;
};
// GET setup/vehicles/{id}/report (contract C6). moneyOut is the three buckets and never includes investment;
// net = moneyIn - moneyOut and afterSavings = net - savings. costs repeats moneyOut for older screens.
export type VehicleReport = {
  vehicleId: string;
  from: string;
  through: string;
  moneyIn: number;
  target: number;
  repairs: number;
  charges: number;
  loans: number;
  moneyOut: number;
  net: number;
  savings: number;
  afterSavings: number;
  costs: number;
  postings: Posting[];
};

export const expenseBucketNames: Record<ExpenseBucket, string> = {
  1: "Repairs and maintenance",
  2: "Recurring charges",
  3: "Loan repayments",
};

// The bucket a cost counts in: every cost reports under one, and a row saved without one counts as a recurring
// charge, which is how the API reports it too. Savings are not money out and report under none.
export function costBucket(row: {
  kind: number;
  bucket?: ExpenseBucket | null;
}): ExpenseBucket | null {
  if (row.kind !== 1) return null;
  return row.bucket ?? 2;
}

export { RegPlate } from "../ui";
