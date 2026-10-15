"use client";

import { useRef } from "react";

import { startOfWeek } from "@xcode/shared/dates";
import { revenueExportPath } from "@xcode/shared/reports";

import { useResource } from "../lib/data";
import { useFormats } from "../lib/formats";
import { useSession } from "../lib/session-context";
import type { MyScope } from "../lib/types";
import { ExportMenu } from "./reports/ExportMenu";
import { useReportExport } from "./reports/exportReport";
import { captureStart, DEFAULT_LOW_DAY_THRESHOLD } from "./revenue/capture";
import { CaptureDialog } from "./revenue/CaptureDialog";
import { useCaptureFlow } from "./revenue/useCaptureFlow";
import { useGridRows } from "./revenue/useGridRows";
import { useWeekGrid } from "./revenue/useWeekGrid";
import { WeekGrid } from "./revenue/WeekGrid";
import { WeekToolbar } from "./revenue/WeekToolbar";
import {
  Banner,
  Button,
  LoadingRegion,
  PageHeader,
  TableRowsSkeleton,
} from "./ui";

// The week grid (v2.30): one row a vehicle, one column a day, then Week total and Gap to target. A tap on a cell
// opens a pop up for that vehicle and day; "Capture revenue" opens the oldest missing day, or today.
export function RevenuePage() {
  const { can } = useSession();
  const formats = useFormats();
  const canView = can("revenue.view");
  const canCapture = can("revenue.capture");
  const gridRef = useRef<HTMLDivElement>(null);
  const bodyRef = useRef<HTMLTableSectionElement>(null);

  const grid = useWeekGrid(canView);
  const { week, data, today } = grid;
  const rows = useGridRows(data, bodyRef);
  // The earliest day this person may still change (the back-dating limit, v2.32), for the pop up's date control.
  const scope = useResource<MyScope>(canView ? "setup/access/me" : null);
  const earliest = scope.data?.earliest ?? null;
  const threshold = data?.lowDayThreshold ?? DEFAULT_LOW_DAY_THRESHOLD;
  const flow = useCaptureFlow({
    data,
    canCapture,
    reload: week.reload,
    markStale: grid.markStale,
    gridRef,
    vehicles: rows.vehicles,
    rows: rows.rows,
  });
  const exporter = useReportExport();

  if (!canView) {
    return (
      <PageHeader
        title="Revenue"
        description="Your access does not include revenue records."
      />
    );
  }

  function capture(from: HTMLElement) {
    if (!data) return;
    const start = captureStart(data, earliest);
    if (!start) return;
    // The grid moves to that day's week; the pop up reads the day from it, or from the vehicle's own week meanwhile.
    const weekStart = startOfWeek(start.date, formats.firstDayOfWeek());
    if (weekStart !== data.weekStart) grid.setWeekStart(weekStart);
    flow.open({ vehicleId: start.vehicleId, date: start.date, done: [] }, from);
  }

  return (
    <>
      <PageHeader
        title="Revenue"
        actions={
          canCapture && (
            <Button
              tone="primary"
              disabled={grid.stale || !data}
              aria-busy={grid.stale ? true : undefined}
              onClick={(event) => capture(event.currentTarget)}
            >
              Capture revenue
            </Button>
          )
        }
      />
      <WeekToolbar
        start={grid.start}
        shown={grid.shown}
        data={data}
        companyId={grid.companyId}
        search={grid.search}
        exportMenu={
          (can("revenue.export") || can("reports.export")) && (
            <ExportMenu
              disabled={exporter.exporting || !data}
              onExport={(format) =>
                data &&
                void exporter.run(
                  revenueExportPath({
                    weekStart: data.weekStart,
                    companyId: grid.companyId || undefined,
                    format,
                  }),
                  "Revenue",
                  { from: data.weekStart, to: data.weekThrough },
                  format,
                )
              }
            />
          )
        }
        onWeek={grid.setWeekStart}
        onCompany={grid.setCompanyId}
        onSearch={grid.setSearch}
      />

      {exporter.error && <Banner>{exporter.error}</Banner>}
      {week.error && <Banner>{week.error}</Banner>}

      {!data ? (
        week.loading && (
          <LoadingRegion label="Loading revenue" className="tbl">
            <div className="scroll">
              <table>
                <tbody>
                  <TableRowsSkeleton columns={4} />
                </tbody>
              </table>
            </div>
          </LoadingRegion>
        )
      ) : (
        <WeekGrid
          data={data}
          days={grid.days}
          today={today}
          canCapture={canCapture}
          searching={grid.searching}
          grid={rows}
          gridRef={gridRef}
          bodyRef={bodyRef}
          onOpenDay={flow.openDay}
        />
      )}

      <CaptureDialog
        flow={flow}
        today={today}
        earliest={earliest}
        threshold={threshold}
      />
    </>
  );
}
