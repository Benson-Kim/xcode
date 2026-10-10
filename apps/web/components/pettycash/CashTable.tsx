"use client";

import type { PettyCashEntry } from "@xcode/shared/pettyCash";

import { useFormats } from "../../lib/formats";
import { DataTable, Td, Tr } from "../ui";
import { Days } from "./dayGroups";
import { RowActions, type EntryActions } from "./RowActions";

const columns = (currency: string) => [
  { label: "Manager" },
  { label: "What" },
  { label: `Amount (${currency})`, numeric: true },
  { label: "Actions", hidden: true },
];

// Cash given to floats and taken back from them. Cash taken back reads "Less KES 300", as cash returned does in the
// design.
export function CashTable({
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
  return (
    <DataTable
      columns={columns(currency)}
      loading={loading}
      loadingLabel="Loading cash received"
      isEmpty={!entries.length}
      failed={failed}
      emptyMessage={
        days
          ? "No cash movements in this period."
          : "No cash movements on this day."
      }
    >
      <Days
        entries={entries}
        grouped={days}
        before={2}
        after={1}
        totalLabel={`Day total (${currency})`}
        row={(entry) => {
          const back = entry.total < 0;
          return (
            <Tr key={entry.id}>
              <Td label="Manager">
                <strong className="font-bold text-ink">
                  {entry.holderName}
                </strong>
              </Td>
              <Td label="What">
                {entry.note || (back ? "Cash returned" : "Cash given")}
              </Td>
              <Td label={`Amount (${currency})`} numeric>
                <strong
                  className={
                    back ? "font-bold text-clay" : "font-bold text-ink"
                  }
                >
                  {back
                    ? `Less ${formats.formatNumber(-entry.total)}`
                    : formats.formatNumber(entry.total)}
                </strong>
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
