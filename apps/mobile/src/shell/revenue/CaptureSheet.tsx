import { useState, type ReactNode } from "react";
import { Pressable, StyleSheet, TextInput, View } from "react-native";

import {
  DEFAULT_LOW_BELOW,
  NOT_FUELED,
  REVENUE_NOTE_LIMIT,
  REVENUE_REASONS,
  fuelChoice,
  isRecorded,
  keptFuel,
  parseRevenueAmount,
  type RevenueFuel,
  type RevenueReason,
} from "@xcode/shared/revenue";

import { useFormats } from "../../lib/formats";
import type { NewCapture } from "../../revenue/queue";
import {
  Button,
  ErrorText,
  Sheet,
  Text,
  alpha,
  fonts,
  useTheme,
} from "../../ui";
import { IconButton } from "../parts";
import { useTargets } from "../targets";
import { gapText } from "./HeaderNav";
import type { Target } from "./model";

type Entry = Pick<NewCapture, "amount" | "reason" | "note" | "fuel">;

const typedAmount = (text: string) => {
  const parsed = parseRevenueAmount(text);
  return parsed.ok ? parsed.amount : null;
};

// The form's values and what saving them does (v2.34, v2.37). Below the vehicle's low figure for the day an amount
// needs one of the reasons; with no amount a reason records no revenue. The fuel answer follows the amount: none
// without one, and Yes only from the fuel question amount.
function useCaptureForm({
  target,
  canReason,
  fuelQuestionFrom,
  onSave,
}: {
  target: Target;
  canReason: boolean;
  fuelQuestionFrom?: number;
  onSave: (entry: Entry) => Promise<void>;
}) {
  const formats = useFormats();
  const start =
    target.waiting ?? (isRecorded(target.cell) ? target.cell : undefined);
  const lowBelow = target.cell?.lowBelow ?? DEFAULT_LOW_BELOW;
  const [amount, setAmount] = useState(
    start?.amount != null ? String(start.amount) : "",
  );
  const [reason, setReason] = useState<RevenueReason | "">(
    REVENUE_REASONS.find((item) => item === start?.reason) ?? "",
  );
  const [note, setNote] = useState(start?.note ?? "");
  const [fuel, setFuel] = useState<RevenueFuel | null>(start?.fuel ?? null);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  async function save() {
    const parsedAmount = parseRevenueAmount(amount);
    if (!parsedAmount.ok) return setError(parsedAmount.error);
    const value = parsedAmount.amount;
    const low = value !== null && value < lowBelow;
    if (value === null && !reason)
      return setError(
        canReason
          ? "Enter the revenue or pick a reason."
          : "Enter the revenue.",
      );
    if (low && !reason)
      return setError(
        `Choose the reason. Revenue is below ${formats.kes(lowBelow)}.`,
      );
    const why = value === null || low ? reason || null : null;
    if (why === "Other" && !note.trim()) return setError("Say what happened.");
    const told = why === "Other" ? note.trim() : null;
    setError("");
    setSaving(true);
    try {
      // A day with no amount sends no fuel answer: the server keeps none for it.
      await onSave(
        value !== null
          ? {
              amount: value,
              reason: why,
              note: told,
              fuel: keptFuel(fuel, value, fuelQuestionFrom),
            }
          : { amount: null, reason: why, note: told },
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
    fuel,
    lowBelow,
    choice: fuelChoice(typedAmount(amount), lowBelow, fuelQuestionFrom),
    error,
    saving,
    save,
    changeAmount: (value: string) => {
      const cleaned = value.replace(/[^\d.,]/g, "");
      setAmount(cleaned);
      setFuel(keptFuel(fuel, typedAmount(cleaned), fuelQuestionFrom));
      setError("");
    },
    pickReason: (item: RevenueReason) => {
      setReason(reason === item ? "" : item);
      setError("");
    },
    // Tapping the chosen answer again clears it: the question is optional.
    answerFuel: (answer: RevenueFuel) => {
      setFuel(fuel === answer ? null : answer);
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
  busy,
  onClose,
  onOpenGap,
}: {
  target: Target;
  busy: boolean;
  onClose: () => void;
  onOpenGap: (date: string) => void;
}) {
  const { colors } = useTheme();
  const formats = useFormats();
  const targets = useTargets();
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
            {targets && target.cell && target.cell.expected > 0
              ? `${formats.formatWeekdayDate(target.date)}. Expected ${formats.kes(target.cell.expected)}`
              : formats.formatWeekdayDate(target.date)}
          </Text>
        </View>
        <IconButton
          icon="close"
          label="Close"
          disabled={busy}
          onPress={onClose}
        />
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
            disabled={busy}
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

function OrNoRevenue() {
  const { colors } = useTheme();
  return (
    <View style={styles.or}>
      <View style={[styles.rule, { backgroundColor: colors.cardLine }]} />
      <Text style={{ fontSize: 13, color: colors.grey }}>or no revenue</Text>
      <View style={[styles.rule, { backgroundColor: colors.cardLine }]} />
    </View>
  );
}

function RowLabel({ title, sub }: { title: string; sub?: string }) {
  const { colors } = useTheme();
  return (
    <View style={{ gap: 2 }}>
      <Text weight="semibold" style={{ fontSize: 15 }}>
        {title}
      </Text>
      {sub ? (
        <Text style={{ fontSize: 13, color: colors.grey }}>{sub}</Text>
      ) : null}
    </View>
  );
}

// One choice that can be tapped again to clear it: a reason, Not fueled, or a fuel answer.
function Chip({
  label,
  chosen,
  role,
  wide,
  onPress,
}: {
  label: string;
  chosen: boolean;
  role: "radio" | "checkbox";
  wide?: boolean;
  onPress: () => void;
}) {
  const { colors } = useTheme();
  return (
    <Pressable
      accessibilityRole={role}
      accessibilityLabel={label}
      accessibilityState={{ checked: chosen }}
      onPress={onPress}
      style={[
        styles.reason,
        !wide && styles.chip,
        chosen
          ? {
              borderWidth: 2,
              borderColor: colors.blue,
              backgroundColor: colors.blueSoft,
            }
          : { borderColor: colors.line, backgroundColor: colors.surface },
      ]}
    >
      <Text
        weight="semibold"
        style={{ color: chosen ? colors.blueDark : colors.navy }}
      >
        {label}
      </Text>
    </Pressable>
  );
}

// Not fueled, optional: under the reasons of a low day, or alone on the Tag row.
function NotFueled({
  fuel,
  onAnswer,
}: {
  fuel: RevenueFuel | null;
  onAnswer: (answer: RevenueFuel) => void;
}) {
  return (
    <View style={styles.reasons}>
      <Chip
        label={NOT_FUELED}
        role="checkbox"
        chosen={fuel === "no"}
        onPress={() => onAnswer("no")}
      />
    </View>
  );
}

// From the fuel question amount: Fueled? Yes or No, in an amber box. Optional; saving never waits for it.
function FuelQuestion({
  fuel,
  onAnswer,
}: {
  fuel: RevenueFuel | null;
  onAnswer: (answer: RevenueFuel) => void;
}) {
  const { colors } = useTheme();
  return (
    <View style={[styles.info, { backgroundColor: colors.amberBg, gap: 8 }]}>
      <Text weight="semibold" style={{ color: colors.amberText }}>
        Fueled?
      </Text>
      <View
        accessibilityRole="radiogroup"
        accessibilityLabel="Fueled?"
        style={styles.reasons}
      >
        <Chip
          label="Yes"
          role="radio"
          chosen={fuel === "yes"}
          onPress={() => onAnswer("yes")}
        />
        <Chip
          label="No"
          role="radio"
          chosen={fuel === "no"}
          onPress={() => onAnswer("no")}
        />
      </View>
    </View>
  );
}

function ReasonPicker({
  label,
  reason,
  onPick,
}: {
  label: string;
  reason: RevenueReason | "";
  onPick: (item: RevenueReason) => void;
}) {
  return (
    <>
      <View
        accessibilityRole="radiogroup"
        accessibilityLabel={label}
        style={styles.reasons}
      >
        {REVENUE_REASONS.map((item) => (
          <Chip
            key={item}
            label={item}
            role="radio"
            wide
            chosen={reason === item}
            onPress={() => onPick(item)}
          />
        ))}
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

// Capture: an amount, or a reason for no revenue (only with "Record a no earnings reason"). Under the amount, the
// rows v2.37 asks for: below the vehicle's low figure a reason (required) then Not fueled; up to the fuel question
// amount a Tag row with Not fueled; from it Fueled? Yes or No. Other needs a short note.
export function CaptureSheet({
  target,
  canReason,
  fuelQuestionFrom,
  onSave,
  onClose,
  onOpenGap,
}: {
  target: Target;
  canReason: boolean;
  fuelQuestionFrom?: number;
  onSave: (entry: Entry) => Promise<void>;
  onClose: () => void;
  // Closes the sheet and moves the screen to the vehicle's earlier gap.
  onOpenGap: (date: string) => void;
}) {
  const form = useCaptureForm({
    target,
    canReason,
    fuelQuestionFrom,
    onSave,
  });
  const formats = useFormats();
  const submit = () => void form.save();
  const otherNote =
    form.reason === "Other" ? (
      <NoteField
        value={form.note}
        onChange={form.changeNote}
        onSubmit={submit}
      />
    ) : null;
  const rows: Record<typeof form.choice, ReactNode> = {
    none: canReason ? (
      <>
        <OrNoRevenue />
        <ReasonPicker
          label="No revenue reason"
          reason={form.reason}
          onPick={form.pickReason}
        />
        {otherNote}
      </>
    ) : null,
    reasons: (
      <>
        <RowLabel
          title="Reason"
          sub={`Revenue is below ${formats.kes(form.lowBelow)}.`}
        />
        <ReasonPicker
          label="Low revenue reason"
          reason={form.reason}
          onPick={form.pickReason}
        />
        {otherNote}
        <NotFueled fuel={form.fuel} onAnswer={form.answerFuel} />
      </>
    ),
    tag: (
      <>
        <RowLabel title="Tag" />
        <NotFueled fuel={form.fuel} onAnswer={form.answerFuel} />
      </>
    ),
    ask: <FuelQuestion fuel={form.fuel} onAnswer={form.answerFuel} />,
  };
  return (
    <Sheet busy={form.saving} onClose={onClose}>
      <SheetHead
        target={target}
        busy={form.saving}
        onClose={onClose}
        onOpenGap={onOpenGap}
      />
      <AmountField
        value={form.amount}
        autoFocus={!form.reason}
        onChange={form.changeAmount}
        onSubmit={submit}
      />
      {rows[form.choice]}
      <ErrorText>{form.error}</ErrorText>
      <Button onPress={submit} busy={form.saving} busyText="Saving…">
        Save
      </Button>
    </Sheet>
  );
}

const styles = StyleSheet.create({
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
  chip: { width: "auto", flexGrow: 0, paddingHorizontal: 16 },
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
