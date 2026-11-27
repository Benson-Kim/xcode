import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type {
  RevenueCell,
  RevenueVehicle,
  RevenueWeek,
} from "@xcode/shared/revenue";

import { ExportMenu } from "../components/reports/ExportMenu";
import { drawSummaryImage } from "../components/revenue/drawSummaryImage";
import {
  summaryHeight,
  summaryLayout,
  summaryPeriod,
  weekCounts,
} from "../components/revenue/summaryImage";
import { RevenuePage } from "../components/RevenuePage";
import { renderInApp } from "./renderInApp";

// Sunday 4 to Saturday 10 October 2026; the business date is Friday the 9th, as in the owner's sample.
const SUNDAY_WEEK = [
  "2026-10-04",
  "2026-10-05",
  "2026-10-06",
  "2026-10-07",
  "2026-10-08",
  "2026-10-09",
  "2026-10-10",
];
const TODAY = "2026-10-09";
const number = new Intl.NumberFormat("en-US").format;

function cell(date: string, over: Partial<RevenueCell> = {}): RevenueCell {
  const status = date > TODAY ? "future" : "missing";
  return {
    date,
    status,
    expected: 0,
    amount: null,
    reason: null,
    note: null,
    canEdit: false,
    editedAfterCapture: false,
    version: null,
    ...over,
  };
}

const paid = (amount: number, reason: string | null = null) => ({
  status: "amount" as const,
  amount,
  reason,
});
const why = (reason: string) => ({ status: "reason" as const, reason });

function vehicle(
  registration: string,
  days: Record<string, Partial<RevenueCell>>,
  dates = SUNDAY_WEEK,
): RevenueVehicle {
  const cells = dates.map((date) => cell(date, days[date]));
  return {
    id: registration,
    companyId: "north",
    companyName: "North Star",
    registration,
    joinedOn: "2026-01-01",
    leftOn: null,
    earliestMissing: null,
    days: cells,
    totalAmount: cells.reduce((sum, day) => sum + (day.amount ?? 0), 0),
    totalExpected: 0,
    percent: null,
  };
}

function week(
  vehicles: RevenueVehicle[],
  over: Partial<RevenueWeek> = {},
  dates = SUNDAY_WEEK,
): RevenueWeek {
  return {
    weekStart: dates[0]!,
    weekThrough: dates[6]!,
    currentWeekStart: dates[0]!,
    businessDate: TODAY,
    companies: [
      { id: "north", name: "North Star" },
      { id: "metro", name: "Metro Link" },
    ],
    vehicles,
    totalAmount: vehicles.reduce((sum, item) => sum + item.totalAmount, 0),
    totalExpected: 0,
    percent: null,
    dayTotals: dates.map((date) => ({
      date,
      amount: vehicles.reduce(
        (sum, item) =>
          sum + (item.days.find((day) => day.date === date)?.amount ?? 0),
        0,
      ),
      expected: 0,
    })),
    belowThresholdDays: 3,
    missingDays: 1,
    ...over,
  };
}

const [SUN, MON, TUE, WED, THU, FRI] = SUNDAY_WEEK;

const fleet = () => [
  vehicle("KDH 208T", {
    [SUN!]: paid(5100),
    [MON!]: paid(7550),
    [TUE!]: why("Garage"),
    [WED!]: why("Garage"),
    [THU!]: paid(8350),
  }),
  vehicle("KDA 317L", {
    [SUN!]: paid(5550),
    [MON!]: paid(7150),
    [TUE!]: paid(7100),
    [WED!]: paid(8250),
  }),
  vehicle("KDK 095R", {
    [SUN!]: paid(6600),
    [MON!]: paid(7550),
    [TUE!]: paid(12400),
    [WED!]: paid(8900),
    [THU!]: paid(3500, "Other"),
  }),
];

describe("summaryLayout", () => {
  it("orders the vehicles highest revenue first and draws each day as the grid states it", () => {
    const layout = summaryLayout(week(fleet()), "", number);

    expect(layout.rows.map((row) => [row.registration, row.total])).toEqual([
      ["KDK 095R", "38,950"],
      ["KDA 317L", "28,050"],
      ["KDH 208T", "21,000"],
    ]);
    const [kdk, kda, kdh] = layout.rows;
    expect(kdk!.cells[4]).toEqual({
      state: "amount",
      text: "3,500",
      note: "Other",
    });
    expect(kdk!.cells[2]).toEqual({
      state: "amount",
      text: "12,400",
      note: null,
    });
    expect(kdh!.cells[2]).toEqual({
      state: "reason",
      text: "Garage",
      note: null,
    });
    expect(kda!.cells[4]).toEqual({
      state: "missing",
      text: "Missing",
      note: null,
    });
    expect(kda!.cells[5]).toEqual({ state: "due", text: "Due", note: null });
    expect(kda!.cells[6]).toEqual({ state: "blank", text: "", note: null });
    expect(kda!.missing).toBe("1 missing");
    expect(kdk!.missing).toBeNull();
  });

  it("carries the week revenue once, at the end of the Total row, with each day's total", () => {
    const layout = summaryLayout(week(fleet()), "", number);

    expect(layout.dayTotals).toEqual([
      "17,250",
      "22,250",
      "19,500",
      "17,150",
      "11,850",
      null,
      null,
    ]);
    expect(layout.total).toBe("88,000");
  });

  it("writes a past day without revenue as 0 in the Total row, and leaves today and later blank", () => {
    const layout = summaryLayout(
      week([vehicle("KDA 317L", { [SUN!]: why("Garage") })]),
      "",
      number,
    );

    expect(layout.dayTotals).toEqual(["0", "0", "0", "0", "0", null, null]);
  });

  it("names the period in full, adds the company only when one is filtered, and names the file after it", () => {
    const all = summaryLayout(week(fleet()), "", number);
    const north = summaryLayout(week(fleet()), "north", number);

    expect(all.title).toBe("Weekly Performance");
    expect(all.period).toBe("4 to 10 October 2026");
    expect(all.subtitle).toBe("4 to 10 October 2026");
    expect(north.subtitle).toBe("4 to 10 October 2026, North Star");
    expect(all.fileName).toBe("Weekly Performance, 4 to 10 October 2026.png");
  });

  it("shows Missing days and Low days from the Revenue bar's figures, Missing days marked when above 0", () => {
    expect(summaryLayout(week(fleet()), "", number).figures).toEqual([
      { label: "Missing days", value: "1", alert: true },
      { label: "Low days", value: "3", alert: false },
    ]);
    expect(
      summaryLayout(week(fleet(), { missingDays: 0 }), "", number).figures[0],
    ).toEqual({ label: "Missing days", value: "0", alert: false });
  });

  it("puts the day columns in the order of the week on screen, whichever day it starts on", () => {
    const monday = SUNDAY_WEEK.map((date) =>
      date.replace(/\d\d$/, (day) => String(Number(day) + 1).padStart(2, "0")),
    );
    const sunday = summaryLayout(week(fleet()), "", number);
    const fromMonday = summaryLayout(
      week([vehicle("KDA 317L", {}, monday)], {}, monday),
      "",
      number,
    );

    expect(sunday.days.map((day) => day.weekday)).toEqual([
      "Sun",
      "Mon",
      "Tue",
      "Wed",
      "Thu",
      "Fri",
      "Sat",
    ]);
    expect(sunday.days.map((day) => day.day)).toEqual([
      "4",
      "5",
      "6",
      "7",
      "8",
      "9",
      "10",
    ]);
    expect(sunday.days.filter((day) => day.today)).toEqual([
      { date: FRI, weekday: "Fri", day: "9", today: true },
    ]);
    expect(fromMonday.days[0]!.weekday).toBe("Mon");
    expect(fromMonday.period).toBe("5 to 11 October 2026");
  });

  it("is 1200 pixels wide and grows a row taller with each vehicle", () => {
    const one = summaryLayout(week(fleet().slice(0, 1)), "", number);
    const three = summaryLayout(week(fleet()), "", number);

    expect(three.width).toBe(1200);
    expect(three.height - one.height).toBe(2 * 88);
    expect(summaryHeight(9)).toBe(1172);
    expect(summaryLayout(week([]), "", number).height).toBe(summaryHeight(1));
  });
});

describe("summaryPeriod", () => {
  it("writes the month and the year once where the week shares them", () => {
    expect(summaryPeriod("2026-09-27", "2026-10-03")).toBe(
      "27 September to 3 October 2026",
    );
    expect(summaryPeriod("2025-12-28", "2026-01-03")).toBe(
      "28 December 2025 to 3 January 2026",
    );
  });
});

describe("weekCounts", () => {
  it("takes the API's figures, and counts from the grid only when the API sends none", () => {
    const counted = week(fleet(), {
      belowThresholdDays: undefined,
      missingDays: undefined,
    });

    expect(weekCounts(counted)).toEqual({ low: 3, notFueled: 0, missing: 4 });
    expect(weekCounts(week(fleet()))).toEqual({
      low: 3,
      notFueled: 0,
      missing: 1,
    });
    expect(
      weekCounts(
        week(fleet(), {
          belowThresholdDays: 7,
          notFueledDays: 2,
          missingDays: 4,
        }),
      ),
    ).toEqual({ low: 7, notFueled: 2, missing: 4 });
  });

  it("counts only the No answers on days with revenue when the API sends no Not fueled figure", () => {
    const tagged = week([
      vehicle("KDA 317L", {
        [SUN!]: { ...paid(12600), fuel: "no" },
        [MON!]: { ...paid(2500, "Garage"), fuel: "no" },
        [TUE!]: { ...paid(13000), fuel: "yes" },
        [WED!]: paid(8000),
      }),
    ]);

    expect(weekCounts(tagged).notFueled).toBe(2);
  });
});

describe("Not fueled in the summary image", () => {
  const tagged = () =>
    week([
      vehicle("KDA 317L", {
        [SUN!]: { ...paid(12600), fuel: "no" },
        [MON!]: { ...paid(2500, "Garage"), fuel: "no" },
        [TUE!]: { ...paid(13000), fuel: "yes" },
      }),
    ]);

  it("writes Not fueled under an amount with no reason, the reason where there is one, and nothing for Yes", () => {
    const [row] = summaryLayout(tagged(), "", number).rows;

    expect(row!.cells[0]).toEqual({
      state: "amount",
      text: "12,600",
      note: "Not fueled",
      fuelNote: true,
    });
    expect(row!.cells[1]).toEqual({
      state: "amount",
      text: "2,500",
      note: "Garage",
    });
    expect(row!.cells[2]).toEqual({
      state: "amount",
      text: "13,000",
      note: null,
    });
  });

  it("draws Not fueled grey and a reason amber", async () => {
    const drawn: Record<string, unknown> = {};
    const target: Record<string, unknown> = {
      fillText: (text: string) => {
        drawn[text] = target.fillStyle;
      },
      // Narrow enough that neither note is cut to fit its column.
      measureText: (text: string) => ({ width: text.length * 6 }),
      createLinearGradient: () => ({ addColorStop: () => {} }),
    };
    const pen = new Proxy(target, {
      get: (object, key: string) => object[key] ?? (() => {}),
    });
    const context = vi
      .spyOn(HTMLCanvasElement.prototype, "getContext")
      .mockImplementation(() => pen as unknown as CanvasRenderingContext2D);

    await drawSummaryImage(summaryLayout(tagged(), "", number));
    context.mockRestore();

    expect(drawn["Not fueled"]).toBe("#547079");
    expect(drawn["Garage"]).toBe("#8A6100");
  });
});

describe("ExportMenu", () => {
  it("offers only Excel and PDF to the pages that add nothing", () => {
    renderInApp(<ExportMenu disabled={false} onExport={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: "Export" }));

    expect(
      screen.getAllByRole("menuitem").map((item) => item.textContent),
    ).toEqual(["Excel", "PDF"]);
  });
});

// --- the Revenue page: menu, pop up, change-log row, file ---

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });

function serve(grid: RevenueWeek, logged: () => Response) {
  const fetcher = vi.fn(
    async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      if (init?.method === "POST") return logged();
      if (path.startsWith("/api/setup/access/me"))
        return json({ allCompanies: true, earliest: null });
      if (path.startsWith("/api/setup/revenue")) return json(grid);
      return json({}, 404);
    },
  );
  vi.stubGlobal("fetch", fetcher);
  return fetcher;
}

// jsdom draws nothing: a 2D context that records the text written, and a canvas that hands back a PNG blob.
function recordCanvas() {
  const written: string[] = [];
  const pen = new Proxy(
    {
      fillText: (text: string) => written.push(text),
      measureText: (text: string) => ({ width: text.length * 10 }),
      createLinearGradient: () => ({ addColorStop: () => {} }),
    } as Record<string, unknown>,
    { get: (target, key: string) => target[key] ?? (() => {}) },
  );
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockImplementation(
    () => pen as unknown as CanvasRenderingContext2D,
  );
  vi.spyOn(HTMLCanvasElement.prototype, "toBlob").mockImplementation(function (
    callback: BlobCallback,
  ) {
    callback(new Blob(["png"], { type: "image/png" }));
  });
  return written;
}

function recordDownloads() {
  URL.createObjectURL = vi.fn(() => "blob:image");
  URL.revokeObjectURL = vi.fn();
  const saved: string[] = [];
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (
    this: HTMLAnchorElement,
  ) {
    saved.push(this.download);
  });
  return saved;
}

const posts = (fetcher: ReturnType<typeof serve>) =>
  fetcher.mock.calls
    .filter(([, init]) => init?.method === "POST")
    .map(([input, init]) => ({
      path: String(input),
      body: JSON.parse(String(init?.body)),
    }));

async function openImage() {
  await screen.findByRole("table", { name: /Revenue by vehicle and day/ });
  fireEvent.click(screen.getByRole("button", { name: "Export" }));
  expect(
    screen.getAllByRole("menuitem").map((item) => item.textContent),
  ).toEqual(["Excel", "PDF", "Summary image"]);
  fireEvent.click(screen.getByRole("menuitem", { name: "Summary image" }));
  const dialog = await screen.findByRole("dialog", { name: "Summary image" });
  await within(dialog).findByRole("img", {
    name: "Weekly Performance, 4 to 10 October 2026",
  });
  return dialog;
}

afterEach(() => vi.unstubAllGlobals());

describe("Revenue, Export, Summary image", () => {
  it("shows the picture of the week on screen, then logs the export and saves the PNG", async () => {
    const written = recordCanvas();
    const saved = recordDownloads();
    const fetcher = serve(
      week(fleet()),
      () => new Response(null, { status: 204 }),
    );
    renderInApp(<RevenuePage />, {
      permissions: ["revenue.view", "revenue.export"],
    });

    const dialog = await openImage();

    expect(written).toEqual(
      expect.arrayContaining([
        "Weekly Performance",
        "4 to 10 October 2026",
        "Missing days",
        "Low days",
        "KDK 095R",
        "1 missing",
        "Due",
        "Missing",
        "Total",
        "88,000",
      ]),
    );
    expect(written).not.toContain("XCODE");
    expect(posts(fetcher)).toEqual([]);

    fireEvent.click(within(dialog).getByRole("button", { name: "Save image" }));

    await waitFor(() =>
      expect(saved).toEqual(["Weekly Performance, 4 to 10 October 2026.png"]),
    );
    expect(posts(fetcher)).toEqual([
      {
        path: "/api/setup/revenue/export/image",
        body: { weekStart: "2026-10-04", companyId: null, q: null },
      },
    ]);
    await waitFor(() =>
      expect(
        screen.queryByRole("dialog", { name: "Summary image" }),
      ).not.toBeInTheDocument(),
    );
  });

  it("saves nothing when the change log refuses the export, and says why", async () => {
    recordCanvas();
    const saved = recordDownloads();
    serve(week(fleet()), () =>
      json({ detail: "Your access does not include this." }, 403),
    );
    renderInApp(<RevenuePage />, {
      permissions: ["revenue.view", "revenue.export"],
    });

    const dialog = await openImage();
    fireEvent.click(within(dialog).getByRole("button", { name: "Save image" }));

    expect(
      await within(dialog).findByText("Your access does not include this."),
    ).toBeInTheDocument();
    expect(saved).toEqual([]);
  });

  it("leaves Summary image out of the menu without revenue.export", async () => {
    serve(week(fleet()), () => new Response(null, { status: 204 }));
    renderInApp(<RevenuePage />, {
      permissions: ["revenue.view", "reports.export"],
    });

    await screen.findByRole("table", { name: /Revenue by vehicle and day/ });
    fireEvent.click(screen.getByRole("button", { name: "Export" }));
    expect(
      screen.getAllByRole("menuitem").map((item) => item.textContent),
    ).toEqual(["Excel", "PDF"]);
  });
});
