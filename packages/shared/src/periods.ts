// One period model for the ledger and the reports: {from, to, unit}, both days included. unit says how previous and
// next move: a day, a week, four weeks (one week at a time), a calendar month, or a custom span by its own length.

import { daysBetween, shiftDate, startOfWeek } from "./dates";

export type PeriodUnit = "day" | "week" | "fourWeeks" | "month" | "custom";

export interface Period {
  from: string;
  to: string;
  unit: PeriodUnit;
}

export type PeriodPreset =
  | "today"
  | "yesterday"
  | "thisWeek"
  | "lastWeek"
  | "lastFourWeeks"
  | "thisMonth"
  | "lastMonth";

export const PERIOD_PRESETS: readonly { id: PeriodPreset; label: string }[] = [
  { id: "today", label: "Today" },
  { id: "yesterday", label: "Yesterday" },
  { id: "thisWeek", label: "This week" },
  { id: "lastWeek", label: "Last week" },
  { id: "lastFourWeeks", label: "Last 4 weeks" },
  { id: "thisMonth", label: "This month" },
  { id: "lastMonth", label: "Last month" },
];

// The first day of the month `months` away from the month holding `date`.
function monthStart(date: string, months: number): string {
  const year = Number(date.slice(0, 4));
  const month = Number(date.slice(5, 7)) - 1 + months;
  const y = year + Math.floor(month / 12);
  const m = ((month % 12) + 12) % 12;
  return `${String(y).padStart(4, "0")}-${String(m + 1).padStart(2, "0")}-01`;
}

function calendarMonth(date: string, months: number): Period {
  const from = monthStart(date, months);
  return { from, to: shiftDate(monthStart(from, 1), -1), unit: "month" };
}

// Every preset counts from the organization's business date and its first day of the week (0 = Sunday).
export function presetPeriod(
  preset: PeriodPreset,
  businessDate: string,
  firstDayOfWeek: number,
): Period {
  const week = startOfWeek(businessDate, firstDayOfWeek);
  switch (preset) {
    case "today":
      return { from: businessDate, to: businessDate, unit: "day" };
    case "yesterday": {
      const day = shiftDate(businessDate, -1);
      return { from: day, to: day, unit: "day" };
    }
    case "thisWeek":
      return { from: week, to: shiftDate(week, 6), unit: "week" };
    case "lastWeek":
      return {
        from: shiftDate(week, -7),
        to: shiftDate(week, -1),
        unit: "week",
      };
    case "lastFourWeeks":
      return {
        from: shiftDate(week, -28),
        to: shiftDate(week, -1),
        unit: "fourWeeks",
      };
    case "thisMonth":
      return calendarMonth(businessDate, 0);
    case "lastMonth":
      return calendarMonth(businessDate, -1);
  }
}

// The preset a period is, if any, so a picker can show it as chosen.
export function matchingPreset(
  period: Pick<Period, "from" | "to">,
  businessDate: string,
  firstDayOfWeek: number,
): PeriodPreset | null {
  const hit = PERIOD_PRESETS.find(({ id }) => {
    const candidate = presetPeriod(id, businessDate, firstDayOfWeek);
    return candidate.from === period.from && candidate.to === period.to;
  });
  return hit?.id ?? null;
}

// Previous (-1) or next (+1) period of the same kind.
export function shiftPeriod(period: Period, direction: -1 | 1): Period {
  if (period.unit === "month") return calendarMonth(period.from, direction);
  const step =
    period.unit === "week" || period.unit === "fourWeeks"
      ? 7
      : daysBetween(period.from, period.to) + 1;
  return {
    from: shiftDate(period.from, direction * step),
    to: shiftDate(period.to, direction * step),
    unit: period.unit,
  };
}

// A custom period from two days, in either order.
export function customPeriod(a: string, b: string): Period {
  const [from, to] = a <= b ? [a, b] : [b, a];
  return { from, to, unit: from === to ? "day" : "custom" };
}

// Next is offered only while the next period starts on or before the business date.
export const canMoveNext = (period: Period, businessDate: string) =>
  shiftPeriod(period, 1).from <= businessDate;

export const periodDays = (period: Pick<Period, "from" | "to">) =>
  daysBetween(period.from, period.to) + 1;
