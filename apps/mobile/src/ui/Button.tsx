import {
  Pressable,
  StyleSheet,
  type StyleProp,
  type ViewStyle,
} from "react-native";
import { Text } from "./Text";
import { useTheme } from "./theme";

type ButtonProps = {
  children: string;
  onPress: () => void;
  tone?: "primary" | "outline";
  busy?: boolean;
  busyText?: string;
  disabled?: boolean;
  style?: StyleProp<ViewStyle>;
};

export function Button({
  children,
  onPress,
  tone = "primary",
  busy,
  busyText,
  disabled,
  style,
}: ButtonProps) {
  const { colors } = useTheme();
  const primary = tone === "primary";
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{
        disabled: Boolean(disabled || busy),
        busy: Boolean(busy),
      }}
      disabled={disabled || busy}
      onPress={onPress}
      style={({ pressed }) => [
        styles.button,
        primary
          ? {
              backgroundColor: busy
                ? colors.blueBusy
                : pressed
                  ? colors.blueDark
                  : colors.blue,
            }
          : {
              borderWidth: 2,
              borderColor: colors.blue,
              backgroundColor: pressed ? colors.blueWash : "transparent",
            },
        disabled && !busy && styles.disabled,
        style,
      ]}
    >
      <Text
        weight="semibold"
        style={[styles.label, { color: primary ? colors.white : colors.blue }]}
      >
        {busy && busyText ? busyText : children}
      </Text>
    </Pressable>
  );
}

export function LinkButton({
  children,
  onPress,
  disabled,
  align,
}: {
  children: string;
  onPress: () => void;
  disabled?: boolean;
  align?: "start" | "end";
}) {
  const { colors } = useTheme();
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ disabled: Boolean(disabled) }}
      disabled={disabled}
      onPress={onPress}
      style={[
        styles.link,
        align === "start" && { paddingLeft: 0 },
        align === "end" && { paddingRight: 0 },
      ]}
    >
      {({ pressed }) => (
        <Text
          weight={disabled ? "medium" : "semibold"}
          style={{
            fontSize: 15,
            color: disabled
              ? colors.grey
              : pressed
                ? colors.blueDark
                : colors.blue,
            textDecorationLine: pressed ? "underline" : "none",
          }}
        >
          {children}
        </Text>
      )}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  button: {
    height: 56,
    width: "100%",
    borderRadius: 999,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: 16,
  },
  label: { fontSize: 17 },
  disabled: { opacity: 0.55 },
  link: { minHeight: 44, paddingHorizontal: 8, justifyContent: "center" },
});
