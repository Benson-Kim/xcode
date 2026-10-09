import type { ExpenseLedgerRow } from "@xcode/shared/expenses";
import type { Formatter } from "@xcode/shared/format";

// "KDA 482M, Tyres, KES 3,500": names a row for a button or a dialog, so a screen reader hears which one.
export const rowLabel = (formats: Formatter, row: ExpenseLedgerRow) =>
  `${row.registration}, ${row.itemName}, ${formats.kes(row.total)}`;
