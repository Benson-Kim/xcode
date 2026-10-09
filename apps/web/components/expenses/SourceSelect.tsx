"use client";

import {
  EXPENSE_SOURCE_LABELS,
  EXPENSE_SOURCES,
  type ExpenseSource,
} from "@xcode/shared/expenses";

import { SearchSelect, type SearchOption } from "../ui";

export type SourceFilter = ExpenseSource | "all";

const OPTIONS: SearchOption[] = [
  { value: "all", label: "All sources" },
  ...EXPENSE_SOURCES.map((source) => ({
    value: source,
    label: EXPENSE_SOURCE_LABELS[source],
  })),
];

export function SourceSelect({
  value,
  onChange,
}: {
  value: SourceFilter;
  onChange: (value: SourceFilter) => void;
}) {
  return (
    <SearchSelect
      aria-label="Source"
      density="compact"
      inline
      options={OPTIONS}
      value={value}
      onChange={(next) => onChange(next as SourceFilter)}
    />
  );
}
