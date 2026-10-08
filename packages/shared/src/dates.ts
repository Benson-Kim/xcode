import { dateTimeFormat, remember } from "./intlCache";

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

const DATE_SHAPE = /^\d{4}-\d{2}-\d{2}$/;

const isLeapYear = (year: number) =>
  year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);

const MONTH_LENGTHS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];

const daysInMonth = (year: number, month: number) =>
  month === 2 && isLeapYear(year) ? 29 : MONTH_LENGTHS[month - 1]!;

export const isDate = (value: unknown): value is string => {
  if (typeof value !== "string" || !DATE_SHAPE.test(value)) return false;
  const month = Number(value.slice(5, 7));
  const day = Number(value.slice(8, 10));
  return (
    month >= 1 &&
    month <= 12 &&
    day >= 1 &&
    day <= daysInMonth(Number(value.slice(0, 4)), month)
  );
};

function epochDayOf(year: number, month: number, day: number) {
  const y = month <= 2 ? year - 1 : year;
  const era = Math.floor(y / 400);
  const yearOfEra = y - era * 400;
  const dayOfYear =
    Math.floor((153 * (month + (month > 2 ? -3 : 9)) + 2) / 5) + day - 1;
  const dayOfEra =
    yearOfEra * 365 +
    Math.floor(yearOfEra / 4) -
    Math.floor(yearOfEra / 100) +
    dayOfYear;
  return era * 146097 + dayOfEra - 719468;
}

// Days since 1970-01-01, or NaN for text that is not a yyyy-MM-dd date. Days past the end of a month roll
// into the next one, as a Date would.
function epochDay(value: string) {
  if (!DATE_SHAPE.test(value)) return NaN;
  const month = Number(value.slice(5, 7));
  const day = Number(value.slice(8, 10));
  if (month < 1 || month > 12 || day < 1 || day > 31) return NaN;
  return epochDayOf(Number(value.slice(0, 4)), month, day);
}

function civilFromEpochDay(days: number) {
  const z = days + 719468;
  const era = Math.floor(z / 146097);
  const dayOfEra = z - era * 146097;
  const yearOfEra = Math.floor(
    (dayOfEra -
      Math.floor(dayOfEra / 1460) +
      Math.floor(dayOfEra / 36524) -
      Math.floor(dayOfEra / 146096)) /
      365,
  );
  const dayOfYear =
    dayOfEra -
    (365 * yearOfEra + Math.floor(yearOfEra / 4) - Math.floor(yearOfEra / 100));
  const shifted = Math.floor((5 * dayOfYear + 2) / 153);
  const day = dayOfYear - Math.floor((153 * shifted + 2) / 5) + 1;
  const month = shifted < 10 ? shifted + 3 : shifted - 9;
  const year = yearOfEra + era * 400 + (month <= 2 ? 1 : 0);
  return { year, month, day };
}

const pad = (value: number, length: number) =>
  String(value).padStart(length, "0");

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

export function weekdayIndex(value: string) {
  const days = epochDay(value);
  return Number.isNaN(days) ? NaN : ((days % 7) + 11) % 7;
}

export const weekdayShortName = (value: string) =>
  SHORT_WEEKDAY_NAMES[weekdayIndex(value)] as string;

export const weekdayName = (index: number) => WEEKDAY_NAMES[index];

export const shortMonthName = (index: number) => SHORT_MONTH_NAMES[index];

export const mediumDateLabel = (
  day: number,
  month: number,
  year: string | number,
) => `${day} ${shortMonthName(month)} ${year}`;

export function dayOfMonth(value: string) {
  const days = epochDay(value);
  return Number.isNaN(days) ? NaN : civilFromEpochDay(days).day;
}

export function shiftDate(value: string, days: number) {
  if (!isDate(value)) return value;
  const { year, month, day } = civilFromEpochDay(epochDay(value) + days);
  return `${pad(year, 4)}-${pad(month, 2)}-${pad(day, 2)}`;
}

export const daysBetween = (from: string, to: string) =>
  epochDay(to) - epochDay(from);

export const startOfWeek = (value: string, weekStartsOn: number) =>
  shiftDate(value, -((weekdayIndex(value) - weekStartsOn + 7) % 7));

export type WeekDay = {
  date: string;
  weekday: number;
  shortName: string;
  dayOfMonth: number;
};

export function weekDays(start: string, length = 7): WeekDay[] {
  if (!isDate(start)) return [];
  const first = epochDay(start);
  const firstWeekday = ((first % 7) + 11) % 7;
  return Array.from({ length }, (_, offset) => {
    const { year, month, day } = civilFromEpochDay(first + offset);
    const weekday = (firstWeekday + offset) % 7;
    return {
      date: `${pad(year, 4)}-${pad(month, 2)}-${pad(day, 2)}`,
      weekday,
      shortName: SHORT_WEEKDAY_NAMES[weekday]!,
      dayOfMonth: day,
    };
  });
}

export const firstOfMonth = (value: string) => `${value.slice(0, 8)}01`;

const PART_OPTIONS: Intl.DateTimeFormatOptions = {
  year: "numeric",
  month: "numeric",
  day: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
};

export function dateParts(date: Date, timeZone?: string) {
  const values: Record<string, string> = {};
  for (const part of dateTimeFormat(
    "en-GB",
    "parts",
    timeZone,
    PART_OPTIONS,
  ).formatToParts(date)) {
    values[part.type] = part.value;
  }
  return {
    year: values.year!,
    month: Number(values.month) - 1,
    day: Number(values.day),
    hour: Number(values.hour),
    minute: Number(values.minute),
  };
}

const validTimeZones = new Map<string, string | undefined>();

function safeTimeZone(timeZone: string | undefined) {
  if (!timeZone) return undefined;
  return remember(validTimeZones, timeZone, () => {
    try {
      dateTimeFormat("en-GB", "parts", timeZone, PART_OPTIONS);
      return timeZone;
    } catch {
      return undefined;
    }
  });
}

function formatInZone(
  date: Date,
  locale: string,
  datePattern: string,
  timeZone: string | undefined,
) {
  if (datePattern === "medium") {
    const { year, month, day } = dateParts(date, timeZone);
    return mediumDateLabel(day, month, year);
  }
  const dateStyle = datePattern === "short" ? "short" : "long";
  return dateTimeFormat(locale, dateStyle, timeZone, { dateStyle }).format(
    date,
  );
}

export function formatCalendarDate(
  date: Date,
  { locale, datePattern, timeZone }: DateFormatSettings,
) {
  return formatInZone(date, locale, datePattern, timeZone);
}

// A calendar date in the organization's date format ("5 Sep 2026" by default). The value is a calendar day,
// so it is read as UTC midnight and shown in UTC; the organization's zone would move it back a day west of UTC.
export function formatDateOnly(value: string, settings: DateFormatSettings) {
  return formatInZone(
    calendarDate(value),
    settings.locale,
    settings.datePattern,
    "UTC",
  );
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

export function formatTimestamp(value: string, settings: DateFormatSettings) {
  const date = new Date(value);
  if (isNaN(date.getTime())) return value;
  const zone = safeTimeZone(settings.timeZone);
  const { hour, minute } = dateParts(date, zone);
  const minutes = String(minute).padStart(2, "0");
  const time = settings.hour12
    ? `${hour % 12 || 12}:${minutes} ${hour < 12 ? "am" : "pm"}`
    : `${String(hour).padStart(2, "0")}:${minutes}`;
  return `${formatInZone(date, settings.locale, settings.datePattern, zone)} ${time}`;
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
