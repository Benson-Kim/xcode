// A stand-in for the XCODE API behind fetch: tests say how each route answers and read what was sent.
type Reply = [status: number, body: unknown] | "offline";
type Handler = (body: Record<string, string>, headers: Record<string, string>) => Reply;

export const people = {
  owner: { userId: "u-antony", firstName: "Antony", lastName: "Maina", role: "Owner", permissions: ["dash.revenue", "dash.net", "dash.costs", "dash.gaps", "revenue.view", "revenue.correct", "people.view", "people.manage", "companies.manage", "audit.view"] },
  manager: { userId: "u-brian", firstName: "Brian", lastName: "Mwangi", role: "Fleet manager", permissions: ["dash.revenue", "revenue.view", "pettycash.spend"] },
  clerk: { userId: "u-wanjiru", firstName: "Wanjiru", lastName: "Kamau", role: "Revenue clerk", permissions: ["dash.capture", "dash.gaps", "revenue.view", "revenue.capture", "revenue.no_earnings"] },
};

export const catalog = [
  { name: "Dashboard", items: [{ key: "dash.capture", label: "See today's capture for my vehicles", needs: [] }, { key: "dash.revenue", label: "See revenue totals", needs: [] }] },
  {
    name: "Revenue",
    items: [
      { key: "revenue.view", label: "View revenue records", needs: [] },
      { key: "revenue.capture", label: "Capture revenue", needs: ["revenue.view"] },
      { key: "revenue.no_earnings", label: "Record a no earnings reason", needs: ["revenue.capture"] },
      { key: "revenue.correct", label: "Correct revenue after the day", needs: ["revenue.view"] },
    ],
  },
  { name: "Setup", items: [{ key: "companies.manage", label: "Set up PSV companies", needs: [] }, { key: "people.view", label: "View people", needs: [] }] },
];

export const tokens = (n = 1) => ({ status: "authenticated", accessToken: `access-${n}`, refreshToken: `refresh-${n}` });

export function fakeApi() {
  const routes = new Map<string, Handler>();
  const calls: { path: string; body: Record<string, string>; headers: Record<string, string> }[] = [];
  const fetch = jest.fn(async (url: string, init: RequestInit = {}) => {
    const path = url.replace(/^https?:\/\/[^/]+\//, "");
    const body = init.body ? JSON.parse(String(init.body)) : {};
    const headers = (init.headers ?? {}) as Record<string, string>;
    calls.push({ path, body, headers });
    const reply = routes.get(path)?.(body, headers) ?? [404, {}];
    if (reply === "offline") throw new TypeError("Network request failed");
    const [status, json] = reply;
    return { ok: status >= 200 && status < 300, status, json: async () => json } as Response;
  });
  globalThis.fetch = fetch as unknown as typeof globalThis.fetch;
  return {
    calls,
    on(path: string, handler: Handler | Reply) {
      routes.set(path, typeof handler === "function" ? handler : () => handler);
    },
    sent: (path: string) => calls.filter((call) => call.path === path).map((call) => call.body),
  };
}
