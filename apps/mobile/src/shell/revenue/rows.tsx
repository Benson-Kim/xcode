import { memo, type ReactElement, type ReactNode } from "react";
import { FlatList, Pressable, StyleSheet, View } from "react-native";

import { percentText, type Formatter } from "@xcode/shared/format";
import { STATUS_META, awaitsCapture, isRecorded } from "@xcode/shared/revenue";

import { useFormats } from "../../lib/formats";
import type {
  QueuedCapture,
  RevenueCell,
  RevenueVehicle,
  RevenueWeek,
} from "../../revenue/types";
import { Text, useTheme } from "../../ui";
import { Card, Chip, LineSkeleton } from "../parts";
import {
  STATE_TAG,
  TONE_COLOR,
  onCurrentWeek,
  valueText,
  type Colors,
  type DayRowData,
  type ViewMode,
} from "./model";
import { styles as shared } from "./styles";

// Rows sit in one white list, as in the design: rounded at the ends, a divider between them.
const rowShell = (first: boolean, last: boolean, colors: Colors) => [
  styles.row,
  { borderColor: colors.cardLine, backgroundColor: colors.surface },
  first && styles.firstRow,
  last && styles.lastRow,
  !first && { borderTopWidth: 1, borderTopColor: colors.divider },
];

// What a day row says about its day: the accessibility status and the right-hand content.
function rowValue(
  formats: Formatter,
  colors: Colors,
  cell: RevenueCell,
  queued: QueuedCapture | undefined,
  tappable: boolean,
): { status: string; right: ReactNode } {
  if (queued)
    return {
      status: `${valueText(formats, queued)}, ${STATE_TAG[queued.state].toLowerCase()}`,
      right: (
        <>
          <Text weight="bold">{valueText(formats, queued)}</Text>
          <Text
            style={{
              fontSize: 13,
              color: queued.state === "pending" ? colors.amberText : colors.red,
            }}
          >
            {STATE_TAG[queued.state]}
          </Text>
        </>
      ),
    };
  if (isRecorded(cell)) {
    const status =
      cell.amount !== null
        ? formats.kes(cell.amount)
        : (cell.reason ?? STATUS_META.reason.label);
    return {
      status,
      right:
        cell.amount !== null ? (
          <Text weight="bold">{status}</Text>
        ) : (
          <Chip>{status}</Chip>
        ),
    };
  }
  if (awaitsCapture(cell)) {
    const status = tappable ? "Enter revenue" : STATUS_META[cell.status].label;
    return {
      status,
      right: tappable ? (
        <View style={[styles.enter, { borderColor: colors.red }]}>
          <Text weight="bold" style={{ fontSize: 14, color: colors.red }}>
            Enter
          </Text>
        </View>
      ) : (
        <Text
          weight="semibold"
          style={{
            fontSize: 14,
            color: colors[TONE_COLOR[STATUS_META[cell.status].tone]],
          }}
        >
          {status}
        </Text>
      ),
    };
  }
  const meta = STATUS_META[cell.status];
  return {
    status: meta.label,
    right: (
      <Text style={{ fontSize: 13, color: colors[TONE_COLOR[meta.tone]] }}>
        {meta.label}
      </Text>
    ),
  };
}

// Memoized: typing in the capture sheet leaves the rows alone, and a row redraws only when its own day changes.
export const DayRow = memo(function DayRow({
  vehicle,
  cell,
  queued,
  tappable,
  first,
  last,
  onOpen,
}: DayRowData & {
  first: boolean;
  last: boolean;
  onOpen: (vehicleId: string) => void;
}) {
  const { colors } = useTheme();
  const formats = useFormats();
  const { status, right } = rowValue(formats, colors, cell, queued, tappable);
  const content = (
    <>
      <View style={styles.rowLeft}>
        <Text weight="bold">{vehicle.registration}</Text>
        <Text style={{ fontSize: 13, color: colors.grey }}>
          {cell.editedAfterCapture && !queued
            ? `${vehicle.companyName}, edited after capture`
            : vehicle.companyName}
        </Text>
      </View>
      <View style={styles.rowRight}>{right}</View>
    </>
  );
  const label = `${vehicle.registration}, ${status}`;
  return tappable ? (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      onPress={() => onOpen(vehicle.id)}
      style={({ pressed }) => [
        rowShell(first, last, colors),
        pressed && { backgroundColor: colors.pressed },
      ]}
    >
      {content}
    </Pressable>
  ) : (
    <View
      accessible
      accessibilityLabel={label}
      style={rowShell(first, last, colors)}
    >
      {content}
    </View>
  );
});

export const WeekRow = memo(function WeekRow({
  vehicle,
  first,
  last,
  onOpen,
}: {
  vehicle: RevenueVehicle;
  first: boolean;
  last: boolean;
  onOpen: (vehicleId: string) => void;
}) {
  const { colors } = useTheme();
  const { kes } = useFormats();
  const share =
    vehicle.percent === null
      ? ""
      : `${percentText(vehicle.percent)} of ${kes(vehicle.totalExpected)}`;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`${vehicle.registration}, ${kes(vehicle.totalAmount)}${share ? `, ${share}` : ""}. Open the week`}
      onPress={() => onOpen(vehicle.id)}
      style={({ pressed }) => [
        rowShell(first, last, colors),
        pressed && { backgroundColor: colors.pressed },
      ]}
    >
      <View style={styles.rowLeft}>
        <Text weight="bold">{vehicle.registration}</Text>
        <Text style={{ fontSize: 13, color: colors.grey }}>
          {vehicle.companyName}
        </Text>
      </View>
      <View style={styles.rowRight}>
        <Text weight="bold">{kes(vehicle.totalAmount)}</Text>
        {share ? (
          <Text
            style={{
              fontSize: 13,
              color: (vehicle.percent ?? 100) < 90 ? colors.red : colors.grey,
            }}
          >
            {share}
          </Text>
        ) : null}
      </View>
    </Pressable>
  );
});

export function DayList({
  rows,
  header,
  empty,
  onOpen,
}: {
  rows: DayRowData[];
  header: ReactElement;
  empty: ReactElement | null;
  onOpen: (vehicleId: string) => void;
}) {
  return (
    <FlatList
      style={shared.list}
      contentContainerStyle={shared.content}
      keyboardShouldPersistTaps="handled"
      data={rows}
      keyExtractor={(row) => row.vehicle.id}
      ListHeaderComponent={header}
      ListEmptyComponent={empty}
      renderItem={({ item, index }) => (
        <DayRow
          vehicle={item.vehicle}
          cell={item.cell}
          queued={item.queued}
          tappable={item.tappable}
          first={index === 0}
          last={index === rows.length - 1}
          onOpen={onOpen}
        />
      )}
    />
  );
}

export function WeekList({
  week,
  header,
  empty,
  onOpen,
}: {
  week: RevenueWeek | undefined;
  header: ReactElement;
  empty: ReactElement | null;
  onOpen: (vehicleId: string) => void;
}) {
  return (
    <FlatList
      style={shared.list}
      contentContainerStyle={shared.content}
      data={week?.vehicles ?? []}
      keyExtractor={(vehicle) => vehicle.id}
      ListHeaderComponent={header}
      ListEmptyComponent={empty}
      renderItem={({ item, index }) => (
        <WeekRow
          vehicle={item}
          first={index === 0}
          last={index === (week?.vehicles.length ?? 0) - 1}
          onOpen={onOpen}
        />
      )}
    />
  );
}

// A day or earlier week before the vehicles joined (or after they left) is empty too, which is not having none.
export function emptyList({
  loading,
  week,
  mode,
  inWeek,
}: {
  loading: boolean;
  week: RevenueWeek | undefined;
  mode: ViewMode;
  inWeek: boolean;
}) {
  if (loading) return <LineSkeleton lines={4} />;
  if (!week || (mode === "day" && !inWeek)) return null;
  if (week.vehicles.length === 0 && onCurrentWeek(week))
    return (
      <Card
        title="No vehicles in your view"
        sub="Vehicles you may capture revenue for will appear here."
      />
    );
  return (
    <Card
      title={
        mode === "day" ? "No vehicles on this day" : "No vehicles this week"
      }
      sub="None of the vehicles in your view were in service then."
    />
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    gap: 12,
    minHeight: 60,
    paddingVertical: 8,
    paddingHorizontal: 16,
    borderLeftWidth: 1,
    borderRightWidth: 1,
  },
  firstRow: {
    borderTopWidth: 1,
    borderTopLeftRadius: 14,
    borderTopRightRadius: 14,
  },
  lastRow: {
    borderBottomWidth: 1,
    borderBottomLeftRadius: 14,
    borderBottomRightRadius: 14,
  },
  rowLeft: { flexShrink: 1 },
  rowRight: { alignItems: "flex-end", flexShrink: 0 },
  enter: {
    paddingVertical: 6,
    paddingHorizontal: 14,
    borderWidth: 1,
    borderStyle: "dashed",
    borderRadius: 999,
  },
});
