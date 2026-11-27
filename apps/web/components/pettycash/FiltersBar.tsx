"use client";

import type { ReactNode } from "react";

import type {
  PettyCashHolder,
  PettyCashVehicleOption,
} from "@xcode/shared/pettyCash";

import { SelectInput, TextInput } from "../ui";
import {
  ENTRY_STATUS_LABELS,
  ENTRY_STATUSES,
  type EntryStatus,
} from "./status";

export type StatusFilter = EntryStatus | "all";

const STATUS_OPTIONS: { value: StatusFilter; label: string }[] = [
  { value: "all", label: "All statuses" },
  ...ENTRY_STATUSES.map((value) => ({
    value,
    label: ENTRY_STATUS_LABELS[value],
  })),
];

export const vehicleLabel = (vehicle: PettyCashVehicleOption) =>
  vehicle.fleetNumber
    ? `${vehicle.registration} · ${vehicle.fleetNumber}`
    : vehicle.registration;

// The views first, then the manager, the vehicle, the status and the search, with the actions at the end.
export function FiltersBar({
  views,
  holders,
  holderId,
  onHolderChange,
  vehicles,
  vehicleId,
  onVehicleChange,
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
  // Left out where entries carry no vehicle, as on cash received.
  vehicles?: PettyCashVehicleOption[];
  vehicleId?: string;
  onVehicleChange?: (vehicleId: string) => void;
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
      {vehicles && onVehicleChange && (
        <SelectInput
          aria-label="Vehicle"
          value={vehicleId ?? ""}
          onChange={(event) => onVehicleChange(event.target.value)}
        >
          <option value="">All vehicles</option>
          {vehicles.map((vehicle) => (
            <option key={vehicle.id} value={vehicle.id}>
              {vehicleLabel(vehicle)}
            </option>
          ))}
        </SelectInput>
      )}
      {status && onStatusChange && (
        <SelectInput
          aria-label="Status"
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
        placeholder="Search"
        value={search}
        onChange={(event) => onSearchChange(event.target.value)}
      />
      <span className="sp" aria-hidden="true" />
      {actions}
    </div>
  );
}
