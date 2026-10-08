import { useEffect, useState } from "react";
import { StyleSheet, View } from "react-native";

import {
  initials,
  percentText,
  plural,
  type Formatter,
} from "@xcode/shared/format";
import {
  canSee,
  permissionChecker,
  startsOnToday,
  type DashboardKey,
} from "@xcode/shared/permissions";
import {
  canOpenPettyCash,
  type PettyCashDashboard,
} from "@xcode/shared/pettyCash";
import { REVENUE_PERIODS } from "@xcode/shared/revenue";

import { VERSION } from "../auth/AuthLayout";
import { apiGet, SessionEndedError } from "../lib/api";
import { useFormats } from "../lib/formats";
import { useConnected } from "../lib/network";
import type { StoredPerson } from "../lib/storage";
import { PETTY_CASH_CARDS, pettyFigures } from "../pettycash/dashboard";
import {
  PettyCashScreen,
  type PettyCashSection,
} from "../pettycash/PettyCashScreen";
import { firstOfMonth, isDate, shiftDate } from "../revenue/dates";
import type { RevenueDashboard } from "../revenue/types";
import { Banner, Button, Text, useTheme } from "../ui";
import {
  DASHBOARD_CARDS,
  periodLabel,
  SETUP_LINKS,
  TABS,
  type Period,
  type PermissionGroup,
  type Tab,
} from "./access";
import {
  Bullets,
  Card,
  CardAction,
  CardNote,
  CardValue,
  Chip,
  IconButton,
  LineSkeleton,
  ProgressBar,
  ScreenTitle,
  SectionTitle,
  Segmented,
  WhoRow,
} from "./parts";

export type Catalog = { groups: PermissionGroup[] | null; error: string };

// The cards backed by revenue records; the others keep their "not available yet" state until their data exists.
const REVENUE_CARDS: readonly DashboardKey[] = [
  "dash.capture",
  "dash.revenue",
  "dash.gaps",
  "dash.edits",
];

type Figures = {
  value?: string;
  bad?: boolean;
  bar?: number;
  note?: string;
  list?: string[];
};

// What a revenue card shows, from that card's own figures only, or null when the API left them out (null: not shown
// to this person). A note never speaks for a figure that is null.
// The wording follows XCODE Web.
function revenueFigures(
  formats: Formatter,
  permission: string,
  dashboard: RevenueDashboard,
  period: Period,
): Figures | null {
  const {
    capturedToday,
    vehiclesToday,
    revenue,
    expected,
    percent,
    missingDays,
    missingVehicles,
    editedRecords,
  } = dashboard;
  if (permission === "dash.capture") {
    if (capturedToday === null || vehiclesToday === null) return null;
    if (vehiclesToday === 0)
      return { note: "None of your vehicles is in the fleet today." };
    const left = Math.max(0, vehiclesToday - capturedToday);
    return {
      value: `${capturedToday} of ${vehiclesToday} captured`,
      note: left
        ? `${plural(left, "vehicle", "vehicles")} still to capture`
        : "Every vehicle has a record for today.",
    };
  }
  if (permission === "dash.revenue") {
    if (revenue === null) return null;
    const soFar =
      period !== "month" && capturedToday !== null && vehiclesToday
        ? `. ${capturedToday} of ${vehiclesToday} vehicles have a record so far.`
        : "";
    if (percent === null || expected === null)
      return {
        value: revenue ? formats.kes(revenue) : undefined,
        note: `No weekly target applies in this period${soFar}`,
      };
    return {
      value: formats.kes(revenue),
      bar: percent,
      note: `${percentText(percent)} of target ${formats.kes(expected)}, from each vehicle’s weekly target${soFar}`,
    };
  }
  if (permission === "dash.gaps") {
    if (missingDays === null) return null;
    return {
      value: plural(missingDays, "day", "days"),
      bad: missingDays > 0,
      note: missingDays
        ? `${missingVehicles === null ? "" : `On ${plural(missingVehicles, "vehicle", "vehicles")}. `}Always this month, whatever period you pick.`
        : "Every vehicle has a record for every day.",
    };
  }
  if (editedRecords === null) return null;
  return {
    value: plural(editedRecords, "record", "records"),
    note: editedRecords
      ? undefined
      : "Nothing was changed after capture in this period.",
  };
}

// Missing days count the month up to yesterday: today is not a gap before it is captured.
function gapsSub(formats: Formatter, businessDate?: string) {
  if (!isDate(businessDate)) return "This month. No record and no reason.";
  const first = firstOfMonth(businessDate);
  const yesterday = shiftDate(businessDate, -1);
  return first <= yesterday
    ? `${formats.formatDateRange(first, yesterday)}. No record and no reason.`
    : "No record and no reason.";
}

export function HomeScreen({
  person,
  offline,
  businessDate,
  canOpen,
  onOpen,
  onLock,
  onSessionEnded,
}: {
  person: StoredPerson;
  offline: boolean;
  businessDate?: string;
  canOpen: (tab: Tab) => boolean;
  onOpen: (tab: Tab, section?: PettyCashSection) => void;
  onLock: () => void;
  onSessionEnded: () => void;
}) {
  const { colors } = useTheme();
  const formats = useFormats();
  const connected = useConnected();
  const has = permissionChecker(person.permissions);
  // People who capture or spend start on today; everyone else on the month so far.
  const [period, setPeriod] = useState<Period>(
    startsOnToday(has) ? "today" : "month",
  );
  const cards = DASHBOARD_CARDS.filter((card) => has(card.permission));
  const label = periodLabel(formats, period, businessDate);
  // Each revenue card reads the dashboard for its period: the one picked, or its own (missing days: the month).
  const periodOf = (card: (typeof cards)[number]) => card.period ?? period;
  const needed = [
    ...new Set(
      cards
        .filter((card) => REVENUE_CARDS.includes(card.permission))
        .map(periodOf),
    ),
  ]
    .sort()
    .join(",");
  const [dashboards, setDashboards] = useState<
    Partial<Record<Period, RevenueDashboard>>
  >({});
  const [dashboardError, setDashboardError] = useState("");
  useEffect(() => {
    setDashboards({});
    setDashboardError("");
    if (!needed || offline) return;
    let active = true;
    for (const each of needed.split(",") as Period[])
      apiGet<RevenueDashboard>(`setup/revenue/dashboard?period=${each}`).then(
        (value) =>
          active && setDashboards((current) => ({ ...current, [each]: value })),
        (reason: Error) => {
          if (!active) return;
          if (reason instanceof SessionEndedError) return onSessionEnded();
          setDashboardError(reason.message);
        },
      );
    return () => {
      active = false;
    };
  }, [needed, offline, onSessionEnded]);
  const wantsPetty = cards.some((card) =>
    PETTY_CASH_CARDS.includes(card.permission),
  );
  const [petty, setPetty] = useState<PettyCashDashboard | null>(null);
  const [pettyError, setPettyError] = useState("");
  useEffect(() => {
    setPetty(null);
    setPettyError("");
    if (!wantsPetty || offline) return;
    let active = true;
    apiGet<PettyCashDashboard>("setup/pettycash/dashboard").then(
      (value) => active && setPetty(value),
      (reason: Error) => {
        if (!active) return;
        if (reason instanceof SessionEndedError) return onSessionEnded();
        setPettyError(reason.message);
      },
    );
    return () => {
      active = false;
    };
  }, [wantsPetty, offline, onSessionEnded]);
  return (
    <View style={styles.screen}>
      <WhoRow
        initials={initials(person.firstName, person.lastName)}
        name={`Hi ${person.firstName}`}
        role={person.role}
        action={<IconButton icon="lock" label="Lock app" onPress={onLock} />}
      />
      {offline && (
        <Banner tone="offline">
          {`${connected ? "Can't reach the XCODE server." : "No internet."} You are seeing what this phone saved at your last sign in.`}
        </Banner>
      )}
      <Segmented
        label="Period"
        options={REVENUE_PERIODS.map((option) => ({ ...option }))}
        value={period}
        onChange={setPeriod}
      />
      <View style={[styles.chip, { backgroundColor: colors.divider }]}>
        <Text weight="semibold" style={{ fontSize: 14 }}>
          Your access
        </Text>
      </View>
      {cards.length ? (
        cards.map((card) => {
          // Live cards show the API's figures, never placeholder zeros while loading, offline or refused.
          const live = REVENUE_CARDS.includes(card.permission);
          const isPetty = PETTY_CASH_CARDS.includes(card.permission);
          const dashboard = dashboards[periodOf(card)];
          const loaded = isPetty ? petty : dashboard;
          const failed = isPetty ? pettyError : dashboardError;
          const figures: Figures | null = isPetty
            ? petty
              ? pettyFigures(formats, card.permission, petty)
              : null
            : live && dashboard
              ? revenueFigures(
                  formats,
                  card.permission,
                  dashboard,
                  periodOf(card),
                )
              : null;
          const sub =
            card.permission === "dash.capture"
              ? `Your vehicles, ${isDate(businessDate) ? formats.formatDateOnly(businessDate) : "today"}`
              : card.permission === "dash.gaps"
                ? gapsSub(formats, businessDate)
                : (card.sub ?? "").replace("{period}", label);
          const action =
            card.action &&
            card.tab &&
            canOpen(card.tab) &&
            (!card.actionNeeds || card.actionNeeds.some(has));
          return (
            <Card key={card.permission} title={card.title} sub={sub}>
              {card.unavailable ? (
                <>
                  <Chip>Not available yet</Chip>
                  <CardNote>{card.unavailable}</CardNote>
                </>
              ) : figures ? (
                <>
                  {figures.value ? (
                    <CardValue bad={figures.bad}>{figures.value}</CardValue>
                  ) : null}
                  {figures.bar !== undefined ? (
                    <ProgressBar percent={figures.bar} />
                  ) : null}
                  {figures.note ? <CardNote>{figures.note}</CardNote> : null}
                  {figures.list?.length ? (
                    <Bullets items={figures.list} />
                  ) : null}
                </>
              ) : loaded ? (
                <CardNote>Not shown with your access.</CardNote>
              ) : offline ? (
                <CardNote>
                  {`Connect to the internet to see ${isPetty ? "petty cash" : "revenue"} figures.`}
                </CardNote>
              ) : failed ? (
                <CardNote>{failed}</CardNote>
              ) : (
                <LineSkeleton lines={2} />
              )}
              {action ? (
                <CardAction
                  primary={card.primary}
                  onPress={() => onOpen(card.tab!, card.section)}
                >
                  {card.action!}
                </CardAction>
              ) : null}
            </Card>
          );
        })
      ) : (
        <Card
          title="Nothing to show yet"
          sub="Your admin decides what you can see here."
        />
      )}
      <Text style={[styles.version, { color: colors.grey }]}>{VERSION}</Text>
    </View>
  );
}

// Spend: petty cash for people with any petty cash permission; what else they may do there (office bills), from
// their permissions, until that screen is built.
export function ModuleScreen({
  tab,
  person,
  catalog,
  offline,
  businessDate,
  start,
  onSessionEnded,
}: {
  tab: Tab;
  person: StoredPerson;
  catalog: Catalog;
  offline: boolean;
  businessDate?: string;
  start?: PettyCashSection;
  onSessionEnded: () => void;
}) {
  const definition = TABS.find((item) => item.id === tab)!;
  const labels = (catalog.groups ?? [])
    .filter((group) => definition.groups?.includes(group.name))
    .flatMap((group) =>
      group.items
        .filter((item) => person.permissions.includes(item.key))
        .map((item) => item.label),
    );
  const petty = tab === "spend" && canOpenPettyCash(person.permissions);
  const others =
    tab !== "spend" || permissionChecker(person.permissions)("bills.view");
  return (
    <View style={styles.screen}>
      <ScreenTitle>{definition.label}</ScreenTitle>
      {petty ? (
        <PettyCashScreen
          offline={offline}
          businessDate={businessDate}
          start={start}
          onSessionEnded={onSessionEnded}
        />
      ) : null}
      {others ? (
        <Card title="What you can do here" sub="Based on your permissions">
          {catalog.groups ? (
            <Bullets items={labels} />
          ) : catalog.error ? (
            <CardNote>{catalog.error}</CardNote>
          ) : (
            <LineSkeleton />
          )}
          <CardNote>{definition.unavailable ?? ""}</CardNote>
        </Card>
      ) : null}
    </View>
  );
}

export function MoreScreen({
  person,
  catalog,
  busy,
  onLock,
  onSwitchUser,
}: {
  person: StoredPerson;
  catalog: Catalog;
  busy: boolean;
  onLock: () => void;
  onSwitchUser: () => void;
}) {
  const { colors } = useTheme();
  const has = permissionChecker(person.permissions);
  const links = SETUP_LINKS.filter((link) => canSee(link, has));
  return (
    <View style={styles.screen}>
      <ScreenTitle>More</ScreenTitle>
      <WhoRow
        initials={initials(person.firstName, person.lastName)}
        name={`${person.firstName} ${person.lastName}`}
        role={person.role}
      />
      {links.length > 0 && (
        <View style={{ gap: 12 }}>
          <SectionTitle>Setup</SectionTitle>
          <View
            style={[
              styles.links,
              { borderColor: colors.cardLine, backgroundColor: colors.surface },
            ]}
          >
            {links.map((link, index) => (
              <View
                key={link.label}
                accessible
                accessibilityLabel={`${link.label}, on XCODE Web`}
                style={[
                  styles.link,
                  index > 0 && {
                    borderTopWidth: 1,
                    borderTopColor: colors.divider,
                  },
                ]}
              >
                <Text style={{ flexShrink: 1 }}>{link.label}</Text>
                <Text
                  style={{ fontSize: 13, color: colors.grey, flexShrink: 0 }}
                >
                  On XCODE Web
                </Text>
              </View>
            ))}
          </View>
        </View>
      )}
      <SectionTitle>Your access</SectionTitle>
      <View
        style={[
          styles.access,
          { borderColor: colors.cardLine, backgroundColor: colors.surface },
        ]}
      >
        <View>
          <Text style={{ fontSize: 13, color: colors.grey }}>Role</Text>
          <Text weight="semibold">{person.role || "Not assigned"}</Text>
        </View>
        {catalog.groups ? (
          catalog.groups.map((group) => {
            const mine = group.items.filter((item) =>
              person.permissions.includes(item.key),
            );
            if (!mine.length) return null;
            return (
              <View key={group.name} style={{ gap: 4 }}>
                <Text weight="bold" style={{ fontSize: 14, marginTop: 8 }}>
                  {group.name}
                </Text>
                <Bullets items={mine.map((item) => item.label)} />
              </View>
            );
          })
        ) : catalog.error ? (
          <CardNote>{catalog.error}</CardNote>
        ) : (
          <LineSkeleton lines={4} />
        )}
      </View>
      <Button tone="outline" disabled={busy} onPress={onLock}>
        Lock app
      </Button>
      <Button
        tone="outline"
        busy={busy}
        busyText="Switching…"
        onPress={onSwitchUser}
      >
        Switch user
      </Button>
      <Text style={[styles.version, { color: colors.grey }]}>{VERSION}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { gap: 16 },
  chip: {
    alignSelf: "flex-start",
    minHeight: 36,
    paddingHorizontal: 12,
    borderRadius: 999,
    justifyContent: "center",
  },
  version: { fontSize: 12, textAlign: "center", marginTop: 8 },
  links: { borderWidth: 1, borderRadius: 14, overflow: "hidden" },
  link: {
    minHeight: 52,
    paddingHorizontal: 16,
    paddingVertical: 8,
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    gap: 12,
  },
  access: { borderWidth: 1, borderRadius: 14, padding: 20, gap: 8 },
});
