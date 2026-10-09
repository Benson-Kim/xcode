import { Pressable, StyleSheet, View } from "react-native";

import { percentText } from "@xcode/shared/format";
import { STATUS_META, isRecorded } from "@xcode/shared/revenue";

import { useFormats } from "../../lib/formats";
import { useConnected } from "../../lib/network";
import { shiftDate } from "../../revenue/dates";
import type { RevenueQueue } from "../../revenue/queue";
import type {
  QueuedCapture,
  RevenueVehicle,
  RevenueWeek,
} from "../../revenue/types";
import { Banner, Button, Icon, Text, useTheme } from "../../ui";
import { IconButton, ScreenTitle, Segmented } from "../parts";
import {
  MODES,
  OFFLINE_EMPTY,
  OFFLINE_SAVED,
  onCurrentWeek,
  UNREACHABLE_EMPTY,
  UNREACHABLE_SAVED,
  type DayRowData,
  type ViewMode,
} from "./model";
import { QueuePanel } from "./QueuePanel";
import { styles as shared } from "./styles";

function LoadNotice({
  saved,
  error,
  loading,
  onRetry,
}: {
  saved: boolean;
  error: string;
  loading: boolean;
  onRetry: () => void;
}) {
  const connected = useConnected();
  return (
    <>
      {saved ? (
        <Banner tone="offline">
          {connected ? UNREACHABLE_SAVED : OFFLINE_SAVED}
        </Banner>
      ) : error === OFFLINE_EMPTY ? (
        <Banner tone="offline">
          {connected ? UNREACHABLE_EMPTY : OFFLINE_EMPTY}
        </Banner>
      ) : error ? (
        <Banner tone="error">{error}</Banner>
      ) : null}
      {error && !loading ? (
        <Button tone="outline" onPress={onRetry} style={shared.smallButton}>
          Try again
        </Button>
      ) : null}
    </>
  );
}

function DetailNav({
  vehicle,
  week,
  onBack,
}: {
  vehicle: RevenueVehicle;
  week: RevenueWeek;
  onBack: () => void;
}) {
  const { colors } = useTheme();
  const formats = useFormats();
  return (
    <View style={styles.dateNav}>
      <IconButton icon="back" label="Back to the week" onPress={onBack} />
      <View style={styles.navText}>
        <Text
          weight="bold"
          accessibilityRole="header"
          style={{ fontSize: 17, textAlign: "center" }}
        >
          {vehicle.registration}
        </Text>
        <Text style={{ fontSize: 14, color: colors.grey, textAlign: "center" }}>
          {`${vehicle.companyName}, ${formats.formatDateRange(week.weekStart, week.weekThrough)}`}
        </Text>
      </View>
      {/* Balances the back button, so the title sits in the middle as the day and week titles do. */}
      <View style={styles.navSpacer} />
    </View>
  );
}

// How many of the day's vehicles are captured, counting those still waiting on this phone.
function DayProgress({ rows }: { rows: DayRowData[] }) {
  const { colors } = useTheme();
  const inFleet = rows.filter((row) => STATUS_META[row.cell.status].inFleet);
  if (!inFleet.length) return null;
  const done = inFleet.filter(
    (row) => isRecorded(row.cell) || row.queued,
  ).length;
  // Not sent yet: waiting on this phone to go out (a conflict or refusal is shown as such).
  const unsent = inFleet.filter(
    (row) => row.queued?.state === "pending",
  ).length;
  return (
    <Text style={{ fontSize: 14, color: colors.grey }}>
      <Text
        weight="bold"
        style={{ fontSize: 14, color: colors.navy }}
      >{`${done} of ${inFleet.length}`}</Text>
      {` captured${unsent ? `, ${unsent} not sent yet` : ""}`}
    </Text>
  );
}

// A gap is mentioned, never required.
export const gapText = (date: string) =>
  `No record yet from ${date}. You can fill it when you have it.`;

function MissingBanner({
  earliest,
  onGo,
}: {
  earliest: string;
  onGo: (date: string) => void;
}) {
  const { colors } = useTheme();
  const formats = useFormats();
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`${gapText(formats.formatWeekdayDate(earliest))} Go there`}
      onPress={() => onGo(earliest)}
      style={[
        styles.missBanner,
        { borderColor: colors.amberLine, backgroundColor: colors.amberBg },
      ]}
    >
      <Icon name="alert" size={18} color={colors.amberText} />
      <Text
        style={{ flex: 1, fontSize: 14, color: colors.amberText }}
      >{`${gapText(formats.formatWeekdayDate(earliest))} Tap to go there.`}</Text>
    </Pressable>
  );
}

function DayNav({
  day,
  week,
  inWeek,
  rows,
  earliest,
  onGo,
}: {
  day: string;
  week: RevenueWeek;
  inWeek: boolean;
  rows: DayRowData[];
  earliest: string | null;
  onGo: (date: string) => void;
}) {
  const formats = useFormats();
  return (
    <>
      <View style={styles.dateNav}>
        <IconButton
          icon="back"
          label="Previous day"
          onPress={() => onGo(shiftDate(day, -1))}
        />
        <Text weight="bold" style={[styles.navText, { fontSize: 17 }]}>
          {formats.formatWeekdayDate(day)}
        </Text>
        <IconButton
          icon="forward"
          label="Next day"
          disabled={day >= week.businessDate}
          onPress={() => onGo(shiftDate(day, 1))}
        />
      </View>
      {inWeek && <DayProgress rows={rows} />}
      {earliest && <MissingBanner earliest={earliest} onGo={onGo} />}
    </>
  );
}

function WeekNav({
  week,
  onWeek,
}: {
  week: RevenueWeek;
  onWeek: (weekStart: string | undefined) => void;
}) {
  const { colors } = useTheme();
  const formats = useFormats();
  const { kes } = formats;
  return (
    <>
      <View style={styles.dateNav}>
        <IconButton
          icon="back"
          label="Previous week"
          onPress={() => onWeek(shiftDate(week.weekStart, -7))}
        />
        <Text weight="bold" style={[styles.navText, { fontSize: 17 }]}>
          {formats.formatDateRange(week.weekStart, week.weekThrough)}
        </Text>
        <IconButton
          icon="forward"
          label="Next week"
          disabled={onCurrentWeek(week)}
          onPress={() => {
            const next = shiftDate(week.weekStart, 7);
            onWeek(next >= week.currentWeekStart ? undefined : next);
          }}
        />
      </View>
      {week.vehicles.length > 0 && (
        <Text style={{ fontSize: 14, color: colors.grey }}>
          <Text weight="bold" style={{ fontSize: 14, color: colors.navy }}>
            {kes(week.totalAmount)}
          </Text>
          {week.totalExpected > 0
            ? ` of ${kes(week.totalExpected)} expected to date${week.percent === null ? "" : `, ${percentText(week.percent)}`}`
            : " so far"}
        </Text>
      )}
    </>
  );
}

export type HeaderProps = {
  mode: ViewMode;
  onMode: (mode: ViewMode) => void;
  week: RevenueWeek | undefined;
  detailVehicle: RevenueVehicle | undefined;
  onBack: () => void;
  notice: { saved: boolean; error: string; loading: boolean };
  onRetry: () => void;
  queue: RevenueQueue;
  canReplace: (entry: QueuedCapture) => boolean;
  day: string;
  inWeek: boolean;
  rows: DayRowData[];
  firstNeeded: string | null;
  onGoDay: (date: string) => void;
  onWeek: (weekStart: string | undefined) => void;
};

function Nav(props: HeaderProps) {
  const { week, detailVehicle, mode, day } = props;
  if (week && detailVehicle)
    return (
      <DetailNav vehicle={detailVehicle} week={week} onBack={props.onBack} />
    );
  if (week && mode === "day" && day)
    return (
      <DayNav
        day={day}
        week={week}
        inWeek={props.inWeek}
        rows={props.rows}
        earliest={
          props.firstNeeded && props.firstNeeded < day
            ? props.firstNeeded
            : null
        }
        onGo={props.onGoDay}
      />
    );
  if (week && mode === "week")
    return <WeekNav week={week} onWeek={props.onWeek} />;
  return null;
}

export function RevenueHeader(props: HeaderProps) {
  return (
    <View style={shared.header}>
      <ScreenTitle>Revenue</ScreenTitle>
      {!props.detailVehicle && (
        <Segmented
          label="Revenue view"
          options={MODES}
          value={props.mode}
          onChange={(next) => {
            props.onMode(next);
            if (next === "day" && props.day && !props.inWeek)
              props.onGoDay(props.day);
          }}
        />
      )}
      <LoadNotice {...props.notice} onRetry={props.onRetry} />
      <QueuePanel queue={props.queue} canReplace={props.canReplace} />
      <Nav {...props} />
    </View>
  );
}

const styles = StyleSheet.create({
  dateNav: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 8,
  },
  navText: { flex: 1, textAlign: "center", alignItems: "center" },
  navSpacer: { width: 44 },
  missBanner: {
    flexDirection: "row",
    gap: 8,
    alignItems: "flex-start",
    minHeight: 44,
    paddingVertical: 12,
    paddingHorizontal: 14,
    borderWidth: 1,
    borderRadius: 12,
  },
});
