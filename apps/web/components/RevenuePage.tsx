"use client";

import { useRef } from "react";

import { useFormats } from "../lib/formats";
import { useSession } from "../lib/session-context";
import { openAt } from "./revenue/capture";
import { CaptureDialog } from "./revenue/CaptureDialog";
import { useCaptureFlow } from "./revenue/useCaptureFlow";
import { useGridRows } from "./revenue/useGridRows";
import { useWeekGrid } from "./revenue/useWeekGrid";
import { WeekGrid } from "./revenue/WeekGrid";
import { WeekToolbar } from "./revenue/WeekToolbar";
import { Banner, LoadingRegion, PageHeader, TableRowsSkeleton } from "./ui";

export function RevenuePage() {
  const { can } = useSession();
  const formats = useFormats();
  const canView = can("revenue.view");
  const canCapture = can("revenue.capture");
  const gridRef = useRef<HTMLDivElement>(null);
  const bodyRef = useRef<HTMLTableSectionElement>(null);

  const grid = useWeekGrid(canView, canCapture);
  const { week, data, today } = grid;
  const rows = useGridRows(data, bodyRef);
  const flow = useCaptureFlow({
    data,
    canCapture,
    today,
    formats,
    reload: week.reload,
    markStale: grid.markStale,
    gridRef,
    vehicles: rows.vehicles,
    rows: rows.rows,
  });

  if (!canView) {
    return (
      <section>
        <PageHeader
          title="Revenue"
          description="Your access does not include revenue records."
        />
      </section>
    );
  }

  return (
    <section>
      <PageHeader title="Revenue" />
      <WeekToolbar
        start={grid.start}
        shown={grid.shown}
        data={data}
        companyId={grid.companyId}
        first={grid.first}
        stale={grid.stale}
        onWeek={grid.setWeekStart}
        onCompany={grid.setCompanyId}
        onCapture={(target, from) =>
          flow.open(openAt(formats, target.vehicle, target.date, today), from)
        }
      />

      {week.error && <Banner className="mt-4">{week.error}</Banner>}

      {!data ? (
        week.loading && (
          <LoadingRegion
            label="Loading revenue"
            className="mt-4 overflow-hidden rounded-[14px] border border-card-line bg-surface"
          >
            <table className="w-full border-collapse">
              <tbody>
                <TableRowsSkeleton columns={4} />
              </tbody>
            </table>
          </LoadingRegion>
        )
      ) : (
        <WeekGrid
          data={data}
          days={grid.days}
          today={today}
          canCapture={canCapture}
          grid={rows}
          gridRef={gridRef}
          bodyRef={bodyRef}
          onOpenDay={flow.openDay}
        />
      )}

      <CaptureDialog flow={flow} canChooseReason={can("revenue.no_earnings")} />
    </section>
  );
}
