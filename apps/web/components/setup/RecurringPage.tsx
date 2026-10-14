"use client";

import { useState } from "react";

import { MONTH_NAMES } from "@xcode/shared/dates";

import { useAppearance } from "../../lib/appearance";
import { streamError, useResource, useStreamedList } from "../../lib/data";
import { useFormats } from "../../lib/formats";
import { useSession } from "../../lib/session-context";
import type { ExpenseItemOption, MyScope } from "../../lib/types";
import { RecurringEditor } from "../RecurringEditor";
import {
  BandFigure,
  BandStats,
  Banner,
  Button,
  DataTable,
  Dialog,
  FormSkeleton,
  HeroBand,
  ListPager,
  PageHeader,
} from "../ui";
import { usePagedList } from "../usePagedList";
import { RecurringRow, SavingsFooter } from "./RecurringRows";
import { RecurringRunsDialog } from "./RecurringRunsDialog";
import type { RecurringItem, RecurringSummary, VehicleOption } from "./shared";
import { useRecurringPause } from "./useRecurringPause";

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

// "October 2026", from the summary's month.
function monthLabel(from: string | undefined) {
  if (!from) return "";
  return `${MONTH_NAMES[Number(from.slice(5, 7)) - 1]} ${from.slice(0, 4)}`;
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
  title,
  error,
  loading,
  onClose,
}: {
  title: string;
  error: string;
  loading: boolean;
  onClose: () => void;
}) {
  return (
    <Dialog open size="md" title={title} onClose={onClose}>
      {error || !loading ? (
        <Banner>{error || "This item is no longer in your list."}</Banner>
      ) : (
        <FormSkeleton cards={3} label="Loading the scheduled item" />
      )}
    </Dialog>
  );
}

// Scheduled expenses and Savings are two pages on one model (v2.30). The page sets the kind and which rights
// apply: scheduled.* for expenses, savings.* for savings. Each has its own headline bar.
export function RecurringPage({
  kind = "expense",
  canManage = false,
  openItem,
  newForVehicle,
}: {
  kind?: "expense" | "saving";
  // The released key commitments.manage, which still grants everything here.
  canManage?: boolean;
  openItem?: string;
  newForVehicle?: string;
}) {
  const { can } = useSession();
  const { appearance } = useAppearance();
  const { formatNumber } = useFormats();
  const savings = kind === "saving";
  const prefix = savings ? "savings" : "scheduled";
  const canAdd = can(`${prefix}.add`) || canManage;
  const canEdit = can(`${prefix}.edit`) || canManage;
  const canPause = can(`${prefix}.pause`) || canManage;
  const [runsFor, setRunsFor] = useState<RecurringItem | null>(null);
  const [editing, setEditing] = useState<string | null>(
    newForVehicle ? "new" : (openItem ?? null),
  );
  // The list comes a server page at a time, filtered by the server. An item opened from elsewhere that is not on the
  // page shown is looked for in the whole list.
  const paged = usePagedList<RecurringItem>(
    `setup/recurring?kind=${savings ? "savings" : "cost"}`,
  );
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
  const options = useResource<VehicleOption[]>(
    canAdd || canEdit ? "setup/recurring/vehicle-options" : null,
  );
  const mine = useResource<MyScope>(
    canAdd || canEdit ? "setup/access/me" : null,
  );
  const expenseItems = useResource<ExpenseItemOption[]>(
    !savings && (canAdd || canEdit) && editing
      ? "setup/expense-items/options"
      : null,
  );
  const items = recurring.items;

  const editedItem =
    editing && editing !== "new"
      ? items.find((candidate) => candidate.id === editing)
      : undefined;
  const stillLoading = recurring.loading || recurring.pendingRows > 0;
  const editor = !editing ? null : editing === "new" || editedItem ? (
    <RecurringEditor
      item={editedItem}
      kind={savings ? 2 : 1}
      vehiclesLoading={options.loading}
      vehicles={editorVehicles(options.data ?? [], editedItem)}
      expenseItems={expenseItems.data}
      fullScope={mine.data?.allCompanies ?? false}
      loadError={options.error || expenseItems.error}
      preselectVehicle={editing === "new" ? newForVehicle : undefined}
      canEdit={(editedItem ? canEdit : canAdd) && !editedItem?.partial}
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
      title={savings ? "Saving" : "Scheduled expense"}
      error={recurring.error}
      loading={stillLoading}
      onClose={() => setEditing(null)}
    />
  );

  // Due dates count from the organization's business date, never the computer clock.
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
  const fleet = activeFleet(options.data);
  const month = monthLabel(summary.data?.from);
  const counts = {
    running:
      (savings ? summary.data?.runningSavings : summary.data?.runningCosts) ??
      paged.items.filter((item) => !item.pausedFrom && !finished(item)).length,
    paused:
      (savings ? summary.data?.pausedSavings : summary.data?.pausedCosts) ??
      paged.items.filter((item) => item.pausedFrom).length,
  };
  return (
    <>
      <PageHeader
        title={savings ? "Savings" : "Scheduled expenses"}
        actions={
          canAdd ? (
            <Button tone="primary" onClick={() => setEditing("new")}>
              {savings ? "New saving" : "New scheduled expense"}
            </Button>
          ) : undefined
        }
      />
      <HeroBand>
        {summary.data ? (
          <>
            <BandFigure
              label={savings ? "Savings balance" : `Due in ${month}`}
              value={formatNumber(
                savings ? summary.data.savingsBalance : summary.data.costsDue,
              )}
            />
            <BandStats
              items={[
                ...(savings
                  ? [
                      {
                        label: `Saved in ${month}`,
                        value: formatNumber(summary.data.saved),
                      },
                    ]
                  : []),
                { label: "Running", value: String(counts.running) },
                { label: "Paused", value: String(counts.paused) },
              ]}
            />
          </>
        ) : (
          <BandFigure label={savings ? "Savings balance" : "Due"} value="" />
        )}
      </HeroBand>
      {(paged.error || options.error || pause.error || summary.error) && (
        <Banner>
          {streamError(paged) || options.error || pause.error || summary.error}
        </Banner>
      )}
      <DataTable
        columns={columns(savings)}
        loading={paged.loading}
        pendingRows={paged.pendingRows}
        loadingLabel={
          savings ? "Loading savings" : "Loading scheduled expenses"
        }
        isEmpty={!visible.length}
        failed={Boolean(paged.error)}
        emptyMessage={savings ? "No savings yet." : "Nothing scheduled."}
        footer={
          savings && visible.length ? (
            <SavingsFooter rows={visible} />
          ) : undefined
        }
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
            canEdit={canEdit && !item.partial}
            canPause={canPause && !item.partial}
            busy={pause.busyId !== null}
            onOpen={() => setEditing(item.id)}
            onRuns={() => setRunsFor(item)}
            onPause={() => void pause.toggle(item)}
          />
        ))}
      </DataTable>
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
