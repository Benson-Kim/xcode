"use client";

import { useState } from "react";

// The ids ticked in a list. They go as soon as `key` changes, which is whatever decides what the list shows.
export function useSelection(key: string) {
  const [ticked, setTicked] = useState({ key, ids: [] as string[] });
  const ids = ticked.key === key ? ticked.ids : [];
  return {
    ids,
    toggle: (id: string) =>
      setTicked({
        key,
        ids: ids.includes(id) ? ids.filter((one) => one !== id) : [...ids, id],
      }),
    clear: () => setTicked({ key, ids: [] }),
  };
}
