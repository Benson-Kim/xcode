import { useState } from "react";
import {
  KeyboardAvoidingView,
  Modal,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  TextInput,
  View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import {
  REVENUE_NOTE_LIMIT,
  REVENUE_REASONS,
  isRecorded,
  parseRevenueAmount,
  type RevenueReason,
} from "@xcode/shared/revenue";

import { useFormats } from "../../lib/formats";
import type { NewCapture } from "../../revenue/queue";
import { Button, ErrorText, Text, alpha, fonts, useTheme } from "../../ui";
import { IconButton } from "../parts";
import { gapText } from "./HeaderNav";
import type { Target } from "./model";

type Entry = Pick<NewCapture, "amount" | "reason" | "note">;

// The form's values and what saving them does. Amount and reason exclude each other: typing one clears the other.
function useCaptureForm({
  target,
  canReason,
  onSave,
}: {
  target: Target;
  canReason: boolean;
  onSave: (entry: Entry) => Promise<void>;
}) {
  const start =
    target.waiting ?? (isRecorded(target.cell) ? target.cell : undefined);
  const [amount, setAmount] = useState(
    start?.amount != null ? String(start.amount) : "",
  );
  const [reason, setReason] = useState<RevenueReason | "">(
    REVENUE_REASONS.find((item) => item === start?.reason) ?? "",
  );
  const [note, setNote] = useState(start?.note ?? "");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  async function save() {
    const parsedAmount = parseRevenueAmount(amount);
    if (parsedAmount.ok && parsedAmount.amount === null && !reason)
      return setError(
        canReason
          ? "Enter the revenue or pick a reason."
          : "Enter the revenue.",
      );
    if (!parsedAmount.ok) return setError(parsedAmount.error);
    if (reason === "Other" && !note.trim())
      return setError("Say what happened.");
    setError("");
    setSaving(true);
    try {
      await onSave(
        parsedAmount.amount !== null
          ? { amount: parsedAmount.amount, reason: null, note: null }
          : {
              amount: null,
              reason: reason || null,
              note: reason === "Other" ? note.trim() : null,
            },
      );
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "The entry could not be kept on this phone.",
      );
    } finally {
      setSaving(false);
    }
  }

  return {
    amount,
    reason,
    note,
    error,
    saving,
    save,
    changeAmount: (value: string) => {
      setAmount(value.replace(/[^\d.,]/g, ""));
      setError("");
      if (value) setReason("");
    },
    pickReason: (item: RevenueReason) => {
      setReason(reason === item ? "" : item);
      setAmount("");
      setError("");
    },
    changeNote: (value: string) => {
      setNote(value.slice(0, REVENUE_NOTE_LIMIT));
      setError("");
    },
  };
}

// The focused field, as Field shows it: a blue border and, in the web preview, the design's soft ring instead of the browser's.
function useFocusRing() {
  const { colors } = useTheme();
  const [focused, setFocused] = useState(false);
  return {
    ring: focused
      ? {
          borderColor: colors.blue,
          outlineStyle: "solid" as const,
          outlineWidth: 3,
          outlineOffset: 1,
          outlineColor: alpha(colors.blue, 0.35),
        }
      : { outlineWidth: 0 },
    handlers: {
      onFocus: () => setFocused(true),
      onBlur: () => setFocused(false),
    },
  };
}

function SheetHead({
  target,
  onClose,
  onOpenGap,
}: {
  target: Target;
  onClose: () => void;
  onOpenGap: (date: string) => void;
}) {
  const { colors } = useTheme();
  const formats = useFormats();
  return (
    <>
      <View style={styles.sheetHead}>
        <View style={{ flex: 1 }}>
          <Text
            weight="bold"
            accessibilityRole="header"
            style={{ fontSize: 22, lineHeight: 28 }}
          >
            {target.vehicle.registration}
          </Text>
          <Text style={{ fontSize: 14, color: colors.grey }}>
            {target.cell && target.cell.expected > 0
              ? `${formats.formatWeekdayDate(target.date)}. Expected ${formats.kes(target.cell.expected)}`
              : formats.formatWeekdayDate(target.date)}
          </Text>
        </View>
        <IconButton icon="close" label="Close" onPress={onClose} />
      </View>
      {target.earlier ? (
        <View
          style={[styles.info, { backgroundColor: colors.amberBg, gap: 6 }]}
        >
          <Text style={{ color: colors.amberText, fontSize: 14 }}>
            {gapText(formats.formatWeekdayDate(target.earlier))}
          </Text>
          <Button
            tone="outline"
            onPress={() => onOpenGap(target.earlier!)}
            style={{ width: "auto", height: 44 }}
          >
            {`Open ${formats.formatDateOnly(target.earlier)}`}
          </Button>
        </View>
      ) : null}
    </>
  );
}

function AmountField({
  value,
  autoFocus,
  onChange,
  onSubmit,
}: {
  value: string;
  autoFocus: boolean;
  onChange: (value: string) => void;
  onSubmit: () => void;
}) {
  const { colors, fontScale } = useTheme();
  const { currencyCode } = useFormats();
  const { ring, handlers } = useFocusRing();
  return (
    <View style={{ gap: 8 }}>
      <Text weight="semibold" style={{ fontSize: 15 }}>
        Revenue
      </Text>
      {/* The figure is the day's net revenue: the crew settle fuel and their own pay out of the takings. */}
      <Text style={{ fontSize: 13, color: colors.grey }}>
        What the vehicle handed in for the day, after the crew settle fuel and
        their own pay.
      </Text>
      <View style={styles.money}>
        <View
          style={[
            styles.currency,
            { borderColor: colors.line, backgroundColor: colors.field },
          ]}
        >
          <Text style={{ color: colors.grey }}>{currencyCode()}</Text>
        </View>
        <TextInput
          accessibilityLabel="Revenue amount"
          value={value}
          onChangeText={onChange}
          keyboardType="decimal-pad"
          autoFocus={autoFocus}
          returnKeyType="done"
          onSubmitEditing={onSubmit}
          {...handlers}
          style={[
            styles.amount,
            {
              borderColor: colors.line,
              color: colors.navy,
              fontFamily: fonts.regular,
              fontSize: 26 * fontScale,
            },
            ring,
          ]}
        />
      </View>
    </View>
  );
}

function ReasonPicker({
  reason,
  onPick,
}: {
  reason: RevenueReason | "";
  onPick: (item: RevenueReason) => void;
}) {
  const { colors } = useTheme();
  return (
    <>
      <View style={styles.or}>
        <View style={[styles.rule, { backgroundColor: colors.cardLine }]} />
        <Text style={{ fontSize: 13, color: colors.grey }}>or no revenue</Text>
        <View style={[styles.rule, { backgroundColor: colors.cardLine }]} />
      </View>
      <View
        accessibilityRole="radiogroup"
        accessibilityLabel="No revenue reason"
        style={styles.reasons}
      >
        {REVENUE_REASONS.map((item) => {
          const chosen = reason === item;
          return (
            <Pressable
              key={item}
              accessibilityRole="radio"
              accessibilityLabel={item}
              accessibilityState={{ checked: chosen }}
              onPress={() => onPick(item)}
              style={[
                styles.reason,
                chosen
                  ? {
                      borderWidth: 2,
                      borderColor: colors.blue,
                      backgroundColor: colors.blueSoft,
                    }
                  : {
                      borderColor: colors.line,
                      backgroundColor: colors.surface,
                    },
              ]}
            >
              <Text
                weight="semibold"
                style={{
                  color: chosen ? colors.blueDark : colors.navy,
                }}
              >
                {item}
              </Text>
            </Pressable>
          );
        })}
      </View>
    </>
  );
}

function NoteField({
  value,
  onChange,
  onSubmit,
}: {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
}) {
  const { colors, fontScale } = useTheme();
  const { ring, handlers } = useFocusRing();
  return (
    <View style={{ gap: 8 }}>
      <Text weight="semibold" style={{ fontSize: 15 }}>
        What happened
      </Text>
      <TextInput
        accessibilityLabel="What happened"
        value={value}
        maxLength={REVENUE_NOTE_LIMIT}
        // Picking Other asks what happened, so the note is ready to type, as in the design.
        autoFocus
        returnKeyType="done"
        onSubmitEditing={onSubmit}
        {...handlers}
        onChangeText={onChange}
        style={[
          styles.note,
          {
            borderColor: colors.line,
            color: colors.navy,
            fontFamily: fonts.regular,
            fontSize: 18 * fontScale,
          },
          ring,
        ]}
      />
      <Text
        style={{ fontSize: 13, color: colors.grey }}
      >{`${value.length} of ${REVENUE_NOTE_LIMIT} characters`}</Text>
    </View>
  );
}

// Capture: an amount, or a reason for no revenue (only with "Record a no earnings reason"). Other needs a short note.
export function CaptureSheet({
  target,
  canReason,
  onSave,
  onClose,
  onOpenGap,
}: {
  target: Target;
  canReason: boolean;
  onSave: (entry: Entry) => Promise<void>;
  onClose: () => void;
  // Closes the sheet and moves the screen to the vehicle's earlier gap.
  onOpenGap: (date: string) => void;
}) {
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const form = useCaptureForm({ target, canReason, onSave });
  const submit = () => void form.save();
  return (
    <Modal visible transparent animationType="slide" onRequestClose={onClose}>
      <KeyboardAvoidingView
        style={[styles.scrim, { backgroundColor: colors.scrim }]}
        behavior={Platform.OS === "ios" ? "padding" : undefined}
      >
        <View
          accessibilityViewIsModal
          style={[styles.sheet, { backgroundColor: colors.surface }]}
        >
          <ScrollView
            keyboardShouldPersistTaps="handled"
            contentContainerStyle={[
              styles.sheetContent,
              { paddingBottom: 28 + insets.bottom },
            ]}
          >
            <SheetHead
              target={target}
              onClose={onClose}
              onOpenGap={onOpenGap}
            />
            <AmountField
              value={form.amount}
              autoFocus={!form.reason}
              onChange={form.changeAmount}
              onSubmit={submit}
            />
            {canReason && (
              <>
                <ReasonPicker reason={form.reason} onPick={form.pickReason} />
                {form.reason === "Other" && (
                  <NoteField
                    value={form.note}
                    onChange={form.changeNote}
                    onSubmit={submit}
                  />
                )}
              </>
            )}
            <ErrorText>{form.error}</ErrorText>
            <Button onPress={submit} busy={form.saving} busyText="Saving…">
              Save
            </Button>
          </ScrollView>
        </View>
      </KeyboardAvoidingView>
    </Modal>
  );
}

const styles = StyleSheet.create({
  scrim: { flex: 1, justifyContent: "flex-end" },
  sheet: {
    width: "100%",
    maxWidth: 420,
    maxHeight: "92%",
    alignSelf: "center",
    borderTopLeftRadius: 20,
    borderTopRightRadius: 20,
  },
  sheetContent: { gap: 14, padding: 20, paddingBottom: 28 },
  sheetHead: { flexDirection: "row", alignItems: "flex-start", gap: 12 },
  info: {
    paddingVertical: 10,
    paddingHorizontal: 12,
    borderRadius: 10,
    fontSize: 14,
    overflow: "hidden",
  },
  money: { flexDirection: "row", alignItems: "stretch" },
  currency: {
    justifyContent: "center",
    paddingHorizontal: 14,
    borderWidth: 1,
    borderRightWidth: 0,
    borderTopLeftRadius: 12,
    borderBottomLeftRadius: 12,
  },
  amount: {
    flex: 1,
    minWidth: 0,
    height: 60,
    paddingHorizontal: 14,
    borderWidth: 1,
    borderTopRightRadius: 12,
    borderBottomRightRadius: 12,
  },
  or: { flexDirection: "row", alignItems: "center", gap: 12 },
  rule: { flex: 1, height: 1 },
  reasons: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  reason: {
    width: "48%",
    flexGrow: 1,
    minHeight: 52,
    borderWidth: 1,
    borderRadius: 12,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: 8,
  },
  note: { height: 56, paddingHorizontal: 16, borderWidth: 1, borderRadius: 12 },
});
