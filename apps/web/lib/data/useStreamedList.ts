"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import type { Page } from "../types";
import { apiRequest } from "./request";
import { withRetry } from "./retry";

type Loaded<T> = {
  path: string | null;
  items: T[];
  total: number;
  done: boolean;
  error: string;
};

// Streams any paged API list (path relative to /api): rows appear as each page arrives instead of after the last one.
// `pendingRows` is one placeholder per page still to come (at most four), so placeholders shrink as data lands.
// reload() refetches in the background and swaps the list in once it is complete.
export function useStreamedList<T>(path: string | null, pageSize = 25) {
  const [loaded, setLoaded] = useState<Loaded<T>>({
    path: null,
    items: [],
    total: 0,
    done: false,
    error: "",
  });
  const [version, setVersion] = useState(0);
  const shown = useRef<string | null>(null);

  useEffect(() => {
    if (path === null) return;
    let active = true;
    const controller = new AbortController();
    const progressive = shown.current !== path;
    (async () => {
      const items: T[] = [];
      let total = 0;
      try {
        for (let page = 1; ; page++) {
          const separator = path.includes("?") ? "&" : "?";
          const result = await withRetry(
            () =>
              apiRequest<Page<T>>(
                `${path}${separator}page=${page}&pageSize=${pageSize}`,
                { signal: controller.signal },
              ),
            controller.signal,
          );
          if (!active) return;
          if (!Array.isArray(result?.items))
            throw new Error("The server's answer was not the list that was expected. Reload the page and try again.");
          items.push(...result.items);
          total = result.total;
          const done = items.length >= total || result.items.length === 0;
          if (progressive || done) {
            shown.current = path;
            setLoaded({ path, items: [...items], total, done, error: "" });
          }
          if (done) return;
        }
      } catch (error) {
        if (active)
          setLoaded((current) => ({
            ...current,
            path,
            done: true,
            error: (error as Error).message,
          }));
      }
    })();
    return () => {
      active = false;
      controller.abort();
    };
  }, [path, pageSize, version]);

  const reload = useCallback(() => setVersion((current) => current + 1), []);
  const current = loaded.path === path;
  const remaining =
    current && !loaded.done
      ? Math.max(0, loaded.total - loaded.items.length)
      : 0;
  return {
    items: current ? loaded.items : [],
    total: current ? loaded.total : 0,
    loading: path !== null && !current,
    pendingRows: Math.min(4, Math.ceil(remaining / pageSize)),
    error: current ? loaded.error : "",
    reload,
  };
}
