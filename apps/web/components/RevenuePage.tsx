"use client";

import { useRef, useState } from "react";

import { useFormats } from "../lib/formats";
import { useSession } from "../lib/session-context";
import { CaptureDialog } from "./revenue/CaptureDialog";
import { captureDayFor, weekStartFor } from "./revenue/fleetDay";
import { FleetDayDialog } from "./revenue/FleetDayDialog";
import { useCaptureFlow } from "./revenue/useCaptureFlow";
import { useGridRows } from "./revenue/useGridRows";
import { useWeekGrid } from "./revenue/useWeekGrid";
import { WeekGrid } from "./revenue/WeekGrid";
import { WeekToolbar } from "./revenue/WeekToolbar";
import {
  Banner,
  LoadingRegion,
  PageHeader,
  TableRowsSkeleton,
  useToast,
} from "./ui";

export function RevenuePage() {
  const { can } = useSession();
  const formats = useFormats();
  const toast = useToast();
  const canView = can("revenue.view");
  const canCapture = can("revenue.capture");
  const gridRef = useRef<HTMLDivElement>(null);
  const bodyRef = useRef<HTMLTableSectionElement>(null);

  const grid = useWeekGrid(canView);
  const { week, data, today } = grid;
  const rows = useGridRows(data, bodyRef);
  const flow = useCaptureFlow({
    data,
    canCapture,
    today,
    reload: week.reload,
    markStale: grid.markStale,
    gridRef,
    vehicles: rows.vehicles,
    rows: rows.rows,
  });
  // The day Capture revenue is open on, or null while it is closed.
  const [capturing, setCapturing] = useState<string | null>(null);

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
        canCapture={canCapture}
        stale={grid.stale}
        onWeek={grid.setWeekStart}
        onCompany={grid.setCompanyId}
        onCapture={(shown) => setCapturing(captureDayFor(shown))}
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
      <FleetDayDialog
        date={capturing}
        today={today}
        companyId={grid.companyId}
        companyName={
          data?.companies.find((company) => company.id === grid.companyId)
            ?.name ?? ""
        }
        canChooseReason={can("revenue.no_earnings")}
        onDate={setCapturing}
        onClose={() => setCapturing(null)}
        onSaved={(date) => {
          setCapturing(null);
          toast(`Saved ${formats.formatWeekdayDate(date)}`);
          // The grid moves to the saved day's week and reads it again.
          const start = data ? weekStartFor(date, data.weekStart) : "";
          if (data && start !== data.weekStart) grid.setWeekStart(start);
          else {
            grid.markStale();
            week.reload();
          }
        }}
      />
    </section>
  );
}
