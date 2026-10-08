import type { Formatter } from "@xcode/shared/format";

// A float below zero keeps its minus sign, "KES -5,666", and is shown in red where it is drawn.
export const balanceText = (formats: Formatter, amount: number) =>
  formats.kes(amount);

// Units as entered, up to three decimals: 11.875, 4.5, 1,001.
export const unitsText = (formats: Formatter, units: number) =>
  new Intl.NumberFormat(formats.formats.locale, {
    minimumFractionDigits: 0,
    maximumFractionDigits: 3,
    useGrouping: formats.formats.useGrouping,
  }).format(units);
