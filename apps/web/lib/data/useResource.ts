"use client";

import { useCallback, useMemo, useSyncExternalStore } from "react";

import {
  type Loader,
  type Snapshot,
  readSnapshot,
  reloadEntry,
  subscribeEntry,
} from "./cache";
import { apiRequest } from "./request";
import { withRetry } from "./retry";

const idle: Snapshot<never> = {
  value: undefined,
  error: "",
  validating: false,
};

// Cached data shows at once and is revalidated in the background; `loading` is true only while there is no data.
// Components on the same path share one fetch, and it is aborted when the last of them unmounts.
export function useResource<T>(path: string | null) {
  const key = path === null ? null : `r:${path}`;
  const load = useMemo<Loader<T>>(
    () => async (signal) => ({
      value: await withRetry(() => apiRequest<T>(path!, { signal }), signal),
    }),
    [path],
  );
  const subscribe = useCallback(
    (notify: () => void) =>
      key === null ? () => {} : subscribeEntry(key, path!, load, notify),
    [key, path, load],
  );
  const snapshot = useSyncExternalStore(
    subscribe,
    () => readSnapshot<T>(key),
    () => idle as Snapshot<T>,
  );
  const reload = useCallback(() => reloadEntry(key), [key]);
  return {
    data: snapshot.value,
    error: snapshot.error,
    loading: path !== null && snapshot.value === undefined && !snapshot.error,
    isValidating: snapshot.validating,
    reload,
  };
}
