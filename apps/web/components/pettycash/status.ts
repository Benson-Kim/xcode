import {
  PETTY_CASH_STATUS_LABELS,
  type PettyCashEntry,
  type PettyCashStatus,
} from "@xcode/shared/pettyCash";

export type EntryStatus = PettyCashStatus;

export const ENTRY_STATUSES: readonly EntryStatus[] = [
  "waiting",
  "sentBack",
  "approved",
  "rejected",
];

export const ENTRY_STATUS_LABELS: Record<EntryStatus, string> = {
  ...PETTY_CASH_STATUS_LABELS,
  rejected: "Rejected",
};

export const statusOf = (entry: PettyCashEntry): EntryStatus | null =>
  entry.status;

export const isWaiting = (entry: PettyCashEntry) =>
  statusOf(entry) === "waiting";

export const isSentBack = (entry: PettyCashEntry) =>
  statusOf(entry) === "sentBack";

export const isRejected = (entry: PettyCashEntry) =>
  statusOf(entry) === "rejected";

export const isUndecided = (entry: PettyCashEntry) =>
  isWaiting(entry) || isSentBack(entry);

// An expense is approved only while it waits and has not been sent back.
export const canApproveEntry = (entry: PettyCashEntry) =>
  entry.canReview && isWaiting(entry);
