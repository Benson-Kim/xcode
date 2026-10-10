"use client";

import type { PettyCashEntry } from "@xcode/shared/pettyCash";

import { useFormats } from "../../lib/formats";
import { RowAction, StatusBadge } from "../ui";
import { entryLabel } from "./labels";

export type EntryActions = {
  busyId: string | null;
  onApprove: (entry: PettyCashEntry) => void;
  onSendBack: (entry: PettyCashEntry) => void;
  onEdit: (entry: PettyCashEntry) => void;
  onRemove: (entry: PettyCashEntry) => void;
};

// The buttons the server says this person may use on one entry. The rules themselves are the server's.
export function RowActions({
  entry,
  actions,
}: {
  entry: PettyCashEntry;
  actions: EntryActions;
}) {
  const formats = useFormats();
  const label = entryLabel(formats, entry);
  const busy = actions.busyId === entry.id;
  return (
    <div className="tacts">
      {entry.aboveLimit && (
        <StatusBadge tone="warn">Above your limit</StatusBadge>
      )}
      {entry.canEdit && (
        <RowAction
          disabled={busy}
          aria-label={`Edit ${label}`}
          onClick={() => actions.onEdit(entry)}
        >
          Edit
        </RowAction>
      )}
      {entry.canReview && (
        <RowAction
          tone="warn"
          disabled={busy}
          aria-label={`Send back ${label}`}
          onClick={() => actions.onSendBack(entry)}
        >
          Send back
        </RowAction>
      )}
      {entry.canRemove && (
        <RowAction
          tone="bad"
          disabled={busy}
          aria-label={`Delete ${label}`}
          onClick={() => actions.onRemove(entry)}
        >
          Delete
        </RowAction>
      )}
      {entry.canReview && (
        <RowAction
          tone="ok"
          disabled={busy}
          aria-label={`Approve ${label}`}
          onClick={() => actions.onApprove(entry)}
        >
          Approve
        </RowAction>
      )}
    </div>
  );
}
