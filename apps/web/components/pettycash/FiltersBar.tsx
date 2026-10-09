"use client";

import type { ReactNode } from "react";

import type { Period } from "@xcode/shared/periods";
import {
  PETTY_CASH_STATUS_LABELS,
  PETTY_CASH_STATUSES,
  type PettyCashHolder,
  type PettyCashStatus,
} from "@xcode/shared/pettyCash";

import { PeriodPicker } from "../period/PeriodPicker";
import {
  SearchSelect,
  Skeleton,
  Spacer,
  TextInput,
  Toolbar,
  type SearchOption,
} from "../ui";

export type StatusFilter = PettyCashStatus | "all";

const STATUS_OPTIONS: SearchOption[] = [
  { value: "all", label: "All statuses" },
  ...PETTY_CASH_STATUSES.map((value) => ({
    value,
    label: PETTY_CASH_STATUS_LABELS[value],
  })),
];

// The period first, then the manager, the status and the search, with the actions at the end.
export function FiltersBar({
  period,
  businessDate,
  firstDayOfWeek,
  onPeriodChange,
  holders,
  holderId,
  onHolderChange,
  status,
  onStatusChange,
  search,
  onSearchChange,
  actions,
}: {
  // Null until the page knows the business date.
  period: Period | null;
  businessDate: string | null;
  firstDayOfWeek: number;
  onPeriodChange: (period: Period) => void;
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
    <Toolbar>
      {period && businessDate ? (
        <PeriodPicker
          period={period}
          businessDate={businessDate}
          firstDayOfWeek={firstDayOfWeek}
          onChange={onPeriodChange}
        />
      ) : (
        <Skeleton className="h-11 w-56" />
      )}
      {holders && (
        <SearchSelect
          aria-label="Manager"
          density="compact"
          inline
          value={holderId}
          onChange={onHolderChange}
          options={[
            { value: "", label: "Everyone" },
            ...holders.map((holder) => ({
              value: holder.id,
              label: `${holder.name}${holder.active ? "" : " (not active)"}`,
            })),
          ]}
        />
      )}
      {status && onStatusChange && (
        <SearchSelect
          aria-label="Show"
          density="compact"
          inline
          value={status}
          onChange={(value) => onStatusChange(value as StatusFilter)}
          options={STATUS_OPTIONS}
        />
      )}
      <TextInput
        type="search"
        aria-label="Search"
        density="compact"
        inline
        placeholder="Search vehicle, item or note"
        value={search}
        onChange={(event) => onSearchChange(event.target.value)}
      />
      <Spacer />
      <div className="flex flex-wrap items-center gap-2">{actions}</div>
    </Toolbar>
  );
}
