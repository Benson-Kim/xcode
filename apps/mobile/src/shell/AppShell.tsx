import { useState } from "react";
import { ScrollView, StyleSheet, View } from "react-native";
import { VERSION } from "../auth/AuthLayout";
import type { StoredPerson } from "../lib/storage";
import { initials } from "../session";
import { Banner, Button, Text, useTheme } from "../ui";
import { IconButton, WhoRow } from "./parts";

type Props = {
  person: StoredPerson;
  offline: boolean;
  onLock: () => void;
  onSwitchUser: () => Promise<void>;
  onSessionEnded: () => void;
};

// Signed in: who the phone is trusted for, with lock and switch user. The dashboard, bottom menu and
// Your access, driven by the person's permissions, come with people and access.
export function AppShell({ person, offline, onLock, onSwitchUser }: Props) {
  const { colors } = useTheme();
  const [switching, setSwitching] = useState(false);
  return (
    <ScrollView style={{ backgroundColor: colors.cream }} contentContainerStyle={styles.content}>
      <View style={styles.screen}>
        <WhoRow initials={initials(person)} name={`Hi ${person.firstName}`} role={person.role} action={<IconButton icon="lock" label="Lock app" onPress={onLock} />} />
        {offline && <Banner tone="offline">No internet. You are seeing what this phone saved at your last sign in.</Banner>}
        <Button
          tone="outline"
          busy={switching}
          busyText="Switching…"
          onPress={() => {
            setSwitching(true);
            void onSwitchUser().finally(() => setSwitching(false));
          }}
        >
          Switch user
        </Button>
        <Text style={[styles.version, { color: colors.grey }]}>{VERSION}</Text>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  content: { width: "100%", maxWidth: 420, alignSelf: "center", paddingTop: 28, paddingHorizontal: 24, paddingBottom: 32 },
  screen: { gap: 16 },
  version: { fontSize: 12, textAlign: "center", marginTop: 8 },
});
