import type { Formatter } from "@xcode/shared/format";
import type {
  ReportCell,
  ReportCellKind,
  ReportColumn,
  ReportFigure,
} from "@xcode/shared/reports";

import { RegPlate, Td, cn } from "../ui";

export type Units = (value: number) => string;

const percent = (value: number) => `${Math.round(value * 10) / 10}%`;

// Shares and how much of a target was reached draw a bar (.prog); other percentages are plain figures.
const PLAIN_PERCENT = ["recovered"];
const isBar = (column: ReportColumn) =>
  column.kind === "percent" && !PLAIN_PERCENT.includes(column.key);

// Right-aligned columns (th.r, td.r), as the design's money, net, int and pct1 columns.
export const isNumeric = (column: ReportColumn) =>
  ["money", "net", "count", "quantity", "percent"].includes(column.kind) &&
  !isBar(column);

// The row's name (td.item): the item, what is missing, the manager leading a row.
const isItem = (column: ReportColumn, index: number) =>
  ["item", "missing", "what"].includes(column.key) ||
  (column.key === "manager" && index === 0);

// What a number reads as: money and net as amounts (with the currency, unless inCurrency is false, as in the
// columns and the figures beside the headline), count as a whole number, quantity up to three decimals, percent as n%.
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

// One cell as the design's cellHtml draws it: plates for vehicles (plain text in the footer), net in bold with a
// loss in clay, shares as a bar with the figure beside it.
export function ReportTd({
  formats,
  units,
  column,
  index,
  cell,
  foot = false,
}: {
  formats: Formatter;
  units: Units;
  column: ReportColumn;
  index: number;
  cell: ReportCell;
  foot?: boolean;
}) {
  const label = foot ? undefined : column.label;
  const text = cellText(formats, units, column.kind, cell);
  if (text === "") return <Td label={label} />;
  if (column.kind === "vehicle")
    return <Td label={label}>{foot ? text : <RegPlate>{text}</RegPlate>}</Td>;
  if (column.kind === "net")
    return (
      <Td
        label={label}
        numeric
        className={cn("tot", typeof cell === "number" && cell < 0 && "neg")}
      >
        {text}
      </Td>
    );
  if (isBar(column) && typeof cell === "number") {
    const width = Math.max(0, Math.min(cell, 100));
    return (
      <Td label={label}>
        <div className="prog">
          <div className="t">
            <i
              className={cn(width >= 100 && "full") || undefined}
              style={{ width: `${width}%` }}
            />
          </div>
          <span>{text}</span>
        </div>
      </Td>
    );
  }
  return (
    <Td
      label={label}
      numeric={isNumeric(column)}
      item={!foot && isItem(column, index)}
    >
      {text}
    </Td>
  );
}
