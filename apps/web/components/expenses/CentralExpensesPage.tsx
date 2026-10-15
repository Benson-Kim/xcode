"use client";

import { useState } from "react";

import {
  expenseLedgerPath,
  type ExpenseLedger,
  type ExpenseLedgerRow,
} from "@xcode/shared/expenses";
import { presetPeriod, type Period } from "@xcode/shared/periods";
import { canSee, NAV } from "@xcode/shared/permissions";
import { expenseExportPath } from "@xcode/shared/reports";

import { useAppearance } from "../../lib/appearance";
import { useResource } from "../../lib/data";
import { useFormats } from "../../lib/formats";
import { useSession } from "../../lib/session-context";
import { useDebounced } from "../../lib/useDebounced";
import { PeriodPicker } from "../period/PeriodPicker";
import { ExportMenu } from "../reports/ExportMenu";
import { useReportExport } from "../reports/exportReport";
import { BandSkeleton } from "../revenue/RegPlate";
import {
  Banner,
  Button,
  HeroBand,
  PageHeader,
  Pager,
  RetryBanner,
  usePaging,
  useToast,
} from "../ui";
import { ExpenseDialog, type ExpenseDialogState } from "./ExpenseDialog";
import { FigureCards } from "./FigureCards";
import { LedgerTable } from "./LedgerTable";
import { RemoveExpenseDialog } from "./RemoveExpenseDialog";
import { SourceSelect, type SourceFilter } from "./SourceSelect";

// The day a new expense opens on: today when the period holds it, otherwise the period's last day.
function newExpenseDate(period: Period, businessDate: string) {
  return period.from <= businessDate && businessDate <= period.to
    ? businessDate
    : period.to;
}

export function CentralExpensesPage({
  onOpenPettyCash,
}: {
  onOpenPettyCash: (date: string) => void;
}) {
  const formats = useFormats();
  const toast = useToast();
  const { can } = useSession();
  const appearanceDate = useAppearance().appearance?.businessDate;

  const [chosen, setChosen] = useState<Period | null>(null);
  const [source, setSource] = useState<SourceFilter>("all");
  const [search, setSearch] = useState("");
  const [notice, setNotice] = useState("");
  const [dialog, setDialog] = useState<ExpenseDialogState>(null);
  const [removing, setRemoving] = useState<ExpenseLedgerRow | null>(null);
  const exporter = useReportExport();

  const query = useDebounced(search.trim());

  const firstDayOfWeek = formats.firstDayOfWeek();
  const [known, setKnown] = useState<ExpenseLedger | undefined>(undefined);
  const businessDate = known?.businessDate ?? appearanceDate ?? null;
  const period =
    chosen ??
    (businessDate
      ? presetPeriod("thisWeek", businessDate, firstDayOfWeek)
      : null);

  const paging = usePaging(`${period?.from}|${period?.to}|${source}|${query}`);
  const path = period
    ? expenseLedgerPath({
        from: period.from,
        to: period.to,
        source: source === "all" ? undefined : source,
        q: query || undefined,
        page: paging.page,
        pageSize: paging.pageSize,
      })
    : null;
  const ledger = useResource<ExpenseLedger>(path);
  if (ledger.data && ledger.data !== known) setKnown(ledger.data);
  if (ledger.data) paging.stepBack(ledger.data.total);

  const permissions = known?.permissions;
  const rows = ledger.data?.items ?? [];
  const total = ledger.data?.total ?? 0;
  const figures =
    known && period && known.from === period.from && known.to === period.to
      ? known.figures
      : undefined;
  const mayOpenPettyCash = canSee(NAV.pettycash, can);
  const filtered = source !== "all" || query !== "";

  const formDate =
    period && businessDate
      ? newExpenseDate(period, businessDate)
      : businessDate;

  const refresh = ledger.reload;

  // A refusal keeps the explanation on the page; a save says so in a toast.
  function done(explain: string, toasted?: string) {
    setNotice(explain);
    setDialog(null);
    setRemoving(null);
    if (toasted) toast(toasted);
    refresh();
  }

  return (
    <>
      <PageHeader
        title="Central expenses"
        description=""
        actions={
          permissions?.canRecord && (
            <Button tone="primary" onClick={() => setDialog({})}>
              Record expense
            </Button>
          )
        }
      />

      <HeroBand
        period={
          period && businessDate ? (
            <PeriodPicker
              period={period}
              businessDate={businessDate}
              firstDayOfWeek={firstDayOfWeek}
              onChange={setChosen}
            />
          ) : undefined
        }
        tools={
          <LedgerTools
            source={source}
            onSource={setSource}
            search={search}
            onSearch={setSearch}
            exporter={can("reports.export") ? exporter : undefined}
            period={period}
            query={query}
          />
        }
      >
        {figures ? <FigureCards figures={figures} /> : <BandSkeleton />}
      </HeroBand>

      {notice && <Banner>{notice}</Banner>}
      {exporter.error && <Banner>{exporter.error}</Banner>}

      {ledger.error && !known && (
        <RetryBanner onRetry={ledger.reload}>{ledger.error}</RetryBanner>
      )}

      {ledger.error && known && <Banner>{ledger.error}</Banner>}

      <div id="expT">
        <LedgerTable
          rows={rows}
          total={total}
          amount={ledger.data?.amount ?? 0}
          loading={path === null ? !ledger.error : ledger.loading}
          failed={Boolean(ledger.error)}
          filtered={filtered}
          actions={{
            onEdit: (row) => setDialog({ entry: row }),
            onRemove: setRemoving,
            onOpenDay: mayOpenPettyCash
              ? (row) => onOpenPettyCash(row.date)
              : undefined,
          }}
        />
      </div>

      <Pager
        page={paging.page}
        pageSize={paging.pageSize}
        total={total}
        onPageChange={paging.setPage}
        onPageSizeChange={paging.setPageSize}
      />

      {permissions && formDate && businessDate && (
        <ExpenseDialog
          state={dialog}
          date={formDate}
          businessDate={businessDate}
          onSaved={(message) => done("", message)}
          onConflict={done}
          onClose={() => setDialog(null)}
        />
      )}

      <RemoveExpenseDialog
        row={removing}
        onDone={(message) => done("", message)}
        onConflict={done}
        onClose={() => setRemoving(null)}
      />
    </>
  );
}

// Export of the ledger as listed: the same period, source and search.
function LedgerExport({
  exporter,
  period,
  source,
  query,
}: {
  exporter: ReturnType<typeof useReportExport>;
  period: Period;
  source: SourceFilter;
  query: string;
}) {
  return (
    <ExportMenu
      disabled={exporter.exporting}
      onExport={(format) =>
        void exporter.run(
          expenseExportPath({
            from: period.from,
            to: period.to,
            source: source === "all" ? undefined : source,
            q: query || undefined,
            format,
          }),
          "Central expenses",
          period,
          format,
        )
      }
    />
  );
}

// The band's source choice and search, then the export for someone who may export.
function LedgerTools({
  source,
  onSource,
  search,
  onSearch,
  exporter,
  period,
  query,
}: {
  source: SourceFilter;
  onSource: (value: SourceFilter) => void;
  search: string;
  onSearch: (value: string) => void;
  exporter?: ReturnType<typeof useReportExport>;
  period: Period | null;
  query: string;
}) {
  return (
    <>
      <SourceSelect value={source} onChange={onSource} />
      <input
        type="search"
        aria-label="Search"
        className="inp srch"
        placeholder="Search"
        value={search}
        onChange={(event) => onSearch(event.target.value)}
      />
      {exporter && period && (
        <LedgerExport
          exporter={exporter}
          period={period}
          source={source}
          query={query}
        />
      )}
    </>
  );
}
