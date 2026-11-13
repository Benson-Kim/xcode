"use client";

import { useState } from "react";

import { apiRequest } from "../../lib/data";
import { Button, Dialog, Field, TextInput, useToast } from "../ui";

// The new company pop up. taken holds the names already in use; onAdded receives the saved company.
export function AddCompanyDialog({
  initialName = "",
  taken,
  onAdded,
  onClose,
}: {
  initialName?: string;
  taken: string[];
  onAdded: (company: { id: string; name: string }) => void;
  onClose: () => void;
}) {
  const toast = useToast();
  const [name, setName] = useState(initialName);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function add() {
    const trimmed = name.trim();
    if (!trimmed) return setError("Enter the company name.");
    const lower = trimmed.toLowerCase();
    if (taken.some((other) => other.toLowerCase() === lower))
      return setError("This company already exists.");
    setBusy(true);
    try {
      const { id } = await apiRequest<{ id: string }>("setup/companies", {
        method: "POST",
        body: JSON.stringify({ name: trimmed }),
      });
      toast(`${trimmed} added.`);
      onAdded({ id, name: trimmed });
    } catch (value) {
      setError((value as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog
      open
      title="New company"
      size="sm"
      busy={busy}
      onClose={onClose}
      footer={
        <>
          <Button tone="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button
            type="submit"
            form="company-add-form"
            tone="ok"
            disabled={busy}
          >
            Save
          </Button>
        </>
      }
    >
      <form
        id="company-add-form"
        className="contents"
        onSubmit={(event) => {
          event.preventDefault();
          void add();
        }}
      >
        <Field id="new-company" label="Name" error={error}>
          <TextInput
            autoFocus
            value={name}
            onChange={(event) => {
              setName(event.target.value);
              setError("");
            }}
          />
        </Field>
      </form>
    </Dialog>
  );
}
