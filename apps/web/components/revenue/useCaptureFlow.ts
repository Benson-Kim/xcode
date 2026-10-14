import { useCallback, useState, type RefObject } from "react";

import { nextToCapture } from "@xcode/shared/capture";
import { shiftDate } from "@xcode/shared/dates";
import type { RevenueVehicle, RevenueWeek } from "@xcode/shared/revenue";

import { useResource } from "../../lib/data";
import { vehicleWeekPath } from "../../lib/endpoints/revenue";
import { captureAt, type Capture } from "./capture";
import { useFocusReturn } from "./useFocusReturn";
import type { useRowWindow } from "./useRowWindow";

export type OpenDay = (
  vehicle: RevenueVehicle,
  date: string,
  from: HTMLElement,
) => void;

type Flow = {
  data: RevenueWeek | undefined;
  canCapture: boolean;
  reload: () => void;
  markStale: () => void;
  gridRef: RefObject<HTMLElement | null>;
  vehicles: RevenueVehicle[];
  rows: ReturnType<typeof useRowWindow>;
};

// The day being captured, where it opens from, and where capture goes after a save.
export function useCaptureFlow({
  data,
  canCapture,
  reload,
  markStale,
  gridRef,
  vehicles,
  rows,
}: Flow) {
  const [capture, setCapture] = useState<Capture | null>(null);

  const gridVehicle = capture
    ? data?.vehicles.find((vehicle) => vehicle.id === capture.vehicleId)
    : undefined;
  const gridCell = capture
    ? gridVehicle?.days.find((day) => day.date === capture.date)
    : undefined;
  const elsewhere = useResource<RevenueWeek>(
    capture && data && !gridCell
      ? vehicleWeekPath(capture.vehicleId, capture.date)
      : null,
  );
  const otherVehicle = elsewhere.data?.vehicles[0];
  const otherCell = capture
    ? otherVehicle?.days.find((day) => day.date === capture.date)
    : undefined;

  const { remember, isShown } = useFocusReturn(
    capture !== null,
    gridRef,
    vehicles,
    rows,
  );

  function open(next: Capture, from: HTMLElement) {
    if (!capture) remember(from);
    setCapture(next);
  }

  // Stable, so a row re-renders only when its own vehicle or state changes.
  const openDay = useCallback<OpenDay>(
    (item, date, from) => {
      if (!isShown()) remember(from);
      setCapture(captureAt(item, date));
    },
    [isShown, remember],
  );

  // After a save: a new capture moves to the next vehicle with no record for that day and closes when none is
  // left; a correction closes. The grid reloads alongside.
  async function advance(saved: Capture, wasNew: boolean) {
    markStale();
    reload();
    const done = [...saved.done, saved.vehicleId];
    const next =
      data && wasNew
        ? nextToCapture(
            data,
            saved.vehicleId,
            saved.date,
            (id, date) => date === saved.date && done.includes(id),
            canCapture,
          )
        : null;
    setCapture(next ? captureAt(next.vehicle, saved.date, done) : null);
  }

  return {
    capture,
    open,
    openDay,
    advance,
    close: () => setCapture(null),
    // The pop up's own date control: the same vehicle, a day earlier or later.
    shiftDay: (days: number) =>
      capture &&
      setCapture({ ...capture, date: shiftDate(capture.date, days), done: [] }),
    title: gridVehicle?.registration ?? otherVehicle?.registration ?? "",
    vehicle: gridCell ? gridVehicle : otherCell ? otherVehicle : undefined,
    cell: gridCell ?? otherCell,
    elsewhere,
  };
}
