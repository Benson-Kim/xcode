// @vitest-environment node
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { GET, POST, PUT } from "../app/api/setup/[...path]/route";
const jar = vi.hoisted(() => new Map<string, string>());
vi.mock("next/headers", () => ({ cookies: async () => ({ get: (name: string) => (jar.has(name) ? { value: jar.get(name) } : undefined) }) }));
beforeEach(() => {
  jar.clear();
  jar.set("access", "access-value");
});
afterEach(() => { vi.unstubAllGlobals(); vi.unstubAllEnvs(); });
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

it("forwards revenue, expense catalog and investment paths, and nothing unlisted", async () => {
  const fetcher = vi.fn(async (url: string) => new Response(JSON.stringify({ url }), { status: 200 }));
  vi.stubGlobal("fetch", fetcher);
  const allowed = [
    ["revenue"],
    ["revenue", "dashboard"],
    ["revenue", "v-1", "2026-09-21"],
    ["expense-categories"],
    ["expense-categories", "c-1", "items"],
    ["expense-categories", "c-1", "stop"],
    ["expense-items", "options"],
    ["expense-items", "i-1", "restore"],
    ["investment", "e-1"],
    ["vehicles", "v-1", "investment"],
  ];
  for (const path of allowed) expect((await get(path)).status, path.join("/")).toBe(200);
  expect(fetcher.mock.calls.map(([url]) => String(url).replace(/^.*\/setup\//, ""))).toEqual(allowed.map((path) => path.join("/")));

  fetcher.mockClear();
  for (const path of [["expense"], ["expense-categoriesx"], ["investments"], ["revenues", "x"], ["auth", "session"]])
    expect((await get(path)).status, path.join("/")).toBe(404);
  expect(fetcher).not.toHaveBeenCalled();
});

// The largest legitimate body is a logo upload: a data URL of about 350 KB.
const MB = 1024 * 1024;
const write = (method: "POST" | "PUT", body: string | ReadableStream<Uint8Array>, headers: Record<string, string> = {}) =>
  (method === "POST" ? POST : PUT)(
    // A streamed body needs duplex "half", which the request types do not list yet.
    new NextRequest("http://localhost:3000/api/setup/organization/logo", {
      method,
      body,
      headers: { "content-type": "application/json", ...headers },
      duplex: "half",
    } as ConstructorParameters<typeof NextRequest>[1]),
    { params: Promise.resolve({ path: ["organization", "logo"] }) },
  );

it("refuses a body over 1 MB before forwarding it, by its declared and its actual size", async () => {
  const fetcher = vi.fn(async () => new Response("{}", { status: 200 }));
  vi.stubGlobal("fetch", fetcher);

  const declared = await write("PUT", "{}", { "content-length": String(MB + 1) });
  expect(declared.status).toBe(413);
  expect(await declared.json()).toEqual({ status: "payload_too_large" });

  // No length declared: the body is counted as it is read.
  const chunk = new Uint8Array(256 * 1024).fill(0x61);
  let sent = 0;
  const stream = new ReadableStream<Uint8Array>({
    pull(controller) {
      if (sent++ < 5) controller.enqueue(chunk);
      else controller.close();
    },
  });
  const streamed = await write("POST", stream);
  expect(streamed.status).toBe(413);
  expect(await streamed.json()).toEqual({ status: "payload_too_large" });
  expect(fetcher).not.toHaveBeenCalled();

  const logo = JSON.stringify({ dataUrl: `data:image/png;base64,${"A".repeat(350 * 1024)}` });
  expect((await write("PUT", logo)).status).toBe(200);
  expect(fetcher).toHaveBeenCalledOnce();
  expect((fetcher.mock.calls[0] as unknown as [string, RequestInit])[1].body).toBe(logo);
});

it("tells the API which browser a request comes from, only through trusted proxy hops", async () => {
  const fetcher = vi.fn(async () => new Response("{}", { status: 200 }));
  vi.stubGlobal("fetch", fetcher);
  const call = (headers: Record<string, string>) =>
    GET(new NextRequest("http://localhost:3000/api/setup/people", { headers }), { params: Promise.resolve({ path: ["people"] }) });
  await call({ "x-forwarded-for": "203.0.113.99, 198.51.100.7", "x-real-ip": "198.51.100.8" });
  vi.stubEnv("TRUSTED_PROXY_HOPS", "1");
  await call({ "x-forwarded-for": "203.0.113.99, 198.51.100.7", "x-real-ip": "198.51.100.8" });
  await call({ "x-real-ip": "198.51.100.8" });
  const sent = (fetcher.mock.calls as unknown as [string, RequestInit][]).map(([, init]) => (init.headers as Record<string, string>)["X-Forwarded-For"]);
  expect(sent).toEqual([undefined, "198.51.100.7", undefined]);
});

it("never forwards an empty body, which fetch would send as text/plain and the API would refuse", async () => {
  const fetcher = vi.fn().mockResolvedValue(new Response("{}", { status: 200 }));
  vi.stubGlobal("fetch", fetcher);
  const request = new NextRequest("http://localhost:3000/api/setup/people/3f2c/deactivate", { method: "POST" });
  expect((await POST(request, { params: Promise.resolve({ path: ["people", "3f2c", "deactivate"] }) })).status).toBe(200);
  const init = fetcher.mock.calls[0][1];
  expect(init.body).toBeUndefined();
  expect(init.headers["Content-Type"]).toBeUndefined();
});
