import {
  canOpen,
  entryText,
  openingFor,
  type Handled,
  type Opening,
} from "@xcode/shared/capture";
import type { Formatter } from "@xcode/shared/format";
import { isRecorded, type StatusTone } from "@xcode/shared/revenue";

import type {
  QueuedCapture,
  RevenueCell,
  RevenueVehicle,
  RevenueWeek,
} from "../../revenue/types";
import type { useTheme } from "../../ui";

export type Colors = ReturnType<typeof useTheme>["colors"];

export type ViewMode = "day" | "week";
export const MODES: { value: ViewMode; label: string }[] = [
  { value: "day", label: "Day" },
  { value: "week", label: "Week" },
];

export const OFFLINE_EMPTY =
  "No internet. Revenue needs a connection to load. Captures already on this phone are kept and sent when you are back online.";
export const OFFLINE_SAVED =
  "No internet. Showing what this phone loaded earlier. Captures are kept on this phone and sent when you are back online.";
// The same notices for a phone that is connected while the server does not answer.
export const UNREACHABLE_EMPTY =
  "Can't reach the XCODE server. Revenue needs it to load. Captures already on this phone are kept until it answers.";
export const UNREACHABLE_SAVED =
  "Can't reach the XCODE server. Showing what this phone loaded earlier. Captures are kept on this phone until it answers.";

export type Waiting = ReadonlyMap<string, QueuedCapture>;

export const keyOf = (vehicleId: string, date: string) =>
  `${vehicleId}/${date}`;

export const cellOf = (vehicle: RevenueVehicle, date: string) =>
  vehicle.days.find((cell) => cell.date === date);

export const TONE_COLOR: Record<StatusTone, keyof Colors> = {
  muted: "grey",
  normal: "navy",
  alert: "red",
};

export const valueText = (
  formats: Formatter,
  entry: { amount: number | null; reason: string | null },
) => entryText(formats, entry) ?? "";

// Captures waiting on this phone count as done.
export const handledBy =
  (waiting: Waiting): Handled =>
  (vehicleId, date) =>
    waiting.has(keyOf(vehicleId, date));

// What a tap on a vehicle's day opens: that day (earlier is the vehicle's first gap before it, a hint), or nothing.
export type Target = {
  vehicle: RevenueVehicle;
  date: string;
  cell?: RevenueCell;
  waiting?: QueuedCapture;
  earlier: string | null;
};

export const targetAt = (
  vehicle: RevenueVehicle,
  opening: Opening,
): Target => ({
  vehicle,
  date: opening.date,
  cell: cellOf(vehicle, opening.date),
  earlier: opening.earlier,
});

export function targetFor(
  vehicle: RevenueVehicle,
  date: string,
  week: RevenueWeek,
  waiting: Waiting,
  canCapture: boolean,
): Target | null {
  const cell = cellOf(vehicle, date);
  const queued = waiting.get(keyOf(vehicle.id, date));
  // A conflict is settled with Keep saved value or Replace with mine.
  if (queued)
    return queued.state === "conflict"
      ? null
      : { vehicle, date, cell, waiting: queued, earlier: null };
  // Changing a record: the API says whether this person may (today with capture or correct, a past day with correct).
  if (!cell || !canOpen(cell, canCapture)) return null;
  if (isRecorded(cell)) return { vehicle, date, cell, earlier: null };
  return targetAt(vehicle, openingFor(vehicle, date, week, handledBy(waiting)));
}

export const STATE_TAG: Record<QueuedCapture["state"], string> = {
  pending: "Not sent yet",
  conflict: "Conflict",
  failed: "Not saved",
};

export type DayRowData = {
  vehicle: RevenueVehicle;
  cell: RevenueCell;
  queued?: QueuedCapture;
  tappable: boolean;
};

export const onCurrentWeek = (week: RevenueWeek) =>
  week.weekStart >= week.currentWeekStart;
