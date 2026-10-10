"use client";

import { useState } from "react";

import { presetPeriod, type Period } from "@xcode/shared/periods";
import {
  FLEET_REPORTS,
  PETTY_CASH_REPORTS,
  REPORTS_ACCESS_PATH,
  UNDATED_REPORTS,
  reportExportPath,
  reportPath,
  type ReportGroup,
  type ReportHolder,
  type ReportId,
  type ReportTable,
  type ReportsAccess,
} from "@xcode/shared/reports";

import { useResource } from "../../lib/data";
import { useDebounced } from "../../lib/useDebounced";
import { PeriodPicker } from "../period/PeriodPicker";
import {
  Banner,
  HeroBand,
  PageHeader,
  RetryBanner,
  SegmentedControl,
  SearchSelect,
  Skeleton,
  Spacer,
  TextInput,
  Toolbar,
  usePaging,
} from "../ui";
import { ExportMenu } from "./ExportMenu";
import { useReportExport } from "./exportReport";
import { ReportBand, ReportView } from "./ReportView";

const GROUPS: { value: ReportGroup; label: string }[] = [
  { value: "fleet", label: "Fleet" },
  { value: "pettycash", label: "Petty cash" },
];

export function ReportsPage() {
  const access = useResource<ReportsAccess>(REPORTS_ACCESS_PATH);
  return (
    <section className="flex flex-col gap-3.5">
      <PageHeader title="Reports" description="" />
      {access.error && !access.data && (
        <RetryBanner onRetry={access.reload}>{access.error}</RetryBanner>
      )}
      {!access.data && !access.error && <Skeleton className="h-11 w-2/3" />}
      {access.data && <ReportsView access={access.data} />}
    </section>
  );
}

function ReportsView({ access }: { access: ReportsAccess }) {
  const exporter = useReportExport();
  const [group, setGroup] = useState<ReportGroup>(
    access.fleet.length ? "fleet" : "pettycash",
  );
  const [chosen, setChosen] = useState<ReportId | null>(null);
  const [chosenPeriod, setChosenPeriod] = useState<Period | null>(null);
  const [holderId, setHolderId] = useState("");
  const [search, setSearch] = useState("");

  const catalog = group === "fleet" ? FLEET_REPORTS : PETTY_CASH_REPORTS;
  const listed: readonly ReportId[] =
    group === "fleet" ? access.fleet : access.pettyCash;
  const reports = catalog.filter((report) => listed.includes(report.id));
  const report = reports.find((entry) => entry.id === chosen) ?? reports[0];
  const dated = report ? !UNDATED_REPORTS.includes(report.id) : false;
  const firstDayOfWeek = access.firstDayOfWeek;
  const period =
    chosenPeriod ??
    presetPeriod("thisWeek", access.businessDate, firstDayOfWeek);
  const holder = group === "pettycash" && holderId ? holderId : undefined;
  const q = useDebounced(search.trim());
  const query = {
    from: dated ? period.from : undefined,
    to: dated ? period.to : undefined,
    holderId: holder,
    q: q || undefined,
  };
  const paging = usePaging(
    `${group}|${report?.id}|${query.from}|${query.to}|${holder}|${q}`,
  );

  const table = useResource<ReportTable>(
    report
      ? reportPath(group, report.id, {
          ...query,
          page: paging.page,
          pageSize: paging.pageSize,
        })
      : null,
  );
  if (table.data) paging.stepBack(table.data.total);

  if (!access.fleet.length && !access.pettyCash.length)
    return <Banner>No reports are available to you.</Banner>;

  return (
    <>
      <HeroBand
        period={
          dated ? (
            <PeriodPicker
              period={period}
              businessDate={access.businessDate}
              firstDayOfWeek={firstDayOfWeek}
              onChange={setChosenPeriod}
            />
          ) : undefined
        }
      >
        <ReportBand table={table.data} />
      </HeroBand>

      <Toolbar>
        {access.fleet.length > 0 && access.pettyCash.length > 0 && (
          <SegmentedControl
            label="Report type"
            options={GROUPS}
            value={group}
            onChange={(next) => {
              setGroup(next);
              setChosen(null);
            }}
          />
        )}
        <SearchSelect
          aria-label="Report"
          density="compact"
          inline
          options={reports.map((entry) => ({
            value: entry.id,
            label: entry.label,
          }))}
          value={report?.id ?? ""}
          onChange={(id) => setChosen(id as ReportId)}
        />
        {group === "pettycash" && access.holders.length > 1 && (
          <HolderSelect
            holders={access.holders}
            value={holderId}
            onChange={setHolderId}
          />
        )}
        <TextInput
          type="search"
          aria-label="Search"
          density="compact"
          inline
          className="max-w-80 flex-[1_1_110px]"
          placeholder="Search the rows"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
        />
        <Spacer />
        {access.canExport && (
          <ExportMenu
            disabled={exporter.exporting || !table.data || !report}
            onExport={(format) =>
              report &&
              void exporter.run(
                reportExportPath(group, report.id, { ...query, format }),
                report.label,
                dated ? period : null,
                format,
              )
            }
          />
        )}
      </Toolbar>

      {exporter.error && <Banner>{exporter.error}</Banner>}
      {table.error && (
        <RetryBanner onRetry={table.reload}>{table.error}</RetryBanner>
      )}

      <ReportView
        table={table.data}
        loading={table.loading}
        failed={Boolean(table.error)}
        paging={paging}
      />
    </>
  );
}

function HolderSelect({
  holders,
  value,
  onChange,
}: {
  holders: ReportHolder[];
  value: string;
  onChange: (holderId: string) => void;
}) {
  return (
    <SearchSelect
      aria-label="Manager"
      density="compact"
      inline
      options={[
        { value: "", label: "All managers" },
        ...holders.map((entry) => ({
          value: entry.id,
          label: `${entry.name}${entry.active ? "" : " (not active)"}`,
        })),
      ]}
      value={value}
      onChange={onChange}
    />
  );
}
