import { Pressable, StyleSheet } from "react-native";

import { Icon } from "./Icon";
import { Text } from "./Text";
import { useTheme } from "./theme";

// The one show/hide control of every PIN entry.
export function ShowPinToggle({
  shown,
  onToggle,
}: {
  shown: boolean;
  onToggle: () => void;
}) {
  const { colors } = useTheme();
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={shown ? "Hide PIN" : "Show PIN"}
      onPress={onToggle}
      style={({ pressed }) => [
        styles.toggle,
        pressed && { backgroundColor: colors.blueTint },
      ]}
    >
      <Icon name={shown ? "eyeOff" : "eye"} size={20} color={colors.blue} />
      <Text weight="semibold" style={{ fontSize: 15, color: colors.blue }}>
        {shown ? "Hide" : "Show"}
      </Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  toggle: {
    minHeight: 44,
    paddingHorizontal: 10,
    borderRadius: 10,
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
  },
});
