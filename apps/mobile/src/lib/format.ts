// Display formats. They follow the organization's locale settings once the app has loaded them;
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

let formats = defaults;

export function configureFormats(next?: Partial<Formats> | null) {
  formats = { ...defaults, ...next };
}

export const currencyCode = () => formats.currency;

// "KES 49,000": whole amounts stay whole; the organization's decimals are the most shown.
export function money(amount: number) {
  const number = amount.toLocaleString(formats.locale, {
    maximumFractionDigits: formats.numberDecimals,
    useGrouping: formats.useGroupping,
  });
  return `${formats.currency} ${number}`;
}
