import {
  PETTY_CASH_STATUS_LABELS,
  type PettyCashStatus,
} from "@xcode/shared/pettyCash";

import { StatusBadge } from "../ui";

const TONES = { waiting: "warn", approved: "ok", sentBack: "off" } as const;

export function StatusTag({ status }: { status: PettyCashStatus }) {
  return (
    <StatusBadge tone={TONES[status]}>
      {PETTY_CASH_STATUS_LABELS[status]}
    </StatusBadge>
  );
}
