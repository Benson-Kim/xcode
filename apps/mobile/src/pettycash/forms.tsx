import { useState } from "react";
import { Pressable, StyleSheet, Switch, View } from "react-native";

import {
  PETTY_CASH_COMMENT_LIMIT,
  PETTY_CASH_NOTE_LIMIT,
  PETTY_CASH_PAYEE_LIMIT,
  PETTY_CASH_REASON_LIMIT,
  PETTY_CASH_UNITS_ERROR,
  parsePettyCashAmount,
  parsePettyCashUnits,
  pettyCashTotal,
  type PettyCashEntry,
  type PettyCashOptions,
  type PettyCashPermissions,
  type PettyCashSaved,
  type SavePettyCashEntry,
} from "@xcode/shared/pettyCash";

import { SessionEndedError } from "../lib/api";
import { useFormats } from "../lib/formats";
import { LineSkeleton, SectionTitle } from "../shell/parts";
import { Button, ErrorText, Field, Text, useTheme } from "../ui";
import { newEntryId, send, useLoaded, type Outcome } from "./client";
import { DayStepper, Picker } from "./parts";

type Common = {
  businessDate: string;
  permissions: PettyCashPermissions;
  stamp: number;
  onCancel?: () => void;
  onSaved: (message: string) => void;
  // The entry changed or went away while the form was open: the screen shows the message and reloads.
  onStale: (message: string) => void;
  onSessionEnded: () => void;
};

type EntryFormProps = Common & { entry?: PettyCashEntry; date: string };

// One save at a time. 400 and 403 stay on the form; 409 and 404 hand over to the screen, which reloads.
function useSave(common: Common) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function save(call: () => Promise<Outcome<unknown>>, done: string) {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      const result = await call();
      if (result.ok) common.onSaved(done);
      else if (result.reload) common.onStale(result.message);
      else setError(result.message);
    } catch (reason) {
      if (reason instanceof SessionEndedError) common.onSessionEnded();
      else setError("The request could not be completed.");
    } finally {
      setBusy(false);
    }
  }
  return { busy, error, save };
}

function Footer({
  busy,
  error,
  submit,
  onCancel,
  saveLabel,
}: {
  busy: boolean;
  error: string;
  submit: () => void;
  onCancel?: () => void;
  saveLabel: string;
}) {
  return (
    <View style={{ gap: 12 }}>
      <ErrorText>{error}</ErrorText>
      <Button busy={busy} busyText="Saving…" onPress={submit}>
        {saveLabel}
      </Button>
      {onCancel ? (
        <Button tone="outline" disabled={busy} onPress={onCancel}>
          Cancel
        </Button>
      ) : null}
    </View>
  );
}

function useOptions(date: string, enabled: boolean, common: Common) {
  return useLoaded<PettyCashOptions>(
    enabled ? `setup/pettycash/options?date=${date}` : null,
    common.stamp,
    common.onSessionEnded,
  );
}

function OptionsState({
  loading,
  error,
  retry,
}: {
  loading: boolean;
  error: string;
  retry: () => void;
}) {
  if (loading) return <LineSkeleton lines={2} />;
  if (!error) return null;
  return (
    <View style={{ gap: 8 }}>
      <ErrorText>{error}</ErrorText>
      <Button tone="outline" onPress={retry}>
        Try again
      </Button>
    </View>
  );
}

const clean = (value: string) => value.trim() || null;

// The amount each, shown with its live total when units are known.
function AmountFields({
  units,
  setUnits,
  unitsError,
  amount,
  setAmount,
  amountError,
  label,
}: {
  units?: string;
  setUnits?: (value: string) => void;
  unitsError?: string;
  amount: string;
  setAmount: (value: string) => void;
  amountError: string;
  label: string;
}) {
  const { colors } = useTheme();
  const { kes } = useFormats();
  const parsed = parsePettyCashAmount(amount);
  const count = units === undefined ? 1 : parsePettyCashUnits(units);
  return (
    <>
      {setUnits ? (
        <Field
          label="Units"
          value={units}
          onChangeText={setUnits}
          keyboardType="decimal-pad"
          autoCorrect={false}
          error={unitsError}
        />
      ) : null}
      <Field
        label={label}
        value={amount}
        onChangeText={setAmount}
        keyboardType="numbers-and-punctuation"
        autoCorrect={false}
        error={amountError}
      />
      {setUnits && parsed.ok && count !== null ? (
        <Text
          weight="semibold"
          accessibilityLiveRegion="polite"
          style={{ fontSize: 16, color: colors.navy }}
        >
          {`Total ${kes(pettyCashTotal(count, parsed.amount))}`}
        </Text>
      ) : null}
    </>
  );
}

export function ExpenseForm({ entry, date: start, ...common }: EntryFormProps) {
  const formats = useFormats();
  const [id] = useState(() => entry?.id ?? newEntryId());
  const [date, setDate] = useState(entry?.date ?? start);
  const [vehicleId, setVehicleId] = useState(entry?.vehicleId ?? "");
  const [itemId, setItemId] = useState(entry?.expenseItemId ?? "");
  const [units, setUnits] = useState(entry ? String(entry.units) : "1");
  const [amount, setAmount] = useState(entry ? String(entry.unitAmount) : "");
  const [note, setNote] = useState(entry?.note ?? "");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const options = useOptions(date, true, common);
  const { busy, error, save } = useSave(common);

  const vehicles = (options.data?.vehicles ?? [])
    .filter((vehicle) => vehicle.active || vehicle.id === entry?.vehicleId)
    .map((vehicle) => ({
      value: vehicle.id,
      label: vehicle.registration,
      sub: vehicle.companyName,
    }));
  if (entry?.vehicleId && !vehicles.some((v) => v.value === entry.vehicleId))
    vehicles.push({
      value: entry.vehicleId,
      label: entry.registration ?? "Vehicle",
      sub: "",
    });
  const items = (options.data?.items ?? []).map((item) => ({
    value: item.id,
    label: item.name,
    sub: item.categoryName,
  }));
  if (
    entry?.expenseItemId &&
    !items.some((i) => i.value === entry.expenseItemId)
  )
    items.push({
      value: entry.expenseItemId,
      label: entry.expenseItemName ?? "Item",
      sub: "",
    });

  function submit() {
    const next: Record<string, string> = {};
    if (!vehicles.some((vehicle) => vehicle.value === vehicleId))
      next.vehicle = "Choose a vehicle.";
    if (!items.some((item) => item.value === itemId))
      next.item = "Choose an item.";
    const count = parsePettyCashUnits(units);
    if (count === null) next.units = PETTY_CASH_UNITS_ERROR;
    const parsed = parsePettyCashAmount(amount);
    if (!parsed.ok) next.amount = parsed.error;
    setErrors(next);
    if (Object.keys(next).length || count === null || !parsed.ok) return;
    const body: SavePettyCashEntry = {
      ...(entry ? { version: entry.version } : { id }),
      kind: "expense",
      date,
      vehicleId,
      expenseItemId: itemId,
      units: count,
      unitAmount: parsed.amount,
      note: clean(note),
    };
    void save(
      () =>
        entry
          ? send<PettyCashSaved>("PUT", `entries/${entry.id}`, body)
          : send<PettyCashSaved>("POST", "entries", body),
      entry
        ? "Expense changed. It waits for approval again."
        : "Expense saved. It waits for approval.",
    );
  }

  return (
    <View style={styles.form}>
      <SectionTitle>{entry ? "Edit expense" : "Record expense"}</SectionTitle>
      <DayStepper
        label="Date"
        date={date}
        businessDate={common.businessDate}
        formats={formats}
        onChange={setDate}
      />
      <OptionsState
        loading={options.loading}
        error={options.error}
        retry={options.retry}
      />
      {options.data ? (
        <>
          <Picker
            label="Vehicle"
            options={vehicles}
            value={vehicleId}
            onChange={setVehicleId}
            error={errors.vehicle}
            empty="No vehicles on this day."
          />
          <Picker
            label="Item"
            options={items}
            value={itemId}
            onChange={setItemId}
            error={errors.item}
            empty="No expense items are set up."
          />
        </>
      ) : null}
      <AmountFields
        units={units}
        setUnits={setUnits}
        unitsError={errors.units}
        amount={amount}
        setAmount={setAmount}
        amountError={errors.amount ?? ""}
        label="Amount each"
      />
      <Field
        label="Note (optional)"
        value={note}
        onChangeText={setNote}
        maxLength={PETTY_CASH_NOTE_LIMIT}
      />
      <Footer
        busy={busy}
        error={error}
        submit={submit}
        onCancel={common.onCancel}
        saveLabel="Save expense"
      />
    </View>
  );
}

export function CreditForm({ entry, date: start, ...common }: EntryFormProps) {
  const formats = useFormats();
  const { colors } = useTheme();
  const { permissions } = common;
  const issuer = permissions.canIssue;
  const [id] = useState(() => entry?.id ?? newEntryId());
  const [date, setDate] = useState(entry?.date ?? start);
  const [holderId, setHolderId] = useState(
    entry?.holderId ?? permissions.holderId ?? "",
  );
  const [payee, setPayee] = useState(entry?.payee ?? "");
  const [reason, setReason] = useState(entry?.note ?? "");
  const [amount, setAmount] = useState(entry ? String(entry.unitAmount) : "");
  const [reimbursable, setReimbursable] = useState(
    entry?.reimbursable ?? false,
  );
  const [errors, setErrors] = useState<Record<string, string>>({});
  const options = useOptions(date, issuer, common);
  const { busy, error, save } = useSave(common);

  function submit() {
    const next: Record<string, string> = {};
    if (issuer && !holderId) next.holder = "Choose a manager.";
    if (!payee.trim()) next.payee = "Enter who was paid.";
    if (!reason.trim()) next.reason = "Enter the reason.";
    const parsed = parsePettyCashAmount(amount);
    if (!parsed.ok) next.amount = parsed.error;
    setErrors(next);
    if (Object.keys(next).length || !parsed.ok) return;
    const body: SavePettyCashEntry = {
      ...(entry ? { version: entry.version } : { id }),
      kind: "credit",
      date,
      ...(issuer ? { holderId } : {}),
      payee: payee.trim(),
      note: reason.trim(),
      unitAmount: parsed.amount,
      reimbursable,
    };
    void save(
      () =>
        entry
          ? send<PettyCashSaved>("PUT", `entries/${entry.id}`, body)
          : send<PettyCashSaved>("POST", "entries", body),
      "Credit note saved. It waits for approval.",
    );
  }

  return (
    <View style={styles.form}>
      <SectionTitle>{entry ? "Edit credit note" : "Credit note"}</SectionTitle>
      <DayStepper
        label="Date"
        date={date}
        businessDate={common.businessDate}
        formats={formats}
        onChange={setDate}
      />
      {issuer ? (
        <>
          <OptionsState
            loading={options.loading}
            error={options.error}
            retry={options.retry}
          />
          {options.data ? (
            <Picker
              label="Manager"
              options={options.data.holders.map((holder) => ({
                value: holder.id,
                label: holder.name,
              }))}
              value={holderId}
              onChange={setHolderId}
              error={errors.holder}
            />
          ) : null}
        </>
      ) : null}
      <Field
        label="Paid to"
        value={payee}
        onChangeText={setPayee}
        maxLength={PETTY_CASH_PAYEE_LIMIT}
        error={errors.payee}
      />
      <Field
        label="Reason"
        value={reason}
        onChangeText={setReason}
        maxLength={PETTY_CASH_NOTE_LIMIT}
        error={errors.reason}
      />
      <AmountFields
        amount={amount}
        setAmount={setAmount}
        amountError={errors.amount ?? ""}
        label="Amount"
      />
      <Pressable
        accessibilityRole="switch"
        accessibilityLabel="Money to be paid back"
        accessibilityState={{ checked: reimbursable }}
        onPress={() => setReimbursable((value) => !value)}
        style={styles.switchRow}
      >
        <Text style={{ flex: 1 }}>Money to be paid back</Text>
        <View
          pointerEvents="none"
          importantForAccessibility="no-hide-descendants"
        >
          <Switch
            value={reimbursable}
            trackColor={{ true: colors.blue, false: colors.line }}
          />
        </View>
      </Pressable>
      <Footer
        busy={busy}
        error={error}
        submit={submit}
        onCancel={common.onCancel}
        saveLabel="Save credit note"
      />
    </View>
  );
}

export function CashForm({ entry, date: start, ...common }: EntryFormProps) {
  const formats = useFormats();
  const [id] = useState(() => entry?.id ?? newEntryId());
  const [date, setDate] = useState(entry?.date ?? start);
  const [holderId, setHolderId] = useState(entry?.holderId ?? "");
  const [amount, setAmount] = useState(entry ? String(entry.unitAmount) : "");
  const [note, setNote] = useState(entry?.note ?? "");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const options = useOptions(date, true, common);
  const { busy, error, save } = useSave(common);

  function submit() {
    const next: Record<string, string> = {};
    if (!holderId) next.holder = "Choose a manager.";
    const parsed = parsePettyCashAmount(amount);
    if (!parsed.ok) next.amount = parsed.error;
    setErrors(next);
    if (Object.keys(next).length || !parsed.ok) return;
    const body: SavePettyCashEntry = {
      ...(entry ? { version: entry.version } : { id }),
      kind: "cash",
      holderId,
      date,
      unitAmount: parsed.amount,
      note: clean(note),
    };
    void save(
      () =>
        entry
          ? send<PettyCashSaved>("PUT", `entries/${entry.id}`, body)
          : send<PettyCashSaved>("POST", "entries", body),
      entry ? "Cash entry changed." : "Cash recorded.",
    );
  }

  return (
    <View style={styles.form}>
      <SectionTitle>{entry ? "Edit cash given" : "Give cash"}</SectionTitle>
      <DayStepper
        label="Date"
        date={date}
        businessDate={common.businessDate}
        formats={formats}
        onChange={setDate}
      />
      <OptionsState
        loading={options.loading}
        error={options.error}
        retry={options.retry}
      />
      {options.data ? (
        <Picker
          label="Manager"
          options={options.data.holders.map((holder) => ({
            value: holder.id,
            label: holder.name,
          }))}
          value={holderId}
          onChange={setHolderId}
          error={errors.holder}
        />
      ) : null}
      <AmountFields
        amount={amount}
        setAmount={setAmount}
        amountError={errors.amount ?? ""}
        label="Amount"
      />
      <Field
        label="Note (optional)"
        value={note}
        onChangeText={setNote}
        maxLength={PETTY_CASH_NOTE_LIMIT}
      />
      <Footer
        busy={busy}
        error={error}
        submit={submit}
        onCancel={common.onCancel}
        saveLabel="Save cash"
      />
    </View>
  );
}

// Removing and sending back each need a typed reason before they go.
export function ReasonForm({
  entry,
  mode,
  ...common
}: Common & { entry: PettyCashEntry; mode: "remove" | "sendBack" }) {
  const remove = mode === "remove";
  const [text, setText] = useState("");
  const [problem, setProblem] = useState("");
  const { busy, error, save } = useSave(common);

  function submit() {
    if (!text.trim()) {
      setProblem(
        remove
          ? "Enter the reason for removing it."
          : "Enter a comment for the person who recorded it.",
      );
      return;
    }
    setProblem("");
    void save(
      () =>
        send<PettyCashSaved>(
          "POST",
          `entries/${entry.id}/${remove ? "remove" : "send-back"}`,
          remove
            ? { version: entry.version, reason: text.trim() }
            : { version: entry.version, comment: text.trim() },
        ),
      remove ? "Entry removed." : "Entry sent back.",
    );
  }

  return (
    <View style={styles.form}>
      <SectionTitle>{remove ? "Remove entry" : "Send back"}</SectionTitle>
      <Field
        label={remove ? "Reason for removing" : "Comment"}
        value={text}
        onChangeText={setText}
        multiline
        maxLength={remove ? PETTY_CASH_REASON_LIMIT : PETTY_CASH_COMMENT_LIMIT}
        error={problem}
        style={{ height: 112, paddingTop: 14, textAlignVertical: "top" }}
      />
      <Footer
        busy={busy}
        error={error}
        submit={submit}
        onCancel={common.onCancel}
        saveLabel={remove ? "Remove entry" : "Send back"}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  form: { gap: 16 },
  switchRow: {
    minHeight: 56,
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
  },
});
