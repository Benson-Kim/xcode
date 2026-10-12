import { useMemo, type RefObject } from "react";

import type { RevenueVehicle } from "@xcode/shared/revenue";

import { useRowWindow } from "./useRowWindow";

// Above this many vehicles only the rows near the screen are rendered.
const WINDOW_FROM = 60;
const NO_VEHICLES: RevenueVehicle[] = [];

// The row numbers screen readers hear, and the rows in the window.
export function useGridRows(
  data: { vehicles: RevenueVehicle[] } | undefined,
  body: RefObject<HTMLElement | null>,
) {
  const vehicles = data?.vehicles ?? NO_VEHICLES;
  const windowed = vehicles.length > WINDOW_FROM;
  const items = useMemo(() => vehicles.map((item) => [item.id]), [vehicles]);
  const rowIndex = useMemo(() => {
    const at: number[] = [];
    let next = 2;
    for (const keys of items) {
      at.push(next);
      next += keys.length;
    }
    return at;
  }, [items]);
  // The header, every vehicle's rows, and the totals row last.
  const rowCount = (rowIndex.at(-1) ?? 1) + (items.at(-1)?.length ?? 0);
  const rows = useRowWindow(items, windowed, body);

  return { vehicles, windowed, rowIndex, rowCount, rows };
}
