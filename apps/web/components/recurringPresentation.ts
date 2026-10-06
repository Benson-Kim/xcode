import {
  calendarDate,
  MONTH_NAMES,
  ordinal,
  weekdayName,
} from "@xcode/shared/dates";

export const RECURRING_FREQUENCY = {
  daily: 1,
  weekly: 2,
  monthly: 3,
  yearly: 4,
} as const;

export const RECURRING_FREQUENCY_OPTIONS = [
  { value: RECURRING_FREQUENCY.weekly, label: "Every week" },
  { value: RECURRING_FREQUENCY.monthly, label: "Every month" },
  { value: RECURRING_FREQUENCY.yearly, label: "Every year" },
];

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

export function recurringNextPostings(
  item: RecurringScheduleItem,
  today: string,
  limit = 5,
): string[] {
  if (limit < 1) return [];
  const postings: string[] = [];
  const candidate = calendarDate(item.start > today ? item.start : today);
  for (let offset = 0; offset < 3660 && postings.length < limit; offset++) {
    const candidateDate = candidate.toISOString().slice(0, 10);
    if (item.end && candidateDate > item.end) return postings;
    if (item.stoppedFrom && candidateDate >= item.stoppedFrom) return postings;

    const lastDay = new Date(
      Date.UTC(candidate.getUTCFullYear(), candidate.getUTCMonth() + 1, 0),
    ).getUTCDate();
    const dayOfMonth = candidate.getUTCDate();
    const targetDay = item.lastDay
      ? lastDay
      : Math.min(item.day ?? 1, lastDay);
    const onDay = dayOfMonth === targetDay;
    const isDue =
      item.frequency === RECURRING_FREQUENCY.daily ||
      (item.frequency === RECURRING_FREQUENCY.weekly &&
        candidate.getUTCDay() === item.day) ||
      (item.frequency === RECURRING_FREQUENCY.monthly && onDay) ||
      (item.frequency === RECURRING_FREQUENCY.yearly &&
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
  if (item.frequency === RECURRING_FREQUENCY.daily) return "Every day";
  if (item.frequency === RECURRING_FREQUENCY.weekly)
    return `Every ${weekdayName(item.day ?? 0)}`;
  if (item.frequency === RECURRING_FREQUENCY.yearly) {
    const month = MONTH_NAMES[(item.month ?? 1) - 1];
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
    frequency === RECURRING_FREQUENCY.yearly
      ? amount / 12
      : amount *
          (frequency === RECURRING_FREQUENCY.daily
            ? 30.4
            : frequency === RECURRING_FREQUENCY.weekly
              ? 4.35
              : 1),
  );
}
