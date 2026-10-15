import { useId, useState } from "react";

import { peopleApi } from "../../lib/endpoints/people";
import type { Person } from "../../lib/types";
import { Banner, Button, Dialog, useToast } from "../ui";
import { personStatus } from "./model";

// Block a person (the API asks for a reason, kept in the change log), or unblock them. Blocking removes their
// trusted devices and ends their sessions at once.
export function BlockDialog({
  person,
  onDone,
  onClose,
}: {
  person: Person;
  onDone: () => void;
  onClose: () => void;
}) {
  const toast = useToast();
  const formId = useId();
  const blocked = personStatus(person) === "blocked";
  const name = `${person.firstName} ${person.lastName}`;
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function act() {
    if (!blocked && !reason.trim()) return setError("Enter the reason.");
    setBusy(true);
    setError("");
    try {
      await peopleApi.lifecycle(
        person.id,
        blocked ? "activate" : "deactivate",
        {
          version: person.version,
          ...(blocked ? {} : { reason: reason.trim() }),
        },
      );
      toast(`${name} ${blocked ? "unblocked" : "blocked"}`);
      onDone();
    } catch (value) {
      setError((value as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog
      open
      size="sm"
      title={blocked ? "Unblock person" : "Block person"}
      subtitle={name}
      onClose={onClose}
      footer={
        <>
          <Button tone="outline" disabled={busy} onClick={onClose}>
            Cancel
          </Button>
          <Button
            tone={blocked ? "ok" : "danger"}
            type="submit"
            form={formId}
            disabled={busy}
          >
            {blocked ? "Unblock" : "Block"}
          </Button>
        </>
      }
    >
      <form
        id={formId}
        className="contents"
        onSubmit={(event) => {
          event.preventDefault();
          void act();
        }}
      >
        {!blocked && (
          <div className="f">
            <label htmlFor="dNote">Reason</label>
            <input
              className="inp"
              id="dNote"
              autoFocus
              maxLength={500}
              value={reason}
              onChange={(event) => {
                setReason(event.target.value);
                setError("");
              }}
            />
          </div>
        )}
        {error && <Banner>{error}</Banner>}
      </form>
    </Dialog>
  );
}
