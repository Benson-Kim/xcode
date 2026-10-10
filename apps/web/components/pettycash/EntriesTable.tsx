"use client";

import { useMemo } from "react";

import { plural } from "@xcode/shared/format";
import type { PettyCashEntry } from "@xcode/shared/pettyCash";

import { useAppearance } from "../../lib/appearance";
import { useFormats } from "../../lib/formats";
import { RegPlate } from "../revenue/RegPlate";
import { CellNote, DataTable, StatusBadge, Td, Tr } from "../ui";
import { Days } from "./dayGroups";
import { unitsFormat } from "./labels";
import { RowActions, type EntryActions } from "./RowActions";
import { StatusTag } from "./StatusTag";

const columns = [
  { label: "Vehicle" },
  { label: "Item" },
  { label: "Qty", numeric: true },
  { label: "Unit cost", numeric: true },
  { label: "Total amount", numeric: true },
  { label: "Manager" },
  { label: "Status" },
  { label: "Actions", numeric: true },
];

// Expenses and credit notes of the days shown, under a row for each day when there are several. A credit note names
// its payee and belongs to no vehicle. The footer counts every matching entry; it adds them up (less those sent
// back) when they are all on this page.
export function EntriesTable({
  entries,
  total,
  days,
  loading,
  failed,
  actions,
}: {
  entries: PettyCashEntry[];
  total: number;
  days: boolean;
  loading: boolean;
  failed: boolean;
  actions: EntryActions;
}) {
  const formats = useFormats();
  const locale = useAppearance().appearance?.formats.locale ?? "en-GB";
  const unitsText = useMemo(() => unitsFormat(locale), [locale]);
  return (
    <DataTable
      columns={columns}
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
          <td colSpan={4}>Expenses, {plural(total, "entry", "entries")}</td>
          <td className="r">
            {entries.length === total &&
              formats.formatNumber(
                entries
                  .filter((entry) => entry.status !== "sentBack")
                  .reduce((sum, entry) => sum + entry.total, 0),
              )}
          </td>
          <td colSpan={3} />
        </tr>
      }
    >
      <Days
        entries={entries}
        grouped={days}
        span={8}
        note={(day) =>
          `${plural(day.entries.length, "entry", "entries")}, ${formats.kes(day.total)}`
        }
        row={(entry) => {
          const credit = entry.kind === "credit";
          return (
            <Tr key={entry.id}>
              <Td label={credit ? "Payee" : "Vehicle"}>
                {credit ? (
                  <strong>{entry.payee}</strong>
                ) : (
                  <RegPlate>{entry.registration}</RegPlate>
                )}
                {credit && (
                  <CellNote>
                    <StatusBadge tone="off">Credit note</StatusBadge>
                  </CellNote>
                )}
              </Td>
              <Td label={credit ? "Reason" : "Item"} className="item">
                {credit ? entry.note : entry.expenseItemName}
                {credit && entry.reimbursable && (
                  <CellNote>To be paid back</CellNote>
                )}
                {!credit && entry.note && <CellNote>{entry.note}</CellNote>}
                {entry.status === "sentBack" && entry.sentBackNote && (
                  <CellNote>Sent back: {entry.sentBackNote}</CellNote>
                )}
              </Td>
              <Td label="Qty" numeric>
                {credit ? "" : unitsText(entry.units)}
              </Td>
              <Td label="Unit cost" numeric>
                {credit ? "" : formats.formatNumber(entry.unitAmount)}
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
