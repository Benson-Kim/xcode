// Revenue as the phone sees it: the API's shapes (contract C2, shared with XCODE Web) and what the phone keeps
// until the API has accepted it.
export type { RevenueCell, RevenueStatus, RevenueVehicle, RevenueWeek, SaveRevenue } from "@xcode/shared";
import type { RevenueCell, RevenueDashboard as SharedDashboard } from "@xcode/shared";

// The API leaves a figure null when the person may not see it (revenue, expected and percent, and today's capture
// counts, without dash.revenue or dash.capture; missing days without dash.gaps; edited records without dash.edits).
type Figures = "revenue" | "expected" | "percent" | "capturedToday" | "vehiclesToday" | "missingDays" | "missingVehicles" | "editedRecords";
export type RevenueDashboard = Omit<SharedDashboard, Figures> & { [K in Figures]: number | null };

export const REASONS = ["Garage", "Arrest", "No Crew", "Other"] as const;
export type RevenueReason = (typeof REASONS)[number];

// Other needs a short description of what happened.
export const NOTE_LIMIT = 80;

// What the API holds for a day, as a 409 reports it.
export type SavedValue = Pick<RevenueCell, "amount" | "reason" | "note"> & { version: number | null };

// pending: waiting to be sent. blocked: the API wants an earlier day first, and it is sent again once that day is in.
// conflict: the day already holds a different record; the person keeps it or replaces it with theirs.
// failed: refused (not permitted, vehicle out of scope, invalid); kept until the person tries again or discards it.
export type QueueState = "pending" | "blocked" | "conflict" | "failed";

// A capture kept on this phone until the API accepts it. Nothing leaves the queue except on a 200 or the person's discard.
export interface QueuedCapture {
  vehicleId: string;
  registration: string;
  date: string;
  amount: number | null;
  reason: RevenueReason | null;
  note: string | null;
  // null for a new record; a correction sends the version it was read at.
  version: number | null;
  state: QueueState;
  message: string;
  // With blocked: the day to capture first.
  earliestMissing: string | null;
  // With conflict: what the API holds, once known.
  current: SavedValue | null;
  queuedAt: number;
}

// The error bodies C2 defines for a save (ProblemDetails plus its extensions).
export interface RevenueProblem {
  title?: string;
  detail?: string;
  current?: RevenueCell;
  earliestMissing?: string;
}
