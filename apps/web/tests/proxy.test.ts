// @vitest-environment node
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { GET, POST } from "../app/api/auth/[...path]/route";
const jar = vi.hoisted(() => new Map<string, string>());
vi.mock("next/headers", () => ({ cookies: async () => ({ get: (name: string) => jar.has(name) ? { value: jar.get(name) } : undefined }) }));
beforeEach(() => { jar.clear(); jar.set("device", "browser-device"); });
afterEach(() => vi.unstubAllGlobals());
const request = (origin = "http://localhost:3000", body: object = { email: "person@example.com", pin: "5826", deviceId: "forged" }, path = "sign-in") => new NextRequest(`http://localhost:3000/api/auth/${path}`, { method: "POST", headers: { origin, "content-type": "application/json" }, body: JSON.stringify(body) });
const upstream = (body: object, status = 200) => vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status }));
const jwt = (exp: number) => `header.${Buffer.from(JSON.stringify({ exp })).toString("base64url")}.signature`;
const verify = (rememberDevice: boolean) => POST(request(undefined, { code: "123456", rememberDevice }, "verify-device"), { params: Promise.resolve({ path: ["verify-device"] }) });
it("rejects cross-origin cookie-authenticated POSTs", async () => {
  const fetcher = vi.fn(); vi.stubGlobal("fetch", fetcher);
  expect((await POST(request("https://other.example"), { params: Promise.resolve({ path: ["sign-in"] }) })).status).toBe(403);
  expect(fetcher).not.toHaveBeenCalled();
});
it("keeps tokens in HttpOnly cookies and binds requests to the browser device", async () => {
  const fetcher = upstream({ status: "authenticated", accessToken: "access-value", refreshToken: "refresh-value" });
  vi.stubGlobal("fetch", fetcher);
  const result = await POST(request(), { params: Promise.resolve({ path: ["sign-in"] }) });
  expect(await result.json()).toEqual({ status: "authenticated" });
  expect(result.cookies.get("access")?.value).toBe("access-value");
  expect(result.headers.get("set-cookie")).toContain("HttpOnly");
  expect(result.headers.get("set-cookie")).toContain("SameSite=strict");
  expect(JSON.parse(fetcher.mock.calls[0][1].body).deviceId).toBe("browser-device");
});
it("sets the access cookie to the lifetime of the token inside it", async () => {
  const exp = Math.floor(Date.now() / 1000) + 300;
  vi.stubGlobal("fetch", upstream({ status: "authenticated", accessToken: jwt(exp), refreshToken: "refresh-value" }));
  const result = await POST(request(), { params: Promise.resolve({ path: ["sign-in"] }) });
  expect(result.cookies.get("access")?.maxAge).toBeGreaterThanOrEqual(299);
  expect(result.cookies.get("access")?.maxAge).toBeLessThanOrEqual(300);
});
it("keeps a remembered device and its session after the browser closes", async () => {
  vi.stubGlobal("fetch", upstream({ status: "authenticated", accessToken: "access-value", refreshToken: "refresh-value" }));
  const result = await verify(true);
  expect(result.cookies.get("device")?.maxAge).toBe(365 * 24 * 3600);
  expect(result.cookies.get("remember")?.value).toBe("1");
  expect(result.cookies.get("refresh")?.maxAge).toBe(90 * 24 * 3600);
});
it("trusts a device only for the browser session unless asked to remember it", async () => {
  vi.stubGlobal("fetch", upstream({ status: "authenticated", accessToken: "access-value", refreshToken: "refresh-value" }));
  const result = await verify(false);
  expect(result.cookies.get("device")?.value).toBe("browser-device");
  expect(result.cookies.get("device")?.maxAge).toBeUndefined();
  expect(result.cookies.get("refresh")?.maxAge).toBeUndefined();
  expect(result.cookies.get("remember")?.maxAge).toBe(0);
});
it("keeps the remembered choice on refresh without re-extending the device cookie", async () => {
  jar.set("remember", "1");
  vi.stubGlobal("fetch", upstream({ status: "authenticated", accessToken: "access-value", refreshToken: "rotated" }));
  const result = await POST(request(undefined, {}, "refresh"), { params: Promise.resolve({ path: ["refresh"] }) });
  expect(result.cookies.get("device")).toBeUndefined();
  expect(result.cookies.get("refresh")?.maxAge).toBe(90 * 24 * 3600);
});
it("starts a new browser as a session-only device", async () => {
  jar.clear();
  vi.stubGlobal("fetch", upstream({ status: "verification_required" }, 202));
  const result = await POST(request(), { params: Promise.resolve({ path: ["sign-in"] }) });
  expect(result.cookies.get("device")?.value).toBeTruthy();
  expect(result.cookies.get("device")?.maxAge).toBeUndefined();
});
it("passes the organization's minimum PIN length back to the client", async () => {
  vi.stubGlobal("fetch", upstream({ status: "invalid_pin", minimumPinLength: 6 }, 400));
  const result = await POST(request(undefined, { pin: "6942", code: "123456" }, "pin-reset/complete"), { params: Promise.resolve({ path: ["pin-reset", "complete"] }) });
  expect(result.status).toBe(400);
  expect(await result.json()).toMatchObject({ status: "invalid_pin", minimumPinLength: 6 });
});

it("answers 503 with a timeout when the API is down while checking the session", async () => {
  jar.set("access", "access-value");
  const fetcher = vi.fn().mockRejectedValue(new TypeError("fetch failed"));
  vi.stubGlobal("fetch", fetcher);
  const result = await GET(new NextRequest("http://localhost:3000/api/auth/session"), { params: Promise.resolve({ path: ["session"] }) });
  expect(result.status).toBe(503);
  expect(await result.json()).toEqual({ status: "service_unavailable" });
  expect(fetcher.mock.calls[0][1].signal).toBeInstanceOf(AbortSignal);
});

it("refuses a sign-in body over 1 MB without calling the API", async () => {
  const fetcher = vi.fn(); vi.stubGlobal("fetch", fetcher);
  const result = await POST(request(undefined, { email: "x".repeat(1024 * 1024) }), { params: Promise.resolve({ path: ["sign-in"] }) });
  expect(result.status).toBe(413);
  expect(await result.json()).toEqual({ status: "payload_too_large" });
  expect(fetcher).not.toHaveBeenCalled();
});

// The API limits sign-in tries per client. Every browser reaches it from this proxy, so the proxy names the browser.
it("tells the API which browser a sign-in comes from", async () => {
  const fetcher = upstream({ status: "authentication_failed" }, 401);
  vi.stubGlobal("fetch", fetcher);
  const signIn = (headers: Record<string, string>) => POST(
    new NextRequest("http://localhost:3000/api/auth/sign-in", { method: "POST", headers: { origin: "http://localhost:3000", "content-type": "application/json", ...headers }, body: "{}" }),
    { params: Promise.resolve({ path: ["sign-in"] }) });
  await signIn({ "x-forwarded-for": " 198.51.100.7 , 10.0.0.1", "x-real-ip": "198.51.100.9" });
  await signIn({ "x-real-ip": "198.51.100.8" });
  await signIn({});
  expect(fetcher.mock.calls.map(([, init]) => init.headers["X-Forwarded-For"])).toEqual(["198.51.100.7", "198.51.100.8", undefined]);
  expect(Object.keys(fetcher.mock.calls[2][1].headers)).not.toContain("X-Forwarded-For");
});

it("tells the API which browser a session check comes from", async () => {
  jar.set("access", "access-value");
  const fetcher = upstream({ userId: "u-1" });
  vi.stubGlobal("fetch", fetcher);
  await GET(new NextRequest("http://localhost:3000/api/auth/session", { headers: { "x-forwarded-for": "198.51.100.7" } }), { params: Promise.resolve({ path: ["session"] }) });
  expect(fetcher.mock.calls[0][1].headers["X-Forwarded-For"]).toBe("198.51.100.7");
});
