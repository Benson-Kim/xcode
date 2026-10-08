import { act, renderHook, waitFor } from "@testing-library/react";
import { StrictMode, type ReactNode } from "react";
import { afterEach, expect, it, vi } from "vitest";

import { authApi } from "../lib/api";
import { apiRequest, useResource } from "../lib/data";

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

type Doc = { v: number };

const json = (body: object, status = 200) =>
  new Response(JSON.stringify(body), { status });

// Answers GETs with a counter that goes up on every call, so each answer says which fetch produced it.
function serve(options: { hold?: boolean } = {}) {
  let count = 0;
  const held: (() => void)[] = [];
  const signals: AbortSignal[] = [];
  const fetcher = vi.fn(async (input: string, init?: RequestInit) => {
    if (init?.method && init.method !== "GET") return json({ ok: true });
    signals.push(init?.signal as AbortSignal);
    const v = ++count;
    if (options.hold) await new Promise<void>((resolve) => held.push(resolve));
    return json({ v });
  });
  vi.stubGlobal("fetch", fetcher);
  return {
    fetcher,
    signals,
    gets: () =>
      fetcher.mock.calls.filter(
        ([, init]) => !init?.method || init.method === "GET",
      ).length,
    releaseAll: () =>
      act(async () => held.splice(0).forEach((release) => release())),
  };
}

const usePeople = () => useResource<Doc>("setup/people");

it("makes one fetch for two components on the same path", async () => {
  const server = serve();
  const first = renderHook(usePeople);
  const second = renderHook(usePeople);

  await waitFor(() => expect(first.result.current.data).toEqual({ v: 1 }));
  await waitFor(() => expect(second.result.current.data).toEqual({ v: 1 }));
  expect(server.gets()).toBe(1);
});

it("aborts the shared fetch only when the last component leaves", async () => {
  const server = serve({ hold: true });
  const first = renderHook(usePeople);
  const second = renderHook(usePeople);
  await waitFor(() => expect(server.gets()).toBe(1));

  first.unmount();
  expect(server.signals[0].aborted).toBe(false);
  second.unmount();
  expect(server.signals[0].aborted).toBe(true);
});

it("shows cached data at once and swaps in the fresh answer", async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  const server = serve();
  const first = renderHook(usePeople);
  await waitFor(() => expect(first.result.current.data).toEqual({ v: 1 }));
  first.unmount();
  await act(async () => {
    await vi.advanceTimersByTimeAsync(5000);
  });

  const second = renderHook(usePeople);
  expect(second.result.current.data).toEqual({ v: 1 });
  expect(second.result.current.loading).toBe(false);
  expect(second.result.current.isValidating).toBe(true);
  await waitFor(() => expect(second.result.current.data).toEqual({ v: 2 }));
  expect(second.result.current.isValidating).toBe(false);
  expect(server.gets()).toBe(2);
});

it("does not ask again for an answer that has just arrived", async () => {
  const server = serve();
  const first = renderHook(usePeople);
  await waitFor(() => expect(first.result.current.data).toEqual({ v: 1 }));
  first.unmount();

  const second = renderHook(usePeople);
  expect(second.result.current.data).toEqual({ v: 1 });
  expect(second.result.current.isValidating).toBe(false);
  expect(server.gets()).toBe(1);
});

it("reload asks the server again", async () => {
  const server = serve();
  const { result } = renderHook(usePeople);
  await waitFor(() => expect(result.current.data).toEqual({ v: 1 }));

  act(() => result.current.reload());

  await waitFor(() => expect(result.current.data).toEqual({ v: 2 }));
  expect(server.gets()).toBe(2);
});

it("does not keep a failure", async () => {
  const fetcher = vi
    .fn()
    .mockResolvedValueOnce(json({ title: "Failed" }, 400))
    .mockResolvedValue(json({ v: 2 }));
  vi.stubGlobal("fetch", fetcher);
  const first = renderHook(usePeople);
  await waitFor(() => expect(first.result.current.error).toBe("Failed"));
  expect(first.result.current.loading).toBe(false);
  first.unmount();

  const second = renderHook(usePeople);
  expect(second.result.current.error).toBe("");
  expect(second.result.current.loading).toBe(true);
  await waitFor(() => expect(second.result.current.data).toEqual({ v: 2 }));
  expect(fetcher).toHaveBeenCalledTimes(2);
});

it("drops what is cached under setup/ after a change succeeds", async () => {
  const server = serve();
  const first = renderHook(usePeople);
  await waitFor(() => expect(first.result.current.data).toEqual({ v: 1 }));
  first.unmount();

  await apiRequest("setup/people/1", { method: "PUT", body: "{}" });

  const second = renderHook(usePeople);
  expect(second.result.current.data).toBeUndefined();
  expect(second.result.current.loading).toBe(true);
  await waitFor(() => expect(second.result.current.data).toEqual({ v: 2 }));
  expect(server.gets()).toBe(2);
});

it("leaves the cache alone when a change is refused or is only a read", async () => {
  const fetcher = vi.fn(async (input: string, init?: RequestInit) =>
    init?.method === "PUT" ? json({ title: "No" }, 409) : json({ v: 1 }),
  );
  vi.stubGlobal("fetch", fetcher);
  const first = renderHook(usePeople);
  await waitFor(() => expect(first.result.current.data).toEqual({ v: 1 }));
  first.unmount();

  await expect(
    apiRequest("setup/people/1", { method: "PUT", body: "{}" }),
  ).rejects.toThrow("No");
  await apiRequest("setup/vehicles");

  const second = renderHook(usePeople);
  expect(second.result.current.data).toEqual({ v: 1 });
  expect(fetcher).toHaveBeenCalledTimes(3);
});

it("refetches what is on screen when a change lands while its fetch is still under way", async () => {
  const server = serve({ hold: true });
  const { result } = renderHook(usePeople);
  await waitFor(() => expect(server.gets()).toBe(1));

  await apiRequest("setup/people/1", { method: "PUT", body: "{}" });
  await waitFor(() => expect(server.gets()).toBe(2));
  expect(server.signals[0].aborted).toBe(true);
  act(() => result.current.reload());
  expect(server.gets()).toBe(2);

  await server.releaseAll();
  await waitFor(() => expect(result.current.data).toEqual({ v: 2 }));
});

it("forgets everything when a sign-in call finishes", async () => {
  const fetcher = vi.fn(async (input: string) =>
    input.startsWith("/api/auth/")
      ? json({ status: "signed_out" })
      : json({ v: fetcher.mock.calls.length }),
  );
  vi.stubGlobal("fetch", fetcher);
  const first = renderHook(usePeople);
  await waitFor(() => expect(first.result.current.data).toEqual({ v: 1 }));
  first.unmount();

  await authApi("sign-out", {
    phoneNumber: "",
    pin: "",
    code: "",
    rememberDevice: false,
  });

  const second = renderHook(usePeople);
  expect(second.result.current.data).toBeUndefined();
  await waitFor(() => expect(second.result.current.data).toEqual({ v: 3 }));
});

it("forgets everything when the session ends", async () => {
  const fetcher = vi.fn(async (input: string) =>
    input === "/api/setup/vehicles"
      ? json({}, 401)
      : input === "/api/auth/refresh"
        ? json({}, 401)
        : json({ v: 1 }),
  );
  vi.stubGlobal("fetch", fetcher);
  const first = renderHook(usePeople);
  await waitFor(() => expect(first.result.current.data).toEqual({ v: 1 }));
  first.unmount();

  await expect(apiRequest("setup/vehicles")).rejects.toThrow();

  const second = renderHook(usePeople);
  expect(second.result.current.data).toBeUndefined();
  await waitFor(() => expect(second.result.current.data).toEqual({ v: 1 }));
});

it("makes one live fetch under StrictMode's double effect", async () => {
  const server = serve();
  const wrapper = ({ children }: { children: ReactNode }) => (
    <StrictMode>{children}</StrictMode>
  );
  const { result } = renderHook(usePeople, { wrapper });

  await waitFor(() => expect(result.current.data).toEqual({ v: 1 }));
  expect(result.current.error).toBe("");
  expect(result.current.loading).toBe(false);
  expect(result.current.isValidating).toBe(false);
  expect(server.gets()).toBe(1);
  expect(server.signals[0].aborted).toBe(false);
});
