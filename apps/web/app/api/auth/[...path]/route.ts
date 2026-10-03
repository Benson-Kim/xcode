import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";
import type { AuthRequest, AuthResponse } from "@xcode/shared";
import { forwardedFor, readLimitedBody } from "../../body";

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
  if (!access) return NextResponse.json({ status: "authentication_failed" }, { status: 401 });
  try {
    const response = await fetch(`${process.env.API_URL || "http://localhost:5000"}/auth/session`, {
      headers: { Authorization: `Bearer ${access}`, ...forwardedFor(request) },
      cache: "no-store",
      signal: AbortSignal.timeout(15_000),
    });
    return new NextResponse(await response.text(), { status: response.status, headers: { "Content-Type": "application/json", "Cache-Control": "no-store" } });
  } catch {
    // The API is down or too slow: the same answer the setup proxy gives.
    return NextResponse.json({ status: "service_unavailable" }, { status: 503, headers: { "Cache-Control": "no-store" } });
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

  if (!body || typeof body !== "object")
    return NextResponse.json({ status: "invalid_request" }, { status: 400 });

  const existingDevice = jar.get("device")?.value;
  const deviceId = existingDevice || crypto.randomUUID();
  const upstreamOperation =
    operation === "devices/current/revoke"
      ? `devices/${encodeURIComponent(deviceId)}/revoke`
      : operation;

  try {
    const response = await fetch(
      `${process.env.API_URL || "http://localhost:5000"}/auth/${upstreamOperation}`,
      {
        method: "POST",
        cache: "no-store",
        headers: {
          "Content-Type": "application/json",
          ...forwardedFor(request),
          ...(jar.get("access")
            ? { Authorization: `Bearer ${jar.get("access")!.value}` }
            : {}),
        },
        body: JSON.stringify({
          phoneNumber: body.phoneNumber || "",
          email: body.email || "",
          pin: body.pin || "",
          code: body.code || "",
          deviceId,
          refreshToken: jar.get("refresh")?.value || "",
        }),
        signal: AbortSignal.timeout(15_000),
      },
    );
    const result = (await response
      .json()
      .catch(() => ({ status: "authentication_failed" }))) as AuthResponse;
    const output = NextResponse.json(
      {
        status: result.status,
        retryAfterSeconds: result.retryAfterSeconds,
        developmentCode: result.developmentCode,
        maskedEmail: result.maskedEmail,
        minimumPinLength: result.minimumPinLength,
      },
      { status: response.status },
    );
    output.headers.set("Cache-Control", "no-store");
    // "Remember this device" decides whether trust outlives the browser session. Unless the person
    // asks for it, the device id is a session cookie: once the browser closes, the next sign-in
    // is a new device and needs an email code again. The choice is made when trust is granted and
    // then kept (via the remember marker) instead of re-extending the cookie on every call.
    const trusted =
      response.ok &&
      trustingOperations.has(operation) &&
      Boolean(result.accessToken);
    const persist = trusted
      ? body.rememberDevice === true
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
    if (response.ok && result.accessToken && result.refreshToken) {
      output.cookies.set("access", result.accessToken, {
        ...cookieOptions,
        maxAge: secondsUntilExpiry(result.accessToken),
      });
      output.cookies.set("refresh", result.refreshToken, {
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
  } catch {
    return NextResponse.json(
      { status: "authentication_failed" },
      { status: 503 },
    );
  }
}

function sameOrigin(
  origin: string,
  host: string | null,
  expectedOrigin: string,
) {
  try {
    const parsed = new URL(origin);
    const expected = new URL(expectedOrigin);
    return (
      parsed.protocol === expected.protocol &&
      parsed.host === (host || expected.host)
    );
  } catch {
    return false;
  }
}
