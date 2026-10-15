"use client";

import { useId, useState, type FormEvent } from "react";

import {
  PETTY_CASH_COMMENT_LIMIT,
  PETTY_CASH_REASON_LIMIT,
  type PettyCashEntry,
  type PettyCashSaved,
  type SendBackPettyCashEntry,
} from "@xcode/shared/pettyCash";

import { useFormats } from "../../lib/formats";
import { RegPlate } from "../revenue/RegPlate";
import { Banner, Button, Field, TextInput } from "../ui";
import { DialogFooter, FormDialog } from "./DialogFooter";
import { longDay } from "./labels";
import { entryPath, sendJson } from "./request";
import { useDialogAction } from "./useDialogAction";

export type ReasonAction = "sendBack" | "reject" | "reopen" | "remove";
export type ReasonState = { action: ReasonAction; entry: PettyCashEntry };

type Spec = {
  title: string;
  submit: string;
  tone: "warn" | "danger";
  // Ready answers that fill the field (.quick).
  quick: string[];
  // False where the dialog only confirms: deleting an expense before it is approved needs no reason.
  asks: boolean;
  limit: number;
  route: string;
  body: (version: number, reason: string) => unknown;
  done: string;
};

const decision = (version: number, reason: string) => ({ version, reason });

function specFor({ action, entry }: ReasonState): Spec {
  if (action === "sendBack")
    return {
      title: "Send back expense",
      submit: "Send back",
      tone: "warn",
      quick: ["No receipt", "Wrong amount", "Wrong vehicle", "Wrong item"],
      asks: true,
      limit: PETTY_CASH_COMMENT_LIMIT,
      route: "send-back",
      body: (version, comment): SendBackPettyCashEntry => ({
        version,
        comment,
      }),
      done: `Sent back to ${entry.holderName}`,
    };
  if (action === "reject")
    return {
      title: "Reject expense",
      submit: "Reject",
      tone: "danger",
      quick: ["No receipt", "Not agreed", "Wrong amount", "Wrong vehicle"],
      asks: true,
      limit: PETTY_CASH_COMMENT_LIMIT,
      route: "reject",
      body: decision,
      done: "Rejected",
    };
  if (action === "reopen")
    return {
      title: "Reopen expense",
      submit: "Reopen",
      tone: "warn",
      quick: [
        "Wrong amount",
        "Wrong vehicle",
        "Wrong item",
        "Approved by mistake",
      ],
      asks: true,
      limit: PETTY_CASH_COMMENT_LIMIT,
      route: "reopen",
      body: decision,
      done: "Reopened. Waiting for approval.",
    };
  const common = {
    submit: "Delete",
    tone: "danger" as const,
    limit: PETTY_CASH_REASON_LIMIT,
    route: "remove",
    done: "Deleted",
  };
  if (entry.kind !== "expense")
    return {
      ...common,
      title:
        entry.kind === "credit" ? "Delete credit note" : "Delete cash issued",
      quick: ["Entered twice", "Wrong manager", "Wrong amount"],
      asks: true,
      body: decision,
    };
  const approved = entry.status === "approved";
  return {
    ...common,
    title: approved ? "Delete approved expense" : "Delete expense",
    quick: ["Entered twice", "Recorded by mistake"],
    asks: approved,
    body: (version, reason) =>
      reason ? decision(version, reason) : { version },
  };
}

type Shared = {
  onDone: (message: string) => void;
  onConflict: (message: string) => void;
  onClose: () => void;
};

function ReasonForm({
  state,
  spec,
  onDone,
  onConflict,
  onClose,
}: Shared & { state: ReasonState; spec: Spec }) {
  const { entry } = state;
  const [text, setText] = useState("");
  const [problem, setProblem] = useState("");
  const { saving, error, run } = useDialogAction(onConflict);
  const formId = useId();

  function submit(event: FormEvent) {
    event.preventDefault();
    const value = text.trim();
    if (spec.asks && !value) return setProblem("Enter the reason.");
    setProblem("");
    void run(async () => {
      await sendJson<PettyCashSaved>(
        "POST",
        entryPath(entry.id, spec.route),
        spec.body(entry.version, spec.asks ? value : ""),
      );
      onDone(spec.done);
    });
  }

  return (
    <form
      id={formId}
      noValidate
      onSubmit={submit}
      className="flex flex-col gap-3.5"
    >
      <EntryContext entry={entry} />
      {spec.asks && (
        <Field id="pc-reason" label="Reason" error={problem}>
          <TextInput
            autoFocus
            maxLength={spec.limit}
            autoComplete="off"
            value={text}
            onChange={(event) => setText(event.target.value)}
          />
          <div className="quick">
            {spec.quick.map((answer) => (
              <button
                key={answer}
                type="button"
                onClick={() => setText(answer)}
              >
                {answer}
              </button>
            ))}
          </div>
        </Field>
      )}
      {error && <Banner>{error}</Banner>}
      <DialogFooter>
        <Button tone="outline" onClick={onClose}>
          Cancel
        </Button>
        <Button type="submit" form={formId} tone={spec.tone} disabled={saving}>
          {spec.submit}
        </Button>
      </DialogFooter>
    </form>
  );
}

// What the entry is (.mctx): the vehicle and item of an expense, or the kind of cash entry, with its amount.
function EntryContext({ entry }: { entry: PettyCashEntry }) {
  const formats = useFormats();
  return (
    <div className="mctx">
      <div className="what">
        {entry.kind === "expense" ? (
          <>
            {entry.registration && <RegPlate>{entry.registration}</RegPlate>}
            <span>{entry.expenseItemName}</span>
          </>
        ) : (
          <span>
            {entry.kind === "credit"
              ? "Credit note"
              : entry.total < 0
                ? "Cash taken back"
                : "Cash issued"}
          </span>
        )}
      </div>
      <b className="num">{formats.kes(entry.total)}</b>
    </div>
  );
}

// One pop up for the five actions that answer for themselves with a reason: send back, reject, reopen, and deleting an
// expense or a cash entry.
export function ReasonDialog({
  state,
  onDone,
  onConflict,
  onClose,
}: Shared & { state: ReasonState | null }) {
  const formats = useFormats();
  const spec = state ? specFor(state) : null;
  return (
    <FormDialog
      open={Boolean(state)}
      title={spec?.title ?? ""}
      subtitle={
        state
          ? `${state.entry.holderName} · ${longDay(formats, state.entry.date)}`
          : undefined
      }
      onClose={onClose}
    >
      {state && spec && (
        <ReasonForm
          key={`${state.action}:${state.entry.id}`}
          state={state}
          spec={spec}
          onDone={onDone}
          onConflict={onConflict}
          onClose={onClose}
        />
      )}
    </FormDialog>
  );
}
