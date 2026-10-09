import type { Formatter } from "@xcode/shared/format";
import {
  canSee,
  DASHBOARD_CARDS as SHARED_CARDS,
  NAV,
  permissionChecker,
  type NavId,
  type DashboardKey,
  type PermissionKey,
} from "@xcode/shared/permissions";
import { revenuePeriodLabel, type RevenuePeriod } from "@xcode/shared/revenue";

import type { PettyCashSection } from "../pettycash/PettyCashScreen";
import { firstOfMonth, isDate, shiftDate, startOfWeek } from "../revenue/dates";
import type { IconName } from "../ui";

export type { PermissionGroup } from "@xcode/shared/permissions";

export type Tab = "home" | "revenue" | "spend" | "more";

// Each tab shows when the person holds any of its permissions.
// The server remains the authority for every record and action.
export const TABS: {
  id: Tab;
  label: string;
  icon: IconName;
  any?: readonly PermissionKey[];
  groups?: string[];
  unavailable?: string;
}[] = [
  { id: "home", label: "Home", icon: "home" },
  {
    id: "revenue",
    label: "Revenue",
    icon: "revenue",
    any: [...NAV.revenue.any, "revenue.capture"],
    groups: ["Revenue"],
  },
  {
    id: "spend",
    label: "Spend",
    icon: "spend",
    any: [...NAV.pettycash.any, "bills.view"],
    groups: ["Office bills"],
    unavailable: "Office bills are not available from the current API yet.",
  },
  { id: "more", label: "More", icon: "more" },
];

const SETUP_IDS = [
  "companies",
  "vehicles",
  "expenses",
  "recurring",
  "people",
  "history",
  "settings",
] as const satisfies readonly NavId[];

export const SETUP_LINKS = SETUP_IDS.map((id) => ({
  label: NAV[id].label,
  any: NAV[id].any,
}));

export const allowedTabs = (permissions: readonly string[]) => {
  const can = permissionChecker(permissions);
  return TABS.filter((tab) => canSee(tab, can));
};

export type Period = RevenuePeriod;

// The dashboard cards, in the order XCODE Web shows them, each for the people with its permission. Cards whose
// figures the API does not serve yet say so (unavailable) rather than showing zeros. In sub, {period} stands for the
// period picked ("This month, 1 to 30 Sep 2026"); the capture and missing days cards work out their own.
type CardExtras = {
  sub?: string;
  unavailable?: string;
  action?: string;
  tab?: Tab;
  primary?: boolean;
  // The action shows only to people holding one of these (as well as the tab).
  actionNeeds?: PermissionKey[];
  // A card that always covers this period, whichever the person picks.
  period?: Period;
  // The part of the Spend tab the action opens.
  section?: PettyCashSection;
};

// What only the phone says about each card; the key, title and order come from @xcode/shared/permissions.
const CARD_EXTRAS = {
  "dash.capture": {
    action: "Capture revenue",
    tab: "revenue",
    primary: true,
  },
  "dash.float": {
    sub: "Balance now",
    action: "Record spending",
    tab: "spend",
    primary: true,
    actionNeeds: ["pettycash.spend"],
    section: "float",
  },
  "dash.revenue": { sub: "{period}" },
  "dash.net": {
    sub: "Revenue less all costs. {period}",
    unavailable: "Needs cost totals, which are not connected yet.",
  },
  "dash.costs": {
    sub: "{period}. Fuel and crew pay are not tracked; revenue is recorded net of them.",
    unavailable: "Cost totals are not connected yet.",
  },
  "dash.gaps": {
    period: "month",
    action: "Fill the gaps",
    tab: "revenue",
    actionNeeds: ["revenue.capture", "revenue.correct"],
  },
  "dash.pettycash": {
    sub: "All managers",
    action: "Review entries",
    tab: "spend",
    actionNeeds: ["pettycash.approve_item"],
    section: "approvals",
  },
  "dash.commitments": {
    sub: "Next 30 days",
    unavailable: "Yearly items are not connected yet.",
  },
  "dash.investment": {
    sub: "Against what has come back",
    unavailable: "What has come back is not connected yet.",
  },
  "dash.edits": { sub: "{period}" },
} satisfies Record<DashboardKey, CardExtras>;

export const DASHBOARD_CARDS: ({
  permission: DashboardKey;
  title: string;
} & CardExtras)[] = SHARED_CARDS.map((card) => ({
  ...card,
  ...(CARD_EXTRAS as Record<DashboardKey, CardExtras>)[card.permission],
}));

// Today is the organization's business date ("yyyy-MM-dd"), never the phone's clock; until the phone has one,
export function periodLabel(
  formats: Formatter,
  period: Period,
  businessDate: string | undefined,
) {
  const name = revenuePeriodLabel(period);

  if (!isDate(businessDate)) return name;
  if (period === "today")
    return `${name}, ${formats.formatDateOnly(businessDate)}`;
  if (period === "month")
    return `${name}, ${formats.formatDateRange(firstOfMonth(businessDate), businessDate)}`;

  const start = startOfWeek(businessDate, formats.firstDayOfWeek());

  return `${name}, ${formats.formatDateRange(start, shiftDate(start, 6))}`;
}
