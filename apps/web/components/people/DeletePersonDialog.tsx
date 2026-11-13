import { useState } from "react";

import { ApiError } from "../../lib/data";
import { peopleApi } from "../../lib/endpoints/people";
import type { Person } from "../../lib/types";
import { Banner, Button, Dialog, useToast } from "../ui";
import { personStatus } from "./model";

export type InsteadAction = "block" | "erase";

// Delete a person added by mistake: permanent, and only while they have no records. The server refuses someone
// with records (409, its detail says why); the dialog then offers Block, or Erase for someone already blocked.
export function DeletePersonDialog({
  person,
  onDone,
  onClose,
  onInstead,
}: {
  person: Person;
  onDone: () => void;
  onClose: () => void;
  onInstead: (action: InsteadAction) => void;
}) {
  const toast = useToast();
  const name = `${person.firstName} ${person.lastName}`;
  const instead: InsteadAction =
    personStatus(person) === "blocked" ? "erase" : "block";
  const [error, setError] = useState("");
  const [inUse, setInUse] = useState(false);
  const [busy, setBusy] = useState(false);

  async function act() {
    setBusy(true);
    setError("");
    try {
      await peopleApi.remove(person.id);
      toast(`${name} deleted`);
      onDone();
    } catch (value) {
      setInUse(value instanceof ApiError && value.status === 409);
      setError((value as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog
      open
      size="sm"
      title="Delete person"
      subtitle={name}
      busy={busy}
      onClose={onClose}
      footer={
        <>
          <Button tone="outline" disabled={busy} onClick={onClose}>
            Cancel
          </Button>
          {inUse ? (
            <Button tone="danger" onClick={() => onInstead(instead)}>
              {instead === "block" ? "Block instead" : "Erase instead"}
            </Button>
          ) : (
            <Button tone="danger" disabled={busy} onClick={() => void act()}>
              Delete permanently
            </Button>
          )}
        </>
      }
    >
      <p>
        This cannot be undone. {name} is removed from this organization for
        good. It works only while they have no records: once they have recorded
        anything, block them instead.
      </p>
      {error && <Banner>{error}</Banner>}
    </Dialog>
  );
}
