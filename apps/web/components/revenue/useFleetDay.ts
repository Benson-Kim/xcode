"use client";

import { useEffect, useRef, useState } from "react";

import type { RevenueDay, RevenueReason } from "@xcode/shared/revenue";

import { ApiError } from "../../lib/data";
import { revenueApi } from "../../lib/endpoints/revenue";
import { dayRows, entryOf, type DayEntry, type DayProblem } from "./fleetDay";

type Loaded = { key: string; day?: RevenueDay; error?: string };

const failed = (failure: unknown, fallback: string) =>
  failure instanceof Error ? failure.message : fallback;

// The day as the server has it, read again whenever the dialog opens on a day or company, and after a conflict. The
// day already shown stays up while it is read again, and a late answer for another day is dropped.
function useDayData(date: string | null, companyId: string) {
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [round, setRound] = useState(0);
  const key = date === null ? null : `${date}|${companyId}|${round}`;
  useEffect(() => {
    if (date === null) return;
    const controller = new AbortController();
    const current = `${date}|${companyId}|${round}`;
    revenueApi.fleetDay(date, companyId, controller.signal).then(
      (day) => setLoaded({ key: current, day }),
      (failure: unknown) => {
        if (!controller.signal.aborted)
          setLoaded({
            key: current,
            error: failed(failure, "The day could not be loaded."),
          });
      },
    );
    return () => controller.abort();
  }, [date, companyId, round]);
  const sameDay =
    loaded !== null &&
    date !== null &&
    loaded.key.startsWith(`${date}|${companyId}|`);
  return {
    day: sameDay ? loaded.day : undefined,
    error: loaded?.key === key ? loaded.error : undefined,
    reload: () => setRound((value) => value + 1),
  };
}

// Capture revenue for one day: the rows as typed, and saving the changed ones together.
export function useFleetDay({
  date,
  companyId,
  canChooseReason,
  onSaved,
}: {
  date: string | null;
  companyId: string;
  canChooseReason: boolean;
  onSaved: (date: string, count: number) => void;
}) {
  const data = useDayData(date, companyId);
  const [typed, setTyped] = useState<Record<string, DayEntry>>({});
  const [problems, setProblems] = useState<DayProblem[]>([]);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const busy = useRef(false);
  // A new day starts from what is saved.
  const [opened, setOpened] = useState(date);
  if (opened !== date) {
    setOpened(date);
    setTyped({});
    setProblems([]);
    setError("");
  }

  const entry = (vehicleId: string): DayEntry => {
    const vehicle = data.day?.vehicles.find((item) => item.id === vehicleId);
    return typed[vehicleId] ?? (vehicle ? entryOf(vehicle.day) : blankEntry);
  };
  const change = (vehicleId: string, next: Partial<DayEntry>) => {
    setTyped((current) => ({
      ...current,
      [vehicleId]: { ...entry(vehicleId), ...next },
    }));
    setProblems((current) =>
      current.filter((problem) => problem.vehicleId !== vehicleId),
    );
    setError("");
  };

  async function save() {
    const day = data.day;
    if (!day || date === null || busy.current) return;
    const { rows, problems: found } = dayRows(day, typed, canChooseReason);
    setProblems(found);
    if (found.length) return setError("");
    if (!rows.length)
      return setError(
        "Enter the revenue or a no-earnings reason for at least one vehicle.",
      );
    busy.current = true;
    setSaving(true);
    setError("");
    try {
      await revenueApi.saveFleetDay(date, { rows });
      onSaved(date, rows.length);
    } catch (failure) {
      refuse(failure);
    } finally {
      busy.current = false;
      setSaving(false);
    }
  }

  // A row changed by someone else shows its saved record again, so nothing is saved over what was not seen.
  function refuse(failure: unknown) {
    setError(failed(failure, "The day could not be saved."));
    if (!(failure instanceof ApiError) || failure.status !== 409) return;
    const changed = failure.body.vehicleId;
    if (typeof changed === "string")
      setTyped((current) => {
        const kept = { ...current };
        delete kept[changed];
        return kept;
      });
    data.reload();
  }

  return {
    day: data.day,
    loadError: data.error,
    typed,
    entry,
    problems,
    error,
    saving,
    typeAmount: (vehicleId: string, amount: string) =>
      change(
        vehicleId,
        amount.trim() ? { amount, reason: "", note: "" } : { amount },
      ),
    chooseReason: (vehicleId: string, reason: RevenueReason | "") =>
      change(vehicleId, {
        reason,
        note: reason === "Other" ? entry(vehicleId).note : "",
      }),
    typeNote: (vehicleId: string, note: string) => change(vehicleId, { note }),
    save: () => void save(),
  };
}

const blankEntry: DayEntry = { amount: "", reason: "", note: "" };
