import type { Formatter } from "./format";
import {
  awaitsCapture,
  type RevenueCell,
  type RevenueVehicle,
  type RevenueWeek,
} from "./revenue";

// Whether the caller has already dealt with the vehicle's day (a capture waiting on the phone, or done in this run).
export type Handled = (vehicleId: string, date: string) => boolean;

export const notHandled: Handled = () => false;

export const cellOn = (
  vehicle: RevenueVehicle,
  date: string,
): RevenueCell | undefined => vehicle.days.find((cell) => cell.date === date);

export const activeOn = (vehicle: RevenueVehicle, date: string): boolean =>
  vehicle.joinedOn <= date &&
  (vehicle.leftOn === null || date < vehicle.leftOn);

// Still needs a record. Inside the loaded week the cell says so. Anywhere else only the vehicle's earliest gap is known
// to be missing: days are captured in any order, so a later day outside the week may or may not have a record.
export function needsRecord(
  vehicle: RevenueVehicle,
  date: string,
  handled: Handled = notHandled,
): boolean {
  if (handled(vehicle.id, date)) return false;
  const cell = cellOn(vehicle, date);
  if (cell) return awaitsCapture(cell);
  return activeOn(vehicle, date) && vehicle.earliestMissing === date;
}

// The first day, up to the business date, that the vehicle is known to still need: its earliest gap, or a missing
// cell of the loaded week, whichever comes first. earliestMissing leaves out today, so today counts only when the
// loaded week holds it.
export function earliestNeeded(
  vehicle: RevenueVehicle,
  week: Pick<RevenueWeek, "businessDate">,
  handled: Handled = notHandled,
): string | null {
  let first: string | null = null;
  const days = [
    vehicle.earliestMissing,
    ...vehicle.days.map((cell) => cell.date),
  ];
  for (const date of days)
    if (
      date !== null &&
      date <= week.businessDate &&
      (first === null || date < first) &&
      needsRecord(vehicle, date, handled)
    )
      first = date;
  return first;
}

export function earliestNeededDay(
  week: RevenueWeek,
  handled: Handled = notHandled,
): string | null {
  let first: string | null = null;
  for (const vehicle of week.vehicles) {
    const date = earliestNeeded(vehicle, week, handled);
    if (date && (!first || date < first)) first = date;
  }
  return first;
}

// A missing day offers capture to anyone who may capture; any other day is a correction the API vouches for.
export const canOpen = (cell: RevenueCell, canCapture: boolean): boolean =>
  awaitsCapture(cell) ? canCapture : cell.canEdit;

// Where a tap on a day lands: always that day. earlier is the vehicle's first gap before it, as a hint that it can be
// filled when the record turns up; it never blocks the day.
export type Opening = { date: string; earlier: string | null };

export function openingFor(
  vehicle: RevenueVehicle,
  tapped: string,
  week: Pick<RevenueWeek, "businessDate">,
  handled: Handled = notHandled,
): Opening {
  const first = earliestNeeded(vehicle, week, handled);
  return {
    date: tapped,
    earlier: first !== null && first < tapped ? first : null,
  };
}

// After a save: the next vehicle (this one first, then in grid order, wrapping round) that still needs the same day,
// and where it opens: that day.
export function nextToCapture(
  week: RevenueWeek,
  fromVehicleId: string,
  day: string,
  handled: Handled,
  canCapture: boolean,
): { vehicle: RevenueVehicle; opening: Opening } | null {
  if (!canCapture) return null;
  const from = Math.max(
    0,
    week.vehicles.findIndex((vehicle) => vehicle.id === fromVehicleId),
  );
  for (const vehicle of [
    ...week.vehicles.slice(from),
    ...week.vehicles.slice(0, from),
  ])
    if (needsRecord(vehicle, day, handled))
      return { vehicle, opening: openingFor(vehicle, day, week, handled) };
  return null;
}

// What the day holds: the amount or the reason; null when it holds neither.
export function entryText(
  formats: Pick<Formatter, "kes">,
  entry: Pick<RevenueCell, "amount" | "reason">,
): string | null {
  if (entry.amount !== null) return formats.kes(entry.amount);
  return entry.reason || null;
}
