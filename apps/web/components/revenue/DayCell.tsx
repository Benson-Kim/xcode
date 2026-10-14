import { memo } from "react";

import { canOpen } from "@xcode/shared/capture";
import {
  STATUS_META,
  type RevenueCell,
  type RevenueVehicle,
} from "@xcode/shared/revenue";

import { useFormats } from "../../lib/formats";
import { cn } from "../ui";
import { cellState } from "./capture";
import type { OpenDay } from "./useCaptureFlow";

// One day of a vehicle's week (v2.29): the amount with the reason in small type under it when the day was low, a
// reason chip for a no revenue day, "Missing" for a past day with no record, "Due" for today. A cell the person
// can change is a button; the server says which (canEdit covers the rights and the back-dating limit).
export const DayCell = memo(function DayCell({
  vehicle,
  cell,
  today,
  canCapture,
  onOpen,
}: {
  vehicle: RevenueVehicle;
  cell: RevenueCell;
  today: string;
  canCapture: boolean;
  onOpen: OpenDay;
}) {
  const formats = useFormats();
  const clickable = canOpen(cell, canCapture) && cell.canEdit;
  const meta = STATUS_META[cell.status];
  const now = cell.date === today;
  const content = meta.recorded ? (
    cell.amount !== null ? (
      <>
        {formats.formatNumber(cell.amount)}
        {cell.reason && <small className="rwhy">{cell.reason}</small>}
      </>
    ) : (
      <span className="chip mute">{cell.reason}</span>
    )
  ) : meta.awaitsCapture ? (
    now ? (
      <span className="due">Due</span>
    ) : (
      <span className="chip wait">{meta.label}</span>
    )
  ) : (
    <span className="sr-only">{meta.label}</span>
  );
  return (
    <td className={cn("r", clickable && "rcell")}>
      {clickable ? (
        <button
          type="button"
          className="rc"
          data-opens={`${vehicle.id}|${cell.date}`}
          title={`${vehicle.registration}, ${formats.formatWeekdayDate(cell.date)}`}
          aria-label={`${vehicle.registration}, ${formats.formatWeekdayDate(cell.date)}: ${cellState(formats, cell)}`}
          onClick={(event) => onOpen(vehicle, cell.date, event.currentTarget)}
        >
          {content}
        </button>
      ) : (
        content
      )}
    </td>
  );
});
