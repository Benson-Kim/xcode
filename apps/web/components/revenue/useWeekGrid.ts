import { useMemo, useState } from "react";

import { weekDays } from "@xcode/shared/dates";
import type { RevenueWeek } from "@xcode/shared/revenue";

import { revenueWeekPath } from "../../lib/endpoints/revenue";
import { useDebounced } from "../../lib/useDebounced";
import { useRevenueWeek } from "./useRevenueWeek";

// The week on screen: which week, company and search, the data for it, and what the toolbar derives from it.
export function useWeekGrid(canView: boolean) {
  const [weekStart, setWeekStart] = useState("");
  const [companyId, setCompanyId] = useState("");
  // The search matches the registration or the fleet number, on the server, once typing pauses (v2.29).
  const [search, setSearch] = useState("");
  const q = useDebounced(search.trim());

  const query = useMemo(
    () => revenueWeekPath({ weekStart, companyId, q }),
    [companyId, weekStart, q],
  );
  // One request per week and company for all but the largest fleets; every cell comes from it.
  const week = useRevenueWeek(canView ? query : null, companyId, q);
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
    search,
    setSearch,
    searching: q !== "",
    today,
    start,
    days,
  };
}
