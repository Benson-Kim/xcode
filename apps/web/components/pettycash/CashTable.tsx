"use client";

import type { PettyCashEntry } from "@xcode/shared/pettyCash";

import { useFormats } from "../../lib/formats";
import { DataTable, RowAction, Td, Tr, type Column } from "../ui";
import { Days } from "./dayGroups";
import { entryLabel } from "./labels";

const columns: Column[] = [
  { label: "Type" },
  { label: "Manager" },
  { label: "Reason" },
  { label: "In", numeric: true },
  { label: "Out", numeric: true },
];

// What an entry did to the cash received: cash issued and money repaid count in, credit notes and cash taken back
// count out.
const net = (entry: PettyCashEntry) =>
  entry.kind === "cash" ? entry.total : -entry.total;

const sumNet = (entries: PettyCashEntry[]) =>
  Math.round(entries.reduce((sum, entry) => sum + net(entry), 0) * 100) / 100;

// Cash issued to managers, taken back from them, and credit notes, as money in and money out. Neither is reviewed or
// edited; a person who may delete cash entries has an Actions column, with Delete on the rows the server lets them
// delete. The footer nets every entry out when they are all on this page.
export function CashTable({
  entries,
  total,
  days,
  searching,
  loading,
  failed,
  canDelete,
  onRemove,
}: {
  entries: PettyCashEntry[];
  total: number;
  days: boolean;
  searching: boolean;
  loading: boolean;
  failed: boolean;
  canDelete: boolean;
  onRemove: (entry: PettyCashEntry) => void;
}) {
  const formats = useFormats();
  const shown = canDelete
    ? [...columns, { label: "Actions", numeric: true }]
    : columns;
  return (
    <DataTable
      columns={shown}
      loading={loading}
      loadingLabel="Loading cash received"
      isEmpty={!entries.length}
      failed={failed}
      emptyMessage={searching ? "Nothing matches." : "No cash moved."}
      footer={
        <tr>
          <td colSpan={3}>Net cash received</td>
          <td className="r" colSpan={2}>
            {entries.length === total && formats.formatNumber(sumNet(entries))}
          </td>
          {canDelete && <td />}
        </tr>
      }
    >
      <Days
        entries={entries}
        grouped={days}
        span={shown.length}
        note={(day) => `Net cash received ${formats.kes(sumNet(day.entries))}`}
        row={(entry) => {
          const credit = entry.kind === "credit";
          const money = net(entry);
          return (
            <Tr key={entry.id}>
              <Td label="Type">
                {credit ? (
                  <span className="chip bad">Credit note</span>
                ) : entry.total < 0 ? (
                  "Cash taken back"
                ) : (
                  "Cash issued"
                )}
              </Td>
              <Td label="Manager" className="nw">
                {entry.holderName}
              </Td>
              <Td label="Reason">{entry.note}</Td>
              <Td label="In" numeric className="tot">
                {money > 0 && formats.formatNumber(money)}
              </Td>
              <Td label="Out" numeric className="tot neg">
                {money < 0 && formats.formatNumber(-money)}
              </Td>
              {canDelete && (
                <Td numeric>
                  <div className="tacts">
                    {entry.canRemove && (
                      <RowAction
                        tone="bad"
                        aria-label={`Delete ${entryLabel(formats, entry)}`}
                        onClick={() => onRemove(entry)}
                      >
                        Delete
                      </RowAction>
                    )}
                  </div>
                </Td>
              )}
            </Tr>
          );
        }}
      />
    </DataTable>
  );
}
