// @vitest-environment node
import { NextRequest } from "next/server";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { GET, POST, PUT } from "../app/api/setup/[...path]/route";
const jar = vi.hoisted(() => new Map<string, string>());
vi.mock("next/headers", () => ({
  cookies: async () => ({
    get: (name: string) =>
      jar.has(name) ? { value: jar.get(name) } : undefined,
  }),
}));
beforeEach(() => {
  jar.clear();
  jar.set("access", "access-value");
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});
const get = (path: string[]) =>
  GET(new NextRequest("http://localhost:3000/api/setup/people"), {
    params: Promise.resolve({ path }),
  });

it("never lets a path segment step outside /setup", async () => {
  const fetcher = vi.fn();
  vi.stubGlobal("fetch", fetcher);
  for (const path of [
    ["people", "..", "..", "auth", "session"],
    ["people", "../../auth/session"],
    ["people", ".", "x"],
    ["people", "a\\..\\b"],
    ["people", ""],
  ])
    expect((await get(path)).status).toBe(404);
  expect(fetcher).not.toHaveBeenCalled();
});

it("forwards allowed paths with the access token", async () => {
  const fetcher = vi
    .fn()
    .mockResolvedValue(new Response("{}", { status: 200 }));
  vi.stubGlobal("fetch", fetcher);
  expect((await get(["people", "3f2c", "deactivate"])).status).toBe(200);
  expect(fetcher.mock.calls[0][0]).toMatch(
    /\/setup\/people\/3f2c\/deactivate$/,
  );
  expect(fetcher.mock.calls[0][1].headers.Authorization).toBe(
    "Bearer access-value",
  );
});

it("forwards revenue, expense catalog and investment paths, and nothing unlisted", async () => {
  const fetcher = vi.fn(
    async (url: string) =>
      new Response(JSON.stringify({ url }), { status: 200 }),
  );
  vi.stubGlobal("fetch", fetcher);
  const allowed = [
    ["revenue"],
    ["revenue", "dashboard"],
    ["revenue", "v-1", "2026-09-21"],
    ["expense-categories"],
    ["expense-categories", "c-1", "items"],
    ["expense-categories", "c-1", "stop"],
    ["expense-items", "options"],
    ["expense-items", "i-1", "restore"],
    ["investment", "e-1"],
    ["vehicles", "v-1", "investment"],
  ];
  for (const path of allowed)
    expect((await get(path)).status, path.join("/")).toBe(200);
  expect(
    fetcher.mock.calls.map(([url]) => String(url).replace(/^.*\/setup\//, "")),
  ).toEqual(allowed.map((path) => path.join("/")));

  fetcher.mockClear();
  for (const path of [
    ["expense"],
    ["expense-categoriesx"],
    ["investments"],
    ["revenues", "x"],
    ["auth", "session"],
  ])
    expect((await get(path)).status, path.join("/")).toBe(404);
  expect(fetcher).not.toHaveBeenCalled();
});

it("forwards every petty cash path", async () => {
  const fetcher = vi.fn(
    async (url: string) =>
      new Response(JSON.stringify({ url }), { status: 200 }),
  );
  vi.stubGlobal("fetch", fetcher);
  const allowed = [
    ["pettycash", "overview"],
    ["pettycash", "entries"],
    ["pettycash", "options"],
    ["pettycash", "dashboard"],
    ["pettycash", "approve-day"],
    ["pettycash", "entries", "e-1"],
    ["pettycash", "entries", "e-1", "approve"],
    ["pettycash", "entries", "e-1", "send-back"],
    ["pettycash", "entries", "e-1", "remove"],
  ];
  for (const path of allowed)
    expect((await get(path)).status, path.join("/")).toBe(200);
  expect(
    fetcher.mock.calls.map(([url]) => String(url).replace(/^.*\/setup\//, "")),
  ).toEqual(allowed.map((path) => path.join("/")));

  fetcher.mockClear();
  for (const path of [["pettycashx"], ["petty-cash", "overview"]])
    expect((await get(path)).status, path.join("/")).toBe(404);
  expect(fetcher).not.toHaveBeenCalled();
});

it("forwards the expenses ledger and reports paths, and nothing like them", async () => {
  const fetcher = vi.fn(
    async (url: string) =>
      new Response(JSON.stringify({ url }), { status: 200 }),
  );
  vi.stubGlobal("fetch", fetcher);
  const allowed = [
    ["expenses", "ledger"],
    ["expenses", "options"],
    ["expenses", "entries"],
    ["expenses", "entries", "e-1"],
    ["expenses", "entries", "e-1", "remove"],
    ["reports"],
    ["reports", "fleet", "net"],
    ["reports", "pettycash", "cashBook", "export"],
  ];
  for (const path of allowed)
    expect((await get(path)).status, path.join("/")).toBe(200);
  expect(
    fetcher.mock.calls.map(([url]) => String(url).replace(/^.*\/setup\//, "")),
  ).toEqual(allowed.map((path) => path.join("/")));

  fetcher.mockClear();
  for (const path of [["expensesx", "ledger"], ["report"], ["reportsx"]])
    expect((await get(path)).status, path.join("/")).toBe(404);
  expect(fetcher).not.toHaveBeenCalled();
});

// The largest legitimate body is a logo upload: a data URL of about 350 KB.
const MB = 1024 * 1024;
const write = (
  method: "POST" | "PUT",
  body: string | ReadableStream<Uint8Array>,
  headers: Record<string, string> = {},
) =>
  (method === "POST" ? POST : PUT)(
    // A streamed body needs duplex "half", which the request types do not list yet.
    new NextRequest("http://localhost:3000/api/setup/organization/logo", {
      method,
      body,
      headers: { "content-type": "application/json", ...headers },
      duplex: "half",
    } as ConstructorParameters<typeof NextRequest>[1]),
    { params: Promise.resolve({ path: ["organization", "logo"] }) },
  );

it("refuses a body over 1 MB before forwarding it, by its declared and its actual size", async () => {
  const fetcher = vi.fn(async () => new Response("{}", { status: 200 }));
  vi.stubGlobal("fetch", fetcher);

  const declared = await write("PUT", "{}", {
    "content-length": String(MB + 1),
  });
  expect(declared.status).toBe(413);
  expect(await declared.json()).toEqual({ status: "payload_too_large" });

  // No length declared: the body is counted as it is read.
  const chunk = new Uint8Array(256 * 1024).fill(0x61);
  let sent = 0;
  const stream = new ReadableStream<Uint8Array>({
    pull(controller) {
      if (sent++ < 5) controller.enqueue(chunk);
      else controller.close();
    },
  });
  const streamed = await write("POST", stream);
  expect(streamed.status).toBe(413);
  expect(await streamed.json()).toEqual({ status: "payload_too_large" });
  expect(fetcher).not.toHaveBeenCalled();

  const logo = JSON.stringify({
    dataUrl: `data:image/png;base64,${"A".repeat(350 * 1024)}`,
  });
  expect((await write("PUT", logo)).status).toBe(200);
  expect(fetcher).toHaveBeenCalledOnce();
  expect(
    (fetcher.mock.calls[0] as unknown as [string, RequestInit])[1].body,
  ).toBe(logo);
});

it("tells the API which browser a request comes from, only through trusted proxy hops", async () => {
  const fetcher = vi.fn(async () => new Response("{}", { status: 200 }));
  vi.stubGlobal("fetch", fetcher);
  const call = (headers: Record<string, string>) =>
    GET(
      new NextRequest("http://localhost:3000/api/setup/people", { headers }),
      { params: Promise.resolve({ path: ["people"] }) },
    );
  await call({
    "x-forwarded-for": "203.0.113.99, 198.51.100.7",
    "x-real-ip": "198.51.100.8",
  });
  vi.stubEnv("TRUSTED_PROXY_HOPS", "1");
  await call({
    "x-forwarded-for": "203.0.113.99, 198.51.100.7",
    "x-real-ip": "198.51.100.8",
  });
  await call({ "x-real-ip": "198.51.100.8" });
  const sent = (fetcher.mock.calls as unknown as [string, RequestInit][]).map(
    ([, init]) => (init.headers as Record<string, string>)["X-Forwarded-For"],
  );
  expect(sent).toEqual([undefined, "198.51.100.7", undefined]);
});

it("never forwards an empty body, which fetch would send as text/plain and the API would refuse", async () => {
  const fetcher = vi
    .fn()
    .mockResolvedValue(new Response("{}", { status: 200 }));
  vi.stubGlobal("fetch", fetcher);
  const request = new NextRequest(
    "http://localhost:3000/api/setup/people/3f2c/deactivate",
    { method: "POST" },
  );
  expect(
    (
      await POST(request, {
        params: Promise.resolve({ path: ["people", "3f2c", "deactivate"] }),
      })
    ).status,
  ).toBe(200);
  const init = fetcher.mock.calls[0][1];
  expect(init.body).toBeUndefined();
  expect(init.headers["Content-Type"]).toBeUndefined();
});

it("turns an upstream 5xx into a 503 with a request id", async () => {
  const fetcher = vi
    .fn()
    .mockResolvedValue(new Response("stack trace", { status: 502 }));
  vi.stubGlobal("fetch", fetcher);
  const result = await get(["people"]);
  expect(result.status).toBe(503);
  expect(result.headers.get("Cache-Control")).toBe("no-store");
  const body = await result.json();
  expect(body).toEqual({
    status: "service_unavailable",
    requestId: expect.any(String),
  });
  expect(fetcher.mock.calls[0][1].headers["X-Request-ID"]).toBe(body.requestId);
});

it("answers 503 with no-store and logs when the API cannot be reached", async () => {
  const log = vi.spyOn(console, "error").mockImplementation(() => undefined);
  vi.stubGlobal(
    "fetch",
    vi.fn().mockRejectedValue(new TypeError("fetch failed")),
  );
  const result = await get(["people"]);
  expect(result.status).toBe(503);
  expect(result.headers.get("Cache-Control")).toBe("no-store");
  const body = await result.json();
  expect(body).toEqual({
    status: "service_unavailable",
    requestId: expect.any(String),
  });
  expect(JSON.parse(log.mock.calls[0][0] as string)).toMatchObject({
    requestId: body.requestId,
    operation: "people",
  });
});

const text = new TextEncoder();
const decode = (chunk: Uint8Array | undefined) =>
  new TextDecoder().decode(chunk);

// An upstream body that the test releases piece by piece, and that errors the way fetch does when its signal aborts.
function controlledBody(signal?: AbortSignal | null) {
  let controller!: ReadableStreamDefaultController<Uint8Array>;
  const cancelled = vi.fn();
  const body = new ReadableStream<Uint8Array>({
    start(c) {
      controller = c;
      signal?.addEventListener("abort", () => c.error(signal.reason));
    },
    cancel: cancelled,
  });
  return {
    body,
    cancelled,
    send: (value: string) => controller.enqueue(text.encode(value)),
    close: () => controller.close(),
    fail: (error: Error) => controller.error(error),
  };
}

it("hands the caller the first chunk before the upstream body has finished", async () => {
  const upstream = controlledBody();
  upstream.send("first,");
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      new Response(upstream.body, {
        status: 200,
        headers: { "Content-Type": "application/json; charset=utf-8" },
      }),
    ),
  );
  const result = await get(["people"]);
  expect(result.status).toBe(200);
  expect(result.headers.get("Content-Type")).toBe(
    "application/json; charset=utf-8",
  );
  expect(result.headers.get("Cache-Control")).toBe("no-store");
  expect(result.headers.get("X-Request-ID")).toEqual(expect.any(String));

  const reader = result.body!.getReader();
  expect(decode((await reader.read()).value)).toBe("first,");
  upstream.send("second");
  expect(decode((await reader.read()).value)).toBe("second");
  upstream.close();
  expect((await reader.read()).done).toBe(true);
});

it("never forwards the upstream's encoding, length or transfer headers, whose bytes fetch has already decoded", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      new Response('{"ok":true}', {
        status: 200,
        headers: {
          "Content-Type": "application/json",
          "Content-Encoding": "br",
          "Content-Length": "9",
          "Transfer-Encoding": "chunked",
          "X-Powered-By": "upstream",
        },
      }),
    ),
  );
  const result = await get(["people"]);
  for (const name of [
    "content-encoding",
    "content-length",
    "transfer-encoding",
    "x-powered-by",
  ])
    expect(result.headers.get(name), name).toBeNull();
  expect(await result.json()).toEqual({ ok: true });
});

it("passes a status without a body through as one", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(new Response(null, { status: 204 })),
  );
  const result = await get(["people", "3f2c", "restore"]);
  expect(result.status).toBe(204);
  expect(result.body).toBeNull();
});

it("does not cut off a slow body once the API has answered", async () => {
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
  try {
    const upstream = {
      current: undefined as ReturnType<typeof controlledBody> | undefined,
    };
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_url: string, init: RequestInit) => {
        upstream.current = controlledBody(init.signal);
        upstream.current.send("early,");
        return new Response(upstream.current.body, { status: 200 });
      }),
    );
    const result = await get(["people"]);
    const reader = result.body!.getReader();
    expect(decode((await reader.read()).value)).toBe("early,");

    await vi.advanceTimersByTimeAsync(60_000);
    upstream.current!.send("late");
    upstream.current!.close();
    expect(decode((await reader.read()).value)).toBe("late");
    expect((await reader.read()).done).toBe(true);
  } finally {
    vi.useRealTimers();
  }
});

it("answers 503 when the API does not send its headers in 15 seconds", async () => {
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
  const log = vi.spyOn(console, "error").mockImplementation(() => undefined);
  try {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        (_url: string, init: RequestInit) =>
          new Promise((_resolve, reject) =>
            init.signal!.addEventListener("abort", () =>
              reject(init.signal!.reason),
            ),
          ),
      ),
    );
    const pending = get(["people"]);
    await vi.advanceTimersByTimeAsync(14_999);
    await vi.advanceTimersByTimeAsync(1);
    const result = await pending;
    expect(result.status).toBe(503);
    expect(await result.json()).toEqual({
      status: "service_unavailable",
      requestId: expect.any(String),
    });
    expect(JSON.parse(log.mock.calls[0][0] as string)).toMatchObject({
      operation: "people",
      level: "error",
    });
  } finally {
    vi.useRealTimers();
  }
});

it("cancels the unread body of an upstream 5xx", async () => {
  const upstream = controlledBody();
  upstream.send("stack trace");
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(new Response(upstream.body, { status: 500 })),
  );
  expect((await get(["people"])).status).toBe(503);
  expect(upstream.cancelled).toHaveBeenCalledOnce();
});

it("logs a body that fails after the response has started and errors the stream", async () => {
  const log = vi.spyOn(console, "error").mockImplementation(() => undefined);
  const upstream = controlledBody();
  upstream.send("partial");
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(new Response(upstream.body, { status: 200 })),
  );
  const result = await get(["people"]);
  const reader = result.body!.getReader();
  expect(decode((await reader.read()).value)).toBe("partial");
  upstream.fail(new TypeError("terminated"));
  await expect(reader.read()).rejects.toThrow("terminated");
  expect(JSON.parse(log.mock.calls[0][0] as string)).toMatchObject({
    operation: "people",
    error: "terminated",
    level: "error",
  });
});

it("stops reading the upstream body when the caller goes away", async () => {
  const upstream = controlledBody();
  upstream.send("some");
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(new Response(upstream.body, { status: 200 })),
  );
  const result = await get(["people"]);
  const reader = result.body!.getReader();
  await reader.read();
  await reader.cancel();
  expect(upstream.cancelled).toHaveBeenCalledOnce();
});
