"use client";

import { useState, type FormEvent } from "react";

import {
  EXPENSE_REASON_LIMIT,
  expenseEntryPath,
  type ExpenseLedgerRow,
  type ExpenseSaved,
  type RemoveExpense,
} from "@xcode/shared/expenses";

import { useFormats } from "../../lib/formats";
import { sendJson } from "../pettycash/request";
import { useDialogAction } from "../pettycash/useDialogAction";
import {
  Banner,
  Button,
  CardNote,
  Dialog,
  Field,
  FormActions,
  TextInput,
} from "../ui";
import { rowLabel } from "./labels";

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
    <Dialog open={Boolean(row)} title="Remove this expense" onClose={onClose}>
      {row && (
        <RemoveForm
          row={row}
          onDone={onDone}
          onConflict={onConflict}
          onClose={onClose}
        />
      )}
    </Dialog>
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
    <form noValidate onSubmit={submit} className="flex flex-col gap-3.5">
      <CardNote>{rowLabel(formats, row)}</CardNote>
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
      <FormActions>
        <Button type="submit" tone="danger" disabled={saving}>
          Remove
        </Button>
        <Button tone="quiet" onClick={onClose}>
          Cancel
        </Button>
      </FormActions>
    </form>
  );
}
