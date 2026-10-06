import { useCallback, useEffect, useRef, useState } from "react";
import { Pressable, ScrollView, StyleSheet, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { SessionEndedError, apiGet } from "../lib/api";
import type { StoredPerson } from "../lib/storage";
import { queueCounts, useRevenueQueue } from "../revenue/queue";
import { Icon, Text, useTheme } from "../ui";
import { allowedTabs, type PermissionGroup, type Tab } from "./access";
import { RevenueScreen } from "./RevenueScreen";
import { HomeScreen, ModuleScreen, MoreScreen, type Catalog } from "./screens";

type Props = {
  person: StoredPerson;
  offline: boolean;
  // The organization's business date as last loaded ("yyyy-MM-dd"), kept for offline use; every "today" comes from it.
  businessDate?: string;
  onLock: () => void;
  onSwitchUser: () => Promise<void>;
  onSessionEnded: () => void;
};

// The signed-in app: one screen at a time above the bottom menu. Menus show only what the person may use;
// the server checks every action.
export function AppShell({ person, offline, businessDate, onLock, onSwitchUser, onSessionEnded }: Props) {
  const { colors, fontScale } = useTheme();
  const insets = useSafeAreaInsets();
  const [tab, setTab] = useState<Tab>("home");
  const [catalog, setCatalog] = useState<Catalog>({ groups: null, error: "" });
  const [switching, setSwitching] = useState(false);
  const scroll = useRef<ScrollView>(null);
  const tabs = allowedTabs(person.permissions);
  // One callback for the life of this screen, so screens that load data do not reload when the app redraws.
  const ended = useRef(onSessionEnded);
  useEffect(() => {
    ended.current = onSessionEnded;
  });
  const sessionEnded = useCallback(() => ended.current(), []);
  // Revenue captured on this phone and not yet accepted by the API.
  const queue = useRevenueQueue(person.userId, sessionEnded);
  const counts = queueCounts(queue.entries);
  const unsent = [
    counts.waiting ? `${counts.waiting} waiting to send` : "",
    counts.conflicts ? `${counts.conflicts} ${counts.conflicts === 1 ? "conflict" : "conflicts"}` : "",
    counts.failed ? `${counts.failed} not saved` : "",
  ].filter(Boolean);

  // Permission names for Your access and the module screens.
  useEffect(() => {
    let active = true;
    apiGet<PermissionGroup[]>("setup/access/catalog")
      .then((groups) => active && setCatalog({ groups, error: "" }))
      .catch((error: Error) => {
        if (!active) return;
        if (error instanceof SessionEndedError) return sessionEnded();
        setCatalog({ groups: null, error: offline ? "Connect to the internet to see your permissions." : error.message });
      });
    return () => {
      active = false;
    };
  }, [offline, sessionEnded]);

  function open(next: Tab) {
    setTab(next);
    scroll.current?.scrollTo({ y: 0, animated: false });
  }

  return (
    <View style={[styles.shell, { backgroundColor: colors.cream }]}>
      {tab === "revenue" ? (
        // The revenue lists scroll themselves (FlatList), so only the rows on screen are drawn.
        <RevenueScreen person={person} queue={queue} businessDate={businessDate} onSessionEnded={sessionEnded} />
      ) : (
        <ScrollView ref={scroll} contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
          {tab === "home" ? (
            <HomeScreen
              person={person}
              offline={offline}
              businessDate={businessDate}
              canOpen={(target) => tabs.some((item) => item.id === target)}
              onOpen={open}
              onLock={onLock}
              onSessionEnded={sessionEnded}
            />
          ) : tab === "more" ? (
            <MoreScreen
              person={person}
              catalog={catalog}
              busy={switching}
              onLock={onLock}
              onSwitchUser={() => {
                setSwitching(true);
                void onSwitchUser().finally(() => setSwitching(false));
              }}
            />
          ) : (
            <ModuleScreen tab={tab} person={person} catalog={catalog} />
          )}
        </ScrollView>
      )}
      <View accessibilityRole="tablist" accessibilityLabel="Main" style={[styles.nav, { borderTopColor: colors.cardLine, backgroundColor: colors.surface, paddingBottom: insets.bottom }]}>
        {tabs.map((item) => {
          const current = item.id === tab;
          const badge = item.id === "revenue" && unsent.length ? counts.waiting + counts.conflicts + counts.failed : 0;
          return (
            <Pressable
              key={item.id}
              accessibilityRole="tab"
              accessibilityLabel={badge ? `${item.label}, ${unsent.join(", ")}` : item.label}
              accessibilityState={{ selected: current }}
              onPress={() => open(item.id)}
              style={[styles.navItem, current && { borderTopColor: colors.blue }]}
            >
              <View>
                <Icon name={item.icon} size={24} color={current ? colors.blue : colors.grey} />
                {badge ? (
                  <View
                    style={[
                      styles.badge,
                      // The count grows with the person's text size, and its circle with it.
                      { top: -6 * fontScale, minWidth: 18 * fontScale, height: 18 * fontScale, borderRadius: 9 * fontScale },
                      { backgroundColor: counts.conflicts || counts.failed ? colors.red : colors.amberText },
                    ]}
                  >
                    <Text weight="bold" style={{ fontSize: 11, lineHeight: 14, color: colors.onFill }}>
                      {badge > 99 ? "99+" : String(badge)}
                    </Text>
                  </View>
                ) : null}
              </View>
              <Text weight="semibold" style={{ fontSize: 12, lineHeight: 16, color: current ? colors.blue : colors.grey, textDecorationLine: current ? "underline" : "none" }}>
                {item.label}
              </Text>
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  shell: { flex: 1 },
  content: { width: "100%", maxWidth: 420, alignSelf: "center", paddingTop: 28, paddingHorizontal: 24, paddingBottom: 32 },
  nav: { flexDirection: "row", borderTopWidth: 1 },
  badge: { position: "absolute", top: -6, left: 14, minWidth: 18, height: 18, paddingHorizontal: 4, borderRadius: 9, alignItems: "center", justifyContent: "center" },
  navItem: { flex: 1, minHeight: 64, alignItems: "center", justifyContent: "center", gap: 3, borderTopWidth: 3, borderTopColor: "transparent" },
});
