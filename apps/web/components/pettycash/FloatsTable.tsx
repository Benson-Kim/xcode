"use client";

import type { PettyCashFloat } from "@xcode/shared/pettyCash";

import { useFormats } from "../../lib/formats";
import { CellNote, DataTable, SubHeading, Td, Tr } from "../ui";

const columns = (currency: string) => [
  { label: "Manager" },
  { label: `Cash received (${currency})`, numeric: true },
  { label: `Money out (${currency})`, numeric: true },
  { label: `Cash in hand (${currency})`, numeric: true },
  { label: `Waiting (${currency})`, numeric: true },
  { label: `Approved (${currency})`, numeric: true },
  { label: "Last cash" },
];

// Each float to date: cash in hand is cash received less every expense and credit note, approved or not.
export function FloatsTable({
  floats,
  loading,
}: {
  floats?: PettyCashFloat[];
  loading: boolean;
}) {
  const formats = useFormats();
  const currency = formats.currencyCode();
  return (
    <>
      <SubHeading className="mt-6">Floats</SubHeading>
      <DataTable
        columns={columns(currency)}
        loading={loading}
        loadingLabel="Loading floats"
        isEmpty={!floats?.length}
        emptyMessage="No floats yet."
        className="mt-2"
      >
        {floats?.map((float) => (
          <Tr key={float.holderId}>
            <Td label="Manager">
              <strong>{float.name}</strong>
              {!float.active && <CellNote>Not active</CellNote>}
            </Td>
            <Td label={`Cash received (${currency})`} numeric>
              {formats.formatNumber(float.cashReceived)}
            </Td>
            <Td label={`Money out (${currency})`} numeric>
              {formats.formatNumber(float.expenses + float.creditNotes)}
            </Td>
            <Td
              label={`Cash in hand (${currency})`}
              numeric
              className={float.balance < 0 ? "text-red" : undefined}
            >
              <strong>{formats.formatNumber(float.balance)}</strong>
            </Td>
            <Td label={`Waiting (${currency})`} numeric>
              {formats.formatNumber(float.waiting)}
              {float.waitingCount > 0 && (
                <CellNote>
                  {float.waitingCount === 1
                    ? "1 entry"
                    : `${float.waitingCount} entries`}
                </CellNote>
              )}
            </Td>
            <Td label={`Approved (${currency})`} numeric>
              {formats.formatNumber(float.approved)}
            </Td>
            <Td label="Last cash">
              {float.lastCashOn
                ? formats.formatDateOnly(float.lastCashOn)
                : "None"}
            </Td>
          </Tr>
        ))}
      </DataTable>
    </>
  );
}
