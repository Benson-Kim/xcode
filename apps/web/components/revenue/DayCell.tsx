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
import { PILL, TONE_CLASS } from "./styles";
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
      <span className={PILL}>{cell.reason}</span>
    )
  ) : missing ? (
    clickable ? (
      "Enter"
    ) : (
      meta.label
    )
  ) : (
    <span className="sr-only">{meta.label}</span>
  );
  const edited = cell.editedAfterCapture && (
    <small className="text-[11px] font-normal text-grey">Edited</small>
  );
  const className = cn(
    "inline-flex min-h-9 min-w-17 flex-col items-end justify-center rounded-lg px-2 tabular-nums",
    missing && "items-center text-[13px] font-bold",
    missing && (now ? "text-teal" : TONE_CLASS[meta.tone]),
  );
  if (!clickable)
    return (
      <span className={className}>
        {content}
        {edited}
      </span>
    );
  return (
    <button
      type="button"
      data-opens={`${vehicle.id}|${cell.date}`}
      aria-label={`${vehicle.registration}, ${formats.formatWeekdayDate(cell.date)}: ${cellState(formats, cell)}`}
      onClick={(event) => onOpen(vehicle, cell.date, event.currentTarget)}
      className={cn(
        className,
        "hover:bg-hover",
        missing && "border border-dashed",
        missing && (now ? "border-teal" : "border-clay"),
      )}
    >
      {content}
      {edited}
    </button>
  );
});
