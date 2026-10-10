"use client";

import { useId, useState, type FormEvent } from "react";

import {
  EXPENSE_REASON_LIMIT,
  expenseEntryPath,
  type ExpenseLedgerRow,
  type ExpenseSaved,
  type RemoveExpense,
} from "@xcode/shared/expenses";

import { useFormats } from "../../lib/formats";
import { DialogFooter, FormDialog } from "../pettycash/DialogFooter";
import { sendJson } from "../pettycash/request";
import { useDialogAction } from "../pettycash/useDialogAction";
import { RegPlate } from "../revenue/RegPlate";
import { Banner, Button, Field, TextInput } from "../ui";

export function RemoveExpenseDialog({
  row,
  onDone,
  onConflict,
  onClose,
}: {
  row: ExpenseLedgerRow | null;
  onDone: (message: string) => void;
  onConflict: (message: string) => void;
  onClose: () => void;
}) {
  return (
    <FormDialog
      open={Boolean(row)}
      title="Remove this expense"
      subtitle={
        row?.recordedByName ? `Recorded by ${row.recordedByName}` : undefined
      }
      onClose={onClose}
    >
      {row && (
        <RemoveForm
          row={row}
          onDone={onDone}
          onConflict={onConflict}
          onClose={onClose}
        />
      )}
    </FormDialog>
  );
}

function RemoveForm({
  row,
  onDone,
  onConflict,
  onClose,
}: {
  row: ExpenseLedgerRow;
  onDone: (message: string) => void;
  onConflict: (message: string) => void;
  onClose: () => void;
}) {
  const formats = useFormats();
  const [reason, setReason] = useState("");
  const [problem, setProblem] = useState("");
  const { saving, error, run } = useDialogAction(onConflict);
  const formId = useId();

  function submit(event: FormEvent) {
    event.preventDefault();
    const text = reason.trim();
    if (!text) return setProblem("Say why this expense is being removed.");
    setProblem("");
    const body: RemoveExpense = { version: row.version ?? 0, reason: text };
    void run(async () => {
      await sendJson<ExpenseSaved>(
        "POST",
        expenseEntryPath(row.id, "remove"),
        body,
      );
      onDone("Expense removed.");
    });
  }

  return (
    <form
      id={formId}
      noValidate
      onSubmit={submit}
      className="flex flex-col gap-3.5"
    >
      <div className="mctx">
        <div className="what">
          <RegPlate>{row.registration}</RegPlate>
          <span>{row.itemName}</span>
        </div>
        <b className="num">{formats.kes(row.total)}</b>
      </div>
      <Field
        id="ex-reason"
        label="Reason for removing"
        hint="The expense leaves every list and total."
        error={problem}
      >
        <TextInput
          autoFocus
          maxLength={EXPENSE_REASON_LIMIT}
          autoComplete="off"
          value={reason}
          onChange={(event) => setReason(event.target.value)}
        />
      </Field>
      {error && <Banner>{error}</Banner>}
      <DialogFooter>
        <Button tone="outline" onClick={onClose}>
          Cancel
        </Button>
        <Button type="submit" form={formId} tone="danger" disabled={saving}>
          Remove
        </Button>
      </DialogFooter>
    </form>
  );
}
