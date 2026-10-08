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

// The day being captured and the day the person set out to fill (an earlier gap opens first), plus the vehicles
// already done for that day in this run, so a grid that has not reloaded yet never sends capture back to them.
export type Capture = {
  vehicleId: string;
  date: string;
  target: string;
  info: string;
  done: string[];
};

// A missing day waits for the vehicle's earliest gap, so a tap on a later one opens that gap first.
export function captureAt(
  formats: Formatter,
  vehicle: RevenueVehicle,
  day: string,
  at: Opening,
  done: string[] = [],
): Capture {
  const info = at.earlier
    ? `Fill ${formats.formatWeekdayDate(at.earlier)} first.`
    : "";
  return { vehicleId: vehicle.id, date: at.date, target: day, info, done };
}

export function openAt(
  formats: Formatter,
  vehicle: RevenueVehicle,
  day: string,
  businessDate: string,
  done: string[] = [],
): Capture {
  return captureAt(
    formats,
    vehicle,
    day,
    openingFor(vehicle, day, { businessDate }),
    done,
  );
}

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
