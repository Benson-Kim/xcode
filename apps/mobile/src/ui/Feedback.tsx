import type { ReactNode } from "react";
import { StyleSheet, View } from "react-native";

import { Icon } from "./Icon";
import { Text } from "./Text";
import { useTheme } from "./theme";

export function ErrorText({
  children,
  center,
}: {
  children: string;
  center?: boolean;
}) {
  const { colors } = useTheme();
  if (!children) return null;
  return (
    <View
      accessibilityRole="alert"
      accessibilityLiveRegion="polite"
      style={[styles.error, center && styles.center]}
    >
      <View style={styles.icon}>
        <Icon name="alert" size={18} color={colors.red} />
      </View>
      <Text
        style={[
          styles.errorText,
          { color: colors.red },
          center && { textAlign: "center" },
        ]}
      >
        {children}
      </Text>
    </View>
  );
}

export function Banner({
  tone = "error",
  children,
}: {
  tone?: "error" | "offline";
  children: string;
}) {
  const { colors } = useTheme();
  const offline = tone === "offline";
  return (
    <View
      accessibilityRole={offline ? undefined : "alert"}
      accessibilityLiveRegion="polite"
      style={[
        styles.banner,
        offline
          ? { backgroundColor: colors.amberBg, borderColor: colors.amberLine }
          : { backgroundColor: colors.redBg, borderColor: colors.redLine },
      ]}
    >
      <View style={styles.icon}>
        <Icon
          name={offline ? "offline" : "alert"}
          size={18}
          color={offline ? colors.amberText : colors.redText}
        />
      </View>
      <Text
        style={{
          flex: 1,
          fontSize: 15,
          color: offline ? colors.amberText : colors.redText,
        }}
      >
        {children}
      </Text>
    </View>
  );
}

export function DemoBox({ children }: { children: ReactNode }) {
  const { colors } = useTheme();
  return (
    <View style={[styles.demo, { borderColor: colors.line }]}>{children}</View>
  );
}

const styles = StyleSheet.create({
  error: { flexDirection: "row", gap: 6, alignItems: "flex-start" },
  center: { justifyContent: "center" },
  icon: { marginTop: 2 },
  errorText: { flexShrink: 1, fontSize: 14, lineHeight: 20 },
  banner: {
    flexDirection: "row",
    gap: 10,
    alignItems: "flex-start",
    paddingVertical: 12,
    paddingHorizontal: 14,
    borderRadius: 12,
    borderWidth: 1,
  },
  demo: {
    paddingVertical: 10,
    paddingHorizontal: 14,
    borderWidth: 1,
    borderStyle: "dashed",
    borderRadius: 12,
    gap: 4,
  },
});
