"use client";

import { useMemo } from "react";

import {
  EXPENSE_SOURCE_LABELS,
  type ExpenseLedgerRow,
} from "@xcode/shared/expenses";

import { useAppearance } from "../../lib/appearance";
import { useFormats } from "../../lib/formats";
import { unitsFormat } from "../pettycash/labels";
import {
  CellNote,
  DataTable,
  PlainTag,
  RowAction,
  Td,
  Tr,
  type Column,
} from "../ui";
import { rowLabel } from "./labels";

const columns = (currency: string): Column[] => [
  { label: "Date" },
  { label: "Vehicle" },
  { label: "Item" },
  { label: "Qty", numeric: true },
  { label: `Unit cost (${currency})`, numeric: true },
  { label: `Total amount (${currency})`, numeric: true },
  { label: "Source" },
  { label: "Recorded by" },
  { label: "Actions", hidden: true },
];

export type LedgerActions = {
  onEdit: (row: ExpenseLedgerRow) => void;
  onRemove: (row: ExpenseLedgerRow) => void;
  // Given only when the person may open Petty cash.
  onOpenDay?: (row: ExpenseLedgerRow) => void;
};

export function LedgerTable({
  rows,
  total,
  amount,
  loading,
  failed,
  filtered,
  actions,
}: {
  rows: ExpenseLedgerRow[];
  // Every row matching the filters, and their amount, not only the rows shown.
  total: number;
  amount: number;
  loading: boolean;
  failed: boolean;
  filtered: boolean;
  actions: LedgerActions;
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
      isEmpty={!rows.length}
      failed={failed}
      emptyMessage={
        filtered ? "Nothing matches." : "No expenses in this period."
      }
    >
      {rows.map((row) => {
        const label = rowLabel(formats, row);
        return (
          <Tr key={row.id}>
            <Td label="Date" className="whitespace-nowrap">
              {formats.formatDateOnly(row.date)}
            </Td>
            <Td label="Vehicle">
              <strong>{row.registration}</strong>
            </Td>
            <Td label="Item">
              {row.itemName}
              {row.categoryName && <CellNote>{row.categoryName}</CellNote>}
              {row.note && <CellNote>{row.note}</CellNote>}
              {row.group && (
                <CellNote>
                  Shared by {row.group.size} vehicles,{" "}
                  {formats.kes(row.group.total)} in all
                </CellNote>
              )}
            </Td>
            <Td label="Qty" numeric>
              {unitsText(row.units)}
            </Td>
            <Td label={`Unit cost (${currency})`} numeric>
              {formats.formatNumber(row.unitAmount)}
            </Td>
            <Td label={`Total amount (${currency})`} numeric>
              <strong>{formats.formatNumber(row.total)}</strong>
            </Td>
            <Td label="Source">
              <PlainTag>{EXPENSE_SOURCE_LABELS[row.source]}</PlainTag>
            </Td>
            <Td label="Recorded by">
              {row.source === "scheduled" ? (
                <span className="text-grey">Standing order</span>
              ) : (
                row.recordedByName
              )}
              {row.source === "pettycash" && row.holderName && (
                <CellNote>{row.holderName}&apos;s float</CellNote>
              )}
            </Td>
            <Td>
              <span className="flex flex-wrap justify-end gap-2">
                {row.canEdit && (
                  <RowAction
                    aria-label={`Edit ${label}`}
                    onClick={() => actions.onEdit(row)}
                  >
                    Edit
                  </RowAction>
                )}
                {row.canRemove && (
                  <RowAction
                    tone="bad"
                    aria-label={`Remove ${label}`}
                    onClick={() => actions.onRemove(row)}
                  >
                    Remove
                  </RowAction>
                )}
                {row.source === "pettycash" && actions.onOpenDay && (
                  <RowAction
                    aria-label={`Open ${formats.formatDateOnly(row.date)} in Petty cash`}
                    onClick={() => actions.onOpenDay?.(row)}
                  >
                    Open day
                  </RowAction>
                )}
              </span>
            </Td>
          </Tr>
        );
      })}
      <Tr>
        <Td colSpan={5} className="font-semibold">
          {total} {total === 1 ? "expense" : "expenses"}
        </Td>
        <Td numeric className="font-bold">
          {formats.formatNumber(amount)}
        </Td>
        <Td colSpan={3} />
      </Tr>
    </DataTable>
  );
}
