import { datePattern, formatDate } from "../lib/format";

// Frequency: 1 every day (legacy, read only), 2 weekly on `day` (0 is Sunday), 3 monthly on `day` or the last day,
// 4 yearly in `month` (1 to 12) on `day` or the last day.
export type RecurringScheduleItem = {
  frequency: number;
  day?: number | null;
  lastDay: boolean;
  month?: number | null;
  start: string;
  end?: string | null;
  stoppedFrom?: string | null;
};

const weekdayNames = [
  "Sunday",
  "Monday",
  "Tuesday",
  "Wednesday",
  "Thursday",
  "Friday",
  "Saturday",
];

export const monthNames = [
  "January",
  "February",
  "March",
  "April",
  "May",
  "June",
  "July",
  "August",
  "September",
  "October",
  "November",
  "December",
];

// "1st", "22nd", "13th".
export function ordinal(value: number) {
  const lastTwo = value % 100;
  const suffix =
    lastTwo >= 11 && lastTwo <= 13
      ? "th"
      : ["th", "st", "nd", "rd"][value % 10] || "th";
  return `${value}${suffix}`;
}

// The first day of a date's month: the earliest a scheduled item may start, taken from the business date.
export function firstOfMonth(date: string) {
  return `${date.slice(0, 8)}01`;
}

function parseDateOnly(value: string) {
  const [year, month, day] = value.split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, day));
}

// A calendar date in the organization's date format ("5 Sep 2026" by default).
export function formatDateOnly(value: string) {
  return formatDate(parseDateOnly(value));
}

// "1 to 26 Sep 2026", or "28 Sep to 4 Oct 2026" across months
export function formatDateRange(from: string, through: string) {
  const [start, end] = [parseDateOnly(from), parseDateOnly(through)];
  if (
    datePattern() !== "medium" ||
    start.getUTCFullYear() !== end.getUTCFullYear()
  )
    return `${formatDateOnly(from)} to ${formatDateOnly(through)}`;
  const [day, month] = formatDateOnly(from).split(" ");
  return `${day}${start.getUTCMonth() === end.getUTCMonth() ? "" : ` ${month}`} to ${formatDateOnly(through)}`;
}

export function recurringNextPostings(
  item: RecurringScheduleItem,
  today: string,
  limit = 5,
): string[] {
  if (limit < 1) return [];
  const postings: string[] = [];
  const candidate = parseDateOnly(item.start > today ? item.start : today);
  for (let offset = 0; offset < 3660 && postings.length < limit; offset++) {
    const candidateDate = candidate.toISOString().slice(0, 10);
    if (item.end && candidateDate > item.end) return postings;
    if (item.stoppedFrom && candidateDate >= item.stoppedFrom) return postings;

    const lastDay = new Date(
      Date.UTC(candidate.getUTCFullYear(), candidate.getUTCMonth() + 1, 0),
    ).getUTCDate();
    const onDay = candidate.getUTCDate() === (item.lastDay ? lastDay : item.day);
    const isDue =
      item.frequency === 1 ||
      (item.frequency === 2 && candidate.getUTCDay() === item.day) ||
      (item.frequency === 3 && onDay) ||
      (item.frequency === 4 &&
        onDay &&
        candidate.getUTCMonth() + 1 === item.month);
    if (isDue) postings.push(candidateDate);
    candidate.setUTCDate(candidate.getUTCDate() + 1);
  }
  return postings;
}

export function recurringNextPosting(
  item: RecurringScheduleItem,
  today: string,
) {
  return recurringNextPostings(item, today, 1)[0] ?? null;
}

export function recurringFrequency(item: RecurringScheduleItem) {
  if (item.frequency === 1) return "Every day";
  if (item.frequency === 2) return `Every ${weekdayNames[item.day ?? 0]}`;
  if (item.frequency === 4) {
    const month = monthNames[(item.month ?? 1) - 1];
    return item.lastDay
      ? `Every year on the last day of ${month}`
      : `Every year on ${ordinal(item.day ?? 1)} ${month}`;
  }
  if (item.lastDay) return "Last day of every month";
  return `Every month on the ${ordinal(item.day ?? 1)}`;
}

// About how much it comes to in a month: a yearly amount is spread over twelve.
export function recurringMonthlyEstimate(amount: number, frequency: number) {
  return Math.round(
    frequency === 4
      ? amount / 12
      : amount * (frequency === 1 ? 30.4 : frequency === 2 ? 4.35 : 1),
  );
}
