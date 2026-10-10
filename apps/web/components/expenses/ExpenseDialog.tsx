"use client";

import { useState, type FormEvent } from "react";

import {
  EXPENSE_ENTRIES_PATH,
  EXPENSE_NOTE_LIMIT,
  expenseEntryPath,
  expenseTotal,
  type ChangeExpense,
  type ExpenseLedgerRow,
  type ExpenseRecorded,
  type ExpenseSaved,
  type RecordExpense,
} from "@xcode/shared/expenses";
import type { Formatter } from "@xcode/shared/format";
import {
  PETTY_CASH_UNITS_ERROR,
  parsePettyCashAmount,
  parsePettyCashUnits,
} from "@xcode/shared/pettyCash";

import { useFormats } from "../../lib/formats";
import { DialogFooter } from "../pettycash/DialogFooter";
import { itemOptions } from "../pettycash/itemOptions";
import { newEntryId, sendJson } from "../pettycash/request";
import { useDialogAction } from "../pettycash/useDialogAction";
import { Banner, Button, Dialog, Field, TextInput } from "../ui";
import { DateField, PurchaseFields, VehicleField } from "./PurchaseFields";
import { SplitRows, splitState, type Split } from "./SplitRows";
import { isDateShape, useExpenseChoices } from "./useExpenseChoices";

// null is closed, {} a new expense, { entry } a central row being changed.
export type ExpenseDialogState = { entry?: ExpenseLedgerRow } | null;

export function ExpenseDialog({
  state,
  date,
  businessDate,
  onSaved,
  onConflict,
  onClose,
}: {
  state: ExpenseDialogState;
  // The day a new expense opens on.
  date: string;
  businessDate: string;
  onSaved: (message: string) => void;
  onConflict: (message: string) => void;
  onClose: () => void;
}) {
  return (
    <Dialog
      open={Boolean(state)}
      title={state?.entry ? "Edit expense" : "Record expense"}
      subtitle={
        state?.entry
          ? `Recorded by ${state.entry.recordedByName ?? "someone"}`
          : undefined
      }
      onClose={onClose}
    >
      {state && (
        <ExpenseForm
          entry={state.entry}
          startDate={date}
          businessDate={businessDate}
          onSaved={onSaved}
          onConflict={onConflict}
          onClose={onClose}
        />
      )}
    </Dialog>
  );
}

type Fields = Omit<RecordExpense, "id"> & { vehicleId: string };

// A new expense is posted with its client id; a row being changed is put at the version it was read at.
async function saveExpense(
  entry: ExpenseLedgerRow | undefined,
  newId: string,
  { vehicleId, allocations, ...purchase }: Fields,
) {
  if (entry) {
    const body: ChangeExpense = {
      ...purchase,
      vehicleId,
      version: entry.version ?? 0,
    };
    await sendJson<ExpenseSaved>("PUT", expenseEntryPath(entry.id), body);
    return;
  }
  const body: RecordExpense = { id: newId, ...purchase, allocations };
  await sendJson<ExpenseRecorded>("POST", EXPENSE_ENTRIES_PATH, body);
}

function recordedText(
  formats: Formatter,
  total: number,
  rows: number | undefined,
  registration = "the vehicle",
) {
  return rows
    ? `${formats.kes(total)} recorded across ${rows} vehicles.`
    : `${formats.kes(total)} recorded on ${registration}.`;
}

function ExpenseForm({
  entry,
  startDate,
  businessDate,
  onSaved,
  onConflict,
  onClose,
}: {
  entry?: ExpenseLedgerRow;
  startDate: string;
  businessDate: string;
  onSaved: (message: string) => void;
  onConflict: (message: string) => void;
  onClose: () => void;
}) {
  const formats = useFormats();
  // One id per opened form: a save repeated after a lost answer creates nothing twice.
  const [newId] = useState(newEntryId);
  const [date, setDate] = useState(entry?.date ?? startDate);
  const [itemId, setItemId] = useState(entry?.expenseItemId ?? "");
  const [units, setUnits] = useState(String(entry?.units ?? 1));
  const [cost, setCost] = useState(entry ? String(entry.unitAmount) : "");
  const [note, setNote] = useState(entry?.note ?? "");
  const [vehicleId, setVehicleId] = useState(entry?.vehicleId ?? "");
  const [splits, setSplits] = useState<Split[] | null>(null);
  const { saving, error, run } = useDialogAction(onConflict);

  const {
    vehicleChoices,
    vehicleOptions,
    itemChoices,
    error: choicesError,
  } = useExpenseChoices(date, entry);

  const parsedCost = parsePettyCashAmount(cost);
  const count = parsePettyCashUnits(units);
  const total =
    parsedCost.ok && count !== null
      ? expenseTotal(count, parsedCost.amount)
      : null;

  const dateProblem = !isDateShape(date)
    ? "Enter the date."
    : date > businessDate
      ? "The date cannot be after today."
      : "";
  const unitsProblem =
    units.trim() && count === null ? PETTY_CASH_UNITS_ERROR : "";
  const costProblem = cost.trim() && !parsedCost.ok ? parsedCost.error : "";

  const split = splits ? splitState(splits, total) : null;
  const valid =
    !dateProblem &&
    Boolean(itemId) &&
    count !== null &&
    parsedCost.ok &&
    (split ? split.valid : Boolean(vehicleId));

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!valid || !parsedCost.ok || count === null || total === null) return;
    const text = note.trim() || null;

    void run(async () => {
      await saveExpense(entry, newId, {
        date,
        vehicleId,
        expenseItemId: itemId,
        units: count,
        unitAmount: parsedCost.amount,
        note: text,
        allocations: split
          ? splits!.map((row, at) => ({
              vehicleId: row.vehicleId,
              amount: split.amounts[at],
            }))
          : [{ vehicleId, amount: total }],
      });
      if (entry) return onSaved("Saved.");
      const picked = vehicleChoices.find((v) => v.id === vehicleId);
      onSaved(
        recordedText(formats, total, splits?.length, picked?.registration),
      );
    });
  }

  return (
    <form noValidate onSubmit={submit} className="flex flex-col gap-3.5">
      {choicesError && <Banner>{choicesError}</Banner>}
      <DateField
        date={date}
        businessDate={businessDate}
        problem={dateProblem}
        onChange={setDate}
      />
      <PurchaseFields
        itemId={itemId}
        onItem={setItemId}
        itemOptions={itemOptions(itemChoices)}
        units={units}
        onUnits={setUnits}
        unitsProblem={unitsProblem}
        cost={cost}
        onCost={setCost}
        costProblem={costProblem}
        group={entry?.group ?? null}
        total={total}
      />
      <Field id="ex-note" label="Note" hint="Optional.">
        <TextInput
          maxLength={EXPENSE_NOTE_LIMIT}
          value={note}
          onChange={(event) => setNote(event.target.value)}
        />
      </Field>
      {splits ? (
        <SplitRows
          splits={splits}
          total={total}
          vehicleOptions={vehicleOptions}
          onChange={setSplits}
          onSingle={(id) => {
            setVehicleId(id);
            setSplits(null);
          }}
        />
      ) : (
        <VehicleField
          vehicleId={vehicleId}
          options={vehicleOptions}
          onVehicle={setVehicleId}
          onSplit={
            entry
              ? undefined
              : () =>
                  setSplits([
                    { vehicleId, amount: "" },
                    { vehicleId: "", amount: "" },
                  ])
          }
        />
      )}
      {error && <Banner>{error}</Banner>}
      <DialogFooter>
        <Button tone="outline" onClick={onClose}>
          Cancel
        </Button>
        <Button type="submit" tone="ok" disabled={saving || !valid}>
          {splits ? `Save ${splits.length} entries` : "Save"}
        </Button>
      </DialogFooter>
    </form>
  );
}
