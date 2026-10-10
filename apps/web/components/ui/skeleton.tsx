import type { ReactNode } from "react";

import { Card } from "./card";
import { cn } from "./cn";
import { FormLayout, Grid2 } from "./layout";

// A placeholder bar in the shape of the content that is on its way, in the design's quiet fill (paper-2).
export function Skeleton({ className }: { className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={cn(
        "block h-4 rounded-md bg-paper-2 motion-safe:animate-pulse",
        className,
      )}
    />
  );
}

// Wraps placeholders so assistive technology hears one "Loading" announcement instead of empty shapes.
export function LoadingRegion({
  label,
  className,
  children,
}: {
  label: string;
  className?: string;
  children: ReactNode;
}) {
  return (
    <div
      role="status"
      aria-busy="true"
      aria-live="polite"
      className={className}
    >
      <span className="sr-only">{label}</span>
      {children}
    </div>
  );
}

const WIDTHS = ["w-3/4", "w-1/2", "w-2/3", "w-5/12"];

// Placeholder rows for a list table, one bar per column.
export function TableRowsSkeleton({
  columns,
  rows = 4,
}: {
  columns: number;
  rows?: number;
}) {
  return (
    <>
      {Array.from({ length: rows }, (_, row) => (
        <tr key={row}>
          {Array.from({ length: columns }, (_, column) => (
            <td key={column}>
              <Skeleton className={WIDTHS[(row + column) % WIDTHS.length]} />
              {column === 0 && <Skeleton className="mt-2 h-3 w-1/3" />}
            </td>
          ))}
        </tr>
      ))}
    </>
  );
}

// Placeholder dashboard cards.
export function CardGridSkeleton({ count = 3 }: { count?: number }) {
  return (
    <LoadingRegion
      label="Loading your dashboard"
      className="grid grid-cols-[repeat(auto-fill,minmax(300px,1fr))] items-start gap-4 max-[480px]:grid-cols-1"
    >
      {Array.from({ length: count }, (_, index) => (
        <Card key={index}>
          <Skeleton className="w-2/5" />
          <Skeleton className="h-3 w-1/3" />
          <Skeleton className="mt-2 h-8 w-3/5" />
          <Skeleton className="h-3 w-4/5" />
        </Card>
      ))}
    </LoadingRegion>
  );
}

// Placeholder form cards: a header and a grid of labelled fields each.
export function FormSkeleton({
  cards = 2,
  fields = 4,
  label,
}: {
  cards?: number;
  fields?: number;
  label: string;
}) {
  return (
    <LoadingRegion label={label}>
      <FormLayout>
        {Array.from({ length: cards }, (_, card) => (
          <Card key={card} density="form">
            <Skeleton className="w-1/4" />
            <Grid2>
              {Array.from({ length: fields }, (_, field) => (
                <div key={field} className="flex flex-col gap-1.5">
                  <Skeleton className="h-3.5 w-1/3" />
                  <Skeleton className="h-10 rounded-[10px]" />
                </div>
              ))}
            </Grid2>
          </Card>
        ))}
      </FormLayout>
    </LoadingRegion>
  );
}

// Placeholder rows for a card list or a report grid.
export function ListSkeleton({ rows = 3 }: { rows?: number }) {
  return (
    <div className="mt-1" aria-hidden="true">
      {Array.from({ length: rows }, (_, row) => (
        <div
          key={row}
          className="flex justify-between gap-3 border-t border-divider py-3"
        >
          <div className="flex w-1/2 flex-col gap-1.5">
            <Skeleton className="w-3/4" />
            <Skeleton className="h-3 w-1/2" />
          </div>
          <Skeleton className="w-20" />
        </div>
      ))}
    </div>
  );
}

export function StatGridSkeleton({ count = 5 }: { count?: number }) {
  return (
    <div
      className="grid grid-cols-[repeat(auto-fill,minmax(160px,1fr))] gap-3"
      aria-hidden="true"
    >
      {Array.from({ length: count }, (_, index) => (
        <div
          key={index}
          className="flex flex-col gap-2 rounded-xl border border-line bg-surface px-4 py-2.5"
        >
          <Skeleton className="h-3 w-2/3" />
          <Skeleton className="h-5 w-1/2" />
        </div>
      ))}
    </div>
  );
}
