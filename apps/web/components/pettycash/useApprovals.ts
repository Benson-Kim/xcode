"use client";

import { useState } from "react";

import { plural } from "@xcode/shared/format";
import type {
  PettyCashDayApproved,
  PettyCashEntry,
  PettyCashSaved,
} from "@xcode/shared/pettyCash";

import { useFormats } from "../../lib/formats";
import { useToast } from "../ui";
import { entryLabel } from "./labels";
import { entryPath, failureMessage, isConflict, sendJson } from "./request";

export const BULK = "bulk";

// Approving one entry, the ticked ones or a whole day or period. A refusal is shown as a notice; a conflict also
// reloads, so the person sees what changed. onBulkDone runs after a bulk approve, or its conflict.
export function useApprovals({
  refresh,
  onNotice,
  onBulkDone,
}: {
  refresh: () => void;
  onNotice: (message: string) => void;
  onBulkDone: () => void;
}) {
  const formats = useFormats();
  const toast = useToast();
  const [busyId, setBusyId] = useState<string | null>(null);

  async function approve(entry: PettyCashEntry) {
    setBusyId(entry.id);
    onNotice("");
    try {
      await sendJson<PettyCashSaved>("POST", entryPath(entry.id, "approve"), {
        version: entry.version,
      });
      toast(`Approved ${entryLabel(formats, entry)}.`);
      refresh();
    } catch (reason) {
      onNotice(failureMessage(reason));
      if (isConflict(reason)) refresh();
    } finally {
      setBusyId(null);
    }
  }

  async function approveMany(path: string, body: unknown, nothing: string) {
    setBusyId(BULK);
    onNotice("");
    try {
      const result = await sendJson<PettyCashDayApproved>("POST", path, body);
      const skipped = result.skipped
        ? ` ${plural(result.skipped, "entry was", "entries were")} left for someone else to approve.`
        : "";
      toast(
        result.approved
          ? `Approved ${plural(result.approved, "entry", "entries")}, ${formats.kes(result.total)}.${skipped}`
          : `${nothing}${skipped}`,
      );
      onBulkDone();
      refresh();
    } catch (reason) {
      onNotice(failureMessage(reason));
      if (isConflict(reason)) {
        onBulkDone();
        refresh();
      }
    } finally {
      setBusyId(null);
    }
  }

  return { busyId, approve, approveMany };
}
