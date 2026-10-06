// @vitest-environment node
import { NextRequest } from "next/server";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { GET, POST } from "../app/api/auth/[...path]/route";
const jar = vi.hoisted(() => new Map<string, string>());
vi.mock("next/headers", () => ({ cookies: async () => ({ get: (name: string) => jar.has(name) ? { value: jar.get(name) } : undefined }) }));
beforeEach(() => { jar.clear(); jar.set("device", "browser-device"); });
afterEach(() => { vi.unstubAllGlobals(); vi.unstubAllEnvs(); });
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
it("passes the development code back to the client outside production", async () => {
  vi.stubGlobal("fetch", upstream({ status: "verification_required", developmentCode: "481516", maskedEmail: "a***@example.com" }, 202));
  const result = await POST(request(), { params: Promise.resolve({ path: ["sign-in"] }) });
  expect(await result.json()).toEqual({ status: "verification_required", developmentCode: "481516", maskedEmail: "a***@example.com" });
});
it("never passes the development code back to the client in production, even when the API sends one", async () => {
  vi.stubEnv("NODE_ENV", "production");
  vi.stubEnv("API_URL", "https://api.example.com");
  vi.stubGlobal("fetch", upstream({ status: "verification_required", developmentCode: "481516", maskedEmail: "a***@example.com" }, 202));
  const result = await POST(request(), { params: Promise.resolve({ path: ["sign-in"] }) });
  expect(result.status).toBe(202);
  const body = await result.json();
  expect(body).not.toHaveProperty("developmentCode");
  expect(body).toEqual({ status: "verification_required", maskedEmail: "a***@example.com" });
});

it("answers 503 with a timeout when the API is down while checking the session", async () => {
  jar.set("access", "access-value");
  const fetcher = vi.fn().mockRejectedValue(new TypeError("fetch failed"));
  vi.stubGlobal("fetch", fetcher);
  const result = await GET(new NextRequest("http://localhost:3000/api/auth/session"), { params: Promise.resolve({ path: ["session"] }) });
  expect(result.status).toBe(503);
  expect(await result.json()).toEqual({ status: "service_unavailable", requestId: expect.any(String) });
  expect(fetcher.mock.calls[0][1].signal).toBeInstanceOf(AbortSignal);
});

it("maps an upstream 5xx on the session check to 503 service_unavailable with a request id", async () => {
  jar.set("access", "access-value");
  const fetcher = upstream({ title: "Internal Server Error", detail: "NullReferenceException in AuthService" }, 500);
  vi.stubGlobal("fetch", fetcher);
  const result = await GET(new NextRequest("http://localhost:3000/api/auth/session"), { params: Promise.resolve({ path: ["session"] }) });
  expect(result.status).toBe(503);
  expect(result.headers.get("Cache-Control")).toBe("no-store");
  const body = await result.json();
  expect(body).toEqual({ status: "service_unavailable", requestId: expect.any(String) });
  expect(fetcher.mock.calls[0][1].headers["X-Request-ID"]).toBe(body.requestId);
});

it("passes an upstream answer below 500 on the session check through unchanged", async () => {
  jar.set("access", "access-value");
  vi.stubGlobal("fetch", upstream({ status: "authentication_failed" }, 401));
  const result = await GET(new NextRequest("http://localhost:3000/api/auth/session"), { params: Promise.resolve({ path: ["session"] }) });
  expect(result.status).toBe(401);
  expect(await result.json()).toEqual({ status: "authentication_failed" });
});

it("refuses a sign-in body over 1 MB without calling the API", async () => {
  const fetcher = vi.fn(); vi.stubGlobal("fetch", fetcher);
  const result = await POST(request(undefined, { email: "x".repeat(1024 * 1024) }), { params: Promise.resolve({ path: ["sign-in"] }) });
  expect(result.status).toBe(413);
  expect(await result.json()).toEqual({ status: "payload_too_large" });
  expect(fetcher).not.toHaveBeenCalled();
});

// The API limits sign-in tries per client. A client-sent X-Forwarded-For survives Next.js, so it is only believed
// through the entries the trusted proxies appended (TRUSTED_PROXY_HOPS, default 0).
async function signInWith(headers: Record<string, string>) {
  const fetcher = upstream({ status: "authentication_failed" }, 401);
  vi.stubGlobal("fetch", fetcher);
  await POST(
    new NextRequest("http://localhost:3000/api/auth/sign-in", { method: "POST", headers: { origin: "http://localhost:3000", "content-type": "application/json", ...headers }, body: "{}" }),
    { params: Promise.resolve({ path: ["sign-in"] }) });
  return fetcher.mock.calls[0][1].headers as Record<string, string>;
}

it("forwards no client address unless proxies are trusted, so a rotated header cannot open new rate-limit partitions", async () => {
  const sent = await signInWith({ "x-forwarded-for": "198.51.100.7", "x-real-ip": "198.51.100.9", forwarded: "for=198.51.100.5" });
  expect(Object.keys(sent).map((k) => k.toLowerCase())).not.toContain("x-forwarded-for");
  expect(Object.keys(sent).map((k) => k.toLowerCase())).not.toContain("x-real-ip");
  expect(Object.keys(sent).map((k) => k.toLowerCase())).not.toContain("forwarded");
});

it("takes the Nth entry from the right of X-Forwarded-For, never what the client put first", async () => {
  vi.stubEnv("TRUSTED_PROXY_HOPS", "1");
  expect((await signInWith({ "x-forwarded-for": "203.0.113.99, 198.51.100.7", "x-real-ip": "198.51.100.9" }))["X-Forwarded-For"]).toBe("198.51.100.7");
  vi.stubEnv("TRUSTED_PROXY_HOPS", "2");
  expect((await signInWith({ "x-forwarded-for": "203.0.113.99, 198.51.100.7, 10.0.0.1" }))["X-Forwarded-For"]).toBe("198.51.100.7");
});

it("forwards nothing when the trusted entry is missing or not an IP, or the setting is invalid", async () => {
  vi.stubEnv("TRUSTED_PROXY_HOPS", "2");
  expect(await signInWith({ "x-forwarded-for": "198.51.100.7" })).not.toHaveProperty("X-Forwarded-For");
  vi.stubEnv("TRUSTED_PROXY_HOPS", "1");
  expect(await signInWith({ "x-forwarded-for": "198.51.100.7, evil\"; drop" })).not.toHaveProperty("X-Forwarded-For");
  expect(await signInWith({})).not.toHaveProperty("X-Forwarded-For");
  vi.stubEnv("TRUSTED_PROXY_HOPS", "-1");
  expect(await signInWith({ "x-forwarded-for": "198.51.100.7" })).not.toHaveProperty("X-Forwarded-For");
  vi.stubEnv("TRUSTED_PROXY_HOPS", "abc");
  expect(await signInWith({ "x-forwarded-for": "198.51.100.7" })).not.toHaveProperty("X-Forwarded-For");
});

it("tells the API which browser a session check comes from", async () => {
  vi.stubEnv("TRUSTED_PROXY_HOPS", "1");
  jar.set("access", "access-value");
  const fetcher = upstream({ userId: "u-1" });
  vi.stubGlobal("fetch", fetcher);
  await GET(new NextRequest("http://localhost:3000/api/auth/session", { headers: { "x-forwarded-for": "203.0.113.99, 198.51.100.7" } }), { params: Promise.resolve({ path: ["session"] }) });
  expect(fetcher.mock.calls[0][1].headers["X-Forwarded-For"]).toBe("198.51.100.7");
});

it("rejects non-string auth fields and does not coerce arrays or objects", async () => {
  const fetcher = vi.fn(); vi.stubGlobal("fetch", fetcher);
  await POST(request(undefined, { phoneNumber: ["injected"], pin: { $gt: "" } } as unknown as object), { params: Promise.resolve({ path: ["sign-in"] }) });
  const sent = fetcher.mock.calls[0]?.[1]?.body ? JSON.parse(fetcher.mock.calls[0][1].body) : null;
  if (sent) {
    expect(sent.phoneNumber).toBe("");
    expect(sent.pin).toBe("");
  }
});

it("rejects an array body", async () => {
  const fetcher = vi.fn(); vi.stubGlobal("fetch", fetcher);
  const result = await POST(
    new NextRequest("http://localhost:3000/api/auth/sign-in", { method: "POST", headers: { origin: "http://localhost:3000", "content-type": "application/json" }, body: JSON.stringify([{ phoneNumber: "0712345678" }]) }),
    { params: Promise.resolve({ path: ["sign-in"] }) },
  );
  expect(result.status).toBe(400);
  expect(fetcher).not.toHaveBeenCalled();
});

it("rejects oversized field values before they reach the API", async () => {
  const fetcher = vi.fn(); vi.stubGlobal("fetch", fetcher);
  const result = await POST(request(undefined, { pin: "1".repeat(9) }), { params: Promise.resolve({ path: ["sign-in"] }) });
  expect(result.status).toBe(400);
  expect(fetcher).not.toHaveBeenCalled();
});

it("maps an upstream 5xx to 503 service_unavailable", async () => {
  vi.stubGlobal("fetch", upstream({ title: "Internal Server Error" }, 500));
  const result = await POST(request(), { params: Promise.resolve({ path: ["sign-in"] }) });
  expect(result.status).toBe(503);
  expect(await result.json()).toEqual({ status: "service_unavailable", requestId: expect.any(String) });
});

it("maps an upstream response with no status field to 503", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("{}", { status: 200 })));
  const result = await POST(request(), { params: Promise.resolve({ path: ["sign-in"] }) });
  expect(result.status).toBe(503);
  expect(await result.json()).toMatchObject({ status: "service_unavailable" });
});

it("maps a network failure on POST to 503 service_unavailable with a request id, and logs it", async () => {
  const log = vi.spyOn(console, "error").mockImplementation(() => undefined);
  const fetcher = vi.fn().mockRejectedValue(new TypeError("fetch failed"));
  vi.stubGlobal("fetch", fetcher);
  const result = await POST(request(), { params: Promise.resolve({ path: ["sign-in"] }) });
  expect(result.status).toBe(503);
  expect(result.headers.get("Cache-Control")).toBe("no-store");
  const body = await result.json();
  expect(body).toEqual({ status: "service_unavailable", requestId: expect.any(String) });
  expect(fetcher.mock.calls[0][1].headers["X-Request-ID"]).toBe(body.requestId);
  expect(JSON.parse(log.mock.calls[0][0] as string)).toMatchObject({ requestId: body.requestId, operation: "sign-in", level: "error", error: "fetch failed" });
});

it("requires API_URL in production", async () => {
  vi.stubEnv("NODE_ENV", "production");
  vi.stubEnv("API_URL", "");
  const { upstreamUrl } = await import("../app/api/body");
  expect(() => upstreamUrl()).toThrow("API_URL is required in production");
});

it("requires HTTPS for API_URL in production unless local", async () => {
  vi.stubEnv("NODE_ENV", "production");
  vi.stubEnv("API_URL", "http://api.example.com");
  const { upstreamUrl } = await import("../app/api/body");
  expect(() => upstreamUrl()).toThrow("HTTPS");
});

it("allows HTTP localhost API_URL in production", async () => {
  vi.stubEnv("NODE_ENV", "production");
  vi.stubEnv("API_URL", "http://localhost:5000");
  const { upstreamUrl } = await import("../app/api/body");
  expect(upstreamUrl()).toBe("http://localhost:5000");
});

it("allows HTTP 127.0.0.1 and any HTTPS API_URL in production", async () => {
  vi.stubEnv("NODE_ENV", "production");
  const { upstreamUrl } = await import("../app/api/body");
  for (const url of ["http://127.0.0.1:5000", "https://api.example.com"]) {
    vi.stubEnv("API_URL", url);
    expect(upstreamUrl(), url).toBe(url);
  }
});

it("refuses HTTP for a host that only looks local in production", async () => {
  vi.stubEnv("NODE_ENV", "production");
  const { upstreamUrl } = await import("../app/api/body");
  for (const url of ["http://localhost.evil.example", "http://127.0.0.1.evil.example", "http://localhost@evil.example", "not a url"]) {
    vi.stubEnv("API_URL", url);
    expect(() => upstreamUrl(), url).toThrow("HTTPS");
  }
});
