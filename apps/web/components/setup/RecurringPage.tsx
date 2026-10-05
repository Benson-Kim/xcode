"use client";

import { useState } from "react";

import { useResource, useStreamedList } from "../../lib/data";
import { kes, plural } from "../../lib/format";
import { Banner, Button, CellNote, DataTable, FormSkeleton, PageHeader, RowButton, SegmentedControl, Spacer, StatusBadge, Td, Toolbar, Tr } from "../ui";
import { recurringCategoryNames, type RecurringItem, type VehicleOption } from "./shared";
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
  const [filter, setFilter] = useState<Filter>("all");
  const [editing, setEditing] = useState<string | null>(
    newForVehicle ? "new" : (openItem ?? null),
  );
  // Viewing needs only commitments access: shares carry their registration. The vehicle picker is for editors.
  const options = useResource<VehicleOption[]>(
    canManage ? "setup/recurring/vehicle-options" : null,
  );

  const recurring = useStreamedList<RecurringItem>("setup/recurring");
  const items = recurring.items;

  if (editing) {
    const item = editing === "new" ? undefined : items.find((candidate) => candidate.id === editing);
    // An existing item opens as soon as the page holding it arrives; a new one opens straight away. The
    // vehicle picker fills in when its own request lands.
    if (editing !== "new" && !item) {
      const stillLoading = recurring.loading || recurring.pendingRows > 0;
      return (
        <section>
          <PageHeader title="Recurring cost or saving" />
          {recurring.error || !stillLoading ? (
            <Banner className="mt-5">{recurring.error || "This item is no longer in your list."}</Banner>
          ) : (
            <FormSkeleton cards={3} label="Loading the recurring item" />
          )}
        </section>
      );
    }
    return (
      <RecurringEditor
        item={item}
        vehiclesLoading={canManage && options.loading}
        vehicles={editorVehicles(options.data ?? [], item)}
        preselectVehicle={editing === "new" ? newForVehicle : undefined}
        canEdit={canManage && !item?.partial}
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
        pendingRows={recurring.pendingRows}
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
                <CellNote>
                  {item.partial ? "Your vehicles' share. " : ""}About {kes(recurringMonthlyEstimate(item.amount, item.frequency))} a month
                </CellNote>
              </Td>
              <Td label="How often">{recurringFrequency(item)}</Td>
              <Td label="Vehicles">
                {plural(item.allocations.length, "vehicle", "vehicles")}
                <CellNote>
                  {registrations.slice(0, 2).join(", ")}
                  {item.allocations.length > 2 ? ` and ${item.allocations.length - 2} more` : ""}
                  {item.partial ? ", plus vehicles you can't see" : ""}
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
