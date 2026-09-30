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

// "KES 49,000": whole amounts stay whole; the organization's decimals are the most shown.
export function money(amount: number) {
  const number = amount.toLocaleString(formats.locale, {
    maximumFractionDigits: formats.numberDecimals,
    useGrouping: formats.useGroupping,
  });
  return `${formats.currency} ${number}`;
}
