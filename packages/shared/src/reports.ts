// Reports: every report is one table the server builds for a period, with a headline figure and a few figures beside
// it. Fleet reports need reports.view (Investment also invest.view); petty cash reports also need pettycash.spend
// (your own float) or pettycash.view_all (every float). Every figure is cut to the vehicles the person can see.

import { withQuery } from "./query";

export type ReportGroup = "fleet" | "pettycash";

export type FleetReportId =
  "net" | "target" | "moneyOut" | "gaps" | "savings" | "investment";

export type PettyCashReportId =
  "cashBook" | "managers" | "vehicles" | "items" | "waiting" | "sentBack";

export type ReportId = FleetReportId | PettyCashReportId;

export const FLEET_REPORTS: readonly { id: FleetReportId; label: string }[] = [
  { id: "net", label: "Net by vehicle" },
  { id: "target", label: "Revenue against target" },
  { id: "moneyOut", label: "Money out" },
  { id: "gaps", label: "Capture gaps" },
  { id: "savings", label: "Savings" },
  { id: "investment", label: "Investment" },
];

export const PETTY_CASH_REPORTS: readonly {
  id: PettyCashReportId;
  label: string;
}[] = [
  { id: "cashBook", label: "Cash book" },
  { id: "managers", label: "By manager" },
  { id: "vehicles", label: "By vehicle" },
  { id: "items", label: "By item" },
  { id: "waiting", label: "Waiting for approval" },
  { id: "sentBack", label: "Sent back" },
];

// Reports that do not take a period: Investment covers each vehicle since it joined, Waiting lists everything still
// waiting.
export const UNDATED_REPORTS: readonly ReportId[] = ["investment", "waiting"];

// How a cell reads. money and net are amounts (net shows below zero as bad); date is "yyyy-MM-dd"; count and
// quantity are plain numbers (quantity up to three decimals); percent is 0 to 100 with up to one decimal.
export type ReportCellKind =
  | "text"
  | "vehicle"
  | "date"
  | "money"
  | "net"
  | "count"
  | "quantity"
  | "percent";

export type ReportCell = string | number | null;

// sum: the footer adds this column up over the rows shown.
export interface ReportColumn {
  key: string;
  label: string;
  kind: ReportCellKind;
  sum: boolean;
}

export interface ReportFigure {
  label: string;
  value: number;
  kind: "money" | "net" | "count" | "percent";
}

// from and to are the days covered, to never after the business date; both null for an undated report.
export interface ReportTable {
  group: ReportGroup;
  report: ReportId;
  title: string;
  from: string | null;
  to: string | null;
  businessDate: string;
  headline: ReportFigure;
  figures: ReportFigure[];
  columns: ReportColumn[];
  // Only the requested page of the rows matching q.
  rows: ReportCell[][];
  pageNumber: number;
  pageSize: number;
  // The rows matching q across every page.
  total: number;
  // The footer: each sum column added up over every matching row, null for the other columns.
  totals: (number | null)[];
}

export interface ReportHolder {
  id: string;
  name: string;
  active: boolean;
}

// GET setup/reports: the reports this person may open. holders lists the floats the petty cash reports can be cut
// to (only their own without pettycash.view_all). canExport is reports.export.
export interface ReportsAccess {
  businessDate: string;
  firstDayOfWeek: number;
  fleet: FleetReportId[];
  pettyCash: PettyCashReportId[];
  holders: ReportHolder[];
  canExport: boolean;
}

export interface ReportQuery {
  from?: string;
  to?: string;
  holderId?: string;
  companyId?: string;
  // Each word must appear in the row; the server matches what the cells show.
  q?: string;
  page?: number;
  // 1 to 100; the server's default is 50.
  pageSize?: number;
}

export type ReportExportFormat = "xlsx" | "pdf";

// The export is the table as shown: the same period and filters, and every row the search leaves (not one page).
export interface ReportExportQuery extends Omit<
  ReportQuery,
  "page" | "pageSize"
> {
  format: ReportExportFormat;
}

export const REPORTS_ACCESS_PATH = "setup/reports";

export const reportPath = (
  group: ReportGroup,
  report: ReportId,
  query: ReportQuery = {},
) => withQuery(`setup/reports/${group}/${report}`, query);

export const reportExportPath = (
  group: ReportGroup,
  report: ReportId,
  query: ReportExportQuery,
) => withQuery(`setup/reports/${group}/${report}/export`, query);
