"use client";

import { useCallback, useEffect, useState } from "react";
import { apiRequest } from "../../lib/data";
import { formatDateTime } from "../../lib/format";
import type { Page } from "../../lib/types";
import { formatDateOnly } from "../recurringPresentation";
import { Banner, Button, DataTable, Hint, PageHeader, Td, Tr } from "../ui";
import type { HistoryRow } from "./shared";

const PAGE_SIZE = 25;

const sections: Record<string, string> = {
  companies: "PSV companies",
  vehicles: "Vehicles",
  investment: "Investment",
  expenses: "Expense categories",
  recurring: "Scheduled expenses and savings",
  organization: "Organization details",
  businessDate: "Business date",
  localization: "Locale and time",
  branding: "Brand",
  securityPolicy: "Security policy",
  logo: "Logo",
  people: "People and access",
};

type FieldChange = { key: string; label: string; before: string; after: string };
type Snapshot = { raw: string } | { fields: Map<string, { label: string; value: string }> } | null;

// "weeklyTarget" or "WeeklyTarget" -> "Weekly target".
function humanize(key: string) {
  const words = key.replace(/([a-z0-9])([A-Z])/g, "$1 $2").replace(/_/g, " ").toLowerCase();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

function display(value: unknown) {
  if (value === null || value === undefined) return "None";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value)) return formatDateOnly(value);
  if (typeof value === "string" && /^\d{4}-\d{2}-\d{2}T/.test(value) && !Number.isNaN(Date.parse(value))) return formatDateTime(value);
  return String(value);
}

// Every value in a saved snapshot, keyed by its path: nested objects and lists become "Versions 2 › Amount".
function flatten(value: unknown, path: string[], labels: string[], into: Map<string, { label: string; value: string }>) {
  const entries: [string, unknown, string][] = Array.isArray(value)
    ? value.map((entry, index) => [String(index), entry, `${index + 1}`])
    : value && typeof value === "object"
      ? Object.entries(value).map(([key, entry]) => [key, entry, humanize(key)])
      : [];
  if (!entries.length) {
    const empty = Array.isArray(value) || (value && typeof value === "object");
    into.set(path.join("."), { label: labels.join(" › ") || "Value", value: empty ? "None" : display(value) });
    return into;
  }
  for (const [key, entry, label] of entries) {
    // A list position joins the name before it ("Versions 2"), so a path reads as a sentence.
    const nextLabels = Array.isArray(value) && labels.length ? [...labels.slice(0, -1), `${labels[labels.length - 1]} ${label}`] : [...labels, label];
    flatten(entry, [...path, key], nextLabels, into);
  }
  return into;
}

// A saved value: missing or "null" (nothing there, as before a create), JSON, or plain text shown as it is.
function parse(value?: string | null): Snapshot {
  if (value === undefined || value === null || value === "null") return null;
  try {
    return { fields: flatten(JSON.parse(value), [], [], new Map()) };
  } catch {
    return { raw: value };
  }
}

// What a change did, field by field. An update lists only the fields that changed; a create lists them all.
export function fieldChanges(before?: string | null, after?: string | null): FieldChange[] {
  const [old, next] = [parse(before), parse(after)];
  if (!old && !next) return [];
  if ((old && "raw" in old) || (next && "raw" in next))
    return [{ key: "raw", label: "Saved value", before: before && before !== "null" ? before : "—", after: after && after !== "null" ? after : "—" }];
  const oldFields = old?.fields ?? new Map<string, { label: string; value: string }>();
  const newFields = next?.fields ?? new Map<string, { label: string; value: string }>();
  const keys = [...new Set([...newFields.keys(), ...oldFields.keys()])];
  return keys
    .map((key) => ({
      key,
      label: (newFields.get(key) ?? oldFields.get(key))!.label,
      before: oldFields.get(key)?.value ?? "—",
      after: newFields.get(key)?.value ?? "—",
    }))
    .filter((change) => change.before !== change.after);
}

type Loaded = { items: HistoryRow[]; total: number; pages: number; done: boolean; error: string };

const rowKey = (row: HistoryRow) => `${row.version}-${row.entityId}`;

// The change log a page at a time: the first page when it opens, and the next only when the person asks for it.
// Changes saved meanwhile push older rows down a page, so rows already shown are not added twice.
function useHistoryPages() {
  const [loaded, setLoaded] = useState<Loaded>({ items: [], total: 0, pages: 0, done: false, error: "" });
  const [pending, setPending] = useState<number | null>(1);

  const receive = useCallback(
    (page: number) =>
      apiRequest<Page<HistoryRow>>(`setup/history?page=${page}&pageSize=${PAGE_SIZE}`)
        .then(
          (result) =>
            setLoaded((current) => {
              const kept = page === 1 ? [] : current.items;
              const seen = new Set(kept.map(rowKey));
              const items = [...kept, ...result.items.filter((row) => !seen.has(rowKey(row)))];
              return { items, total: result.total, pages: page, done: result.items.length < PAGE_SIZE || items.length >= result.total, error: "" };
            }),
          (error: Error) => setLoaded((current) => ({ ...current, error: error.message })),
        )
        .finally(() => setPending(null)),
    [],
  );

  useEffect(() => {
    void receive(1);
  }, [receive]);

  function more() {
    if (pending !== null) return;
    setPending(loaded.pages + 1);
    void receive(loaded.pages + 1);
  }

  return {
    ...loaded,
    loading: loaded.pages === 0 && pending === 1,
    loadingMore: loaded.pages > 0 && pending !== null,
    hasMore: loaded.pages > 0 && !loaded.done,
    more,
  };
}

function ChangeTable({ caption, changes }: { caption: string; changes: FieldChange[] }) {
  const cell = "border-t border-divider py-1 pr-3 align-top text-left [overflow-wrap:anywhere]";
  return (
    <table className="mt-2 w-full table-fixed border-collapse text-[13px]">
      <caption className="sr-only">{caption}</caption>
      <thead>
        <tr>
          {["Field", "Before", "After"].map((heading) => (
            <th key={heading} scope="col" className="py-1 pr-3 text-left font-semibold text-grey">
              {heading}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {changes.map((change) => (
          <tr key={change.key}>
            <th scope="row" className={`${cell} font-semibold`}>
              {change.label}
            </th>
            <td className={cell}>{change.before}</td>
            <td className={cell}>{change.after}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function HistoryPage() {
  const history = useHistoryPages();
  const rows = history.items;
  return (
    <section>
      <PageHeader title="Change log" description="Who changed what in setup, people and access, with each value before and after the change." />
      {history.error && <Banner className="mt-5">{history.error}</Banner>}
      <DataTable
        columns={[{ label: "When" }, { label: "Who" }, { label: "What changed" }]}
        loading={history.loading}
        pendingRows={history.loadingMore ? 1 : 0}
        loadingLabel="Loading the change log"
        isEmpty={!rows.length}
        emptyMessage="No setup changes yet."
      >
        {rows.map((row) => {
          const what = `${sections[row.section] ?? row.section}: ${row.reason}`;
          const changes = fieldChanges(row.before, row.after);
          return (
            <Tr key={rowKey(row)}>
              <Td label="When" className="whitespace-nowrap">
                {formatDateTime(row.occurredAt)}
              </Td>
              <Td label="Who">{row.actorName || "Someone no longer in the organization"}</Td>
              <Td label="What changed" title={sections[row.section] ?? row.section}>
                <div>{what}</div>
                {changes.length > 0 && <ChangeTable caption={`${what}, before and after`} changes={changes} />}
              </Td>
            </Tr>
          );
        })}
      </DataTable>
      {rows.length > 0 && (
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <Hint>
            {history.hasMore ? `Showing ${rows.length} of ${history.total} changes` : rows.length === 1 ? "1 change" : `Showing all ${rows.length} changes`}
          </Hint>
          {history.hasMore && (
            <Button tone="outline" disabled={history.loadingMore} aria-busy={history.loadingMore || undefined} onClick={history.more}>
              {history.loadingMore ? "Loading..." : "Load more"}
            </Button>
          )}
        </div>
      )}
    </section>
  );
}
