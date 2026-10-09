import { useState } from "react";
import { StyleSheet, View } from "react-native";

import {
  RELEASE,
  installUpdate,
  useAvailableUpdate,
  type AvailableUpdate,
  type UpdateSource,
} from "../lib/updates";
import { Button, LinkButton, Text, useTheme } from "../ui";

// Shown above every screen when a newer build is published. Update downloads it for Android to install; Later hides
// it until the app is opened again.
export function UpdateNotice({
  source = RELEASE,
  fetcher = fetch,
}: {
  source?: UpdateSource;
  fetcher?: typeof fetch;
}) {
  const update = useAvailableUpdate(source, fetcher);
  const [later, setLater] = useState(false);
  if (!update || later) return null;
  return (
    <UpdateBanner
      update={update}
      onUpdate={() => void installUpdate(update)}
      onLater={() => setLater(true)}
    />
  );
}

function UpdateBanner({
  update,
  onUpdate,
  onLater,
}: {
  update: AvailableUpdate;
  onUpdate: () => void;
  onLater: () => void;
}) {
  const { colors } = useTheme();
  return (
    <View
      accessible={false}
      role="status"
      accessibilityLiveRegion="polite"
      style={[
        styles.bar,
        { backgroundColor: colors.blueSoft, borderColor: colors.blueTint },
      ]}
    >
      <Text style={[styles.text, { color: colors.navy }]}>
        {`A new version of XCODE is ready (${update.version}).`}
      </Text>
      <View style={styles.actions}>
        <LinkButton onPress={onLater}>Later</LinkButton>
        <Button onPress={onUpdate} style={styles.button}>
          Update
        </Button>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  bar: {
    flexDirection: "row",
    flexWrap: "wrap",
    alignItems: "center",
    gap: 8,
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderBottomWidth: 1,
  },
  text: { flex: 1, minWidth: 180, fontSize: 14 },
  actions: { flexDirection: "row", alignItems: "center", gap: 12 },
  button: { minHeight: 36, paddingHorizontal: 14 },
});
