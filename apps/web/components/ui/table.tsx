"use client";

import { useContext, type ComponentProps, type ReactNode } from "react";

import { cn } from "./cn";
import { InDialogContext } from "./dialog";
import { TableRowsSkeleton } from "./skeleton";

export type Column = { label: string; numeric?: boolean; hidden?: boolean };

// A list (.tbl). On the page it runs edge to edge across the sheet, its first and last columns keeping the page's side
// margin; in a pop-up it is a bordered card. While loading it shows placeholder rows, never the empty message; below
// 720px each row becomes a stack of labelled cells.
export function DataTable({
  columns,
  loading = false,
  pendingRows = 0,
  isEmpty = false,
  emptyMessage,
  failed = false,
  loadingLabel = "Loading",
  className,
  footer,
  children,
}: {
  columns: Column[];
  loading?: boolean;
  // Placeholder rows after the rows already shown, while more pages are on their way.
  pendingRows?: number;
  isEmpty?: boolean;
  emptyMessage: ReactNode;
  // The list could not be loaded (the page says why): an empty list then is not "nothing here yet".
  failed?: boolean;
  loadingLabel?: string;
  className?: string;
  // Totals row(s) under the list (<tr> elements).
  footer?: ReactNode;
  children?: ReactNode;
}) {
  const inDialog = useContext(InDialogContext);
  return (
    <div
      className={cn(
        // A table wider than the sheet scrolls inside it: clipping would put the last columns, and the row
        // actions in them, out of reach with no way to get at them.
        "tbl overflow-x-auto bg-surface",
        inDialog
          ? "flex-none rounded-[18px] border border-line [&_td]:px-3 [&_td]:py-[7px] [&_th]:px-3 [&_th]:py-[9px]"
          : "-mx-(--gut) border-y border-line min-[721px]:[&_td:first-child]:pl-(--gut) min-[721px]:[&_td:last-child]:pr-(--gut) [&_th:first-child]:pl-(--gut) [&_th:last-child]:pr-(--gut) max-[720px]:[&_td]:px-(--gut)",
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
                  "border-b border-line px-4 py-3 text-left text-[11.5px] font-bold tracking-[0.08em] whitespace-nowrap text-slate uppercase",
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
                className="px-4 py-[26px] text-left text-slate max-[720px]:block"
              >
                {failed ? "This list could not be loaded." : emptyMessage}
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
        {footer && !loading && !isEmpty && (
          <tfoot className="max-[720px]:block [&_td]:border-t [&_td]:border-b-0 [&_td]:border-line [&_td]:bg-paper-2 [&_td]:font-bold [&_td]:text-ink">
            {footer}
          </tfoot>
        )}
      </table>
    </div>
  );
}

export function Tr({ className, ...props }: ComponentProps<"tr">) {
  return (
    <tr
      {...props}
      className={cn(
        "hover:[&>td]:bg-paper [&:last-child>td]:border-b-0 max-[720px]:block max-[720px]:border-b max-[720px]:border-divider max-[720px]:py-2 max-[720px]:last:border-b-0",
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
        "border-b border-divider px-4 py-[11px] align-middle [overflow-wrap:anywhere]",
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
      className={cn("block text-[13px] font-normal text-slate", className)}
    />
  );
}
