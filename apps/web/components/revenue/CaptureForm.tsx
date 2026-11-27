import { useId, useRef } from "react";

import { shiftDate } from "@xcode/shared/dates";
import {
  NOT_FUELED,
  REVENUE_REASONS,
  type RevenueCell,
  type RevenueFuel,
  type RevenueVehicle,
} from "@xcode/shared/revenue";

import { useFormats } from "../../lib/formats";
import { DialogFooter } from "../pettycash/DialogFooter";
import { Banner, Button, CurrencyInput, useDialogBusy } from "../ui";
import { ConflictChoice } from "./ConflictChoice";
import { useCaptureEntry } from "./useCaptureEntry";

// Revenue for one vehicle on one day (v2.30): the date first, as previous, date, next; the day's own target while
// Targets is on (v2.38); the amount; then the reason and fuel tags (v2.37). Cancel and Save.
export function CaptureForm({
  vehicle,
  cell,
  today,
  earliest,
  fuelQuestionFrom,
  showTargets,
  onShiftDay,
  onCancel,
  onDone,
  reload,
}: {
  vehicle: RevenueVehicle;
  cell: RevenueCell;
  today: string;
  // The earliest day this person may still change, or null for no limit.
  earliest: string | null;
  fuelQuestionFrom: number;
  showTargets: boolean;
  onShiftDay: (days: number) => void;
  onCancel: () => void;
  onDone: (wasNew: boolean) => Promise<void>;
  // Reads the day again, for a conflict that came without the saved record.
  reload: () => Promise<RevenueCell | undefined>;
}) {
  const formats = useFormats();
  const amountRef = useRef<HTMLInputElement>(null);
  const entry = useCaptureEntry({
    vehicle,
    cell,
    fuelQuestionFrom,
    amountRef,
    onDone,
    reload,
  });
  const { conflict, saving, error } = entry;
  useDialogBusy(saving);
  const formId = useId();
  const previous = shiftDate(cell.date, -1);
  const noPrevious = earliest !== null && previous < earliest;
  const noNext = cell.date >= today;
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
      <div className="mstep">
        <div className="step day">
          <button
            type="button"
            aria-label="Previous day"
            disabled={noPrevious || saving}
            onClick={() => onShiftDay(-1)}
          >
            ‹
          </button>
          <span className="d">{formats.formatWeekdayDate(cell.date)}</span>
          <button
            type="button"
            aria-label="Next day"
            disabled={noNext || saving}
            onClick={() => onShiftDay(1)}
          >
            ›
          </button>
        </div>
      </div>
      {showTargets && (
        <div className="mctx">
          <div className="what">
            <span>Day target</span>
          </div>
          <b className="num">{formats.kes(cell.expected)}</b>
        </div>
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
          <div className="f">
            <label htmlFor="rvAmt">Revenue, KES</label>
            <CurrencyInput
              ref={amountRef}
              id="rvAmt"
              value={entry.amount}
              onChange={(event) => entry.typeAmount(event.target.value)}
            />
          </div>
          <EntryTags entry={entry} />
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

// Under the amount (v2.37). Below the vehicle's low figure: the four reasons, one required, then a thin divider and
// Not fueled. From the low figure: a Tag row with only Not fueled. From the fuel question amount: the amber Fueled?
// box with Yes and No. A fuel answer is optional and a second tap clears it.
function EntryTags({ entry }: { entry: ReturnType<typeof useCaptureEntry> }) {
  const { asksReason, choice, fuel } = entry;
  const answer = (value: RevenueFuel, label: string) => (
    <button
      type="button"
      aria-pressed={fuel === value}
      onClick={() => entry.chooseFuel(value)}
    >
      {label}
    </button>
  );
  const notFueled = choice === "reasons" || choice === "tag";
  const label = asksReason ? "Reason" : "Tag";
  return (
    <>
      {(asksReason || notFueled) && (
        <div className="f">
          <span className="flab">{label}</span>
          <div className="pills" role="group" aria-label={label}>
            {asksReason &&
              REVENUE_REASONS.map((item) => (
                <button
                  key={item}
                  type="button"
                  aria-pressed={entry.reason === item}
                  onClick={() => entry.choose(item)}
                >
                  {item}
                </button>
              ))}
            {asksReason && notFueled && (
              <span className="tsep" aria-hidden="true" />
            )}
            {notFueled && answer("no", NOT_FUELED)}
          </div>
        </div>
      )}
      {choice === "ask" && (
        <div className="fuelrow ask">
          <span className="fq">Fueled?</span>
          <div className="pills" role="group" aria-label="Fueled">
            {answer("yes", "Yes")}
            {answer("no", "No")}
          </div>
        </div>
      )}
    </>
  );
}
