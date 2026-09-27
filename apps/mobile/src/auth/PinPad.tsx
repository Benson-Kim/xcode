import { useEffect, useRef, type ReactNode } from "react";
import {
  Animated,
  Platform,
  Pressable,
  StyleSheet,
  View,
  useWindowDimensions,
} from "react-native";
import { ErrorText, Icon, Text, useTheme } from "../ui";

const KEYS = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "", "0", "back"];

export type PadHeader =
  | { kind: "person"; initials: string; title: string; sub: string }
  | { kind: "heading"; title: string; sub: string };

type Props = {
  header: PadHeader;
  label: string;
  length: number;
  value: string;
  error: string;
  busy: boolean;
  // Bumped on every wrong entry so the dots shake.
  shake: number;
  onDigit: (digit: string) => void;
  onDelete: () => void;
  links?: ReactNode;
};

// The on-screen keypad used for every PIN step. A hardware keyboard works too (the browser preview).
export function PinPad({
  header,
  label,
  length,
  value,
  error,
  busy,
  shake,
  onDigit,
  onDelete,
  links,
}: Props) {
  const { colors, reducedMotion } = useTheme();
  const { height } = useWindowDimensions();
  const short = height < 700;
  const offset = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    if (!shake || reducedMotion) return;
    Animated.sequence(
      [-6, 6, -6, 0].map((toValue) =>
        Animated.timing(offset, {
          toValue,
          duration: 75,
          useNativeDriver: Platform.OS !== "web",
        }),
      ),
    ).start();
  }, [shake, reducedMotion, offset]);

  const latest = useRef({ onDigit, onDelete, busy });
  latest.current = { onDigit, onDelete, busy };
  useEffect(() => {
    if (Platform.OS !== "web") return;
    const listener = (event: KeyboardEvent) => {
      if (
        latest.current.busy ||
        (event.target as HTMLElement | null)?.tagName === "INPUT"
      )
        return;
      if (/^\d$/.test(event.key)) latest.current.onDigit(event.key);
      else if (event.key === "Backspace") latest.current.onDelete();
      else return;
      event.preventDefault();
    };
    document.addEventListener("keydown", listener);
    return () => document.removeEventListener("keydown", listener);
  }, []);

  return (
    <View style={styles.screen}>
      {header.kind === "person" ? (
        <View style={styles.who}>
          <View
            style={[
              styles.avatar,
              short && styles.avatarShort,
              { backgroundColor: colors.brand },
            ]}
            aria-hidden
          >
            {header.initials ? (
              <Text
                weight="bold"
                style={{ color: colors.white, fontSize: short ? 17 : 21 }}
              >
                {header.initials}
              </Text>
            ) : (
              <Icon name="lock" size={24} color={colors.white} />
            )}
          </View>
          <Text weight="bold" accessibilityRole="header" style={styles.title}>
            {header.title}
          </Text>
          <Text style={[styles.sub, { color: colors.grey }]}>{header.sub}</Text>
        </View>
      ) : (
        <View>
          <Text weight="bold" accessibilityRole="header" style={styles.title}>
            {header.title}
          </Text>
          <Text style={[styles.sub, { color: colors.grey, marginTop: 6 }]}>
            {header.sub}
          </Text>
        </View>
      )}

      <View style={styles.entry}>
        <Text weight="semibold" style={{ fontSize: 15 }}>
          {label}
        </Text>
        <Animated.View
          accessible
          accessibilityRole="image"
          accessibilityLabel={`${value.length} of ${length} numbers entered`}
          accessibilityLiveRegion="polite"
          style={[styles.dots, { transform: [{ translateX: offset }] }]}
        >
          {Array.from({ length }, (_, index) => (
            <View
              key={index}
              style={[
                styles.dot,
                { borderColor: colors.navy },
                index < value.length && { backgroundColor: colors.navy },
              ]}
            />
          ))}
        </Animated.View>
        <View style={styles.errorBox}>
          <ErrorText center>{error}</ErrorText>
        </View>
      </View>

      <View style={styles.keypad} accessibilityLabel={label}>
        {KEYS.map((key, index) =>
          key === "" ? (
            <View key={index} style={styles.cell} />
          ) : (
            <View key={index} style={styles.cell}>
              <Pressable
                accessibilityRole="button"
                accessibilityLabel={key === "back" ? "Delete last number" : key}
                accessibilityState={{ disabled: busy }}
                disabled={busy}
                onPress={() => (key === "back" ? onDelete() : onDigit(key))}
                style={({ pressed }) => [
                  styles.key,
                  short && styles.keyShort,
                  key === "back"
                    ? styles.plain
                    : {
                        borderColor: pressed ? colors.blue : colors.keyLine,
                        backgroundColor: pressed
                          ? colors.blueWash
                          : colors.white,
                      },
                  busy && styles.disabled,
                ]}
              >
                {key === "back" ? (
                  <Icon name="backspace" size={28} color={colors.navy} />
                ) : (
                  <Text weight="semibold" style={styles.keyText}>
                    {key}
                  </Text>
                )}
              </Pressable>
            </View>
          ),
        )}
      </View>
      {links}
    </View>
  );
}

export function LinkRow({ children }: { children: ReactNode }) {
  return <View style={styles.row}>{children}</View>;
}

const styles = StyleSheet.create({
  screen: { gap: 16 },
  who: { alignItems: "center", gap: 6 },
  avatar: {
    width: 60,
    height: 60,
    borderRadius: 30,
    alignItems: "center",
    justifyContent: "center",
  },
  avatarShort: { width: 48, height: 48, borderRadius: 24 },
  title: { fontSize: 22, lineHeight: 28, textAlign: "center" },
  sub: { textAlign: "center" },
  entry: { alignItems: "center", gap: 12 },
  dots: { flexDirection: "row", gap: 18 },
  dot: { width: 16, height: 16, borderRadius: 8, borderWidth: 2 },
  errorBox: { minHeight: 44, alignSelf: "stretch" },
  keypad: { flexDirection: "row", flexWrap: "wrap", marginHorizontal: -6 },
  cell: { width: "33.333%", padding: 6 },
  key: {
    height: 64,
    borderWidth: 1,
    borderRadius: 16,
    alignItems: "center",
    justifyContent: "center",
  },
  keyShort: { height: 54 },
  plain: { borderWidth: 0, backgroundColor: "transparent" },
  keyText: { fontSize: 26, lineHeight: 32 },
  disabled: { opacity: 0.5 },
  row: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    flexWrap: "wrap",
    gap: 4,
  },
});
