import {
  calendarDate,
  compactDateRange,
  MONTH_NAMES,
  weekDays,
} from "@xcode/shared/dates";
import {
  fuelTag,
  STATUS_META,
  type RevenueCell,
  type RevenueVehicle,
  type RevenueWeek,
} from "@xcode/shared/revenue";

import { safeFileName } from "../reports/exportReport";

// The Revenue bar's Low days, Not fueled and Missing days: the API's figures for the filtered week, or, from an API
// that does not send them, counted from the grid (a low day holds a reason; a Not fueled day has an amount tagged
// "no"; a missing day is a cell awaiting capture).
export function weekCounts(week: RevenueWeek) {
  let low = 0;
  let notFueled = 0;
  let missing = 0;
  for (const vehicle of week.vehicles)
    for (const day of vehicle.days) {
      if (day.status === "amount" && fuelTag(day.fuel)) notFueled++;
      if (day.status === "reason" || (day.status === "amount" && day.reason))
        low++;
      else if (day.status === "missing") missing++;
    }
  return {
    low: week.belowThresholdDays ?? low,
    notFueled: week.notFueledDays ?? notFueled,
    missing: week.missingDays ?? missing,
  };
}

// Pixel geometry of the summary image (v2.45): a header about a tenth of the picture, then a card holding the table,
// one row a vehicle and the Total row.
export const SUMMARY_GEOMETRY = {
  width: 1200,
  pad: 40,
  header: 124,
  cardTop: 152,
  tableTop: 236,
  row: 88,
  foot: 56,
} as const;

export type SummaryCellState =
  "amount" | "reason" | "missing" | "due" | "blank";

export type SummaryCell = {
  state: SummaryCellState;
  text: string;
  // Small type under an amount: the reason of a low day, or else "Not fueled" (v2.36).
  note: string | null;
  // The note is the Not fueled tag, drawn grey rather than amber.
  fuelNote?: true;
};

export type SummaryDay = {
  date: string;
  weekday: string;
  day: string;
  today: boolean;
};

export type SummaryRow = {
  registration: string;
  // "2 missing" when past days have no record.
  missing: string | null;
  cells: SummaryCell[];
  total: string;
};

export type SummaryLayout = {
  title: string;
  period: string;
  subtitle: string;
  figures: { label: string; value: string; alert: boolean }[];
  days: SummaryDay[];
  rows: SummaryRow[];
  dayTotals: (string | null)[];
  total: string;
  fileName: string;
  width: number;
  height: number;
};

const TITLE = "Weekly Performance";

// "4 to 10 October 2026", "28 September to 4 October 2026", "29 December 2025 to 4 January 2026".
export function summaryPeriod(from: string, through: string) {
  const long = (value: string) => {
    const date = calendarDate(value);
    return `${date.getUTCDate()} ${MONTH_NAMES[date.getUTCMonth()]} ${date.getUTCFullYear()}`;
  };
  return compactDateRange(from, through, long);
}

export const summaryHeight = (rows: number) =>
  SUMMARY_GEOMETRY.tableTop +
  (Math.max(rows, 1) + 1) * SUMMARY_GEOMETRY.row +
  SUMMARY_GEOMETRY.foot;

// A day as the grid shows it: the amount with a low day's reason or else "Not fueled" under it, a reason alone, "Missing" for a past day
// with no record, "Due" for today with none; nothing for a future day or one the vehicle was not in the fleet.
function summaryCell(
  cell: RevenueCell | undefined,
  today: string,
  formatNumber: (amount: number) => string,
): SummaryCell {
  if (!cell) return { state: "blank", text: "", note: null };
  const meta = STATUS_META[cell.status];
  if (meta.recorded) {
    if (cell.amount === null)
      return { state: "reason", text: cell.reason ?? "", note: null };
    const text = formatNumber(cell.amount);
    if (cell.reason) return { state: "amount", text, note: cell.reason };
    const fuel = fuelTag(cell.fuel);
    return fuel
      ? { state: "amount", text, note: fuel, fuelNote: true }
      : { state: "amount", text, note: null };
  }
  if (meta.awaitsCapture)
    return cell.date === today
      ? { state: "due", text: "Due", note: null }
      : { state: "missing", text: "Missing", note: null };
  return { state: "blank", text: "", note: null };
}

function summaryRow(
  vehicle: RevenueVehicle,
  days: string[],
  today: string,
  formatNumber: (amount: number) => string,
): SummaryRow {
  const byDate = new Map(vehicle.days.map((cell) => [cell.date, cell]));
  const cells = days.map((date) =>
    summaryCell(byDate.get(date), today, formatNumber),
  );
  const missing = cells.filter((cell) => cell.state === "missing").length;
  return {
    registration: vehicle.registration,
    missing: missing ? `${missing} missing` : null,
    cells,
    total: formatNumber(vehicle.totalAmount),
  };
}

function dayAmounts(week: RevenueWeek, days: string[]) {
  const sent = new Map(week.dayTotals?.map((day) => [day.date, day.amount]));
  return days.map(
    (date) =>
      sent.get(date) ??
      week.vehicles.reduce((sum, vehicle) => {
        const cell = vehicle.days.find((day) => day.date === date);
        return (
          sum +
          (cell && STATUS_META[cell.status].recorded ? (cell.amount ?? 0) : 0)
        );
      }, 0),
  );
}

// The summary image of the week on screen (Web v2.40 to v2.45), from the same figures as the Revenue bar and grid:
// the vehicles in view (company filter and search applied) highest revenue first, one column a day in the grid's
// order, the Week total, and a Total row that alone carries the week's revenue. Nothing is worked out anew.
export function summaryLayout(
  week: RevenueWeek,
  companyId: string,
  formatNumber: (amount: number) => string,
): SummaryLayout {
  const today = week.businessDate;
  const days = weekDays(week.weekStart);
  const dates = days.map((day) => day.date);
  const period = summaryPeriod(week.weekStart, week.weekThrough);
  const company = companyId
    ? week.companies.find((option) => option.id === companyId)?.name
    : undefined;
  const counts = weekCounts(week);
  const rows = [...week.vehicles]
    .sort(
      (a, b) =>
        b.totalAmount - a.totalAmount ||
        (a.registration < b.registration
          ? -1
          : a.registration > b.registration
            ? 1
            : 0),
    )
    .map((vehicle) => summaryRow(vehicle, dates, today, formatNumber));
  return {
    title: TITLE,
    period,
    subtitle: company ? `${period}, ${company}` : period,
    figures: [
      {
        label: "Missing days",
        value: String(counts.missing),
        alert: counts.missing > 0,
      },
      { label: "Low days", value: String(counts.low), alert: false },
    ],
    days: days.map((day) => ({
      date: day.date,
      weekday: day.shortName,
      day: String(day.dayOfMonth),
      today: day.date === today,
    })),
    rows,
    dayTotals: dayAmounts(week, dates).map((amount, index) =>
      amount || dates[index]! < today ? formatNumber(amount) : null,
    ),
    total: formatNumber(week.totalAmount),
    fileName: `${safeFileName(`${TITLE}, ${period}`)}.png`,
    width: SUMMARY_GEOMETRY.width,
    height: summaryHeight(rows.length),
  };
}
