"use client";

import type { PettyCashEntry } from "@xcode/shared/pettyCash";

import { useFormats } from "../../lib/formats";
import { DataTable, Td, Tr, type Column } from "../ui";
import { Days } from "./dayGroups";
import { RowActions, type EntryActions } from "./RowActions";

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

const hasActions = (entry: PettyCashEntry) =>
  entry.canEdit || entry.canReview || entry.canRemove || entry.aboveLimit;

function statusNote(entry: PettyCashEntry) {
  if (entry.status === "waiting") return "Waiting for approval";
  if (entry.status === "sentBack")
    return entry.sentBackNote
      ? `Sent back: ${entry.sentBackNote}`
      : "Sent back";
  return null;
}

// Cash issued to managers, taken back from them, and credit notes, as money in and money out. Credit notes wait for
// approval, so they carry its status and, where the server allows, its buttons. The footer nets every entry out when
// they are all on this page.
export function CashTable({
  entries,
  total,
  days,
  searching,
  loading,
  failed,
  actions,
}: {
  entries: PettyCashEntry[];
  total: number;
  days: boolean;
  searching: boolean;
  loading: boolean;
  failed: boolean;
  actions: EntryActions;
}) {
  const formats = useFormats();
  const withActions = entries.some(hasActions);
  const shown = withActions
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
          <td className="r" colSpan={withActions ? 3 : 2}>
            {entries.length === total && formats.formatNumber(sumNet(entries))}
          </td>
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
          const status = statusNote(entry);
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
                {status && <span className="note">{status}</span>}
              </Td>
              <Td label="Manager" className="nw">
                {entry.holderName}
              </Td>
              <Td label="Reason">
                {entry.note}
                {credit && entry.payee && (
                  <span className="note">Paid to {entry.payee}</span>
                )}
                {credit && entry.reimbursable && (
                  <span className="note">To be paid back</span>
                )}
              </Td>
              <Td label="In" numeric className="tot">
                {money > 0 && formats.formatNumber(money)}
              </Td>
              <Td label="Out" numeric className="tot neg">
                {money < 0 && formats.formatNumber(-money)}
              </Td>
              {withActions && (
                <Td>
                  <RowActions entry={entry} actions={actions} />
                </Td>
              )}
            </Tr>
          );
        }}
      />
    </DataTable>
  );
}
