"use client";

import { useCallback, useEffect, useState } from "react";
import { apiRequest } from "./request";

type Loaded<T> = { path: string | null; data?: T; error: string };

// Loads one API resource (path relative to /api). `loading` stays true until the response for the current path arrives, so screens show placeholders instead of an empty state.
// reload() refreshes in place and keeps showing the previous data meanwhile; a new path shows placeholders again.
// A null path loads nothing (for example, when the person lacks the permission).
export function useResource<T>(path: string | null) {
  const [loaded, setLoaded] = useState<Loaded<T>>({ path: null, error: "" });
  const [version, setVersion] = useState(0);
  useEffect(() => {
    if (path === null) return;
    let active = true;
    apiRequest<T>(path).then(
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
