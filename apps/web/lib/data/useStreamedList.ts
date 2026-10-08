"use client";

import { useCallback, useMemo, useSyncExternalStore } from "react";

import type { Page } from "../types";
import {
  type Loader,
  type Snapshot,
  readSnapshot,
  reloadEntry,
  subscribeEntry,
} from "./cache";
import { apiRequest } from "./request";
import { withRetry } from "./retry";

const WORKERS = 3;
const NOT_A_LIST =
  "The server's answer was not the list that was expected. Reload the page and try again.";

type Streamed<T> = {
  items: T[];
  total: number;
  pageSize: number;
  pending: number;
  done: boolean;
  partial: boolean;
};

const idle: Snapshot<never> = {
  value: undefined,
  error: "",
  validating: false,
};
const nothing = <T>(pageSize: number): Streamed<T> => ({
  items: [],
  total: 0,
  pageSize,
  pending: 0,
  done: true,
  partial: false,
});
const settled = <T>(list: Streamed<T>): Streamed<T> =>
  list.done ? list : { ...list, pending: 0, done: true, partial: true };

function streamLoader<T>(path: string, pageSize: number): Loader<Streamed<T>> {
  const separator = path.includes("?") ? "&" : "?";
  return async (signal, publish, previous) => {
    const pool = new AbortController();
    signal.addEventListener("abort", () => pool.abort(), { once: true });
    const fetchPage = async (page: number) => {
      const result = await withRetry(
        () =>
          apiRequest<Page<T>>(
            `${path}${separator}page=${page}&pageSize=${pageSize}`,
            { signal: pool.signal },
          ),
        pool.signal,
      );
      if (!Array.isArray(result?.items)) throw new Error(NOT_A_LIST);
      return result;
    };
    const progressive = previous === undefined || previous.items.length === 0;
    const seen = new Set<unknown>();
    const fresh = (rows: T[]) =>
      rows.filter((row) => {
        const id = (row as { id?: unknown } | null)?.id;
        if (id === undefined) return true;
        if (seen.has(id)) return false;
        seen.add(id);
        return true;
      });

    let first: Page<T>;
    try {
      first = await fetchPage(1);
    } catch (error) {
      if (pool.signal.aborted) throw error;
      return {
        value: previous ? settled(previous) : nothing<T>(pageSize),
        error: (error as Error).message,
      };
    }
    const size = first.pageSize > 0 ? first.pageSize : pageSize;
    const total =
      typeof first.total === "number" ? first.total : first.items.length;
    const pages = Math.max(1, Math.ceil(total / size));
    let items = fresh(first.items);
    let committed = 1;
    const arrived = new Map<number, T[]>();
    const state = (done: boolean, partial = false): Streamed<T> => ({
      items,
      total,
      pageSize: size,
      pending: done ? 0 : Math.min(4, pages - committed),
      done,
      partial,
    });
    if (pages > 1 && progressive) publish(state(false));

    let failure: Error | null = null;
    let next = 2;
    const worker = async () => {
      while (!failure && next <= pages) {
        const page = next++;
        try {
          arrived.set(page, (await fetchPage(page)).items);
        } catch (error) {
          if (!failure && !pool.signal.aborted) {
            failure = error as Error;
            pool.abort();
          }
          return;
        }
        const batch: T[][] = [];
        while (arrived.has(committed + 1)) {
          batch.push(fresh(arrived.get(committed + 1)!));
          arrived.delete(committed + 1);
          committed++;
        }
        if (batch.length === 0) continue;
        items = items.concat(...batch);
        if (progressive && committed < pages) publish(state(false));
      }
    };
    await Promise.all(
      Array.from({ length: Math.min(WORKERS, pages - 1) }, worker),
    );
    if (signal.aborted) throw signal.reason;
    if (failure) {
      const message = (failure as Error).message;
      return progressive
        ? { value: state(true, true), error: message }
        : { value: settled(previous!), error: message };
    }
    return { value: state(true) };
  };
}

// What to tell the person when a list failed: a list that stopped part way also says how much of it is shown.
export function streamError(list: {
  error: string;
  partial: boolean;
  items: unknown[];
  total: number;
}) {
  return list.partial
    ? `${list.error} Showing ${list.items.length} of ${list.total}.`
    : list.error;
}

// Streams any paged API list (path relative to /api): rows appear as each page arrives instead of after the last one.
// Page 1 comes first, then the others through a few workers; only the contiguous prefix is shown, so order holds.
// `pendingRows` is one placeholder per page still to come (at most four), so placeholders shrink as data lands.
// A page that still fails after retries stops the rest: the prefix stays, `error` is set and `partial` is true.
// reload() refetches in the background and swaps the list in once it is complete.
export function useStreamedList<T>(path: string | null, pageSize = 25) {
  const key = path === null ? null : `s:${pageSize}:${path}`;
  const load = useMemo(
    () => (path === null ? null : streamLoader<T>(path, pageSize)),
    [path, pageSize],
  );
  const subscribe = useCallback(
    (notify: () => void) =>
      key === null || path === null || load === null
        ? () => {}
        : subscribeEntry(key, path, load, notify),
    [key, path, load],
  );
  const snapshot = useSyncExternalStore(
    subscribe,
    () => readSnapshot<Streamed<T>>(key),
    () => idle as Snapshot<Streamed<T>>,
  );
  const reload = useCallback(() => reloadEntry(key), [key]);
  const value = snapshot.value;
  return {
    items: value?.items ?? [],
    total: value?.total ?? 0,
    loading: path !== null && value === undefined && !snapshot.error,
    pendingRows: value?.pending ?? 0,
    done: value?.done ?? false,
    partial: value?.partial ?? false,
    error: snapshot.error,
    isValidating: snapshot.validating,
    reload,
  };
}
