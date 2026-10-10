"use client";

import { useId, useState, type FormEvent } from "react";

import {
  PETTY_CASH_COMMENT_LIMIT,
  PETTY_CASH_REASON_LIMIT,
  type PettyCashEntry,
  type PettyCashSaved,
  type RemovePettyCashEntry,
  type SendBackPettyCashEntry,
} from "@xcode/shared/pettyCash";

import { useFormats } from "../../lib/formats";
import { RegPlate } from "../revenue/RegPlate";
import { Banner, Button, Field, TextInput } from "../ui";
import { DialogFooter, FormDialog } from "./DialogFooter";
import { entryPath, sendJson } from "./request";
import { useDialogAction } from "./useDialogAction";

type Shared = {
  entry: PettyCashEntry | null;
  onDone: (message: string) => void;
  onConflict: (message: string) => void;
  onClose: () => void;
};

function ReasonForm({
  entry,
  label,
  hint,
  limit,
  missing,
  quick,
  submitLabel,
  tone,
  send,
  onDone,
  onConflict,
  onClose,
}: Omit<Shared, "entry"> & {
  entry: PettyCashEntry;
  label: string;
  hint: string;
  limit: number;
  missing: string;
  // Ready answers that fill the field (.quick).
  quick?: string[];
  submitLabel: string;
  tone: "warn" | "danger";
  send: (text: string) => Promise<string>;
}) {
  const [text, setText] = useState("");
  const [problem, setProblem] = useState("");
  const { saving, error, run } = useDialogAction(onConflict);
  const formId = useId();

  function submit(event: FormEvent) {
    event.preventDefault();
    const value = text.trim();
    if (!value) return setProblem(missing);
    setProblem("");
    void run(async () => onDone(await send(value)));
  }

  return (
    <form
      id={formId}
      noValidate
      onSubmit={submit}
      className="flex flex-col gap-3.5"
    >
      <EntryContext entry={entry} />
      <Field id="pc-reason" label={label} hint={hint} error={problem}>
        <TextInput
          autoFocus
          maxLength={limit}
          autoComplete="off"
          value={text}
          onChange={(event) => setText(event.target.value)}
        />
      </Field>
      {quick && (
        <div className="quick">
          {quick.map((answer) => (
            <button key={answer} type="button" onClick={() => setText(answer)}>
              {answer}
            </button>
          ))}
        </div>
      )}
      {error && <Banner>{error}</Banner>}
      <DialogFooter>
        <Button tone="outline" onClick={onClose}>
          Cancel
        </Button>
        <Button type="submit" form={formId} tone={tone} disabled={saving}>
          {submitLabel}
        </Button>
      </DialogFooter>
    </form>
  );
}

// What the entry is (.mctx): the vehicle and item, or the payee and reason, with its amount.
function EntryContext({ entry }: { entry: PettyCashEntry }) {
  const formats = useFormats();
  const credit = entry.kind === "credit";
  return (
    <div className="mctx">
      <div className="what">
        {entry.registration && <RegPlate>{entry.registration}</RegPlate>}
        <span>
          {entry.kind === "expense"
            ? entry.expenseItemName
            : credit
              ? `Credit note to ${entry.payee ?? "payee"}`
              : `Cash for ${entry.holderName}`}
        </span>
      </div>
      <b className="num">{formats.kes(entry.total)}</b>
    </div>
  );
}

function useEntrySubtitle(entry: PettyCashEntry | null) {
  const formats = useFormats();
  return entry
    ? `${entry.holderName} · ${formats.formatWeekdayDate(entry.date)}`
    : undefined;
}

export function SendBackDialog({ entry, onDone, onConflict, onClose }: Shared) {
  const subtitle = useEntrySubtitle(entry);
  return (
    <FormDialog
      open={Boolean(entry)}
      title="Send back"
      subtitle={subtitle}
      onClose={onClose}
    >
      {entry && (
        <ReasonForm
          entry={entry}
          label="Comment"
          hint="What the manager should fix."
          limit={PETTY_CASH_COMMENT_LIMIT}
          missing="Say what the manager should fix."
          quick={["No receipt", "Not agreed", "Wrong amount", "Wrong vehicle"]}
          submitLabel="Send back"
          tone="warn"
          onDone={onDone}
          onConflict={onConflict}
          onClose={onClose}
          send={async (comment) => {
            const body: SendBackPettyCashEntry = {
              version: entry.version,
              comment,
            };
            await sendJson<PettyCashSaved>(
              "POST",
              entryPath(entry.id, "send-back"),
              body,
            );
            return `Sent back to ${entry.holderName}.`;
          }}
        />
      )}
    </FormDialog>
  );
}

export function RemoveDialog({ entry, onDone, onConflict, onClose }: Shared) {
  const subtitle = useEntrySubtitle(entry);
  return (
    <FormDialog
      open={Boolean(entry)}
      title="Delete this entry"
      subtitle={subtitle}
      onClose={onClose}
    >
      {entry && (
        <ReasonForm
          entry={entry}
          label="Reason for deleting"
          hint="The entry leaves every list and total."
          limit={PETTY_CASH_REASON_LIMIT}
          missing="Say why this entry is being deleted."
          submitLabel="Delete"
          tone="danger"
          onDone={onDone}
          onConflict={onConflict}
          onClose={onClose}
          send={async (reason) => {
            const body: RemovePettyCashEntry = {
              version: entry.version,
              reason,
            };
            await sendJson<PettyCashSaved>(
              "POST",
              entryPath(entry.id, "remove"),
              body,
            );
            return "Entry deleted.";
          }}
        />
      )}
    </FormDialog>
  );
}
