"use client";

import { useState, type FormEvent } from "react";

import {
  PETTY_CASH_COMMENT_LIMIT,
  PETTY_CASH_REASON_LIMIT,
  type PettyCashEntry,
  type PettyCashSaved,
  type RemovePettyCashEntry,
  type SendBackPettyCashEntry,
} from "@xcode/shared/pettyCash";

import { useFormats } from "../../lib/formats";
import {
  Banner,
  Button,
  CardNote,
  Dialog,
  Field,
  FormActions,
  TextInput,
} from "../ui";
import { entryLabel } from "./labels";
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
  submitLabel: string;
  tone: "warn" | "danger";
  send: (text: string) => Promise<string>;
}) {
  const formats = useFormats();
  const [text, setText] = useState("");
  const [problem, setProblem] = useState("");
  const { saving, error, run } = useDialogAction(onConflict);

  function submit(event: FormEvent) {
    event.preventDefault();
    const value = text.trim();
    if (!value) return setProblem(missing);
    setProblem("");
    void run(async () => onDone(await send(value)));
  }

  return (
    <form noValidate onSubmit={submit} className="flex flex-col gap-3.5">
      <CardNote>
        {entryLabel(formats, entry)}, {entry.holderName}
      </CardNote>
      <Field id="pc-reason" label={label} hint={hint} error={problem}>
        <TextInput
          autoFocus
          maxLength={limit}
          autoComplete="off"
          value={text}
          onChange={(event) => setText(event.target.value)}
        />
      </Field>
      {error && <Banner>{error}</Banner>}
      <FormActions>
        <Button type="submit" tone={tone} disabled={saving}>
          {submitLabel}
        </Button>
        <Button tone="quiet" onClick={onClose}>
          Cancel
        </Button>
      </FormActions>
    </form>
  );
}

export function SendBackDialog({ entry, onDone, onConflict, onClose }: Shared) {
  return (
    <Dialog open={Boolean(entry)} title="Send back" onClose={onClose}>
      {entry && (
        <ReasonForm
          entry={entry}
          label="Comment"
          hint="What the manager should fix."
          limit={PETTY_CASH_COMMENT_LIMIT}
          missing="Say what the manager should fix."
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
    </Dialog>
  );
}

export function RemoveDialog({ entry, onDone, onConflict, onClose }: Shared) {
  return (
    <Dialog open={Boolean(entry)} title="Delete this entry" onClose={onClose}>
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
    </Dialog>
  );
}
