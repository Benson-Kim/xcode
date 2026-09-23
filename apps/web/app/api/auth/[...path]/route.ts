import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";
import type { AuthRequest, AuthResponse } from "@xcode/shared";

const allowed = new Set([
  "sign-in",
  "verify-device",
  "setup-pin/request",
  "setup-pin/complete",
  "pin-reset/request",
  "pin-reset/complete",
  "refresh",
  "sign-out",
  "devices/current/revoke",
]);

const cookieOptions = {
  httpOnly: true,
  secure: process.env.NODE_ENV === "production",
  sameSite: "strict" as const,
  path: "/",
};

export async function POST(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
) {
  if (request.headers.get("origin") !== request.nextUrl.origin)
    return NextResponse.json(
      {
        status: "invalid_request",
      },
      { status: 403 },
    );
  
  const { path } = await context.params;
  const operation = path.join("/");
  if (!allowed.has(operation))
    return NextResponse.json({
      status: "invalid_request"
    }, { status: 404 }
    );
  
  const jar = await cookies();
  let body: AuthRequest;

  try {
    body = await request.json();
  } catch {
    return NextResponse.json(
      { status: "invalid_request" }, { status: 400 });
  }

  if (!body || typeof body !== "object")
    return NextResponse.json(
      { status: "invalid_request" }, { status: 400 });
  
  const deviceId = jar.get("device")?.value || crypto.randomUUID();
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
          ...(jar.get("access")
            ? { Authorization: `Bearer ${jar.get("access")!.value}` }
            : {}),
        },
        body: JSON.stringify({
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
      { status: result.status, retryAfterSeconds: result.retryAfterSeconds },
      { status: response.status },
    );
    output.headers.set("Cache-Control", "no-store");
    output.cookies.set("device", deviceId, {
      ...cookieOptions,
      maxAge: 365 * 24 * 3600,
    });
    if (response.ok && result.accessToken && result.refreshToken) {
      output.cookies.set("access", result.accessToken, {
        ...cookieOptions,
        maxAge: 600,
      });
      output.cookies.set("refresh", result.refreshToken, {
        ...cookieOptions,
        maxAge: 30 * 24 * 3600,
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
