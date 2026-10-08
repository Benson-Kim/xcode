import { memo, useMemo } from "react";
import { Pressable, StyleSheet, View } from "react-native";

import type { Formatter } from "@xcode/shared/format";
import {
  STATUS_META,
  awaitsCapture,
  isRecorded,
  type StatusTone,
} from "@xcode/shared/revenue";

import { useFormats } from "../../lib/formats";
import type { QueuedCapture, RevenueCell } from "../../revenue/types";
import { Text, useTheme } from "../../ui";
import { STATE_TAG, TONE_COLOR, valueText } from "./model";
import { styles as shared } from "./styles";

// The day and expected columns of the vehicle week, widened with the person's text size.
export function useColumns() {
  const { fontScale } = useTheme();
  // Capped, so the actual column keeps room for its amounts; beyond the caps the text wraps inside its column.
  return useMemo(
    () => ({
      day: { width: 60 * Math.min(fontScale, 1.35) },
      number: { width: 92 * Math.min(fontScale, 1.15) },
    }),
    [fontScale],
  );
}

// What a day of the vehicle week shows against its target.
export function dayBarFigures(
  formats: Formatter,
  cell: RevenueCell,
  queued: QueuedCapture | undefined,
  today: string,
) {
  // Not a shortfall: future days, days outside the fleet, and today before capture.
  const compared =
    isRecorded(cell) ||
    Boolean(queued) ||
    (awaitsCapture(cell) && cell.date < today);
  const actual = queued ? (queued.amount ?? 0) : (cell.amount ?? 0);
  const share =
    cell.expected > 0
      ? Math.min(1, actual / cell.expected)
      : actual > 0
        ? 1
        : 0;
  const below = actual < cell.expected;
  const shown = queued
    ? `${valueText(formats, queued)}, ${STATE_TAG[queued.state].toLowerCase()}`
    : isRecorded(cell)
      ? cell.amount !== null
        ? formats.kes(cell.amount)
        : (cell.reason ?? STATUS_META.reason.label)
      : awaitsCapture(cell)
        ? cell.date < today
          ? "No record"
          : "Not yet"
        : STATUS_META[cell.status].label;
  const tone: StatusTone = queued
    ? "normal"
    : compared
      ? STATUS_META[cell.status].tone
      : "muted";
  const difference = compared
    ? formats.formatDifference(actual, cell.expected)
    : "";
  return { compared, actual, share, below, shown, tone, difference };
}

function ShareBar({ share, below }: { share: number; below: boolean }) {
  const { colors } = useTheme();
  return (
    <View
      style={[styles.track, { backgroundColor: colors.divider }]}
      aria-hidden
    >
      <View
        style={[
          styles.fill,
          {
            width: `${Math.round(share * 100)}%`,
            backgroundColor: below ? colors.amberLine : colors.green,
          },
        ]}
      />
    </View>
  );
}

export const DayBar = memo(function DayBar({
  cell,
  name,
  today,
  queued,
  tappable,
  onOpen,
}: {
  cell: RevenueCell;
  name: string;
  today: string;
  queued?: QueuedCapture;
  tappable: boolean;
  onOpen: (date: string) => void;
}) {
  const { colors } = useTheme();
  const formats = useFormats();
  const columns = useColumns();
  const { compared, share, below, shown, tone, difference } = dayBarFigures(
    formats,
    cell,
    queued,
    today,
  );
  const content = (
    <>
      <Text style={[shared.detailDay, columns.day]}>{name}</Text>
      <Text
        style={[
          shared.detailNumber,
          columns.number,
          { color: compared ? colors.navy : colors.grey },
        ]}
      >
        {STATUS_META[cell.status].inFleet ? formats.kes(cell.expected) : ""}
      </Text>
      <View style={shared.detailActual}>
        <Text
          weight={
            (isRecorded(cell) && cell.amount !== null) || queued
              ? "semibold"
              : "regular"
          }
          style={{
            fontSize: 14,
            textAlign: "right",
            color: colors[TONE_COLOR[tone]],
          }}
        >
          {shown}
        </Text>
        {compared && <ShareBar share={share} below={below} />}
        {difference ? (
          <Text
            style={{ fontSize: 12, color: below ? colors.red : colors.green }}
          >
            {difference}
          </Text>
        ) : null}
      </View>
    </>
  );
  const label = `${name}: expected ${formats.kes(cell.expected)}, ${shown}${difference ? `, ${difference}` : ""}`;
  return tappable ? (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      onPress={() => onOpen(cell.date)}
      style={({ pressed }) => [
        shared.detailRow,
        { borderBottomColor: colors.divider },
        pressed && { backgroundColor: colors.pressed },
      ]}
    >
      {content}
    </Pressable>
  ) : (
    <View
      accessible
      accessibilityLabel={label}
      style={[shared.detailRow, { borderBottomColor: colors.divider }]}
    >
      {content}
    </View>
  );
});

const styles = StyleSheet.create({
  track: { width: "100%", height: 6, borderRadius: 3, overflow: "hidden" },
  fill: { height: 6, borderRadius: 3 },
});
