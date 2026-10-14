import { useState } from "react";

import { peopleApi } from "../../lib/endpoints/people";
import type { Person } from "../../lib/types";
import { useToast } from "../ui";
import { type Errors, personPayload, validatePerson } from "./model";
import type { PersonFormState } from "./usePersonForm";

export function usePersonActions({
  person,
  today,
  onSaved,
  onChanged,
}: {
  person?: Person;
  today: string;
  onSaved: (name: string, isNew: boolean) => void;
  // A sign-in action acted at once: the pane and the list read the person again.
  onChanged?: () => void;
}) {
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState<Errors>({});
  const [saveError, setSaveError] = useState("");

  async function save(pf: PersonFormState, rolesLoaded: boolean) {
    const { form, permissions } = pf;
    const next = validatePerson(form, {
      rolesLoaded,
      assignableCount: pf.assignable.length,
      permissions,
      today,
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
      onSaved(name, !person);
    } catch (value) {
      setSaveError((value as Error).message);
    } finally {
      setBusy(false);
    }
  }

  // The sign-in actions act at once and are logged; they do not wait for Save.
  async function act(work: () => Promise<unknown>, done: string) {
    setBusy(true);
    setSaveError("");
    try {
      await work();
      toast(done);
      onChanged?.();
    } catch (value) {
      setSaveError((value as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return {
    busy,
    errors,
    saveError,
    save,
    pinReset: () =>
      person &&
      act(
        () => peopleApi.pinReset(person.id),
        `${person.firstName} must set a new PIN at the next sign in`,
      ),
    removeDevice: (deviceId: string) =>
      person &&
      act(() => peopleApi.removeDevice(person.id, deviceId), "Removed"),
    removeAllDevices: () =>
      person &&
      act(
        () =>
          peopleApi.lifecycle(person.id, "sign-out", {
            version: person.version,
          }),
        "Removed",
      ),
  };
}
