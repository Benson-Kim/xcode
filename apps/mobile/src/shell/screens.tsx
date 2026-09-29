import { useEffect, useState } from "react";
import { StyleSheet, View } from "react-native";
import { apiGet, SessionEndedError } from "../lib/api";
import { money } from "../lib/format";
import type { RevenueDashboard } from "@xcode/shared";
import type { StoredPerson } from "../lib/storage";
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

export function HomeScreen({ person, offline, canOpen, onOpen, onLock, onSessionEnded }: { person: StoredPerson; offline: boolean; canOpen: (tab: Tab) => boolean; onOpen: (tab: Tab) => void; onLock: () => void; onSessionEnded: () => void }) {
  const { colors } = useTheme();
  const has = (permission: string) => person.permissions.includes(permission);
  // People who capture or spend start on today; everyone else on the month so far.
  const [period, setPeriod] = useState<Period>(has("dash.capture") || has("dash.float") ? "today" : "month");
  const cards = DASHBOARD_CARDS.filter((card) => has(card.permission));
  const label = periodLabel(period);
  const [dashboard, setDashboard] = useState<RevenueDashboard | null>(null);
  const [dashboardError, setDashboardError] = useState("");
  const dashboardPath = `setup/revenue/dashboard?period=${period}`;
  useEffect(() => {
    const shouldLoad = person.permissions.some((permission) =>
      ["dash.capture", "dash.revenue", "dash.gaps", "dash.edits"].includes(permission),
    );
    if (!shouldLoad || offline) {
      setDashboard(null);
      return;
    }
    let active = true;
    setDashboardError("");
    apiGet<RevenueDashboard>(dashboardPath).then(
      (value) => active && setDashboard(value),
      (reason: Error) => {
        if (!active) return;
        if (reason instanceof SessionEndedError) return onSessionEnded();
        setDashboardError(reason.message);
      },
    );
    return () => {
      active = false;
    };
  }, [dashboardPath, offline, onSessionEnded, person.permissions]);
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
          const value =
            card.permission === "dash.capture" && dashboard
              ? `${dashboard.capturedToday} of ${dashboard.vehiclesToday} captured`
              : card.permission === "dash.revenue" && dashboard
                ? money(dashboard.revenue)
                : card.permission === "dash.gaps" && dashboard
                  ? `${dashboard.missingDays} ${dashboard.missingDays === 1 ? "day" : "days"}`
                  : card.permission === "dash.edits" && dashboard
                    ? `${dashboard.editedRecords} ${dashboard.editedRecords === 1 ? "record" : "records"}`
                    : typeof card.value === "number"
                      ? money(card.value)
                      : card.value;
          const note =
            dashboardError ||
            (card.permission === "dash.capture" && dashboard
              ? `${Math.max(0, dashboard.vehiclesToday - dashboard.capturedToday)} still to capture`
              : card.permission === "dash.revenue" && dashboard
                ? dashboard.percent === null
                  ? "No dated target is available."
                  : `${dashboard.percent}% of expected ${money(dashboard.expected)}`
                : card.permission === "dash.gaps" && dashboard
                  ? `${dashboard.missingVehicles} vehicles with missing days`
                  : card.permission === "dash.edits" && dashboard
                    ? "Changed after the original capture."
                    : card.note);
          return (
            <Card key={card.permission} title={card.title} sub={card.sub ?? label}>
              <CardValue>{value}</CardValue>
              <CardNote>{note}</CardNote>
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
