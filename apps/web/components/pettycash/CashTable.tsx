"use client";

import type { PettyCashEntry } from "@xcode/shared/pettyCash";

import { useFormats } from "../../lib/formats";
import { DataTable, Td, Tr } from "../ui";
import { Days } from "./dayGroups";
import { RowActions, type EntryActions } from "./RowActions";

const columns = [
  { label: "Manager" },
  { label: "Reason" },
  { label: "Amount", numeric: true },
  { label: "Actions", numeric: true },
];

// Cash given to floats and taken back from them. Cash taken back reads "Less KES 300", as cash returned does in the
// design. The footer nets every entry out when they are all on this page.
export function CashTable({
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
  return (
    <DataTable
      columns={columns}
      loading={loading}
      loadingLabel="Loading cash received"
      isEmpty={!entries.length}
      failed={failed}
      emptyMessage={
        days
          ? "No cash movements in this period."
          : "No cash movements on this day."
      }
      footer={
        <tr>
          <td colSpan={2}>Net cash received</td>
          <td className="r">
            {entries.length === total &&
              formats.formatNumber(
                entries.reduce((sum, entry) => sum + entry.total, 0),
              )}
          </td>
          <td />
        </tr>
      }
    >
      <Days
        entries={entries}
        grouped={days}
        span={4}
        note={(day) => `Net cash received ${formats.kes(day.total)}`}
        row={(entry) => {
          const back = entry.total < 0;
          return (
            <Tr key={entry.id}>
              <Td label="Manager" className="nw">
                {entry.holderName}
              </Td>
              <Td label="Reason">
                {entry.note || (back ? "Cash returned" : "Cash given")}
              </Td>
              <Td label="Amount" numeric className={back ? "tot neg" : "tot"}>
                {back
                  ? `Less ${formats.formatNumber(-entry.total)}`
                  : formats.formatNumber(entry.total)}
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
