"use client";

import { useState } from "react";
import { useAppearance } from "../../lib/appearance";
import { useResource, useStreamedList } from "../../lib/data";
import { kes, plural } from "../../lib/format";
import type { ExpenseItemOption } from "../../lib/types";
import { Banner, Button, CellNote, DataTable, FormSkeleton, PageHeader, RowButton, SegmentedControl, SelectInput, Spacer, StatusBadge, Td, Toolbar, Tr } from "../ui";
import { costBucket, expenseBucketNames, type RecurringItem, type VehicleOption } from "./shared";
import { formatDateOnly, recurringFrequency, recurringMonthlyEstimate, recurringNextPosting } from "../recurringPresentation";
import { RecurringEditor } from "../RecurringEditor";

type Filter = "all" | "cost" | "savings";
type Status = "all" | "running" | "stopped";

export function RecurringPage({
  canManage,
  openItem,
  newForVehicle,
}: {
  canManage: boolean;
  openItem?: string;
  newForVehicle?: string;
}) {
  const { appearance } = useAppearance();
  const recurring = useStreamedList<RecurringItem>("setup/recurring");
  const [filter, setFilter] = useState<Filter>("all");
  const [companyFilter, setCompanyFilter] = useState("all");
  const [status, setStatus] = useState<Status>("all");
  const [editing, setEditing] = useState<string | null>(newForVehicle ? "new" : (openItem ?? null));
  // Viewing needs only commitments access: shares carry their registration and costs their item's name. The vehicle
  // picker is for editors; the expense item picker loads once an editor opens.
  const options = useResource<VehicleOption[]>(canManage ? "setup/recurring/vehicle-options" : null);
  const expenseItems = useResource<ExpenseItemOption[]>(canManage && editing ? "setup/expense-items/options" : null);
  const items = recurring.items;

  if (editing) {
    const item = editing === "new" ? undefined : items.find((candidate) => candidate.id === editing);
    // An existing item opens as soon as the page holding it arrives; a new one opens straight away. The
    // vehicle picker fills in when its own request lands.
    if (editing !== "new" && !item) {
      const stillLoading = recurring.loading || recurring.pendingRows > 0;
      return (
        <section>
          <PageHeader title="Scheduled expense or saving" />
          {recurring.error || !stillLoading ? (
            <Banner className="mt-5">{recurring.error || "This item is no longer in your list."}</Banner>
          ) : (
            <FormSkeleton cards={3} label="Loading the scheduled item" />
          )}
        </section>
      );
    }
    return (
      <RecurringEditor
        item={item}
        vehiclesLoading={canManage && options.loading}
        vehicles={editorVehicles(options.data ?? [], item)}
        expenseItems={expenseItems.data}
        loadError={options.error || expenseItems.error}
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

  // Due dates count from the organization's business date, never the computer clock. Until the appearance has
  // loaded, next postings wait for it.
  const today = appearance?.businessDate;
  const hasActiveVehicle = (item: RecurringItem) => item.allocations.some((allocation) => allocation.active !== false);
  const finished = (item: RecurringItem) => (!hasActiveVehicle(item) || item.stoppedFrom || (today && item.end && item.end < today) ? 1 : 0);
  // Companies come from the vehicle options, which only editors load: allocations carry no company.
  const companyOf = new Map((options.data ?? []).map((vehicle) => [vehicle.id, vehicle.companyId]));
  const companies = [...new Map((options.data ?? []).map((vehicle) => [vehicle.companyId, vehicle.companyName])).entries()].sort((left, right) =>
    left[1].localeCompare(right[1]),
  );
  const visible = items
    .filter((item) => filter === "all" || (filter === "cost" ? item.kind === 1 : item.kind === 2))
    .filter((item) => companyFilter === "all" || item.allocations.some((allocation) => companyOf.get(allocation.vehicleId) === companyFilter))
    .filter((item) => status === "all" || (status === "stopped") === Boolean(finished(item)))
    .sort((left, right) => finished(left) - finished(right) || left.name.localeCompare(right.name));
  return (
    <section>
      <PageHeader title="Scheduled expenses and savings" description="Set once. Each posts to its vehicles on its own dates and shows in their reports." />
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
        {companies.length > 1 && (
          <>
            <label htmlFor="recurring-company" className="text-[13px] text-grey">
              Company
            </label>
            <SelectInput id="recurring-company" density="compact" inline value={companyFilter} onChange={(event) => setCompanyFilter(event.target.value)}>
              <option value="all">All companies</option>
              {companies.map(([id, name]) => (
                <option key={id} value={id}>
                  {name}
                </option>
              ))}
            </SelectInput>
          </>
        )}
        <label htmlFor="recurring-status" className="text-[13px] text-grey">
          Show
        </label>
        <SelectInput id="recurring-status" density="compact" inline value={status} onChange={(event) => setStatus(event.target.value as Status)}>
          <option value="all">All</option>
          <option value="running">Running</option>
          <option value="stopped">Stopped</option>
        </SelectInput>
        <Spacer />
        {canManage && <Button onClick={() => setEditing("new")}>Add scheduled expense or saving</Button>}
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
        loadingLabel="Loading scheduled expenses and savings"
        isEmpty={!visible.length}
        emptyMessage="Nothing here yet."
      >
        {visible.map((item) => {
          const active = hasActiveVehicle(item);
          const next = item.stoppedFrom || !active || !today ? null : recurringNextPosting(item, today);
          const registrations = item.allocations.map((allocation) => allocation.registration).filter((registration): registration is string => Boolean(registration));
          const outOfFleetCount = item.allocations.filter((allocation) => allocation.active === false).length;
          // What posts now. `amount` is the saved total, which still counts vehicles not in the fleet today.
          const posting = item.activeAmount ?? item.amount;
          // A cost counts in its item's bucket; a row saved before expense items counts in its old type's bucket.
          const bucket = costBucket(item);
          const countsAs = bucket ? expenseBucketNames[bucket] : "Savings";
          return (
            <Tr key={item.id}>
              <Td label="Item">
                <RowButton onClick={() => setEditing(item.id)}>{item.name}</RowButton>
                <CellNote>
                  {item.note ? `${item.note}. ` : ""}
                  {countsAs}
                </CellNote>
              </Td>
              <Td label="Amount each time" numeric>
                {kes(posting)}
                <CellNote>
                  {item.partial ? "Your vehicles' share. " : ""}
                  {posting !== item.amount
                    ? `${kes(item.amount)} in total, with ${outOfFleetCount === 1 ? "1 share for a vehicle" : `${outOfFleetCount} shares for vehicles`} not in the fleet today. `
                    : ""}
                  About {kes(recurringMonthlyEstimate(posting, item.frequency))} a month
                </CellNote>
              </Td>
              <Td label="How often">{recurringFrequency(item)}</Td>
              <Td label="Vehicles">
                {plural(item.allocations.length, "vehicle", "vehicles")}
                <CellNote>
                  {registrations.slice(0, 2).join(", ")}
                  {item.allocations.length > 2 ? ` and ${item.allocations.length - 2} more` : ""}
                  {outOfFleetCount ? `, ${outOfFleetCount} not in the fleet today` : ""}{item.partial ? ", plus vehicles you can't see" : ""}
                </CellNote>
              </Td>
              <Td label="Period">
                {formatDateOnly(item.start)}
                {item.end ? ` to ${formatDateOnly(item.end)}` : <CellNote>No end date</CellNote>}
              </Td>
              <Td label="Next posting">
                {item.stoppedFrom ? (
                  <StatusBadge tone="off">Stopped</StatusBadge>
                ) : !active ? (
                  <StatusBadge tone="off">No active vehicles</StatusBadge>
                ) : !today ? (
                  "—"
                ) : next ? (
                  formatDateOnly(next)
                ) : (
                  <StatusBadge tone="off">Finished</StatusBadge>
                )}
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
      .map((allocation) => ({
        id: allocation.vehicleId,
        companyId: "",
        companyName: "",
        registration: allocation.registration || "Vehicle",
        active: allocation.active !== false,
      })),
  ];
}
