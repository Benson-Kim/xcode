import { afterEach, vi } from "vitest";

// A stand-in for the XCODE API behind fetch: tests say how each route answers and read what was sent.
export type Reply = readonly [status: number, body?: unknown] | "offline";
export type Sent = {
  method: string;
  path: string;
  body: Record<string, unknown>;
  headers: Record<string, string>;
};
type Handler = (sent: Sent) => Reply | Promise<Reply>;

afterEach(() => vi.unstubAllGlobals());

// Keys are "GET setup/people" or "PUT setup/preferences"; a bare path means GET. A trailing "*" matches by prefix.
export function fakeApi() {
  const routes = new Map<string, Handler>();
  const queued = new Map<string, Handler[]>();
  const calls: Sent[] = [];
  const unhandled: Sent[] = [];
  const keyOf = (key: string) => (/^[A-Z]+ /.test(key) ? key : `GET ${key}`);
  const fetch = vi.fn(async (url: string, init: RequestInit = {}) => {
    const sent: Sent = {
      method: init.method ?? "GET",
      path: url.replace(/^\/api\//, ""),
      body: init.body
        ? (JSON.parse(String(init.body)) as Record<string, unknown>)
        : {},
      headers: (init.headers ?? {}) as Record<string, string>,
    };
    calls.push(sent);
    const key = `${sent.method} ${sent.path}`;
    let handler = queued.get(key)?.shift() ?? routes.get(key);
    if (!handler) {
      for (const [pattern, candidate] of routes) {
        if (pattern.endsWith("*") && key.startsWith(pattern.slice(0, -1)))
          handler = candidate;
      }
    }
    if (!handler) unhandled.push(sent);
    const reply = handler
      ? await handler(sent)
      : ([404, { title: "No route" }] as Reply);
    if (reply === "offline") throw new TypeError("Failed to fetch");
    const [status, json] = reply;
    if (status === 204 || status === 205) return new Response(null, { status });
    return new Response(JSON.stringify(json ?? {}), { status });
  });
  vi.stubGlobal("fetch", fetch);
  const asHandler = (reply: Handler | Reply): Handler =>
    typeof reply === "function" ? reply : () => reply;
  return {
    fetch,
    calls,
    unhandled,
    on(key: string, reply: Handler | Reply) {
      routes.set(keyOf(key), asHandler(reply));
    },
    once(key: string, reply: Handler | Reply) {
      const normal = keyOf(key);
      queued.set(normal, [...(queued.get(normal) ?? []), asHandler(reply)]);
    },
    sent: (key: string) => {
      const normal = keyOf(key);
      return calls
        .filter((call) => `${call.method} ${call.path}` === normal)
        .map((call) => call.body);
    },
  };
}

export const defer = <T>() => {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => (resolve = done));
  return { promise, resolve };
};
