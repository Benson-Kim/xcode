import { useEffect, useState } from "react";
import { StyleSheet, View } from "react-native";
import { apiGet, SessionEndedError } from "../lib/api";
import { money } from "../lib/format";
import type { StoredPerson } from "../lib/storage";
import type { RevenueDashboard } from "../revenue/types";
import { initials } from "../session";
import { Banner, Button, Text, useTheme } from "../ui";
import { VERSION } from "../auth/AuthLayout";
import { DASHBOARD_CARDS, SETUP_LINKS, TABS, periodLabel, type Period, type PermissionGroup, type Tab } from "./access";
import { Bullets, Card, CardAction, CardNote, CardValue, IconButton, LineSkeleton, ScreenTitle, SectionTitle, Segmented, WhoRow } from "./parts";

export type Catalog = { groups: PermissionGroup[] | null; error: string };

const PERIODS: { value: Period; label: string }[] = [
  { value: "today", label: "Today" },
  { value: "week", label: "This week" },
  { value: "month", label: "This month" },
];

// The cards backed by revenue records; the others keep their "not available yet" state until their data exists.
const REVENUE_CARDS = ["dash.capture", "dash.revenue", "dash.gaps", "dash.edits"];
const plural = (count: number, one: string, many: string) => `${count} ${count === 1 ? one : many}`;

// What a revenue card shows, from that card's own figures only, or null when the API left them out (null: not shown
// to this person). A note never speaks for a figure that is null.
function revenueFigures(permission: string, dashboard: RevenueDashboard): { value: string; note?: string } | null {
  const { capturedToday, vehiclesToday, revenue, expected, percent, missingDays, missingVehicles, editedRecords } = dashboard;
  if (permission === "dash.capture") {
    if (capturedToday === null || vehiclesToday === null) return null;
    const left = Math.max(0, vehiclesToday - capturedToday);
    return {
      value: `${capturedToday} of ${vehiclesToday} captured`,
      note: left ? `${plural(left, "vehicle", "vehicles")} still to capture` : "Every vehicle has a record for today.",
    };
  }
  if (permission === "dash.revenue") {
    if (revenue === null) return null;
    return {
      value: money(revenue),
      note: expected === null ? undefined : percent === null ? "No dated target is available." : `${percent}% of expected ${money(expected)}`,
    };
  }
  if (permission === "dash.gaps") {
    if (missingDays === null) return null;
    return {
      value: plural(missingDays, "day", "days"),
      note: !missingDays
        ? "No missing days so far this month."
        : missingVehicles === null
          ? undefined
          : `${plural(missingVehicles, "vehicle", "vehicles")} with missing days`,
    };
  }
  if (editedRecords === null) return null;
  return {
    value: plural(editedRecords, "record", "records"),
    note: editedRecords ? "Changed after the original capture." : "Nothing was changed after capture in this period.",
  };
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
  onOpen: (tab: Tab) => void;
  onLock: () => void;
  onSessionEnded: () => void;
}) {
  const { colors } = useTheme();
  const has = (permission: string) => person.permissions.includes(permission);
  // People who capture or spend start on today; everyone else on the month so far.
  const [period, setPeriod] = useState<Period>(has("dash.capture") || has("dash.float") ? "today" : "month");
  const cards = DASHBOARD_CARDS.filter((card) => has(card.permission));
  const label = periodLabel(period, businessDate);
  // Each revenue card reads the dashboard for its period: the one picked, or its own (missing days: the month).
  const periodOf = (card: (typeof cards)[number]) => card.period ?? period;
  const needed = [...new Set(cards.filter((card) => REVENUE_CARDS.includes(card.permission)).map(periodOf))].sort().join(",");
  const [dashboards, setDashboards] = useState<Partial<Record<Period, RevenueDashboard>>>({});
  const [dashboardError, setDashboardError] = useState("");
  useEffect(() => {
    setDashboards({});
    setDashboardError("");
    if (!needed || offline) return;
    let active = true;
    for (const each of needed.split(",") as Period[])
      apiGet<RevenueDashboard>(`setup/revenue/dashboard?period=${each}`).then(
        (value) => active && setDashboards((current) => ({ ...current, [each]: value })),
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
  return (
    <View style={styles.screen}>
      <WhoRow initials={initials(person)} name={`Hi ${person.firstName}`} role={person.role} action={<IconButton icon="lock" label="Lock app" onPress={onLock} />} />
      {offline && <Banner tone="offline">No internet. You are seeing what this phone saved at your last sign in.</Banner>}
      <Segmented label="Period" options={PERIODS} value={period} onChange={setPeriod} />
      <View style={[styles.chip, { backgroundColor: colors.divider }]}>
        <Text weight="semibold" style={{ fontSize: 14 }}>
          Your access
        </Text>
      </View>
      {cards.length ? (
        cards.map((card) => {
          // Revenue cards show the API's figures, never placeholder zeros while loading, offline or refused.
          const live = REVENUE_CARDS.includes(card.permission);
          const dashboard = dashboards[periodOf(card)];
          const figures = live && dashboard ? revenueFigures(card.permission, dashboard) : null;
          const sub = card.period ? `${periodLabel(card.period, businessDate)}. ${card.sub}` : (card.sub ?? label);
          return (
            <Card key={card.permission} title={card.title} sub={sub}>
              {!live ? (
                <>
                  <CardValue>{typeof card.value === "number" ? money(card.value) : card.value}</CardValue>
                  <CardNote>{card.note}</CardNote>
                </>
              ) : figures ? (
                <>
                  <CardValue>{figures.value}</CardValue>
                  {figures.note ? <CardNote>{figures.note}</CardNote> : null}
                </>
              ) : dashboard ? (
                <CardNote>Not shown with your access.</CardNote>
              ) : offline ? (
                <CardNote>Connect to the internet to see revenue figures.</CardNote>
              ) : dashboardError ? (
                <CardNote>{dashboardError}</CardNote>
              ) : (
                <LineSkeleton lines={2} />
              )}
              {card.action && card.tab && canOpen(card.tab) ? (
                <CardAction primary={card.primary} onPress={() => onOpen(card.tab!)}>
                  {card.action}
                </CardAction>
              ) : null}
            </Card>
          );
        })
      ) : (
        <Card title="Nothing to show yet" sub="Your admin decides what you can see here." />
      )}
      <Text style={[styles.version, { color: colors.grey }]}>{VERSION}</Text>
    </View>
  );
}

// Revenue and Spend: what the person may do there, from their permissions, until those screens are built.
export function ModuleScreen({ tab, person, catalog }: { tab: Tab; person: StoredPerson; catalog: Catalog }) {
  const definition = TABS.find((item) => item.id === tab)!;
  const labels = (catalog.groups ?? [])
    .filter((group) => definition.groups?.includes(group.name))
    .flatMap((group) => group.items.filter((item) => person.permissions.includes(item.key)).map((item) => item.label));
  return (
    <View style={styles.screen}>
      <ScreenTitle>{definition.label}</ScreenTitle>
      <Card title="What you can do here" sub="Based on your permissions">
        {catalog.groups ? <Bullets items={labels} /> : catalog.error ? <CardNote>{catalog.error}</CardNote> : <LineSkeleton />}
        <CardNote>{definition.unavailable ?? ""}</CardNote>
      </Card>
    </View>
  );
}

export function MoreScreen({ person, catalog, busy, onLock, onSwitchUser }: { person: StoredPerson; catalog: Catalog; busy: boolean; onLock: () => void; onSwitchUser: () => void }) {
  const { colors } = useTheme();
  const links = SETUP_LINKS.filter((link) => person.permissions.includes(link.permission));
  return (
    <View style={styles.screen}>
      <ScreenTitle>More</ScreenTitle>
      <WhoRow initials={initials(person)} name={`${person.firstName} ${person.lastName}`} role={person.role} />
      {links.length > 0 && (
        <View style={{ gap: 12 }}>
          <SectionTitle>Setup</SectionTitle>
          <View style={[styles.links, { borderColor: colors.cardLine, backgroundColor: colors.white }]}>
            {links.map((link, index) => (
              <View
                key={link.label}
                accessible
                accessibilityLabel={`${link.label}, on XCODE Web`}
                style={[styles.link, index > 0 && { borderTopWidth: 1, borderTopColor: colors.divider }]}
              >
                <Text style={{ flexShrink: 1 }}>{link.label}</Text>
                <Text style={{ fontSize: 13, color: colors.grey, flexShrink: 0 }}>On XCODE Web</Text>
              </View>
            ))}
          </View>
        </View>
      )}
      <SectionTitle>Your access</SectionTitle>
      <View style={[styles.access, { borderColor: colors.cardLine, backgroundColor: colors.white }]}>
        <View>
          <Text style={{ fontSize: 13, color: colors.grey }}>Role</Text>
          <Text weight="semibold">{person.role || "Not assigned"}</Text>
        </View>
        {catalog.groups ? (
          catalog.groups.map((group) => {
            const mine = group.items.filter((item) => person.permissions.includes(item.key));
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
      <Button tone="outline" busy={busy} busyText="Switching…" onPress={onSwitchUser}>
        Switch user
      </Button>
      <Text style={[styles.version, { color: colors.grey }]}>{VERSION}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { gap: 16 },
  chip: { alignSelf: "flex-start", minHeight: 36, paddingHorizontal: 12, borderRadius: 999, justifyContent: "center" },
  version: { fontSize: 12, textAlign: "center", marginTop: 8 },
  links: { borderWidth: 1, borderRadius: 14, overflow: "hidden" },
  link: { minHeight: 52, paddingHorizontal: 16, paddingVertical: 8, flexDirection: "row", justifyContent: "space-between", alignItems: "center", gap: 12 },
  access: { borderWidth: 1, borderRadius: 14, padding: 20, gap: 8 },
});
