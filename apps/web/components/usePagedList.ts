"use client";

import { useState } from "react";

import { useResource } from "../lib/data";
import type { Page } from "../lib/types";
import { usePaging } from "./ui";

// One server page of a paged API list (path relative to /api) at a time, with the paging state its Pager needs. Any
// change in filterKey (the filters the path does not carry) or in the page size goes back to page 1, and a page that
// disappears under the person (the last row of it was removed) steps back to the last one that exists.
export function usePagedList<T>(path: string | null, filterKey = "") {
  const paging = usePaging(`${path}|${filterKey}`);
  const separator = path?.includes("?") ? "&" : "?";
  const list = useResource<Page<T>>(
    path === null
      ? null
      : `${path}${separator}page=${paging.page}&pageSize=${paging.pageSize}`,
  );
  if (list.data && typeof list.data.total === "number")
    paging.stepBack(list.data.total);
  // The last count is kept while a page fails to load, so the pager stays to go to another page.
  const [counted, setCounted] = useState(0);
  const total = list.data?.total;
  if (typeof total === "number" && total !== counted) setCounted(total);
  return {
    items: list.data?.items ?? [],
    total: total ?? (list.error ? counted : 0),
    loading: list.loading,
    pendingRows: 0,
    error: list.error,
    isValidating: list.isValidating,
    reload: list.reload,
    paging,
  };
}
