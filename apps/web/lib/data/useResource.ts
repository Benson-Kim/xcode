"use client";

import { useCallback, useEffect, useState } from "react";

import { apiRequest } from "./request";
import { withRetry } from "./retry";

type Loaded<T> = { path: string | null; data?: T; error: string };

export function useResource<T>(path: string | null) {
  const [loaded, setLoaded] = useState<Loaded<T>>({ path: null, error: "" });
  const [version, setVersion] = useState(0);
  useEffect(() => {
    if (path === null) return;
    let active = true;
    const controller = new AbortController();
    withRetry(
      () => apiRequest<T>(path, { signal: controller.signal }),
      controller.signal,
    ).then(
      (data) => active && setLoaded({ path, data, error: "" }),
      (error: Error) =>
        active &&
        setLoaded((current) => ({
          path,
          data: current.path === path ? current.data : undefined,
          error: error.message,
        })),
    );
    return () => {
      active = false;
      controller.abort();
    };
  }, [path, version]);
  const reload = useCallback(() => setVersion((current) => current + 1), []);
  const current = loaded.path === path;
  return {
    data: current ? loaded.data : undefined,
    error: current ? loaded.error : "",
    loading: path !== null && !current,
    reload,
  };
}
