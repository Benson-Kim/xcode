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
import {
  DataTable,
  Figure,
  Pager,
  StatGridSkeleton,
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

function FigureCards({ table }: { table: ReportTable }) {
  const { formats, units } = useReportText();
  const show = (figure: ReportFigure, tone: "close" | "plain") => (
    <Figure
      key={figure.label}
      label={figure.label}
      value={numberText(formats, units, figure.kind, figure.value)}
      tone={tone}
      bad={figure.kind === "net" && figure.value < 0}
    />
  );
  return (
    <div
      role="group"
      aria-label="Report figures"
      className="grid grid-cols-[repeat(auto-fit,minmax(210px,1fr))] gap-3.5"
    >
      {show(table.headline, "close")}
      {table.figures.map((figure) => show(figure, "plain"))}
    </div>
  );
}

export type ReportPaging = {
  page: number;
  pageSize: number;
  setPage: (page: number) => void;
  setPageSize: (pageSize: number) => void;
};

// A report as the server built it: its figures, then one page of its rows with a footer that counts and adds up
// every matching row, and the pager.
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
      <div className="mt-5">
        {table ? <FigureCards table={table} /> : <StatGridSkeleton count={4} />}
      </div>
      <DataTable
        columns={columns}
        loading={loading || (!table && !failed)}
        loadingLabel="Loading the report"
        isEmpty={!table?.rows.length}
        failed={failed}
        emptyMessage="Nothing to show."
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
        {table && (
          <Tr>
            {table.columns.map((column, index) => (
              <Td
                key={column.key}
                numeric={NUMERIC_KINDS.includes(column.kind)}
                className="font-bold"
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
        )}
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
