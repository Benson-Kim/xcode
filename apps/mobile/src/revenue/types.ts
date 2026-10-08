// Revenue as the phone sees it
export type {
  RevenueCell,
  RevenueDashboard,
  RevenueStatus,
  RevenueVehicle,
  RevenueWeek,
  SaveRevenue,
} from "@xcode/shared/revenue";
import type { RevenueCell, RevenueReason } from "@xcode/shared/revenue";

export type SavedValue = Pick<RevenueCell, "amount" | "reason" | "note"> & {
  version: number | null;
  canEdit?: boolean;
};

// pending: waiting to be sent.
// blocked: the API wants an earlier day first, and it is sent again once that day is in.
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
  version: number | null;
  state: QueueState;
  message: string;
  // With blocked: the day to capture first.
  earliestMissing: string | null;
  // With conflict: what the API holds, once known.
  current: SavedValue | null;
  queuedAt: number;
  attempts: number;
  lastAttemptAt: number;
}

export interface RevenueProblem {
  title?: string;
  detail?: string;
  current?: RevenueCell;
  earliestMissing?: string;
}
