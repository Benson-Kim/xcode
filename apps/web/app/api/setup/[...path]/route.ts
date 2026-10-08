import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";

import {
  forwardedFor,
  logProxyError,
  readLimitedBody,
  requestId,
  sameOrigin,
  upstreamUrl,
} from "../../body";

const allowedMethods = new Set(["GET", "POST", "PUT", "DELETE"]);
const HEADERS_TIMEOUT_MS = 15_000;
const NO_BODY_STATUSES = new Set([101, 204, 205, 304]);

// Passes the upstream body on chunk by chunk. A failure after the response has started cannot become a 503, so it
// is logged and the stream is errored, which cuts the connection rather than ending the body as if it were whole.
function relay(
  source: ReadableStream<Uint8Array>,
  id: string,
  operation: string,
) {
  const reader = source.getReader();
  return new ReadableStream<Uint8Array>({
    async pull(controller) {
      try {
        const { done, value } = await reader.read();
        if (done) controller.close();
        else controller.enqueue(value);
      } catch (error) {
        logProxyError(id, operation, error);
        controller.error(error);
      }
    },
    cancel: (reason) => reader.cancel(reason),
  });
}

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
  const id = requestId();
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
  if (
    path.some(
      (segment) =>
        segment === "" ||
        segment === "." ||
        segment === ".." ||
        /[/\\]/.test(segment),
    )
  )
    return NextResponse.json({ status: "invalid_request" }, { status: 404 });
  const operation = path.map(encodeURIComponent).join("/");
  if (
    !/^(companies|vehicles|recurring|revenue|pettycash|expense-categories|expense-items|investment|history|preferences|appearance|organization\/logo|organization\/settings|organization\/settings\/(organization|localization|branding|securityPolicy|businessDate)|access\/(catalog|me|roles|scope-options)|people)(\/[^/]+)*$/.test(
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

  const body =
    method === "GET" || method === "DELETE"
      ? undefined
      : await readLimitedBody(request);
  if (body === null)
    return NextResponse.json({ status: "payload_too_large" }, { status: 413 });
  try {
    // The limit is for the API to start answering. Once its headers are here the body is relayed as it arrives,
    // however long it takes.
    const abort = new AbortController();
    const timer = setTimeout(
      () =>
        abort.abort(
          new DOMException("The API did not answer in time.", "TimeoutError"),
        ),
      HEADERS_TIMEOUT_MS,
    );
    let response: Response;
    try {
      response = await fetch(
        `${upstreamUrl()}/setup/${operation}${request.nextUrl.search}`,
        {
          method,
          cache: "no-store",
          headers: {
            Authorization: `Bearer ${access}`,
            "X-Request-ID": id,
            ...forwardedFor(request),
            ...(body ? { "Content-Type": "application/json" } : {}),
          },
          // An empty body is not forwarded: fetch would send it as text/plain, which the API refuses (415).
          body: body || undefined,
          signal: abort.signal,
        },
      );
    } finally {
      clearTimeout(timer);
    }
    if (response.status >= 500) {
      await response.body?.cancel();
      return NextResponse.json(
        { status: "service_unavailable", requestId: id },
        { status: 503, headers: { "Cache-Control": "no-store" } },
      );
    }
    // fetch has already decoded the body, so the upstream's encoding and length headers describe bytes that are
    // no longer these ones. Only the content type is carried over.
    const headers = {
      "Content-Type":
        response.headers.get("Content-Type") || "application/json",
      "Cache-Control": "no-store",
      "X-Request-ID": id,
    };
    if (!response.body || NO_BODY_STATUSES.has(response.status)) {
      await response.body?.cancel();
      return new NextResponse(null, { status: response.status, headers });
    }
    return new NextResponse(relay(response.body, id, operation), {
      status: response.status,
      headers,
    });
  } catch (error) {
    logProxyError(id, operation, error);
    return NextResponse.json(
      { status: "service_unavailable", requestId: id },
      { status: 503, headers: { "Cache-Control": "no-store" } },
    );
  }
}
