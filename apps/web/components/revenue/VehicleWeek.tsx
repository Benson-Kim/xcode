import type { ReactNode } from "react";

import { canOpen } from "@xcode/shared/capture";
import type { WeekDay } from "@xcode/shared/dates";
import type { Formatter } from "@xcode/shared/format";
import {
  STATUS_META,
  type RevenueCell,
  type RevenueVehicle,
} from "@xcode/shared/revenue";

import { useFormats } from "../../lib/formats";
import { cn } from "../ui";
import { cellState } from "./capture";
import { MINI, MINI_HEAD, PILL, TONE_CLASS } from "./styles";

type OnOpen = (date: string, from: HTMLElement) => void;

// Expected, actual, difference and a bar for each day of one vehicle's week.
export function VehicleWeek({
  vehicle,
  days,
  today,
  canCapture,
  onOpen,
}: {
  vehicle: RevenueVehicle;
  days: WeekDay[];
  today: string;
  canCapture: boolean;
  onOpen: OnOpen;
}) {
  const formats = useFormats();
  return (
    <table className="ml-6 w-[calc(100%-24px)] border-collapse max-[720px]:ml-0 max-[720px]:w-full">
      <caption className="sr-only">{vehicle.registration} week detail</caption>
      <thead>
        <tr>
          <th scope="col" className={MINI_HEAD}>
            Day
          </th>
          <th scope="col" className={cn(MINI_HEAD, "text-right")}>
            Expected
          </th>
          <th scope="col" className={cn(MINI_HEAD, "text-right")}>
            Revenue
          </th>
          <th scope="col" className={cn(MINI_HEAD, "text-right")}>
            Difference
          </th>
          <th scope="col" className={MINI_HEAD}>
            <span className="sr-only">Share of expected</span>
          </th>
        </tr>
      </thead>
      <tbody>
        {vehicle.days.map((cell, index) => (
          <VehicleDayRow
            key={cell.date}
            vehicle={vehicle}
            cell={cell}
            day={days[index]}
            today={today}
            canCapture={canCapture}
            onOpen={onOpen}
          />
        ))}
        <tr className="font-bold">
          <th scope="row" className="px-2 py-1.5 text-left text-sm">
            To date
          </th>
          <td className="px-2 py-1.5 text-right text-sm tabular-nums">
            {formats.formatNumber(vehicle.totalExpected)}
          </td>
          <td className="px-2 py-1.5 text-right text-sm tabular-nums">
            {formats.formatNumber(vehicle.totalAmount)}
          </td>
          <td className="px-2 py-1.5 text-right text-sm tabular-nums">
            <Gap
              actual={vehicle.totalAmount}
              expected={vehicle.totalExpected}
            />
          </td>
          <td />
        </tr>
      </tbody>
    </table>
  );
}

function revenueValue(formats: Formatter, cell: RevenueCell, today: string) {
  const meta = STATUS_META[cell.status];
  if (meta.awaitsCapture)
    return (
      <span
        className={cn(
          "text-[13px] font-bold",
          cell.date === today ? "text-teal" : TONE_CLASS[meta.tone],
        )}
      >
        {cell.date < today ? "No record" : "Not yet"}
      </span>
    );
  if (cell.amount !== null) return formats.formatNumber(cell.amount);
  return <span className={PILL}>{cell.reason}</span>;
}

function VehicleDayRow({
  vehicle,
  cell,
  day,
  today,
  canCapture,
  onOpen,
}: {
  vehicle: RevenueVehicle;
  cell: RevenueCell;
  day: WeekDay | undefined;
  today: string;
  canCapture: boolean;
  onOpen: OnOpen;
}) {
  const formats = useFormats();
  const label = (
    <th
      scope="row"
      className={cn(MINI, "text-left font-normal whitespace-nowrap")}
    >
      {`${day?.shortName} ${day?.dayOfMonth}`}
    </th>
  );
  const meta = STATUS_META[cell.status];
  if (!meta.inFleet)
    return (
      <tr className={TONE_CLASS[meta.tone]}>
        {label}
        <td colSpan={4} className={MINI}>
          {meta.label}
        </td>
      </tr>
    );
  const expected = (
    <td className={cn(MINI, "text-right")}>
      {formats.formatNumber(cell.expected)}
    </td>
  );
  if (!meta.recorded && !meta.awaitsCapture)
    return (
      <tr className={TONE_CLASS[meta.tone]}>
        {label}
        {expected}
        <td className={MINI} />
        <td className={MINI} />
        <td className={MINI} />
      </tr>
    );
  const value = revenueValue(formats, cell, today);
  const revenue: ReactNode = canOpen(cell, canCapture) ? (
    <button
      type="button"
      data-opens={`${vehicle.id}|${cell.date}`}
      aria-label={`${vehicle.registration}, ${formats.formatWeekdayDate(cell.date)}: ${cellState(formats, cell)}`}
      onClick={(event) => onOpen(cell.date, event.currentTarget)}
      className="min-h-8 rounded-lg px-1.5 underline decoration-dotted underline-offset-4 hover:bg-hover"
    >
      {value}
    </button>
  ) : (
    value
  );
  if (meta.awaitsCapture)
    return (
      <tr>
        {label}
        {expected}
        <td className={cn(MINI, "text-right")}>{revenue}</td>
        <td className={MINI} />
        <td className={MINI} />
      </tr>
    );
  const actual = cell.amount ?? 0;
  const share = cell.expected ? Math.round((actual / cell.expected) * 100) : 0;
  return (
    <tr>
      {label}
      {expected}
      <td className={cn(MINI, "text-right")}>{revenue}</td>
      <td className={cn(MINI, "text-right")}>
        <Gap actual={actual} expected={cell.expected} />
      </td>
      <td className={MINI}>
        <div
          data-bar
          aria-hidden="true"
          className="h-1.5 w-30 overflow-hidden rounded-full bg-card-line max-[720px]:w-12"
        >
          <span
            className={cn("block h-full", share < 90 ? "bg-red" : "bg-blue")}
            style={{ width: `${Math.min(share, 100)}%` }}
          />
        </div>
      </td>
    </tr>
  );
}

function Gap({ actual, expected }: { actual: number; expected: number }) {
  const formats = useFormats();
  return (
    <span
      className={cn(
        actual < expected && "text-red",
        actual > expected && "text-green",
      )}
    >
      {formats.formatDifference(actual, expected)}
    </span>
  );
}
