"use client";

import type { PettyCashEntry, PettyCashFigures } from "@xcode/shared/pettyCash";
import { pettyCashExportPath } from "@xcode/shared/reports";

import { useFormats } from "../../lib/formats";
import { ExportMenu } from "../reports/ExportMenu";
import type { useReportExport } from "../reports/exportReport";
import { Button } from "../ui";

type Range = { from: string; to: string };

// The approve button at the end of the bar (the design's pcApproveBtn): the ticked entries when there are any,
// otherwise everything waiting in what is shown, "day" for all managers, "these" for one, "all" over several days.
export function ApproveButton({
  ticked,
  canApproveDay,
  range,
  holderId,
  figures,
  busy,
  onApprove,
}: {
  ticked: PettyCashEntry[];
  canApproveDay: boolean;
  range: Range;
  holderId: string;
  figures: PettyCashFigures | undefined;
  busy: boolean;
  onApprove: (path: string, body: unknown, nothing: string) => void;
}) {
  const formats = useFormats();
  const holder = holderId ? { holderId } : {};
  if (ticked.length)
    return (
      <Button
        tone="ok"
        disabled={busy}
        onClick={() =>
          onApprove(
            "setup/pettycash/approve",
            {
              entries: ticked.map((entry) => ({
                id: entry.id,
                version: entry.version,
              })),
            },
            "Nothing to approve.",
          )
        }
      >
        {`Approve ${ticked.length}, ${formats.kes(ticked.reduce((sum, entry) => sum + entry.total, 0))}`}
      </Button>
    );
  if (!canApproveDay) return null;
  const oneDay = range.from === range.to;
  const none = !figures?.waitingCount;
  return (
    <Button
      tone="ok"
      disabled={none || busy}
      onClick={() =>
        onApprove(
          "setup/pettycash/approve-day",
          oneDay
            ? { date: range.from, ...holder }
            : { date: range.from, to: range.to, ...holder },
          oneDay
            ? "Nothing to approve on this day."
            : "Nothing to approve in this period.",
        )
      }
    >
      {`Approve ${oneDay ? (holderId ? "these" : "day") : "all"}${none ? "" : `, ${formats.kes(figures.waiting)}`}`}
    </Button>
  );
}

// Export of the tab shown, for the same period, manager, status and search.
export function PettyCashExport({
  exporter,
  tab,
  range,
  holderId,
  status,
  query,
}: {
  exporter: ReturnType<typeof useReportExport>;
  tab: "expenses" | "cash";
  range: Range;
  holderId: string;
  status: string;
  query: string;
}) {
  return (
    <ExportMenu
      disabled={exporter.exporting}
      onExport={(format) =>
        void exporter.run(
          pettyCashExportPath({
            from: range.from,
            to: range.to,
            holderId: holderId || undefined,
            view: tab,
            status: tab === "expenses" && status !== "all" ? status : undefined,
            q: query || undefined,
            format,
          }),
          tab === "cash" ? "Petty cash, cash received" : "Petty cash, expenses",
          range,
          format,
        )
      }
    />
  );
}
