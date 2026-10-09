import { useCallback, useEffect, useMemo, useState } from "react";

import { earliestNeededDay } from "@xcode/shared/capture";

import { weekHolding } from "../../revenue/dates";
import type { RevenueWeek } from "../../revenue/types";
import {
  cellOf,
  handledBy,
  keyOf,
  targetFor,
  type DayRowData,
  type Waiting,
} from "./model";

// The day on screen, and the earliest day any vehicle is known to still need (offered as a hint to go there).
export function useCaptureDay({
  week,
  waiting,
  canCapture,
  queueLoaded,
  setWeekStart,
}: {
  week: RevenueWeek | undefined;
  waiting: Waiting;
  canCapture: boolean;
  queueLoaded: boolean;
  setWeekStart: (value: string | undefined) => void;
}) {
  const [day, setDay] = useState("");

  // The earliest day any vehicle still needs, worked out once per week and queue rather than on every render.
  const firstNeeded = useMemo(
    () =>
      week && canCapture ? earliestNeededDay(week, handledBy(waiting)) : null,
    [week, waiting, canCapture],
  );

  // Opens on the business date (never the phone's clock). An earlier gap is offered as a hint, not opened for you.
  useEffect(() => {
    if (!week || day || !queueLoaded) return;
    setDay(week.businessDate);
    if (week.businessDate < week.weekStart)
      setWeekStart(weekHolding(week.businessDate, week.currentWeekStart));
  }, [week, day, queueLoaded, setWeekStart]);

  const goToDay = useCallback(
    (next: string) => {
      setDay(next);
      if (week && (next < week.weekStart || next > week.weekThrough)) {
        const holding = weekHolding(next, week.currentWeekStart);
        setWeekStart(holding === week.currentWeekStart ? undefined : holding);
      }
    },
    [week, setWeekStart],
  );

  const inWeek = Boolean(
    week && day >= week.weekStart && day <= week.weekThrough,
  );
  return { day, inWeek, firstNeeded, goToDay };
}

// The day's vehicles with their cell, anything waiting on this phone, and whether a tap opens them.
export function useDayRows({
  week,
  inWeek,
  day,
  waiting,
  canCapture,
}: {
  week: RevenueWeek | undefined;
  inWeek: boolean;
  day: string;
  waiting: Waiting;
  canCapture: boolean;
}) {
  return useMemo<DayRowData[]>(
    () =>
      week && inWeek
        ? week.vehicles.flatMap((vehicle) => {
            const cell = cellOf(vehicle, day);
            if (!cell) return [];
            const queued = waiting.get(keyOf(vehicle.id, day));
            return [
              {
                vehicle,
                cell,
                queued,
                tappable: Boolean(
                  targetFor(vehicle, day, week, waiting, canCapture),
                ),
              },
            ];
          })
        : [],
    [week, inWeek, day, waiting, canCapture],
  );
}
