import { useEffect, useRef, useState } from "react";
import { Pressable, ScrollView, StyleSheet, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { SessionEndedError, apiGet } from "../lib/api";
import type { StoredPerson } from "../lib/storage";
import { Icon, Text, useTheme } from "../ui";
import { allowedTabs, type PermissionGroup, type Tab } from "./access";
import { HomeScreen, ModuleScreen, MoreScreen, type Catalog } from "./screens";

type Props = {
  person: StoredPerson;
  offline: boolean;
  onLock: () => void;
  onSwitchUser: () => Promise<void>;
  onSessionEnded: () => void;
};

// The signed-in app: one screen at a time above the bottom menu. Menus show only what the person may use;
// the server checks every action.
export function AppShell({ person, offline, onLock, onSwitchUser, onSessionEnded }: Props) {
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const [tab, setTab] = useState<Tab>("home");
  const [catalog, setCatalog] = useState<Catalog>({ groups: null, error: "" });
  const [switching, setSwitching] = useState(false);
  const scroll = useRef<ScrollView>(null);
  const tabs = allowedTabs(person.permissions);

  // Permission names for Your access and the module screens.
  useEffect(() => {
    let active = true;
    apiGet<PermissionGroup[]>("setup/access/catalog")
      .then((groups) => active && setCatalog({ groups, error: "" }))
      .catch((error: Error) => {
        if (!active) return;
        if (error instanceof SessionEndedError) return onSessionEnded();
        setCatalog({ groups: null, error: offline ? "Connect to the internet to see your permissions." : error.message });
      });
    return () => {
      active = false;
    };
    // onSessionEnded is stable for the life of this signed-in screen.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [offline]);

  function open(next: Tab) {
    setTab(next);
    scroll.current?.scrollTo({ y: 0, animated: false });
  }

  return (
    <View style={[styles.shell, { backgroundColor: colors.cream }]}>
      <ScrollView ref={scroll} contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
        {tab === "home" ? (
          <HomeScreen person={person} offline={offline} canOpen={(target) => tabs.some((item) => item.id === target)} onOpen={open} onLock={onLock} />
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
      <View accessibilityRole="tablist" accessibilityLabel="Main" style={[styles.nav, { borderTopColor: colors.cardLine, backgroundColor: colors.white, paddingBottom: insets.bottom }]}>
        {tabs.map((item) => {
          const current = item.id === tab;
          return (
            <Pressable
              key={item.id}
              accessibilityRole="tab"
              accessibilityLabel={item.label}
              accessibilityState={{ selected: current }}
              onPress={() => open(item.id)}
              style={[styles.navItem, current && { borderTopColor: colors.blue }]}
            >
              <Icon name={item.icon} size={24} color={current ? colors.blue : colors.grey} />
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
  navItem: { flex: 1, minHeight: 64, alignItems: "center", justifyContent: "center", gap: 3, borderTopWidth: 3, borderTopColor: "transparent" },
});
