"use client";

import type { ReactNode } from "react";

import {
  PETTY_CASH_STATUS_LABELS,
  PETTY_CASH_STATUSES,
  type PettyCashHolder,
  type PettyCashPeriod,
  type PettyCashStatus,
} from "@xcode/shared/pettyCash";

import {
  SegmentedControl,
  SelectInput,
  Spacer,
  TextInput,
  Toolbar,
} from "../ui";
import { DayNavigator } from "./DayNavigator";
import { PERIODS, type PeriodRange } from "./period";

export type StatusFilter = PettyCashStatus | "all";

export function FiltersBar({
  date,
  range,
  businessDate,
  period,
  onPeriodChange,
  onDateChange,
  holders,
  holderId,
  onHolderChange,
  status,
  onStatusChange,
  search,
  onSearchChange,
  actions,
}: {
  date: string | null;
  range: PeriodRange | null;
  businessDate: string | null;
  period: PettyCashPeriod;
  onPeriodChange: (period: PettyCashPeriod) => void;
  onDateChange: (date: string) => void;
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
      <DayNavigator
        date={date}
        range={range}
        businessDate={businessDate}
        period={period}
        onChange={onDateChange}
      />
      <SegmentedControl
        label="Period"
        options={PERIODS}
        value={period}
        onChange={onPeriodChange}
      />
      {holders && (
        <SelectInput
          aria-label="Manager"
          density="compact"
          inline
          value={holderId}
          onChange={(event) => onHolderChange(event.target.value)}
        >
          <option value="">Everyone</option>
          {holders.map((holder) => (
            <option key={holder.id} value={holder.id}>
              {holder.name}
              {holder.active ? "" : " (not active)"}
            </option>
          ))}
        </SelectInput>
      )}
      {status && onStatusChange && (
        <SelectInput
          aria-label="Show"
          density="compact"
          inline
          value={status}
          onChange={(event) =>
            onStatusChange(event.target.value as StatusFilter)
          }
        >
          <option value="all">All</option>
          {PETTY_CASH_STATUSES.map((value) => (
            <option key={value} value={value}>
              {PETTY_CASH_STATUS_LABELS[value]}
            </option>
          ))}
        </SelectInput>
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
