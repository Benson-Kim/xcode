"use client";

import { useMemo } from "react";

import {
  EXPENSE_SOURCE_LABELS,
  type ExpenseLedgerRow,
} from "@xcode/shared/expenses";

import { useAppearance } from "../../lib/appearance";
import { useFormats } from "../../lib/formats";
import { unitsFormat } from "../pettycash/labels";
import { RegPlate } from "../revenue/RegPlate";
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

const columns: Column[] = [
  { label: "Date" },
  { label: "Vehicle" },
  { label: "Item" },
  { label: "Qty", numeric: true },
  { label: "Unit cost", numeric: true },
  { label: "Total amount", numeric: true },
  { label: "Source" },
  { label: "Recorded by" },
  { label: "Actions", numeric: true },
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
  const locale = useAppearance().appearance?.formats.locale ?? "en-GB";
  const unitsText = useMemo(() => unitsFormat(locale), [locale]);
  return (
    <DataTable
      columns={columns}
      loading={loading}
      loadingLabel="Loading expenses"
      isEmpty={!rows.length}
      failed={failed}
      emptyMessage={
        filtered ? "Nothing matches." : "No expenses in this period."
      }
      footer={
        <Tr>
          <Td colSpan={5}>
            {total} {total === 1 ? "expense" : "expenses"}
          </Td>
          <Td numeric>{formats.formatNumber(amount)}</Td>
          <Td colSpan={3} />
        </Tr>
      }
    >
      {rows.map((row) => {
        const label = rowLabel(formats, row);
        return (
          <Tr key={row.id}>
            <Td label="Date" className="nw">
              {formats.formatDateOnly(row.date)}
            </Td>
            <Td label="Vehicle">
              <RegPlate>{row.registration}</RegPlate>
            </Td>
            <Td label="Item" className="item nw">
              {row.itemName}
              {row.group ? (
                <CellNote>
                  Shared by {row.group.size} vehicles,{" "}
                  {formats.kes(row.group.total)} in all
                </CellNote>
              ) : (
                row.note && <CellNote>{row.note}</CellNote>
              )}
            </Td>
            <Td label="Qty" numeric>
              {unitsText(row.units)}
            </Td>
            <Td label="Unit cost" numeric>
              {formats.formatNumber(row.unitAmount)}
            </Td>
            <Td label="Total amount" numeric className="tot">
              {formats.formatNumber(row.total)}
            </Td>
            <Td label="Source">
              <PlainTag>{EXPENSE_SOURCE_LABELS[row.source]}</PlainTag>
            </Td>
            <Td label="Recorded by" className="nw">
              {row.source === "scheduled" ? (
                <span className="muted">Standing order</span>
              ) : (
                row.recordedByName
              )}
              {row.source === "pettycash" && row.holderName && (
                <CellNote>{row.holderName}&apos;s float</CellNote>
              )}
            </Td>
            <Td>
              <div className="tacts">
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
                    tone="plain"
                    aria-label={`Open ${formats.formatDateOnly(row.date)} in Petty cash`}
                    onClick={() => actions.onOpenDay?.(row)}
                  >
                    Open day
                  </RowAction>
                )}
              </div>
            </Td>
          </Tr>
        );
      })}
    </DataTable>
  );
}
