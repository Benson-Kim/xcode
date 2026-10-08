import { plural, type Formatter } from "@xcode/shared/format";
import type { PettyCashDashboard } from "@xcode/shared/pettyCash";

import { balanceText } from "./format";

export const PETTY_CASH_CARDS = ["dash.float", "dash.pettycash"];

export type PettyFigures = {
  value: string;
  bad?: boolean;
  note?: string;
  list?: string[];
};

// What a petty cash card shows, or null when the API left that part out (not shown to this person).
export function pettyFigures(
  formats: Formatter,
  permission: string,
  dashboard: PettyCashDashboard,
): PettyFigures | null {
  const { kes } = formats;
  if (permission === "dash.float") {
    const float = dashboard.float;
    if (!float) return null;
    const waiting = float.waitingCount
      ? `${plural(float.waitingCount, "entry", "entries")}, ${kes(float.waitingTotal)}, waiting for approval`
      : "Nothing is waiting for approval";
    return {
      value: balanceText(formats, float.balance),
      bad: float.balance < 0,
      note: [
        waiting,
        float.sentBackCount
          ? `${plural(float.sentBackCount, "entry was", "entries were")} sent back to you`
          : "",
        `${kes(float.approvedThisMonth)} approved this month`,
      ]
        .filter(Boolean)
        .join(". "),
    };
  }
  const approvals = dashboard.approvals;
  if (!approvals) return null;
  const limit =
    approvals.approvalLimit === null
      ? ""
      : ` You can approve entries up to ${kes(approvals.approvalLimit)}${
          approvals.aboveLimit
            ? `. ${plural(approvals.aboveLimit, "entry is", "entries are")} above your limit.`
            : ". All are within your limit."
        }`;
  return {
    value: plural(approvals.count, "entry", "entries"),
    note: approvals.count
      ? `${kes(approvals.total)} in total.${limit}`
      : "Nothing is waiting for approval.",
    list: approvals.holders.map(
      (holder) =>
        `${holder.name}: ${plural(holder.count, "entry", "entries")}, ${kes(holder.total)}, oldest ${formats.formatDateOnly(holder.oldest)}`,
    ),
  };
}
