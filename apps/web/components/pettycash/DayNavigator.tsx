"use client";

import type { PettyCashPeriod } from "@xcode/shared/pettyCash";

import { useFormats } from "../../lib/formats";
import { shiftDate } from "../revenueFormat";
import { ChevronIcon, IconButton, Skeleton } from "../ui";
import { periodStep, type PeriodRange } from "./period";

// Steps a day or a week at a time, always to the first day of the next one, which is never after the business date.
export function DayNavigator({
  date,
  range,
  businessDate,
  period,
  onChange,
}: {
  date: string | null;
  range: PeriodRange | null;
  businessDate: string | null;
  period: PettyCashPeriod;
  onChange: (date: string) => void;
}) {
  const formats = useFormats();
  const unit = period === "week" ? "week" : "day";
  const step = periodStep(period);
  const next = range ? shiftDate(range.from, step) : null;
  return (
    <div className="flex items-center gap-1">
      <IconButton
        aria-label={`Previous ${unit}`}
        disabled={!range}
        onClick={() => range && onChange(shiftDate(range.from, -step))}
      >
        <ChevronIcon size={20} className="rotate-90" />
      </IconButton>
      <strong
        aria-live="polite"
        className="min-w-44 text-center text-[15px] max-[600px]:min-w-0"
      >
        {date && range ? (
          period === "week" ? (
            formats.formatDateRange(range.from, range.to)
          ) : (
            formats.formatWeekdayDate(date)
          )
        ) : (
          <Skeleton className="mx-auto w-36" />
        )}
      </strong>
      <IconButton
        aria-label={`Next ${unit}`}
        disabled={!range || !next || !businessDate || next > businessDate}
        onClick={() => next && onChange(next)}
      >
        <ChevronIcon size={20} className="-rotate-90" />
      </IconButton>
    </div>
  );
}
