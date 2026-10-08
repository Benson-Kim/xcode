import { useState } from "react";

import { plural } from "@xcode/shared/format";

import {
  recurringApi,
  type SaveRecurringRequest,
} from "../../lib/endpoints/recurring";
import { useFormats } from "../../lib/formats";
import type { RecurringItem } from "../setup/shared";
import { useToast } from "../ui";
import {
  type Errors,
  type RecurringInput,
  validateRecurring,
} from "./validate";

type Params = {
  item?: RecurringItem;
  canEdit: boolean;
  locked: boolean;
  onSaved: () => Promise<void> | void;
};

export function useRecurringActions({
  item,
  canEdit,
  locked,
  onSaved,
}: Params) {
  const toast = useToast();
  const formats = useFormats();
  const [errors, setErrors] = useState<Errors>({});
  const [busy, setBusy] = useState(false);
  const [saveError, setSaveError] = useState("");
  const [confirmStop, setConfirmStop] = useState(false);
  const [stopReason, setStopReason] = useState("");
  const [stopError, setStopError] = useState("");

  async function run(request: () => Promise<unknown>, message: string) {
    setBusy(true);
    try {
      await request();
      toast(message);
      await onSaved();
      return true;
    } catch (value) {
      setSaveError((value as Error).message);
      return false;
    } finally {
      setBusy(false);
    }
  }

  async function save(input: RecurringInput, body: SaveRecurringRequest) {
    if (locked || busy) return;
    const next = validateRecurring(input, formats);
    setErrors(next);
    setSaveError("");
    if (Object.keys(next).length) return;
    await run(
      () => recurringApi.save(item, body),
      item
        ? `Changes saved for ${body.name}.`
        : `${body.name} added. It now posts to ${plural(body.allocations.length, "vehicle", "vehicles")}.`,
    );
  }

  async function stop() {
    if (!item || locked || busy) return;
    if (!confirmStop) return setConfirmStop(true);
    if (!stopReason.trim()) {
      setStopError("Give a reason for stopping this item.");
      return;
    }
    setStopError("");
    if (
      !(await run(
        () => recurringApi.stop(item.id, stopReason),
        `${item.name} stopped.`,
      ))
    )
      setConfirmStop(false);
  }

  // A stop dated after the business date has not taken effect, so it can be cancelled and the item keeps posting
  async function cancelStop() {
    if (!item || !canEdit || busy) return;
    await run(
      () => recurringApi.restore(item.id),
      `The stop of ${item.name} was cancelled.`,
    );
  }

  function changeStopReason(value: string) {
    setStopReason(value);
    setStopError("");
  }

  return {
    busy,
    errors,
    saveError,
    confirmStop,
    stopReason,
    changeStopReason,
    stopError,
    save,
    stop,
    cancelStop,
  };
}
