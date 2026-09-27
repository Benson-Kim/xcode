// @vitest-environment node
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { GET } from "../app/api/setup/[...path]/route";
const jar = vi.hoisted(() => new Map<string, string>());
vi.mock("next/headers", () => ({ cookies: async () => ({ get: (name: string) => (jar.has(name) ? { value: jar.get(name) } : undefined) }) }));
beforeEach(() => {
  jar.clear();
  jar.set("access", "access-value");
});
afterEach(() => vi.unstubAllGlobals());
const get = (path: string[]) => GET(new NextRequest("http://localhost:3000/api/setup/people"), { params: Promise.resolve({ path }) });

it("never lets a path segment step outside /setup", async () => {
  const fetcher = vi.fn();
  vi.stubGlobal("fetch", fetcher);
  for (const path of [["people", "..", "..", "auth", "session"], ["people", "../../auth/session"], ["people", ".", "x"], ["people", "a\\..\\b"], ["people", ""]])
    expect((await get(path)).status).toBe(404);
  expect(fetcher).not.toHaveBeenCalled();
});

it("forwards allowed paths with the access token", async () => {
  const fetcher = vi.fn().mockResolvedValue(new Response("{}", { status: 200 }));
  vi.stubGlobal("fetch", fetcher);
  expect((await get(["people", "3f2c", "deactivate"])).status).toBe(200);
  expect(fetcher.mock.calls[0][0]).toMatch(/\/setup\/people\/3f2c\/deactivate$/);
  expect(fetcher.mock.calls[0][1].headers.Authorization).toBe("Bearer access-value");
});
