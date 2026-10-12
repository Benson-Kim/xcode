"use client";

import { useRef, useState } from "react";

import { revenueExportPath } from "@xcode/shared/reports";

import { useFormats } from "../lib/formats";
import { useSession } from "../lib/session-context";
import { ExportMenu } from "./reports/ExportMenu";
import { useReportExport } from "./reports/exportReport";
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
  Button,
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
  const exporter = useReportExport();

  if (!canView) {
    return (
      <PageHeader
        title="Revenue"
        description="Your access does not include revenue records."
      />
    );
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
              onClick={() => data && setCapturing(captureDayFor(data))}
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
        exportMenu={
          can("reports.export") && (
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
    </>
  );
}
