import { useEffect, useState } from "react";
import { Linking, Platform, StyleSheet, View } from "react-native";

import { onUpdateRequired } from "../lib/api";
import { androidPackage, appVersion } from "../lib/appVersion";
import { Button, Text, useTheme } from "../ui";

// Google Play opens on the app's own page. iOS gets no button until the app has an App Store id.
const storeUrl =
  Platform.OS === "android" && process.env.EXPO_PUBLIC_DISTRIBUTION === "store"
    ? `https://play.google.com/store/apps/details?id=${androidPackage}`
    : null;

type Required = { minimumVersion: string | null } | null;

// Set once the API refuses this version. It stays until the app restarts, which updating it does.
export function useUpdateRequired(): Required {
  const [required, setRequired] = useState<Required>(null);
  useEffect(
    () => onUpdateRequired((minimumVersion) => setRequired({ minimumVersion })),
    [],
  );
  return required;
}

export function UpdateRequired({
  minimumVersion,
}: {
  minimumVersion: string | null;
}) {
  const { colors } = useTheme();
  return (
    <View style={styles.screen}>
      <Text weight="bold" accessibilityRole="header" style={styles.h1}>
        Update XCODE
      </Text>
      <Text style={{ color: colors.grey }}>
        {`This version of XCODE (${appVersion}) is no longer supported. ${
          minimumVersion
            ? `Install version ${minimumVersion} or newer`
            : "Install the latest version"
        } to carry on. Anything waiting to be sent stays on this phone.`}
      </Text>
      {storeUrl && (
        <Button onPress={() => void Linking.openURL(storeUrl)}>
          Open Google Play
        </Button>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, justifyContent: "center", gap: 16, padding: 24 },
  h1: { fontSize: 26, lineHeight: 31 },
});
