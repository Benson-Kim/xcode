import type { ComponentProps, ReactNode } from "react";
import { cn } from "./cn";
import { TableRowsSkeleton } from "./skeleton";

export type Column = { label: string; numeric?: boolean; hidden?: boolean };

// A list in a card. While loading it shows placeholder rows, never the
// empty message; below 720px each row becomes a stack of labelled cells.
export function DataTable({
  columns,
  loading = false,
  pendingRows = 0,
  isEmpty = false,
  emptyMessage,
  loadingLabel = "Loading",
  className,
  children,
}: {
  columns: Column[];
  loading?: boolean;
  // Placeholder rows after the rows already shown, while more pages are on their way.
  pendingRows?: number;
  isEmpty?: boolean;
  emptyMessage: ReactNode;
  loadingLabel?: string;
  className?: string;
  children?: ReactNode;
}) {
  return (
    <div
      className={cn(
        // A table wider than the card scrolls inside it: clipping would put the last columns, and the row
        // actions in them, out of reach with no way to get at them.
        "mt-4 overflow-x-auto rounded-[14px] border border-card-line bg-white",
        className,
      )}
    >
      <table
        className="w-full border-collapse max-[720px]:block"
        aria-busy={loading || pendingRows > 0 || undefined}
      >
        {loading && <caption className="sr-only">{loadingLabel}</caption>}
        <thead className="max-[720px]:hidden">
          <tr>
            {columns.map((column, index) => (
              <th
                key={column.label || index}
                scope="col"
                className={cn(
                  "border-b border-card-line bg-paper px-4 py-3 text-left text-[13px] font-semibold text-grey",
                  column.numeric && "text-right",
                )}
              >
                {column.hidden ? (
                  <span className="sr-only">{column.label}</span>
                ) : (
                  column.label
                )}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="max-[720px]:block">
          {loading ? (
            <TableRowsSkeleton columns={columns.length} />
          ) : isEmpty ? (
            <tr className="max-[720px]:block">
              <td
                colSpan={columns.length}
                className="px-4 py-6 text-center text-grey max-[720px]:block"
              >
                {emptyMessage}
              </td>
            </tr>
          ) : (
            <>
              {children}
              {pendingRows > 0 && (
                <TableRowsSkeleton
                  columns={columns.length}
                  rows={pendingRows}
                />
              )}
            </>
          )}
        </tbody>
      </table>
    </div>
  );
}

export function Tr({ className, ...props }: ComponentProps<"tr">) {
  return (
    <tr
      {...props}
      className={cn(
        "[&:last-child>td]:border-b-0 max-[720px]:block max-[720px]:border-b max-[720px]:border-divider max-[720px]:py-2 max-[720px]:last:border-b-0",
        className,
      )}
    />
  );
}

// A cell; `label` names it in the stacked narrow layout.
export function Td({
  label,
  numeric = false,
  className,
  ...props
}: ComponentProps<"td"> & { label?: string; numeric?: boolean }) {
  return (
    <td
      {...props}
      data-label={label}
      className={cn(
        // A long name with nothing to break on wraps rather than widening its column past the card.
        "border-b border-divider px-4 py-3 align-top text-[15px] [overflow-wrap:anywhere]",
        "max-[720px]:block max-[720px]:w-full max-[720px]:border-0 max-[720px]:py-1",
        label &&
          "max-[720px]:before:block max-[720px]:before:text-xs max-[720px]:before:text-grey max-[720px]:before:content-[attr(data-label)]",
        numeric &&
          "text-right whitespace-nowrap tabular-nums max-[720px]:text-left",
        className,
      )}
    />
  );
}

// Secondary line under a cell value.
export function CellNote({ className, ...props }: ComponentProps<"small">) {
  return (
    <small
      {...props}
      className={cn("block text-[13px] text-grey", className)}
    />
  );
}
