import { currencyCode, datePattern, formatDate, kes } from "../lib/format";

// Revenue dates are the organization's business dates ("2026-09-28"). They are only ever read from the API,
// never from the computer clock, and are handled as UTC calendar days.

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

const calendarDay = (iso: string) => new Date(`${iso}T00:00:00Z`);

export function shiftDate(iso: string, days: number) {
  const date = calendarDay(iso);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

export const weekday = (iso: string) => WEEKDAYS[calendarDay(iso).getUTCDay()];

export const dayOfMonth = (iso: string) => String(calendarDay(iso).getUTCDate());

export const shortDate = (iso: string) => formatDate(calendarDay(iso));

// "Mon 28 Sep 2026"
export const longDate = (iso: string) => `${weekday(iso)} ${shortDate(iso)}`;

// "28 Sep to 4 Oct 2026" and "1 to 29 Sep 2026", as the design writes a range; other date formats give both dates.
export function rangeLabel(from: string, through: string) {
  if (datePattern() !== "medium") return `${shortDate(from)} to ${shortDate(through)}`;
  const start = calendarDay(from);
  const end = calendarDay(through);
  const first =
    start.getUTCFullYear() !== end.getUTCFullYear()
      ? shortDate(from)
      : start.getUTCMonth() !== end.getUTCMonth()
        ? shortDate(from).replace(/ \d+$/, "")
        : dayOfMonth(from);
  return `${first} to ${shortDate(through)}`;
}

// A figure without its currency, as the week grid shows amounts ("1,250").
export const figure = (value: number) => kes(value).slice(currencyCode().length + 1);

// Words, not a minus sign: "KES 1,200 below", "KES 350 above", "On target".
export function difference(actual: number, expected: number) {
  const gap = Math.round((actual - expected) * 100) / 100;
  return gap === 0 ? "On target" : `${kes(Math.abs(gap))} ${gap > 0 ? "above" : "below"}`;
}
