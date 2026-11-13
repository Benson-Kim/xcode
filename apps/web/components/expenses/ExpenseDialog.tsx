"use client";

import { useId, useState, type FormEvent } from "react";

import {
  EXPENSE_ENTRIES_PATH,
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

import { useResource } from "../../lib/data";
import { useFormats } from "../../lib/formats";
import type { MyScope } from "../../lib/types";
import { DateStep } from "../pettycash/DateStep";
import { DialogFooter, FormDialog } from "../pettycash/DialogFooter";
import { itemOptions } from "../pettycash/itemOptions";
import { newEntryId, sendJson } from "../pettycash/request";
import { useDialogAction } from "../pettycash/useDialogAction";
import { useQuickAdds } from "../setup/useQuickAdds";
import { Banner, Button } from "../ui";
import { PurchaseFields, VehicleField } from "./PurchaseFields";
import {
  allocationsOf,
  SplitRows,
  splitState,
  startSplit,
  withRowVehicle,
  type Split,
} from "./SplitRows";
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
    <FormDialog
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
    </FormDialog>
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

// The quantity and unit cost as typed, read: the total, and what is wrong with either.
function figuresOf(units: string, cost: string) {
  const parsedCost = parsePettyCashAmount(cost);
  const count = parsePettyCashUnits(units);
  return {
    parsedCost,
    count,
    total:
      parsedCost.ok && count !== null
        ? expenseTotal(count, parsedCost.amount)
        : null,
    unitsProblem: units.trim() && count === null ? PETTY_CASH_UNITS_ERROR : "",
    costProblem: cost.trim() && !parsedCost.ok ? parsedCost.error : "",
  };
}

const dateProblemOf = (date: string, businessDate: string) =>
  !isDateShape(date)
    ? "Enter the date."
    : date > businessDate
      ? "The date cannot be after today."
      : "";

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
  const [vehicleId, setVehicleId] = useState(entry?.vehicleId ?? "");
  const [splits, setSplits] = useState<Split[] | null>(null);
  const { saving, error, run } = useDialogAction(onConflict);
  const formId = useId();
  // The earliest day this person may still change (the back-dating limit, v2.32): the date control stops there,
  // and a new expense started from an older day opens on it.
  const scope = useResource<MyScope>("setup/access/me");
  const earliest = scope.data?.earliest ?? null;
  const day = !entry && earliest && date < earliest ? earliest : date;

  const {
    vehicleChoices,
    vehicleOptions,
    itemChoices,
    error: choicesError,
    listing,
  } = useExpenseChoices(day, entry);
  const quickAdd = useQuickAdds({
    ...listing,
    onItem: setItemId,
    onVehicle: (id, row) =>
      row === null
        ? setVehicleId(id)
        : setSplits((current) => current && withRowVehicle(current, row, id)),
    date: day,
  });

  const { parsedCost, count, total, unitsProblem, costProblem } = figuresOf(
    units,
    cost,
  );
  const dateProblem = dateProblemOf(day, businessDate);

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

    void run(async () => {
      await saveExpense(entry, newId, {
        date: day,
        vehicleId,
        expenseItemId: itemId,
        units: count,
        unitAmount: parsedCost.amount,
        note: null,
        allocations: allocationsOf(splits, vehicleId, total),
      });
      if (entry) return onSaved("Saved.");
      const picked = vehicleChoices.find((v) => v.id === vehicleId);
      onSaved(
        recordedText(formats, total, splits?.length, picked?.registration),
      );
    });
  }

  return (
    <>
      <form
        id={formId}
        noValidate
        onSubmit={submit}
        className="flex flex-col gap-3.5"
      >
        {choicesError && <Banner>{choicesError}</Banner>}
        <DateStep
          date={day}
          earliest={earliest}
          latest={businessDate}
          onChange={setDate}
        />
        {dateProblem && <div className="ferr">{dateProblem}</div>}
        {!splits && (
          <VehicleField
            vehicleId={vehicleId}
            options={quickAdd.withVehicles(vehicleOptions)}
            onVehicle={setVehicleId}
            onAddVehicle={quickAdd.addVehicle}
            onSplit={entry ? undefined : () => setSplits(startSplit(vehicleId))}
          />
        )}
        <PurchaseFields
          itemId={itemId}
          onItem={setItemId}
          itemOptions={quickAdd.withItems(itemOptions(itemChoices))}
          onAddItem={quickAdd.addItem}
          units={units}
          onUnits={setUnits}
          unitsProblem={unitsProblem}
          cost={cost}
          onCost={setCost}
          costProblem={costProblem}
          total={total}
        />
        {splits && (
          <SplitRows
            splits={splits}
            total={total}
            vehicleOptions={quickAdd.withVehicles(vehicleOptions)}
            onChange={setSplits}
            onAddVehicle={quickAdd.addVehicle}
            onSingle={(id) => {
              setVehicleId(id);
              setSplits(null);
            }}
          />
        )}
        {error && (
          <div className="ferr" role="alert">
            {error}
          </div>
        )}
        <DialogFooter>
          <Button tone="outline" disabled={saving} onClick={onClose}>
            Cancel
          </Button>
          <Button
            type="submit"
            form={formId}
            tone="ok"
            disabled={saving || !valid}
          >
            {splits ? `Save ${splits.length} entries` : "Save"}
          </Button>
        </DialogFooter>
      </form>
      {quickAdd.dialogs}
    </>
  );
}
