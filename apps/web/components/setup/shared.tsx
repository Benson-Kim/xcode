import type { ExpenseBucket } from "../../lib/types";

export type Company = { id: string; name: string; vehicleCount: number; active?: boolean; archivedOn?: string | null };

export type Vehicle = {
  id: string;
  companyId: string;
  companyName: string;
  registration: string;
  joinedOn: string;
  leftOn?: string | null;
  active?: boolean;
  weeklyTarget: number;
  targets?: { effectiveFrom: string; weeklyAmount: number; revision: number }[];
  recurringItems?: number;
};

// What the scheduled-item editor needs to pick vehicles (GET recurring/vehicle-options).
export type VehicleOption = Pick<Vehicle, "id" | "companyId" | "companyName" | "registration"> & { active?: boolean };

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
// A cost picks an expense item (its bucket comes from the item's category); `category` is only set on legacy rows.
export type RecurringItem = {
  id: string;
  name: string;
  kind: number;
  category?: number | null;
  // The saved total of every share, including vehicles that have left the fleet; activeAmount is what still posts.
  amount: number;
  activeAmount?: number;
  frequency: number;
  day?: number | null;
  lastDay: boolean;
  start: string;
  end?: string | null;
  stoppedFrom?: string | null;
  allocations: { vehicleId: string; amount: number; registration?: string | null; active?: boolean }[];
  // Also posts to vehicles outside the viewer's scope: amount and allocations are only their share, and it is read-only.
  partial?: boolean;
  expenseItemId?: string | null;
  expenseItemName?: string | null;
  bucket?: ExpenseBucket | null;
  note?: string | null;
  month?: number | null;
};

// A scheduled item's share falling due on a day. Every cost carries its bucket; savings have none.
export type Posting = {
  itemId: string;
  versionId: string;
  date: string;
  name: string;
  kind: number;
  category?: number | null;
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

// The bucket a cost posting counts under. The API sends one for every cost; a Phase 1 row without one follows its old
// category (assumption A2): repairs and upkeep count as repairs and maintenance, the other three as recurring charges.
export function postingBucket(posting: Pick<Posting, "bucket" | "category">): ExpenseBucket {
  return posting.bucket ?? (posting.category === 2 ? 1 : 2);
}

// The cost types used before expense items. Rows saved with them stay readable.
export const recurringCategoryNames: Record<number, string> = {
  1: "Running costs",
  2: "Repairs and upkeep",
  3: "Crew costs",
  4: "Fixed commitments",
};
