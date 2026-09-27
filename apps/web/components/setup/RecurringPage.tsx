"use client";

import { useState } from "react";
import type { Page } from "../../lib/types";
import { useSetupData } from "../../lib/useSetupData";
import { kes, plural } from "../../lib/format";
import { Banner, Button, CellNote, DataTable, FormSkeleton, PageHeader, RowButton, SegmentedControl, Spacer, StatusBadge, Td, Toolbar, Tr } from "../ui";
import { LIST, recurringCategoryNames, type RecurringItem, type VehicleOption } from "./shared";
import { formatDateOnly, recurringFrequency, recurringMonthlyEstimate, recurringNextPosting, todayDateOnly } from "../recurringPresentation";
import { RecurringEditor } from "../RecurringEditor";

type Filter = "all" | "cost" | "savings";

export function RecurringPage({
  canManage,
  openItem,
  newForVehicle,
}: {
  canManage: boolean;
  openItem?: string;
  newForVehicle?: string;
}) {
  const recurring = useSetupData<Page<RecurringItem>>(`recurring${LIST}`);
  // Viewing needs only commitments access: shares carry their registration. The vehicle picker is for editors.
  const options = useSetupData<VehicleOption[]>(canManage ? "recurring/vehicle-options" : null);
  const [filter, setFilter] = useState<Filter>("all");
  const [editing, setEditing] = useState<string | null>(newForVehicle ? "new" : (openItem ?? null));
  const items = recurring.data?.items ?? [];

  if (editing) {
    const item = editing === "new" ? undefined : items.find((candidate) => candidate.id === editing);
    const waiting = recurring.loading || (canManage && options.loading);
    if (waiting || (editing !== "new" && !item))
      return (
        <section>
          <PageHeader title={editing === "new" ? "Add recurring cost or saving" : "Recurring cost or saving"} />
          {recurring.error ? <Banner className="mt-5">{recurring.error}</Banner> : <FormSkeleton cards={3} label="Loading the recurring item" />}
        </section>
      );
    return (
      <RecurringEditor
        item={item}
        vehicles={editorVehicles(options.data ?? [], item)}
        preselectVehicle={editing === "new" ? newForVehicle : undefined}
        canEdit={canManage}
        onCancel={() => setEditing(null)}
        onSaved={() => {
          setEditing(null);
          recurring.reload();
        }}
      />
    );
  }

  const today = todayDateOnly();
  const finished = (item: RecurringItem) => (item.stoppedFrom || (item.end && item.end < today) ? 1 : 0);
  const visible = items
    .filter((item) => filter === "all" || (filter === "cost" ? item.kind === 1 : item.kind === 2))
    .sort((left, right) => finished(left) - finished(right) || left.name.localeCompare(right.name));
  return (
    <section>
      <PageHeader title="Recurring costs and savings" description="Set once. Each posts to its vehicles on its own dates and shows in their reports." />
      {(recurring.error || options.error) && <Banner className="mt-5">{recurring.error || options.error}</Banner>}
      <Toolbar>
        <SegmentedControl
          label="Show"
          options={[
            { value: "all", label: "All" },
            { value: "cost", label: "Costs" },
            { value: "savings", label: "Savings" },
          ]}
          value={filter}
          onChange={setFilter}
        />
        <Spacer />
        {canManage && <Button onClick={() => setEditing("new")}>Add recurring cost or saving</Button>}
      </Toolbar>
      <DataTable
        columns={[
          { label: "Item" },
          { label: "Amount each time", numeric: true },
          { label: "How often" },
          { label: "Vehicles" },
          { label: "Period" },
          { label: "Next posting" },
        ]}
        loading={recurring.loading}
        loadingLabel="Loading recurring costs and savings"
        isEmpty={!visible.length}
        emptyMessage="Nothing here yet."
      >
        {visible.map((item) => {
          const next = item.stoppedFrom ? null : recurringNextPosting(item, today);
          const registrations = item.allocations.map((allocation) => allocation.registration).filter((registration): registration is string => Boolean(registration));
          return (
            <Tr key={item.id}>
              <Td label="Item">
                <RowButton onClick={() => setEditing(item.id)}>{item.name}</RowButton>
                <CellNote>{item.kind === 2 ? "Savings" : recurringCategoryNames[item.category || 4]}</CellNote>
              </Td>
              <Td label="Amount each time" numeric>
                {kes(item.amount)}
                <CellNote>About {kes(recurringMonthlyEstimate(item.amount, item.frequency))} a month</CellNote>
              </Td>
              <Td label="How often">{recurringFrequency(item)}</Td>
              <Td label="Vehicles">
                {plural(item.allocations.length, "vehicle", "vehicles")}
                <CellNote>
                  {registrations.slice(0, 2).join(", ")}
                  {item.allocations.length > 2 ? ` and ${item.allocations.length - 2} more` : ""}
                </CellNote>
              </Td>
              <Td label="Period">
                {formatDateOnly(item.start)}
                {item.end ? ` to ${formatDateOnly(item.end)}` : <CellNote>No end date</CellNote>}
              </Td>
              <Td label="Next posting">
                {item.stoppedFrom ? <StatusBadge tone="off">Stopped</StatusBadge> : next ? formatDateOnly(next) : <StatusBadge tone="off">Finished</StatusBadge>}
              </Td>
            </Tr>
          );
        })}
      </DataTable>
    </section>
  );
}

// The picker's vehicles, plus any on the item it does not list (for example, when only viewing).
function editorVehicles(vehicles: VehicleOption[], item?: RecurringItem): VehicleOption[] {
  const listed = new Set(vehicles.map((vehicle) => vehicle.id));
  return [
    ...vehicles,
    ...(item?.allocations ?? [])
      .filter((allocation) => !listed.has(allocation.vehicleId))
      .map((allocation) => ({ id: allocation.vehicleId, companyId: "", companyName: "", registration: allocation.registration || "Vehicle" })),
  ];
}
