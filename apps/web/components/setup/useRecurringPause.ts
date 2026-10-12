import { useState } from "react";

import { recurringApi } from "../../lib/endpoints/recurring";
import { useToast } from "../ui";
import type { RecurringItem } from "./shared";

// Pauses or resumes one item at a time; the page reloads its list and summary when it is done.
export function useRecurringPause(onDone: () => void) {
  const toast = useToast();
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState("");

  async function toggle(item: RecurringItem) {
    if (busyId) return;
    const pausing = !item.pausedFrom;
    setBusyId(item.id);
    setError("");
    try {
      await (pausing
        ? recurringApi.pause(item.id)
        : recurringApi.resume(item.id));
      toast(pausing ? `${item.name} paused` : `${item.name} running`);
      onDone();
    } catch (value) {
      setError((value as Error).message);
    } finally {
      setBusyId(null);
    }
  }

  return { busyId, error, toggle };
}
