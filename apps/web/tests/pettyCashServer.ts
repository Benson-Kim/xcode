import { vi } from "vitest";

import { shiftDate, startOfWeek } from "@xcode/shared/dates";
import type {
  PettyCashDashboard,
  PettyCashEntry,
  PettyCashFloat,
  PettyCashOptions,
  PettyCashOverview,
  PettyCashPeriod,
  PettyCashPermissions,
  PettyCashVehicleOption,
} from "@xcode/shared/pettyCash";

import { appearanceFixture } from "./renderInApp";

export const BUSINESS_DATE = "2026-09-30";

export const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });

export const permissionsOf = (
  over: Partial<PettyCashPermissions> = {},
): PettyCashPermissions => ({
  holderId: "h1",
  canSpend: true,
  canViewAll: false,
  canIssue: false,
  canIssueNegative: false,
  canApproveItem: false,
  canApproveDay: false,
  approvalLimit: null,
  canView: true,
  canSpendOther: false,
  canEditOwn: false,
  canEdit: false,
  canDeleteOwn: false,
  canDelete: false,
  canDeleteApproved: false,
  canSendBack: false,
  canReject: false,
  canReopen: false,
  canCredit: false,
  canDeleteCash: false,
  earliestDate: null,
  ...over,
});

// The shared status type does not list "rejected" yet; the wire does.
export const REJECTED: PettyCashEntry["status"] = "rejected";

export const expense = (
  over: Partial<PettyCashEntry> = {},
): PettyCashEntry => ({
  id: "e1",
  kind: "expense",
  holderId: "h1",
  holderName: "Grace Wanjiru",
  date: BUSINESS_DATE,
  vehicleId: "v1",
  registration: "KDA 482M",
  expenseItemId: "i1",
  expenseItemName: "Tyres",
  bucket: 1,
  units: 1,
  unitAmount: 3500,
  total: 3500,
  payee: null,
  note: null,
  reimbursable: false,
  status: "waiting",
  sentBackNote: null,
  reviewedByName: null,
  reviewedAt: null,
  recordedByName: "Grace Wanjiru",
  recordedAt: "2026-09-30T08:00:00Z",
  updatedAt: "2026-09-30T08:00:00Z",
  version: 3,
  canEdit: false,
  canRemove: false,
  canReview: false,
  aboveLimit: false,
  rejectReason: null,
  reopenReason: null,
  canSendBack: false,
  canReject: false,
  canReopen: false,
  ...over,
});

export const credit = (over: Partial<PettyCashEntry> = {}): PettyCashEntry =>
  expense({
    id: "c1",
    kind: "credit",
    vehicleId: null,
    registration: null,
    expenseItemId: null,
    expenseItemName: null,
    bucket: null,
    unitAmount: 800,
    total: 800,
    payee: "Mama Njeri",
    note: "Refund for a double charge",
    ...over,
  });

export const cash = (over: Partial<PettyCashEntry> = {}): PettyCashEntry =>
  expense({
    id: "k1",
    kind: "cash",
    vehicleId: null,
    registration: null,
    expenseItemId: null,
    expenseItemName: null,
    bucket: null,
    unitAmount: 5000,
    total: 5000,
    status: null,
    recordedByName: "Office",
    ...over,
  });

type ServedOptions = Omit<PettyCashOptions, "vehicles"> & {
  vehicles: (PettyCashVehicleOption & { fleetNumber?: string })[];
};

export const OPTIONS: ServedOptions = {
  vehicles: [
    {
      id: "v1",
      companyId: "c1",
      companyName: "Rongai Express",
      registration: "KDA 482M",
      active: true,
    },
    {
      id: "v2",
      companyId: "c1",
      companyName: "Rongai Express",
      registration: "KDB 100X",
      fleetNumber: "7",
      active: true,
    },
  ],
  items: [
    {
      id: "i1",
      name: "Tyres",
      categoryId: "g",
      categoryName: "Garage and repairs",
      bucket: 1,
    },
    {
      id: "i2",
      name: "Brake pads",
      categoryId: "g",
      categoryName: "Garage and repairs",
      bucket: 1,
    },
    {
      id: "i3",
      name: "Parking",
      categoryId: "f",
      categoryName: "Fees",
      bucket: 2,
    },
  ],
  holders: [
    { id: "h1", name: "Grace Wanjiru", active: true },
    { id: "h2", name: "Peter Otieno", active: true },
  ],
};

export const DAY_FIGURES = {
  openingBalance: 12000,
  cashReceived: 5000,
  expenses: 3500,
  creditNotes: 500,
  moneyOut: 4000,
  closingBalance: 13000,
  waiting: 3500,
  waitingCount: 1,
};
export const WEEK_FIGURES = {
  openingBalance: 9000,
  cashReceived: 21000,
  expenses: 14000,
  creditNotes: 2000,
  moneyOut: 16000,
  closingBalance: 14000,
  waiting: 9000,
  waitingCount: 3,
};

// The first day of the week is Monday, as in the appearance fixture.
export function overviewOf(
  permissions: PettyCashPermissions,
  date = BUSINESS_DATE,
  over: Partial<PettyCashOverview> = {},
  period: PettyCashPeriod = "day",
): PettyCashOverview {
  const from = period === "week" ? startOfWeek(date, 1) : date;
  return {
    businessDate: BUSINESS_DATE,
    date,
    period,
    from,
    to: period === "week" ? shiftDate(from, 6) : date,
    permissions,
    holders: OPTIONS.holders,
    figures: period === "week" ? WEEK_FIGURES : DAY_FIGURES,
    floats: [
      {
        holderId: "h1",
        name: "Grace Wanjiru",
        active: true,
        cashReceived: 20000,
        creditNotes: 500,
        expenses: 7000,
        waiting: 3500,
        waitingCount: 1,
        approved: 4000,
        sentBack: 0,
        balance: 12500,
        lastCashOn: "2026-09-29",
      },
    ],
    ...over,
  };
}

type Answer = Response | Promise<Response> | undefined;

type Options = {
  permissions?: PettyCashPermissions;
  entries?: PettyCashEntry[];
  floats?: PettyCashFloat[];
  dashboard?: PettyCashDashboard;
  // The session's permission keys; answering them turns the server into one the app shell can sign in to.
  session?: string[];
  answer?: (path: string, init: RequestInit | undefined) => Answer;
};

const DECISIONS = /^entries\/([^/]+)\/(send-back|reject|reopen|remove)$/;

// What send back, reject, reopen and remove do to an entry, so the list read after them shows it.
function decide(
  rows: PettyCashEntry[],
  id: string,
  action: string,
  body: { comment?: string; reason?: string },
) {
  const at = rows.findIndex((row) => row.id === id);
  if (at < 0) return;
  const row = rows[at];
  if (action === "remove") return void rows.splice(at, 1);
  const next = { ...row, version: row.version + 1 };
  if (action === "send-back") {
    next.status = "sentBack";
    next.sentBackNote = body.comment ?? null;
  } else if (action === "reject") {
    Object.assign(next, { status: "rejected", rejectReason: body.reason });
  } else {
    Object.assign(next, {
      status: "waiting",
      sentBackNote: null,
      rejectReason: null,
      reopenReason: body.reason,
    });
  }
  rows[at] = next;
}

// Answers the petty cash endpoints. A write is answered `{ id, version: 4, status: "waiting", balance: 0 }` unless `answer` says otherwise.
// Send back, reject, reopen and remove also change the entry they name.
export function servePettyCash(options: Options = {}) {
  const permissions = options.permissions ?? permissionsOf();
  const rows = [...(options.entries ?? [])];
  const fetcher = vi.fn(
    async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      const custom = options.answer?.(path, init);
      if (custom) return custom;
      if (options.session && path === "/api/auth/session")
        return json({
          userId: "me",
          firstName: "Test",
          lastName: "User",
          role: "Owner",
          permissions: options.session,
        });
      if (options.session && path === "/api/setup/appearance")
        return json(appearanceFixture(BUSINESS_DATE));
      const url = new URL(path, "http://localhost");
      const method = (init?.method ?? "GET").toUpperCase();
      if (!url.pathname.startsWith("/api/setup/pettycash/"))
        return json({}, 404);
      const route = url.pathname.slice("/api/setup/pettycash/".length);
      if (method !== "GET") {
        const decision = DECISIONS.exec(route);
        if (decision)
          decide(
            rows,
            decision[1],
            decision[2],
            JSON.parse(String(init?.body ?? "{}")),
          );
        return json({ id: "saved", version: 4, status: "waiting", balance: 0 });
      }
      if (route === "overview") {
        const from = url.searchParams.get("from");
        const to = url.searchParams.get("to");
        if (from && to)
          return json(
            overviewOf(
              permissions,
              to,
              {
                ...(options.floats ? { floats: options.floats } : {}),
                from,
                to,
                period: from === to ? "day" : "range",
                figures: from === to ? DAY_FIGURES : WEEK_FIGURES,
              },
              "day",
            ),
          );
        const period =
          url.searchParams.get("period") === "week" ? "week" : "day";
        return json(
          overviewOf(
            permissions,
            url.searchParams.get("date") ?? BUSINESS_DATE,
            options.floats ? { floats: options.floats } : {},
            period,
          ),
        );
      }
      if (route === "options") return json(OPTIONS);
      if (route === "dashboard")
        return json(options.dashboard ?? { float: null, approvals: null });
      if (route === "entries") {
        const kinds = url.searchParams.get("kind")?.split(",");
        const status = url.searchParams.get("status");
        const from = url.searchParams.get("from");
        const to = url.searchParams.get("to");
        const items = rows.filter(
          (entry) =>
            (!kinds || kinds.includes(entry.kind)) &&
            (!status || entry.status === status) &&
            (!from || entry.date >= from) &&
            (!to || entry.date <= to),
        );
        const pageSize = Number(url.searchParams.get("pageSize") ?? 100);
        const pageNumber = Number(url.searchParams.get("page") ?? 1);
        return json({
          items: items.slice(
            (pageNumber - 1) * pageSize,
            pageNumber * pageSize,
          ),
          pageNumber,
          pageSize,
          total: items.length,
        });
      }
      return json({}, 404);
    },
  );
  vi.stubGlobal("fetch", fetcher);
  return fetcher;
}

export const paths = (
  fetcher: ReturnType<typeof servePettyCash>,
  method = "GET",
) =>
  fetcher.mock.calls
    .filter(
      ([, init]) =>
        ((init as RequestInit | undefined)?.method ?? "GET").toUpperCase() ===
        method,
    )
    .map(([input]) => String(input));

export const writes = (fetcher: ReturnType<typeof servePettyCash>) =>
  fetcher.mock.calls
    .filter(([, init]) => (init as RequestInit | undefined)?.method)
    .map(([input, init]) => ({
      path: String(input),
      method: (init as RequestInit).method,
      body: JSON.parse(String((init as RequestInit).body)),
    }));
