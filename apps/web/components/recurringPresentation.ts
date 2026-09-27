import { datePattern, formatDate } from "../lib/format";

export type RecurringScheduleItem = {
  frequency: number;
  day?: number | null;
  lastDay: boolean;
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

export function todayDateOnly(now = new Date()) {
  return new Date(
    Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()),
  )
    .toISOString()
    .slice(0, 10);
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
    const isDue =
      item.frequency === 1 ||
      (item.frequency === 2 && candidate.getUTCDay() === item.day) ||
      (item.frequency === 3 &&
        candidate.getUTCDate() === (item.lastDay ? lastDay : item.day));
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
  if (item.lastDay) return "Last day of every month";

  const day = item.day ?? 1;
  const lastTwo = day % 100;
  const suffix =
    lastTwo >= 11 && lastTwo <= 13
      ? "th"
      : ["th", "st", "nd", "rd"][day % 10] || "th";
  return `Every month on the ${day}${suffix}`;
}

export function recurringMonthlyEstimate(amount: number, frequency: number) {
  return Math.round(
    amount * (frequency === 1 ? 30.4 : frequency === 2 ? 4.35 : 1),
  );
}
