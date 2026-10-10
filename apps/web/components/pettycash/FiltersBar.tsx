"use client";

import type { ReactNode } from "react";

import {
  PETTY_CASH_STATUS_LABELS,
  PETTY_CASH_STATUSES,
  type PettyCashHolder,
  type PettyCashStatus,
} from "@xcode/shared/pettyCash";

import { SelectInput, TextInput } from "../ui";

export type StatusFilter = PettyCashStatus | "all";

const STATUS_OPTIONS: { value: StatusFilter; label: string }[] = [
  { value: "all", label: "All statuses" },
  ...PETTY_CASH_STATUSES.map((value) => ({
    value,
    label: PETTY_CASH_STATUS_LABELS[value],
  })),
];

// The views first, then the manager, the status and the search, with the actions at the end.
export function FiltersBar({
  views,
  holders,
  holderId,
  onHolderChange,
  status,
  onStatusChange,
  search,
  onSearchChange,
  actions,
}: {
  views: ReactNode;
  // Given only to a person who may see every float.
  holders?: PettyCashHolder[];
  holderId: string;
  onHolderChange: (holderId: string) => void;
  // Left out where the list has no status, as on cash received.
  status?: StatusFilter;
  onStatusChange?: (status: StatusFilter) => void;
  search: string;
  onSearchChange: (search: string) => void;
  actions: ReactNode;
}) {
  return (
    <div className="bar">
      {views}
      {holders && (
        <SelectInput
          aria-label="Manager"
          value={holderId}
          onChange={(event) => onHolderChange(event.target.value)}
        >
          <option value="">All managers</option>
          {holders.map((holder) => (
            <option key={holder.id} value={holder.id}>
              {`${holder.name}${holder.active ? "" : " (not active)"}`}
            </option>
          ))}
        </SelectInput>
      )}
      {status && onStatusChange && (
        <SelectInput
          aria-label="Show"
          value={status}
          onChange={(event) =>
            onStatusChange(event.target.value as StatusFilter)
          }
        >
          {STATUS_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </SelectInput>
      )}
      <TextInput
        type="search"
        aria-label="Search"
        className="srch"
        placeholder="Search vehicle, item or note"
        value={search}
        onChange={(event) => onSearchChange(event.target.value)}
      />
      <span className="sp" aria-hidden="true" />
      {actions}
    </div>
  );
}
