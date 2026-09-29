import { OfflineError, apiGet } from "../lib/api";
import type { RevenueWeek } from "./types";

// The weeks loaded while signed in, held in memory only (never written to the phone), so capture carries on
// when the connection drops or the app locks and reopens without internet. They go when the app closes.
const KEEP = 8;
const kept = new Map<string, RevenueWeek>();
let keptFor = "";

export const weekPath = (weekStart?: string, vehicleId?: string) => {
  const query = [weekStart && `weekStart=${encodeURIComponent(weekStart)}`, vehicleId && `vehicleId=${encodeURIComponent(vehicleId)}`].filter(Boolean).join("&");
  return `setup/revenue${query ? `?${query}` : ""}`;
};

// A week from the API, or the copy loaded earlier when there is no connection (saved: true).
export async function loadWeek(owner: string, weekStart?: string, vehicleId?: string): Promise<{ week: RevenueWeek; saved: boolean }> {
  if (keptFor !== owner) {
    kept.clear();
    keptFor = owner;
  }
  const path = weekPath(weekStart, vehicleId);
  try {
    const week = await apiGet<RevenueWeek>(path);
    kept.delete(path);
    kept.set(path, week);
    // The current week asked for without a date is also that week asked for by date.
    if (!weekStart) kept.set(weekPath(week.weekStart, vehicleId), week);
    while (kept.size > KEEP) kept.delete(kept.keys().next().value!);
    return { week, saved: false };
  } catch (error) {
    const copy = kept.get(path);
    if (error instanceof OfflineError && copy) return { week: copy, saved: true };
    throw error;
  }
}
