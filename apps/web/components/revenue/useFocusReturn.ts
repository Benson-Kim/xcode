import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type RefObject,
} from "react";

import type { RevenueVehicle } from "@xcode/shared/revenue";

import type { useRowWindow } from "./useRowWindow";

// Focus goes back to the day that opened capture, or to the grid when that day is no longer a button. A day that
// scrolled out of the window meanwhile is brought back first.
export function useFocusReturn(
  dialogOpen: boolean,
  gridRef: RefObject<HTMLElement | null>,
  vehicles: RevenueVehicle[],
  rows: ReturnType<typeof useRowWindow>,
) {
  const opener = useRef<HTMLElement | null>(null);
  const dialogShown = useRef(false);
  const [restore, setRestore] = useState<string | null>(null);
  useEffect(() => {
    dialogShown.current = dialogOpen;
    if (dialogOpen || !opener.current) return;
    const element = opener.current;
    opener.current = null;
    if (element.isConnected) element.focus();
    else if (element.dataset.opens) setRestore(element.dataset.opens);
    else gridRef.current?.focus();
  }, [dialogOpen, gridRef]);
  const { start: shownFrom, end: shownTo, reveal } = rows;
  useEffect(() => {
    if (!restore) return;
    const target = gridRef.current?.querySelector<HTMLElement>(
      `[data-opens="${restore}"]`,
    );
    const index = vehicles.findIndex((item) =>
      restore.startsWith(`${item.id}|`),
    );
    if (!target && index >= 0 && (index < shownFrom || index >= shownTo))
      return reveal(index);
    setRestore(null);
    (target ?? gridRef.current)?.focus();
  }, [restore, vehicles, shownFrom, shownTo, reveal, gridRef]);

  return {
    // Where focus returns to: set when capture opens from a control.
    remember: useCallback((from: HTMLElement) => {
      opener.current = from;
    }, []),
    // A day opened while the dialog is already up keeps the first opener.
    isShown: useCallback(() => dialogShown.current, []),
  };
}
