// @vitest-environment node
import { afterEach, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { POST } from "../app/api/auth/[...path]/route";
vi.mock("next/headers", () => ({ cookies: async () => ({ get: (name: string) => name === "device" ? { value: "browser-device" } : undefined }) }));
afterEach(() => vi.unstubAllGlobals());
const request = (origin = "http://localhost:3000") => new NextRequest("http://localhost:3000/api/auth/sign-in", { method: "POST", headers: { origin, "content-type": "application/json" }, body: JSON.stringify({ email: "person@example.com", pin: "5826", deviceId: "forged" }) });
it("rejects cross-origin cookie-authenticated POSTs", async () => {
  const fetcher = vi.fn(); vi.stubGlobal("fetch", fetcher);
  expect((await POST(request("https://other.example"), { params: Promise.resolve({ path: ["sign-in"] }) })).status).toBe(403);
  expect(fetcher).not.toHaveBeenCalled();
});
it("keeps tokens in HttpOnly cookies and binds requests to the browser device", async () => {
  const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({ status: "authenticated", accessToken: "access-value", refreshToken: "refresh-value" }), { status: 200 }));
  vi.stubGlobal("fetch", fetcher);
  const result = await POST(request(), { params: Promise.resolve({ path: ["sign-in"] }) });
  expect(await result.json()).toEqual({ status: "authenticated" });
  expect(result.cookies.get("access")?.value).toBe("access-value");
  expect(result.headers.get("set-cookie")).toContain("HttpOnly");
  expect(result.headers.get("set-cookie")).toContain("SameSite=strict");
  expect(JSON.parse(fetcher.mock.calls[0][1].body).deviceId).toBe("browser-device");
});
