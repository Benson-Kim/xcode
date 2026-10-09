import { useEffect, useRef, useState, type RefObject } from "react";

import {
  type RevenueCell,
  type RevenueReason,
  type RevenueVehicle,
} from "@xcode/shared/revenue";

import { ApiError } from "../../lib/data";
import { revenueApi } from "../../lib/endpoints/revenue";
import { isReason, readEntry } from "./capture";

type Conflict = { message: string; current: RevenueCell };

type Entry = {
  vehicle: RevenueVehicle;
  cell: RevenueCell;
  canChooseReason: boolean;
  amountRef: RefObject<HTMLInputElement | null>;
  noteRef: RefObject<HTMLInputElement | null>;
  onDone: () => Promise<void>;
  // Reads the day again, for a conflict that came without the saved record.
  reload: () => Promise<RevenueCell | undefined>;
};

// One day's entry: what was typed or picked, saving it, and the conflict a save can come back with.
export function useCaptureEntry({
  vehicle,
  cell,
  canChooseReason,
  amountRef,
  noteRef,
  onDone,
  reload,
}: Entry) {
  // The record as it was when the day opened. A grid reload can bring a newer one, but saving over what the person
  // never saw must come back as a conflict, so its version is the one sent.
  const [opened] = useState(cell);
  const [amount, setAmount] = useState(
    opened.amount === null ? "" : String(opened.amount),
  );
  const [reason, setReason] = useState<RevenueReason | "">(
    isReason(opened.reason) ? opened.reason : "",
  );
  const [note, setNote] = useState(opened.note ?? "");
  const [error, setError] = useState("");
  const [conflict, setConflict] = useState<Conflict | null>(null);
  const [saving, setSaving] = useState(false);
  // Blocks a second save (Enter, or a quick second click) while one is on its way, before the disabled button renders.
  const busy = useRef(false);
  useEntryFocus(opened.reason === "Other", amountRef, noteRef);

  const entry = () => readEntry({ amount, reason, note, canChooseReason });

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
      await onDone();
    });
  }

  function choose(item: RevenueReason) {
    setReason((current) => (current === item ? "" : item));
    setAmount("");
    setError("");
  }

  return {
    opened,
    amount,
    reason,
    note,
    error,
    conflict,
    saving,
    mine: entry(),
    submit: () => save(opened.version ?? null),
    replace: (version: number | null) => save(version),
    keepSaved: () => void settle(onDone),
    choose,
    typeAmount: (value: string) => {
      setAmount(value);
      setError("");
      if (value) setReason("");
    },
    typeNote: (value: string) => {
      setNote(value);
      setError("");
    },
  };
}

// After the dialog has opened (which focuses its first control), put the cursor where the entry goes.
function useEntryFocus(
  onNote: boolean,
  amountRef: RefObject<HTMLInputElement | null>,
  noteRef: RefObject<HTMLInputElement | null>,
) {
  const opensOnNote = useRef(onNote);
  useEffect(() => {
    const timer = setTimeout(
      () => (opensOnNote.current ? noteRef : amountRef).current?.focus(),
      0,
    );
    return () => clearTimeout(timer);
  }, [amountRef, noteRef]);
}
