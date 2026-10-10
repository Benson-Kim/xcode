"use client";

import {
  EXPENSE_SOURCE_LABELS,
  EXPENSE_SOURCES,
  type ExpenseSource,
} from "@xcode/shared/expenses";

import { SelectInput } from "../ui";

export type SourceFilter = ExpenseSource | "all";

const OPTIONS: { value: SourceFilter; label: string }[] = [
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
    <SelectInput
      aria-label="Source"
      value={value}
      onChange={(event) => onChange(event.target.value as SourceFilter)}
    >
      {OPTIONS.map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </SelectInput>
  );
}
