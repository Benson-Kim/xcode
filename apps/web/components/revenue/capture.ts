import { entryText, openingFor, type Opening } from "@xcode/shared/capture";
import type { Formatter } from "@xcode/shared/format";
import {
  awaitsCapture,
  parseRevenueAmount,
  REVENUE_REASONS,
  STATUS_META,
  type RevenueCell,
  type RevenueReason,
  type RevenueVehicle,
  type SaveRevenue,
} from "@xcode/shared/revenue";

export const isReason = (value: string | null): value is RevenueReason =>
  REVENUE_REASONS.includes(value as RevenueReason);

// The day being captured, the vehicle's earliest gap before it (a hint, never a requirement), and the vehicles already
// done for that day in this run, so a grid that has not reloaded yet never sends capture back to them.
export type Capture = {
  vehicleId: string;
  date: string;
  gap: string | null;
  done: string[];
};

// A tap opens the day that was tapped; an earlier gap is only mentioned.
export function captureAt(
  vehicle: RevenueVehicle,
  at: Opening,
  done: string[] = [],
): Capture {
  return { vehicleId: vehicle.id, date: at.date, gap: at.earlier, done };
}

export function openAt(
  vehicle: RevenueVehicle,
  day: string,
  businessDate: string,
  done: string[] = [],
): Capture {
  return captureAt(vehicle, openingFor(vehicle, day, { businessDate }), done);
}

// The gentle line under the date when the vehicle has an earlier day with no record.
export const gapHint = (formats: Formatter, gap: string) =>
  `No record yet from ${formats.formatWeekdayDate(gap)}. You can fill it when you have it.`;

export function entryLabel(
  formats: Formatter,
  entry: Pick<RevenueCell, "amount" | "reason" | "note">,
) {
  const text = entryText(formats, entry);
  if (text === null) return "No record";
  return entry.amount === null && entry.note ? `${text}: ${entry.note}` : text;
}

export function cellState(formats: Formatter, cell: RevenueCell) {
  const state = awaitsCapture(cell)
    ? STATUS_META[cell.status].label
    : entryLabel(formats, cell);
  return cell.editedAfterCapture ? `${state}, edited after capture` : state;
}

type Typed = {
  amount: string;
  reason: RevenueReason | "";
  note: string;
  canChooseReason: boolean;
};

// What the person typed or picked as a record to save, or what is wrong with it.
export function readEntry({
  amount,
  reason,
  note,
  canChooseReason,
}: Typed): SaveRevenue | string {
  const parsedAmount = parseRevenueAmount(amount);
  if (!parsedAmount.ok) return parsedAmount.error;
  if (parsedAmount.amount !== null)
    return { amount: parsedAmount.amount, reason: null, note: null };
  if (!canChooseReason) return "Enter the revenue.";
  if (!reason) return "Enter the revenue or pick a reason.";
  if (reason === "Other" && !note.trim()) return "Say what happened.";
  return {
    amount: null,
    reason,
    note: reason === "Other" ? note.trim() : null,
  };
}
