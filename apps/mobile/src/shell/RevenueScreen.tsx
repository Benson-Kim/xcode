import { memo, useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { FlatList, KeyboardAvoidingView, Modal, Platform, Pressable, ScrollView, StyleSheet, TextInput, View, type TextInputProps } from "react-native";
import { useNetworkState } from "expo-network";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { OfflineError, SessionEndedError } from "../lib/api";
import { currencyCode, money } from "../lib/format";
import type { StoredPerson } from "../lib/storage";
import { dayLabel, longDayLabel, rangeLabel, shiftDate, shortDayLabel, weekHolding } from "../revenue/dates";
import { queueCounts, type NewCapture, type RevenueQueue } from "../revenue/queue";
import { NOTE_LIMIT, REASONS, type QueuedCapture, type RevenueCell, type RevenueReason, type RevenueVehicle, type RevenueWeek } from "../revenue/types";
import { loadWeek } from "../revenue/week";
import { Banner, Button, ErrorText, Icon, Text, fonts, useTheme } from "../ui";
import { Card, Chip, IconButton, LineSkeleton, ScreenTitle, Segmented } from "./parts";

type ViewMode = "day" | "week";
const MODES: { value: ViewMode; label: string }[] = [
  { value: "day", label: "Day" },
  { value: "week", label: "Week" },
];

const OFFLINE_EMPTY = "No internet. Revenue needs a connection to load. Captures already on this phone are kept and sent when you are back online.";
const OFFLINE_SAVED = "No internet. Showing what this phone loaded earlier. Captures are kept on this phone and sent when you are back online.";

type Waiting = ReadonlyMap<string, QueuedCapture>;
const keyOf = (vehicleId: string, date: string) => `${vehicleId}/${date}`;
const cellOf = (vehicle: RevenueVehicle, date: string) => vehicle.days.find((cell) => cell.date === date);
const recorded = (cell?: RevenueCell) => cell?.status === "amount" || cell?.status === "reason";
const valueText = (entry: { amount: number | null; reason: string | null }) => (entry.amount !== null ? money(entry.amount) : entry.reason ?? "");

// The first day this vehicle still needs, counting captures waiting on this phone as done. Days outside the loaded
// week are only known when a capture waits for them, so the search stops at the first day it cannot vouch for:
// at most (captures waiting for the vehicle + 8) steps.
function nextMissing(vehicle: RevenueVehicle, week: RevenueWeek, waiting: Waiting) {
  // earliestMissing leaves out today; with nothing missing before today, today is the only candidate.
  for (let date = vehicle.earliestMissing ?? week.businessDate; date <= week.businessDate; date = shiftDate(date, 1)) {
    if (waiting.has(keyOf(vehicle.id, date))) continue;
    const cell = date >= week.weekStart && date <= week.weekThrough ? cellOf(vehicle, date) : undefined;
    if (!cell || cell.status === "missing") return date;
  }
  return null;
}

// What a tap on a vehicle's day opens: that day, an earlier day that must be filled first, or nothing.
type Target = { vehicle: RevenueVehicle; date: string; cell?: RevenueCell; waiting?: QueuedCapture; info: string };

function targetFor(vehicle: RevenueVehicle, date: string, week: RevenueWeek, waiting: Waiting, canCapture: boolean): Target | null {
  const cell = cellOf(vehicle, date);
  const queued = waiting.get(keyOf(vehicle.id, date));
  // A conflict is settled with Keep saved value or Replace with mine.
  if (queued) return queued.state === "conflict" ? null : { vehicle, date, cell, waiting: queued, info: "" };
  if (!cell) return null;
  // Changing a record: the API says whether this person may (today with capture or correct, a past day with correct).
  if (recorded(cell)) return cell.canEdit ? { vehicle, date, cell, info: "" } : null;
  if (cell.status !== "missing" || !canCapture) return null;
  const first = nextMissing(vehicle, week, waiting);
  if (!first || first >= date) return { vehicle, date, cell, info: "" };
  return { vehicle, date: first, cell: cellOf(vehicle, first), info: `Fill ${longDayLabel(first)} first.` };
}

// After saving, the next vehicle (from this one on) still missing that day.
function nextTarget(week: RevenueWeek, fromVehicle: string, day: string, waiting: Waiting, canCapture: boolean) {
  const from = Math.max(0, week.vehicles.findIndex((vehicle) => vehicle.id === fromVehicle));
  for (const vehicle of [...week.vehicles.slice(from), ...week.vehicles.slice(0, from)]) {
    if (cellOf(vehicle, day)?.status !== "missing" || waiting.has(keyOf(vehicle.id, day))) continue;
    const target = targetFor(vehicle, day, week, waiting, canCapture);
    if (target) return target;
  }
  return null;
}

const STATE_TAG: Record<QueuedCapture["state"], string> = { pending: "Not sent yet", blocked: "Waiting for an earlier day", conflict: "Conflict", failed: "Not saved" };

export function RevenueScreen({
  person,
  queue,
  businessDate,
  onSessionEnded,
}: {
  person: StoredPerson;
  queue: RevenueQueue;
  // The business date the phone last saw, for when no week has loaded (offline).
  businessDate?: string;
  onSessionEnded: () => void;
}) {
  const { colors } = useTheme();
  const owner = person.userId ?? person.phoneNumber;
  const canView = person.permissions.includes("revenue.view");
  const canCapture = person.permissions.includes("revenue.capture");
  const canReason = person.permissions.includes("revenue.no_earnings");
  const canCorrect = person.permissions.includes("revenue.correct");

  const [mode, setMode] = useState<ViewMode>("day");
  // undefined: the current week, which the API works out from the organization's business date.
  const [weekStart, setWeekStart] = useState<string | undefined>();
  const [day, setDay] = useState("");
  const [data, setData] = useState<{ week: RevenueWeek; saved: boolean } | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [detail, setDetail] = useState<string | null>(null);
  const [target, setTarget] = useState<Target | null>(null);
  const [fromDay, setFromDay] = useState(true);
  // Bumped by Try again after a failed load.
  const [attempt, setAttempt] = useState(0);
  // Reloads once a round of sending settles, not on every answer in it.
  const [shown, setShown] = useState(queue.revision);
  useEffect(() => {
    if (!queue.syncing && queue.revision !== shown) setShown(queue.revision);
  }, [queue.syncing, queue.revision, shown]);

  useEffect(() => {
    if (!canView) return;
    let active = true;
    setLoading(true);
    loadWeek(owner, weekStart).then(
      (result) => {
        if (!active) return;
        setData(result);
        setError("");
        setLoading(false);
      },
      (reason: Error) => {
        if (!active) return;
        setLoading(false);
        if (reason instanceof SessionEndedError) return onSessionEnded();
        setError(reason instanceof OfflineError ? OFFLINE_EMPTY : reason.message);
      },
    );
    return () => {
      active = false;
    };
  }, [canView, owner, weekStart, shown, attempt, onSessionEnded]);

  // When the connection comes back, a week that could not load, or that shows an earlier copy, loads again.
  const network = useNetworkState();
  const online = network.isConnected !== false && network.isInternetReachable !== false;
  const stale = Boolean(error || data?.saved);
  useEffect(() => {
    if (online && stale) setAttempt((value) => value + 1);
    // Only the connection coming back retries; a failure while online waits for Try again.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [online]);

  const week = data?.week;
  // Replacing a saved record is changing it: today needs capture or correct, an earlier day needs correct (as the API rules).
  const today = week?.businessDate ?? businessDate;
  const canReplace = useCallback((entry: QueuedCapture) => canCorrect || (canCapture && entry.date === today), [canCorrect, canCapture, today]);
  const waiting = useMemo<Waiting>(() => new Map(queue.entries.map((entry) => [keyOf(entry.vehicleId, entry.date), entry])), [queue.entries]);

  // Opens on the earliest day still missing for people who capture, otherwise on the business date (never the phone's clock).
  useEffect(() => {
    if (!week || day || !queue.loaded) return;
    let first = week.businessDate;
    if (canCapture)
      for (const vehicle of week.vehicles) {
        const missing = nextMissing(vehicle, week, waiting);
        if (missing && missing < first) first = missing;
      }
    setDay(first);
    if (first < week.weekStart) setWeekStart(weekHolding(first, week.currentWeekStart));
  }, [week, day, queue.loaded, waiting, canCapture]);

  const goToDay = useCallback(
    (next: string) => {
      setDay(next);
      if (week && (next < week.weekStart || next > week.weekThrough)) {
        const holding = weekHolding(next, week.currentWeekStart);
        setWeekStart(holding === week.currentWeekStart ? undefined : holding);
      }
    },
    [week],
  );

  const inWeek = Boolean(week && day >= week.weekStart && day <= week.weekThrough);
  const rows = useMemo(
    () =>
      week && inWeek
        ? week.vehicles.flatMap((vehicle) => {
            const cell = cellOf(vehicle, day);
            if (!cell) return [];
            const queued = waiting.get(keyOf(vehicle.id, day));
            return [{ vehicle, cell, queued, tappable: Boolean(targetFor(vehicle, day, week, waiting, canCapture)) }];
          })
        : [],
    [week, inWeek, day, waiting, canCapture],
  );

  const openDay = useCallback(
    (vehicleId: string) => {
      const vehicle = week?.vehicles.find((item) => item.id === vehicleId);
      if (!week || !vehicle) return;
      setFromDay(true);
      setTarget(targetFor(vehicle, day, week, waiting, canCapture));
    },
    [week, day, waiting, canCapture],
  );

  const openDetailDay = useCallback(
    (vehicle: RevenueVehicle, date: string, detailWeek: RevenueWeek) => {
      setFromDay(false);
      setTarget(targetFor(vehicle, date, detailWeek, waiting, canCapture));
    },
    [waiting, canCapture],
  );

  const save = useCallback(
    async (open: Target, entry: Pick<NewCapture, "amount" | "reason" | "note">) => {
      const version = open.waiting ? open.waiting.version : recorded(open.cell) ? open.cell?.version ?? null : null;
      const capture: NewCapture = { vehicleId: open.vehicle.id, registration: open.vehicle.registration, date: open.date, ...entry, version };
      await queue.add(capture);
      if (!week || !fromDay) return setTarget(null);
      const after = new Map(waiting).set(keyOf(capture.vehicleId, capture.date), { ...capture, state: "pending", message: "", earliestMissing: null, current: null, queuedAt: 0 });
      setTarget(nextTarget(week, open.vehicle.id, day, after, canCapture));
    },
    [queue, waiting, week, fromDay, day, canCapture],
  );

  if (!canView)
    return (
      <View style={[styles.content, { gap: 16 }]}>
        <ScreenTitle>Revenue</ScreenTitle>
        <Card title="Revenue access" sub="Your admin has not granted revenue viewing access." />
      </View>
    );

  const currentWeek = Boolean(week && week.weekStart >= week.currentWeekStart);
  const detailVehicle = detail ? week?.vehicles.find((vehicle) => vehicle.id === detail) : undefined;

  let earliest: string | null = null;
  if (week && canCapture && mode === "day")
    for (const vehicle of week.vehicles) {
      const missing = nextMissing(vehicle, week, waiting);
      if (missing && missing < day && (!earliest || missing < earliest)) earliest = missing;
    }
  const counted = rows.filter((row) => row.cell.status !== "none");
  const done = counted.filter((row) => recorded(row.cell) || row.queued).length;
  // Not sent yet: waiting on this phone to go out (a conflict or refusal is shown as such).
  const unsent = counted.filter((row) => row.queued && (row.queued.state === "pending" || row.queued.state === "blocked")).length;
  const retry = () => setAttempt((value) => value + 1);

  const header = (
    <View style={styles.header}>
      <ScreenTitle>Revenue</ScreenTitle>
      {!detailVehicle && (
        <Segmented
          label="Revenue view"
          options={MODES}
          value={mode}
          onChange={(next) => {
            setMode(next);
            if (next === "day" && day && !inWeek) goToDay(day);
          }}
        />
      )}
      {data?.saved ? <Banner tone="offline">{OFFLINE_SAVED}</Banner> : error ? <Banner tone={error === OFFLINE_EMPTY ? "offline" : "error"}>{error}</Banner> : null}
      {error && !loading ? (
        <Button tone="outline" onPress={retry} style={styles.smallButton}>
          Try again
        </Button>
      ) : null}
      <QueuePanel queue={queue} canReplace={canReplace} onOpenDay={goToDay} />
      {week && detailVehicle ? (
        <View style={styles.dateNav}>
          <IconButton icon="back" label="Back to the week" onPress={() => setDetail(null)} />
          <View style={styles.navText}>
            <Text weight="bold" accessibilityRole="header" style={{ fontSize: 17, textAlign: "center" }}>
              {detailVehicle.registration}
            </Text>
            <Text style={{ fontSize: 14, color: colors.grey, textAlign: "center" }}>{`${detailVehicle.companyName}, ${rangeLabel(week.weekStart, week.weekThrough)}`}</Text>
          </View>
          {/* Balances the back button, so the title sits in the middle as the day and week titles do. */}
          <View style={styles.navSpacer} />
        </View>
      ) : week && mode === "day" && day ? (
        <>
          <View style={styles.dateNav}>
            <IconButton icon="back" label="Previous day" onPress={() => goToDay(shiftDate(day, -1))} />
            <Text weight="bold" style={[styles.navText, { fontSize: 17 }]}>
              {longDayLabel(day)}
            </Text>
            <IconButton icon="forward" label="Next day" disabled={day >= week.businessDate} onPress={() => goToDay(shiftDate(day, 1))} />
          </View>
          {inWeek && counted.length > 0 && (
            <Text style={{ fontSize: 14, color: colors.grey }}>
              <Text weight="bold" style={{ fontSize: 14, color: colors.navy }}>{`${done} of ${counted.length}`}</Text>
              {` captured${unsent ? `, ${unsent} not sent yet` : ""}`}
            </Text>
          )}
          {earliest && (
            <Pressable
              accessibilityRole="button"
              accessibilityLabel={`Earlier days are missing. Start with ${longDayLabel(earliest)}`}
              onPress={() => goToDay(earliest!)}
              style={[styles.missBanner, { borderColor: colors.redLine, backgroundColor: colors.redBg }]}
            >
              <Icon name="alert" size={18} color={colors.redText} />
              <Text style={{ flex: 1, fontSize: 14, color: colors.redText }}>{`Earlier days are missing. Start with ${longDayLabel(earliest)}`}</Text>
            </Pressable>
          )}
        </>
      ) : week && mode === "week" ? (
        <>
          <View style={styles.dateNav}>
            <IconButton icon="back" label="Previous week" onPress={() => setWeekStart(shiftDate(week.weekStart, -7))} />
            <Text weight="bold" style={[styles.navText, { fontSize: 17 }]}>
              {rangeLabel(week.weekStart, week.weekThrough)}
            </Text>
            <IconButton
              icon="forward"
              label="Next week"
              disabled={currentWeek}
              onPress={() => {
                const next = shiftDate(week.weekStart, 7);
                setWeekStart(next >= week.currentWeekStart ? undefined : next);
              }}
            />
          </View>
          {week.vehicles.length > 0 && (
            <Text style={{ fontSize: 14, color: colors.grey }}>
              <Text weight="bold" style={{ fontSize: 14, color: colors.navy }}>
                {money(week.totalAmount)}
              </Text>
              {` of ${money(week.totalExpected)} expected to date${week.percent === null ? "" : `, ${week.percent}%`}`}
            </Text>
          )}
        </>
      ) : null}
    </View>
  );

  // A day or earlier week before the vehicles joined (or after they left) is empty too, which is not having none.
  const empty = loading ? (
    <LineSkeleton lines={4} />
  ) : !week || (mode === "day" && !inWeek) ? null : week.vehicles.length === 0 && currentWeek ? (
    <Card title="No vehicles in your view" sub="Vehicles you may capture revenue for will appear here." />
  ) : (
    <Card title={mode === "day" ? "No vehicles on this day" : "No vehicles this week"} sub="None of the vehicles in your view were in service then." />
  );

  return (
    <>
      {detailVehicle && week ? (
        <VehicleWeek
          key={`${detailVehicle.id}/${week.weekStart}/${shown}`}
          owner={owner}
          fallback={detailVehicle}
          week={week}
          waiting={waiting}
          canCapture={canCapture}
          header={header}
          onOpen={openDetailDay}
          onSessionEnded={onSessionEnded}
        />
      ) : mode === "day" ? (
        <FlatList
          style={styles.list}
          contentContainerStyle={styles.content}
          keyboardShouldPersistTaps="handled"
          data={rows}
          keyExtractor={(row) => row.vehicle.id}
          ListHeaderComponent={header}
          ListEmptyComponent={empty}
          renderItem={({ item, index }) => (
            <DayRow vehicle={item.vehicle} cell={item.cell} queued={item.queued} tappable={item.tappable} first={index === 0} last={index === rows.length - 1} onOpen={openDay} />
          )}
        />
      ) : (
        <FlatList
          style={styles.list}
          contentContainerStyle={styles.content}
          data={week?.vehicles ?? []}
          keyExtractor={(vehicle) => vehicle.id}
          ListHeaderComponent={header}
          ListEmptyComponent={empty}
          renderItem={({ item, index }) => <WeekRow vehicle={item} first={index === 0} last={index === (week?.vehicles.length ?? 0) - 1} onOpen={setDetail} />}
        />
      )}
      {target && (
        <CaptureSheet key={keyOf(target.vehicle.id, target.date)} target={target} canReason={canReason} onSave={(entry) => save(target, entry)} onClose={() => setTarget(null)} />
      )}
    </>
  );
}

type Colors = ReturnType<typeof useTheme>["colors"];

// Rows sit in one white list, as in the design: rounded at the ends, a divider between them.
const rowShell = (first: boolean, last: boolean, colors: Colors) => [
  styles.row,
  { borderColor: colors.cardLine, backgroundColor: colors.white },
  first && styles.firstRow,
  last && styles.lastRow,
  !first && { borderTopWidth: 1, borderTopColor: colors.divider },
];

// Memoized: typing in the capture sheet leaves the rows alone, and a row redraws only when its own day changes.
const DayRow = memo(function DayRow({
  vehicle,
  cell,
  queued,
  tappable,
  first,
  last,
  onOpen,
}: {
  vehicle: RevenueVehicle;
  cell: RevenueCell;
  queued?: QueuedCapture;
  tappable: boolean;
  first: boolean;
  last: boolean;
  onOpen: (vehicleId: string) => void;
}) {
  const { colors } = useTheme();
  let status: string;
  let right: ReactNode;
  if (queued) {
    status = `${valueText(queued)}, ${STATE_TAG[queued.state].toLowerCase()}`;
    right = (
      <>
        <Text weight="bold">{valueText(queued)}</Text>
        <Text style={{ fontSize: 13, color: queued.state === "pending" ? colors.amberText : colors.red }}>{STATE_TAG[queued.state]}</Text>
      </>
    );
  } else if (cell.status === "amount") {
    status = money(cell.amount ?? 0);
    right = <Text weight="bold">{status}</Text>;
  } else if (cell.status === "reason") {
    status = cell.reason ?? "No revenue";
    right = <Chip>{status}</Chip>;
  } else if (cell.status === "missing") {
    status = tappable ? "Enter revenue" : "Missing";
    right = tappable ? (
      <View style={[styles.enter, { borderColor: colors.red }]}>
        <Text weight="bold" style={{ fontSize: 14, color: colors.red }}>
          Enter
        </Text>
      </View>
    ) : (
      <Text weight="semibold" style={{ fontSize: 14, color: colors.red }}>
        Missing
      </Text>
    );
  } else {
    status = cell.status === "future" ? "Not yet" : "Not counted";
    right = <Text style={{ fontSize: 13, color: colors.grey }}>{status}</Text>;
  }
  const content = (
    <>
      <View style={styles.rowLeft}>
        <Text weight="bold">{vehicle.registration}</Text>
        <Text style={{ fontSize: 13, color: colors.grey }}>{cell.editedAfterCapture && !queued ? `${vehicle.companyName}, edited after capture` : vehicle.companyName}</Text>
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
      style={({ pressed }) => [rowShell(first, last, colors), pressed && { backgroundColor: colors.pressed }]}
    >
      {content}
    </Pressable>
  ) : (
    <View accessible accessibilityLabel={label} style={rowShell(first, last, colors)}>
      {content}
    </View>
  );
});

const WeekRow = memo(function WeekRow({ vehicle, first, last, onOpen }: { vehicle: RevenueVehicle; first: boolean; last: boolean; onOpen: (vehicleId: string) => void }) {
  const { colors } = useTheme();
  const share = vehicle.percent === null ? "" : `${vehicle.percent}% of ${money(vehicle.totalExpected)}`;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`${vehicle.registration}, ${money(vehicle.totalAmount)}${share ? `, ${share}` : ""}. Open the week`}
      onPress={() => onOpen(vehicle.id)}
      style={({ pressed }) => [rowShell(first, last, colors), pressed && { backgroundColor: colors.pressed }]}
    >
      <View style={styles.rowLeft}>
        <Text weight="bold">{vehicle.registration}</Text>
        <Text style={{ fontSize: 13, color: colors.grey }}>{vehicle.companyName}</Text>
      </View>
      <View style={styles.rowRight}>
        <Text weight="bold">{money(vehicle.totalAmount)}</Text>
        {share ? <Text style={{ fontSize: 13, color: (vehicle.percent ?? 100) < 90 ? colors.red : colors.grey }}>{share}</Text> : null}
      </View>
    </Pressable>
  );
});

// The day and expected columns of the vehicle week, widened with the person's text size.
function useColumns() {
  const { fontScale } = useTheme();
  // Capped, so the actual column keeps room for its amounts; beyond the caps the text wraps inside its column.
  return useMemo(() => ({ day: { width: 60 * Math.min(fontScale, 1.35) }, number: { width: 92 * Math.min(fontScale, 1.15) } }), [fontScale]);
}

const gap = (actual: number, expected: number) => {
  const difference = Math.round((actual - expected) * 100) / 100;
  return difference === 0 ? "On target" : `${money(Math.abs(difference))} ${difference > 0 ? "above" : "below"}`;
};

// One vehicle's week: expected, actual and the difference for each day, with a bar against expected.
function VehicleWeek({
  owner,
  fallback,
  week,
  waiting,
  canCapture,
  header,
  onOpen,
  onSessionEnded,
}: {
  owner: string;
  fallback: RevenueVehicle;
  week: RevenueWeek;
  waiting: Waiting;
  canCapture: boolean;
  header: ReactNode;
  onOpen: (vehicle: RevenueVehicle, date: string, week: RevenueWeek) => void;
  onSessionEnded: () => void;
}) {
  const { colors } = useTheme();
  const columns = useColumns();
  const [vehicle, setVehicle] = useState<RevenueVehicle>(fallback);
  const [problem, setProblem] = useState("");
  useEffect(() => {
    let active = true;
    loadWeek(owner, week.weekStart, fallback.id).then(
      ({ week: loaded }) => {
        const found = loaded.vehicles.find((item) => item.id === fallback.id);
        if (active && found) setVehicle(found);
      },
      (reason: Error) => {
        if (!active) return;
        if (reason instanceof SessionEndedError) return onSessionEnded();
        // Offline, the week list's copy of this vehicle stays on screen.
        setProblem(reason instanceof OfflineError ? "" : reason.message);
      },
    );
    return () => {
      active = false;
    };
  }, [owner, week.weekStart, fallback.id, onSessionEnded]);

  const vehicleWeek = useMemo(() => ({ ...week, vehicles: [vehicle] }), [week, vehicle]);
  const open = useCallback((date: string) => onOpen(vehicle, date, vehicleWeek), [onOpen, vehicle, vehicleWeek]);
  return (
    <FlatList
      style={styles.list}
      contentContainerStyle={styles.content}
      data={vehicle.days}
      keyExtractor={(cell) => cell.date}
      ListHeaderComponent={
        <View style={styles.header}>
          {header}
          {problem ? <ErrorText>{problem}</ErrorText> : null}
          <View style={[styles.detailRow, styles.detailHead, { borderBottomColor: colors.cardLine }]}>
            <Text weight="semibold" style={[styles.detailDay, columns.day, { color: colors.grey }]}>
              Day
            </Text>
            <Text weight="semibold" style={[styles.detailNumber, columns.number, { color: colors.grey }]}>
              Expected
            </Text>
            <Text weight="semibold" style={[styles.detailActual, { fontSize: 14, color: colors.grey, textAlign: "right" }]}>
              Actual and difference
            </Text>
          </View>
        </View>
      }
      renderItem={({ item }) => (
        <DayBar
          cell={item}
          today={week.businessDate}
          queued={waiting.get(keyOf(vehicle.id, item.date))}
          tappable={Boolean(targetFor(vehicle, item.date, vehicleWeek, waiting, canCapture))}
          onOpen={open}
        />
      )}
      ListFooterComponent={
        <View accessible accessibilityLabel={`To date: expected ${money(vehicle.totalExpected)}, actual ${money(vehicle.totalAmount)}, ${gap(vehicle.totalAmount, vehicle.totalExpected)}`} style={styles.detailRow}>
          <Text weight="bold" style={[styles.detailDay, columns.day]}>
            To date
          </Text>
          <Text weight="bold" style={[styles.detailNumber, columns.number]}>
            {money(vehicle.totalExpected)}
          </Text>
          <View style={styles.detailActual}>
            <Text weight="bold">{money(vehicle.totalAmount)}</Text>
            <Text style={{ fontSize: 13, color: vehicle.totalAmount < vehicle.totalExpected ? colors.red : colors.green }}>{gap(vehicle.totalAmount, vehicle.totalExpected)}</Text>
          </View>
        </View>
      }
    />
  );
}

const DayBar = memo(function DayBar({ cell, today, queued, tappable, onOpen }: { cell: RevenueCell; today: string; queued?: QueuedCapture; tappable: boolean; onOpen: (date: string) => void }) {
  const { colors } = useTheme();
  const columns = useColumns();
  // Not a shortfall: future days, days outside the fleet, and today before capture.
  const counted = recorded(cell) || Boolean(queued) || (cell.status === "missing" && cell.date < today);
  const actual = queued ? queued.amount ?? 0 : cell.amount ?? 0;
  const share = cell.expected > 0 ? Math.min(1, actual / cell.expected) : actual > 0 ? 1 : 0;
  const below = actual < cell.expected;
  const shown = queued
    ? `${valueText(queued)}, ${STATE_TAG[queued.state].toLowerCase()}`
    : cell.status === "amount"
      ? money(cell.amount ?? 0)
      : cell.status === "reason"
        ? cell.reason ?? "No revenue"
        : cell.status === "missing"
          ? cell.date < today
            ? "No record"
            : "Not yet"
          : cell.status === "future"
            ? "Not yet"
            : "Not counted";
  const difference = counted ? gap(actual, cell.expected) : "";
  const content = (
    <>
      <Text style={[styles.detailDay, columns.day]}>{shortDayLabel(cell.date)}</Text>
      <Text style={[styles.detailNumber, columns.number, { color: counted ? colors.navy : colors.grey }]}>{cell.status === "none" ? "" : money(cell.expected)}</Text>
      <View style={styles.detailActual}>
        <Text
          weight={cell.status === "amount" || queued ? "semibold" : "regular"}
          style={{ fontSize: 14, textAlign: "right", color: counted && cell.status === "missing" && !queued ? colors.red : counted ? colors.navy : colors.grey }}
        >
          {shown}
        </Text>
        {counted && (
          <View style={[styles.track, { backgroundColor: colors.divider }]} aria-hidden>
            <View style={[styles.fill, { width: `${Math.round(share * 100)}%`, backgroundColor: below ? colors.amberLine : colors.green }]} />
          </View>
        )}
        {difference ? <Text style={{ fontSize: 12, color: below ? colors.red : colors.green }}>{difference}</Text> : null}
      </View>
    </>
  );
  const label = `${shortDayLabel(cell.date)}: expected ${money(cell.expected)}, ${shown}${difference ? `, ${difference}` : ""}`;
  return tappable ? (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      onPress={() => onOpen(cell.date)}
      style={({ pressed }) => [styles.detailRow, { borderBottomColor: colors.divider }, pressed && { backgroundColor: colors.pressed }]}
    >
      {content}
    </Pressable>
  ) : (
    <View accessible accessibilityLabel={label} style={[styles.detailRow, { borderBottomColor: colors.divider }]}>
      {content}
    </View>
  );
});

// Captures that have not reached the API yet. Conflicts and refusals wait for the person; the rest go on their own.
function QueuePanel({ queue, canReplace, onOpenDay }: { queue: RevenueQueue; canReplace: (entry: QueuedCapture) => boolean; onOpenDay: (date: string) => void }) {
  // Replacing needs the person's own right to change that day, and the API's say on the saved record (canEdit).
  const mayReplace = (entry: QueuedCapture) => canReplace(entry) && entry.current?.canEdit !== false;
  const { colors } = useTheme();
  const network = useNetworkState();
  const offline = network.isConnected === false || network.isInternetReachable === false;
  if (!queue.entries.length) return null;
  const counts = queueCounts(queue.entries);
  const summary = [
    counts.waiting ? `${counts.waiting} waiting to send` : "",
    counts.conflicts ? `${counts.conflicts} ${counts.conflicts === 1 ? "conflict" : "conflicts"}` : "",
    counts.failed ? `${counts.failed} not saved` : "",
  ].filter(Boolean);
  return (
    <View style={[styles.panel, { borderColor: colors.amberLine, backgroundColor: colors.amberBg }]}>
      <View style={styles.panelHead}>
        <View style={{ flex: 1 }}>
          <Text weight="bold" accessibilityRole="header" style={{ color: colors.amberText }}>
            On this phone
          </Text>
          <Text style={{ fontSize: 14, color: colors.amberText }}>{summary.join(", ")}</Text>
          {offline && counts.waiting > 0 ? (
            <Text style={{ fontSize: 14, color: colors.amberText }}>No internet. They are sent when you are back online.</Text>
          ) : null}
        </View>
        {counts.waiting > 0 && (
          <Button tone="outline" busy={queue.syncing} busyText="Sending…" onPress={() => void queue.sync()} style={styles.smallButton}>
            Send now
          </Button>
        )}
      </View>
      {queue.entries
        .filter((entry) => entry.state !== "pending")
        .map((entry) => (
          <View key={keyOf(entry.vehicleId, entry.date)} style={[styles.problem, { borderColor: colors.cardLine, backgroundColor: colors.white }]}>
            <Text weight="bold">{`${entry.registration}, ${longDayLabel(entry.date)}`}</Text>
            <Text style={{ fontSize: 14 }}>{entry.message}</Text>
            {entry.state === "conflict" ? (
              <>
                <Text style={{ fontSize: 14, color: colors.grey }}>
                  {entry.current ? `Saved: ${valueText(entry.current)}${entry.current.note ? ` (${entry.current.note})` : ""}` : "Connect to the internet to see what was saved."}
                </Text>
                <Text style={{ fontSize: 14, color: colors.grey }}>{`Yours: ${valueText(entry)}${entry.note ? ` (${entry.note})` : ""}`}</Text>
                {entry.current && !mayReplace(entry) ? (
                  <Text style={{ fontSize: 14, color: colors.grey }}>
                    {canReplace(entry)
                      ? "Your access does not include changing the saved record for this day."
                      : "Changing a day after it has passed needs Correct revenue after the day."}
                  </Text>
                ) : null}
                {/* Stacked: each choice keeps its whole label on one line on a narrow phone. */}
                <View style={styles.choices}>
                  {entry.current ? (
                    mayReplace(entry) && (
                      <Button onPress={() => void queue.replace(entry)} style={styles.choice}>
                        Replace with mine
                      </Button>
                    )
                  ) : (
                    <Button onPress={() => void queue.retry(entry)} style={styles.choice}>
                      Check again
                    </Button>
                  )}
                  <Button tone="outline" onPress={() => void queue.discard(entry)} style={styles.choice}>
                    Keep saved value
                  </Button>
                </View>
              </>
            ) : (
              <View style={styles.actions}>
                {entry.state === "blocked" && entry.earliestMissing ? (
                  <Button tone="outline" onPress={() => onOpenDay(entry.earliestMissing!)} style={styles.flexButton}>
                    {`Open ${dayLabel(entry.earliestMissing)}`}
                  </Button>
                ) : (
                  <Button tone="outline" onPress={() => void queue.retry(entry)} style={styles.flexButton}>
                    Try again
                  </Button>
                )}
                <Button tone="outline" onPress={() => void queue.discard(entry)} style={styles.flexButton}>
                  Discard
                </Button>
              </View>
            )}
          </View>
        ))}
    </View>
  );
}

const AMOUNT = /^\d{1,12}(\.\d{1,2})?$/;

// Capture: an amount, or a reason for no revenue (only with "Record a no earnings reason"). Other needs a short note.
function CaptureSheet({
  target,
  canReason,
  onSave,
  onClose,
}: {
  target: Target;
  canReason: boolean;
  onSave: (entry: Pick<NewCapture, "amount" | "reason" | "note">) => Promise<void>;
  onClose: () => void;
}) {
  const { colors, fontScale } = useTheme();
  const insets = useSafeAreaInsets();
  const [focused, setFocused] = useState<"amount" | "note" | null>(null);
  const start = target.waiting ?? (recorded(target.cell) ? target.cell : undefined);
  const [amount, setAmount] = useState(start?.amount != null ? String(start.amount) : "");
  const [reason, setReason] = useState<RevenueReason | "">(REASONS.find((item) => item === start?.reason) ?? "");
  const [note, setNote] = useState(start?.note ?? "");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  async function save() {
    const text = amount.replace(/[,\s]/g, "");
    if (!text && !reason) return setError(canReason ? "Enter the revenue or pick a reason." : "Enter the revenue.");
    if (text && (!AMOUNT.test(text) || Number(text) <= 0)) return setError("Enter the revenue as a positive amount with at most two decimals.");
    if (reason === "Other" && !note.trim()) return setError("Say what happened.");
    setError("");
    setSaving(true);
    try {
      await onSave(text ? { amount: Number(text), reason: null, note: null } : { amount: null, reason: reason || null, note: reason === "Other" ? note.trim() : null });
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The entry could not be kept on this phone.");
    } finally {
      setSaving(false);
    }
  }

  // The focused field, as Field shows it: a blue border and, in the web preview, the design's soft ring instead of the browser's.
  const focus = (field: "amount" | "note"): TextInputProps["style"] =>
    focused === field
      ? { borderColor: colors.blue, outlineStyle: "solid", outlineWidth: 3, outlineOffset: 1, outlineColor: `${colors.blue}59` }
      : { outlineWidth: 0 };
  const track = (field: "amount" | "note") => ({ onFocus: () => setFocused(field), onBlur: () => setFocused((now) => (now === field ? null : now)) });

  return (
    <Modal visible transparent animationType="slide" onRequestClose={onClose}>
      <KeyboardAvoidingView style={[styles.scrim, { backgroundColor: colors.scrim }]} behavior={Platform.OS === "ios" ? "padding" : undefined}>
        <View accessibilityViewIsModal style={[styles.sheet, { backgroundColor: colors.white }]}>
          <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={[styles.sheetContent, { paddingBottom: 28 + insets.bottom }]}>
            <View style={styles.sheetHead}>
              <View style={{ flex: 1 }}>
                <Text weight="bold" accessibilityRole="header" style={{ fontSize: 22, lineHeight: 28 }}>
                  {target.vehicle.registration}
                </Text>
                <Text style={{ fontSize: 14, color: colors.grey }}>{target.cell ? `${longDayLabel(target.date)}. Expected ${money(target.cell.expected)}` : longDayLabel(target.date)}</Text>
              </View>
              <IconButton icon="close" label="Close" onPress={onClose} />
            </View>
            {target.info ? <Text style={[styles.info, { backgroundColor: colors.amberBg, color: colors.amberText }]}>{target.info}</Text> : null}
            <View style={{ gap: 8 }}>
              <Text weight="semibold" style={{ fontSize: 15 }}>
                Revenue
              </Text>
              <View style={styles.money}>
                <View style={[styles.currency, { borderColor: colors.line, backgroundColor: colors.field }]}>
                  <Text style={{ color: colors.grey }}>{currencyCode()}</Text>
                </View>
                <TextInput
                  accessibilityLabel="Revenue amount"
                  value={amount}
                  onChangeText={(value) => {
                    setAmount(value.replace(/[^\d.,]/g, ""));
                    setError("");
                    if (value) setReason("");
                  }}
                  keyboardType="decimal-pad"
                  autoFocus={!reason}
                  returnKeyType="done"
                  onSubmitEditing={() => void save()}
                  {...track("amount")}
                  style={[styles.amount, { borderColor: colors.line, color: colors.navy, fontFamily: fonts.regular, fontSize: 26 * fontScale }, focus("amount")]}
                />
              </View>
            </View>
            {canReason && (
              <>
                <View style={styles.or}>
                  <View style={[styles.rule, { backgroundColor: colors.cardLine }]} />
                  <Text style={{ fontSize: 13, color: colors.grey }}>or no revenue</Text>
                  <View style={[styles.rule, { backgroundColor: colors.cardLine }]} />
                </View>
                <View accessibilityRole="radiogroup" accessibilityLabel="No revenue reason" style={styles.reasons}>
                  {REASONS.map((item) => {
                    const chosen = reason === item;
                    return (
                      <Pressable
                        key={item}
                        accessibilityRole="radio"
                        accessibilityLabel={item}
                        accessibilityState={{ checked: chosen }}
                        onPress={() => {
                          setReason(chosen ? "" : item);
                          setAmount("");
                          setError("");
                        }}
                        style={[styles.reason, chosen ? { borderWidth: 2, borderColor: colors.blue, backgroundColor: colors.blueTint } : { borderColor: colors.line, backgroundColor: colors.white }]}
                      >
                        <Text weight="semibold" style={{ color: chosen ? colors.blueDark : colors.navy }}>
                          {item}
                        </Text>
                      </Pressable>
                    );
                  })}
                </View>
                {reason === "Other" && (
                  <View style={{ gap: 8 }}>
                    <Text weight="semibold" style={{ fontSize: 15 }}>
                      What happened
                    </Text>
                    <TextInput
                      accessibilityLabel="What happened"
                      value={note}
                      maxLength={NOTE_LIMIT}
                      // Picking Other asks what happened, so the note is ready to type, as in the design.
                      autoFocus
                      returnKeyType="done"
                      onSubmitEditing={() => void save()}
                      {...track("note")}
                      onChangeText={(value) => {
                        setNote(value.slice(0, NOTE_LIMIT));
                        setError("");
                      }}
                      style={[styles.note, { borderColor: colors.line, color: colors.navy, fontFamily: fonts.regular, fontSize: 18 * fontScale }, focus("note")]}
                    />
                    <Text style={{ fontSize: 13, color: colors.grey }}>{`${note.length} of ${NOTE_LIMIT} characters`}</Text>
                  </View>
                )}
              </>
            )}
            <ErrorText>{error}</ErrorText>
            <Button onPress={() => void save()} busy={saving} busyText="Saving…">
              Save
            </Button>
          </ScrollView>
        </View>
      </KeyboardAvoidingView>
    </Modal>
  );
}

const styles = StyleSheet.create({
  list: { flex: 1 },
  content: { width: "100%", maxWidth: 420, alignSelf: "center", paddingTop: 28, paddingHorizontal: 24, paddingBottom: 32 },
  header: { gap: 16, marginBottom: 16 },
  dateNav: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 8 },
  navText: { flex: 1, textAlign: "center", alignItems: "center" },
  navSpacer: { width: 44 },
  missBanner: { flexDirection: "row", gap: 8, alignItems: "flex-start", minHeight: 44, paddingVertical: 12, paddingHorizontal: 14, borderWidth: 1, borderRadius: 12 },
  row: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", gap: 12, minHeight: 60, paddingVertical: 8, paddingHorizontal: 16, borderLeftWidth: 1, borderRightWidth: 1 },
  firstRow: { borderTopWidth: 1, borderTopLeftRadius: 14, borderTopRightRadius: 14 },
  lastRow: { borderBottomWidth: 1, borderBottomLeftRadius: 14, borderBottomRightRadius: 14 },
  rowLeft: { flexShrink: 1 },
  rowRight: { alignItems: "flex-end", flexShrink: 0 },
  enter: { paddingVertical: 6, paddingHorizontal: 14, borderWidth: 1, borderStyle: "dashed", borderRadius: 999 },
  detailHead: { minHeight: 0, paddingVertical: 6 },
  detailRow: { flexDirection: "row", alignItems: "center", gap: 8, minHeight: 60, paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: "transparent" },
  detailDay: { width: 60, fontSize: 14 },
  detailNumber: { width: 92, fontSize: 14, textAlign: "right" },
  detailActual: { flex: 1, alignItems: "flex-end", gap: 4 },
  track: { width: "100%", height: 6, borderRadius: 3, overflow: "hidden" },
  fill: { height: 6, borderRadius: 3 },
  panel: { borderWidth: 1, borderRadius: 14, padding: 14, gap: 12 },
  panelHead: { flexDirection: "row", alignItems: "center", gap: 12 },
  smallButton: { width: "auto", height: 44, paddingHorizontal: 16 },
  problem: { borderWidth: 1, borderRadius: 12, padding: 12, gap: 6 },
  actions: { flexDirection: "row", gap: 8, marginTop: 4 },
  flexButton: { flex: 1, width: "auto", height: 48, paddingHorizontal: 8 },
  choices: { gap: 8, marginTop: 4 },
  choice: { height: 48 },
  scrim: { flex: 1, justifyContent: "flex-end" },
  sheet: { width: "100%", maxWidth: 420, maxHeight: "92%", alignSelf: "center", borderTopLeftRadius: 20, borderTopRightRadius: 20 },
  sheetContent: { gap: 14, padding: 20, paddingBottom: 28 },
  sheetHead: { flexDirection: "row", alignItems: "flex-start", gap: 12 },
  info: { paddingVertical: 10, paddingHorizontal: 12, borderRadius: 10, fontSize: 14, overflow: "hidden" },
  money: { flexDirection: "row", alignItems: "stretch" },
  currency: { justifyContent: "center", paddingHorizontal: 14, borderWidth: 1, borderRightWidth: 0, borderTopLeftRadius: 12, borderBottomLeftRadius: 12 },
  amount: { flex: 1, minWidth: 0, height: 60, paddingHorizontal: 14, borderWidth: 1, borderTopRightRadius: 12, borderBottomRightRadius: 12 },
  or: { flexDirection: "row", alignItems: "center", gap: 12 },
  rule: { flex: 1, height: 1 },
  reasons: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  reason: { width: "48%", flexGrow: 1, minHeight: 52, borderWidth: 1, borderRadius: 12, alignItems: "center", justifyContent: "center", paddingHorizontal: 8 },
  note: { height: 56, paddingHorizontal: 16, borderWidth: 1, borderRadius: 12 },
});
