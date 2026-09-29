import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";
import { readLimitedBody } from "../../body";

const allowedMethods = new Set(["GET", "POST", "PUT", "DELETE"]);

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
) {
  return proxy(request, context, "GET");
}

export async function POST(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
) {
  return proxy(request, context, "POST");
}

export async function PUT(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
) {
  return proxy(request, context, "PUT");
}

export async function DELETE(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
) {
  return proxy(request, context, "DELETE");
}

async function proxy(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
  method: string,
) {
  if (!allowedMethods.has(method))
    return NextResponse.json({ status: "invalid_request" }, { status: 405 });
  const origin = request.headers.get("origin");
  const expectedOrigin = request.nextUrl.origin;
  if (
    origin &&
    !sameOrigin(origin, request.headers.get("host"), expectedOrigin)
  )
    return NextResponse.json({ status: "invalid_request" }, { status: 403 });

  const { path } = await context.params;
  // Each segment is one plain name or id: "..", "." or an encoded slash must never reach the API as a path step.
  if (path.some((segment) => segment === "" || segment === "." || segment === ".." || /[/\\]/.test(segment)))
    return NextResponse.json({ status: "invalid_request" }, { status: 404 });
  const operation = path.map(encodeURIComponent).join("/");
  if (
    !/^(companies|vehicles|recurring|revenue|expense-categories|expense-items|investment|history|preferences|appearance|organization\/logo|organization\/settings|organization\/settings\/(organization|localization|branding|securityPolicy|businessDate)|access\/(catalog|roles|scope-options)|people)(\/[^/]+)*$/.test(
      operation,
    )
  )
    return NextResponse.json({ status: "invalid_request" }, { status: 404 });

  const jar = await cookies();
  const access = jar.get("access")?.value;
  if (!access)
    return NextResponse.json(
      { status: "authentication_failed" },
      { status: 401 },
    );

  const body = method === "GET" || method === "DELETE" ? undefined : await readLimitedBody(request);
  if (body === null)
    return NextResponse.json({ status: "payload_too_large" }, { status: 413 });
  try {
    const response = await fetch(
      `${process.env.API_URL || "http://localhost:5000"}/setup/${operation}${request.nextUrl.search}`,
      {
        method,
        cache: "no-store",
        headers: {
          Authorization: `Bearer ${access}`,
          ...(body ? { "Content-Type": "application/json" } : {}),
        },
        body,
        signal: AbortSignal.timeout(15_000),
      },
    );
    const result = await response.text();
    return new NextResponse(result, {
      status: response.status,
      headers: {
        "Content-Type":
          response.headers.get("Content-Type") || "application/json",
        "Cache-Control": "no-store",
      },
    });
  } catch {
    return NextResponse.json(
      { status: "service_unavailable" },
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
