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

// What the recurring editor needs to pick vehicles (GET recurring/vehicle-options).
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

export type RecurringItem = {
  id: string;
  name: string;
  kind: number;
  category?: number | null;
  amount: number;
  frequency: number;
  day?: number | null;
  lastDay: boolean;
  start: string;
  end?: string | null;
  stoppedFrom?: string | null;
  allocations: { vehicleId: string; amount: number; registration?: string | null; active?: boolean }[];
  // Also posts to vehicles outside the viewer's scope: amount and allocations are only their share, and it is read-only.
  partial?: boolean;
};

export type Posting = { itemId: string; versionId: string; date: string; name: string; kind: number; category?: number | null; amount: number };
export type VehicleReport = { vehicleId: string; from: string; through: string; costs: number; savings: number; postings: Posting[] };

export const recurringCategoryNames: Record<number, string> = {
  1: "Running costs",
  2: "Repairs and upkeep",
  3: "Crew costs",
  4: "Fixed commitments",
};
