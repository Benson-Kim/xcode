import { PETTY_CASH_PERMISSIONS } from "./pettyCash";

// Keep PERMISSION_KEYS equal to PermissionCatalog (apps/api/Application/AccessContracts.cs); tests/api/PermissionKeysTests.cs fails on drift.
export const PERMISSION_KEYS = [
  "dash.capture",
  "dash.float",
  "dash.revenue",
  "dash.net",
  "dash.costs",
  "dash.gaps",
  "dash.pettycash",
  "dash.commitments",
  "dash.investment",
  "dash.edits",
  "revenue.view",
  "revenue.capture",
  "revenue.no_earnings",
  "revenue.correct",
  "expenses.view",
  "expenses.capture",
  "expenses.correct",
  "expenses.setup",
  "pettycash.spend",
  "pettycash.view_all",
  "pettycash.approve_item",
  "pettycash.approve_day",
  "pettycash.issue",
  "pettycash.issue_negative",
  "bills.view",
  "bills.capture",
  "bills.approve",
  "commitments.view",
  "commitments.manage",
  "reports.view",
  "reports.export",
  "companies.manage",
  "vehicles.manage",
  "invest.view",
  "invest.manage",
  "people.view",
  "people.manage",
  "access.manage",
  "audit.view",
  "organization.manage",
] as const;

export type PermissionKey = (typeof PERMISSION_KEYS)[number];

export type PermissionCheck = (key: PermissionKey) => boolean;

export const permissionChecker = (held: readonly string[]): PermissionCheck => {
  const set = new Set(held);
  return (key) => set.has(key);
};

// The catalog is server data, so its keys stay strings: a newer API may send a key this build does not know.
export type PermissionItem = { key: string; label: string; needs: string[] };
export type PermissionGroup = { name: string; items: PermissionItem[] };

// Without `any` the item is for everyone; with an empty `any` it is for nobody.
export type NavRule = {
  readonly label?: string;
  readonly any?: readonly PermissionKey[];
};

export const canSee = (rule: NavRule, can: PermissionCheck): boolean =>
  rule.any === undefined || rule.any.some(can);

export const NAV = {
  dashboard: { label: "Dashboard" },
  revenue: { label: "Revenue", any: ["revenue.view"] },
  centralexpenses: { label: "Central expenses", any: ["expenses.view"] },
  reports: { label: "Reports", any: ["reports.view"] },
  pettycash: { label: "Petty cash", any: PETTY_CASH_PERMISSIONS },
  companies: { label: "PSV companies", any: ["companies.manage"] },
  vehicles: { label: "Vehicles", any: ["vehicles.manage", "invest.view"] },
  expenses: {
    label: "Expense categories",
    any: ["expenses.setup", "expenses.view", "commitments.view"],
  },
  recurring: {
    label: "Scheduled expenses and savings",
    any: ["commitments.view"],
  },
  people: { label: "People and access", any: ["people.view"] },
  history: { label: "Change log", any: ["audit.view"] },
  settings: { label: "Organization settings", any: ["organization.manage"] },
} as const satisfies Record<string, NavRule & { label: string }>;

export type NavId = keyof typeof NAV;

export const PRIMARY_NAV = [
  "dashboard",
  "revenue",
] as const satisfies readonly NavId[];

export const EXPENSES_NAV = [
  "centralexpenses",
  "pettycash",
  "recurring",
] as const satisfies readonly NavId[];

export const SETUP_NAV = [
  "companies",
  "vehicles",
  "expenses",
  "people",
  "history",
  "settings",
] as const satisfies readonly NavId[];

export type NavSection =
  | { kind: "items"; items: readonly NavId[] }
  | { kind: "group"; id: string; label: string; items: readonly NavId[] };

// The menu top to bottom: loose items, or a collapsible group with its own heading.
export const NAV_SECTIONS: readonly NavSection[] = [
  { kind: "items", items: PRIMARY_NAV },
  { kind: "group", id: "expenses", label: "Expenses", items: EXPENSES_NAV },
  { kind: "items", items: ["reports"] },
  { kind: "group", id: "setup", label: "Setup", items: SETUP_NAV },
];

export const DASHBOARD_CARDS = [
  { permission: "dash.capture", title: "Today's revenue" },
  { permission: "dash.float", title: "My petty cash float" },
  { permission: "dash.revenue", title: "Revenue" },
  { permission: "dash.net", title: "Net contribution" },
  { permission: "dash.costs", title: "Money out" },
  { permission: "dash.gaps", title: "Missing revenue days" },
  { permission: "dash.pettycash", title: "Petty cash to approve" },
  { permission: "dash.commitments", title: "Yearly items due" },
  { permission: "dash.investment", title: "Money invested" },
  { permission: "dash.edits", title: "Edited after capture" },
] as const satisfies readonly { permission: PermissionKey; title: string }[];

export type DashboardKey = (typeof DASHBOARD_CARDS)[number]["permission"];

export const startsOnToday = (can: PermissionCheck) =>
  can("dash.capture") || can("dash.float");
