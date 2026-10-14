"use client";

import type { PettyCashEntry } from "@xcode/shared/pettyCash";

import { useFormats } from "../../lib/formats";
import { RowAction, StatusBadge } from "../ui";
import { entryLabel } from "./labels";
import { RowMenu, type RowMenuItem } from "./RowMenu";
import { canApproveEntry, isUndecided, isWaiting } from "./status";

export type EntryActions = {
  busyId: string | null;
  onApprove: (entry: PettyCashEntry) => void;
  onSendBack: (entry: PettyCashEntry) => void;
  onReject: (entry: PettyCashEntry) => void;
  onReopen: (entry: PettyCashEntry) => void;
  onEdit: (entry: PettyCashEntry) => void;
  onRemove: (entry: PettyCashEntry) => void;
};

// The less used actions of an expense row, in the design's order: send back, reject, delete.
function lessUsed(entry: PettyCashEntry, actions: EntryActions) {
  const items: RowMenuItem[] = [];
  if (entry.canSendBack && isWaiting(entry))
    items.push({
      label: "Send back",
      onSelect: () => actions.onSendBack(entry),
    });
  if (entry.canReject && isUndecided(entry))
    items.push({
      label: "Reject",
      tone: "bad",
      onSelect: () => actions.onReject(entry),
    });
  if (entry.canRemove)
    items.push({
      label: "Delete",
      tone: "bad",
      onSelect: () => actions.onRemove(entry),
    });
  return items;
}

// The buttons the server says this person may use on one entry. The rules themselves are the server's. Edit and
// Approve stay buttons, Reopen shows on a decided expense, and send back, reject and delete show as one button when
// only one applies, otherwise under More.
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
  const more = lessUsed(entry, actions);
  const [single] = more;
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
      {entry.canReopen && (
        <RowAction
          tone="warn"
          disabled={busy}
          aria-label={`Reopen ${label}`}
          onClick={() => actions.onReopen(entry)}
        >
          Reopen
        </RowAction>
      )}
      {more.length === 1 && (
        <RowAction
          tone={single.tone}
          disabled={busy}
          aria-label={`${single.label} ${label}`}
          onClick={single.onSelect}
        >
          {single.label}
        </RowAction>
      )}
      {more.length > 1 && (
        <RowMenu label={label} items={more} disabled={busy} />
      )}
      {canApproveEntry(entry) && (
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
