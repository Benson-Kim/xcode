import type { Formatter } from "@xcode/shared/format";
import type {
  ReportCell,
  ReportCellKind,
  ReportFigure,
} from "@xcode/shared/reports";

import { RegPlate } from "../revenue/RegPlate";
import { ProgressBar, cn } from "../ui";

export const NUMERIC_KINDS: readonly ReportCellKind[] = [
  "money",
  "net",
  "count",
  "quantity",
  "percent",
];

export type Units = (value: number) => string;

const percent = (value: number) => `${Math.round(value * 10) / 10}%`;

// What a number reads as: money and net as amounts (with the currency, unless inCurrency is false, as in the
// columns of a table whose headings name it), count as a whole number, quantity up to three decimals, percent as n%.
export function numberText(
  formats: Formatter,
  units: Units,
  kind: ReportCellKind | ReportFigure["kind"],
  value: number,
  inCurrency = true,
) {
  switch (kind) {
    case "money":
    case "net":
      return inCurrency ? formats.kes(value) : formats.formatNumber(value);
    case "quantity":
      return units(value);
    case "percent":
      return percent(value);
    default:
      return formats.formatNumber(value);
  }
}

// The text of a cell as it is shown, amounts without their currency.
export function cellText(
  formats: Formatter,
  units: Units,
  kind: ReportCellKind,
  cell: ReportCell,
) {
  if (cell === null || cell === "") return "";
  if (kind === "date") return formats.formatDateOnly(String(cell));
  if (typeof cell === "number")
    return numberText(formats, units, kind, cell, false);
  return cell;
}

export function CellValue({
  formats,
  units,
  kind,
  cell,
}: {
  formats: Formatter;
  units: Units;
  kind: ReportCellKind;
  cell: ReportCell;
}) {
  const text = cellText(formats, units, kind, cell);
  if (kind === "net" && typeof cell === "number" && cell < 0)
    return <span className="font-semibold text-red">{text}</span>;
  if (kind === "percent" && typeof cell === "number")
    return (
      <span className="flex min-w-24 flex-col items-end gap-1">
        <span>{text}</span>
        <span className="w-full">
          <ProgressBar value={cell} />
        </span>
      </span>
    );
  if (kind === "vehicle") return <RegPlate>{text}</RegPlate>;
  return <span className={cn(kind === "text" && "block")}>{text}</span>;
}
