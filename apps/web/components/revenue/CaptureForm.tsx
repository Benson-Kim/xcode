import { useId, useRef } from "react";

import type { RevenueCell, RevenueVehicle } from "@xcode/shared/revenue";

import { useFormats } from "../../lib/formats";
import { DialogFooter } from "../pettycash/DialogFooter";
import {
  Banner,
  Button,
  CurrencyInput,
  Field,
  Hint,
  LinkButton,
  Note,
} from "../ui";
import { entryLabel, gapHint } from "./capture";
import { ConflictChoice } from "./ConflictChoice";
import { ReasonPicker } from "./ReasonPicker";
import { useCaptureEntry } from "./useCaptureEntry";

export function CaptureForm({
  vehicle,
  cell,
  gap,
  canChooseReason,
  onCancel,
  onDone,
  onOpenGap,
  reload,
}: {
  vehicle: RevenueVehicle;
  cell: RevenueCell;
  // The vehicle's earliest day with no record before this one, mentioned but never required.
  gap: string | null;
  canChooseReason: boolean;
  onCancel: () => void;
  // Called once the day is settled (saved, or the saved record kept): moves capture on.
  onDone: () => Promise<void>;
  onOpenGap: (date: string) => void;
  // Reads the day again, for a conflict that came without the saved record.
  reload: () => Promise<RevenueCell | undefined>;
}) {
  const formats = useFormats();
  const amountRef = useRef<HTMLInputElement>(null);
  const noteRef = useRef<HTMLInputElement>(null);
  const entry = useCaptureEntry({
    vehicle,
    cell,
    canChooseReason,
    amountRef,
    noteRef,
    onDone,
    reload,
  });
  const { opened, conflict, saving, error } = entry;
  const formId = useId();
  return (
    <form
      id={formId}
      noValidate
      className="flex flex-col gap-3.5"
      onSubmit={(event) => {
        event.preventDefault();
        entry.submit();
      }}
    >
      <div className="mctx">
        <span className="what">{`${formats.formatWeekdayDate(cell.date)}. Expected ${formats.kes(cell.expected)}`}</span>
      </div>
      {gap && <GapHint date={gap} onOpen={onOpenGap} />}
      {!canChooseReason && !conflict && opened.reason && (
        <Hint>{`Recorded as ${entryLabel(formats, opened)}. Enter the revenue to replace it.`}</Hint>
      )}
      {conflict ? (
        <ConflictChoice
          message={conflict.message}
          current={conflict.current}
          mine={entry.mine}
          saving={saving}
          onReplace={() => entry.replace(conflict.current.version ?? null)}
          onKeep={entry.keepSaved}
        />
      ) : (
        <>
          <Field
            id="revenue-amount"
            label="Revenue"
            hint="What the vehicle handed in for the day, after the crew settle fuel and their own pay."
          >
            <CurrencyInput
              ref={amountRef}
              value={entry.amount}
              className="h-14! text-2xl!"
              onChange={(event) => entry.typeAmount(event.target.value)}
            />
          </Field>
          {canChooseReason && (
            <ReasonPicker
              reason={entry.reason}
              note={entry.note}
              noteRef={noteRef}
              onChoose={entry.choose}
              onNote={entry.typeNote}
            />
          )}
          {error && <Banner>{error}</Banner>}
          <DialogFooter>
            <Button tone="outline" disabled={saving} onClick={onCancel}>
              Cancel
            </Button>
            <Button tone="ok" type="submit" form={formId} disabled={saving}>
              {saving ? "Saving…" : "Save"}
            </Button>
          </DialogFooter>
        </>
      )}
    </form>
  );
}

// Says the vehicle has an earlier day with no record, and offers to go there. Saving this day never waits for it.
function GapHint({
  date,
  onOpen,
}: {
  date: string;
  onOpen: (date: string) => void;
}) {
  const formats = useFormats();
  return (
    <Note tone="info" className="flex flex-wrap items-center gap-x-3 gap-y-1">
      <span>{gapHint(formats, date)}</span>
      <LinkButton compact onClick={() => onOpen(date)}>
        {`Open ${formats.formatDateOnly(date)}`}
      </LinkButton>
    </Note>
  );
}
