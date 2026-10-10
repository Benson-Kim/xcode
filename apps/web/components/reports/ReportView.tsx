"use client";

import { useMemo } from "react";

import { plural } from "@xcode/shared/format";
import type {
  ReportColumn,
  ReportFigure,
  ReportTable,
} from "@xcode/shared/reports";

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
import { CellValue, NUMERIC_KINDS, numberText, type Units } from "./cells";

export function useReportText() {
  const formats = useFormats();
  const locale = useAppearance().appearance?.formats.locale ?? "en-GB";
  const units: Units = useMemo(() => unitsFormat(locale), [locale]);
  return { formats, units };
}

const isMoney = (figure: ReportFigure) =>
  figure.kind === "money" || figure.kind === "net";

// The headline card of a report: its headline figure and the others beside it.
export function ReportBand({ table }: { table: ReportTable | undefined }) {
  const { formats, units } = useReportText();
  if (!table) return <BandSkeleton />;
  const { headline } = table;
  return (
    <div role="group" aria-label="Report figures" className="contents">
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
            value: numberText(formats, units, figure.kind, figure.value),
            tone:
              figure.kind === "net" && figure.value < 0
                ? ("neg" as const)
                : undefined,
          }))}
        />
      )}
    </div>
  );
}

export type ReportPaging = {
  page: number;
  pageSize: number;
  setPage: (page: number) => void;
  setPageSize: (pageSize: number) => void;
};

// A report as the server built it: one page of its rows with a footer that counts and adds up every matching
// row, and the pager.
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
  const currency = formats.currencyCode();
  const named = (column: ReportColumn) =>
    column.kind === "money" || column.kind === "net"
      ? `${column.label} (${currency})`
      : column.label;
  const columns: Column[] = (table?.columns ?? []).map((column) => ({
    label: named(column),
    numeric: NUMERIC_KINDS.includes(column.kind),
  }));

  return (
    <>
      <DataTable
        columns={columns}
        loading={loading || (!table && !failed)}
        loadingLabel="Loading the report"
        isEmpty={!table?.rows.length}
        failed={failed}
        emptyMessage="Nothing to show."
        footer={
          table && (
            <Tr>
              {table.columns.map((column, index) => (
                <Td
                  key={column.key}
                  numeric={NUMERIC_KINDS.includes(column.kind)}
                >
                  {index === 0
                    ? plural(table.total, "row", "rows")
                    : table.totals[index] == null
                      ? ""
                      : numberText(
                          formats,
                          units,
                          column.kind,
                          table.totals[index],
                          false,
                        )}
                </Td>
              ))}
            </Tr>
          )
        }
      >
        {table?.rows.map((row, at) => (
          <Tr key={at}>
            {table.columns.map((column, index) => (
              <Td
                key={column.key}
                label={named(column)}
                numeric={NUMERIC_KINDS.includes(column.kind)}
              >
                <CellValue
                  formats={formats}
                  units={units}
                  kind={column.kind}
                  cell={row[index]}
                />
              </Td>
            ))}
          </Tr>
        ))}
      </DataTable>
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
