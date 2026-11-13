import { useId, useState } from "react";

import { peopleApi } from "../../lib/endpoints/people";
import type { Person } from "../../lib/types";
import { Banner, Button, Dialog, useToast } from "../ui";

// Erase a blocked person's personal details. The API needs the version seen and a typed reason, which stays in the
// change log. It cannot be undone.
export function EraseDialog({
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
  const name = `${person.firstName} ${person.lastName}`;
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function act() {
    if (!reason.trim()) return setError("Enter the reason.");
    setBusy(true);
    setError("");
    try {
      await peopleApi.erase(person.id, {
        version: person.version,
        reason: reason.trim(),
      });
      toast(`${name} erased`);
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
      title="Erase person"
      subtitle={name}
      onClose={onClose}
      footer={
        <>
          <Button tone="outline" disabled={busy} onClick={onClose}>
            Cancel
          </Button>
          <Button tone="danger" type="submit" form={formId} disabled={busy}>
            Erase permanently
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
        <p>
          This cannot be undone. {name}&apos;s name, email address and mobile
          number are erased from this organization and its history, and they can
          never sign in again. Money records stay, shown as Former member.
        </p>
        <div className="f">
          <label htmlFor="eraseNote">Reason</label>
          <input
            className="inp"
            id="eraseNote"
            autoFocus
            maxLength={500}
            value={reason}
            onChange={(event) => {
              setReason(event.target.value);
              setError("");
            }}
          />
        </div>
        {error && <Banner>{error}</Banner>}
      </form>
    </Dialog>
  );
}
