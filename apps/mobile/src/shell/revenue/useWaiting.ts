import { useCallback, useMemo } from "react";

import type { QueuedCapture } from "../../revenue/types";
import { keyOf, type Waiting } from "./model";

// What waits on this phone, by vehicle and day, and who may replace a saved record with it.
export function useWaiting({
  entries,
  today,
  canCapture,
  canCorrect,
}: {
  entries: readonly QueuedCapture[];
  today: string | undefined;
  canCapture: boolean;
  canCorrect: boolean;
}) {
  const waiting = useMemo<Waiting>(
    () =>
      new Map(
        entries.map((entry) => [keyOf(entry.vehicleId, entry.date), entry]),
      ),
    [entries],
  );
  // Replacing a saved record is changing it: today needs capture or correct, an earlier day needs correct (as the API rules).
  const canReplace = useCallback(
    (entry: QueuedCapture) =>
      canCorrect || (canCapture && entry.date === today),
    [canCorrect, canCapture, today],
  );
  return { waiting, canReplace };
}
