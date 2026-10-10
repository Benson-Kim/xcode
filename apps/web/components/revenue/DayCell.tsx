import { memo } from "react";

import { canOpen } from "@xcode/shared/capture";
import {
  STATUS_META,
  type RevenueCell,
  type RevenueVehicle,
} from "@xcode/shared/revenue";

import { useFormats } from "../../lib/formats";
import { cellState } from "./capture";
import type { OpenDay } from "./useCaptureFlow";

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
  const clickable = canOpen(cell, canCapture);
  const meta = STATUS_META[cell.status];
  const missing = meta.awaitsCapture;
  const now = cell.date === today;
  const content = meta.recorded ? (
    cell.amount !== null ? (
      formats.formatNumber(cell.amount)
    ) : (
      <span className="chip mute">{cell.reason}</span>
    )
  ) : missing ? (
    now ? (
      <span className="due">Due</span>
    ) : (
      <span className="chip wait">{meta.label}</span>
    )
  ) : (
    <span className="sr-only">{meta.label}</span>
  );
  const edited = cell.editedAfterCapture && (
    <span className="note">Edited</span>
  );
  if (!clickable)
    return (
      <>
        {content}
        {edited}
      </>
    );
  return (
    <button
      type="button"
      data-opens={`${vehicle.id}|${cell.date}`}
      aria-label={`${vehicle.registration}, ${formats.formatWeekdayDate(cell.date)}: ${cellState(formats, cell)}`}
      onClick={(event) => onOpen(vehicle, cell.date, event.currentTarget)}
      className="-mx-1.5 rounded-lg px-1.5 py-0.5 text-right hover:bg-paper-2"
    >
      {content}
      {edited}
    </button>
  );
});
