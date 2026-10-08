import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { streamError, useStreamedList } from "../lib/data";

type Row = { id: string; label?: string };

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

// A paged list the test can hold back page by page. `echo` is the page size the server answers with.
function serve(options: {
  total: number;
  echo?: number;
  gated?: number[];
  refuse?: number[];
  rows?: (page: number, index: number) => Row;
}) {
  const echo = options.echo ?? 25;
  const pending = new Map<number, () => void>();
  const signals: AbortSignal[] = [];
  const requested: number[] = [];
  const state = { inFlight: 0, peak: 0, gated: new Set(options.gated ?? []) };
  const fetcher = vi.fn(
    (input: string, init: RequestInit) =>
      new Promise<Response>((resolve, reject) => {
        const url = new URL(input, "http://app");
        const page = Number(url.searchParams.get("page"));
        requested.push(page);
        signals.push(init.signal as AbortSignal);
        let open = true;
        const settle = () => {
          if (!open) return false;
          open = false;
          state.inFlight--;
          return true;
        };
        state.inFlight++;
        state.peak = Math.max(state.peak, state.inFlight);
        init.signal?.addEventListener(
          "abort",
          () => settle() && reject(new DOMException("Aborted", "AbortError")),
        );
        const respond = () => {
          if (!settle()) return;
          if (options.refuse?.includes(page))
            return resolve(
              new Response(JSON.stringify({ title: "Refused" }), {
                status: 400,
              }),
            );
          const count = Math.max(
            0,
            Math.min(echo, options.total - (page - 1) * echo),
          );
          const items = Array.from({ length: count }, (_, index) =>
            options.rows
              ? options.rows(page, index)
              : { id: `r-${(page - 1) * echo + index + 1}` },
          );
          resolve(
            new Response(
              JSON.stringify({
                items,
                pageNumber: page,
                pageSize: echo,
                total: options.total,
              }),
              { status: 200 },
            ),
          );
        };
        if (state.gated.has(page)) pending.set(page, respond);
        else respond();
      }),
  );
  vi.stubGlobal("fetch", fetcher);
  return {
    fetcher,
    signals,
    requested,
    state,
    release: (page: number) =>
      act(async () => {
        const respond = pending.get(page);
        pending.delete(page);
        respond?.();
      }),
  };
}

const ids = (items: Row[]) => items.map((item) => item.id);
const range = (from: number, to: number) =>
  Array.from({ length: to - from + 1 }, (_, index) => `r-${from + index}`);

it("asks for no more than three pages at a time", async () => {
  const server = serve({ total: 250, gated: [2, 3, 4, 5, 6, 7, 8, 9, 10] });
  const { result } = renderHook(() => useStreamedList<Row>("setup/people"));

  await waitFor(() => expect(result.current.items).toHaveLength(25));
  await waitFor(() => expect(server.requested).toEqual([1, 2, 3, 4]));
  expect(result.current.pendingRows).toBe(4);

  for (let page = 2; page <= 10; page++) {
    await server.release(page);
    await waitFor(() =>
      expect(server.requested.length).toBeLessThanOrEqual(
        Math.min(10, page + 3),
      ),
    );
  }
  await waitFor(() => expect(result.current.items).toHaveLength(250));
  expect(server.state.peak).toBe(3);
  expect(server.requested.slice().sort((a, b) => a - b)).toEqual([
    1, 2, 3, 4, 5, 6, 7, 8, 9, 10,
  ]);
  expect(result.current.done).toBe(true);
  expect(result.current.partial).toBe(false);
});

it("shows a page that arrived early only once the pages before it are in", async () => {
  const server = serve({ total: 75, gated: [2, 3] });
  const { result } = renderHook(() => useStreamedList<Row>("setup/people"));
  await waitFor(() => expect(server.requested).toEqual([1, 2, 3]));

  await server.release(3);
  expect(ids(result.current.items)).toEqual(range(1, 25));
  expect(result.current.pendingRows).toBe(2);

  await server.release(2);
  await waitFor(() => expect(result.current.items).toHaveLength(75));
  expect(ids(result.current.items)).toEqual(range(1, 75));
  expect(result.current.pendingRows).toBe(0);
  expect(result.current.done).toBe(true);
});

it("takes the page count from the page size the server answered with", async () => {
  const server = serve({ total: 60, echo: 25 });
  const { result } = renderHook(() =>
    useStreamedList<Row>("setup/people", 100),
  );

  await waitFor(() => expect(result.current.items).toHaveLength(60));
  expect(server.requested.slice().sort()).toEqual([1, 2, 3]);
  expect(result.current.done).toBe(true);
});

it("never asks beyond the last page the total allows", async () => {
  const server = serve({ total: 50 });
  const { result } = renderHook(() => useStreamedList<Row>("setup/people"));

  await waitFor(() => expect(result.current.done).toBe(true));
  expect(server.requested.slice().sort()).toEqual([1, 2]);
  expect(result.current.items).toHaveLength(50);
});

it("aborts every page still in flight when the list unmounts", async () => {
  const server = serve({ total: 250, gated: [2, 3, 4, 5, 6, 7, 8, 9, 10] });
  const { result, unmount } = renderHook(() =>
    useStreamedList<Row>("setup/people"),
  );
  await waitFor(() => expect(server.requested).toEqual([1, 2, 3, 4]));
  expect(result.current.items).toHaveLength(25);

  unmount();

  expect(server.signals.every((signal) => signal.aborted)).toBe(true);
  expect(server.state.inFlight).toBe(0);
  expect(server.requested).toEqual([1, 2, 3, 4]);
});

it("keeps the pages before a failing one and says the list is partial", async () => {
  const server = serve({ total: 100, gated: [2, 3, 4], refuse: [3] });
  const { result } = renderHook(() => useStreamedList<Row>("setup/people"));
  await waitFor(() => expect(server.requested).toEqual([1, 2, 3, 4]));

  await server.release(2);
  await server.release(3);

  await waitFor(() => expect(result.current.error).toBe("Refused"));
  expect(ids(result.current.items)).toEqual(range(1, 50));
  expect(result.current.done).toBe(true);
  expect(result.current.partial).toBe(true);
  expect(result.current.pendingRows).toBe(0);
  expect(streamError(result.current)).toBe("Refused Showing 50 of 100.");
  expect(server.signals[3].aborted).toBe(true);
  expect(server.state.inFlight).toBe(0);
});

it("is not partial when the first page fails", async () => {
  serve({ total: 100, refuse: [1] });
  const { result } = renderHook(() => useStreamedList<Row>("setup/people"));

  await waitFor(() => expect(result.current.error).toBe("Refused"));
  expect(result.current.items).toEqual([]);
  expect(result.current.done).toBe(true);
  expect(result.current.partial).toBe(false);
  expect(result.current.loading).toBe(false);
});

it("swaps a reloaded list in only when every page is in", async () => {
  const server = serve({
    total: 75,
    rows: (page, index) => ({
      id: `r-${(page - 1) * 25 + index + 1}`,
      label: "old",
    }),
  });
  const { result } = renderHook(() => useStreamedList<Row>("setup/people"));
  await waitFor(() => expect(result.current.done).toBe(true));
  expect(result.current.items).toHaveLength(75);

  server.state.gated = new Set([2, 3]);
  act(() => result.current.reload());
  await waitFor(() =>
    expect(server.requested.filter((page) => page === 2)).toHaveLength(2),
  );
  expect(result.current.isValidating).toBe(true);
  expect(result.current.items.every((item) => item.label === "old")).toBe(true);

  await server.release(2);
  expect(result.current.items.every((item) => item.label === "old")).toBe(true);
  expect(result.current.pendingRows).toBe(0);
  await server.release(3);
  await waitFor(() => expect(result.current.isValidating).toBe(false));
  expect(result.current.items).toHaveLength(75);
});

it("keeps a row once when rows shift between pages", async () => {
  serve({
    total: 75,
    rows: (page, index) => ({
      id:
        page === 2 && index === 0 ? "r-25" : `r-${(page - 1) * 25 + index + 1}`,
    }),
  });
  const { result } = renderHook(() => useStreamedList<Row>("setup/people"));

  await waitFor(() => expect(result.current.done).toBe(true));
  const found = ids(result.current.items);
  expect(new Set(found).size).toBe(found.length);
  expect(found).toHaveLength(74);
  expect(found.slice(0, 26)).toEqual(range(1, 25).concat("r-27"));
});

it("streams a list once for two components and from the cache afterwards", async () => {
  const server = serve({ total: 75 });
  const first = renderHook(() => useStreamedList<Row>("setup/companies"));
  const second = renderHook(() => useStreamedList<Row>("setup/companies"));
  await waitFor(() => expect(first.result.current.items).toHaveLength(75));
  await waitFor(() => expect(second.result.current.items).toHaveLength(75));
  expect(server.fetcher).toHaveBeenCalledTimes(3);

  first.unmount();
  second.unmount();
  const third = renderHook(() => useStreamedList<Row>("setup/companies"));
  expect(third.result.current.items).toHaveLength(75);
  expect(third.result.current.loading).toBe(false);
  expect(server.fetcher).toHaveBeenCalledTimes(3);
});
