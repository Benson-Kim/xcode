import { OfflineError, ServerError, apiGet } from "../lib/api";
import { loadCaptureList, saveCaptureList, type StoredCaptureList } from "../lib/storage";
import type { RevenueCell, RevenueWeek } from "./types";

// The weeks loaded while signed in, held in memory only (never written to the phone), so capture carries on
// when the connection drops or the app locks and reopens without internet. They go when the app closes.
const KEEP = 8;
const kept = new Map<string, RevenueWeek>();
let keptFor = "";

export const weekPath = (weekStart?: string, vehicleId?: string) => {
  const query = [weekStart && `weekStart=${encodeURIComponent(weekStart)}`, vehicleId && `vehicleId=${encodeURIComponent(vehicleId)}`].filter(Boolean).join("&");
  return `setup/revenue${query ? `?${query}` : ""}`;
};

// D9: what the phone writes down so capture still works after an offline cold start, when nothing is in
// memory. Only the vehicles and the days open to capture; no amounts, no targets, no totals.
const captureList = (owner: string, week: RevenueWeek): StoredCaptureList => ({
  owner,
  weekStart: week.weekStart,
  weekThrough: week.weekThrough,
  currentWeekStart: week.currentWeekStart,
  businessDate: week.businessDate,
  vehicles: week.vehicles.map((vehicle) => ({
    id: vehicle.id,
    registration: vehicle.registration,
    companyName: vehicle.companyName,
    days: vehicle.days.filter((day) => day.canEdit).map((day) => day.date),
  })),
  savedAt: Date.now(),
});

// A day from the saved list: open to capture, with nothing yet recorded and no target to show.
const minimalCell = (date: string): RevenueCell => ({
  date,
  status: "missing",
  expected: 0,
  amount: null,
  reason: null,
  note: null,
  canEdit: true,
  editedAfterCapture: false,
  version: null,
});

// The saved list read back as a week, so the screens take it the same way they take one from the API.
const fromCaptureList = (list: StoredCaptureList): RevenueWeek => ({
  weekStart: list.weekStart,
  weekThrough: list.weekThrough,
  currentWeekStart: list.currentWeekStart,
  businessDate: list.businessDate,
  companies: [],
  vehicles: list.vehicles.map((vehicle) => ({
    id: vehicle.id,
    companyId: "",
    companyName: vehicle.companyName,
    registration: vehicle.registration,
    joinedOn: list.weekStart,
    leftOn: null,
    earliestMissing: vehicle.days[0] ?? null,
    days: vehicle.days.map(minimalCell),
    totalAmount: 0,
    totalExpected: 0,
    percent: null,
  })),
  totalAmount: 0,
  totalExpected: 0,
  percent: null,
});

// A week from the API, the copy loaded earlier when there is no connection (saved: true), or, when the app
// started offline with nothing in memory, the saved capture list (minimal: true, so the screens know the
// figures are not there to show).
export async function loadWeek(owner: string, weekStart?: string, vehicleId?: string): Promise<{ week: RevenueWeek; saved: boolean; minimal?: boolean }> {
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
    // Only the whole current week is written down: a single vehicle's week, or a week already gone, would
    // make a list that does not match what capture needs next.
    if (!vehicleId && week.weekStart === week.currentWeekStart)
      await saveCaptureList(captureList(owner, week)).catch(() => {});
    return { week, saved: false };
  } catch (error) {
    if (!(error instanceof OfflineError) || error instanceof ServerError) throw error;
    const copy = kept.get(path);
    if (copy) return { week: copy, saved: true };
    // Nothing in memory: the app started without a connection. The saved list covers the current week only,
    // whether that week was asked for by date or by asking for no date at all.
    const list = vehicleId ? null : await loadCaptureList(owner).catch(() => null);
    if (list && (!weekStart || weekStart === list.weekStart))
      return { week: fromCaptureList(list), saved: true, minimal: true };
    throw error;
  }
}
