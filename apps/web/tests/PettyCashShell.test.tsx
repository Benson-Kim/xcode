import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import type { PettyCashDashboard } from "@xcode/shared/pettyCash";

import { AppShell } from "../components/AppShell";
import {
  expense,
  paths,
  permissionsOf,
  servePettyCash,
} from "./pettyCashServer";

afterEach(() => vi.unstubAllGlobals());

const dashboard: PettyCashDashboard = {
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
    approvalLimit: 5000,
    aboveLimit: 1,
    holders: [
      {
        holderId: "h1",
        name: "Grace Wanjiru",
        count: 2,
        total: 4000,
        oldest: "2026-09-28",
      },
      {
        holderId: "h2",
        name: "Peter Otieno",
        count: 1,
        total: 7000,
        oldest: "2026-09-30",
      },
    ],
  },
};

const card = (name: string) => screen.getByRole("article", { name });
const menu = () => within(screen.getByRole("navigation", { name: "Main" }));

it.each([
  "pettycash.spend",
  "pettycash.view_all",
  "pettycash.approve_item",
  "pettycash.issue",
])(
  "shows the Petty cash menu item for %s and opens the page",
  async (permission) => {
    servePettyCash({ session: [permission], entries: [expense()] });
    render(<AppShell onSignOut={() => {}} />);
    fireEvent.click(await menu().findByRole("button", { name: "Petty cash" }));
    expect(
      await screen.findByRole("heading", { name: "Petty cash", level: 1 }),
    ).toBeInTheDocument();
    expect(
      await screen.findByRole("row", { name: /KDA 482M/ }),
    ).toBeInTheDocument();
  },
);

it("hides the Petty cash menu item without any of its permissions", async () => {
  servePettyCash({
    session: [
      "revenue.view",
      "dash.float",
      "pettycash.issue_negative",
      "pettycash.approve_day",
    ],
  });
  render(<AppShell onSignOut={() => {}} />);
  expect(
    await menu().findByRole("button", { name: "Revenue" }),
  ).toBeInTheDocument();
  expect(
    menu().queryByRole("button", { name: "Petty cash" }),
  ).not.toBeInTheDocument();
});

it("fills the two petty cash cards from the dashboard payload", async () => {
  const fetcher = servePettyCash({
    session: ["dash.float", "dash.pettycash", "pettycash.spend"],
    dashboard,
  });
  render(<AppShell onSignOut={() => {}} />);

  const float = await screen.findByRole("article", {
    name: "My petty cash float",
  });
  expect(await within(float).findByText("KES 2,400")).toBeInTheDocument();
  expect(
    within(float).getByText(
      "2 entries, KES 1,800, waiting for approval. KES 9,500 approved this month.",
    ),
  ).toBeInTheDocument();
  expect(
    within(float).getByRole("button", { name: "Open petty cash" }),
  ).toBeInTheDocument();
  expect(
    within(float).queryByText("Not available yet"),
  ).not.toBeInTheDocument();

  const approvals = card("Petty cash to approve");
  expect(within(approvals).getByText("3 entries")).toBeInTheDocument();
  expect(
    within(approvals).getByText(
      "KES 11,000 in total. You can approve entries up to KES 5,000. 1 entry is above your limit.",
    ),
  ).toBeInTheDocument();
  const holders = within(approvals).getAllByRole("listitem");
  expect(holders).toHaveLength(2);
  expect(within(holders[0]).getByText("Grace Wanjiru")).toBeInTheDocument();
  expect(
    within(holders[0]).getByText("Oldest 28 Sep 2026"),
  ).toBeInTheDocument();
  expect(within(holders[0]).getByText("KES 4,000")).toBeInTheDocument();
  expect(within(holders[0]).getByText("2 entries")).toBeInTheDocument();
  expect(
    within(holders[1]).getByText("Oldest 30 Sep 2026"),
  ).toBeInTheDocument();
  expect(
    paths(fetcher).filter((path) => path === "/api/setup/pettycash/dashboard"),
  ).toHaveLength(1);
});

it("shows a float below zero with its minus sign and in the bad tone", async () => {
  servePettyCash({
    session: ["dash.float", "pettycash.spend"],
    dashboard: {
      float: {
        balance: -250,
        waitingCount: 0,
        waitingTotal: 0,
        sentBackCount: 1,
        approvedThisMonth: 0,
      },
      approvals: null,
    },
  });
  render(<AppShell onSignOut={() => {}} />);
  const float = await screen.findByRole("article", {
    name: "My petty cash float",
  });
  const value = await within(float).findByText("KES -250");
  expect(value).toHaveClass("text-red");
  expect(
    within(float).getByText(
      "Nothing is waiting for approval. 1 entry was sent back. KES 0 approved this month.",
    ),
  ).toBeInTheDocument();
});

it("opens Petty cash on the waiting entries from the approval card", async () => {
  const fetcher = servePettyCash({
    session: ["dash.pettycash", "pettycash.approve_item"],
    permissions: permissionsOf({
      canSpend: false,
      canApproveItem: true,
      canViewAll: true,
    }),
    dashboard,
    entries: [expense({ canReview: true })],
  });
  render(<AppShell onSignOut={() => {}} />);
  fireEvent.click(
    await within(
      await screen.findByRole("article", { name: "Petty cash to approve" }),
    ).findByRole("button", { name: "Review entries" }),
  );

  expect(await screen.findByRole("combobox", { name: "Show" })).toHaveValue(
    "waiting",
  );
  await waitFor(() =>
    expect(
      paths(fetcher).some(
        (path) =>
          path.startsWith("/api/setup/pettycash/entries") &&
          path.includes("status=waiting"),
      ),
    ).toBe(true),
  );
});

it("keeps both cards, and their request, away from people without their permissions", async () => {
  const fetcher = servePettyCash({
    session: ["dash.revenue", "revenue.view"],
    dashboard,
  });
  render(<AppShell onSignOut={() => {}} />);
  await menu().findByRole("button", { name: "Revenue" });
  expect(
    screen.queryByRole("article", { name: "My petty cash float" }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole("article", { name: "Petty cash to approve" }),
  ).not.toBeInTheDocument();
  expect(paths(fetcher).some((path) => path.includes("pettycash"))).toBe(false);
});

it("leaves out the card the server withholds even when its key is held", async () => {
  servePettyCash({
    session: ["dash.float", "dash.pettycash"],
    dashboard: { float: null, approvals: dashboard.approvals },
  });
  render(<AppShell onSignOut={() => {}} />);
  expect(
    await within(
      await screen.findByRole("article", { name: "Petty cash to approve" }),
    ).findByText("3 entries"),
  ).toBeInTheDocument();
  expect(
    screen.queryByRole("article", { name: "My petty cash float" }),
  ).not.toBeInTheDocument();
});

it("says so on the cards when the dashboard cannot be loaded, rather than showing zeros", async () => {
  servePettyCash({
    session: ["dash.float", "dash.pettycash"],
    answer: (path) =>
      path.endsWith("/pettycash/dashboard")
        ? new Response("{}", { status: 404 })
        : undefined,
  });
  render(<AppShell onSignOut={() => {}} />);
  const float = await screen.findByRole("article", {
    name: "My petty cash float",
  });
  expect(
    await within(float).findByText("The request could not be completed."),
  ).toBeInTheDocument();
  expect(screen.getByRole("main")).not.toHaveTextContent(/KES 0\b/);
});
