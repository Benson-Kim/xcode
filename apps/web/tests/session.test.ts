import { expect, it, vi } from "vitest";

import {
  fetchWithSession,
  onSessionExpired,
  watchSession,
} from "../lib/session";

const json = (status: number) => new Response("{}", { status });

it("refreshes an expired access token once and retries the request", async () => {
  const fetcher = vi
    .fn()
    .mockResolvedValueOnce(json(401))
    .mockResolvedValueOnce(json(200))
    .mockResolvedValueOnce(json(200));
  vi.stubGlobal("fetch", fetcher);

  const response = await fetchWithSession("/api/setup/companies");

  expect(response.status).toBe(200);
  expect(fetcher.mock.calls.map(([input]) => input)).toEqual([
    "/api/setup/companies",
    "/api/auth/refresh",
    "/api/setup/companies",
  ]);
});

it("shares one refresh between concurrent requests", async () => {
  let refreshed = false;
  const fetcher = vi.fn(async (input: string) => {
    if (input === "/api/auth/refresh") {
      await new Promise((resolve) => setTimeout(resolve, 10));
      refreshed = true;
      return json(200);
    }
    return json(refreshed ? 200 : 401);
  });
  vi.stubGlobal("fetch", fetcher);

  const responses = await Promise.all([
    fetchWithSession("/api/setup/companies"),
    fetchWithSession("/api/setup/vehicles"),
  ]);

  expect(responses.map((response) => response.status)).toEqual([200, 200]);
  expect(
    fetcher.mock.calls.filter(([input]) => input === "/api/auth/refresh"),
  ).toHaveLength(1);
});

it("announces the end of the session when refresh fails", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValueOnce(json(401)).mockResolvedValueOnce(json(401)),
  );
  const expired = vi.fn();
  const stop = onSessionExpired(expired);

  const response = await fetchWithSession("/api/setup/companies");

  stop();
  expect(response.status).toBe(401);
  expect(expired).toHaveBeenCalledOnce();
});

const superseded = () =>
  new Response(JSON.stringify({ status: "refresh_superseded" }), {
    status: 401,
  });

it("asks once more when another tab renewed the session first, and keeps the session", async () => {
  const fetcher = vi
    .fn()
    .mockResolvedValueOnce(json(401))
    .mockResolvedValueOnce(superseded())
    .mockResolvedValueOnce(json(200))
    .mockResolvedValueOnce(json(200));
  vi.stubGlobal("fetch", fetcher);
  const expired = vi.fn();
  const stop = onSessionExpired(expired);

  const response = await fetchWithSession("/api/setup/companies");

  stop();
  expect(response.status).toBe(200);
  expect(fetcher.mock.calls.map(([input]) => input)).toEqual([
    "/api/setup/companies",
    "/api/auth/refresh",
    "/api/auth/refresh",
    "/api/setup/companies",
  ]);
  expect(expired).not.toHaveBeenCalled();
});

it("ends the session after a second superseded refresh instead of asking again", async () => {
  const fetcher = vi
    .fn()
    .mockResolvedValueOnce(json(401))
    .mockResolvedValueOnce(superseded())
    .mockResolvedValueOnce(superseded());
  vi.stubGlobal("fetch", fetcher);
  const expired = vi.fn();
  const stop = onSessionExpired(expired);

  const response = await fetchWithSession("/api/setup/companies");

  stop();
  expect(response.status).toBe(401);
  expect(
    fetcher.mock.calls.filter(([input]) => input === "/api/auth/refresh"),
  ).toHaveLength(2);
  expect(expired).toHaveBeenCalledOnce();
});

it("renews under one lock shared by every tab of the browser", async () => {
  const granted: string[] = [];
  const request = vi.fn(async (name: string, run: () => Promise<unknown>) => {
    granted.push(name);
    return run();
  });
  Object.defineProperty(navigator, "locks", {
    value: { request },
    configurable: true,
  });
  const fetcher = vi
    .fn()
    .mockResolvedValueOnce(json(401))
    .mockImplementationOnce(async () => {
      expect(granted).toEqual(["xcode:refresh"]);
      return json(200);
    })
    .mockResolvedValueOnce(json(200));
  vi.stubGlobal("fetch", fetcher);

  try {
    expect((await fetchWithSession("/api/setup/companies")).status).toBe(200);
  } finally {
    Reflect.deleteProperty(navigator, "locks");
  }
  expect(request).toHaveBeenCalledOnce();
});

it("does not ask again after a plainly refused refresh", async () => {
  const fetcher = vi
    .fn()
    .mockResolvedValueOnce(json(401))
    .mockResolvedValueOnce(json(401));
  vi.stubGlobal("fetch", fetcher);

  await fetchWithSession("/api/setup/companies");

  expect(fetcher).toHaveBeenCalledTimes(2);
});

function comeBack(visibility: "visible" | "hidden" = "visible") {
  Object.defineProperty(document, "visibilityState", {
    value: visibility,
    configurable: true,
  });
  document.dispatchEvent(new Event("visibilitychange"));
}

async function settle() {
  await new Promise((resolve) => setTimeout(resolve, 0));
}

function watched(fetcher: ReturnType<typeof vi.fn>) {
  vi.stubGlobal("fetch", fetcher);
  const expired = vi.fn();
  const stopExpired = onSessionExpired(expired);
  let clock = 1_000_000;
  const stopWatching = watchSession(() => clock);
  return {
    expired,
    advance: (ms: number) => (clock += ms),
    stop: () => {
      stopWatching();
      stopExpired();
    },
  };
}

it("signs out when the tab comes back and the server has ended the session", async () => {
  const fetcher = vi
    .fn()
    .mockResolvedValueOnce(json(401))
    .mockResolvedValueOnce(json(401));
  const watch = watched(fetcher);

  comeBack();
  await settle();

  watch.stop();
  expect(fetcher.mock.calls.map(([input]) => input)).toEqual([
    "/api/auth/session",
    "/api/auth/refresh",
  ]);
  expect(watch.expired).toHaveBeenCalledOnce();
});

it("keeps the session when the check answers 200, also on window focus", async () => {
  const fetcher = vi.fn().mockResolvedValue(json(200));
  const watch = watched(fetcher);

  window.dispatchEvent(new Event("focus"));
  await settle();

  watch.stop();
  expect(fetcher).toHaveBeenCalledOnce();
  expect(watch.expired).not.toHaveBeenCalled();
});

it("does nothing when the check cannot reach the server", async () => {
  const fetcher = vi.fn().mockRejectedValue(new TypeError("offline"));
  const watch = watched(fetcher);

  comeBack();
  await settle();

  watch.stop();
  expect(fetcher).toHaveBeenCalledOnce();
  expect(watch.expired).not.toHaveBeenCalled();
});

it("checks at most once every 30 seconds and not while hidden", async () => {
  const fetcher = vi.fn().mockResolvedValue(json(200));
  const watch = watched(fetcher);

  comeBack("hidden");
  comeBack();
  window.dispatchEvent(new Event("focus"));
  watch.advance(29_000);
  comeBack();
  await settle();
  expect(fetcher).toHaveBeenCalledTimes(1);

  watch.advance(1_000);
  comeBack();
  await settle();

  watch.stop();
  expect(fetcher).toHaveBeenCalledTimes(2);
});
