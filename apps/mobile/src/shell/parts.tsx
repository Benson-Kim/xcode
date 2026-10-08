import type { ReactNode } from "react";
import { Pressable, StyleSheet, View } from "react-native";

import { Icon, Text, useTheme, type IconName } from "../ui";

export function ScreenTitle({ children }: { children: string }) {
  return (
    <Text weight="bold" accessibilityRole="header" style={styles.h1}>
      {children}
    </Text>
  );
}

export function SectionTitle({ children }: { children: string }) {
  return (
    <Text weight="bold" accessibilityRole="header" style={styles.section}>
      {children}
    </Text>
  );
}

// Avatar, name and role, with an optional action (the lock button on Home).
export function WhoRow({
  initials,
  name,
  role,
  action,
}: {
  initials: string;
  name: string;
  role: string;
  action?: ReactNode;
}) {
  const { colors, fontScale } = useTheme();
  return (
    <View style={styles.who}>
      <View
        style={[styles.avatar, { backgroundColor: colors.brand }]}
        aria-hidden
      >
        {/* Decorative initials keep their size so a larger text preference cannot push them out of the circle. */}
        <Text
          weight="bold"
          style={{
            color: colors.onBrand,
            fontSize: 16 / fontScale,
            lineHeight: 20 / fontScale,
          }}
        >
          {initials}
        </Text>
      </View>
      <View style={styles.whoText}>
        <Text weight="bold" numberOfLines={1} style={styles.name}>
          {name}
        </Text>
        <Text numberOfLines={1} style={{ fontSize: 14, color: colors.grey }}>
          {role}
        </Text>
      </View>
      {action}
    </View>
  );
}

export function IconButton({
  icon,
  label,
  onPress,
  disabled,
}: {
  icon: IconName;
  label: string;
  onPress: () => void;
  disabled?: boolean;
}) {
  const { colors } = useTheme();
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityState={{ disabled: Boolean(disabled) }}
      disabled={disabled}
      onPress={onPress}
      style={({ pressed }) => [
        styles.iconButton,
        {
          borderColor: colors.keyLine,
          backgroundColor: pressed ? colors.blueTint : colors.surface,
        },
        disabled && { opacity: 0.35 },
      ]}
    >
      <Icon name={icon} size={22} color={colors.navy} />
    </Pressable>
  );
}

export function Segmented<T extends string>({
  label,
  options,
  value,
  onChange,
}: {
  label: string;
  options: { value: T; label: string }[];
  value: T;
  onChange: (value: T) => void;
}) {
  const { colors } = useTheme();
  return (
    <View
      accessibilityLabel={label}
      style={[styles.segmented, { backgroundColor: colors.divider }]}
    >
      {options.map((option) => {
        const selected = option.value === value;
        return (
          <Pressable
            key={option.value}
            accessibilityRole="button"
            accessibilityState={{ selected }}
            // The track's padding counts as part of each option, so every option is at least 48 points tall to touch.
            hitSlop={{ top: 4, bottom: 4 }}
            onPress={() => onChange(option.value)}
            style={[
              styles.segment,
              selected && [
                styles.selected,
                { backgroundColor: colors.surface },
              ],
            ]}
          >
            <Text
              weight="semibold"
              style={{
                fontSize: 14,
                textAlign: "center",
                color: selected ? colors.navy : colors.grey,
              }}
            >
              {option.label}
            </Text>
          </Pressable>
        );
      })}
    </View>
  );
}

export function Card({
  title,
  sub,
  children,
}: {
  title: string;
  sub?: string;
  children?: ReactNode;
}) {
  const { colors } = useTheme();
  return (
    <View
      style={[
        styles.card,
        { borderColor: colors.cardLine, backgroundColor: colors.surface },
      ]}
    >
      <View style={styles.cardHeader}>
        <Text weight="bold" accessibilityRole="header" style={styles.cardTitle}>
          {title}
        </Text>
        {sub ? (
          <Text style={{ fontSize: 13, lineHeight: 18, color: colors.grey }}>
            {sub}
          </Text>
        ) : null}
      </View>
      {children}
    </View>
  );
}

// bad: a figure that needs attention, in red as in the design.
export function CardValue({
  children,
  bad,
}: {
  children: string;
  bad?: boolean;
}) {
  const { colors } = useTheme();
  return (
    <Text weight="bold" style={[styles.value, bad && { color: colors.red }]}>
      {children}
    </Text>
  );
}

// A share of a target. The note beside it states the percentage, so the bar itself is hidden from screen readers.
export function ProgressBar({ percent }: { percent: number }) {
  const { colors } = useTheme();
  const width = `${Math.max(0, Math.min(100, Math.round(percent)))}%` as const;
  return (
    <View aria-hidden style={[styles.bar, { backgroundColor: colors.divider }]}>
      <View style={[styles.barFill, { width, backgroundColor: colors.blue }]} />
    </View>
  );
}

// A small grey label: a reason for no revenue, or a card that is not available yet.
export function Chip({ children }: { children: string }) {
  const { colors } = useTheme();
  return (
    <View style={[styles.chip, { backgroundColor: colors.divider }]}>
      <Text weight="bold" style={{ fontSize: 13, lineHeight: 18 }}>
        {children}
      </Text>
    </View>
  );
}

export function CardNote({ children }: { children: string }) {
  const { colors } = useTheme();
  return (
    <Text style={{ fontSize: 14, lineHeight: 20, color: colors.grey }}>
      {children}
    </Text>
  );
}

export function CardAction({
  children,
  primary,
  onPress,
}: {
  children: string;
  primary?: boolean;
  onPress: () => void;
}) {
  const { colors } = useTheme();
  return (
    <Pressable
      accessibilityRole="button"
      onPress={onPress}
      style={({ pressed }) => [
        styles.cardAction,
        {
          borderColor: colors.blue,
          backgroundColor: primary
            ? pressed
              ? colors.blueDark
              : colors.blue
            : pressed
              ? colors.blueTint
              : "transparent",
        },
      ]}
    >
      <Text
        weight="semibold"
        style={{ color: primary ? colors.onFill : colors.blue }}
      >
        {children}
      </Text>
    </Pressable>
  );
}

// Grey placeholder lines while a list loads.
export function LineSkeleton({ lines = 3 }: { lines?: number }) {
  const { colors } = useTheme();
  return (
    <View
      accessibilityRole="progressbar"
      accessibilityLabel="Loading"
      style={{ gap: 10 }}
    >
      {Array.from({ length: lines }, (_, index) => (
        <View
          key={index}
          style={{
            height: 14,
            width: `${85 - index * 15}%`,
            borderRadius: 7,
            backgroundColor: colors.divider,
          }}
        />
      ))}
    </View>
  );
}

export function Bullets({ items }: { items: string[] }) {
  return (
    <View style={{ gap: 6, paddingLeft: 4 }}>
      {items.map((item) => (
        <View key={item} style={{ flexDirection: "row", gap: 8 }}>
          <Text style={{ fontSize: 15 }}>{"•"}</Text>
          <Text style={{ fontSize: 15, flexShrink: 1 }}>{item}</Text>
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  h1: { fontSize: 26, lineHeight: 31 },
  section: { marginTop: 8, fontSize: 17, lineHeight: 23 },
  who: { flexDirection: "row", alignItems: "center", gap: 12 },
  avatar: {
    width: 44,
    height: 44,
    borderRadius: 22,
    alignItems: "center",
    justifyContent: "center",
  },
  whoText: { flex: 1, minWidth: 0 },
  name: { fontSize: 20, lineHeight: 24 },
  iconButton: {
    width: 44,
    height: 44,
    borderWidth: 1,
    borderRadius: 12,
    alignItems: "center",
    justifyContent: "center",
  },
  segmented: { flexDirection: "row", borderRadius: 999, padding: 4, gap: 2 },
  segment: {
    flex: 1,
    minHeight: 40,
    borderRadius: 999,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: 8,
  },
  selected: {
    shadowColor: "#14213D",
    shadowOpacity: 0.15,
    shadowRadius: 3,
    shadowOffset: { width: 0, height: 1 },
    elevation: 1,
  },
  card: { borderWidth: 1, borderRadius: 14, padding: 20, gap: 10 },
  cardHeader: { gap: 2 },
  cardTitle: { fontSize: 16, lineHeight: 21 },
  value: { marginTop: 4, fontSize: 30, lineHeight: 35 },
  bar: { height: 8, borderRadius: 999, overflow: "hidden" },
  barFill: { height: 8, borderRadius: 999 },
  chip: {
    alignSelf: "flex-start",
    paddingVertical: 2,
    paddingHorizontal: 10,
    borderRadius: 999,
  },
  cardAction: {
    marginTop: 6,
    minHeight: 52,
    borderWidth: 2,
    borderRadius: 999,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: 20,
  },
});
