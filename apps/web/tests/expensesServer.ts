import type {
  ExpenseLedger,
  ExpenseLedgerRow,
  ExpenseOptions,
  ExpensePermissions,
} from "@xcode/shared/expenses";

import { fakeApi, type Reply, type Sent } from "./fakeApi";

export const BUSINESS_DATE = "2026-10-09";

export const row = (
  over: Partial<ExpenseLedgerRow> = {},
): ExpenseLedgerRow => ({
  id: "r1",
  source: "central",
  date: "2026-10-07",
  vehicleId: "v1",
  registration: "KDA 482M",
  expenseItemId: "i1",
  itemName: "Tyres",
  categoryName: "Garage and repairs",
  bucket: 1,
  units: 4,
  unitAmount: 3500,
  total: 14000,
  note: "Front pair",
  recordedByName: "Brian Mwangi",
  holderName: null,
  scheduleId: null,
  group: null,
  version: 3,
  canEdit: true,
  canRemove: true,
  ...over,
});

export const GROUPED = row({
  id: "r2",
  vehicleId: "v2",
  registration: "KDB 100X",
  expenseItemId: "i2",
  itemName: "Diesel",
  categoryName: "Fuel",
  date: "2026-10-08",
  units: 40,
  unitAmount: 187.5,
  total: 2500,
  note: null,
  group: { id: "g1", size: 3, total: 7500, units: 120, unitAmount: 62.5 },
  version: 1,
  canRemove: false,
});

export const PETTY = row({
  id: "r3",
  source: "pettycash",
  date: "2026-10-06",
  vehicleId: "v2",
  registration: "KDB 100X",
  expenseItemId: "i3",
  itemName: "Parking",
  categoryName: "Fees",
  units: 1,
  unitAmount: 300,
  total: 300,
  note: null,
  recordedByName: "Grace Wanjiru",
  holderName: "Grace Wanjiru",
  version: null,
  canEdit: false,
  canRemove: false,
});

export const SCHEDULED = row({
  id: "s1:2026-10-07:v1",
  source: "scheduled",
  date: "2026-10-07",
  expenseItemId: null,
  itemName: "Insurance",
  categoryName: null,
  units: 1,
  unitAmount: 1200,
  total: 1200,
  note: null,
  recordedByName: null,
  scheduleId: "s1",
  version: null,
  canEdit: false,
  canRemove: false,
});

export const ROWS = [row(), GROUPED, PETTY, SCHEDULED];

// n central rows on one day, newest first, each KES 100.
export const manyRows = (count: number) =>
  Array.from({ length: count }, (_, index) =>
    row({
      id: `m${index + 1}`,
      itemName: `Part ${index + 1}`,
      units: 1,
      unitAmount: 100,
      total: 100,
      note: null,
    }),
  );

export const OPTIONS: ExpenseOptions = {
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
      active: true,
    },
    {
      id: "v3",
      companyId: "c1",
      companyName: "Rongai Express",
      registration: "KDC 200Y",
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
      name: "Diesel",
      categoryId: "f",
      categoryName: "Fuel",
      bucket: 2,
    },
  ],
};

export const permissionsOf = (
  over: Partial<ExpensePermissions> = {},
): ExpensePermissions => ({ canRecord: true, canCorrect: false, ...over });

type Options = {
  rows?: ExpenseLedgerRow[];
  permissions?: ExpensePermissions;
  // Answers given to the first ledger requests instead of the ledger.
  failures?: Reply[];
};

const sum = (rows: ExpenseLedgerRow[]) =>
  Math.round(rows.reduce((total, entry) => total + entry.total, 0) * 100) / 100;

const queryOf = (sent: Sent) =>
  new URL(sent.path, "http://localhost").searchParams;

// The ledger endpoints of the API: a period, a source and a search narrow the rows, and the figures cover the period.
export function serveExpenses(options: Options = {}) {
  const api = fakeApi();
  const rows = options.rows ?? ROWS;
  const failures = [...(options.failures ?? [])];
  api.on("setup/expenses/ledger*", (sent) => {
    const failure = failures.shift();
    if (failure) return failure;
    const query = queryOf(sent);
    const from = query.get("from") ?? "";
    const to = query.get("to") ?? "";
    const inPeriod = rows.filter(
      (entry) => entry.date >= from && entry.date <= to,
    );
    const words = (query.get("q") ?? "")
      .toLowerCase()
      .split(/\s+/)
      .filter(Boolean);
    const matching = inPeriod.filter(
      (entry) =>
        (!query.get("source") || entry.source === query.get("source")) &&
        words.every((word) =>
          `${entry.registration} ${entry.itemName} ${entry.note ?? ""}`
            .toLowerCase()
            .includes(word),
        ),
    );
    const pageSize = Number(query.get("pageSize") ?? 100);
    const pageNumber = Number(query.get("page") ?? 1);
    const by = (source: string) =>
      sum(inPeriod.filter((entry) => entry.source === source));
    const ledger: ExpenseLedger = {
      businessDate: BUSINESS_DATE,
      from,
      to,
      permissions: options.permissions ?? permissionsOf(),
      figures: {
        total: sum(inPeriod),
        central: by("central"),
        pettyCash: by("pettycash"),
        scheduled: by("scheduled"),
      },
      items: matching.slice((pageNumber - 1) * pageSize, pageNumber * pageSize),
      pageNumber,
      pageSize,
      total: matching.length,
      amount: sum(matching),
    };
    return [200, ledger];
  });
  api.on("setup/expenses/options*", [200, OPTIONS]);
  api.on("POST setup/expenses/entries", [200, { ids: ["new1"], total: 0 }]);
  api.on("PUT setup/expenses/entries/*", [200, { id: "r1", version: 4 }]);
  api.on("POST setup/expenses/entries/*", [200, { id: "r1", version: 4 }]);
  return api;
}

export const ledgerReads = (api: ReturnType<typeof serveExpenses>) =>
  api.calls
    .filter(
      (call) =>
        call.method === "GET" && call.path.startsWith("setup/expenses/ledger"),
    )
    .map((call) => call.path);
