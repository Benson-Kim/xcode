"use client";

import { useState } from "react";

import { targetsOn } from "@xcode/shared/appearance";
import {
  mondayFirstIndex,
  shiftDate,
  startOfNextWeek,
  weekdaysFrom,
} from "@xcode/shared/dates";
import { DEFAULT_LOW_BELOW, vehicleLabel } from "@xcode/shared/revenue";

import { useAppearance } from "../../lib/appearance";
import { useResource } from "../../lib/data";
import { vehiclesApi, vehicleTargetsPath } from "../../lib/endpoints/vehicles";
import { useFormats } from "../../lib/formats";
import { Banner, Button, Dialog, ErrorText, RowAction, useToast } from "../ui";
import {
  DayTargetGrid,
  EMPTY_TARGETS,
  hasEveryTarget,
  LOW_FIGURE_MISSING,
  lowFigure,
  LowRevenueField,
  sameTargets,
  targetFigures,
  targetsToText,
} from "./DayTargets";
import type { TargetSet, Vehicle } from "./shared";

// The design's wider pop up for the target history (dialog.tg).
const TARGETS_SIZE = "tg";

function setInForce(sets: TargetSet[] | undefined, date: string) {
  let found: TargetSet | undefined;
  for (const set of sets ?? [])
    if (set.startsOn <= date && (!found || set.startsOn > found.startsOn))
      found = set;
  return found;
}

const lowOf = (set: TargetSet | undefined) =>
  set?.lowBelow ?? DEFAULT_LOW_BELOW;

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
  const { formatDateOnly, formatWeekdayDate, firstDayOfWeek } = useFormats();
  // With Targets off (v2.38) this is the Low revenue pop up: a start date and the low figure; a save carries the
  // day targets in force on that date unchanged.
  const targets = targetsOn(useAppearance().appearance);
  const sets = useResource<TargetSet[]>(vehicleTargetsPath(vehicle.id));
  // A new set starts with the next week (Sunday, v2.41).
  const opensOn = startOfNextWeek(today, firstDayOfWeek());
  const [startsOn, setStartsOn] = useState(opensOn);
  const [typed, setTyped] = useState<string[] | null>(null);
  const [typedLow, setTypedLow] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const opening = setInForce(sets.data, opensOn);
  const values = typed ?? targetsToText(opening?.days);
  const low = typedLow ?? (sets.data ? String(lowOf(opening)) : "");
  const noun = targets ? "target" : "low revenue figure";

  async function save() {
    if (startsOn < today)
      return setError(`A ${noun} cannot start before today.`);
    if (!sets.data)
      return setError(
        "The targets have not loaded yet. Try again in a moment.",
      );
    if (targets && !hasEveryTarget(values))
      return setError("Enter the target for every day.");
    const lowBelow = lowFigure(low);
    if (lowBelow === null) return setError(LOW_FIGURE_MISSING);
    const current = setInForce(sets.data, startsOn);
    const days = targets
      ? targetFigures(values)
      : (current?.days ?? targetFigures(EMPTY_TARGETS));
    if (
      current &&
      sameTargets(current.days, days) &&
      lowOf(current) === lowBelow
    )
      return setError(
        `This is the ${noun} already set for ${formatDateOnly(startsOn)}.`,
      );
    setBusy(true);
    setError("");
    try {
      await vehiclesApi.saveTarget(vehicle.id, { startsOn, days, lowBelow });
      toast(
        `${targets ? "Target" : "Low revenue figure"} saved, from ${formatDateOnly(startsOn)}`,
      );
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
      title={targets ? "Targets" : "Low revenue"}
      subtitle={vehicleLabel(vehicle)}
      busy={busy}
      onClose={onClose}
      footer={
        <>
          <Button tone="outline" disabled={busy} onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" form="targets-form" tone="ok" disabled={busy}>
            {targets ? "Save target" : "Save"}
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
          <span className="flab">
            {targets ? "New target starts" : "Starts"}
          </span>
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
        {targets && (
          <DayTargetGrid
            idPrefix="target-day"
            values={values}
            onChange={(next) => {
              setTyped(next);
              setError("");
            }}
          />
        )}
        <LowRevenueField
          id="target-low"
          value={low}
          onChange={(next) => {
            setTypedLow(next);
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
          targets={targets}
          busy={busy}
          onRemove={(set) => void remove(set)}
        />
      )}
    </Dialog>
  );
}

function TargetHistory({
  sets,
  targets,
  busy,
  onRemove,
}: {
  sets: TargetSet[];
  targets: boolean;
  busy: boolean;
  onRemove: (set: TargetSet) => void;
}) {
  const { formatDateOnly, formatNumber, firstDayOfWeek } = useFormats();
  // The same order as the day figures above it; each set's days are kept Monday first. None while targets are off.
  const week = targets
    ? weekdaysFrom(firstDayOfWeek()).map((day) => ({
        name: day.label.slice(0, 3),
        at: mondayFirstIndex(day.value),
      }))
    : [];
  return (
    <div className="tbl">
      <div className="scroll">
        <table className="tgh">
          <thead>
            <tr>
              <th scope="col">From</th>
              {week.map(({ name }) => (
                <th key={name} scope="col" className="r">
                  {name}
                </th>
              ))}
              {targets && (
                <th scope="col" className="r">
                  Week
                </th>
              )}
              <th scope="col" className="r">
                Low
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
                {week.map(({ name, at }) => (
                  <td key={name} className="r">
                    {formatNumber(set.days[at] ?? 0)}
                  </td>
                ))}
                {targets && (
                  <td className="r tot">{formatNumber(set.weekTotal)}</td>
                )}
                <td className="r">{formatNumber(lowOf(set))}</td>
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
                <td colSpan={week.length + (targets ? 4 : 3)} className="empty">
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
