import { useState } from "react";

import { formatPhone } from "@xcode/shared/format";

import { type LifecycleAction, peopleApi } from "../../lib/endpoints/people";
import type { Person } from "../../lib/types";
import { useToast } from "../ui";
import { type Errors, personPayload, validatePerson } from "./model";
import type { PersonFormState } from "./usePersonForm";

export function usePersonActions({
  person,
  onSaved,
}: {
  person?: Person;
  onSaved: () => void;
}) {
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState<Errors>({});
  const [saveError, setSaveError] = useState("");
  const [confirmRemove, setConfirmRemove] = useState(false);
  const [removeReason, setRemoveReason] = useState("");
  const [removeError, setRemoveError] = useState("");

  async function save(pf: PersonFormState, rolesLoaded: boolean) {
    const { form, permissions } = pf;
    const next = validatePerson(form, {
      rolesLoaded,
      assignableCount: pf.assignable.length,
      permissions,
    });
    setErrors(next);
    setSaveError("");
    if (Object.keys(next).length) return;
    const body = personPayload(form, {
      selectedRole: pf.selectedRole,
      permissions,
      needsLimit: pf.needsLimit,
      version: person?.version,
    });
    const name = `${form.firstName.trim()} ${form.lastName.trim()}`.trim();
    setBusy(true);
    try {
      await peopleApi.save(person, body);
      toast(
        person
          ? `Changes saved for ${name}.`
          : `${name} added. They sign in with ${formatPhone(body.phoneNumber)} and set a PIN with an email code.`,
      );
      onSaved();
    } catch (value) {
      setSaveError((value as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function lifecycle(action: LifecycleAction) {
    if (!person) return;
    if (action === "deactivate" && !confirmRemove)
      return setConfirmRemove(true);
    // Said beside the reason field before asking the server, which needs one too.
    if (action === "deactivate" && !removeReason.trim())
      return setRemoveError("Give a reason for removing access.");
    setRemoveError("");
    setBusy(true);
    try {
      await peopleApi.lifecycle(person.id, action, {
        version: person.version,
        ...(action === "deactivate" ? { reason: removeReason.trim() } : {}),
      });
      toast(
        action === "sign-out"
          ? `${person.firstName} is signed out of every device.`
          : action === "activate"
            ? "Access given back."
            : `Access removed for ${person.firstName} ${person.lastName}.`,
      );
      if (action === "sign-out") setBusy(false);
      else onSaved();
    } catch (value) {
      setSaveError((value as Error).message);
      if (action !== "deactivate") setConfirmRemove(false);
      setBusy(false);
    }
  }

  function changeRemoveReason(value: string) {
    setRemoveReason(value);
    setRemoveError("");
  }

  return {
    busy,
    errors,
    saveError,
    confirmRemove,
    removeReason,
    changeRemoveReason,
    removeError,
    save,
    lifecycle,
  };
}
