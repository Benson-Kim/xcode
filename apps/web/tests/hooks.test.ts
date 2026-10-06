import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { useResource } from "../lib/data";

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

const ok = (body: object) => new Response(JSON.stringify(body), { status: 200 });
const fail = (status: number) => new Response(JSON.stringify({ title: "Failed" }), { status });

it("passes an AbortSignal to fetch and aborts it on unmount", async () => {
  const fetcher = vi.fn(async () => ok({ a: 1 }));
  vi.stubGlobal("fetch", fetcher);
  const { result, unmount } = renderHook(() => useResource<{ a: number }>("setup/people"));
  await waitFor(() => expect(result.current.data).toEqual({ a: 1 }));
  const signal = (fetcher.mock.calls[0] as unknown as [string, RequestInit])[1].signal as AbortSignal;
  expect(signal).toBeInstanceOf(AbortSignal);
  expect(signal.aborted).toBe(false);
  unmount();
  expect(signal.aborted).toBe(true);
});

it("retries once on a 503 and then succeeds", async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  const fetcher = vi.fn().mockResolvedValueOnce(fail(503)).mockResolvedValueOnce(ok({ a: 2 }));
  vi.stubGlobal("fetch", fetcher);
  const { result } = renderHook(() => useResource<{ a: number }>("setup/people"));
  await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(1));
  await act(async () => {
    await vi.advanceTimersByTimeAsync(1000);
  });
  await waitFor(() => expect(result.current.data).toEqual({ a: 2 }));
  expect(fetcher).toHaveBeenCalledTimes(2);
  expect(result.current.error).toBe("");
});

it("stops after two retries on a persistent network failure", async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  const fetcher = vi.fn().mockRejectedValue(new TypeError("fetch failed"));
  vi.stubGlobal("fetch", fetcher);
  const { result } = renderHook(() => useResource("setup/people"));
  await act(async () => {
    await vi.advanceTimersByTimeAsync(4000);
  });
  await waitFor(() => expect(result.current.error).toBe("Unable to reach the server. Check your connection."));
  expect(fetcher).toHaveBeenCalledTimes(3);
});

it("does not retry a 400", async () => {
  const fetcher = vi.fn(async () => fail(400));
  vi.stubGlobal("fetch", fetcher);
  const { result } = renderHook(() => useResource("setup/people"));
  await waitFor(() => expect(result.current.error).toBe("Failed"));
  expect(fetcher).toHaveBeenCalledTimes(1);
});
