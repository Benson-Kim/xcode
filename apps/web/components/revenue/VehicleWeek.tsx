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
import { TONE_CLASS } from "./styles";

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
    <table className="ml-6 w-[calc(100%-24px)] max-[720px]:ml-0 max-[720px]:w-full">
      <caption className="sr-only">{vehicle.registration} week detail</caption>
      <thead>
        <tr>
          <th scope="col">Day</th>
          <th scope="col" className="r">
            Expected
          </th>
          <th scope="col" className="r">
            Revenue
          </th>
          <th scope="col" className="r">
            Difference
          </th>
          <th scope="col">
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
        <tr>
          <th scope="row" className="tracking-normal normal-case">
            To date
          </th>
          <td className="r tot">
            {formats.formatNumber(vehicle.totalExpected)}
          </td>
          <td className="r tot">{formats.formatNumber(vehicle.totalAmount)}</td>
          <td className="r tot">
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
  return <span className="chip mute">{cell.reason}</span>;
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
    <th scope="row" className="font-normal tracking-normal normal-case">
      {`${day?.shortName} ${day?.dayOfMonth}`}
    </th>
  );
  const meta = STATUS_META[cell.status];
  if (!meta.inFleet)
    return (
      <tr className={TONE_CLASS[meta.tone]}>
        {label}
        <td colSpan={4}>{meta.label}</td>
      </tr>
    );
  const expected = <td className="r">{formats.formatNumber(cell.expected)}</td>;
  if (!meta.recorded && !meta.awaitsCapture)
    return (
      <tr className={TONE_CLASS[meta.tone]}>
        {label}
        {expected}
        <td />
        <td />
        <td />
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
        <td className="r">{revenue}</td>
        <td />
        <td />
      </tr>
    );
  const actual = cell.amount ?? 0;
  const share = cell.expected ? Math.round((actual / cell.expected) * 100) : 0;
  return (
    <tr>
      {label}
      {expected}
      <td className="r">{revenue}</td>
      <td className="r">
        <Gap actual={actual} expected={cell.expected} />
      </td>
      <td>
        <div data-bar aria-hidden="true" className="prog">
          <div className="t">
            <i
              className={share >= 100 ? "full" : undefined}
              style={{ width: `${Math.min(share, 100)}%` }}
            />
          </div>
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
