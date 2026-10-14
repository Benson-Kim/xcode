import { useId, useRef } from "react";

import { shiftDate } from "@xcode/shared/dates";
import {
  REVENUE_REASONS,
  type RevenueCell,
  type RevenueVehicle,
} from "@xcode/shared/revenue";

import { useFormats } from "../../lib/formats";
import { DialogFooter } from "../pettycash/DialogFooter";
import { Banner, Button, CurrencyInput } from "../ui";
import { ConflictChoice } from "./ConflictChoice";
import { useCaptureEntry } from "./useCaptureEntry";

// Revenue for one vehicle on one day (v2.30): the date first, as previous, date, next; the day's own target; the
// amount; and the reason, shown only while the amount is below the threshold. Cancel and Save.
export function CaptureForm({
  vehicle,
  cell,
  today,
  earliest,
  threshold,
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
  threshold: number;
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
    threshold,
    amountRef,
    onDone,
    reload,
  });
  const { conflict, saving, error } = entry;
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
      <div className="mctx">
        <div className="what">
          <span>Day target</span>
        </div>
        <b className="num">{formats.kes(cell.expected)}</b>
      </div>
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
          {entry.belowThreshold && (
            <div className="f">
              <span className="flab">Reason</span>
              <div className="pills" role="group" aria-label="Reason">
                {REVENUE_REASONS.map((item) => (
                  <button
                    key={item}
                    type="button"
                    aria-pressed={entry.reason === item}
                    onClick={() => entry.choose(item)}
                  >
                    {item}
                  </button>
                ))}
              </div>
            </div>
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
