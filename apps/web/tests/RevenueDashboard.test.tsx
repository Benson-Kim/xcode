import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { AppShell } from "../components/AppShell";
import type { Appearance } from "../lib/appearance";

const appearance: Appearance = {
  organizationName: "Demo Fleet",
  settingsVersion: 1,
  businessDate: "2026-09-30",
  branding: {
    displayName: "XCODE",
    logoAlt: "XCODE",
    primary: "#1D5FD6",
    secondary: "#14213D",
    accent: "#1E6B3A",
    logo: null,
  },
  formats: {
    locale: "en-GB",
    timeZone: "UTC",
    datePattern: "medium",
    hour12: false,
    firstDayOfWeek: 1,
    weekNumbering: "iso8601",
    currency: "KES",
    useGrouping: true,
    numberDecimals: 2,
    direction: "ltr",
  },
  themeMode: "system",
  reducedMotion: false,
  fontScale: 1,
};

const RANGES: Record<string, [string, string]> = {
  today: ["2026-09-30", "2026-09-30"],
  week: ["2026-09-28", "2026-09-30"],
  month: ["2026-09-01", "2026-09-30"],
};

type Figures = Record<string, number | null>;

function dashboard(period: string, figures: Figures = {}) {
  const [from, through] = RANGES[period];
  return {
    period,
    from,
    through,
    businessDate: "2026-09-30",
    revenue: 12500,
    expected: 15000,
    percent: 83,
    capturedToday: 2,
    vehiclesToday: 5,
    missingDays: 0,
    missingVehicles: 0,
    editedRecords: 1,
    ...figures,
  };
}

const json = (body: unknown) =>
  new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });

function serve(
  permissions: string[],
  answer: (period: string) => Response | Promise<Response> = (period) =>
    json(dashboard(period)),
) {
  const fetcher = vi.fn(async (input: RequestInfo | URL) => {
    const path = String(input);
    if (path === "/api/auth/session")
      return json({
        userId: "me",
        firstName: "Test",
        lastName: "User",
        role: "Owner",
        permissions,
      });
    if (path === "/api/setup/appearance") return json(appearance);
    if (path === "/api/setup/pettycash/dashboard")
      return json({
        float: {
          balance: 2400,
          waitingCount: 2,
          waitingTotal: 1800,
          sentBackCount: 0,
          approvedThisMonth: 9500,
        },
        approvals: {
          count: 3,
          total: 11000,
          approvalLimit: null,
          aboveLimit: 0,
          holders: [],
        },
      });
    const period = /period=(\w+)/.exec(path)?.[1];
    if (path.startsWith("/api/setup/revenue/dashboard") && period)
      return answer(period);
    return new Response("{}", { status: 404 });
  });
  vi.stubGlobal("fetch", fetcher);
  return fetcher;
}

const dashboardCalls = (fetcher: ReturnType<typeof serve>) =>
  fetcher.mock.calls
    .map(([input]) => String(input))
    .filter((path) => path.startsWith("/api/setup/revenue/dashboard"));

const card = (name: string) => screen.getByRole("article", { name });

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

const EVERYTHING = [
  "dash.capture",
  "dash.float",
  "dash.revenue",
  "dash.net",
  "dash.costs",
  "dash.gaps",
  "dash.pettycash",
  "dash.commitments",
  "dash.investment",
  "dash.edits",
  "revenue.view",
  "revenue.capture",
  "audit.view",
];

it("connects the revenue cards from the business date, and keeps the others at 'not available yet' instead of zeros", async () => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date("2027-03-10T09:00:00Z"));
  const fetcher = serve(EVERYTHING, (period) =>
    json(
      dashboard(
        period,
        period === "month" ? { missingDays: 4, missingVehicles: 2 } : {},
      ),
    ),
  );
  render(<AppShell onSignOut={() => {}} />);

  // A capturer starts on today, as in the design.
  expect(
    await within(
      await screen.findByRole("article", { name: "Today's revenue" }),
    ).findByText("2 of 5 captured"),
  ).toBeInTheDocument();
  const capture = card("Today's revenue");
  expect(
    within(capture).getByText("Your vehicles, 30 Sep 2026"),
  ).toBeInTheDocument();
  expect(
    within(capture).getByText("3 vehicles still to capture"),
  ).toBeInTheDocument();
  expect(
    within(capture).getByRole("button", { name: "Capture revenue" }),
  ).toBeInTheDocument();

  const revenue = card("Revenue");
  expect(within(revenue).getByText("Today, 30 Sep 2026")).toBeInTheDocument();
  expect(within(revenue).getByText("KES 12,500")).toBeInTheDocument();
  expect(
    within(revenue).getByText(
      "83% of target KES 15,000, from each vehicle’s weekly target. 2 of 5 vehicles have a record so far.",
    ),
  ).toBeInTheDocument();

  // Missing days always cover this month, whatever period is picked.
  const gaps = card("Missing revenue days");
  expect(
    within(gaps).getByText("1 to 29 Sep 2026. No record and no reason."),
  ).toBeInTheDocument();
  expect(within(gaps).getByText("4 days")).toBeInTheDocument();
  expect(
    within(gaps).getByText(
      "On 2 vehicles. Always this month, whatever period you pick.",
    ),
  ).toBeInTheDocument();
  expect(
    within(gaps).getByRole("button", { name: "Fill the gaps" }),
  ).toBeInTheDocument();

  const edits = card("Edited after capture");
  expect(within(edits).getByText("1 record")).toBeInTheDocument();

  expect(
    await within(card("My petty cash float")).findByText("KES 2,400"),
  ).toBeInTheDocument();
  expect(
    await within(card("Petty cash to approve")).findByText("3 entries"),
  ).toBeInTheDocument();
  for (const name of [
    "Net contribution",
    "Money out",
    "Yearly items due",
    "Money invested",
  ])
    expect(
      within(card(name)).getByText("Not available yet"),
    ).toBeInTheDocument();
  expect(screen.getByRole("main")).not.toHaveTextContent(/KES 0\b|\b0 of 0\b/);
  expect(dashboardCalls(fetcher)).toEqual([
    "/api/setup/revenue/dashboard?period=today",
    "/api/setup/revenue/dashboard?period=month",
  ]);

  fireEvent.click(screen.getByRole("button", { name: "This week" }));
  expect(
    await within(card("Revenue")).findByText("This week, 28 Sep to 4 Oct 2026"),
  ).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "This month" }));
  expect(
    await within(card("Revenue")).findByText("This month, 1 to 30 Sep 2026"),
  ).toBeInTheDocument();
  expect(
    within(card("Revenue")).getByText(
      "83% of target KES 15,000, from each vehicle’s weekly target.",
    ),
  ).toBeInTheDocument();
  // The month figures were already loaded for the gaps card, so choosing the month asks for nothing more.
  expect(dashboardCalls(fetcher)).toEqual([
    "/api/setup/revenue/dashboard?period=today",
    "/api/setup/revenue/dashboard?period=month",
    "/api/setup/revenue/dashboard?period=week",
  ]);
});

it("shows no figure the server withholds, and never asks for the month twice", async () => {
  const fetcher = serve(
    ["dash.capture", "dash.gaps", "dash.edits", "audit.view"],
    (period) =>
      json(
        dashboard(period, {
          revenue: null,
          expected: null,
          percent: null,
          capturedToday: null,
          vehiclesToday: null,
          missingDays: 3,
          missingVehicles: 1,
          editedRecords: 0,
        }),
      ),
  );
  render(<AppShell onSignOut={() => {}} />);

  expect(
    await within(
      await screen.findByRole("article", { name: "Missing revenue days" }),
    ).findByText("3 days"),
  ).toBeInTheDocument();
  expect(
    screen.queryByRole("article", { name: "Revenue" }),
  ).not.toBeInTheDocument();
  const capture = card("Today's revenue");
  expect(capture).not.toHaveTextContent(/captured|still to capture|null/);
  expect(
    within(card("Edited after capture")).getByText(
      "Nothing was changed after capture in this period.",
    ),
  ).toBeInTheDocument();
  expect(screen.getByRole("main")).not.toHaveTextContent(/null|undefined|NaN/);

  fireEvent.click(screen.getByRole("button", { name: "This month" }));
  await waitFor(() =>
    expect(dashboardCalls(fetcher)).toContain(
      "/api/setup/revenue/dashboard?period=month",
    ),
  );
  expect(
    dashboardCalls(fetcher).filter((path) => path.endsWith("period=month")),
  ).toHaveLength(1);
});

it("shows placeholders, not zeros, while the revenue figures load", async () => {
  serve(
    ["dash.revenue", "dash.gaps", "revenue.view"],
    () => new Promise<Response>(() => {}),
  );
  render(<AppShell onSignOut={() => {}} />);

  const revenue = await screen.findByRole("article", { name: "Revenue" });
  expect(within(revenue).getByText("This month")).toBeInTheDocument();
  expect(revenue).toHaveAttribute("aria-busy", "true");
  expect(screen.getByRole("main")).not.toHaveTextContent(/KES 0\b|\b0 days\b/);
});

it("keeps the capture counts out of the revenue card for a viewer the server gives only revenue totals", async () => {
  // A fleet manager: dash.revenue without dash.capture, so the server leaves today's capture counts out.
  serve(["dash.revenue", "revenue.view"], (period) =>
    json(
      dashboard(period, {
        capturedToday: null,
        vehiclesToday: null,
        missingDays: null,
        missingVehicles: null,
        editedRecords: null,
      }),
    ),
  );
  render(<AppShell onSignOut={() => {}} />);

  expect(
    await within(
      await screen.findByRole("article", { name: "Revenue" }),
    ).findByText("KES 12,500"),
  ).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "This week" }));
  expect(
    await within(card("Revenue")).findByText("This week, 28 Sep to 4 Oct 2026"),
  ).toBeInTheDocument();
  expect(
    within(card("Revenue")).getByText(
      "83% of target KES 15,000, from each vehicle’s weekly target.",
    ),
  ).toBeInTheDocument();
  expect(card("Revenue")).not.toHaveTextContent(
    /have a record so far|null|undefined|NaN/,
  );
  expect(
    screen.queryByRole("article", { name: "Today's revenue" }),
  ).not.toBeInTheDocument();
});

it("offers Fill the gaps only while there are gaps to fill", async () => {
  serve(["dash.gaps", "revenue.view", "revenue.capture"], (period) =>
    json(dashboard(period, { missingDays: 0, missingVehicles: 0 })),
  );
  render(<AppShell onSignOut={() => {}} />);

  const gaps = await screen.findByRole("article", {
    name: "Missing revenue days",
  });
  expect(await within(gaps).findByText("0 days")).toBeInTheDocument();
  expect(
    within(gaps).getByText("Every vehicle has a record for every day."),
  ).toBeInTheDocument();
  expect(
    within(gaps).queryByRole("button", { name: "Fill the gaps" }),
  ).not.toBeInTheDocument();
});

it("caps the revenue percent at 999% and reads 999%+ beyond it, on the dashboard", async () => {
  serve(EVERYTHING, (period) =>
    json(
      dashboard(period, {
        revenue: 100000009219,
        expected: 8000.14,
        percent: 1249977794,
      }),
    ),
  );
  render(<AppShell onSignOut={() => {}} />);

  const revenue = await screen.findByRole("article", { name: "Revenue" });
  expect(
    await within(revenue).findByText(/^999%\+ of target KES 8,000\.14/),
  ).toBeInTheDocument();
  expect(within(revenue).queryByText(/1249977794/)).not.toBeInTheDocument();
});
