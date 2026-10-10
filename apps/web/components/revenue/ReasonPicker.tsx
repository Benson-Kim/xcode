import type { RefObject } from "react";

import {
  REVENUE_NOTE_LIMIT,
  REVENUE_REASONS,
  type RevenueReason,
} from "@xcode/shared/revenue";

import { Field, TextInput } from "../ui";

// The reasons a day can have no revenue, and the note that "Other" asks for.
export function ReasonPicker({
  reason,
  note,
  noteRef,
  onChoose,
  onNote,
}: {
  reason: RevenueReason | "";
  note: string;
  noteRef: RefObject<HTMLInputElement | null>;
  onChoose: (reason: RevenueReason) => void;
  onNote: (note: string) => void;
}) {
  return (
    <>
      <p className="m-0 flex items-center gap-3 text-[13px] font-semibold text-slate before:h-px before:flex-1 before:bg-line before:content-[''] after:h-px after:flex-1 after:bg-line after:content-['']">
        or no revenue
      </p>
      <div
        role="group"
        aria-label="No revenue reason"
        className="grid grid-cols-4 gap-2 max-[600px]:grid-cols-2"
      >
        {REVENUE_REASONS.map((item) => (
          <button
            key={item}
            type="button"
            aria-pressed={reason === item}
            onClick={() => onChoose(item)}
            className="min-h-12 rounded-xl border border-line bg-surface text-[15px] font-semibold aria-pressed:border-2 aria-pressed:border-teal aria-pressed:bg-teal-wash aria-pressed:text-teal"
          >
            {item}
          </button>
        ))}
      </div>
      {reason === "Other" && (
        <Field
          id="revenue-note"
          label="What happened"
          hint={`Up to ${REVENUE_NOTE_LIMIT} characters.`}
        >
          <TextInput
            ref={noteRef}
            autoFocus
            maxLength={REVENUE_NOTE_LIMIT}
            value={note}
            onChange={(event) => onNote(event.target.value)}
          />
        </Field>
      )}
    </>
  );
}
