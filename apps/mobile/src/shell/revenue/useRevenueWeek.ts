import { useCallback, useEffect, useState } from "react";

import { OfflineError, ServerError, SessionEndedError } from "../../lib/api";
import { useOnline } from "../../lib/network";
import { useLatest } from "../../lib/useLatest";
import type { RevenueQueue } from "../../revenue/queue";
import type { RevenueWeek } from "../../revenue/types";
import { loadWeek } from "../../revenue/week";
import { OFFLINE_EMPTY } from "./model";

// The week on screen: loaded again when a round of sending settles, when Try again is pressed and when the connection returns.
export function useRevenueWeek({
  canView,
  owner,
  queue,
  onSessionEnded,
}: {
  canView: boolean;
  owner: string;
  queue: Pick<RevenueQueue, "syncing" | "revision">;
  onSessionEnded: () => void;
}) {
  // undefined: the current week, which the API works out from the organization's business date.
  const [weekStart, setWeekStart] = useState<string | undefined>();
  const [data, setData] = useState<{
    week: RevenueWeek;
    saved: boolean;
  } | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  // Bumped by Try again after a failed load.
  const [attempt, setAttempt] = useState(0);
  // Reloads once a round of sending settles, not on every answer in it.
  const [shown, setShown] = useState(queue.revision);
  useEffect(() => {
    if (!queue.syncing && queue.revision !== shown) setShown(queue.revision);
  }, [queue.syncing, queue.revision, shown]);

  const endedRef = useLatest(onSessionEnded);
  useEffect(() => {
    if (!canView) return;
    let active = true;
    setLoading(true);
    loadWeek(owner, weekStart).then(
      (result) => {
        if (!active) return;
        setData(result);
        setError("");
        setLoading(false);
      },
      (reason: Error) => {
        if (!active) return;
        setLoading(false);
        if (reason instanceof SessionEndedError) return endedRef.current();
        setError(
          reason instanceof OfflineError && !(reason instanceof ServerError)
            ? OFFLINE_EMPTY
            : reason.message,
        );
      },
    );
    return () => {
      active = false;
    };
  }, [canView, owner, weekStart, shown, attempt, endedRef]);

  // When the connection comes back, a week that could not load, or that shows an earlier copy, loads again.
  // Only the connection coming back retries; a failure while online waits for Try again.
  const online = useOnline();
  const retry = useCallback(() => setAttempt((value) => value + 1), []);
  const staleRef = useLatest(Boolean(error || data?.saved));
  useEffect(() => {
    if (online && staleRef.current) retry();
  }, [online, retry, staleRef]);

  return {
    week: data?.week,
    saved: Boolean(data?.saved),
    loading,
    error,
    weekStart,
    setWeekStart,
    retry,
    shown,
  };
}
