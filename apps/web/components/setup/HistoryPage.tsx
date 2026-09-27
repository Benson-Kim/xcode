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
  localization: "Locale and time",
  branding: "Brand",
  securityPolicy: "Security policy",
};

export function HistoryPage() {
  const history = useStreamedList<HistoryRow>("setup/history");
  const rows = history.items;
  return (
    <section>
      <PageHeader title="Change log" description="Who changed what in setup and organization settings." />
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
          <Tr key={row.version}>
            <Td label="When" className="whitespace-nowrap">
              {formatDateTime(row.occurredAt)}
            </Td>
            <Td label="Who">{row.actorName || "Someone no longer in the organization"}</Td>
            <Td label="What changed" title={sections[row.section] ?? row.section}>
              {row.reason}
            </Td>
          </Tr>
        ))}
      </DataTable>
    </section>
  );
}
