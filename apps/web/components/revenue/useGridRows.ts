import { useCallback, useMemo, useState, type RefObject } from "react";

import type { RevenueVehicle } from "@xcode/shared/revenue";

import { useRowWindow } from "./useRowWindow";

// Above this many vehicles only the rows near the screen are rendered.
const WINDOW_FROM = 60;
const NO_VEHICLES: RevenueVehicle[] = [];

// Which vehicles' week details are open, the row numbers screen readers hear, and the rows in the window.
export function useGridRows(
  data: { vehicles: RevenueVehicle[] } | undefined,
  body: RefObject<HTMLElement | null>,
) {
  const [expanded, setExpanded] = useState<ReadonlySet<string>>(
    () => new Set(),
  );
  const vehicles = data?.vehicles ?? NO_VEHICLES;
  const windowed = vehicles.length > WINDOW_FROM;
  // Each vehicle is its row, and its week detail while open; screen readers count both among the table's rows.
  const items = useMemo(
    () =>
      vehicles.map((item) =>
        expanded.has(item.id) ? [item.id, `${item.id}:detail`] : [item.id],
      ),
    [vehicles, expanded],
  );
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

  const toggle = useCallback((id: string) => {
    setExpanded((current) => {
      const next = new Set(current);
      if (!next.delete(id)) next.add(id);
      return next;
    });
  }, []);

  return { vehicles, expanded, windowed, rowIndex, rowCount, rows, toggle };
}
