"use client";

import { useState } from "react";

import { failureMessage, isConflict } from "./request";

// Runs a save from a dialog: it disables the buttons while it runs, shows a refusal in the dialog, and hands a
// conflict (someone changed the entry first) to the page, which reloads and explains it.
export function useDialogAction(onConflict: (message: string) => void) {
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function run(action: () => Promise<void>) {
    setSaving(true);
    setError("");
    try {
      await action();
    } catch (reason) {
      if (isConflict(reason)) onConflict(failureMessage(reason));
      else setError(failureMessage(reason));
    } finally {
      setSaving(false);
    }
  }

  return { saving, error, setError, run };
}
