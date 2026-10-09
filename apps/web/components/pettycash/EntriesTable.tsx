"use client";

import { useMemo } from "react";

import type { PettyCashEntry } from "@xcode/shared/pettyCash";

import { useAppearance } from "../../lib/appearance";
import { useFormats } from "../../lib/formats";
import { CellNote, DataTable, StatusBadge, Td, Tr } from "../ui";
import { Days } from "./dayGroups";
import { unitsFormat } from "./labels";
import { RowActions, type EntryActions } from "./RowActions";
import { StatusTag } from "./StatusTag";

const columns = (currency: string) => [
  { label: "Vehicle" },
  { label: "Item" },
  { label: "Units", numeric: true },
  { label: `Amount (${currency})`, numeric: true },
  { label: `Total (${currency})`, numeric: true },
  { label: "Manager" },
  { label: "Status" },
  { label: "Actions", hidden: true },
];

// Expenses and credit notes of the days shown, under a row for each day when there are several. A credit note names
// its payee and belongs to no vehicle.
export function EntriesTable({
  entries,
  days,
  loading,
  failed,
  actions,
}: {
  entries: PettyCashEntry[];
  days: boolean;
  loading: boolean;
  failed: boolean;
  actions: EntryActions;
}) {
  const formats = useFormats();
  const currency = formats.currencyCode();
  const locale = useAppearance().appearance?.formats.locale ?? "en-GB";
  const unitsText = useMemo(() => unitsFormat(locale), [locale]);
  return (
    <DataTable
      columns={columns(currency)}
      loading={loading}
      loadingLabel="Loading expenses"
      isEmpty={!entries.length}
      failed={failed}
      emptyMessage={
        days
          ? "Nothing recorded in this period."
          : "Nothing recorded on this day."
      }
    >
      <Days
        entries={entries}
        grouped={days}
        before={4}
        after={3}
        totalLabel={`Day total (${currency})`}
        row={(entry) => {
          const credit = entry.kind === "credit";
          return (
            <Tr key={entry.id}>
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
              <Td label={`Amount (${currency})`} numeric>
                {credit ? "" : formats.formatNumber(entry.unitAmount)}
              </Td>
              <Td label={`Total (${currency})`} numeric>
                <strong>{formats.formatNumber(entry.total)}</strong>
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
        }}
      />
    </DataTable>
  );
}
