import { useEffect, useMemo, useState } from "react";
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Modal,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  View,
} from "react-native";
import type { RevenueCell, RevenueVehicle, RevenueWeek } from "@xcode/shared";
import { apiGet, apiPut, SessionEndedError } from "../lib/api";
import { money } from "../lib/format";
import type { StoredPerson } from "../lib/storage";
import { Banner, Button, Field, Text, useTheme } from "../ui";
import { Card, CardNote, ScreenTitle, Segmented } from "./parts";

const REASONS = ["Garage", "Arrest", "No Crew", "Other"] as const;
type Reason = (typeof REASONS)[number];
type ViewMode = "day" | "week";

const MODES: { value: ViewMode; label: string }[] = [
  { value: "day", label: "Day" },
  { value: "week", label: "Week" },
];

function shiftDate(value: string, amount: number) {
  const date = new Date(`${value}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + amount);
  return date.toISOString().slice(0, 10);
}

function dayLabel(value: string) {
  return new Date(`${value}T00:00:00Z`).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  });
}

function statusText(cell: RevenueCell) {
  if (cell.status === "amount") return money(cell.amount ?? 0);
  if (cell.status === "reason") return cell.reason ?? "No earnings";
  if (cell.status === "missing") return "Missing";
  if (cell.status === "future") return "Future";
  return "Not active";
}

function statusColor(cell: RevenueCell, colors: ReturnType<typeof useTheme>["colors"]) {
  if (cell.status === "amount" || cell.status === "reason") return colors.green;
  if (cell.status === "missing") return colors.amberText;
  if (cell.status === "none") return colors.grey;
  return colors.grey;
}

export function RevenueScreen({
  person,
  offline,
  onSessionEnded,
}: {
  person: StoredPerson;
  offline: boolean;
  onSessionEnded: () => void;
}) {
  const { colors } = useTheme();
  const [mode, setMode] = useState<ViewMode>("day");
  const [weekStart, setWeekStart] = useState("");
  const [day, setDay] = useState("");
  const [data, setData] = useState<RevenueWeek | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState<{ vehicle: RevenueVehicle; cell: RevenueCell } | null>(null);

  const path = useMemo(
    () => `setup/revenue${weekStart ? `?weekStart=${encodeURIComponent(weekStart)}` : ""}`,
    [weekStart],
  );

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    apiGet<RevenueWeek>(path).then(
      (result) => {
        if (!active) return;
        setData(result);
        setLoading(false);
        if (!weekStart) setWeekStart(result.weekStart);
        setDay((current) => {
          if (current && current >= result.weekStart && current <= result.weekThrough) return current;
          return result.businessDate >= result.weekStart && result.businessDate <= result.weekThrough
            ? result.businessDate
            : result.weekThrough;
        });
      },
      (reason: Error) => {
        if (!active) return;
        setLoading(false);
        if (reason instanceof SessionEndedError) return onSessionEnded();
        setError(reason.message);
      },
    );
    return () => {
      active = false;
    };
  }, [onSessionEnded, path, weekStart]);

  const canView = person.permissions.includes("revenue.view");
  const canChooseReason = person.permissions.includes("revenue.no_earnings");
  const currentWeek = Boolean(data && data.weekStart >= data.currentWeekStart);
  const dayRows = data
    ? data.vehicles
        .map((vehicle) => ({
          vehicle,
          cell: vehicle.days.find((cell) => cell.date === day),
        }))
        .filter((row): row is { vehicle: RevenueVehicle; cell: RevenueCell } => Boolean(row.cell))
    : [];

  if (!canView) {
    return (
      <View style={styles.screen}>
        <ScreenTitle>Revenue</ScreenTitle>
        <Card title="Revenue access" sub="Your admin has not granted revenue viewing access." />
      </View>
    );
  }

  return (
    <View style={styles.screen}>
      <ScreenTitle>Revenue</ScreenTitle>
      <Text style={{ color: colors.grey }}>
        Record revenue or explain why no revenue was earned. Missing days must be handled in order.
      </Text>
      {offline && <Banner tone="offline">No internet. Revenue records need a connection to load and save.</Banner>}
      {error && <Banner>{error}</Banner>}
      <Segmented label="Revenue view" options={MODES} value={mode} onChange={setMode} />

      {data && (
        <View style={styles.controls}>
          <Button
            tone="outline"
            onPress={() => setWeekStart(shiftDate(data.weekStart, -7))}
            disabled={loading}
          >
            Previous week
          </Button>
          <Button
            tone="outline"
            onPress={() => setWeekStart(shiftDate(data.weekStart, 7))}
            disabled={loading || currentWeek}
          >
            Next week
          </Button>
          <Text style={{ color: colors.grey, fontSize: 14 }}>
            {dayLabel(data.weekStart)} – {dayLabel(data.weekThrough)}
          </Text>
        </View>
      )}

      {loading && !data ? (
        <View accessibilityRole="progressbar" style={styles.loading}>
          <ActivityIndicator color={colors.blue} />
          <Text>Loading revenue…</Text>
        </View>
      ) : !data || data.vehicles.length === 0 ? (
        <Card title="No vehicles in scope" sub="There are no active or historical vehicles available for revenue capture." />
      ) : mode === "day" ? (
        <View style={styles.list}>
          <View style={[styles.dayHeader, { borderColor: colors.cardLine, backgroundColor: colors.white }]}>
            <Button
              tone="outline"
              onPress={() => setDay(shiftDate(day, -1))}
              disabled={day <= data.weekStart}
              style={{ width: 104 }}
            >
              Previous day
            </Button>
            <Text weight="bold" style={{ textAlign: "center", flex: 1 }}>{dayLabel(day)}</Text>
            <Button
              tone="outline"
              onPress={() => setDay(shiftDate(day, 1))}
              disabled={day >= data.weekThrough}
              style={{ width: 104 }}
            >
              Next day
            </Button>
          </View>
          {dayRows.map(({ vehicle, cell }) => (
            <RevenueVehicleCard
              key={vehicle.id}
              vehicle={vehicle}
              cell={cell}
              colors={colors}
              onOpen={cell.canEdit ? () => setSelected({ vehicle, cell }) : undefined}
            />
          ))}
          {!dayRows.length && <Card title="No vehicle rows" sub="This date is outside the loaded week." />}
        </View>
      ) : (
        <View style={styles.list}>
          {data.vehicles.map((vehicle) => (
            <Card key={vehicle.id} title={vehicle.registration} sub={vehicle.companyName}>
              <Text style={{ color: colors.grey }}>
                {money(vehicle.totalAmount)} of {money(vehicle.totalExpected)}
                {vehicle.percent === null ? "" : ` · ${vehicle.percent}%`}
              </Text>
              <View style={styles.weekDays}>
                {vehicle.days.map((cell) => (
                  <RevenueCellButton
                    key={cell.date}
                    cell={cell}
                    colors={colors}
                    onPress={cell.canEdit ? () => setSelected({ vehicle, cell }) : undefined}
                  />
                ))}
              </View>
              {vehicle.earliestMissing && (
                <CardNote>Fill from {dayLabel(vehicle.earliestMissing)}.</CardNote>
              )}
            </Card>
          ))}
        </View>
      )}

      {selected && (
        <RevenueEditor
          vehicle={selected.vehicle}
          cell={selected.cell}
          canChooseReason={canChooseReason}
          onClose={() => setSelected(null)}
          onSessionEnded={onSessionEnded}
          onSaved={() => {
            setSelected(null);
            setError("");
            setLoading(true);
            void apiGet<RevenueWeek>(path).then(setData).catch((reason: Error) => {
              if (reason instanceof SessionEndedError) onSessionEnded();
              else setError(reason.message);
            }).finally(() => setLoading(false));
          }}
        />
      )}
    </View>
  );
}

function RevenueVehicleCard({
  vehicle,
  cell,
  colors,
  onOpen,
}: {
  vehicle: RevenueVehicle;
  cell: RevenueCell;
  colors: ReturnType<typeof useTheme>["colors"];
  onOpen?: () => void;
}) {
  return (
    <Card title={vehicle.registration} sub={vehicle.companyName}>
      <View style={styles.cardLine}>
        <View style={{ flex: 1 }}>
          <Text weight="semibold">{statusText(cell)}</Text>
          <Text style={{ fontSize: 14, color: colors.grey }}>Expected {money(cell.expected)}</Text>
        </View>
        {onOpen && (
          <Button tone="outline" onPress={onOpen}>
            {cell.status === "missing" ? "Capture" : "Edit"}
          </Button>
        )}
      </View>
      {cell.editedAfterCapture && <CardNote>Edited after capture.</CardNote>}
    </Card>
  );
}

function RevenueCellButton({
  cell,
  colors,
  onPress,
}: {
  cell: RevenueCell;
  colors: ReturnType<typeof useTheme>["colors"];
  onPress?: () => void;
}) {
  const content = (
    <>
      <Text weight="semibold" style={{ color: statusColor(cell, colors), fontSize: 14 }}>
        {dayLabel(cell.date).replace(/ \d{4}$/, "")}
      </Text>
      <Text style={{ fontSize: 13 }}>{statusText(cell)}</Text>
      <Text style={{ fontSize: 12, color: colors.grey }}>Expected {money(cell.expected)}</Text>
    </>
  );
  return onPress ? (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`${dayLabel(cell.date)}: ${statusText(cell)}`}
      onPress={onPress}
      style={({ pressed }) => [
        styles.dayCell,
        { borderColor: colors.cardLine, backgroundColor: pressed ? colors.blueWash : colors.white },
      ]}
    >
      {content}
    </Pressable>
  ) : (
    <View style={[styles.dayCell, { borderColor: colors.cardLine, backgroundColor: colors.white }]}>{content}</View>
  );
}

function RevenueEditor({
  vehicle,
  cell,
  canChooseReason,
  onClose,
  onSaved,
  onSessionEnded,
}: {
  vehicle: RevenueVehicle;
  cell: RevenueCell;
  canChooseReason: boolean;
  onClose: () => void;
  onSaved: () => void;
  onSessionEnded: () => void;
}) {
  const { colors } = useTheme();
  const [amount, setAmount] = useState(cell.amount === null ? "" : String(cell.amount));
  const [reason, setReason] = useState<Reason | "">((cell.reason as Reason | null) ?? "");
  const [note, setNote] = useState(cell.note ?? "");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  async function save() {
    setError("");
    const text = amount.replace(/,/g, "").trim();
    const numeric = text ? Number(text) : null;
    if (text && (!Number.isFinite(numeric) || numeric <= 0)) return setError("Enter a positive revenue amount.");
    if (numeric !== null && reason) return setError("Choose either revenue or a no-earnings reason.");
    if (numeric === null && !reason) return setError("Enter revenue or choose why there was no revenue.");
    if (reason === "Other" && !note.trim()) return setError("Explain what happened when choosing Other.");
    setSaving(true);
    try {
      await apiPut<{ id: string }>(`setup/revenue/${vehicle.id}/${cell.date}`, {
        amount: numeric,
        reason: reason || null,
        note: reason === "Other" ? note.trim() : null,
      });
      onSaved();
    } catch (caught) {
      if (caught instanceof SessionEndedError) onSessionEnded();
      else setError(caught instanceof Error ? caught.message : "The revenue record could not be saved.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal visible transparent animationType="slide" onRequestClose={onClose}>
      <KeyboardAvoidingView style={styles.modalRoot} behavior={Platform.OS === "ios" ? "padding" : undefined}>
        <View style={[styles.modalCard, { backgroundColor: colors.white, borderColor: colors.cardLine }]}>
          <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={styles.modalContent}>
            <Text weight="bold" accessibilityRole="header" style={styles.modalTitle}>
              {vehicle.registration} · {dayLabel(cell.date)}
            </Text>
            <Text style={{ color: colors.grey }}>
              Expected {money(cell.expected)}. Earlier missing days must be handled first.
            </Text>
            <Field
              label="Revenue amount"
              value={amount}
              onChangeText={(value) => {
                setAmount(value);
                if (value) setReason("");
              }}
              keyboardType="decimal-pad"
              editable={!reason}
              placeholder="0.00"
            />
            <Text weight="semibold">No earnings reason</Text>
            {!canChooseReason && <Text style={{ color: colors.grey, fontSize: 14 }}>Your access does not include no-earnings reasons.</Text>}
            <View style={styles.reasonGrid}>
              {REASONS.map((item) => {
                const selectedReason = reason === item;
                return (
                  <Pressable
                    key={item}
                    accessibilityRole="radio"
                    accessibilityState={{ checked: selectedReason, disabled: !canChooseReason || Boolean(amount) }}
                    disabled={!canChooseReason || Boolean(amount)}
                    onPress={() => {
                      setReason(item);
                      setAmount("");
                      if (item !== "Other") setNote("");
                    }}
                    style={[
                      styles.reason,
                      { borderColor: selectedReason ? colors.blue : colors.line, backgroundColor: selectedReason ? colors.blueWash : colors.white },
                      (!canChooseReason || Boolean(amount)) && styles.disabled,
                    ]}
                  >
                    <Text weight="semibold">{item}</Text>
                  </Pressable>
                );
              })}
            </View>
            {reason === "Other" && (
              <Field
                label="What happened?"
                value={note}
                onChangeText={setNote}
                maxLength={80}
                placeholder="Explain briefly"
              />
            )}
            {error && <Banner>{error}</Banner>}
            <View style={styles.modalActions}>
              <Button tone="outline" onPress={onClose} disabled={saving}>Cancel</Button>
              <Button onPress={() => void save()} busy={saving} busyText="Saving…">Save revenue</Button>
            </View>
          </ScrollView>
        </View>
      </KeyboardAvoidingView>
    </Modal>
  );
}

const styles = StyleSheet.create({
  screen: { gap: 16 },
  controls: { gap: 10 },
  list: { gap: 12 },
  loading: { alignItems: "center", gap: 10, paddingVertical: 40 },
  dayHeader: { flexDirection: "row", alignItems: "center", gap: 8, borderWidth: 1, borderRadius: 14, padding: 10 },
  cardLine: { flexDirection: "row", alignItems: "center", gap: 12 },
  weekDays: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  dayCell: { width: "47%", minHeight: 82, borderWidth: 1, borderRadius: 12, padding: 10, gap: 2 },
  modalRoot: { flex: 1, justifyContent: "flex-end", backgroundColor: "rgba(20,33,61,0.4)" },
  modalCard: { maxHeight: "90%", borderTopWidth: 1, borderRadius: 18, padding: 20 },
  modalContent: { gap: 14, paddingBottom: 18 },
  modalTitle: { fontSize: 22, lineHeight: 28 },
  reasonGrid: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  reason: { minWidth: "47%", minHeight: 48, borderWidth: 2, borderRadius: 12, justifyContent: "center", alignItems: "center", paddingHorizontal: 10 },
  disabled: { opacity: 0.5 },
  modalActions: { flexDirection: "row", gap: 10 },
});
