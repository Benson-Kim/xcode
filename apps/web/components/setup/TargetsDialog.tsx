"use client";

import { useState } from "react";

import { shiftDate, startOfWeek } from "@xcode/shared/dates";
import { vehicleLabel } from "@xcode/shared/revenue";

import { useResource } from "../../lib/data";
import { vehiclesApi, vehicleTargetsPath } from "../../lib/endpoints/vehicles";
import { useFormats } from "../../lib/formats";
import { Banner, Button, Dialog, ErrorText, RowAction, useToast } from "../ui";
import {
  DayTargetGrid,
  hasEveryTarget,
  sameTargets,
  targetFigures,
  targetsToText,
} from "./DayTargets";
import type { TargetSet, Vehicle } from "./shared";

const WEEK = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

// The design's wider pop up for the target history (dialog.tg).
const TARGETS_SIZE = "tg";

function setInForce(sets: TargetSet[] | undefined, date: string) {
  let found: TargetSet | undefined;
  for (const set of sets ?? [])
    if (set.startsOn <= date && (!found || set.startsOn > found.startsOn))
      found = set;
  return found;
}

export function TargetsDialog({
  vehicle,
  today,
  onClose,
  onChanged,
}: {
  vehicle: Vehicle;
  today: string;
  onClose: () => void;
  onChanged: () => void;
}) {
  const toast = useToast();
  const { formatDateOnly, formatWeekdayDate } = useFormats();
  const sets = useResource<TargetSet[]>(vehicleTargetsPath(vehicle.id));
  const opensOn = shiftDate(startOfWeek(today, 1), 7);
  const [startsOn, setStartsOn] = useState(opensOn);
  const [typed, setTyped] = useState<string[] | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const values = typed ?? targetsToText(setInForce(sets.data, opensOn)?.days);

  async function save() {
    const days = targetFigures(values);
    if (startsOn < today)
      return setError("A target cannot start before today.");
    if (!hasEveryTarget(values))
      return setError("Enter the target for every day.");
    const current = setInForce(sets.data, startsOn);
    if (current && sameTargets(current.days, days))
      return setError(
        `This is the target already set for ${formatDateOnly(startsOn)}.`,
      );
    setBusy(true);
    setError("");
    try {
      await vehiclesApi.saveTarget(vehicle.id, { startsOn, days });
      toast(`Target saved, from ${formatDateOnly(startsOn)}`);
      sets.reload();
      onChanged();
      onClose();
    } catch (value) {
      setError((value as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function remove(set: TargetSet) {
    setBusy(true);
    setError("");
    try {
      await vehiclesApi.removeTarget(set.id);
      toast("Removed");
      sets.reload();
      onChanged();
    } catch (value) {
      setError((value as Error).message);
    } finally {
      setBusy(false);
    }
  }

  function moveDate(days: number) {
    setStartsOn(shiftDate(startsOn, days));
    setError("");
  }

  return (
    <Dialog
      open
      size={TARGETS_SIZE}
      title="Targets"
      subtitle={vehicleLabel(vehicle)}
      onClose={onClose}
      footer={
        <>
          <Button tone="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" form="targets-form" tone="ok" disabled={busy}>
            Save target
          </Button>
        </>
      }
    >
      <form
        id="targets-form"
        className="contents"
        onSubmit={(event) => {
          event.preventDefault();
          void save();
        }}
      >
        <div className="f">
          <span className="flab">New target starts</span>
          <div className="mstep">
            <div className="step day">
              <button
                type="button"
                aria-label="Previous day"
                disabled={startsOn <= today}
                onClick={() => moveDate(-1)}
              >
                ‹
              </button>
              <span className="d" aria-live="polite">
                {formatWeekdayDate(startsOn)}
              </span>
              <button
                type="button"
                aria-label="Next day"
                onClick={() => moveDate(1)}
              >
                ›
              </button>
            </div>
          </div>
        </div>
        <DayTargetGrid
          idPrefix="target-day"
          values={values}
          onChange={(next) => {
            setTyped(next);
            setError("");
          }}
        />
        {error && <ErrorText>{error}</ErrorText>}
      </form>
      {sets.error ? (
        <Banner>{sets.error}</Banner>
      ) : sets.loading ? (
        <p role="status" className="hint">
          Loading targets
        </p>
      ) : (
        <TargetHistory
          sets={sets.data ?? []}
          busy={busy}
          onRemove={(set) => void remove(set)}
        />
      )}
    </Dialog>
  );
}

function TargetHistory({
  sets,
  busy,
  onRemove,
}: {
  sets: TargetSet[];
  busy: boolean;
  onRemove: (set: TargetSet) => void;
}) {
  const { formatDateOnly, formatNumber } = useFormats();
  return (
    <div className="tbl">
      <div className="scroll">
        <table className="tgh">
          <thead>
            <tr>
              <th scope="col">From</th>
              {WEEK.map((day) => (
                <th key={day} scope="col" className="r">
                  {day}
                </th>
              ))}
              <th scope="col" className="r">
                Week
              </th>
              <th scope="col">
                <span className="sr-only">Status</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {sets.map((set) => (
              <tr key={set.id}>
                <td className="nw">{formatDateOnly(set.startsOn)}</td>
                {set.days.map((figure, index) => (
                  <td key={WEEK[index]} className="r">
                    {formatNumber(figure)}
                  </td>
                ))}
                <td className="r tot">{formatNumber(set.weekTotal)}</td>
                <td className="r nw">
                  {set.inForce ? (
                    <span className="chip ok">Now</span>
                  ) : set.canRemove ? (
                    <RowAction
                      tone="bad"
                      disabled={busy}
                      aria-label={`Remove the target from ${formatDateOnly(set.startsOn)}`}
                      onClick={() => onRemove(set)}
                    >
                      Remove
                    </RowAction>
                  ) : null}
                </td>
              </tr>
            ))}
            {!sets.length && (
              <tr>
                <td colSpan={WEEK.length + 3} className="empty">
                  No targets yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
