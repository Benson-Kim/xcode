// @vitest-environment node
import { NextRequest } from "next/server";
import { randomBytes } from "node:crypto";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { POST } from "../app/api/auth/[...path]/route";

// Invitation links through the auth proxy: the minted code stays in an HttpOnly cookie that only pin/new reads.
const jar = vi.hoisted(() => new Map<string, string>());
vi.mock("next/headers", () => ({
  cookies: async () => ({
    get: (name: string) =>
      jar.has(name) ? { value: jar.get(name) } : undefined,
  }),
}));
beforeEach(() => {
  jar.clear();
  jar.set("__Host-device", "browser-device");
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

const token = () => randomBytes(32).toString("base64url");
const minted = () => String(100000 + (randomBytes(4).readUInt32BE() % 900000));

const upstream = (body: object, status = 200) =>
  vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status }));

const browser = { origin: "http://localhost:3000" };
const post = (
  path: string,
  body: object,
  headers: Record<string, string> = browser,
) =>
  POST(
    new NextRequest(`http://localhost:3000/api/auth/${path}`, {
      method: "POST",
      headers: {
        ...headers,
        "content-type": "application/json",
        "user-agent":
          "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Version/18.0 Mobile Safari/604.1",
      },
      body: JSON.stringify(body),
    }),
    { params: Promise.resolve({ path: path.split("/") }) },
  );

it("sends redeem the link token, the number and this browser's device, and keeps the minted code from browser JS", async () => {
  jar.delete("__Host-device");
  const link = token();
  const code = minted();
  const fetcher = upstream(
    {
      status: "verification_required",
      purpose: "first_setup",
      code,
      developmentCode: code,
    },
    202,
  );
  vi.stubGlobal("fetch", fetcher);

  const result = await post("invite/redeem", {
    token: link,
    phoneNumber: "0733520614",
    deviceId: "forged",
    deviceName: "forged",
    code: "999999",
  });

  const sent = JSON.parse(fetcher.mock.calls[0][1].body);
  expect(fetcher.mock.calls[0][0]).toBe(
    "http://localhost:5000/auth/invite/redeem",
  );
  expect(sent).toEqual({
    token: link,
    phoneNumber: "0733520614",
    deviceId: result.cookies.get("__Host-device")?.value,
    deviceName: "Safari on iPhone",
  });
  const text = await result.text();
  expect(JSON.parse(text)).toEqual({
    status: "verification_required",
    purpose: "first_setup",
  });
  expect(text).not.toContain(code);
  const cookie = result.cookies.get("__Host-invite");
  expect(cookie?.value).toBe(`0733520614.${code}`);
  expect(cookie?.httpOnly).toBe(true);
  expect(cookie?.sameSite).toBe("strict");
  expect(cookie?.secure).toBe(true);
  expect(cookie?.path).toBe("/");
  expect(cookie?.maxAge).toBe(600);
});

it("refuses a redeem without a well-formed link token before calling the API", async () => {
  const fetcher = vi.fn();
  vi.stubGlobal("fetch", fetcher);
  for (const body of [
    { phoneNumber: "0733520614" },
    { token: "short", phoneNumber: "0733520614" },
    { token: `${token().slice(1)}=`, phoneNumber: "0733520614" },
    { token: 42, phoneNumber: "0733520614" },
  ])
    expect((await post("invite/redeem", body)).status).toBe(400);
  expect(fetcher).not.toHaveBeenCalled();
});

it("passes why a matching link was refused, and nothing it does not know", async () => {
  vi.stubGlobal(
    "fetch",
    upstream(
      { status: "authentication_failed", inviteProblem: "expired" },
      401,
    ),
  );
  const refused = await post("invite/redeem", {
    token: token(),
    phoneNumber: "0733520614",
  });
  expect(refused.status).toBe(401);
  expect(await refused.json()).toEqual({
    status: "authentication_failed",
    inviteProblem: "expired",
  });
  expect(refused.cookies.get("__Host-invite")).toBeUndefined();

  vi.stubGlobal(
    "fetch",
    upstream({ status: "authentication_failed", inviteProblem: "<b>" }, 401),
  );
  expect(
    await (
      await post("invite/redeem", { token: token(), phoneNumber: "0733520614" })
    ).json(),
  ).toEqual({ status: "authentication_failed" });
});

it("spends the minted code on the first PIN and then forgets it", async () => {
  const code = minted();
  jar.set("__Host-invite", `0733520614.${code}`);
  const fetcher = upstream({
    status: "authenticated",
    accessToken: "access-value",
    refreshToken: "refresh-value",
  });
  vi.stubGlobal("fetch", fetcher);

  const result = await post("pin/new", {
    phoneNumber: "0733520614",
    purpose: "first_setup",
    code: "",
    pin: "5826",
    trustDevice: true,
  });

  expect(JSON.parse(fetcher.mock.calls[0][1].body)).toMatchObject({
    purpose: "first_setup",
    code,
    pin: "5826",
  });
  expect(result.cookies.get("__Host-invite")?.maxAge).toBe(0);
  expect(await result.text()).not.toContain(code);
});

it("forgets the minted code when pin/new refuses it, and never sends it for a PIN reset", async () => {
  const code = minted();
  jar.set("__Host-invite", `0733520614.${code}`);
  vi.stubGlobal(
    "fetch",
    upstream({ status: "authentication_failed", triesLeft: null }, 401),
  );
  const refused = await post("pin/new", {
    phoneNumber: "0733520614",
    purpose: "first_setup",
    pin: "5826",
  });
  expect(refused.cookies.get("__Host-invite")?.maxAge).toBe(0);

  const fetcher = upstream({ status: "authenticated" });
  vi.stubGlobal("fetch", fetcher);
  await post("pin/new", {
    phoneNumber: "0733520614",
    purpose: "pin_reset",
    code: "",
    pin: "5826",
  });
  expect(JSON.parse(fetcher.mock.calls[0][1].body).code).toBe("");
});

it("keeps a code minted for another number out of this number's PIN step, and keeps it for that number", async () => {
  jar.set("__Host-invite", `0711000111.${minted()}`);
  const fetcher = upstream({ status: "authentication_failed" }, 401);
  vi.stubGlobal("fetch", fetcher);

  const result = await post("pin/new", {
    phoneNumber: "0733520614",
    purpose: "first_setup",
    pin: "5826",
  });

  expect(JSON.parse(fetcher.mock.calls[0][1].body).code).toBe("");
  expect(result.cookies.get("__Host-invite")).toBeUndefined();
});

it("passes on that the first-setup code is in the invitation email", async () => {
  vi.stubGlobal(
    "fetch",
    upstream(
      {
        status: "verification_required",
        purpose: "first_setup",
        maskedEmail: "a***@example.com",
        invitation: true,
      },
      202,
    ),
  );
  const result = await post("start", { phoneNumber: "0733520614" });
  expect(await result.json()).toMatchObject({ invitation: true });
});

it("refuses a POST from another site, or with no Origin unless the browser says it is same-origin", async () => {
  const fetcher = upstream({ status: "pin_required" });
  vi.stubGlobal("fetch", fetcher);
  const body = { token: token(), phoneNumber: "0733520614" };
  expect(
    (await post("invite/redeem", body, { origin: "https://other.example" }))
      .status,
  ).toBe(403);
  expect((await post("invite/redeem", body, {})).status).toBe(403);
  expect(
    (await post("invite/redeem", body, { "sec-fetch-site": "cross-site" }))
      .status,
  ).toBe(403);
  expect((await post("start", { phoneNumber: "0733520614" }, {})).status).toBe(
    403,
  );
  expect(fetcher).not.toHaveBeenCalled();

  expect(
    (
      await post(
        "start",
        { phoneNumber: "0733520614" },
        { "sec-fetch-site": "same-origin" },
      )
    ).status,
  ).toBe(200);
});
