"use client";

import { useEffect, useState } from "react";

import { isDate } from "@xcode/shared/dates";
import type { Formatter } from "@xcode/shared/format";

import { useFormats } from "../../lib/formats";
import {
  Banner,
  Button,
  DataTable,
  PageHeader,
  Pager,
  SelectInput,
  Td,
  TextInput,
  Toolbar,
  Tr,
} from "../ui";
import { usePagedList } from "../usePagedList";
import type { HistoryRow } from "./shared";

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
  revenue: "Revenue",
  pettycash: "Petty cash",
  centralexpenses: "Central expenses",
  reports: "Reports",
};

type FieldChange = {
  key: string;
  label: string;
  before: string;
  after: string;
};
type Snapshot =
  | { raw: string }
  | { fields: Map<string, { label: string; value: string }> }
  | null;

// "weeklyTarget" or "WeeklyTarget" -> "Weekly target".
function humanize(key: string) {
  const words = key
    .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
    .replace(/_/g, " ")
    .toLowerCase();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

function display(formats: Formatter, value: unknown) {
  if (value === null || value === undefined) return "None";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (isDate(value)) return formats.formatDateOnly(value);
  if (
    typeof value === "string" &&
    /^\d{4}-\d{2}-\d{2}T/.test(value) &&
    !Number.isNaN(Date.parse(value))
  )
    return formats.formatDateTime(value);
  return String(value);
}

// Internal identifiers ("Id", "VehicleId", "companyIds", a record's concurrency "Version", or any value that is a
// bare GUID such as "CapturedBy") mean nothing to a reader, so the log leaves them out.
const internal = (key: string) =>
  /^(ids?|version)$/i.test(key) || /[a-z0-9]Ids?$/.test(key);
const GUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

// Every value in a saved snapshot, keyed by its path: nested objects and lists become "Versions 2 › Amount".
// A list of plain values (such as permissions) is one field, so a change reads as the whole list before and after
// rather than as positions that shifted.
function flatten(
  formats: Formatter,
  value: unknown,
  path: string[],
  labels: string[],
  into: Map<string, { label: string; value: string }>,
) {
  if (
    Array.isArray(value) &&
    value.length &&
    value.every((entry) => entry === null || typeof entry !== "object")
  ) {
    into.set(path.join("."), {
      label: labels.join(" › ") || "Value",
      value: value
        .map((entry) => display(formats, entry))
        .sort()
        .join(", "),
    });
    return into;
  }
  const all: [string, unknown, string][] = Array.isArray(value)
    ? value.map((entry, index) => [String(index), entry, `${index + 1}`])
    : value && typeof value === "object"
      ? Object.entries(value).map(([key, entry]) => [key, entry, humanize(key)])
      : [];
  const entries = Array.isArray(value)
    ? all
    : all.filter(([key]) => !internal(key));
  if (all.length && !entries.length) return into;
  if (!entries.length) {
    if (typeof value === "string" && GUID.test(value)) return into;
    const empty = Array.isArray(value) || (value && typeof value === "object");
    into.set(path.join("."), {
      label: labels.join(" › ") || "Value",
      value: empty ? "None" : display(formats, value),
    });
    return into;
  }
  for (const [key, entry, label] of entries) {
    // A list position joins the name before it ("Versions 2"), so a path reads as a sentence.
    const nextLabels =
      Array.isArray(value) && labels.length
        ? [...labels.slice(0, -1), `${labels[labels.length - 1]} ${label}`]
        : [...labels, label];
    flatten(formats, entry, [...path, key], nextLabels, into);
  }
  return into;
}

// A saved value: missing or "null" (nothing there, as before a create), JSON, or plain text shown as it is.
function parse(formats: Formatter, value?: string | null): Snapshot {
  if (value === undefined || value === null || value === "null") return null;
  try {
    return { fields: flatten(formats, JSON.parse(value), [], [], new Map()) };
  } catch {
    return { raw: value };
  }
}

// What a change did, field by field. An update lists only the fields that changed; a create lists them all.
export function fieldChanges(
  formats: Formatter,
  before?: string | null,
  after?: string | null,
): FieldChange[] {
  const [old, next] = [parse(formats, before), parse(formats, after)];
  if (!old && !next) return [];
  if ((old && "raw" in old) || (next && "raw" in next))
    return [
      {
        key: "raw",
        label: "Saved value",
        before: before && before !== "null" ? before : "—",
        after: after && after !== "null" ? after : "—",
      },
    ];
  const oldFields =
    old?.fields ?? new Map<string, { label: string; value: string }>();
  const newFields =
    next?.fields ?? new Map<string, { label: string; value: string }>();
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

// What the filter bar is asking for. "all" and the empty strings mean "not narrowed".
type Filters = { section: string; from: string; to: string; text: string };

const NOTHING_SET: Filters = { section: "all", from: "", to: "", text: "" };

const narrowed = (filters: Filters) =>
  filters.section !== "all" ||
  Boolean(filters.from || filters.to || filters.text.trim());

// Only the parts that are set are sent, so the request says exactly what the person asked for.
function search(filters: Filters) {
  const parts: string[] = [];
  if (filters.section !== "all")
    parts.push(`section=${encodeURIComponent(filters.section)}`);
  if (filters.from) parts.push(`from=${filters.from}`);
  if (filters.to) parts.push(`to=${filters.to}`);
  if (filters.text.trim())
    parts.push(`text=${encodeURIComponent(filters.text.trim())}`);
  return parts.length ? `&${parts.join("&")}` : "";
}

const rowKey = (row: HistoryRow) => `${row.version}-${row.entityId}`;

// The change log a server page at a time, with its count. The filter is part of the request, so the server counts
// the narrowed log; changing it starts again at page 1.
function useHistoryPages(query: string) {
  return usePagedList<HistoryRow>(`setup/history?includeTotal=true${query}`);
}

function ChangeTable({
  caption,
  changes,
}: {
  caption: string;
  changes: FieldChange[];
}) {
  const cell =
    "border-t border-divider py-1 pr-3 align-top text-left [overflow-wrap:anywhere]";
  return (
    <table className="mt-2 w-full table-fixed border-collapse text-[13px]">
      <caption className="sr-only">{caption}</caption>
      <thead>
        <tr>
          {["Field", "Before", "After"].map((heading) => (
            <th
              key={heading}
              scope="col"
              className="py-1 pr-3 text-left font-semibold text-grey"
            >
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
            <td className={`${cell} text-slate`}>{change.before}</td>
            <td className={`${cell} text-ink`}>{change.after}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function HistoryPage() {
  const formats = useFormats();
  const [filters, setFilters] = useState<Filters>(NOTHING_SET);
  // A section or a date is one choice and is asked for as it is made. Typing is not: the box settles first, so
  // a word is one request rather than one per letter.
  const [settled, setSettled] = useState("");
  useEffect(() => {
    if (filters.text === settled) return;
    const settle = setTimeout(() => setSettled(filters.text), 350);
    return () => clearTimeout(settle);
  }, [filters.text, settled]);

  const applied = { ...filters, text: settled };
  const history = useHistoryPages(search(applied));
  const rows = history.items;
  const some = narrowed(applied);
  const set = (part: Partial<Filters>) =>
    setFilters((current) => ({ ...current, ...part }));
  const label = "text-[13px] text-grey";
  return (
    <section>
      <PageHeader
        title="Change log"
        description="Who changed what in setup, organization settings, people and access, with each value before and after the change."
      />
      {history.error && <Banner className="mb-3.5">{history.error}</Banner>}

      <Toolbar>
        <label htmlFor="log-section" className={label}>
          Section
        </label>
        <SelectInput
          id="log-section"
          density="compact"
          inline
          value={filters.section}
          onChange={(event) => set({ section: event.target.value })}
        >
          <option value="all">All sections</option>
          {Object.entries(sections).map(([key, name]) => (
            <option key={key} value={key}>
              {name}
            </option>
          ))}
        </SelectInput>
        <label htmlFor="log-from" className={label}>
          From
        </label>
        {/* The range cannot be set backwards here, and the server refuses it as well. */}
        <TextInput
          id="log-from"
          type="date"
          density="compact"
          inline
          max={filters.to || undefined}
          value={filters.from}
          onChange={(event) => set({ from: event.target.value })}
        />
        <label htmlFor="log-to" className={label}>
          To
        </label>
        <TextInput
          id="log-to"
          type="date"
          density="compact"
          inline
          min={filters.from || undefined}
          value={filters.to}
          onChange={(event) => set({ to: event.target.value })}
        />
        <label htmlFor="log-search" className={label}>
          Search
        </label>
        <TextInput
          id="log-search"
          type="search"
          density="compact"
          inline
          placeholder="A reason or a name"
          value={filters.text}
          onChange={(event) => set({ text: event.target.value })}
        />
        {narrowed(filters) && (
          <Button tone="quiet" onClick={() => setFilters(NOTHING_SET)}>
            Clear
          </Button>
        )}
      </Toolbar>

      <DataTable
        columns={[
          { label: "When" },
          { label: "Who" },
          { label: "What changed" },
        ]}
        loading={history.loading}
        loadingLabel="Loading the change log"
        isEmpty={!rows.length}
        failed={Boolean(history.error)}
        emptyMessage={
          some ? "No changes match this filter." : "No setup changes yet."
        }
      >
        {rows.map((row) => {
          const what = `${sections[row.section] ?? row.section}: ${row.reason}`;
          const changes = fieldChanges(formats, row.before, row.after);
          return (
            <Tr key={rowKey(row)}>
              <Td label="When" className="whitespace-nowrap">
                {formats.formatDateTime(row.occurredAt)}
              </Td>
              <Td label="Who">
                {row.actorName || "Someone no longer in the organization"}
              </Td>
              <Td
                label="What changed"
                title={sections[row.section] ?? row.section}
              >
                <div className="font-semibold text-ink">{what}</div>
                {changes.length > 0 && (
                  <ChangeTable
                    caption={`${what}, before and after`}
                    changes={changes}
                  />
                )}
              </Td>
            </Tr>
          );
        })}
      </DataTable>
      <Pager
        page={history.paging.page}
        pageSize={history.paging.pageSize}
        total={history.total}
        onPageChange={history.paging.setPage}
        onPageSizeChange={history.paging.setPageSize}
      />
    </section>
  );
}
