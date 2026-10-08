import { plural, type Formatter } from "@xcode/shared/format";
import type {
  PettyCashDashboardApprovals,
  PettyCashDashboardFloat,
  PettyCashStatus,
} from "@xcode/shared/pettyCash";

export type PettyCashCardRow = {
  id: string;
  left: string;
  leftSub: string;
  right: string;
  rightSub: string;
};

export type PettyCashCardFigures = {
  value: string;
  bad?: boolean;
  note: string;
  list?: PettyCashCardRow[];
  // The status Petty cash opens filtered to.
  status?: PettyCashStatus;
};

// "My petty cash float": cash in hand, and what of it still waits for approval.
export function floatFigures(
  formats: Formatter,
  float: PettyCashDashboardFloat,
): PettyCashCardFigures {
  const waiting =
    float.waitingCount > 0
      ? `${plural(float.waitingCount, "entry", "entries")}, ${formats.kes(float.waitingTotal)}, waiting for approval.`
      : "Nothing is waiting for approval.";
  const sentBack =
    float.sentBackCount > 0
      ? ` ${plural(float.sentBackCount, "entry was", "entries were")} sent back.`
      : "";
  return {
    value: formats.kes(float.balance),
    bad: float.balance < 0,
    note: `${waiting}${sentBack} ${formats.kes(float.approvedThisMonth)} approved this month.`,
    status: float.sentBackCount > 0 ? "sentBack" : undefined,
  };
}

// "Petty cash to approve": what waits across the floats this person can see, and who holds it.
export function approvalsFigures(
  formats: Formatter,
  approvals: PettyCashDashboardApprovals,
): PettyCashCardFigures {
  if (approvals.count === 0)
    return {
      value: plural(0, "entry", "entries"),
      note: "Nothing is waiting for approval.",
    };
  let note = `${formats.kes(approvals.total)} in total.`;
  if (approvals.approvalLimit !== null)
    note += ` You can approve entries up to ${formats.kes(approvals.approvalLimit)}${
      approvals.aboveLimit
        ? `. ${plural(approvals.aboveLimit, "entry is", "entries are")} above your limit.`
        : ". All are within your limit."
    }`;
  return {
    value: plural(approvals.count, "entry", "entries"),
    note,
    status: "waiting",
    list: approvals.holders.map((holder) => ({
      id: holder.holderId,
      left: holder.name,
      leftSub: `Oldest ${formats.formatDateOnly(holder.oldest)}`,
      right: formats.kes(holder.total),
      rightSub: plural(holder.count, "entry", "entries"),
    })),
  };
}
