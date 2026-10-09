import { daysBetween, shiftDate } from "@xcode/shared/dates";
import {
  parseRevenueAmount,
  type RevenueCell,
  type RevenueDay,
  type RevenueReason,
  type RevenueWeek,
  type SaveRevenueDay,
} from "@xcode/shared/revenue";

import { isReason, readEntry } from "./capture";

// What one row of the day holds while it is being typed.
export type DayEntry = {
  amount: string;
  reason: RevenueReason | "";
  note: string;
};

export const entryOf = (cell: RevenueCell): DayEntry => ({
  amount: cell.amount === null ? "" : String(cell.amount),
  reason: isReason(cell.reason) ? cell.reason : "",
  note: cell.note ?? "",
});

const same = (a: DayEntry, b: DayEntry) =>
  a.amount.trim() === b.amount.trim() &&
  a.reason === b.reason &&
  (a.reason !== "Other" || a.note.trim() === b.note.trim());

export type DayProblem = { vehicleId: string; message: string };

// The rows to send: each changed row the person may edit, with the version it was read at. A row left blank is
// skipped, since its day can be filled later; a saved row cannot be emptied. Problems name the vehicle.
export function dayRows(
  day: RevenueDay,
  typed: Readonly<Record<string, DayEntry>>,
  canChooseReason: boolean,
) {
  const rows: SaveRevenueDay["rows"] = [];
  const problems: DayProblem[] = [];
  for (const vehicle of day.vehicles) {
    const entry = typed[vehicle.id];
    const cell = vehicle.day;
    if (!entry || !cell.canEdit || same(entry, entryOf(cell))) continue;
    const blank = !entry.amount.trim() && !entry.reason;
    const next = blank
      ? cell.version == null
        ? null
        : "Enter the revenue or pick a reason. A saved day cannot be emptied."
      : readEntry({ ...entry, canChooseReason });
    if (typeof next === "string")
      problems.push({
        vehicleId: vehicle.id,
        message: `${vehicle.registration}: ${next}`,
      });
    else if (next)
      rows.push({
        vehicleId: vehicle.id,
        ...next,
        version: cell.version ?? null,
      });
  }
  return { rows, problems };
}

// The day's total as typed: every row's amount, saved or new, that reads as one.
export function dayTotal(
  day: RevenueDay,
  typed: Readonly<Record<string, DayEntry>>,
) {
  return day.vehicles.reduce((total, vehicle) => {
    const parsed = parseRevenueAmount(
      (typed[vehicle.id] ?? entryOf(vehicle.day)).amount,
    );
    return parsed.ok && parsed.amount !== null ? total + parsed.amount : total;
  }, 0);
}

// Where Capture revenue opens: the latest day before the business date in the week on screen that a vehicle is still
// missing, otherwise the business date, or the week's last day for a past week.
export function captureDayFor(week: RevenueWeek) {
  const through = shiftDate(week.weekStart, 6);
  const last = through < week.businessDate ? through : week.businessDate;
  let latest: string | null = null;
  for (const vehicle of week.vehicles)
    for (const cell of vehicle.days)
      if (
        cell.status === "missing" &&
        cell.date < week.businessDate &&
        (latest === null || cell.date > latest)
      )
        latest = cell.date;
  return latest ?? last;
}

// The first day of the week a date falls in, from any first day of a week.
export const weekStartFor = (date: string, anyWeekStart: string) =>
  shiftDate(anyWeekStart, Math.floor(daysBetween(anyWeekStart, date) / 7) * 7);
