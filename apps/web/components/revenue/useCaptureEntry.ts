import { useEffect, useRef, useState, type RefObject } from "react";

import {
  fuelChoice,
  isRecorded,
  keptFuel,
  type RevenueCell,
  type RevenueFuel,
  type RevenueReason,
  type RevenueVehicle,
} from "@xcode/shared/revenue";

import { ApiError } from "../../lib/data";
import { revenueApi } from "../../lib/endpoints/revenue";
import { useFormats } from "../../lib/formats";
import { isReason, lowFigure, readEntry, typedAmount } from "./capture";

type Conflict = { message: string; current: RevenueCell };

type Entry = {
  vehicle: RevenueVehicle;
  cell: RevenueCell;
  // The amount from which the Fueled? question is asked (an organization setting, v2.37).
  fuelQuestionFrom: number;
  amountRef: RefObject<HTMLInputElement | null>;
  // Called once the day is settled (saved, or the saved record kept): moves capture on. wasNew says whether the
  // day had no record when it opened, so a new capture moves to the next vehicle and a correction closes.
  onDone: (wasNew: boolean) => Promise<void>;
  // Reads the day again, for a conflict that came without the saved record.
  reload: () => Promise<RevenueCell | undefined>;
};

// One day's entry: what was typed or picked, saving it, and the conflict a save can come back with.
export function useCaptureEntry({
  vehicle,
  cell,
  fuelQuestionFrom,
  amountRef,
  onDone,
  reload,
}: Entry) {
  const formats = useFormats();
  // The record as it was when the day opened. A grid reload can bring a newer one, but saving over what the person
  // never saw must come back as a conflict, so its version is the one sent.
  const [opened] = useState(cell);
  const wasNew = !isRecorded(opened);
  const [amount, setAmount] = useState(
    opened.amount === null ? "" : String(opened.amount),
  );
  const [reason, setReason] = useState<RevenueReason | "">(
    isReason(opened.reason) ? opened.reason : "",
  );
  const [fuel, setFuel] = useState<RevenueFuel | null>(opened.fuel ?? null);
  const [error, setError] = useState("");
  const [conflict, setConflict] = useState<Conflict | null>(null);
  const [saving, setSaving] = useState(false);
  // Blocks a second save (Enter, or a quick second click) while one is on its way, before the disabled button renders.
  const busy = useRef(false);
  useEntryFocus(amountRef);

  const lowBelow = lowFigure(cell);
  const entry = () =>
    readEntry({ amount, reason, fuel, lowBelow, fuelQuestionFrom, formats });
  // The reason buttons show only while the amount is below the vehicle's low figure for the day.
  const parsed = Number(amount.replace(/[,\s]/g, ""));
  const asksReason = !amount || !Number.isFinite(parsed) || parsed < lowBelow;
  const choice = fuelChoice(typedAmount(amount), lowBelow, fuelQuestionFrom);

  async function settle(work: () => Promise<void>) {
    if (busy.current) return;
    busy.current = true;
    setSaving(true);
    try {
      await work();
    } finally {
      busy.current = false;
      setSaving(false);
    }
  }

  async function refuse(failure: unknown) {
    if (failure instanceof ApiError && failure.status === 409) {
      // Without the saved record (two first captures at once), read the day again before offering the choice.
      const current =
        (failure.body.current as RevenueCell | undefined) ??
        (await reload().catch(() => undefined));
      if (current) setConflict({ message: failure.message, current });
      else setError(failure.message);
    } else {
      setError(
        failure instanceof Error
          ? failure.message
          : "The revenue could not be saved.",
      );
    }
  }

  // A correction sends the version it was read at; a first capture sends null.
  function save(version: number | null) {
    const next = entry();
    if (typeof next === "string") return setError(next);
    void settle(async () => {
      setError("");
      try {
        await revenueApi.saveDay(vehicle.id, cell.date, { ...next, version });
      } catch (failure) {
        return refuse(failure);
      }
      await onDone(wasNew);
    });
  }

  function choose(item: RevenueReason) {
    setReason((current) => (current === item ? "" : item));
    setError("");
  }

  return {
    opened,
    amount,
    reason,
    fuel,
    asksReason,
    choice,
    error,
    conflict,
    saving,
    mine: entry(),
    submit: () => save(opened.version ?? null),
    replace: (version: number | null) => save(version),
    keepSaved: () => void settle(() => onDone(wasNew)),
    choose,
    // A second tap on the chosen answer clears it.
    chooseFuel: (answer: RevenueFuel) => {
      setFuel((current) => (current === answer ? null : answer));
      setError("");
    },
    // Typing below the question amount drops a Yes and keeps a No; clearing the amount drops either.
    typeAmount: (value: string) => {
      setAmount(value);
      setFuel((current) =>
        keptFuel(current, typedAmount(value), fuelQuestionFrom),
      );
      setError("");
    },
  };
}

// After the dialog has opened (which focuses its first control), put the cursor on the amount.
function useEntryFocus(amountRef: RefObject<HTMLInputElement | null>) {
  useEffect(() => {
    const timer = setTimeout(() => {
      const field = amountRef.current;
      field?.focus();
      field?.select();
    }, 0);
    return () => clearTimeout(timer);
  }, [amountRef]);
}
