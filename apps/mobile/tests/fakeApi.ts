// A stand-in for the XCODE API behind fetch: tests say how each route answers and read what was sent.
type Reply = [status: number, body: unknown] | "offline";
type Handler = (
  body: Record<string, string>,
  headers: Record<string, string>,
) => Reply | Promise<Reply>;

export const people = {
  owner: {
    userId: "u-antony",
    firstName: "Antony",
    lastName: "Maina",
    role: "Owner",
    permissions: [
      "dash.revenue",
      "dash.net",
      "dash.costs",
      "dash.gaps",
      "revenue.view",
      "revenue.correct",
      "people.view",
      "people.manage",
      "companies.manage",
      "audit.view",
    ],
  },
  manager: {
    userId: "u-brian",
    firstName: "Brian",
    lastName: "Mwangi",
    role: "Fleet manager",
    permissions: ["dash.revenue", "revenue.view", "pettycash.spend"],
  },
  clerk: {
    userId: "u-wanjiru",
    firstName: "Wanjiru",
    lastName: "Kamau",
    role: "Revenue clerk",
    permissions: [
      "dash.capture",
      "dash.gaps",
      "revenue.view",
      "revenue.capture",
      "revenue.no_earnings",
    ],
  },
};

export const catalog = [
  {
    name: "Dashboard",
    items: [
      {
        key: "dash.capture",
        label: "See today's capture for my vehicles",
        needs: [],
      },
      { key: "dash.revenue", label: "See revenue totals", needs: [] },
    ],
  },
  {
    name: "Revenue",
    items: [
      { key: "revenue.view", label: "View revenue records", needs: [] },
      {
        key: "revenue.capture",
        label: "Capture revenue",
        needs: ["revenue.view"],
      },
      {
        key: "revenue.no_earnings",
        label: "Record a no earnings reason",
        needs: ["revenue.capture"],
      },
      {
        key: "revenue.correct",
        label: "Correct revenue after the day",
        needs: ["revenue.view"],
      },
    ],
  },
  {
    name: "Setup",
    items: [
      { key: "companies.manage", label: "Set up PSV companies", needs: [] },
      { key: "people.view", label: "View people", needs: [] },
    ],
  },
];

export const revenueWeek = {
  weekStart: "2026-09-28",
  weekThrough: "2026-10-04",
  currentWeekStart: "2026-09-28",
  businessDate: "2026-09-29",
  companies: [{ id: "company-1", name: "North Star" }],
  vehicles: [
    {
      id: "vehicle-1",
      companyId: "company-1",
      companyName: "North Star",
      registration: "KDA 482M",
      joinedOn: "2026-09-28",
      leftOn: null,
      earliestMissing: "2026-09-28",
      days: [
        {
          date: "2026-09-28",
          status: "missing",
          expected: 1000,
          amount: null,
          reason: null,
          note: null,
          canEdit: true,
          editedAfterCapture: false,
        },
        {
          date: "2026-09-29",
          status: "missing",
          expected: 1000,
          amount: null,
          reason: null,
          note: null,
          canEdit: true,
          editedAfterCapture: false,
        },
        {
          date: "2026-09-30",
          status: "future",
          expected: 1000,
          amount: null,
          reason: null,
          note: null,
          canEdit: false,
          editedAfterCapture: false,
        },
        {
          date: "2026-10-01",
          status: "future",
          expected: 1000,
          amount: null,
          reason: null,
          note: null,
          canEdit: false,
          editedAfterCapture: false,
        },
        {
          date: "2026-10-02",
          status: "future",
          expected: 1000,
          amount: null,
          reason: null,
          note: null,
          canEdit: false,
          editedAfterCapture: false,
        },
        {
          date: "2026-10-03",
          status: "future",
          expected: 1000,
          amount: null,
          reason: null,
          note: null,
          canEdit: false,
          editedAfterCapture: false,
        },
        {
          date: "2026-10-04",
          status: "future",
          expected: 1000,
          amount: null,
          reason: null,
          note: null,
          canEdit: false,
          editedAfterCapture: false,
        },
      ],
      totalAmount: 0,
      totalExpected: 2000,
      percent: 0,
    },
  ],
  totalAmount: 0,
  totalExpected: 2000,
  percent: 0,
};

export const revenueDashboard = {
  period: "week",
  from: "2026-09-28",
  through: "2026-09-29",
  businessDate: "2026-09-29",
  revenue: 0,
  expected: 2000,
  percent: 0,
  capturedToday: 0,
  vehiclesToday: 1,
  missingDays: 1,
  missingVehicles: 1,
  editedRecords: 0,
};

export const tokens = (n = 1) => ({
  status: "authenticated",
  accessToken: `access-${n}`,
  refreshToken: `refresh-${n}`,
});

export function fakeApi() {
  const routes = new Map<string, Handler>();
  const calls: {
    path: string;
    body: Record<string, string>;
    headers: Record<string, string>;
  }[] = [];
  const fetch = jest.fn(async (url: string, init: RequestInit = {}) => {
    const path = url.replace(/^https?:\/\/[^/]+\//, "");
    const body = init.body ? JSON.parse(String(init.body)) : {};
    const headers = (init.headers ?? {}) as Record<string, string>;
    calls.push({ path, body, headers });
    const answer = routes.get(path)?.(body, headers);
    const reply = (answer instanceof Promise ? await answer : answer) ?? [
      404,
      {},
    ];
    if (reply === "offline") throw new TypeError("Network request failed");
    const [status, json] = reply;
    return {
      ok: status >= 200 && status < 300,
      status,
      json: async () => json,
    } as Response;
  });
  globalThis.fetch = fetch as unknown as typeof globalThis.fetch;
  return {
    calls,
    on(path: string, handler: Handler | Reply) {
      routes.set(path, typeof handler === "function" ? handler : () => handler);
    },
    sent: (path: string) =>
      calls.filter((call) => call.path === path).map((call) => call.body),
  };
}
