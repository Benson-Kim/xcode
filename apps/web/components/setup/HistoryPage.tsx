"use client";

import { useStreamedList } from "../../lib/data";
import { formatDateTime } from "../../lib/format";
import { Banner, DataTable, PageHeader, Td, Tr } from "../ui";
import type { HistoryRow } from "./shared";

const sections: Record<string, string> = {
  companies: "PSV companies",
  vehicles: "Vehicles",
  recurring: "Recurring costs and savings",
  organization: "Organization details",
  businessDate: "Business date",
  localization: "Locale and time",
  branding: "Brand",
  securityPolicy: "Security policy",
  logo: "Logo",
  people: "People and access",
};

function snapshot(value?: string | null) {
  if (!value || value === "null") return value === "null" ? "None" : "—";
  try {
    return JSON.stringify(JSON.parse(value), null, 2);
  } catch {
    return value;
  }
}

export function HistoryPage() {
  const history = useStreamedList<HistoryRow>("setup/history");
  const rows = history.items;
  return (
    <section>
      <PageHeader title="Change log" description="Who changed what in setup and organization settings, with the saved before and after values." />
      {history.error && <Banner className="mt-5">{history.error}</Banner>}
      <DataTable
        columns={[{ label: "When" }, { label: "Who" }, { label: "What changed" }]}
        loading={history.loading}
        pendingRows={history.pendingRows}
        loadingLabel="Loading the change log"
        isEmpty={!rows.length}
        emptyMessage="No setup changes yet."
      >
        {rows.map((row) => (
          <Tr key={`${row.version}-${row.entityId}`}>
            <Td label="When" className="whitespace-nowrap">
              {formatDateTime(row.occurredAt)}
            </Td>
            <Td label="Who">{row.actorName || "Someone no longer in the organization"}</Td>
            <Td label="What changed" title={sections[row.section] ?? row.section}>
              <div>{sections[row.section] ?? row.section}: {row.reason}</div>
              {(row.before !== undefined || row.after !== undefined) && (
                <details className="mt-1.5 text-xs">
                  <summary className="cursor-pointer text-grey">Show saved values</summary>
                  <div className="mt-1 grid gap-1.5 sm:grid-cols-2">
                    <pre className="m-0 overflow-auto rounded-lg bg-paper p-2">Before{"\n"}{snapshot(row.before)}</pre>
                    <pre className="m-0 overflow-auto rounded-lg bg-paper p-2">After{"\n"}{snapshot(row.after)}</pre>
                  </div>
                </details>
              )}
            </Td>
          </Tr>
        ))}
      </DataTable>
    </section>
  );
}
