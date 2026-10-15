"use client";

import { useMemo } from "react";

import { plural } from "@xcode/shared/format";
import type { PettyCashEntry } from "@xcode/shared/pettyCash";

import { useAppearance } from "../../lib/appearance";
import { useFormats } from "../../lib/formats";
import { RegPlate } from "../revenue/RegPlate";
import { CellNote, DataTable, Td, Tr, type Column } from "../ui";
import { Days } from "./dayGroups";
import { entryLabel, unitsFormat } from "./labels";
import { RowActions, type EntryActions } from "./RowActions";
import { isRejected, isSentBack, isWaiting, statusOf } from "./status";
import { StatusTag } from "./StatusTag";

const SELECT: Column = { label: "Select", hidden: true, width: 38 };

const columns: Column[] = [
  { label: "Vehicle" },
  { label: "Item" },
  { label: "Qty", numeric: true },
  { label: "Unit cost", numeric: true },
  { label: "Total amount", numeric: true },
  { label: "Manager" },
  { label: "Status" },
  { label: "Actions", numeric: true },
];

export type Selection = {
  ids: readonly string[];
  onToggle: (entry: PettyCashEntry) => void;
};

// An expense can be ticked for approval when this person may approve it, it waits (and was not sent back) and it is
// within their limit.
export const selectable = (entry: PettyCashEntry) =>
  entry.canReview && isWaiting(entry) && !entry.aboveLimit;

const counted = (entries: PettyCashEntry[]) =>
  entries
    .filter((entry) => !isRejected(entry))
    .reduce((sum, entry) => sum + entry.total, 0);

// The notes under an item: why it was rejected, what it was sent back for, why it was reopened.
function notesOf(entry: PettyCashEntry) {
  const notes: string[] = [];
  if (entry.note) notes.push(entry.note);
  if (isRejected(entry) && entry.rejectReason) notes.push(entry.rejectReason);
  if (isSentBack(entry) && entry.sentBackNote)
    notes.push(`Sent back, ${entry.sentBackNote}`);
  if ((isWaiting(entry) || isSentBack(entry)) && entry.reopenReason)
    notes.push(`Reopened, ${entry.reopenReason}`);
  return notes;
}

// Expenses of the days shown, under a row for each day when there are several. With a selection, the ones waiting for
// this person to approve have a checkbox. The footer counts every matching entry; it adds them up (less rejected
// ones, which the manager carries) when they are all on this page.
export function EntriesTable({
  entries,
  total,
  days,
  loading,
  failed,
  actions,
  selection,
}: {
  entries: PettyCashEntry[];
  total: number;
  days: boolean;
  loading: boolean;
  failed: boolean;
  actions: EntryActions;
  selection?: Selection;
}) {
  const formats = useFormats();
  const locale = useAppearance().appearance?.formats.locale ?? "en-GB";
  const unitsText = useMemo(() => unitsFormat(locale), [locale]);
  const lead = selection ? 1 : 0;
  return (
    <DataTable
      columns={selection ? [SELECT, ...columns] : columns}
      loading={loading}
      loadingLabel="Loading expenses"
      isEmpty={!entries.length}
      failed={failed}
      emptyMessage={
        days
          ? "Nothing recorded in this period."
          : "Nothing recorded on this day."
      }
      footer={
        <tr>
          <td colSpan={4 + lead}>
            Expenses, {plural(total, "entry", "entries")}
          </td>
          <td className="r">
            {entries.length === total && formats.formatNumber(counted(entries))}
          </td>
          <td colSpan={3} />
        </tr>
      }
    >
      <Days
        entries={entries}
        grouped={days}
        span={8 + lead}
        note={(day) =>
          `${plural(day.entries.length, "entry", "entries")}, ${formats.kes(day.total)}`
        }
        row={(entry) => (
          <Tr key={entry.id}>
            {selection && (
              <Td label="Select">
                {selectable(entry) && (
                  <input
                    className="cb"
                    type="checkbox"
                    aria-label={`Select ${entryLabel(formats, entry)}`}
                    checked={selection.ids.includes(entry.id)}
                    onChange={() => selection.onToggle(entry)}
                  />
                )}
              </Td>
            )}
            <Td label="Vehicle">
              <RegPlate>{entry.registration}</RegPlate>
            </Td>
            <Td label="Item" className="item">
              {entry.expenseItemName}
              {notesOf(entry).map((note) => (
                <CellNote key={note}>{note}</CellNote>
              ))}
            </Td>
            <Td label="Qty" numeric>
              {unitsText(entry.units)}
            </Td>
            <Td label="Unit cost" numeric>
              {formats.formatNumber(entry.unitAmount)}
            </Td>
            <Td
              label="Total amount"
              numeric
              className={entry.total < 0 ? "tot neg" : "tot"}
            >
              {formats.formatNumber(entry.total)}
              {entry.total < 0 && <CellNote>Money back</CellNote>}
            </Td>
            <Td label="Manager" className="nw">
              {entry.holderName}
            </Td>
            <Td label="Status">
              <StatusTag status={statusOf(entry)} />
            </Td>
            <Td numeric>
              <RowActions entry={entry} actions={actions} />
            </Td>
          </Tr>
        )}
      />
    </DataTable>
  );
}
