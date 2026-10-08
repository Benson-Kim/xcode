import { randomUUID } from "expo-crypto";
import { useCallback, useEffect, useRef, useState } from "react";

import {
  pettyCashEntriesPath,
  type PettyCashEntry,
  type PettyCashEntryPage,
  type PettyCashEntryQuery,
} from "@xcode/shared/pettyCash";

import {
  apiGet,
  apiSendResult,
  OfflineError,
  ServerError,
  SessionEndedError,
} from "../lib/api";

// A client-made id for a create, so a retried save is answered with the entry it already made.
export const newEntryId = () => randomUUID();

export type Outcome<T> =
  | { ok: true; data: T }
  | { ok: false; status: number; message: string; reload: boolean };

type Problem = { detail?: string; title?: string };

// The API's detail says what to fix. 409 and 404 mean the phone's copy is out of date, so the caller reloads.
export async function send<T>(
  method: "POST" | "PUT",
  path: string,
  body: unknown,
): Promise<Outcome<T>> {
  try {
    const { status, body: reply } = await apiSendResult<T & Problem>(
      method,
      `setup/pettycash/${path}`,
      body,
    );
    if (status >= 200 && status < 300) return { ok: true, data: reply };
    const detail = reply.detail || reply.title;
    if (status >= 500)
      return {
        ok: false,
        status,
        message: new ServerError().message,
        reload: false,
      };
    if (status === 403)
      return {
        ok: false,
        status,
        message: detail || "You do not have permission to do this.",
        reload: false,
      };
    if (status === 409 || status === 404)
      return {
        ok: false,
        status,
        message:
          detail ||
          (status === 409
            ? "This entry was changed by someone else."
            : "This entry no longer exists."),
        reload: true,
      };
    return {
      ok: false,
      status,
      message: detail || "The request could not be completed.",
      reload: false,
    };
  } catch (error) {
    if (error instanceof SessionEndedError) throw error;
    return {
      ok: false,
      status: 0,
      message:
        error instanceof OfflineError
          ? "No internet connection. Nothing was saved."
          : "The request could not be completed.",
      reload: false,
    };
  }
}

type Loaded<T> = { key: string; data: T | null; error: string };

// Loads one path. A new path or stamp loads again; an answer to an earlier one is dropped.
export function useLoaded<T>(
  path: string | null,
  stamp: number,
  onSessionEnded: () => void,
) {
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<Loaded<T>>({
    key: "",
    data: null,
    error: "",
  });
  const loadKey = path === null ? "" : `${stamp}|${attempt}|${path}`;
  useEffect(() => {
    if (path === null) return;
    let active = true;
    apiGet<T>(path).then(
      (data) => active && setState({ key: loadKey, data, error: "" }),
      (reason: Error) => {
        if (!active) return;
        if (reason instanceof SessionEndedError) return onSessionEnded();
        setState({ key: loadKey, data: null, error: reason.message });
      },
    );
    return () => {
      active = false;
    };
  }, [path, loadKey, onSessionEnded]);
  const settled = state.key === loadKey && loadKey !== "";
  return {
    data: settled ? state.data : null,
    error: settled ? state.error : "",
    loading: path !== null && !settled,
    retry: useCallback(() => setAttempt((value) => value + 1), []),
  };
}

type Pages = {
  key: string;
  items: PettyCashEntry[];
  total: number;
  page: number;
  error: string;
  more: boolean;
};

const NO_PAGES: Pages = {
  key: "",
  items: [],
  total: 0,
  page: 0,
  error: "",
  more: false,
};

// Entries for a query, a page at a time. A new query or stamp starts again from page one. The query object
// must be stable between renders (memoized or a constant).
export function usePagedEntries(
  query: PettyCashEntryQuery | null,
  stamp: number,
  onSessionEnded: () => void,
) {
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<Pages>(NO_PAGES);
  const loadKey =
    query === null ? "" : `${stamp}|${attempt}|${pettyCashEntriesPath(query)}`;
  const latest = useRef("");
  const fetchPage = useCallback(
    (page: number, base: Pages, forKey: string) => {
      if (query === null) return;
      apiGet<PettyCashEntryPage>(
        pettyCashEntriesPath({ ...query, ...(page > 1 ? { page } : {}) }),
      ).then(
        (result) => {
          if (latest.current !== forKey) return;
          const seen = new Set(base.items.map((item) => item.id));
          setState({
            key: forKey,
            items: [
              ...base.items,
              ...result.items.filter((item) => !seen.has(item.id)),
            ],
            total: result.total,
            page,
            error: "",
            more: false,
          });
        },
        (reason: Error) => {
          if (latest.current !== forKey) return;
          if (reason instanceof SessionEndedError) return onSessionEnded();
          setState({
            ...base,
            key: forKey,
            error: reason.message,
            more: false,
          });
        },
      );
    },
    [query, onSessionEnded],
  );
  useEffect(() => {
    latest.current = loadKey;
    if (loadKey) fetchPage(1, { ...NO_PAGES, key: loadKey }, loadKey);
  }, [loadKey, fetchPage]);
  const settled = state.key === loadKey && loadKey !== "";
  return {
    items: settled ? state.items : NO_PAGES.items,
    total: settled ? state.total : 0,
    error: settled ? state.error : "",
    loading: query !== null && !settled,
    hasMore: settled && state.items.length < state.total,
    loadingMore: settled && state.more,
    loadMore: () => {
      if (!settled) return;
      setState({ ...state, more: true });
      fetchPage(state.page + 1, state, loadKey);
    },
    retry: useCallback(() => setAttempt((value) => value + 1), []),
  };
}
