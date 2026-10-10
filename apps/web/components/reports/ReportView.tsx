"use client";

import { useMemo } from "react";

import { plural } from "@xcode/shared/format";
import type { ReportFigure, ReportTable } from "@xcode/shared/reports";

import { useAppearance } from "../../lib/appearance";
import { useFormats } from "../../lib/formats";
import { unitsFormat } from "../pettycash/labels";
import { BandSkeleton } from "../revenue/RegPlate";
import {
  BandFigure,
  BandStats,
  DataTable,
  Pager,
  Td,
  Tr,
  type Column,
} from "../ui";
import { ReportTd, isNumeric, numberText, type Units } from "./cells";

export function useReportText() {
  const formats = useFormats();
  const locale = useAppearance().appearance?.formats.locale ?? "en-GB";
  const units: Units = useMemo(() => unitsFormat(locale), [locale]);
  return { formats, units };
}

const isMoney = (figure: ReportFigure) =>
  figure.kind === "money" || figure.kind === "net";

// The headline card of a report: its headline figure and the others beside it, amounts without the currency as in
// the design.
export function ReportBand({ table }: { table: ReportTable | undefined }) {
  const { formats, units } = useReportText();
  if (!table) return <BandSkeleton />;
  const { headline } = table;
  return (
    <>
      <BandFigure
        label={headline.label}
        value={numberText(formats, units, headline.kind, headline.value, false)}
        currency={isMoney(headline)}
        negative={headline.kind === "net" && headline.value < 0}
      />
      {table.figures.length > 0 && (
        <BandStats
          items={table.figures.map((figure) => ({
            label: figure.label,
            value: numberText(formats, units, figure.kind, figure.value, false),
            tone:
              figure.kind === "net" && figure.value < 0
                ? ("neg" as const)
                : undefined,
          }))}
        />
      )}
    </>
  );
}

export type ReportPaging = {
  page: number;
  pageSize: number;
  setPage: (page: number) => void;
  setPageSize: (pageSize: number) => void;
};

// A report as the server built it (#repT): one page of its rows with a footer that counts and adds up every
// matching row, and the pager.
export function ReportView({
  table,
  loading,
  failed,
  paging,
}: {
  table: ReportTable | undefined;
  loading: boolean;
  failed: boolean;
  paging: ReportPaging;
}) {
  const { formats, units } = useReportText();
  const columns: Column[] = (table?.columns ?? []).map((column) => ({
    label: column.label,
    numeric: isNumeric(column),
  }));

  return (
    <>
      <div id="repT">
        <DataTable
          className="rep"
          columns={columns}
          loading={loading || (!table && !failed)}
          loadingLabel="Loading the report"
          isEmpty={!table?.rows.length}
          failed={failed}
          emptyMessage="Nothing to show."
          footer={
            table && (
              <Tr>
                {table.columns.map((column, index) =>
                  index === 0 ? (
                    <Td key={column.key}>
                      {plural(table.total, "row", "rows")}
                    </Td>
                  ) : (
                    <ReportTd
                      key={column.key}
                      formats={formats}
                      units={units}
                      column={column}
                      index={index}
                      cell={table.totals[index] ?? null}
                      foot
                    />
                  ),
                )}
              </Tr>
            )
          }
        >
          {table?.rows.map((row, at) => (
            <Tr key={at}>
              {table.columns.map((column, index) => (
                <ReportTd
                  key={column.key}
                  formats={formats}
                  units={units}
                  column={column}
                  index={index}
                  cell={row[index]}
                />
              ))}
            </Tr>
          ))}
        </DataTable>
      </div>
      <Pager
        page={paging.page}
        pageSize={paging.pageSize}
        total={table?.total ?? 0}
        onPageChange={paging.setPage}
        onPageSizeChange={paging.setPageSize}
      />
    </>
  );
}
