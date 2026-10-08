import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";

import type { AuthRequest, AuthResponse } from "@xcode/shared/auth";

import {
  forwardedFor,
  logProxyError,
  readLimitedBody,
  requestId,
  sameOrigin,
  upstreamUrl,
} from "../../body";

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
]);

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
    return NextResponse.json({ status: "invalid_request" }, { status: 403 });

  const { path } = await context.params;
  if (path.join("/") !== "session")
    return NextResponse.json({ status: "invalid_request" }, { status: 404 });

  const access = (await cookies()).get("access")?.value;
  if (!access)
    return NextResponse.json(
      { status: "authentication_failed" },
      { status: 401 },
    );
  try {
    const response = await fetch(`${upstreamUrl()}/auth/session`, {
      headers: {
        Authorization: `Bearer ${access}`,
        "X-Request-ID": id,
        ...forwardedFor(request),
      },
      cache: "no-store",
      signal: AbortSignal.timeout(15_000),
    });
    if (response.status >= 500)
      return NextResponse.json(
        { status: "service_unavailable", requestId: id },
        { status: 503, headers: { "Cache-Control": "no-store" } },
      );
    return new NextResponse(await response.text(), {
      status: response.status,
      headers: {
        "Content-Type": "application/json",
        "Cache-Control": "no-store",
      },
    });
  } catch (error) {
    logProxyError(id, "session", error);
    return NextResponse.json(
      { status: "service_unavailable", requestId: id },
      { status: 503, headers: { "Cache-Control": "no-store" } },
    );
  }
}

const cookieOptions = {
  httpOnly: true,
  secure: process.env.NODE_ENV === "production",
  sameSite: "strict" as const,
  path: "/",
};

// Calls that mark this browser as a trusted device when they succeed.
const trustingOperations = new Set([
  "verify-device",
  "setup-pin/complete",
  "pin-reset/complete",
]);
const rememberedSeconds = 365 * 24 * 3600;
// The longest refresh lifetime a security policy allows; the API enforces the organization's real one.
const refreshCookieSeconds = 90 * 24 * 3600;

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
    return NextResponse.json(
      {
        status: "invalid_request",
      },
      { status: 403 },
    );

  const { path } = await context.params;
  const operation = path.join("/");
  if (!allowed.has(operation))
    return NextResponse.json(
      {
        status: "invalid_request",
      },
      { status: 404 },
    );

  const jar = await cookies();
  let body: AuthRequest;

  const text = await readLimitedBody(request);
  if (text === null)
    return NextResponse.json({ status: "payload_too_large" }, { status: 413 });
  try {
    body = JSON.parse(text);
  } catch {
    return NextResponse.json({ status: "invalid_request" }, { status: 400 });
  }

  if (!body || typeof body !== "object" || Array.isArray(body))
    return NextResponse.json({ status: "invalid_request" }, { status: 400 });

  const str = (v: unknown) => (typeof v === "string" ? v : undefined);
  const phoneNumber = str(body.phoneNumber) ?? "";
  const email = str(body.email) ?? "";
  const pin = str(body.pin) ?? "";
  const code = str(body.code) ?? "";
  const rememberDevice = body.rememberDevice === true;

  if (
    phoneNumber.length > 20 ||
    email.length > 320 ||
    pin.length > 8 ||
    code.length > 6
  )
    return NextResponse.json({ status: "invalid_request" }, { status: 400 });

  const existingDevice = jar.get("device")?.value;
  const deviceId = existingDevice || crypto.randomUUID();
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
      body: JSON.stringify({
        phoneNumber,
        email,
        pin,
        code,
        deviceId,
        refreshToken: jar.get("refresh")?.value || "",
      }),
      signal: AbortSignal.timeout(15_000),
    });
    if (response.status >= 500)
      return NextResponse.json(
        { status: "service_unavailable", requestId: id },
        { status: 503, headers: { "Cache-Control": "no-store" } },
      );
    const raw = await response.json().catch(() => null);
    if (!raw || typeof raw !== "object" || typeof raw.status !== "string")
      return NextResponse.json(
        { status: "service_unavailable", requestId: id },
        { status: 503, headers: { "Cache-Control": "no-store" } },
      );
    const result = raw as AuthResponse;
    const safeToken = (v: unknown) =>
      typeof v === "string" && v.length > 0 ? v : undefined;
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
      },
      { status: response.status },
    );
    output.headers.set("Cache-Control", "no-store");
    const trusted =
      response.ok &&
      trustingOperations.has(operation) &&
      Boolean(safeToken(result.accessToken));
    const persist = trusted
      ? rememberDevice
      : jar.get("remember")?.value === "1";
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
    const accessToken = safeToken(result.accessToken);
    const refreshToken = safeToken(result.refreshToken);
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
    if (
      (response.ok &&
        (operation === "sign-out" || operation === "devices/current/revoke")) ||
      (operation === "refresh" && response.status === 401)
    ) {
      output.cookies.set("access", "", { ...cookieOptions, maxAge: 0 });
      output.cookies.set("refresh", "", { ...cookieOptions, maxAge: 0 });
    }
    return output;
  } catch (error) {
    logProxyError(id, operation, error);
    return NextResponse.json(
      { status: "service_unavailable", requestId: id },
      { status: 503, headers: { "Cache-Control": "no-store" } },
    );
  }
}
