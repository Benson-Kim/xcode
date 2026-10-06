// Revenue days are the organization's calendar dates ("yyyy-MM-dd"), worked out in UTC so the phone's own
// clock and time zone never move them.
import {
  calendarDate,
  compactDateRange,
  daysBetween,
  firstOfMonth,
  isDate,
  mediumDateLabel,
  shiftDate,
  startOfWeek,
  weekdayShortName,
} from "@xcode/shared/dates";

export { daysBetween, firstOfMonth, isDate, shiftDate, startOfWeek };

// "29 Sep 2026"
export function dayLabel(value: string) {
  const date = calendarDate(value);
  return mediumDateLabel(
    date.getUTCDate(),
    date.getUTCMonth(),
    date.getUTCFullYear(),
  );
}

// "21 to 27 Sep 2026", "28 Sep to 4 Oct 2026", "29 Dec 2025 to 4 Jan 2026": a month or year shown once when shared.
export const rangeLabel = (from: string, through: string) =>
  compactDateRange(from, through, dayLabel);

// "Tue 29 Sep 2026"
export const longDayLabel = (value: string) =>
  `${weekdayShortName(value)} ${dayLabel(value)}`;

// "Tue 29"
export function shortDayLabel(value: string) {
  const date = calendarDate(value);
  return `${weekdayShortName(value)} ${date.getUTCDate()}`;
}

// The first day of the organization's week that holds a date on or before the current week, from the current
// week's first day as the API reports it (the organization chooses which weekday starts its week).
export const weekHolding = (date: string, currentWeekStart: string) =>
  shiftDate(currentWeekStart, -7 * Math.ceil(daysBetween(date, currentWeekStart) / 7));
