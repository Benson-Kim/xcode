import type { RefObject } from "react";

import type { WeekDay } from "@xcode/shared/dates";
import type { RevenueWeek } from "@xcode/shared/revenue";

import { useFormats } from "../../lib/formats";
import { cn } from "../ui";
import type { OpenDay } from "./useCaptureFlow";
import type { useGridRows } from "./useGridRows";
import { GapChip, VehicleRow } from "./VehicleRow";

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
  searching,
  grid,
  gridRef,
  bodyRef,
  onOpenDay,
}: {
  data: RevenueWeek;
  days: WeekDay[];
  today: string;
  canCapture: boolean;
  searching: boolean;
  grid: Rows;
  gridRef: RefObject<HTMLDivElement | null>;
  bodyRef: RefObject<HTMLTableSectionElement | null>;
  onOpenDay: OpenDay;
}) {
  const formats = useFormats();
  const { vehicles, windowed, rowIndex, rowCount, rows } = grid;
  return (
    <div id="revT" ref={gridRef} tabIndex={-1}>
      <div className="tbl">
        {/* relative: the containing block for the screen-reader-only labels, so they scroll with the grid instead
            of widening the page at tablet widths. */}
        <div className="scroll relative">
          <table
            aria-rowcount={windowed ? rowCount : undefined}
            className="grid"
          >
            <caption className="sr-only">
              Revenue by vehicle and day,{" "}
              {formats.formatDateRange(data.weekStart, data.weekThrough)}
            </caption>
            <GridHead days={days} today={today} windowed={windowed} />
            <tbody ref={bodyRef}>
              {vehicles.length === 0 ? (
                <tr>
                  <td colSpan={10} className="empty">
                    {searching ? "No vehicle matches." : "No vehicles."}
                  </td>
                </tr>
              ) : (
                <>
                  {rows.before > 0 && <OffscreenRows height={rows.before} />}
                  {vehicles.slice(rows.start, rows.end).map((item, offset) => (
                    <VehicleRow
                      key={item.id}
                      vehicle={item}
                      today={today}
                      canCapture={canCapture}
                      rowIndex={
                        windowed ? rowIndex[rows.start + offset] : undefined
                      }
                      measure={rows.measure}
                      onOpenDay={onOpenDay}
                    />
                  ))}
                  {rows.after > 0 && <OffscreenRows height={rows.after} />}
                </>
              )}
            </tbody>
            {vehicles.length > 0 && (
              <GridTotals
                data={data}
                rowIndex={windowed ? rowCount : undefined}
              />
            )}
          </table>
        </div>
      </div>
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
        <th scope="col">Vehicle</th>
        {days.map(({ date, shortName, dayOfMonth }) => (
          <th
            key={date}
            scope="col"
            aria-current={date === today ? "date" : undefined}
            className={cn("r", date === today && "today")}
          >
            {`${shortName} ${dayOfMonth}`}
            {date === today && <span className="sr-only">, today</span>}
          </th>
        ))}
        <th scope="col" className="r">
          Week total
        </th>
        <th scope="col" className="r">
          Gap to target
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
      <tr aria-rowindex={rowIndex}>
        <td>{`${data.vehicles.length} vehicle${data.vehicles.length === 1 ? "" : "s"}`}</td>
        {(data.dayTotals ?? []).map(({ date, amount }) => (
          <td key={date} className="r">
            {amount ? formats.formatNumber(amount) : ""}
          </td>
        ))}
        <td className="r">{formats.formatNumber(data.totalAmount)}</td>
        <td className="r">
          <GapChip gap={data.gap} band={data.gapBand} />
        </td>
      </tr>
    </tfoot>
  );
}
