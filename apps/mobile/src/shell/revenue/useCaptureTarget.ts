import { useCallback, useState } from "react";

import { nextToCapture } from "@xcode/shared/capture";
import { isRecorded } from "@xcode/shared/revenue";

import type { NewCapture, RevenueQueue } from "../../revenue/queue";
import type { RevenueVehicle, RevenueWeek } from "../../revenue/types";
import {
  handledBy,
  keyOf,
  targetAt,
  targetFor,
  type Target,
  type Waiting,
} from "./model";

// The day being captured, and what saving it does next.
export function useCaptureTarget({
  week,
  waiting,
  day,
  canCapture,
  add,
}: {
  week: RevenueWeek | undefined;
  waiting: Waiting;
  day: string;
  canCapture: boolean;
  add: RevenueQueue["add"];
}) {
  const [target, setTarget] = useState<Target | null>(null);
  const [fromDay, setFromDay] = useState(true);

  const openDay = useCallback(
    (vehicleId: string) => {
      const vehicle = week?.vehicles.find((item) => item.id === vehicleId);
      if (!week || !vehicle) return;
      setFromDay(true);
      setTarget(targetFor(vehicle, day, week, waiting, canCapture));
    },
    [week, day, waiting, canCapture],
  );

  const openDetailDay = useCallback(
    (vehicle: RevenueVehicle, date: string, detailWeek: RevenueWeek) => {
      setFromDay(false);
      setTarget(targetFor(vehicle, date, detailWeek, waiting, canCapture));
    },
    [waiting, canCapture],
  );

  const save = useCallback(
    async (
      open: Target,
      entry: Pick<NewCapture, "amount" | "reason" | "note">,
    ) => {
      const version = open.waiting
        ? open.waiting.version
        : isRecorded(open.cell)
          ? (open.cell?.version ?? null)
          : null;
      const capture: NewCapture = {
        vehicleId: open.vehicle.id,
        registration: open.vehicle.registration,
        date: open.date,
        ...entry,
        version,
      };
      await add(capture);
      if (!week || !fromDay) return setTarget(null);
      const after = new Map(waiting).set(
        keyOf(capture.vehicleId, capture.date),
        {
          ...capture,
          state: "pending",
          message: "",
          earliestMissing: null,
          current: null,
          queuedAt: 0,
          attempts: 0,
          lastAttemptAt: 0,
        },
      );
      const next = nextToCapture(
        week,
        open.vehicle.id,
        day,
        handledBy(after),
        canCapture,
      );
      setTarget(next ? targetAt(next.vehicle, next.opening) : null);
    },
    [add, waiting, week, fromDay, day, canCapture],
  );

  const close = useCallback(() => setTarget(null), []);
  return { target, openDay, openDetailDay, save, close };
}
