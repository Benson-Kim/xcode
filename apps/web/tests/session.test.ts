import { expect, it, vi } from "vitest";

import { fetchWithSession, onSessionExpired } from "../lib/session";

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
