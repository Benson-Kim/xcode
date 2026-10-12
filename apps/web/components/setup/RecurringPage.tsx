"use client";

import { useState } from "react";

import { MONTH_NAMES } from "@xcode/shared/dates";

import { useAppearance } from "../../lib/appearance";
import { streamError, useResource, useStreamedList } from "../../lib/data";
import { useFormats } from "../../lib/formats";
import type { ExpenseItemOption } from "../../lib/types";
import { RecurringEditor } from "../RecurringEditor";
import {
  Banner,
  Button,
  DataTable,
  Dialog,
  FormSkeleton,
  ListPager,
  PageHeader,
  Tabs,
} from "../ui";
import { usePagedList } from "../usePagedList";
import { RecurringRow, SavingsFooter } from "./RecurringRows";
import { RecurringRunsDialog } from "./RecurringRunsDialog";
import type { RecurringItem, RecurringSummary, VehicleOption } from "./shared";
import { useRecurringPause } from "./useRecurringPause";

type Filter = "cost" | "savings";

const columns = (savings: boolean) =>
  savings
    ? [
        { label: "Saving" },
        { label: "Vehicles" },
        { label: "Per vehicle", numeric: true },
        { label: "Runs" },
        { label: "Last run" },
        { label: "Balance", numeric: true },
        { label: "Status" },
        { label: "Actions", numeric: true },
      ]
    : [
        { label: "Item" },
        { label: "Vehicles" },
        { label: "Amount per vehicle", numeric: true },
        { label: "Each run", numeric: true },
        { label: "Runs" },
        { label: "Next run" },
        { label: "Status" },
        { label: "Actions", numeric: true },
      ];

// The small lines under the tab names: what the business date's month holds.
function summaryNotes(
  summary: RecurringSummary | undefined,
  kes: (amount: number) => string,
) {
  if (!summary?.from) return undefined;
  const month = `${MONTH_NAMES[Number(summary.from.slice(5, 7)) - 1]} ${summary.from.slice(0, 4)}`;
  return {
    cost: `${kes(summary.costsDue)} in ${month}`,
    savings: `${kes(summary.saved)} saved in ${month} · balance ${kes(summary.savingsBalance)}`,
  };
}

function activeFleet(vehicles: VehicleOption[] | undefined) {
  if (!vehicles) return null;
  return new Set(
    vehicles
      .filter((vehicle) => vehicle.active !== false)
      .map((vehicle) => vehicle.id),
  );
}

function MissingItemDialog({
  error,
  loading,
  onClose,
}: {
  error: string;
  loading: boolean;
  onClose: () => void;
}) {
  return (
    <Dialog open size="lg" title="Scheduled expense" onClose={onClose}>
      {error || !loading ? (
        <Banner>{error || "This item is no longer in your list."}</Banner>
      ) : (
        <FormSkeleton cards={3} label="Loading the scheduled item" />
      )}
    </Dialog>
  );
}

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
  const { kes } = useFormats();
  const [filter, setFilter] = useState<Filter>("cost");
  const [runsFor, setRunsFor] = useState<RecurringItem | null>(null);
  const [editing, setEditing] = useState<string | null>(
    newForVehicle ? "new" : (openItem ?? null),
  );
  // The list comes a server page at a time, filtered by the server. An item opened from elsewhere that is not on the
  // page shown is looked for in the whole list.
  const paged = usePagedList<RecurringItem>(`setup/recurring?kind=${filter}`);
  const summary = useResource<RecurringSummary>("setup/recurring/summary");
  const reloadAll = () => {
    paged.reload();
    summary.reload();
  };
  const pause = useRecurringPause(reloadAll);
  const missing =
    editing !== null &&
    editing !== "new" &&
    !paged.items.some((candidate) => candidate.id === editing);
  const streamed = useStreamedList<RecurringItem>(
    missing ? "setup/recurring" : null,
  );
  const recurring = missing ? streamed : paged;
  // Viewing needs only commitments access: shares carry their registration and costs their item's name. The vehicle
  // picker is for editors; the expense item picker loads once an editor opens.
  const options = useResource<VehicleOption[]>(
    canManage ? "setup/recurring/vehicle-options" : null,
  );
  const expenseItems = useResource<ExpenseItemOption[]>(
    canManage && editing ? "setup/expense-items/options" : null,
  );
  const items = recurring.items;

  // An existing item opens as soon as the page holding it arrives; a new one opens straight away. The vehicle
  // picker fills in when its own request lands.
  const editedItem =
    editing && editing !== "new"
      ? items.find((candidate) => candidate.id === editing)
      : undefined;
  const stillLoading = recurring.loading || recurring.pendingRows > 0;
  const editor = !editing ? null : editing === "new" || editedItem ? (
    <RecurringEditor
      item={editedItem}
      vehiclesLoading={canManage && options.loading}
      vehicles={editorVehicles(options.data ?? [], editedItem)}
      expenseItems={expenseItems.data}
      loadError={options.error || expenseItems.error}
      preselectVehicle={editing === "new" ? newForVehicle : undefined}
      startKind={filter === "savings" ? 2 : 1}
      canEdit={canManage && !editedItem?.partial}
      onCancel={() => setEditing(null)}
      onSaved={() => {
        setEditing(null);
        recurring.reload();
        if (recurring !== paged) paged.reload();
        summary.reload();
      }}
    />
  ) : (
    <MissingItemDialog
      error={recurring.error}
      loading={stillLoading}
      onClose={() => setEditing(null)}
    />
  );

  // Due dates count from the organization's business date, never the computer clock. Until the appearance has
  // loaded, next postings wait for it.
  const today = appearance?.businessDate;
  const hasActiveVehicle = (item: RecurringItem) =>
    item.allocations.some((allocation) => allocation.active !== false);
  const stopped = (item: RecurringItem) =>
    Boolean(item.stoppedFrom && (!today || item.stoppedFrom <= today));
  const finished = (item: RecurringItem) =>
    !hasActiveVehicle(item) ||
    stopped(item) ||
    (today && item.end && item.end < today)
      ? 1
      : 0;
  // The server puts running items first; within the page they read by name.
  const visible = [...paged.items].sort(
    (left, right) =>
      finished(left) - finished(right) || left.name.localeCompare(right.name),
  );
  const savings = filter === "savings";
  const fleet = activeFleet(options.data);
  const notes = summaryNotes(summary.data, kes);
  return (
    <>
      <PageHeader
        title="Scheduled expenses"
        actions={
          canManage ? (
            <Button tone="primary" onClick={() => setEditing("new")}>
              {savings ? "New saving" : "New scheduled expense"}
            </Button>
          ) : undefined
        }
      />
      {(paged.error || options.error || pause.error) && (
        <Banner>{streamError(paged) || options.error || pause.error}</Banner>
      )}
      <Tabs
        id="recurring"
        label="Show"
        options={[
          { value: "cost", label: "Scheduled expenses", note: notes?.cost },
          { value: "savings", label: "Savings", note: notes?.savings },
        ]}
        value={filter}
        onChange={setFilter}
      >
        <DataTable
          columns={columns(savings)}
          loading={paged.loading}
          pendingRows={paged.pendingRows}
          loadingLabel="Loading scheduled expenses and savings"
          isEmpty={!visible.length}
          failed={Boolean(paged.error)}
          emptyMessage="Nothing scheduled."
          footer={savings ? <SavingsFooter rows={visible} /> : undefined}
        >
          {visible.map((item) => (
            <RecurringRow
              key={item.id}
              item={item}
              savings={savings}
              today={today}
              stopped={stopped(item)}
              active={hasActiveVehicle(item)}
              fleet={fleet}
              canEdit={canManage && !item.partial}
              busy={pause.busyId !== null}
              onOpen={() => setEditing(item.id)}
              onRuns={() => setRunsFor(item)}
              onPause={() => void pause.toggle(item)}
            />
          ))}
        </DataTable>
      </Tabs>
      <ListPager list={paged} />
      {editor}
      {runsFor && (
        <RecurringRunsDialog item={runsFor} onClose={() => setRunsFor(null)} />
      )}
    </>
  );
}

// The picker's vehicles, plus any on the item it does not list (for example, when only viewing).
function editorVehicles(
  vehicles: VehicleOption[],
  item?: RecurringItem,
): VehicleOption[] {
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
