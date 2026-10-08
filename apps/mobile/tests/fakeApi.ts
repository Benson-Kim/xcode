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

export const pettyEntry = (over: Record<string, unknown> = {}) => ({
  id: "entry-1",
  kind: "expense",
  holderId: "u-brian",
  holderName: "Brian Mwangi",
  date: "2026-09-29",
  vehicleId: "vehicle-1",
  registration: "KDA 482M",
  expenseItemId: "item-1",
  expenseItemName: "Tyre repair",
  bucket: 2,
  units: 2,
  unitAmount: 750,
  total: 1500,
  payee: null,
  note: null,
  reimbursable: false,
  status: "waiting",
  sentBackNote: null,
  reviewedByName: null,
  reviewedAt: null,
  recordedByName: "Brian Mwangi",
  recordedAt: "2026-09-29T08:00:00Z",
  updatedAt: "2026-09-29T08:00:00Z",
  version: 1,
  canEdit: true,
  canRemove: true,
  canReview: false,
  aboveLimit: false,
  ...over,
});

export const pettyPermissions = (over: Record<string, unknown> = {}) => ({
  holderId: "u-brian",
  canSpend: true,
  canViewAll: false,
  canIssue: false,
  canIssueNegative: false,
  canApproveItem: false,
  canApproveDay: false,
  approvalLimit: null,
  ...over,
});

export const pettyOverview = (over: Record<string, unknown> = {}) => ({
  businessDate: "2026-09-29",
  date: "2026-09-29",
  permissions: pettyPermissions(),
  holders: [{ id: "u-brian", name: "Brian Mwangi", active: true }],
  period: "day",
  from: "2026-09-29",
  to: "2026-09-29",
  figures: {
    openingBalance: 5000,
    cashReceived: 1000,
    expenses: 1500,
    creditNotes: 0,
    moneyOut: 1500,
    closingBalance: 4500,
  },
  floats: [
    {
      holderId: "u-brian",
      name: "Brian Mwangi",
      active: true,
      cashReceived: 6000,
      creditNotes: 0,
      expenses: 1500,
      waiting: 1500,
      waitingCount: 1,
      approved: 0,
      sentBack: 0,
      balance: 4500,
      lastCashOn: "2026-09-28",
    },
  ],
  ...over,
});

export const pettyOptions = {
  vehicles: [
    {
      id: "vehicle-1",
      companyId: "company-1",
      companyName: "North Star",
      registration: "KDA 482M",
      active: true,
    },
    {
      id: "vehicle-2",
      companyId: "company-1",
      companyName: "North Star",
      registration: "KDB 100X",
      active: true,
    },
  ],
  items: [
    {
      id: "item-1",
      name: "Tyre repair",
      categoryId: "cat-1",
      categoryName: "Repairs",
      bucket: 2,
    },
    {
      id: "item-2",
      name: "Diesel",
      categoryId: "cat-2",
      categoryName: "Running",
      bucket: 1,
    },
  ],
  holders: [
    { id: "u-brian", name: "Brian Mwangi", active: true },
    { id: "u-grace", name: "Grace Njeri", active: true },
  ],
};

export const pettyPage = (items: unknown[], total = items.length) => ({
  items,
  pageNumber: 1,
  pageSize: 100,
  total,
});

export const tokens = (n = 1) => ({
  status: "authenticated",
  accessToken: `access-${n}`,
  refreshToken: `refresh-${n}`,
});

export function fakeApi() {
  const routes = new Map<string, Handler>();
  const calls: {
    path: string;
    method: string;
    body: Record<string, string>;
    headers: Record<string, string>;
  }[] = [];
  const fetch = jest.fn(async (url: string, init: RequestInit = {}) => {
    const path = url.replace(/^https?:\/\/[^/]+\//, "");
    const body = init.body ? JSON.parse(String(init.body)) : {};
    const headers = (init.headers ?? {}) as Record<string, string>;
    calls.push({ path, method: init.method ?? "GET", body, headers });
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
