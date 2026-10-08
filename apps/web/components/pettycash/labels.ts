import type { Formatter } from "@xcode/shared/format";
import type { PettyCashEntry } from "@xcode/shared/pettyCash";

export function entrySubject(entry: PettyCashEntry) {
  if (entry.kind === "expense") return entry.registration ?? "expense";
  if (entry.kind === "credit")
    return `credit note to ${entry.payee ?? "payee"}`;
  return `cash for ${entry.holderName}`;
}

// "KDA 482M, KES 3,500": names the entry for a row button or a dialog, so a screen reader hears which one.
export const entryLabel = (formats: Formatter, entry: PettyCashEntry) =>
  `${entrySubject(entry)}, ${formats.kes(entry.total)}`;

// Units as entered, up to three decimals ("11.875", "4.5", "1,001"), in the organization's language.
export function unitsFormat(locale: string) {
  const format = new Intl.NumberFormat(locale, { maximumFractionDigits: 3 });
  return (units: number) => format.format(units);
}
