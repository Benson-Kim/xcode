// Display formats. They follow the organization's locale settings once the app has loaded them;
export type Formats = {
  locale: string;
  timeZone: string;
  datePattern: string;
  hour12: boolean;
  currency: string;
  useGroupping: boolean;
  numberDecimals: number;
  // The organization's first day of the week, 0 (Sunday) to 6, as the API counts its weeks.
  firstDayOfWeek?: number;
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

let formats = defaults;

export function configureFormats(next?: Partial<Formats> | null) {
  formats = { ...defaults, ...next };
}

export const currencyCode = () => formats.currency;

// Monday, the API's own default, until the organization's choice is known, and in place of anything out of range.
export function firstDayOfWeek() {
  const first = formats.firstDayOfWeek;
  return Number.isInteger(first) && first! >= 0 && first! <= 6 ? first! : 1;
}

// "KES 49,000" and "KES 1,500.50": whole amounts stay whole; any other shows the organization's decimals in full.
export function money(amount: number) {
  const number = amount.toLocaleString(formats.locale, {
    minimumFractionDigits: Number.isInteger(amount) ? 0 : formats.numberDecimals,
    maximumFractionDigits: formats.numberDecimals,
    useGrouping: formats.useGroupping,
  });
  return `${formats.currency} ${number}`;
}

// The most a share of a target shows. A vehicle with a tiny target and a large record can reach millions of percent, which tells no one anything.
// Only the display is capped: the stored and API values stay as they are.
export const MAX_PERCENT_SHOWN = 999;

// "83%", and "999%+" for anything above the cap.
export function percentText(percent: number) {
  return percent > MAX_PERCENT_SHOWN ? `${MAX_PERCENT_SHOWN}%+` : `${percent}%`;
}
