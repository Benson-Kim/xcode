"use client";

import { useState, type FormEvent } from "react";

import {
  PETTY_CASH_NOTE_LIMIT,
  PETTY_CASH_PAYEE_LIMIT,
  PETTY_CASH_UNITS_ERROR,
  parsePettyCashAmount,
  parsePettyCashUnits,
  pettyCashTotal,
  type PettyCashEntry,
  type PettyCashHolder,
  type PettyCashKind,
  type PettyCashOptions,
  type PettyCashPermissions,
  type PettyCashSaved,
  type SavePettyCashEntry,
} from "@xcode/shared/pettyCash";

import { useResource } from "../../lib/data";
import { useFormats } from "../../lib/formats";
import {
  Banner,
  Button,
  Choice,
  Dialog,
  ErrorSummary,
  Field,
  Grid2,
  SearchSelect,
  TextInput,
} from "../ui";
import { AmountInput } from "./AmountInput";
import { DialogFooter } from "./DialogFooter";
import { itemOptions } from "./itemOptions";
import {
  ENTRIES_PATH,
  entryPath,
  newEntryId,
  optionsPath,
  sendJson,
} from "./request";
import { useDialogAction } from "./useDialogAction";

export type EntryDialogState = { kind: PettyCashKind; entry?: PettyCashEntry };

type Errors = Partial<
  Record<
    | "date"
    | "units"
    | "amount"
    | "vehicle"
    | "item"
    | "payee"
    | "note"
    | "holder",
    string
  >
>;

const TITLES: Record<PettyCashKind, [string, string]> = {
  expense: ["Add expense", "Edit expense"],
  credit: ["Add credit note", "Edit credit note"],
  cash: ["Add cash", "Edit cash given"],
};

const DATE_SHAPE = /^\d{4}-\d{2}-\d{2}$/;

export function EntryDialog({
  state,
  date,
  businessDate,
  permissions,
  holderId,
  onSaved,
  onConflict,
  onClose,
}: {
  state: EntryDialogState | null;
  date: string;
  businessDate: string;
  permissions: PettyCashPermissions;
  // The manager the list is filtered to, offered first when cash is given.
  holderId: string;
  onSaved: (message: string) => void;
  onConflict: (message: string) => void;
  onClose: () => void;
}) {
  const title = state ? TITLES[state.kind][state.entry ? 1 : 0] : "";
  return (
    <Dialog open={Boolean(state)} title={title} onClose={onClose}>
      {state && (
        <EntryForm
          kind={state.kind}
          entry={state.entry}
          viewedDate={date}
          businessDate={businessDate}
          permissions={permissions}
          holderId={holderId}
          onSaved={onSaved}
          onConflict={onConflict}
          onClose={onClose}
        />
      )}
    </Dialog>
  );
}

function EntryForm({
  kind,
  entry,
  viewedDate,
  businessDate,
  permissions,
  holderId,
  onSaved,
  onConflict,
  onClose,
}: {
  kind: PettyCashKind;
  entry?: PettyCashEntry;
  viewedDate: string;
  businessDate: string;
  permissions: PettyCashPermissions;
  holderId: string;
  onSaved: (message: string) => void;
  onConflict: (message: string) => void;
  onClose: () => void;
}) {
  const formats = useFormats();
  // One id per opened form: a save that is repeated after a lost answer creates nothing twice.
  const [newId] = useState(newEntryId);
  const [date, setDate] = useState(entry?.date ?? viewedDate);
  const [units, setUnits] = useState(String(entry?.units ?? 1));
  const [amount, setAmount] = useState(entry ? String(entry.unitAmount) : "");
  const [vehicleId, setVehicleId] = useState(entry?.vehicleId ?? "");
  const [itemId, setItemId] = useState(entry?.expenseItemId ?? "");
  const [payee, setPayee] = useState(entry?.payee ?? "");
  const [note, setNote] = useState(entry?.note ?? "");
  const [reimbursable, setReimbursable] = useState(
    entry?.reimbursable ?? false,
  );
  const [holder, setHolder] = useState(
    entry?.holderId ??
      (kind === "cash" ? holderId : (permissions.holderId ?? "")),
  );
  const [errors, setErrors] = useState<Errors>({});
  const { saving, error, run } = useDialogAction(onConflict);

  // The choices follow the date on the form; while the next ones load, the last ones stay.
  const options = useResource<PettyCashOptions>(
    DATE_SHAPE.test(date) ? optionsPath(date) : null,
  );
  const [held, setHeld] = useState<PettyCashOptions | undefined>(options.data);
  if (options.data && options.data !== held) setHeld(options.data);
  const choices = options.data ?? held;

  const vehicles = choices?.vehicles ?? [];
  const vehicleChoices =
    entry?.vehicleId &&
    !vehicles.some((vehicle) => vehicle.id === entry.vehicleId)
      ? [
          ...vehicles,
          {
            id: entry.vehicleId,
            registration: entry.registration ?? "",
            companyName: "",
          },
        ]
      : vehicles;
  const items = choices?.items ?? [];
  const itemChoices =
    entry?.expenseItemId &&
    !items.some((item) => item.id === entry.expenseItemId)
      ? [
          ...items,
          {
            id: entry.expenseItemId,
            name: entry.expenseItemName ?? "",
            categoryName: "Other",
            categoryId: "",
            bucket: entry.bucket ?? 2,
          },
        ]
      : items;
  const holders: PettyCashHolder[] = choices?.holders ?? [];
  const holderChoices =
    entry && !holders.some((candidate) => candidate.id === entry.holderId)
      ? [
          ...holders,
          { id: entry.holderId, name: entry.holderName, active: false },
        ]
      : holders;

  const parsed = parsePettyCashAmount(amount);
  const count = parsePettyCashUnits(units);
  const total =
    kind === "expense" && parsed.ok && count !== null
      ? pettyCashTotal(count, parsed.amount)
      : null;
  const pickHolder =
    kind === "cash" || (kind === "credit" && permissions.canIssue);
  const noteLabel = kind === "credit" ? "Reason" : "Note";

  function submit(event: FormEvent) {
    event.preventDefault();
    const found: Errors = {};
    if (!DATE_SHAPE.test(date)) found.date = "Enter the date.";
    else if (date > businessDate)
      found.date = "The date cannot be after today.";
    if (!parsed.ok) found.amount = parsed.error;
    if (kind === "expense") {
      if (count === null) found.units = PETTY_CASH_UNITS_ERROR;
      if (!vehicleId) found.vehicle = "Choose the vehicle.";
      if (!itemId) found.item = "Choose what it was for.";
    }
    if (kind === "credit") {
      if (!payee.trim()) found.payee = "Enter who was paid.";
      if (!note.trim()) found.note = "Say why the money was paid out.";
    }
    if (pickHolder && !holder) found.holder = "Choose the manager.";
    setErrors(found);
    if (!parsed.ok || Object.keys(found).length) return;

    const body: SavePettyCashEntry = {
      ...(entry ? { version: entry.version } : { id: newId }),
      kind,
      date,
      unitAmount: parsed.amount,
      note: note.trim() || null,
    };
    if (kind === "expense")
      Object.assign(body, { vehicleId, expenseItemId: itemId, units: count });
    if (kind === "credit")
      Object.assign(body, { payee: payee.trim(), reimbursable });
    if (pickHolder) body.holderId = holder;

    void run(async () => {
      await (entry
        ? sendJson<PettyCashSaved>("PUT", entryPath(entry.id), body)
        : sendJson<PettyCashSaved>("POST", ENTRIES_PATH, body));
      const waits = kind === "cash" ? "" : " It waits for approval.";
      if (entry) return onSaved(`Saved.${waits}`);
      if (kind === "cash") {
        const name =
          holderChoices.find((candidate) => candidate.id === holder)?.name ??
          "the manager";
        return onSaved(
          parsed.amount < 0
            ? `${formats.kes(-parsed.amount)} taken back from ${name}.`
            : `${formats.kes(parsed.amount)} given to ${name}.`,
        );
      }
      if (kind === "credit")
        return onSaved(
          `Credit note of ${formats.kes(parsed.amount)} to ${payee.trim()} recorded.${waits}`,
        );
      const registration =
        vehicleChoices.find((vehicle) => vehicle.id === vehicleId)
          ?.registration ?? "the vehicle";
      onSaved(
        `${formats.kes(total ?? parsed.amount)} recorded on ${registration}.${waits}`,
      );
    });
  }

  const amountHint =
    total !== null
      ? `Total ${formats.kes(total)}. Use a minus sign for a refund.`
      : "Use a minus sign for money coming back.";

  return (
    <form noValidate onSubmit={submit} className="flex flex-col gap-3.5">
      {options.error && !choices && <Banner>{options.error}</Banner>}
      {kind === "expense" ? (
        <Grid2 narrow>
          <Field id="pc-units" label="Units" error={errors.units}>
            <TextInput
              inputMode="decimal"
              autoComplete="off"
              value={units}
              onChange={(event) => setUnits(event.target.value)}
            />
          </Field>
          <Field
            id="pc-amount"
            label="Amount each"
            hint={amountHint}
            error={errors.amount}
          >
            <AmountInput
              autoFocus
              value={amount}
              onChange={(event) => setAmount(event.target.value)}
            />
          </Field>
        </Grid2>
      ) : (
        <>
          {pickHolder && (
            <Field id="pc-holder" label="Manager" error={errors.holder}>
              <SearchSelect
                options={holderChoices.map((candidate) => ({
                  value: candidate.id,
                  label: `${candidate.name}${candidate.active ? "" : " (not active)"}`,
                }))}
                value={holder}
                placeholder="Choose the manager"
                onChange={setHolder}
              />
            </Field>
          )}
          {kind === "credit" && (
            <Field id="pc-payee" label="Paid to" error={errors.payee}>
              <TextInput
                maxLength={PETTY_CASH_PAYEE_LIMIT}
                autoFocus
                value={payee}
                onChange={(event) => setPayee(event.target.value)}
              />
            </Field>
          )}
          <Field
            id="pc-amount"
            label="Amount"
            hint={amountHint}
            error={errors.amount}
          >
            <AmountInput
              autoFocus={kind === "cash" && !pickHolder}
              value={amount}
              onChange={(event) => setAmount(event.target.value)}
            />
          </Field>
        </>
      )}
      {kind === "expense" && (
        <>
          <Field id="pc-vehicle" label="Vehicle" error={errors.vehicle}>
            <SearchSelect
              options={vehicleChoices.map((vehicle) => ({
                value: vehicle.id,
                label: vehicle.companyName
                  ? `${vehicle.registration}, ${vehicle.companyName}`
                  : vehicle.registration,
              }))}
              value={vehicleId}
              placeholder="Choose the vehicle"
              onChange={setVehicleId}
            />
          </Field>
          <Field id="pc-item" label="What it was for" error={errors.item}>
            <SearchSelect
              options={itemOptions(itemChoices)}
              value={itemId}
              placeholder="Choose the item"
              onChange={setItemId}
            />
          </Field>
        </>
      )}
      <Field id="pc-date" label="Date" error={errors.date}>
        <TextInput
          type="date"
          max={businessDate}
          value={date}
          onChange={(event) => setDate(event.target.value)}
        />
      </Field>
      <Field
        id="pc-note"
        label={noteLabel}
        error={errors.note}
        hint={kind === "credit" ? "Why the money was paid out." : "Optional."}
      >
        <TextInput
          maxLength={PETTY_CASH_NOTE_LIMIT}
          value={note}
          onChange={(event) => setNote(event.target.value)}
        />
      </Field>
      {kind === "credit" && (
        <Choice
          label="The payee should pay this back"
          checked={reimbursable}
          onChange={(event) => setReimbursable(event.target.checked)}
        />
      )}
      <ErrorSummary count={Object.keys(errors).length} />
      {error && <Banner>{error}</Banner>}
      <DialogFooter>
        <Button tone="outline" onClick={onClose}>
          Cancel
        </Button>
        <Button type="submit" tone="ok" disabled={saving}>
          {entry ? "Save" : "Add"}
        </Button>
      </DialogFooter>
    </form>
  );
}
