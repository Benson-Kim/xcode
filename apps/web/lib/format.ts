// Display formats shared by the screens.
// They follow the organization's locale settings (and the person's overrides) once the app shell has loaded them; until then, the design's defaults apply.

export type Formats = {
  locale: string;
  timeZone: string;
  datePattern: string;
  hour12: boolean;
  currency: string;
  useGroupping: boolean;
  numberDecimals: number;
};

const defaults: Formats = {
  locale: "en-GB",
  timeZone: "Africa/Nairobi",
  datePattern: "medium",
  hour12: false,
  currency: "KES",
  useGroupping: true,
  numberDecimals: 2,
};

let formats: Formats = defaults;

export function configureFormats(next?: Partial<Formats> | null) {
  formats = { ...defaults, ...next };
}

export function datePattern() {
  return formats.datePattern;
}

export function currencyCode() {
  return formats.currency;
}

// "KES 49,000" and "KES 1,500.50": whole amounts stay whole; any other shows the organization's decimals in full.
export function kes(amount: number) {
  const number = amount.toLocaleString(formats.locale, {
    minimumFractionDigits: Number.isInteger(amount) ? 0 : formats.numberDecimals,
    maximumFractionDigits: formats.numberDecimals,
    useGrouping: formats.useGroupping,
  });
  return `${formats.currency} ${number}`;
}

// A result that can go below zero, as the design writes it: "KES 1,200 loss" rather than a minus sign.
export function money(amount: number) {
  return amount < 0 ? `${kes(-amount)} loss` : kes(amount);
}

export function plural(count: number, one: string, many: string) {
  return `${count} ${count === 1 ? one : many}`;
}

// +254712345678 -> 0712 345 678, the way people write Kenyan numbers.
export function formatPhone(value: string) {
  const digits = value.replace(/\D/g, "");
  const local = digits.startsWith("254") ? `0${digits.slice(3)}` : digits;
  return local.length === 10
    ? `${local.slice(0, 4)} ${local.slice(4, 7)} ${local.slice(7)}`
    : value;
}

const MONTHS = [
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

function parts(date: Date, timeZone?: string) {
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
    year: values.year,
    month: Number(values.month) - 1,
    day: Number(values.day),
    hour: Number(values.hour),
    minute: values.minute,
  };
}

// A calendar date. "medium" is the design's "5 Sep 2026"; short and long follow the locale.
export function formatDate(date: Date, timeZone = "UTC") {
  if (formats.datePattern === "medium") {
    const { year, month, day } = parts(date, timeZone);
    return `${day} ${MONTHS[month]} ${year}`;
  }
  return new Intl.DateTimeFormat(formats.locale, {
    dateStyle: formats.datePattern === "short" ? "short" : "long",
    timeZone,
  }).format(date);
}

// "20 Sep 2026 16:05" in the organization's time zone, with its 12 or 24-hour clock.
export function formatDateTime(value: string) {
  const date = new Date(value);
  const zone = safeZone(formats.timeZone);
  const { hour, minute } = parts(date, zone);
  const time = formats.hour12
    ? `${hour % 12 || 12}:${minute} ${hour < 12 ? "am" : "pm"}`
    : `${String(hour).padStart(2, "0")}:${minute}`;
  return `${formatDate(date, zone)} ${time}`;
}

function safeZone(zone: string) {
  try {
    new Intl.DateTimeFormat("en-GB", { timeZone: zone });
    return zone;
  } catch {
    return undefined;
  }
}

export function initials(firstName: string, lastName: string) {
  return `${firstName.charAt(0)}${lastName.charAt(0)}`.toUpperCase();
}
