import { entryText } from "@xcode/shared/capture";
import type { Formatter } from "@xcode/shared/format";
import {
  awaitsCapture,
  DEFAULT_LOW_BELOW,
  fuelTag,
  keptFuel,
  parseRevenueAmount,
  REVENUE_REASONS,
  STATUS_META,
  type RevenueCell,
  type RevenueFuel,
  type RevenueReason,
  type RevenueVehicle,
  type RevenueWeek,
  type SaveRevenue,
} from "@xcode/shared/revenue";

export const isReason = (value: string | null): value is RevenueReason =>
  REVENUE_REASONS.includes(value as RevenueReason);

// The vehicle's low revenue figure in force on the cell's day (v2.34); a server that does not send it has the
// migration's figure.
export const lowFigure = (cell: Pick<RevenueCell, "lowBelow">): number =>
  cell.lowBelow ?? DEFAULT_LOW_BELOW;

// The amount typed so far, or null while there is none or it is not a valid amount.
export function typedAmount(value: string): number | null {
  const parsed = parseRevenueAmount(value);
  return parsed.ok ? parsed.amount : null;
}

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

type Entry = Pick<RevenueCell, "amount" | "reason" | "note"> & {
  fuel?: RevenueFuel | null;
};

function recordLabel(formats: Formatter, entry: Entry) {
  // A low day shows the amount with its reason: "KES 2,500, Garage".
  if (entry.amount !== null && entry.reason)
    return `${formats.kes(entry.amount)}, ${entry.reason}`;
  const text = entryText(formats, entry);
  if (text === null) return "No record";
  return entry.amount === null && entry.note ? `${text}: ${entry.note}` : text;
}

// "KES 12,600, Not fueled": only the No answer is ever shown (v2.37).
export function entryLabel(formats: Formatter, entry: Entry) {
  const label = recordLabel(formats, entry);
  const tag = entry.amount !== null ? fuelTag(entry.fuel) : null;
  return tag ? `${label}, ${tag}` : label;
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
  fuel: RevenueFuel | null;
  // The vehicle's low revenue figure for the day, and the amount from which the Fueled? question is asked.
  lowBelow: number;
  fuelQuestionFrom: number;
  formats: Pick<Formatter, "kes">;
};

// What the person typed or picked as a record to save, or what is wrong with it. A day below the vehicle's low
// figure cannot be saved without a reason; at or above it, no reason is kept (v2.34). The fuel answer is always
// sent, so clearing it clears the saved one: none without an amount, and Yes only where the question is asked.
export function readEntry({
  amount,
  reason,
  fuel,
  lowBelow,
  fuelQuestionFrom,
  formats,
}: Typed): SaveRevenue | string {
  const parsedAmount = parseRevenueAmount(amount);
  if (!parsedAmount.ok) return parsedAmount.error;
  const value = parsedAmount.amount;
  const answer = keptFuel(fuel, value, fuelQuestionFrom);
  if (value !== null && value >= lowBelow)
    return { amount: value, reason: null, note: null, fuel: answer };
  if (!reason)
    return value !== null
      ? `Choose the reason. Revenue is below ${formats.kes(lowBelow)}.`
      : "Enter the revenue, or choose the reason for no revenue.";
  return { amount: value, reason, note: null, fuel: answer };
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
