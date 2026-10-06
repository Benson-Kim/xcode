export type RevenueStatus = "none" | "future" | "missing" | "amount" | "reason";

export const REVENUE_REASONS = ["Garage", "Arrest", "No Crew", "Other"] as const;
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

export function revenuePeriodLabel(period: RevenuePeriod): string {
  return REVENUE_PERIODS.find((option) => option.value === period)?.label ?? period;
}
