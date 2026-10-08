import { useMemo, useState } from "react";

import { weekDays } from "@xcode/shared/dates";
import type { RevenueWeek } from "@xcode/shared/revenue";

import { revenueWeekPath } from "../../lib/endpoints/revenue";
import { useRevenueWeek } from "./useRevenueWeek";

// The week on screen: which week and company, the data for it, and what the toolbar and primary action derive from it.
export function useWeekGrid(canView: boolean, canCapture: boolean) {
  const [weekStart, setWeekStart] = useState("");
  const [companyId, setCompanyId] = useState("");

  const query = useMemo(
    () => revenueWeekPath({ weekStart, companyId }),
    [companyId, weekStart],
  );
  // One request per week and company for all but the largest fleets; every cell comes from it.
  const week = useRevenueWeek(canView ? query : null, companyId);
  const data = week.data;
  // The toolbar keeps the last week shown while the next one loads, so its controls (and focus) stay in place.
  const [shown, setShown] = useState<RevenueWeek>();
  if (data && data !== shown) setShown(data);
  // A company picked in another week that this week does not list (an archived one, say) would leave an empty grid,
  // and with one company or none no control to leave it: the filter goes once the week has loaded.
  if (
    data &&
    companyId &&
    !data.companies.some((company) => company.id === companyId)
  )
    setCompanyId("");
  // After a save the grid reloads in place. Until the new week arrives its gaps are out of date, so Capture revenue
  // waits for it rather than opening a day that was just saved.
  const [stale, setStale] = useState<RevenueWeek | null>(null);
  if (stale && (data !== stale || week.error)) setStale(null);

  const today = shown?.businessDate ?? "";
  const start = weekStart || shown?.weekStart || "";
  const days = useMemo(() => (data ? weekDays(data.weekStart) : []), [data]);
  // The grid's primary action starts at the earliest missing day, at the first vehicle missing it.
  const gap = data && canCapture ? data.firstGap : null;
  const gapVehicle = gap
    ? data?.vehicles.find((vehicle) => vehicle.id === gap.vehicleId)
    : undefined;
  const first =
    gap && gapVehicle ? { vehicle: gapVehicle, date: gap.date } : null;

  return {
    week,
    data,
    shown,
    stale: Boolean(stale),
    markStale: () => setStale(data ?? null),
    weekStart,
    setWeekStart,
    companyId,
    setCompanyId,
    today,
    start,
    days,
    first,
  };
}
