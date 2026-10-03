export type Company = {
  id: string;
  name: string;
  vehicleCount: number
};

export type Vehicle = {
  id: string;
  companyId: string;
  companyName: string;
  registration: string;
  joinedOn: string;
  weeklyTarget: number;
  targets?: { effectiveFrom: string; weeklyAmount: number; revision: number }[];
  recurringItems?: number;
};

// What the recurring editor needs to pick vehicles (GET recurring/vehicle-options).
export type VehicleOption = Pick<Vehicle, "id" | "companyId" | "companyName" | "registration">;

export type HistoryRow = {
  version: number;
  section: string;
  entityId: string;
  reason: string;
  occurredAt: string;
  actorId: string;
  actorName: string;
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
  allocations: { vehicleId: string; amount: number; registration?: string | null }[];
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
