// @vitest-environment node
import { NextRequest } from "next/server";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { GET, POST } from "../app/api/auth/[...path]/route";

// The number-first routes of XCODE Web v2.33 through the auth proxy.
const jar = vi.hoisted(() => new Map<string, string>());
vi.mock("next/headers", () => ({
  cookies: async () => ({
    get: (name: string) =>
      jar.has(name) ? { value: jar.get(name) } : undefined,
  }),
}));
beforeEach(() => {
  jar.clear();
  jar.set("device", "browser-device");
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

const upstream = (body: object, status = 200) =>
  vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status }));

const step = (path: string, body: object) =>
  POST(
    new NextRequest(`http://localhost:3000/api/auth/${path}`, {
      method: "POST",
      headers: {
        origin: "http://localhost:3000",
        "content-type": "application/json",
        "user-agent":
          "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36",
      },
      body: JSON.stringify(body),
    }),
    { params: Promise.resolve({ path: path.split("/") }) },
  );

it("sends the number step with the device id, its name and the trusted-device token, never what the browser sent", async () => {
  jar.set("trust", "kept-token");
  const fetcher = upstream({ status: "pin_required" });
  vi.stubGlobal("fetch", fetcher);
  const result = await step("start", {
    phoneNumber: "0733520614",
    deviceToken: "forged",
    deviceName: "forged",
  });
  expect(await result.json()).toEqual({ status: "pin_required" });
  expect(JSON.parse(fetcher.mock.calls[0][1].body)).toEqual({
    phoneNumber: "0733520614",
    deviceId: "browser-device",
    deviceName: "Chrome on Windows",
    deviceToken: "kept-token",
  });
  expect(fetcher.mock.calls[0][0]).toBe("http://localhost:5000/auth/start");
});

it("passes the step envelope back without any token, and keeps the trusted-device token and the person in HttpOnly cookies", async () => {
  jar.delete("device");
  const fetcher = vi
    .fn()
    .mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          status: "authenticated",
          accessToken: "access-value",
          refreshToken: "refresh-value",
          deviceToken: "trust-value",
          purpose: null,
          triesLeft: null,
          pinProblem: null,
        }),
        { status: 200 },
      ),
    )
    .mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          userId: "u1",
          firstName: "Antony",
          lastName: "Maina",
          role: "Owner",
          permissions: [],
        }),
        { status: 200 },
      ),
    );
  vi.stubGlobal("fetch", fetcher);
  const result = await step("code", {
    phoneNumber: "0733520614",
    purpose: "new_device",
    code: "123456",
    trustDevice: true,
  });
  expect(await result.json()).toEqual({ status: "authenticated" });
  expect(JSON.parse(fetcher.mock.calls[0][1].body)).toMatchObject({
    purpose: "new_device",
    code: "123456",
    trustDevice: true,
  });
  expect(result.cookies.get("trust")?.value).toBe("trust-value");
  expect(result.cookies.get("trust")?.maxAge).toBe(90 * 24 * 3600);
  expect(JSON.parse(result.cookies.get("who")!.value)).toEqual({
    phoneNumber: "0733520614",
    firstName: "Antony",
    lastName: "Maina",
    role: "Owner",
  });
  expect(result.cookies.get("access")?.value).toBe("access-value");
  expect(result.cookies.get("refresh")?.maxAge).toBe(90 * 24 * 3600);
  expect(result.cookies.get("device")?.maxAge).toBe(365 * 24 * 3600);
  expect(result.headers.get("set-cookie")).toContain("HttpOnly");
});

it("passes triesLeft, the purpose and the masked email through, and the PIN problem of a refused new PIN", async () => {
  vi.stubGlobal(
    "fetch",
    upstream({ status: "authentication_failed", triesLeft: 2 }, 401),
  );
  let result = await step("pin", { phoneNumber: "0733520614", pin: "1111" });
  expect(result.status).toBe(401);
  expect(await result.json()).toEqual({
    status: "authentication_failed",
    triesLeft: 2,
  });
  vi.stubGlobal(
    "fetch",
    upstream(
      {
        status: "verification_required",
        purpose: "first_setup",
        maskedEmail: "m•••y@example.com",
      },
      202,
    ),
  );
  result = await step("start", { phoneNumber: "0705337482" });
  expect(await result.json()).toEqual({
    status: "verification_required",
    purpose: "first_setup",
    maskedEmail: "m•••y@example.com",
  });
  vi.stubGlobal(
    "fetch",
    upstream(
      { status: "invalid_pin", pinProblem: "weak", minimumPinLength: 4 },
      400,
    ),
  );
  result = await step("pin/new", {
    phoneNumber: "0705337482",
    purpose: "first_setup",
    code: "123456",
    pin: "1234",
  });
  expect(await result.json()).toEqual({
    status: "invalid_pin",
    pinProblem: "weak",
    minimumPinLength: 4,
  });
});

it("forgets the trusted device when a right PIN is answered with a new-device code", async () => {
  jar.set("trust", "old-token");
  jar.set("who", JSON.stringify({ phoneNumber: "0733520614" }));
  vi.stubGlobal(
    "fetch",
    upstream({ status: "verification_required", purpose: "new_device" }, 202),
  );
  const result = await step("pin", { phoneNumber: "0733520614", pin: "4826" });
  expect(result.cookies.get("trust")?.maxAge).toBe(0);
  expect(result.cookies.get("who")?.maxAge).toBe(0);
});

it("keeps the trusted device on sign out, and forgets it when this device is removed", async () => {
  jar.set("trust", "kept-token");
  jar.set("access", "access-value");
  vi.stubGlobal("fetch", upstream({ status: "signed_out" }));
  let result = await step("sign-out", {});
  expect(result.cookies.get("access")?.maxAge).toBe(0);
  expect(result.cookies.get("trust")).toBeUndefined();
  vi.stubGlobal("fetch", upstream({ status: "device_revoked" }));
  result = await step(
    "trusted-devices/0f3b6a2e-2a0b-4f1e-9d2c-7c1a5b3d9e10/remove",
    { thisDevice: true },
  );
  expect(result.status).toBe(200);
  expect(result.cookies.get("trust")?.maxAge).toBe(0);
  expect(result.cookies.get("who")?.maxAge).toBe(0);
  expect(result.cookies.get("access")?.maxAge).toBe(0);
  vi.stubGlobal("fetch", upstream({ status: "device_revoked" }));
  result = await step(
    "trusted-devices/0f3b6a2e-2a0b-4f1e-9d2c-7c1a5b3d9e10/remove",
    {},
  );
  expect(result.cookies.get("trust")).toBeUndefined();
});

it("tells the sign-in screen what this browser remembers, from its cookies alone", async () => {
  const fetcher = vi.fn();
  vi.stubGlobal("fetch", fetcher);
  const ask = () =>
    GET(new NextRequest("http://localhost:3000/api/auth/device"), {
      params: Promise.resolve({ path: ["device"] }),
    });
  expect(await (await ask()).json()).toEqual({ trusted: false });
  jar.set("trust", "kept-token");
  jar.set(
    "who",
    JSON.stringify({
      phoneNumber: "0733520614",
      firstName: "Antony",
      lastName: "Maina",
      role: "Owner",
    }),
  );
  expect(await (await ask()).json()).toEqual({
    trusted: true,
    phoneNumber: "0733520614",
    firstName: "Antony",
    lastName: "Maina",
    role: "Owner",
  });
  expect(fetcher).not.toHaveBeenCalled();
});

it("lists the trusted devices with the session's token, and refuses an unknown purpose", async () => {
  jar.set("access", "access-value");
  const fetcher = upstream([{ id: "d1", name: "Chrome on Windows" }]);
  vi.stubGlobal("fetch", fetcher);
  const result = await GET(
    new NextRequest("http://localhost:3000/api/auth/trusted-devices"),
    { params: Promise.resolve({ path: ["trusted-devices"] }) },
  );
  expect(await result.json()).toEqual([
    { id: "d1", name: "Chrome on Windows" },
  ]);
  expect(fetcher.mock.calls[0][1].headers.Authorization).toBe(
    "Bearer access-value",
  );
  const refused = await step("code", {
    phoneNumber: "0733520614",
    purpose: "steal",
    code: "123456",
  });
  expect(refused.status).toBe(400);
});
