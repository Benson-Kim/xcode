import {
  formatDateOnly as formatDateOnlyWithSettings,
  formatCalendarDate,
  formatCalendarDateRange,
  formatTimestamp,
  weekdayShortName,
} from "./dates";
import { numberFormat } from "./intlCache";

export type Formats = {
  locale: string;
  timeZone: string;
  datePattern: string;
  hour12: boolean;
  currency: string;
  useGrouping: boolean;
  numberDecimals: number;
  firstDayOfWeek: number;
};

const defaults: Formats = {
  locale: "en-GB",
  timeZone: "Africa/Nairobi",
  datePattern: "medium",
  hour12: false,
  currency: "KES",
  useGrouping: true,
  numberDecimals: 2,
  firstDayOfWeek: 1,
};

// Spelling used before the rename; read for one release, never written.
export type FormatsInput = Partial<Formats> & { useGroupping?: boolean };

export function currentFormats<T extends FormatsInput>(
  next: T,
): Omit<T, "useGroupping"> {
  const { useGroupping, ...rest } = next;
  return useGroupping === undefined || rest.useGrouping !== undefined
    ? rest
    : { ...rest, useGrouping: useGroupping };
}

export function createFormatter(next?: FormatsInput | null) {
  const given = next ? currentFormats(next) : {};
  const formats: Formats = {
    ...defaults,
    ...given,
    useGrouping: given.useGrouping ?? defaults.useGrouping,
  };

  function firstDayOfWeek() {
    const first = formats.firstDayOfWeek;
    return Number.isInteger(first) && first >= 0 && first <= 6 ? first : 1;
  }

  function formatNumber(amount: number) {
    return numberFormat(
      formats.locale,
      Number.isInteger(amount) ? 0 : formats.numberDecimals,
      formats.numberDecimals,
      formats.useGrouping,
    ).format(amount);
  }

  function kes(amount: number) {
    return `${formats.currency} ${formatNumber(amount)}`;
  }

  const formatDateOnly = (value: string) =>
    formatDateOnlyWithSettings(value, formats);

  return {
    formats,
    currencyCode: () => formats.currency,
    datePattern: () => formats.datePattern,
    firstDayOfWeek,
    formatNumber,
    kes,
    money: (amount: number) =>
      amount < 0 ? `${kes(-amount)} loss` : kes(amount),
    percentText,
    plural,
    formatDate: (date: Date, timeZone = "UTC") =>
      formatCalendarDate(date, { ...formats, timeZone }),
    formatDateOnly,
    formatWeekdayDate: (value: string) =>
      `${weekdayShortName(value)} ${formatDateOnly(value)}`,
    formatDateRange: (from: string, through: string) =>
      formatCalendarDateRange(from, through, formats),
    formatDateTime: (value: string) => formatTimestamp(value, formats),
    // Words, not a minus sign: "KES 1,200 below", "KES 350 above", "On target".
    formatDifference: (actual: number, expected: number) => {
      const gap = Math.round((actual - expected) * 100) / 100;
      return gap === 0
        ? "On target"
        : `${kes(Math.abs(gap))} ${gap > 0 ? "above" : "below"}`;
    },
  };
}

export type Formatter = ReturnType<typeof createFormatter>;

export const MAX_PERCENT_SHOWN = 999;

export function percentText(percent: number) {
  return percent > MAX_PERCENT_SHOWN ? `${MAX_PERCENT_SHOWN}%+` : `${percent}%`;
}

export function plural(count: number, one: string, many: string) {
  return `${count} ${count === 1 ? one : many}`;
}

export function normalisePhone(value: string) {
  let digits = (value || "").replace(/\D/g, "");

  if (digits.startsWith("254")) digits = "0" + digits.slice(3);
  else if (/^[17]/.test(digits)) digits = "0" + digits;

  return digits;
}

export function formatPhone(value: string) {
  const normalized = normalisePhone(value);

  if (normalized.length === 10) {
    return `${normalized.slice(0, 4)} ${normalized.slice(4, 7)} ${normalized.slice(7)}`;
  }

  return value;
}

export function maskPhone(value: string) {
  const normalized = normalisePhone(value);
  if (normalized.length !== 10) return value;

  return `${normalized.slice(0, 4)} ••• ${normalized.slice(7)}`;
}

export function phoneError(value: string) {
  const normalized = normalisePhone(value);

  if (!normalized) return "Enter your mobile number.";

  if (!/^0[17]\d{8}$/.test(normalized)) {
    return "Enter all 10 numbers, starting 07 or 01.";
  }
  return "";
}

export function initials(firstName: string, lastName: string) {
  return `${firstName.charAt(0)}${lastName.charAt(0)}`.toUpperCase();
}
