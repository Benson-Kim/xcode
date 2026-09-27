import type { IconName } from "../ui";

export type PermissionGroup = {
  name: string;
  items: { key: string; label: string; needs: string[] }[];
};

export type Tab = "home" | "revenue" | "spend" | "more";

// Each tab shows when the person holds any of its permissions.
// Revenue and Spend list what the person may
// do there until their screens are built;
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
    unavailable: "Revenue records are not available from the current API yet.",
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
  { label: "Recurring costs and savings", permission: "commitments.view" },
  { label: "People and access", permission: "people.view" },
  { label: "Change log", permission: "audit.view" },
  { label: "Organization settings", permission: "organization.manage" },
];

export const allowedTabs = (permissions: string[]) =>
  TABS.filter(
    (tab) => !tab.any || tab.any.some((key) => permissions.includes(key)),
  );

export type Period = "today" | "week" | "month";

// The dashboard cards: each needs one permission and shows zero until its data is live.
export const DASHBOARD_CARDS: {
  permission: string;
  title: string;
  sub?: string;
  // A money amount (formatted in the organization's currency) or a count.
  value: number | string;
  note: string;
  action?: string;
  tab?: Tab;
  primary?: boolean;
}[] = [
  {
    permission: "dash.capture",
    title: "Today's revenue",
    sub: "Your vehicles, today",
    value: "0 captured",
    note: "Revenue capture data will appear here.",
    action: "Capture revenue",
    tab: "revenue",
    primary: true,
  },
  {
    permission: "dash.revenue",
    title: "Revenue",
    value: 0,
    note: "No revenue records are available yet.",
  },
  {
    permission: "dash.net",
    title: "Net contribution",
    sub: "Revenue less all costs",
    value: 0,
    note: "Cost and revenue data will appear here.",
  },
  {
    permission: "dash.costs",
    title: "Costs",
    value: 0,
    note: "Cost totals are waiting for records.",
  },
  {
    permission: "dash.gaps",
    title: "Missing revenue days",
    sub: "No record and no reason",
    value: "0 days",
    note: "No gaps are available yet.",
    action: "Open revenue",
    tab: "revenue",
  },
  {
    permission: "dash.commitments",
    title: "Renewals due",
    sub: "Next 30 days",
    value: "0 renewals",
    note: "Renewal data will appear here.",
  },
  {
    permission: "dash.edits",
    title: "Edited after capture",
    value: "0 records",
    note: "Change history will appear here.",
  },
];

const MONTHS = [
  "Jan",
  "Feb",
  "Mar",
  "Apr",
  "May",
  "Jun",
  "Jul",
  "Aug",
  "Sep",
  "Oct",
  "Nov",
  "Dec",
];
const day = (date: Date) =>
  `${date.getDate()} ${MONTHS[date.getMonth()]} ${date.getFullYear()}`;

// "Today, 27 Sep 2026", "This week, 21 to 27 Sep 2026" (weeks run Monday to Sunday), "This month, 1 to 27 Sep 2026".
export function periodLabel(period: Period, now = new Date()) {
  if (period === "today") return `Today, ${day(now)}`;
  if (period === "month") return `This month, 1 to ${day(now)}`;
  const start = new Date(now);
  start.setDate(now.getDate() - ((now.getDay() + 6) % 7));
  const end = new Date(start);
  end.setDate(start.getDate() + 6);
  const startText =
    start.getMonth() === end.getMonth()
      ? `${start.getDate()}`
      : `${start.getDate()} ${MONTHS[start.getMonth()]}`;
  return `This week, ${startText} to ${day(end)}`;
}
