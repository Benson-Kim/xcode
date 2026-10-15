import { entryText } from "@xcode/shared/capture";
import type { Formatter } from "@xcode/shared/format";
import {
  awaitsCapture,
  parseRevenueAmount,
  REVENUE_REASONS,
  STATUS_META,
  type RevenueCell,
  type RevenueReason,
  type RevenueVehicle,
  type RevenueWeek,
  type SaveRevenue,
} from "@xcode/shared/revenue";

export const isReason = (value: string | null): value is RevenueReason =>
  REVENUE_REASONS.includes(value as RevenueReason);

// The fleet's low-day threshold until the week says otherwise (a system setting, v2.29).
export const DEFAULT_LOW_DAY_THRESHOLD = 4000;

// The day being captured, and the vehicles already done for that day in this run, so a grid that has not reloaded
// yet never sends capture back to them.
export type Capture = {
  vehicleId: string;
  date: string;
  done: string[];
};

export function captureAt(
  vehicle: Pick<RevenueVehicle, "id">,
  date: string,
  done: string[] = [],
): Capture {
  return { vehicleId: vehicle.id, date, done };
}

export function entryLabel(
  formats: Formatter,
  entry: Pick<RevenueCell, "amount" | "reason" | "note">,
) {
  // A low day shows the amount with its reason: "KES 2,500, Garage".
  if (entry.amount !== null && entry.reason)
    return `${formats.kes(entry.amount)}, ${entry.reason}`;
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
  threshold: number;
  formats: Pick<Formatter, "kes">;
};

// What the person typed or picked as a record to save, or what is wrong with it. A day below the threshold cannot
// be saved without a reason; at or above it, no reason is kept (v2.29).
export function readEntry({
  amount,
  reason,
  threshold,
  formats,
}: Typed): SaveRevenue | string {
  const parsedAmount = parseRevenueAmount(amount);
  if (!parsedAmount.ok) return parsedAmount.error;
  const value = parsedAmount.amount;
  if (value !== null && value >= threshold)
    return { amount: value, reason: null, note: null };
  if (!reason)
    return value !== null
      ? `Choose the reason. Revenue is below ${formats.kes(threshold)}.`
      : "Enter the revenue, or choose the reason for no revenue.";
  return { amount: value, reason, note: null };
}

// Where "Capture revenue" opens: the oldest missing day, or today, on the first vehicle with no record for it
// (v2.30). Never before the earliest day the person may still change.
export function captureStart(
  week: RevenueWeek,
  earliest: string | null | undefined,
): { vehicleId: string; date: string } | null {
  let date = week.firstGap?.date ?? week.businessDate;
  if (earliest && date < earliest) date = earliest;
  const first = week.vehicles[0];
  if (!first) return null;
  if (week.firstGap && week.firstGap.date === date)
    return { vehicleId: week.firstGap.vehicleId, date };
  const open =
    week.vehicles.find((vehicle) =>
      vehicle.days.some((day) => day.date === date && awaitsCapture(day)),
    ) ?? first;
  return { vehicleId: open.id, date };
}
