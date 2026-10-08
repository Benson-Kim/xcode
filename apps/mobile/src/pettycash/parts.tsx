import { useState } from "react";
import { Pressable, StyleSheet, View } from "react-native";

import { shiftDate, startOfWeek } from "@xcode/shared/dates";
import type { Formatter } from "@xcode/shared/format";
import {
  PETTY_CASH_KIND_LABELS,
  PETTY_CASH_STATUS_LABELS,
  type PettyCashEntry,
  type PettyCashPeriod,
} from "@xcode/shared/pettyCash";

import { IconButton } from "../shell/parts";
import { Field, Icon, Text, useTheme } from "../ui";
import { unitsText } from "./format";

export function Notice({
  tone,
  children,
}: {
  tone: "ok" | "error";
  children: string;
}) {
  const { colors } = useTheme();
  const ok = tone === "ok";
  return (
    <View
      accessibilityRole="alert"
      accessibilityLiveRegion="polite"
      style={[
        styles.notice,
        ok
          ? { backgroundColor: colors.greenBg, borderColor: colors.green }
          : { backgroundColor: colors.redBg, borderColor: colors.redLine },
      ]}
    >
      {ok ? null : <Icon name="alert" size={18} color={colors.redText} />}
      <Text
        style={{
          flex: 1,
          fontSize: 15,
          color: ok ? colors.green : colors.redText,
        }}
      >
        {children}
      </Text>
    </View>
  );
}

// A row action or small standalone button, at least 44 points to touch.
export function SmallButton({
  children,
  onPress,
  tone = "outline",
  disabled,
  label,
}: {
  children: string;
  onPress: () => void;
  tone?: "outline" | "solid" | "danger";
  disabled?: boolean;
  label?: string;
}) {
  const { colors } = useTheme();
  const solid = tone === "solid";
  const color = tone === "danger" ? colors.red : colors.blue;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label ?? children}
      accessibilityState={{ disabled: Boolean(disabled) }}
      disabled={disabled}
      onPress={onPress}
      style={({ pressed }) => [
        styles.small,
        {
          borderColor: color,
          backgroundColor: solid
            ? pressed
              ? colors.blueDark
              : colors.blue
            : pressed
              ? colors.blueTint
              : "transparent",
        },
        disabled && { opacity: 0.55 },
      ]}
    >
      <Text
        weight="semibold"
        style={{ fontSize: 15, color: solid ? colors.onFill : color }}
      >
        {children}
      </Text>
    </Pressable>
  );
}

// The day (or week) shown and its buttons. A week runs from the organization's first day of the week; the next
// one is closed once it would start after the business date.
export function DayStepper({
  label,
  date,
  businessDate,
  formats,
  onChange,
  period = "day",
}: {
  label: string;
  date: string;
  businessDate: string;
  formats: Formatter;
  onChange: (date: string) => void;
  period?: PettyCashPeriod;
}) {
  const week = period === "week";
  const start = week ? startOfWeek(date, formats.firstDayOfWeek()) : date;
  const nextClosed = week
    ? shiftDate(start, 7) > businessDate
    : date >= businessDate;
  const next = shiftDate(date, week ? 7 : 1);
  return (
    <View style={styles.stepper} accessibilityLabel={label}>
      <IconButton
        icon="back"
        label={`Previous ${label.toLowerCase()}`}
        onPress={() => onChange(shiftDate(date, week ? -7 : -1))}
      />
      <Text
        weight="bold"
        style={{ flex: 1, textAlign: "center", fontSize: 17 }}
        accessibilityLiveRegion="polite"
      >
        {week
          ? formats.formatDateRange(start, shiftDate(start, 6))
          : formats.formatDateOnly(date)}
      </Text>
      <IconButton
        icon="forward"
        label={`Next ${label.toLowerCase()}`}
        disabled={nextClosed}
        onPress={() => onChange(next > businessDate ? businessDate : next)}
      />
    </View>
  );
}

export function Stat({
  label,
  value,
  bad,
}: {
  label: string;
  value: string;
  bad?: boolean;
}) {
  const { colors } = useTheme();
  return (
    <View
      accessible
      accessibilityLabel={`${label}, ${value}`}
      style={[
        styles.stat,
        { borderColor: colors.cardLine, backgroundColor: colors.surface },
      ]}
    >
      <Text style={{ fontSize: 13, lineHeight: 18, color: colors.grey }}>
        {label}
      </Text>
      <Text
        weight="bold"
        style={{
          fontSize: 17,
          lineHeight: 22,
          color: bad ? colors.red : colors.navy,
        }}
      >
        {value}
      </Text>
    </View>
  );
}

export type Option = { value: string; label: string; sub?: string };

const LIST_LIMIT = 30;
const SEARCH_AFTER = 8;

// A closed field that opens to a list of choices, narrowed by typing once the list is long.
export function Picker({
  label,
  options,
  value,
  onChange,
  error,
  empty,
}: {
  label: string;
  options: Option[];
  value: string;
  onChange: (value: string) => void;
  error?: string;
  empty?: string;
}) {
  const { colors } = useTheme();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const selected = options.find((option) => option.value === value);
  const needle = query.trim().toLowerCase();
  const shown = options.filter(
    (option) =>
      !needle ||
      `${option.label} ${option.sub ?? ""}`.toLowerCase().includes(needle),
  );
  return (
    <View style={styles.picker}>
      <Text weight="semibold" style={{ fontSize: 15 }}>
        {label}
      </Text>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={`${label}, ${selected ? selected.label : "not chosen"}`}
        accessibilityState={{ expanded: open }}
        onPress={() => setOpen((current) => !current)}
        style={[
          styles.pickerButton,
          {
            borderColor: error ? colors.red : colors.line,
            borderWidth: error ? 2 : 1,
            backgroundColor: colors.surface,
          },
        ]}
      >
        <Text
          numberOfLines={1}
          style={{
            flex: 1,
            fontSize: 18,
            color: selected ? colors.navy : colors.grey,
          }}
        >
          {selected ? selected.label : "Choose"}
        </Text>
        <Text weight="semibold" style={{ fontSize: 14, color: colors.blue }}>
          {open ? "Close" : "Change"}
        </Text>
      </Pressable>
      {open ? (
        <View
          style={[
            styles.list,
            { borderColor: colors.cardLine, backgroundColor: colors.surface },
          ]}
        >
          {options.length > SEARCH_AFTER ? (
            <View style={{ padding: 12 }}>
              <Field
                label={`Search ${label.toLowerCase()}`}
                value={query}
                onChangeText={setQuery}
                autoCapitalize="none"
                autoCorrect={false}
              />
            </View>
          ) : null}
          {shown.length === 0 ? (
            <Text style={{ padding: 16, color: colors.grey }}>
              {options.length === 0
                ? (empty ?? "Nothing to choose from.")
                : "Nothing matches."}
            </Text>
          ) : (
            shown.slice(0, LIST_LIMIT).map((option) => {
              const checked = option.value === value;
              return (
                <Pressable
                  key={option.value}
                  accessibilityRole="radio"
                  accessibilityLabel={
                    option.sub ? `${option.label}, ${option.sub}` : option.label
                  }
                  accessibilityState={{ checked, selected: checked }}
                  onPress={() => {
                    onChange(option.value);
                    setOpen(false);
                    setQuery("");
                  }}
                  style={[
                    styles.choice,
                    { borderTopColor: colors.divider },
                    checked && { backgroundColor: colors.blueTint },
                  ]}
                >
                  <View style={{ flex: 1 }}>
                    <Text weight={checked ? "bold" : "regular"}>
                      {option.label}
                    </Text>
                    {option.sub ? (
                      <Text
                        style={{
                          fontSize: 13,
                          lineHeight: 18,
                          color: colors.grey,
                        }}
                      >
                        {option.sub}
                      </Text>
                    ) : null}
                  </View>
                  {checked ? (
                    <Text
                      weight="semibold"
                      style={{ fontSize: 14, color: colors.blue }}
                    >
                      Chosen
                    </Text>
                  ) : null}
                </Pressable>
              );
            })
          )}
          {shown.length > LIST_LIMIT ? (
            <Text style={{ padding: 12, fontSize: 14, color: colors.grey }}>
              {`Showing ${LIST_LIMIT} of ${shown.length}. Type to narrow the list.`}
            </Text>
          ) : null}
        </View>
      ) : null}
      {error ? (
        <View accessibilityRole="alert" accessibilityLiveRegion="polite">
          <Text style={{ fontSize: 14, lineHeight: 20, color: colors.red }}>
            {error}
          </Text>
        </View>
      ) : null}
    </View>
  );
}

export type EntryActions = {
  onEdit?: (entry: PettyCashEntry) => void;
  onRemove?: (entry: PettyCashEntry) => void;
  onApprove?: (entry: PettyCashEntry) => void;
  onSendBack?: (entry: PettyCashEntry) => void;
};

// One entry. Buttons come from the entry's own flags; nothing here works out who may do what.
export function EntryRow({
  entry,
  formats,
  showHolder,
  showDate,
  busy,
  actions,
}: {
  entry: PettyCashEntry;
  formats: Formatter;
  showHolder?: boolean;
  showDate?: boolean;
  busy?: boolean;
  actions: EntryActions;
}) {
  const { colors } = useTheme();
  const { kes } = formats;
  const title =
    entry.kind === "expense"
      ? [entry.registration, entry.expenseItemName].filter(Boolean).join(", ")
      : entry.kind === "credit"
        ? `${PETTY_CASH_KIND_LABELS.credit}: ${entry.payee ?? ""}`
        : PETTY_CASH_KIND_LABELS.cash;
  const status = entry.status ? PETTY_CASH_STATUS_LABELS[entry.status] : null;
  const detail =
    entry.kind === "expense"
      ? `${unitsText(formats, entry.units)} x ${kes(entry.unitAmount)}`
      : null;
  return (
    <View
      style={[
        styles.row,
        { borderColor: colors.cardLine, backgroundColor: colors.surface },
      ]}
    >
      <View style={{ gap: 4 }}>
        <View style={styles.rowTop}>
          <Text weight="bold" style={{ flex: 1 }}>
            {title}
          </Text>
          <Text weight="bold">{kes(entry.total)}</Text>
        </View>
        {detail ? (
          <Text style={{ fontSize: 14, color: colors.grey }}>{detail}</Text>
        ) : null}
        {showDate ? (
          <Text style={{ fontSize: 14, color: colors.grey }}>
            {formats.formatDateOnly(entry.date)}
          </Text>
        ) : null}
        {showHolder ? (
          <Text style={{ fontSize: 14, color: colors.grey }}>
            {entry.holderName}
          </Text>
        ) : null}
        {entry.note ? (
          <Text style={{ fontSize: 14, color: colors.grey }}>
            {entry.kind === "credit" ? `Reason: ${entry.note}` : entry.note}
          </Text>
        ) : null}
        {entry.kind === "credit" && entry.reimbursable ? (
          <Text style={{ fontSize: 14, color: colors.grey }}>
            To be paid back
          </Text>
        ) : null}
        <View style={styles.chips}>
          {status ? (
            <Chip
              tone={
                entry.status === "approved"
                  ? "ok"
                  : entry.status === "sentBack"
                    ? "bad"
                    : "warn"
              }
            >
              {status}
            </Chip>
          ) : null}
          {entry.aboveLimit ? <Chip tone="warn">Above your limit</Chip> : null}
        </View>
        {entry.status === "sentBack" && entry.sentBackNote ? (
          <Text style={{ fontSize: 14, color: colors.redText }}>
            {`Sent back: ${entry.sentBackNote}`}
          </Text>
        ) : null}
      </View>
      {(entry.canReview || entry.canEdit || entry.canRemove) && (
        <View style={styles.actions}>
          {entry.canReview && actions.onApprove ? (
            <SmallButton
              tone="solid"
              disabled={busy}
              label={`Approve ${title}`}
              onPress={() => actions.onApprove!(entry)}
            >
              Approve
            </SmallButton>
          ) : null}
          {entry.canReview && actions.onSendBack ? (
            <SmallButton
              disabled={busy}
              label={`Send back ${title}`}
              onPress={() => actions.onSendBack!(entry)}
            >
              Send back
            </SmallButton>
          ) : null}
          {entry.canEdit && actions.onEdit ? (
            <SmallButton
              disabled={busy}
              label={`Edit ${title}`}
              onPress={() => actions.onEdit!(entry)}
            >
              Edit
            </SmallButton>
          ) : null}
          {entry.canRemove && actions.onRemove ? (
            <SmallButton
              tone="danger"
              disabled={busy}
              label={`Remove ${title}`}
              onPress={() => actions.onRemove!(entry)}
            >
              Remove
            </SmallButton>
          ) : null}
        </View>
      )}
    </View>
  );
}

function Chip({
  tone,
  children,
}: {
  tone: "ok" | "warn" | "bad";
  children: string;
}) {
  const { colors } = useTheme();
  const palette =
    tone === "ok"
      ? { bg: colors.greenBg, fg: colors.green }
      : tone === "bad"
        ? { bg: colors.redBg, fg: colors.redText }
        : { bg: colors.amberBg, fg: colors.amberText };
  return (
    <View style={[styles.chip, { backgroundColor: palette.bg }]}>
      <Text
        weight="bold"
        style={{ fontSize: 13, lineHeight: 18, color: palette.fg }}
      >
        {children}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  notice: {
    flexDirection: "row",
    gap: 10,
    alignItems: "flex-start",
    paddingVertical: 12,
    paddingHorizontal: 14,
    borderRadius: 12,
    borderWidth: 1,
  },
  small: {
    minHeight: 44,
    minWidth: 44,
    paddingHorizontal: 14,
    borderWidth: 2,
    borderRadius: 999,
    alignItems: "center",
    justifyContent: "center",
  },
  stepper: { flexDirection: "row", alignItems: "center", gap: 12 },
  stat: {
    flexBasis: "47%",
    flexGrow: 1,
    borderWidth: 1,
    borderRadius: 14,
    padding: 14,
    gap: 2,
  },
  picker: { gap: 8 },
  pickerButton: {
    minHeight: 56,
    paddingHorizontal: 16,
    borderRadius: 12,
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
  },
  list: { borderWidth: 1, borderRadius: 12, overflow: "hidden" },
  choice: {
    minHeight: 52,
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderTopWidth: 1,
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
  },
  row: { borderWidth: 1, borderRadius: 14, padding: 16, gap: 12 },
  rowTop: { flexDirection: "row", gap: 12, alignItems: "flex-start" },
  chips: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  chip: {
    alignSelf: "flex-start",
    paddingVertical: 2,
    paddingHorizontal: 10,
    borderRadius: 999,
  },
  actions: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
});
