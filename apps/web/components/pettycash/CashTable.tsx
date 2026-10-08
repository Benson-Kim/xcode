"use client";

import type { PettyCashEntry } from "@xcode/shared/pettyCash";

import { useFormats } from "../../lib/formats";
import { DataTable, Td, Tr } from "../ui";
import { RowActions, type EntryActions } from "./RowActions";

const COLUMNS = [
  { label: "Date" },
  { label: "Manager" },
  { label: "What" },
  { label: "Amount", numeric: true },
  { label: "Actions", hidden: true },
];

// Cash given to floats and taken back from them. Cash taken back reads "Less KES 300", as cash returned does in the
// design.
export function CashTable({
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
  return (
    <DataTable
      columns={COLUMNS}
      loading={loading}
      loadingLabel="Loading cash received"
      isEmpty={!entries.length}
      failed={failed}
      emptyMessage={
        week
          ? "No cash movements in this week."
          : "No cash movements on this day."
      }
    >
      {entries.map((entry) => {
        const back = entry.total < 0;
        return (
          <Tr key={entry.id}>
            <Td label="Date" className="whitespace-nowrap">
              {formats.formatDateOnly(entry.date)}
            </Td>
            <Td label="Manager">
              <strong>{entry.holderName}</strong>
            </Td>
            <Td label="What">
              {entry.note || (back ? "Cash returned" : "Cash given")}
            </Td>
            <Td label="Amount" numeric>
              <strong className={back ? "text-green" : undefined}>
                {back
                  ? `Less ${formats.kes(-entry.total)}`
                  : formats.kes(entry.total)}
              </strong>
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
