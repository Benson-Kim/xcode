import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";

import type {
  AuthRequest,
  AuthResponse,
  CodePurpose,
} from "@xcode/shared/auth";

import {
  deviceNameFrom,
  forwardedFor,
  logProxyError,
  readLimitedBody,
  requestId,
  sameOrigin,
  upstreamUrl,
} from "../../body";

// The released sign-in routes (XCODE Mobile v2.11 still uses them) and the number-first routes of XCODE Web v2.33.
const allowed = new Set([
  "sign-in",
  "verify-device",
  "setup-pin/request",
  "setup-pin/verify",
  "setup-pin/complete",
  "pin-reset/request",
  "pin-reset/verify",
  "pin-reset/complete",
  "refresh",
  "sign-out",
  "devices/current/revoke",
  "start",
  "pin",
  "code",
  "code/resend",
  "pin/forgot",
  "pin/new",
  "pin/change",
]);

const DEVICE_REMOVE = /^trusted-devices\/([0-9a-f-]{36})\/remove$/;
const PURPOSES: readonly string[] = ["first_setup", "new_device", "pin_reset"];

const cookieOptions = {
  httpOnly: true,
  secure: process.env.NODE_ENV === "production",
  sameSite: "strict" as const,
  path: "/",
};

// Calls that mark this browser as a trusted device when they succeed (the released routes).
const trustingOperations = new Set([
  "verify-device",
  "setup-pin/complete",
  "pin-reset/complete",
]);
const rememberedSeconds = 365 * 24 * 3600;
// The longest refresh lifetime a security policy allows; the API enforces the organization's real one.
const refreshCookieSeconds = 90 * 24 * 3600;
// A trusted device's token expires on the server after 90 days unused; the cookie lives as long.
const trustCookieSeconds = 90 * 24 * 3600;

// Who a trusted device remembers, so the sign-in screen can start at the PIN with their name.
type Remembered = {
  phoneNumber: string;
  firstName: string;
  lastName: string;
  role: string;
};

function remembered(jar: {
  get: (name: string) => { value: string } | undefined;
}) {
  try {
    const raw = jar.get("who")?.value;
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<Remembered>;
    if (typeof parsed.phoneNumber !== "string") return null;
    return {
      phoneNumber: parsed.phoneNumber,
      firstName: typeof parsed.firstName === "string" ? parsed.firstName : "",
      lastName: typeof parsed.lastName === "string" ? parsed.lastName : "",
      role: typeof parsed.role === "string" ? parsed.role : "",
    };
  } catch {
    return null;
  }
}

function serviceUnavailable(id: string) {
  return NextResponse.json(
    { status: "service_unavailable", requestId: id },
    { status: 503, headers: { "Cache-Control": "no-store" } },
  );
}

function invalid(status: number, body = "invalid_request") {
  return NextResponse.json({ status: body }, { status });
}

async function passThrough(
  path: string,
  id: string,
  request: NextRequest,
  access: string,
) {
  const response = await fetch(`${upstreamUrl()}/auth/${path}`, {
    headers: {
      Authorization: `Bearer ${access}`,
      "X-Request-ID": id,
      ...forwardedFor(request),
    },
    cache: "no-store",
    signal: AbortSignal.timeout(15_000),
  });
  if (response.status >= 500) return serviceUnavailable(id);
  return new NextResponse(await response.text(), {
    status: response.status,
    headers: {
      "Content-Type": "application/json",
      "Cache-Control": "no-store",
    },
  });
}

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
) {
  const id = requestId();
  const origin = request.headers.get("origin");
  const expectedOrigin = request.nextUrl.origin;
  if (
    origin &&
    !sameOrigin(origin, request.headers.get("host"), expectedOrigin)
  )
    return invalid(403);

  const { path } = await context.params;
  const operation = path.join("/");
  const jar = await cookies();
  // What this browser remembers: a trusted device starts at the PIN with the person's name (nothing upstream).
  if (operation === "device") {
    const who = jar.get("trust")?.value ? remembered(jar) : null;
    return NextResponse.json(
      who ? { trusted: true, ...who } : { trusted: false },
      { headers: { "Cache-Control": "no-store" } },
    );
  }
  if (operation !== "session" && operation !== "trusted-devices")
    return invalid(404);

  const access = jar.get("access")?.value;
  if (!access) return invalid(401, "authentication_failed");
  try {
    return await passThrough(operation, id, request, access);
  } catch (error) {
    logProxyError(id, operation, error);
    return serviceUnavailable(id);
  }
}

// The access cookie lives exactly as long as the token inside it (the organization sets that lifetime).
function secondsUntilExpiry(token: string) {
  try {
    const payload = JSON.parse(
      Buffer.from(token.split(".")[1], "base64url").toString("utf8"),
    ) as { exp?: unknown };
    if (typeof payload.exp === "number")
      return Math.max(0, payload.exp - Math.floor(Date.now() / 1000));
  } catch {
    // Not a JWT; fall back to the default lifetime.
  }
  return 600;
}

const str = (v: unknown) => (typeof v === "string" ? v : undefined);
const safeToken = (v: unknown) =>
  typeof v === "string" && v.length > 0 ? v : undefined;

// The body each route takes, and nothing else, from what the browser sent plus what only this proxy knows: the
// device id, the trusted-device token and the device's name.
function upstreamBody(
  operation: string,
  body: AuthRequest,
  device: { id: string; token?: string; name: string; refreshToken: string },
): Record<string, unknown> {
  const phoneNumber = str(body.phoneNumber) ?? "";
  const pin = str(body.pin) ?? "";
  const code = str(body.code) ?? "";
  const purpose = str(body.purpose) ?? "";
  const trustDevice = body.trustDevice !== false;
  const named = { deviceId: device.id, deviceName: device.name };
  const trusted = device.token ? { deviceToken: device.token } : {};
  switch (operation) {
    case "start":
      return { phoneNumber, ...named, ...trusted };
    case "pin":
      return { phoneNumber, ...named, ...trusted, pin };
    case "code":
      return { phoneNumber, ...named, purpose, code, trustDevice };
    case "code/resend":
      return { phoneNumber, ...named, purpose };
    case "pin/forgot":
      return { phoneNumber, ...named };
    case "pin/new":
      return { phoneNumber, ...named, purpose, code, pin, trustDevice };
    case "pin/change":
      return {
        currentPin: str(body.currentPin) ?? "",
        newPin: str(body.newPin) ?? "",
      };
    default:
      if (DEVICE_REMOVE.test(operation)) return {};
      return {
        phoneNumber,
        email: str(body.email) ?? "",
        pin,
        code,
        deviceId: device.id,
        refreshToken: device.refreshToken,
      };
  }
}

export async function POST(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
) {
  const id = requestId();
  const origin = request.headers.get("origin");
  const expectedOrigin = request.nextUrl.origin;
  if (
    origin &&
    !sameOrigin(origin, request.headers.get("host"), expectedOrigin)
  )
    return invalid(403);

  const { path } = await context.params;
  const operation = path.join("/");
  const removesDevice = DEVICE_REMOVE.test(operation);
  if (!allowed.has(operation) && !removesDevice) return invalid(404);

  const jar = await cookies();
  let body: AuthRequest & { thisDevice?: unknown };

  const text = await readLimitedBody(request);
  if (text === null)
    return NextResponse.json({ status: "payload_too_large" }, { status: 413 });
  try {
    body = JSON.parse(text);
  } catch {
    return invalid(400);
  }

  if (!body || typeof body !== "object" || Array.isArray(body))
    return invalid(400);

  const phoneNumber = str(body.phoneNumber) ?? "";
  const email = str(body.email) ?? "";
  const pin = str(body.pin) ?? "";
  const code = str(body.code) ?? "";
  const purpose = str(body.purpose) ?? "";
  const rememberDevice = body.rememberDevice === true;
  const fields = [body.currentPin, body.newPin, body.trustDevice];

  if (
    phoneNumber.length > 20 ||
    email.length > 320 ||
    pin.length > 8 ||
    code.length > 6 ||
    (str(body.currentPin) ?? "").length > 8 ||
    (str(body.newPin) ?? "").length > 8 ||
    (purpose && !PURPOSES.includes(purpose)) ||
    fields.some(
      (value) =>
        value !== undefined &&
        typeof value !== "string" &&
        typeof value !== "boolean",
    )
  )
    return invalid(400);

  const existingDevice = jar.get("device")?.value;
  const deviceId = existingDevice || crypto.randomUUID();
  const trustToken = jar.get("trust")?.value || undefined;
  const upstreamOperation =
    operation === "devices/current/revoke"
      ? `devices/${encodeURIComponent(deviceId)}/revoke`
      : operation;

  try {
    const response = await fetch(`${upstreamUrl()}/auth/${upstreamOperation}`, {
      method: "POST",
      cache: "no-store",
      headers: {
        "Content-Type": "application/json",
        "X-Request-ID": id,
        ...forwardedFor(request),
        ...(jar.get("access")
          ? { Authorization: `Bearer ${jar.get("access")!.value}` }
          : {}),
      },
      body: JSON.stringify(
        upstreamBody(operation, body, {
          id: deviceId,
          token: trustToken,
          name: deviceNameFrom(request.headers.get("user-agent")),
          refreshToken: jar.get("refresh")?.value || "",
        }),
      ),
      signal: AbortSignal.timeout(15_000),
    });
    if (response.status >= 500) return serviceUnavailable(id);
    const raw = await response.json().catch(() => null);
    if (!raw || typeof raw !== "object" || typeof raw.status !== "string")
      return serviceUnavailable(id);
    const result = raw as AuthResponse;
    const output = NextResponse.json(
      {
        status: result.status,
        retryAfterSeconds:
          typeof result.retryAfterSeconds === "number"
            ? result.retryAfterSeconds
            : undefined,
        developmentCode:
          process.env.NODE_ENV !== "production"
            ? str(result.developmentCode) || undefined
            : undefined,
        maskedEmail: str(result.maskedEmail) || undefined,
        minimumPinLength:
          typeof result.minimumPinLength === "number"
            ? result.minimumPinLength
            : undefined,
        purpose: PURPOSES.includes(str(result.purpose) ?? "")
          ? (result.purpose as CodePurpose)
          : undefined,
        triesLeft:
          typeof result.triesLeft === "number" ? result.triesLeft : undefined,
        pinProblem: str(result.pinProblem) || undefined,
      },
      { status: response.status },
    );
    output.headers.set("Cache-Control", "no-store");

    const accessToken = safeToken(result.accessToken);
    const refreshToken = safeToken(result.refreshToken);
    const newTrust = response.ok ? safeToken(result.deviceToken) : undefined;
    // The released routes trust every verified device; the number-first ones answer a token only when trusted.
    const trusted =
      newTrust !== undefined ||
      (response.ok &&
        trustingOperations.has(operation) &&
        Boolean(accessToken));
    const persist = trusted
      ? newTrust !== undefined || rememberDevice
      : jar.get("remember")?.value === "1" || Boolean(trustToken);
    if (trusted || !existingDevice) {
      output.cookies.set("device", deviceId, {
        ...cookieOptions,
        ...(persist ? { maxAge: rememberedSeconds } : {}),
      });
      output.cookies.set("remember", persist ? "1" : "", {
        ...cookieOptions,
        maxAge: persist ? rememberedSeconds : 0,
      });
    }
    if (newTrust) {
      output.cookies.set("trust", newTrust, {
        ...cookieOptions,
        maxAge: trustCookieSeconds,
      });
      // The trusted device remembers its person: the name comes from the session the new token opens.
      const who = await whoIs(accessToken, phoneNumber, id, request);
      output.cookies.set("who", JSON.stringify(who), {
        ...cookieOptions,
        maxAge: trustCookieSeconds,
      });
    }
    if (response.ok && accessToken && refreshToken) {
      output.cookies.set("access", accessToken, {
        ...cookieOptions,
        maxAge: secondsUntilExpiry(accessToken),
      });
      output.cookies.set("refresh", refreshToken, {
        ...cookieOptions,
        ...(persist ? { maxAge: refreshCookieSeconds } : {}),
      });
    }
    // The server no longer trusts this device: a right PIN came back asking for a code.
    const distrusted =
      operation === "pin" &&
      result.status === "verification_required" &&
      result.purpose === "new_device";
    const forgets =
      (response.ok && operation === "devices/current/revoke") ||
      (response.ok && removesDevice && body.thisDevice === true);
    if (distrusted || forgets) {
      output.cookies.set("trust", "", { ...cookieOptions, maxAge: 0 });
      output.cookies.set("who", "", { ...cookieOptions, maxAge: 0 });
    }
    if (
      (response.ok && operation === "sign-out") ||
      forgets ||
      (operation === "refresh" && response.status === 401)
    ) {
      output.cookies.set("access", "", { ...cookieOptions, maxAge: 0 });
      output.cookies.set("refresh", "", { ...cookieOptions, maxAge: 0 });
    }
    return output;
  } catch (error) {
    logProxyError(id, operation, error);
    return serviceUnavailable(id);
  }
}

// The person a trusted device remembers. The session read can fail without failing the sign-in: the screen then
// greets by number alone until the next trusted sign-in.
async function whoIs(
  accessToken: string | undefined,
  phoneNumber: string,
  id: string,
  request: NextRequest,
): Promise<Remembered> {
  const blank = { phoneNumber, firstName: "", lastName: "", role: "" };
  if (!accessToken) return blank;
  try {
    const response = await fetch(`${upstreamUrl()}/auth/session`, {
      headers: {
        Authorization: `Bearer ${accessToken}`,
        "X-Request-ID": id,
        ...forwardedFor(request),
      },
      cache: "no-store",
      signal: AbortSignal.timeout(15_000),
    });
    if (!response.ok) return blank;
    const session = (await response.json()) as Partial<Remembered>;
    return {
      phoneNumber,
      firstName: str(session.firstName) ?? "",
      lastName: str(session.lastName) ?? "",
      role: str(session.role) ?? "",
    };
  } catch (error) {
    logProxyError(id, "session", error);
    return blank;
  }
}
