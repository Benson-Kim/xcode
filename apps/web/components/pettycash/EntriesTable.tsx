"use client";

import { useMemo } from "react";

import type { PettyCashEntry } from "@xcode/shared/pettyCash";

import { useAppearance } from "../../lib/appearance";
import { useFormats } from "../../lib/formats";
import { CellNote, DataTable, StatusBadge, Td, Tr } from "../ui";
import { unitsFormat } from "./labels";
import { RowActions, type EntryActions } from "./RowActions";
import { StatusTag } from "./StatusTag";

const DATE_COLUMN = { label: "Date" };

const COLUMNS = [
  { label: "Vehicle" },
  { label: "Item" },
  { label: "Units", numeric: true },
  { label: "Amount", numeric: true },
  { label: "Total", numeric: true },
  { label: "Manager" },
  { label: "Status" },
  { label: "Actions", hidden: true },
];

// Expenses and credit notes of the day or the week. A credit note names its payee and belongs to no vehicle.
export function EntriesTable({
  entries,
  week,
  loading,
  failed,
  actions,
}: {
  entries: PettyCashEntry[];
  week: boolean;
  loading: boolean;
  failed: boolean;
  actions: EntryActions;
}) {
  const formats = useFormats();
  const locale = useAppearance().appearance?.formats.locale ?? "en-GB";
  const unitsText = useMemo(() => unitsFormat(locale), [locale]);
  return (
    <DataTable
      columns={week ? [DATE_COLUMN, ...COLUMNS] : COLUMNS}
      loading={loading}
      loadingLabel="Loading expenses"
      isEmpty={!entries.length}
      failed={failed}
      emptyMessage={
        week
          ? "Nothing recorded in this week."
          : "Nothing recorded on this day."
      }
    >
      {entries.map((entry) => {
        const credit = entry.kind === "credit";
        return (
          <Tr key={entry.id}>
            {week && <Td label="Date">{formats.formatDateOnly(entry.date)}</Td>}
            <Td label={credit ? "Payee" : "Vehicle"}>
              <strong>{credit ? entry.payee : entry.registration}</strong>
              {credit && (
                <CellNote>
                  <StatusBadge>Credit note</StatusBadge>
                </CellNote>
              )}
            </Td>
            <Td label={credit ? "Reason" : "Item"}>
              {credit ? entry.note : entry.expenseItemName}
              {credit && entry.reimbursable && (
                <CellNote>To be paid back</CellNote>
              )}
              {!credit && entry.note && <CellNote>{entry.note}</CellNote>}
              {entry.status === "sentBack" && entry.sentBackNote && (
                <CellNote className="text-red-text">
                  Sent back: {entry.sentBackNote}
                </CellNote>
              )}
            </Td>
            <Td label="Units" numeric>
              {credit ? "" : unitsText(entry.units)}
            </Td>
            <Td label="Amount" numeric>
              {credit ? "" : formats.kes(entry.unitAmount)}
            </Td>
            <Td label="Total" numeric>
              <strong>{formats.kes(entry.total)}</strong>
              {entry.total < 0 && <CellNote>Money back</CellNote>}
            </Td>
            <Td label="Manager">{entry.holderName}</Td>
            <Td label="Status">
              {entry.status && <StatusTag status={entry.status} />}
            </Td>
            <Td>
              <RowActions entry={entry} actions={actions} />
            </Td>
          </Tr>
        );
      })}
    </DataTable>
  );
}
