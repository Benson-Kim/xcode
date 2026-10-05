// Revenue days are the organization's calendar dates ("yyyy-MM-dd"), worked out in UTC so the phone's own
// clock and time zone never move them.
const DAY = 24 * 60 * 60 * 1000;
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

export const isDate = (value: unknown): value is string => typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value);

const toTime = (value: string) => Date.parse(`${value}T00:00:00Z`);

export const shiftDate = (value: string, days: number) => new Date(toTime(value) + days * DAY).toISOString().slice(0, 10);

export const daysBetween = (from: string, to: string) => Math.round((toTime(to) - toTime(from)) / DAY);

// "29 Sep 2026"
export function dayLabel(value: string) {
  const date = new Date(toTime(value));
  return `${date.getUTCDate()} ${MONTHS[date.getUTCMonth()]} ${date.getUTCFullYear()}`;
}

// "21 to 27 Sep 2026", "28 Sep to 4 Oct 2026", "29 Dec 2025 to 4 Jan 2026": a month or year shown once when shared.
export function rangeLabel(from: string, through: string) {
  const [start, end] = [new Date(toTime(from)), new Date(toTime(through))];
  const first =
    start.getUTCFullYear() !== end.getUTCFullYear()
      ? dayLabel(from)
      : start.getUTCMonth() !== end.getUTCMonth()
        ? `${start.getUTCDate()} ${MONTHS[start.getUTCMonth()]}`
        : `${start.getUTCDate()}`;
  return `${first} to ${dayLabel(through)}`;
}

// "Tue 29 Sep 2026"
export const longDayLabel = (value: string) => `${WEEKDAYS[new Date(toTime(value)).getUTCDay()]} ${dayLabel(value)}`;

// "Tue 29"
export function shortDayLabel(value: string) {
  const date = new Date(toTime(value));
  return `${WEEKDAYS[date.getUTCDay()]} ${date.getUTCDate()}`;
}

// The first day of the organization's week that holds a date on or before the current week, from the current
// week's first day as the API reports it (the organization chooses which weekday starts its week).
export const weekHolding = (date: string, currentWeekStart: string) =>
  shiftDate(currentWeekStart, -7 * Math.ceil(daysBetween(date, currentWeekStart) / 7));
