import { describe, expect, it } from "vitest";

import {
  FLEET_REPORTS,
  PETTY_CASH_REPORTS,
  REPORTS_ACCESS_PATH,
  UNDATED_REPORTS,
  reportExportPath,
  reportPath,
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
