import { ENTRY_STATUS_LABELS, type EntryStatus } from "./status";

const CLASSES: Record<EntryStatus, string> = {
  waiting: "chip wait",
  sentBack: "chip back",
  approved: "chip ok",
  rejected: "chip bad",
};

export function StatusTag({ status }: { status: EntryStatus | null }) {
  if (!status) return null;
  return <span className={CLASSES[status]}>{ENTRY_STATUS_LABELS[status]}</span>;
}
