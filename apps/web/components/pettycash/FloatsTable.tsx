"use client";

import type { PettyCashFloat } from "@xcode/shared/pettyCash";

import { useFormats } from "../../lib/formats";
import { CellNote, DataTable, SubHeading, Td, Tr } from "../ui";

const columns = [
  { label: "Manager" },
  { label: "Cash received", numeric: true },
  { label: "Money out", numeric: true },
  { label: "Cash in hand", numeric: true },
  { label: "Waiting", numeric: true },
  { label: "Approved", numeric: true },
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
  return (
    <>
      <SubHeading className="px-(--gut)">Floats</SubHeading>
      <DataTable
        columns={columns}
        loading={loading}
        loadingLabel="Loading floats"
        isEmpty={!floats?.length}
        emptyMessage="No floats yet."
      >
        {floats?.map((float) => (
          <Tr key={float.holderId}>
            <Td label="Manager" className="item nw">
              {float.name}
              {!float.active && <CellNote>Not active</CellNote>}
            </Td>
            <Td label="Cash received" numeric>
              {formats.formatNumber(float.cashReceived)}
            </Td>
            <Td label="Money out" numeric>
              {formats.formatNumber(float.expenses + float.creditNotes)}
            </Td>
            <Td
              label="Cash in hand"
              numeric
              className={float.balance < 0 ? "tot neg" : "tot"}
            >
              {formats.formatNumber(float.balance)}
            </Td>
            <Td label="Waiting" numeric>
              {formats.formatNumber(float.waiting)}
              {float.waitingCount > 0 && (
                <CellNote>
                  {float.waitingCount === 1
                    ? "1 entry"
                    : `${float.waitingCount} entries`}
                </CellNote>
              )}
            </Td>
            <Td label="Approved" numeric>
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
