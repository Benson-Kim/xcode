import { useRef } from "react";

import type { RevenueCell, RevenueVehicle } from "@xcode/shared/revenue";

import { useFormats } from "../../lib/formats";
import {
  Banner,
  Button,
  CurrencyInput,
  Field,
  FormActions,
  Hint,
  Note,
} from "../ui";
import { entryLabel } from "./capture";
import { ConflictChoice } from "./ConflictChoice";
import { ReasonPicker } from "./ReasonPicker";
import { useCaptureEntry } from "./useCaptureEntry";

export function CaptureForm({
  vehicle,
  cell,
  info,
  canChooseReason,
  onCancel,
  onDone,
  onOpenDay,
  reload,
}: {
  vehicle: RevenueVehicle;
  cell: RevenueCell;
  info: string;
  canChooseReason: boolean;
  onCancel: () => void;
  // Called once the day is settled (saved, or the saved record kept): moves capture on.
  onDone: () => Promise<void>;
  onOpenDay: (date: string) => void;
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
  const { opened, conflict, saving, earlier, error } = entry;
  return (
    <form
      noValidate
      className="flex flex-col gap-3.5"
      onSubmit={(event) => {
        event.preventDefault();
        entry.submit();
      }}
    >
      <p className="m-0 text-[13px] text-grey">{`${formats.formatWeekdayDate(cell.date)}. Expected ${formats.kes(cell.expected)}`}</p>
      {info && <Note>{info}</Note>}
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
          {earlier && <EarlierDay date={earlier} onOpen={onOpenDay} />}
          {error && <Banner>{error}</Banner>}
          <FormActions>
            <Button tone="ok" type="submit" disabled={saving}>
              {saving ? "Saving…" : "Save"}
            </Button>
            <Button tone="quiet" disabled={saving} onClick={onCancel}>
              Cancel
            </Button>
          </FormActions>
        </>
      )}
    </form>
  );
}

function EarlierDay({
  date,
  onOpen,
}: {
  date: string;
  onOpen: (date: string) => void;
}) {
  const formats = useFormats();
  return (
    <>
      <Note>{`Record ${formats.formatWeekdayDate(date)} first.`}</Note>
      <Button
        tone="outline"
        className="self-start"
        onClick={() => onOpen(date)}
      >
        {`Open ${formats.formatWeekdayDate(date)}`}
      </Button>
    </>
  );
}
