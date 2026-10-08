export const REVENUE_STATUSES = [
  "none",
  "future",
  "missing",
  "amount",
  "reason",
] as const;
export type RevenueStatus = (typeof REVENUE_STATUSES)[number];

export type StatusTone = "muted" | "normal" | "alert";

export interface StatusMeta {
  // In service that day: counts toward "x of y captured" and has an expected figure.
  inFleet: boolean;
  // Holds an amount or a no-revenue reason.
  recorded: boolean;
  // Still needs a record.
  awaitsCapture: boolean;
  // What a cell with nothing else to show says.
  label: string;
  tone: StatusTone;
}

export const STATUS_META: Record<RevenueStatus, StatusMeta> = {
  none: {
    inFleet: false,
    recorded: false,
    awaitsCapture: false,
    label: "Not counted",
    tone: "muted",
  },
  future: {
    inFleet: true,
    recorded: false,
    awaitsCapture: false,
    label: "Not yet",
    tone: "muted",
  },
  missing: {
    inFleet: true,
    recorded: false,
    awaitsCapture: true,
    label: "Missing",
    tone: "alert",
  },
  amount: {
    inFleet: true,
    recorded: true,
    awaitsCapture: false,
    label: "Recorded",
    tone: "normal",
  },
  reason: {
    inFleet: true,
    recorded: true,
    awaitsCapture: false,
    label: "No revenue",
    tone: "normal",
  },
};

export const isRecorded = (cell?: Pick<RevenueCell, "status">): boolean =>
  Boolean(cell && STATUS_META[cell.status].recorded);

export const awaitsCapture = (cell?: Pick<RevenueCell, "status">): boolean =>
  Boolean(cell && STATUS_META[cell.status].awaitsCapture);

export const REVENUE_REASONS = [
  "Garage",
  "Arrest",
  "No Crew",
  "Other",
] as const;
export type RevenueReason = (typeof REVENUE_REASONS)[number];

export const REVENUE_NOTE_LIMIT = 80;

export const REVENUE_AMOUNT_ERROR =
  "Enter the revenue as a positive amount with at most two decimals.";

export type RevenueAmountResult =
  | { ok: true; amount: number | null }
  | { ok: false; error: typeof REVENUE_AMOUNT_ERROR };

const PLAIN_AMOUNT = /^\d{1,12}(\.\d{1,2})?$/;
const GROUPED_AMOUNT = /^\d{1,3}(,\d{3})+(\.\d{1,2})?$/;

export function parseRevenueAmount(value: string): RevenueAmountResult {
  const trimmed = value.replace(/\s/g, "");
  if (!trimmed || /^,+$/.test(trimmed)) return { ok: true, amount: null };
  if (!PLAIN_AMOUNT.test(trimmed) && !GROUPED_AMOUNT.test(trimmed))
    return { ok: false, error: REVENUE_AMOUNT_ERROR };
  const num = Number(trimmed.replace(/,/g, ""));
  if (num <= 0) return { ok: false, error: REVENUE_AMOUNT_ERROR };
  return { ok: true, amount: num };
}

export interface RevenueCompanyOption {
  id: string;
  name: string;
}

export interface RevenueCell {
  date: string;
  status: RevenueStatus;
  expected: number;
  amount: number | null;
  reason: string | null;
  note: string | null;
  canEdit: boolean;
  editedAfterCapture: boolean;
  version?: number | null;
}

export interface RevenueVehicle {
  id: string;
  companyId: string;
  companyName: string;
  registration: string;
  joinedOn: string;
  leftOn: string | null;
  earliestMissing: string | null;
  days: RevenueCell[];
  totalAmount: number;
  totalExpected: number;
  percent: number | null;
}

export interface RevenueDayTotal {
  date: string;
  amount: number;
  expected: number;
}

export interface RevenueGap {
  vehicleId: string;
  date: string;
}

// The totals, day totals and first gap cover the whole grid; vehicles may be one page of it. The paging fields are
// absent from a week rebuilt on the phone from its saved capture list.
export interface RevenueWeek {
  weekStart: string;
  weekThrough: string;
  currentWeekStart: string;
  businessDate: string;
  companies: RevenueCompanyOption[];
  vehicles: RevenueVehicle[];
  totalAmount: number;
  totalExpected: number;
  percent: number | null;
  pageNumber?: number;
  pageSize?: number;
  totalVehicles?: number;
  truncated?: boolean;
  dayTotals?: RevenueDayTotal[];
  firstGap?: RevenueGap | null;
}

export const REVENUE_WEEK_PAGE_SIZE = 100;

// A week asked for without paging lists the grid up to the API's limit and says when it stopped there. The pages
// still to fetch, at REVENUE_WEEK_PAGE_SIZE vehicles each, carry on from the last vehicle listed.
export function remainingWeekPages(week: RevenueWeek): number[] {
  if (!week.truncated || !week.totalVehicles) return [];
  const from = Math.floor(week.vehicles.length / REVENUE_WEEK_PAGE_SIZE) + 1;
  const last = Math.ceil(week.totalVehicles / REVENUE_WEEK_PAGE_SIZE);
  return Array.from(
    { length: Math.max(last - from + 1, 0) },
    (_, index) => from + index,
  );
}

// The whole grid from its first response and the pages after it. A vehicle listed twice (the fleet changed between
// requests) is kept once.
export function mergeWeekPages(
  first: RevenueWeek,
  rest: RevenueWeek[],
): RevenueWeek {
  if (rest.length === 0) return first;
  const seen = new Set<string>();
  const vehicles = [first, ...rest]
    .flatMap((page) => page.vehicles)
    .filter(
      (vehicle) => !seen.has(vehicle.id) && Boolean(seen.add(vehicle.id)),
    );
  return { ...first, vehicles, truncated: false };
}

// Each figure is null for a viewer who may not see the card it belongs to.
export interface RevenueDashboard {
  period: RevenuePeriod;
  from: string;
  through: string;
  businessDate: string;
  revenue: number | null;
  expected: number | null;
  percent: number | null;
  capturedToday: number | null;
  vehiclesToday: number | null;
  missingDays: number | null;
  missingVehicles: number | null;
  editedRecords: number | null;
}

export interface SaveRevenue {
  amount: number | null;
  reason: RevenueReason | null;
  note: string | null;
  version?: number | null;
}

export const REVENUE_PERIODS = [
  { value: "today", label: "Today" },
  { value: "week", label: "This week" },
  { value: "month", label: "This month" },
] as const;

export type RevenuePeriod = (typeof REVENUE_PERIODS)[number]["value"];

export const REVENUE_REPORT_PERIODS = [
  REVENUE_PERIODS[1],
  REVENUE_PERIODS[2],
] as const;

export type RevenueReportPeriod =
  (typeof REVENUE_REPORT_PERIODS)[number]["value"];

const REVENUE_PERIOD_LABELS = new Map<string, string>(
  REVENUE_PERIODS.map(({ value, label }) => [value, label]),
);

export function revenuePeriodLabel(period: RevenuePeriod): string {
  return REVENUE_PERIOD_LABELS.get(period) ?? period;
}
