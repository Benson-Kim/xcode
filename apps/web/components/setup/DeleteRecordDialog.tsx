"use client";

import { useState } from "react";

import { Banner, Button, Dialog, useToast } from "../ui";

// A setup record to delete: what kind it is, in words ("main category", "vehicle"), its name, and the call. `rule`
// says when it can be deleted, if not "while nothing uses it".
export type DeleteTarget = {
  noun: string;
  name: string;
  remove: () => Promise<unknown>;
  rule?: string;
};

// Asks before deleting a setup record added by mistake. The API deletes only a record nothing uses; when something
// does, its refusal says what to do instead and stays in the dialog.
export function useDeleteRecord(onDeleted: () => void) {
  const [target, setTarget] = useState<DeleteTarget | null>(null);
  const toast = useToast();
  const dialog = target && (
    <DeleteRecordDialog
      key={`${target.noun}:${target.name}`}
      target={target}
      onClose={() => setTarget(null)}
      onDeleted={() => {
        toast(`${target.name} deleted.`);
        setTarget(null);
        onDeleted();
      }}
    />
  );
  return { ask: setTarget, dialog };
}

function DeleteRecordDialog({
  target,
  onClose,
  onDeleted,
}: {
  target: DeleteTarget;
  onClose: () => void;
  onDeleted: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function confirm() {
    setBusy(true);
    setError("");
    try {
      await target.remove();
      onDeleted();
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
      title={`Delete ${target.noun}`}
      subtitle={target.name}
      busy={busy}
      onClose={onClose}
      footer={
        <>
          <Button tone="outline" disabled={busy} onClick={onClose}>
            Cancel
          </Button>
          <Button tone="danger" disabled={busy} onClick={() => void confirm()}>
            Delete
          </Button>
        </>
      }
    >
      <p>
        Delete {target.name}? This cannot be undone.{" "}
        {target.rule ?? "It can be deleted only while nothing uses it."}
      </p>
      {error && <Banner>{error}</Banner>}
    </Dialog>
  );
}
