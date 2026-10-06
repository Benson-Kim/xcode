const DAY = 24 * 60 * 60 * 1000;

export const WEEKDAYS = [
  { value: 0, label: "Sunday" },
  { value: 1, label: "Monday" },
  { value: 2, label: "Tuesday" },
  { value: 3, label: "Wednesday" },
  { value: 4, label: "Thursday" },
  { value: 5, label: "Friday" },
  { value: 6, label: "Saturday" },
] as const;

const WEEKDAY_NAMES = WEEKDAYS.map(({ label }) => label);

const SHORT_WEEKDAY_NAMES = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

export const MONTH_NAMES = [
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

const SHORT_MONTH_NAMES = [
  "Jan",
  "Feb",
  "Mar",
  "Apr",
  "May",
  "Jun",
  "Jul",
  "Aug",
  "Sep",
  "Oct",
  "Nov",
  "Dec",
];

export type DateFormatSettings = {
  locale: string;
  timeZone?: string;
  datePattern: string;
  hour12: boolean;
};

export const isDate = (value: unknown): value is string => {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value))
    return false;
  const d = new Date(`${value}T00:00:00Z`);
  return (
    d.getUTCFullYear() === Number(value.slice(0, 4)) &&
    d.getUTCMonth() === Number(value.slice(5, 7)) - 1 &&
    d.getUTCDate() === Number(value.slice(8, 10))
  );
};

// "1st", "22nd", "13th".
export function ordinal(value: number) {
  const lastTwo = value % 100;
  const suffix =
    lastTwo >= 11 && lastTwo <= 13
      ? "th"
      : ["th", "st", "nd", "rd"][value % 10] || "th";
  return `${value}${suffix}`;
}

export const calendarDate = (value: string) => new Date(`${value}T00:00:00Z`);

export const weekdayIndex = (value: string) => calendarDate(value).getUTCDay();

export const weekdayShortName = (value: string) =>
  SHORT_WEEKDAY_NAMES[weekdayIndex(value)];

export const weekdayName = (index: number) => WEEKDAY_NAMES[index];

export const shortMonthName = (index: number) => SHORT_MONTH_NAMES[index];

export const mediumDateLabel = (
  day: number,
  month: number,
  year: string | number,
) => `${day} ${shortMonthName(month)} ${year}`;

export const dayOfMonth = (value: string) => calendarDate(value).getUTCDate();

export function shiftDate(value: string, days: number) {
  if (!isDate(value)) return value;
  const date = calendarDate(value);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

export const daysBetween = (from: string, to: string) =>
  Math.round((calendarDate(to).getTime() - calendarDate(from).getTime()) / DAY);

export const startOfWeek = (value: string, weekStartsOn: number) =>
  shiftDate(value, -((weekdayIndex(value) - weekStartsOn + 7) % 7));

export const firstOfMonth = (value: string) => `${value.slice(0, 8)}01`;

export function dateParts(date: Date, timeZone?: string) {
  const values = Object.fromEntries(
    new Intl.DateTimeFormat("en-GB", {
      timeZone,
      year: "numeric",
      month: "numeric",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: "h23",
    })
      .formatToParts(date)
      .map((part) => [part.type, part.value]),
  );
  return {
    year: values.year!,
    month: Number(values.month) - 1,
    day: Number(values.day),
    hour: Number(values.hour),
    minute: Number(values.minute),
  };
}

function safeTimeZone(timeZone: string | undefined) {
  if (!timeZone) return undefined;
  try {
    new Intl.DateTimeFormat("en-GB", { timeZone });
    return timeZone;
  } catch {
    return undefined;
  }
}

export function formatCalendarDate(
  date: Date,
  { locale, datePattern, timeZone }: DateFormatSettings,
) {
  if (datePattern === "medium") {
    const { year, month, day } = dateParts(date, timeZone);
    return mediumDateLabel(day, month, year);
  }
  return new Intl.DateTimeFormat(locale, {
    dateStyle: datePattern === "short" ? "short" : "long",
    timeZone,
  }).format(date);
}

// A calendar date in the organization's date format ("5 Sep 2026" by default).
export function formatDateOnly(value: string, settings: DateFormatSettings) {
  return formatCalendarDate(calendarDate(value), settings);
}

export function formatCalendarDateRange(
  from: string,
  through: string,
  settings: DateFormatSettings,
) {
  const format = (value: string) => formatDateOnly(value, settings);
  return settings.datePattern === "medium"
    ? compactDateRange(from, through, format)
    : `${format(from)} to ${format(through)}`;
}

export function formatTimestamp(
  value: string,
  settings: DateFormatSettings,
) {
  const date = new Date(value);
  if (isNaN(date.getTime())) return value;
  const zone = safeTimeZone(settings.timeZone);
  const { hour, minute } = dateParts(date, zone);
  const minutes = String(minute).padStart(2, "0");
  const time = settings.hour12
    ? `${hour % 12 || 12}:${minutes} ${hour < 12 ? "am" : "pm"}`
    : `${String(hour).padStart(2, "0")}:${minutes}`;
  return `${formatCalendarDate(date, { ...settings, timeZone: zone })} ${time}`;
}

export function compactDateRange(
  from: string,
  through: string,
  formatDate: (value: string) => string,
) {
  const start = calendarDate(from);
  const end = calendarDate(through);
  const first =
    start.getUTCFullYear() !== end.getUTCFullYear()
      ? formatDate(from)
      : start.getUTCMonth() !== end.getUTCMonth()
        ? formatDate(from).replace(/ \d+$/, "")
        : String(start.getUTCDate());
  return `${first} to ${formatDate(through)}`;
}
