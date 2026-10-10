"use client";

import type { ComponentProps, ReactNode } from "react";

import { cn } from "./cn";
import { TableRowsSkeleton } from "./skeleton";

export type Column = { label: string; numeric?: boolean; hidden?: boolean };

// A list (.tbl > .scroll > table). Straight on the sheet it runs edge to edge, its first and last columns on the
// page's side margin; in a pop up it is a bordered card (.mb .tbl). Both come from the design's stylesheet. A table
// wider than the sheet scrolls sideways inside it. While loading it shows placeholder rows, never the empty message.
export function DataTable({
  columns,
  loading = false,
  pendingRows = 0,
  isEmpty = false,
  emptyMessage,
  failed = false,
  loadingLabel = "Loading",
  id,
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
  id?: string;
  className?: string;
  // Totals row(s) under the list (<tr> elements).
  footer?: ReactNode;
  children?: ReactNode;
}) {
  return (
    <div id={id} className={cn("tbl", className)}>
      <div className="scroll">
        <table aria-busy={loading || pendingRows > 0 || undefined}>
          {loading && <caption className="sr-only">{loadingLabel}</caption>}
          <thead>
            <tr>
              {columns.map((column, index) => (
                <th
                  key={column.label || index}
                  scope="col"
                  className={cn(column.numeric && "r")}
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
          <tbody>
            {loading ? (
              <TableRowsSkeleton columns={columns.length} />
            ) : isEmpty ? (
              <tr>
                <td colSpan={columns.length} className="empty">
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
          {footer && !loading && !isEmpty && <tfoot>{footer}</tfoot>}
        </table>
      </div>
    </div>
  );
}

// A row; `group` is a heading row across the table (tr.grp), `editing` the row being changed (tr.editing).
export function Tr({
  group = false,
  editing = false,
  className,
  ...props
}: ComponentProps<"tr"> & { group?: boolean; editing?: boolean }) {
  return (
    <tr
      {...props}
      className={
        cn(group && "grp", editing && "editing", className) || undefined
      }
    />
  );
}

// A cell: `numeric` right-aligns a figure (td.r), `item` is the row's name (td.item). `label` names the column the
// cell is in; it is kept on the cell as data-label.
export function Td({
  label,
  numeric = false,
  item = false,
  className,
  ...props
}: ComponentProps<"td"> & {
  label?: string;
  numeric?: boolean;
  item?: boolean;
}) {
  return (
    <td
      {...props}
      data-label={label}
      className={cn(numeric && "r", item && "item", className) || undefined}
    />
  );
}

// Secondary line under a cell value (td .note).
export function CellNote({ className, ...props }: ComponentProps<"small">) {
  return <small {...props} className={cn("note", className)} />;
}
