import {
  revenuePeriodLabel,
  type RevenuePeriod,
} from "@xcode/shared/revenue";

import {
  dayLabel,
  isDate,
  rangeLabel,
  shiftDate,
  startOfWeek,
} from "../revenue/dates";
import type { IconName } from "../ui";

export type PermissionGroup = {
  name: string;
  items: { key: string; label: string; needs: string[] }[];
};

export type Tab = "home" | "revenue" | "spend" | "more";

// Each tab shows when the person holds any of its permissions.
// The server remains the authority for every record and action.
export const TABS: {
  id: Tab;
  label: string;
  icon: IconName;
  any?: string[];
  groups?: string[];
  unavailable?: string;
}[] = [
  { id: "home", label: "Home", icon: "home" },
  {
    id: "revenue",
    label: "Revenue",
    icon: "revenue",
    any: ["revenue.view", "revenue.capture"],
    groups: ["Revenue"],
  },
  {
    id: "spend",
    label: "Spend",
    icon: "spend",
    any: [
      "pettycash.spend",
      "pettycash.approve_item",
      "pettycash.view_all",
      "bills.view",
    ],
    groups: ["Petty cash", "Office bills"],
    unavailable:
      "Petty cash and office bills are not available from the current API yet.",
  },
  { id: "more", label: "More", icon: "more" },
];

export const SETUP_LINKS = [
  { label: "PSV companies", permission: "companies.manage" },
  { label: "Vehicles", permission: "vehicles.manage" },
  { label: "Scheduled expenses and savings", permission: "commitments.view" },
  { label: "People and access", permission: "people.view" },
  { label: "Change log", permission: "audit.view" },
  { label: "Organization settings", permission: "organization.manage" },
];

export const allowedTabs = (permissions: string[]) =>
  TABS.filter(
    (tab) => !tab.any || tab.any.some((key) => permissions.includes(key)),
  );

export type Period = RevenuePeriod;

// The dashboard cards, in the order XCODE Web shows them, each for the people with its permission. Cards whose
// figures the API does not serve yet say so (unavailable) rather than showing zeros. In sub, {period} stands for the
// period picked ("This month, 1 to 30 Sep 2026"); the capture and missing days cards work out their own.
export const DASHBOARD_CARDS: {
  permission: string;
  title: string;
  sub?: string;
  unavailable?: string;
  action?: string;
  tab?: Tab;
  primary?: boolean;
  // The action shows only to people holding one of these (as well as the tab).
  actionNeeds?: string[];
  // A card that always covers this period, whichever the person picks.
  period?: Period;
}[] = [
  {
    permission: "dash.capture",
    title: "Today's revenue",
    action: "Capture revenue",
    tab: "revenue",
    primary: true,
  },
  {
    permission: "dash.float",
    title: "My petty cash float",
    sub: "Cash in hand now",
    unavailable: "Petty cash is not connected yet.",
  },
  { permission: "dash.revenue", title: "Revenue", sub: "{period}" },
  {
    permission: "dash.net",
    title: "Net contribution",
    sub: "Revenue less all costs. {period}",
    unavailable: "Needs cost totals, which are not connected yet.",
  },
  {
    permission: "dash.costs",
    title: "Money out",
    sub: "{period}. Fuel and crew pay are not tracked; revenue is recorded net of them.",
    unavailable: "Cost totals are not connected yet.",
  },
  {
    permission: "dash.gaps",
    title: "Missing revenue days",
    period: "month",
    action: "Fill the gaps",
    tab: "revenue",
    actionNeeds: ["revenue.capture", "revenue.correct"],
  },
  {
    permission: "dash.pettycash",
    title: "Petty cash to approve",
    sub: "All managers",
    unavailable: "Petty cash is not connected yet.",
  },
  {
    permission: "dash.commitments",
    title: "Yearly items due",
    sub: "Next 30 days",
    unavailable: "Yearly items are not connected yet.",
  },
  {
    permission: "dash.investment",
    title: "Money invested",
    sub: "Against what has come back",
    unavailable: "What has come back is not connected yet.",
  },
  { permission: "dash.edits", title: "Edited after capture", sub: "{period}" },
];

// Today is the organization's business date ("yyyy-MM-dd"), never the phone's clock; until the phone has one,
export function periodLabel(
  period: Period,
  businessDate: string | undefined,
  weekStartsOn: number,
) {
  const name = revenuePeriodLabel(period);

  if (!isDate(businessDate)) return name;
  if (period === "today") return `${name}, ${dayLabel(businessDate)}`;
  if (period === "month") return `${name}, 1 to ${dayLabel(businessDate)}`;

  const start = startOfWeek(businessDate, weekStartsOn);

  return `${name}, ${rangeLabel(start, shiftDate(start, 6))}`;
}
