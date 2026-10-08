"use client";

import { useEffect, useMemo, useState } from "react";

import {
  loadWholeWeek,
  remainingWeekPages,
  REVENUE_WEEK_PAGE_SIZE,
  type RevenueWeek,
} from "@xcode/shared/revenue";

import { apiRequest, useResource } from "../../lib/data";
import { withRetry } from "../../lib/data/retry";
import { revenueWeekPagePath } from "../../lib/endpoints/revenue";

const WORKERS = 4;

type Rest = { first: RevenueWeek; week?: RevenueWeek; error: string };

async function fetchPages(
  first: RevenueWeek,
  companyId: string,
  signal: AbortSignal,
) {
  const numbers = remainingWeekPages(first);
  const pages: RevenueWeek[] = new Array(numbers.length);
  let next = 0;
  const worker = async () => {
    while (next < numbers.length) {
      const index = next++;
      const path = revenueWeekPagePath({
        weekStart: first.weekStart,
        companyId,
        page: numbers[index],
        pageSize: REVENUE_WEEK_PAGE_SIZE,
      });
      pages[index] = await withRetry(
        () => apiRequest<RevenueWeek>(path, { signal }),
        signal,
      );
    }
  };
  await Promise.all(
    Array.from({ length: Math.min(WORKERS, numbers.length) }, worker),
  );
  return pages;
}

// The whole week grid. The first request lists it up to the API's limit; a larger fleet's other vehicles follow in
// pages, and the grid changes only once they are all in, keeping the last whole week meanwhile. Pages that do not
// add up to one fleet are loaded again from the first answer.
export function useRevenueWeek(path: string | null, companyId: string) {
  const first = useResource<RevenueWeek>(path);
  const data = first.data;
  const [rest, setRest] = useState<Rest>();
  const pending = data ? remainingWeekPages(data).length > 0 : false;

  useEffect(() => {
    if (!data || !pending || !path) return;
    const controller = new AbortController();
    const { signal } = controller;
    loadWholeWeek(
      data,
      (week) => fetchPages(week, companyId, signal),
      () => withRetry(() => apiRequest<RevenueWeek>(path, { signal }), signal),
    ).then(
      (week) => setRest({ first: data, week, error: "" }),
      (error: Error) =>
        !signal.aborted && setRest({ first: data, error: error.message }),
    );
    return () => controller.abort();
  }, [data, pending, companyId, path]);

  const loaded = rest?.first === data ? rest : undefined;
  const whole = useMemo(
    () => data && (!pending ? data : loaded?.week),
    [data, pending, loaded],
  );
  const [kept, setKept] = useState<{
    path: string | null;
    week: RevenueWeek;
  }>();
  if (whole && kept?.week !== whole) setKept({ path, week: whole });
  const waiting = pending && !loaded;

  return {
    data: whole ?? (waiting && kept?.path === path ? kept.week : undefined),
    error: first.error || loaded?.error || "",
    loading: first.loading || (waiting && kept?.path !== path),
    reload: first.reload,
  };
}
