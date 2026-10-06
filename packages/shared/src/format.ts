import {
  formatDateOnly as formatDateOnlyWithSettings,
  formatCalendarDate,
  formatCalendarDateRange,
  formatTimestamp,
} from "./dates";

export type Formats = {
  locale: string;
  timeZone: string;
  datePattern: string;
  hour12: boolean;
  currency: string;
  useGroupping: boolean;
  numberDecimals: number;
  firstDayOfWeek: number;
};

const defaults: Formats = {
  locale: "en-GB",
  timeZone: "Africa/Nairobi",
  datePattern: "medium",
  hour12: false,
  currency: "KES",
  useGroupping: true,
  numberDecimals: 2,
  firstDayOfWeek: 1,
};

export function createFormatter(next?: Partial<Formats> | null) {
  const formats: Formats = { ...defaults, ...next };

  function firstDayOfWeek() {
    const first = formats.firstDayOfWeek;
    return Number.isInteger(first) && first >= 0 && first <= 6 ? first : 1;
  }

  function kes(amount: number) {
    const number = amount.toLocaleString(formats.locale, {
      minimumFractionDigits: Number.isInteger(amount)
        ? 0
        : formats.numberDecimals,
      maximumFractionDigits: formats.numberDecimals,
      useGrouping: formats.useGroupping,
    });
    return `${formats.currency} ${number}`;
  }

  return {
    formats,
    currencyCode: () => formats.currency,
    datePattern: () => formats.datePattern,
    firstDayOfWeek,
    kes,
    money: (amount: number) =>
      amount < 0 ? `${kes(-amount)} loss` : kes(amount),
    percentText,
    plural,
    formatDate: (date: Date, timeZone = "UTC") =>
      formatCalendarDate(date, { ...formats, timeZone }),
    formatDateOnly: (value: string) =>
      formatDateOnlyWithSettings(value, formats),
    formatDateRange: (from: string, through: string) =>
      formatCalendarDateRange(from, through, formats),
    formatDateTime: (value: string) => formatTimestamp(value, formats),
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
