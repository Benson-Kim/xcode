import type { RefObject } from "react";

import type { WeekDay } from "@xcode/shared/dates";
import { percentText } from "@xcode/shared/format";
import type { RevenueWeek } from "@xcode/shared/revenue";

import { useFormats } from "../../lib/formats";
import { cn } from "../ui";
import { DAY_COLUMN, HEAD } from "./styles";
import type { OpenDay } from "./useCaptureFlow";
import type { useGridRows } from "./useGridRows";
import { VehicleRow } from "./VehicleRow";

type Rows = ReturnType<typeof useGridRows>;

// Stands in for the rows outside the window, so the page keeps the whole grid's height.
function OffscreenRows({ height }: { height: number }) {
  return (
    <tr aria-hidden="true">
      <td colSpan={10} className="border-0 p-0" style={{ height }} />
    </tr>
  );
}

export function WeekGrid({
  data,
  days,
  today,
  canCapture,
  grid,
  gridRef,
  bodyRef,
  onOpenDay,
}: {
  data: RevenueWeek;
  days: WeekDay[];
  today: string;
  canCapture: boolean;
  grid: Rows;
  gridRef: RefObject<HTMLDivElement | null>;
  bodyRef: RefObject<HTMLTableSectionElement | null>;
  onOpenDay: OpenDay;
}) {
  const formats = useFormats();
  const { vehicles, expanded, windowed, rowIndex, rowCount, rows, toggle } =
    grid;
  return (
    // relative: the card is the containing block for the screen-reader-only labels (absolutely positioned) in the
    // grid, so they scroll with it instead of widening the page at tablet widths.
    <div
      ref={gridRef}
      tabIndex={-1}
      className="relative mt-4 overflow-x-auto rounded-[14px] border border-card-line bg-surface"
    >
      <table
        aria-rowcount={windowed ? rowCount : undefined}
        className="w-full border-collapse min-[721px]:min-w-225"
      >
        <caption className="sr-only">
          Revenue by vehicle and day,{" "}
          {formats.formatDateRange(data.weekStart, data.weekThrough)}
        </caption>
        <GridHead days={days} today={today} windowed={windowed} />
        <tbody ref={bodyRef}>
          {vehicles.length === 0 ? (
            <tr>
              <td colSpan={10} className="px-4 py-6 text-center text-grey">
                No vehicles.
              </td>
            </tr>
          ) : (
            <>
              {rows.before > 0 && <OffscreenRows height={rows.before} />}
              {vehicles.slice(rows.start, rows.end).map((item, offset) => (
                <VehicleRow
                  key={item.id}
                  vehicle={item}
                  isOpen={expanded.has(item.id)}
                  days={days}
                  today={today}
                  canCapture={canCapture}
                  rowIndex={
                    windowed ? rowIndex[rows.start + offset] : undefined
                  }
                  measure={rows.measure}
                  onToggle={toggle}
                  onOpenDay={onOpenDay}
                />
              ))}
              {rows.after > 0 && <OffscreenRows height={rows.after} />}
            </>
          )}
        </tbody>
        {vehicles.length > 0 && (
          <GridTotals data={data} rowIndex={windowed ? rowCount : undefined} />
        )}
      </table>
    </div>
  );
}

function GridHead({
  days,
  today,
  windowed,
}: {
  days: WeekDay[];
  today: string;
  windowed: boolean;
}) {
  return (
    <thead>
      <tr aria-rowindex={windowed ? 1 : undefined}>
        <th
          scope="col"
          className={cn(HEAD, "sticky left-0 z-1 min-w-35 text-left")}
        >
          Vehicle
        </th>
        {days.map(({ date, shortName, dayOfMonth }) => (
          <th
            key={date}
            scope="col"
            aria-current={date === today ? "date" : undefined}
            className={cn(
              HEAD,
              DAY_COLUMN,
              "text-right",
              date === today && "shadow-[inset_0_-3px_0_var(--color-blue)]",
            )}
          >
            {shortName}{" "}
            <span
              className={cn(
                "block text-base font-bold text-navy",
                date === today && "text-blue-dark",
              )}
            >
              {dayOfMonth}
            </span>
            {date === today && <span className="sr-only">, today</span>}
          </th>
        ))}
        <th scope="col" className={cn(HEAD, "text-right")}>
          Week
        </th>
        <th scope="col" className={cn(HEAD, "text-right")}>
          vs expected
        </th>
      </tr>
    </thead>
  );
}

function GridTotals({
  data,
  rowIndex,
}: {
  data: RevenueWeek;
  rowIndex: number | undefined;
}) {
  const formats = useFormats();
  return (
    <tfoot>
      <tr aria-rowindex={rowIndex} className="bg-paper font-bold">
        <th
          scope="row"
          className="sticky left-0 z-1 bg-paper px-2 py-2 text-left"
        >
          All vehicles
        </th>
        {(data.dayTotals ?? []).map(({ date, amount }) => (
          <td
            key={date}
            className={cn("px-2 py-2 text-right tabular-nums", DAY_COLUMN)}
          >
            {amount ? formats.formatNumber(amount) : ""}
          </td>
        ))}
        <td className="px-2 py-2 text-right tabular-nums">
          {formats.formatNumber(data.totalAmount)}
        </td>
        <td className="px-2 py-2 text-right tabular-nums">
          {data.percent === null ? "" : percentText(data.percent)}
        </td>
      </tr>
    </tfoot>
  );
}
