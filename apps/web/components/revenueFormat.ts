import {
  calendarDate,
  dayOfMonth as calendarDayOfMonth,
  shiftDate,
  weekdayShortName,
} from "@xcode/shared/dates";
import type { Formatter } from "@xcode/shared/format";

// Revenue dates are the organization's business dates ("2026-09-28"). They are only ever read from the API,
// never from the computer clock, and are handled as UTC calendar days.

export { shiftDate };

export const weekday = weekdayShortName;

export const dayOfMonth = (iso: string) => String(calendarDayOfMonth(iso));

export const shortDate = (formats: Formatter, iso: string) =>
  formats.formatDate(calendarDate(iso));

// "Mon 28 Sep 2026"
export const longDate = (formats: Formatter, iso: string) =>
  `${weekday(iso)} ${shortDate(formats, iso)}`;

// A figure without its currency, as the week grid shows amounts ("1,250").
export const figure = (formats: Formatter, value: number) =>
  formats.kes(value).slice(formats.currencyCode().length + 1);

// Words, not a minus sign: "KES 1,200 below", "KES 350 above", "On target".
export function difference(
  formats: Formatter,
  actual: number,
  expected: number,
) {
  const gap = Math.round((actual - expected) * 100) / 100;
  return gap === 0
    ? "On target"
    : `${formats.kes(Math.abs(gap))} ${gap > 0 ? "above" : "below"}`;
}
