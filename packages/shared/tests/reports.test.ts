import { describe, expect, it } from "vitest";

import {
  FLEET_REPORTS,
  PETTY_CASH_REPORTS,
  REPORTS_ACCESS_PATH,
  UNDATED_REPORTS,
  expenseExportPath,
  pettyCashExportPath,
  reportExportPath,
  reportPath,
  revenueExportPath,
} from "../src/reports";

describe("the catalog", () => {
  it("labels the fleet reports", () => {
    expect(FLEET_REPORTS.map((report) => [report.id, report.label])).toEqual([
      ["net", "Net by vehicle"],
      ["target", "Revenue against target"],
      ["moneyOut", "Money out"],
      ["gaps", "Capture gaps"],
      ["savings", "Savings"],
      ["investment", "Investment"],
    ]);
  });

  it("labels the petty cash reports", () => {
    expect(
      PETTY_CASH_REPORTS.map((report) => [report.id, report.label]),
    ).toEqual([
      ["cashBook", "Cash book"],
      ["managers", "By manager"],
      ["vehicles", "By vehicle"],
      ["items", "By item"],
      ["waiting", "Waiting for approval"],
      ["sentBack", "Sent back"],
    ]);
  });

  it("names the reports that take no period", () => {
    expect(UNDATED_REPORTS).toEqual(["investment", "waiting"]);
  });
});

describe("paths", () => {
  it("builds the access path", () => {
    expect(REPORTS_ACCESS_PATH).toBe("setup/reports");
  });

  it("builds a report path with the period and manager, skipping what is empty", () => {
    expect(reportPath("fleet", "net")).toBe("setup/reports/fleet/net");
    expect(
      reportPath("fleet", "net", { from: "2026-10-05", to: "2026-10-11" }),
    ).toBe("setup/reports/fleet/net?from=2026-10-05&to=2026-10-11");
    expect(
      reportPath("pettycash", "cashBook", {
        from: "2026-10-05",
        to: "2026-10-11",
        holderId: "h1",
      }),
    ).toBe(
      "setup/reports/pettycash/cashBook?from=2026-10-05&to=2026-10-11&holderId=h1",
    );
    expect(reportPath("pettycash", "waiting", { holderId: undefined })).toBe(
      "setup/reports/pettycash/waiting",
    );
  });

  it("builds a report path with the search and the page", () => {
    expect(
      reportPath("fleet", "net", {
        from: "2026-10-05",
        to: "2026-10-11",
        q: "kda 482m",
        page: 2,
        pageSize: 25,
      }),
    ).toBe(
      "setup/reports/fleet/net?from=2026-10-05&to=2026-10-11&q=kda+482m&page=2&pageSize=25",
    );
    expect(reportPath("fleet", "net", { q: "", page: 1 })).toBe(
      "setup/reports/fleet/net?page=1",
    );
  });

  it("builds the export path for a PDF as for a workbook", () => {
    expect(
      reportExportPath("pettycash", "cashBook", {
        from: "2026-10-05",
        to: "2026-10-11",
        holderId: "h1",
        q: "fuel",
        format: "pdf",
      }),
    ).toBe(
      "setup/reports/pettycash/cashBook/export?from=2026-10-05&to=2026-10-11&holderId=h1&q=fuel&format=pdf",
    );
  });

  it("builds the export path with the search and the format", () => {
    expect(
      reportExportPath("fleet", "net", {
        from: "2026-10-05",
        to: "2026-10-11",
        q: "KDA 482M",
        format: "xlsx",
      }),
    ).toBe(
      "setup/reports/fleet/net/export?from=2026-10-05&to=2026-10-11&q=KDA+482M&format=xlsx",
    );
    expect(
      reportExportPath("fleet", "investment", { q: "", format: "xlsx" }),
    ).toBe("setup/reports/fleet/investment/export?format=xlsx");
  });
});

describe("screen exports", () => {
  it("asks for the revenue week with the query names the API reads", () => {
    expect(
      revenueExportPath({
        weekStart: "2026-10-12",
        companyId: "c1",
        format: "xlsx",
      }),
    ).toBe(
      "setup/revenue/export?weekStart=2026-10-12&companyId=c1&format=xlsx",
    );
    expect(revenueExportPath({ weekStart: "2026-10-12", format: "pdf" })).toBe(
      "setup/revenue/export?weekStart=2026-10-12&format=pdf",
    );
  });

  it("asks for the central expenses of a period, its source and search", () => {
    expect(
      expenseExportPath({
        from: "2026-10-01",
        to: "2026-10-31",
        source: "pc",
        q: "fuel tank",
        format: "pdf",
      }),
    ).toBe(
      "setup/expenses/export?from=2026-10-01&to=2026-10-31&source=pc&q=fuel+tank&format=pdf",
    );
  });

  it("asks for the petty-cash view of one holder, leaving empty filters out", () => {
    expect(
      pettyCashExportPath({
        from: "2026-10-05",
        to: "2026-10-11",
        holderId: "h1",
        view: "expenses",
        status: "waiting",
        q: "",
        format: "xlsx",
      }),
    ).toBe(
      "setup/pettycash/export?from=2026-10-05&to=2026-10-11&holderId=h1&view=expenses&status=waiting&format=xlsx",
    );
    expect(
      pettyCashExportPath({
        from: "2026-10-05",
        to: "2026-10-11",
        view: "cash",
        format: "pdf",
      }),
    ).toBe(
      "setup/pettycash/export?from=2026-10-05&to=2026-10-11&view=cash&format=pdf",
    );
  });
});
