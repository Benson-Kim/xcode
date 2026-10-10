"use client";

import { useState } from "react";

import { plural } from "@xcode/shared/format";

import { useAppearance } from "../../lib/appearance";
import { streamError, useResource, useStreamedList } from "../../lib/data";
import { useFormats } from "../../lib/formats";
import type { ExpenseItemOption } from "../../lib/types";
import { RecurringEditor } from "../RecurringEditor";
import {
  recurringFrequency,
  recurringMonthlyEstimate,
  recurringNextPosting,
} from "../recurringPresentation";
import {
  Banner,
  Button,
  CellNote,
  DataTable,
  Dialog,
  FormSkeleton,
  PageHeader,
  ListPager,
  RowAction,
  RowActionGroup,
  SelectInput,
  StatusBadge,
  Tabs,
  Td,
  Toolbar,
  Tr,
} from "../ui";
import { usePagedList } from "../usePagedList";
import {
  costBucket,
  expenseBucketNames,
  type RecurringItem,
  RegPlate,
  type VehicleOption,
} from "./shared";

type Filter = "all" | "cost" | "savings";
type Status = "all" | "running" | "stopped";

function listPath(kind: Filter, companyId: string, status: Status) {
  const query = new URLSearchParams();
  if (kind !== "all") query.set("kind", kind);
  if (companyId !== "all") query.set("companyId", companyId);
  if (status !== "all") query.set("status", status);
  return `setup/recurring${query.toString() ? `?${query}` : ""}`;
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
  const [filter, setFilter] = useState<Filter>("cost");
  const [companyFilter, setCompanyFilter] = useState("all");
  const [status, setStatus] = useState<Status>("all");
  const [editing, setEditing] = useState<string | null>(
    newForVehicle ? "new" : (openItem ?? null),
  );
  // The list comes a server page at a time, filtered by the server. An item opened from elsewhere that is not on the
  // page shown is looked for in the whole list.
  const paged = usePagedList<RecurringItem>(
    listPath(filter, companyFilter, status),
  );
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
      }}
    />
  ) : (
    <Dialog
      open
      size="lg"
      title="Scheduled expense"
      onClose={() => setEditing(null)}
    >
      {recurring.error || !stillLoading ? (
        <Banner>
          {recurring.error || "This item is no longer in your list."}
        </Banner>
      ) : (
        <FormSkeleton cards={3} label="Loading the scheduled item" />
      )}
    </Dialog>
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
  // Companies come from the vehicle options, which only editors load: allocations carry no company.
  const companies = [
    ...new Map(
      (options.data ?? []).map((vehicle) => [
        vehicle.companyId,
        vehicle.companyName,
      ]),
    ).entries(),
  ].sort((left, right) => left[1].localeCompare(right[1]));
  // The server filters and puts running items first; within the page they read by name.
  const visible = [...paged.items].sort(
    (left, right) =>
      finished(left) - finished(right) || left.name.localeCompare(right.name),
  );
  const savings = filter === "savings";
  const fleet = options.data
    ? new Set(
        options.data
          .filter((vehicle) => vehicle.active !== false)
          .map((vehicle) => vehicle.id),
      )
    : null;
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
      {(paged.error || options.error) && (
        <Banner>{streamError(paged) || options.error}</Banner>
      )}
      <Tabs
        id="recurring"
        label="Show"
        options={[
          { value: "cost", label: "Scheduled expenses" },
          { value: "savings", label: "Savings" },
        ]}
        value={savings ? "savings" : "cost"}
        onChange={setFilter}
      >
        <RecurringFilters
          companies={companies}
          companyFilter={companyFilter}
          setCompanyFilter={setCompanyFilter}
          status={status}
          setStatus={setStatus}
        />
        <DataTable
          columns={[
            { label: savings ? "Saving" : "Item" },
            { label: "Vehicles" },
            {
              label: savings ? "Per vehicle" : "Amount per vehicle",
              numeric: true,
            },
            { label: "Each run", numeric: true },
            { label: "Runs" },
            { label: "Next run" },
            { label: "Status" },
            { label: "Actions", numeric: true },
          ]}
          loading={paged.loading}
          pendingRows={paged.pendingRows}
          loadingLabel="Loading scheduled expenses and savings"
          isEmpty={!visible.length}
          failed={Boolean(paged.error)}
          emptyMessage="Nothing scheduled."
        >
          {visible.map((item) => (
            <RecurringRow
              key={item.id}
              item={item}
              today={today}
              stopped={stopped(item)}
              active={hasActiveVehicle(item)}
              fleet={fleet}
              canEdit={canManage && !item.partial}
              onOpen={() => setEditing(item.id)}
            />
          ))}
        </DataTable>
      </Tabs>
      <ListPager list={paged} />
      {editor}
    </>
  );
}

function RecurringFilters({
  companies,
  companyFilter,
  setCompanyFilter,
  status,
  setStatus,
}: {
  companies: [string, string][];
  companyFilter: string;
  setCompanyFilter: (value: string) => void;
  status: Status;
  setStatus: (value: Status) => void;
}) {
  return (
    <Toolbar>
      {companies.length > 1 && (
        <>
          <label htmlFor="recurring-company" className="sr-only">
            Company
          </label>
          <SelectInput
            id="recurring-company"
            density="compact"
            inline
            value={companyFilter}
            onChange={(event) => setCompanyFilter(event.target.value)}
          >
            <option value="all">All companies</option>
            {companies.map(([id, name]) => (
              <option key={id} value={id}>
                {name}
              </option>
            ))}
          </SelectInput>
        </>
      )}
      <label htmlFor="recurring-status" className="sr-only">
        Show
      </label>
      <SelectInput
        id="recurring-status"
        density="compact"
        inline
        value={status}
        onChange={(event) => setStatus(event.target.value as Status)}
      >
        <option value="all">All</option>
        <option value="running">Running</option>
        <option value="stopped">Stopped</option>
      </SelectInput>
    </Toolbar>
  );
}

function RecurringStatus({
  item,
  today,
  stopped,
  active,
  next,
}: {
  item: RecurringItem;
  today?: string;
  stopped: boolean;
  active: boolean;
  next: string | null;
}) {
  const { formatDateOnly } = useFormats();
  const futureStop =
    item.stoppedFrom && today && item.stoppedFrom > today
      ? item.stoppedFrom
      : null;
  if (stopped) return <StatusBadge tone="off">Stopped</StatusBadge>;
  if (!active) return <StatusBadge tone="off">No active vehicles</StatusBadge>;
  if (futureStop)
    return (
      <StatusBadge tone="warn">Stops {formatDateOnly(futureStop)}</StatusBadge>
    );
  if (today && !next) return <StatusBadge tone="neutral">Finished</StatusBadge>;
  return <StatusBadge tone="ok">Running</StatusBadge>;
}

function RecurringRow({
  item,
  today,
  stopped,
  active,
  fleet,
  canEdit,
  onOpen,
}: {
  item: RecurringItem;
  today?: string;
  stopped: boolean;
  active: boolean;
  fleet: Set<string> | null;
  canEdit: boolean;
  onOpen: () => void;
}) {
  const { formatDateOnly, formatNumber, kes } = useFormats();
  const next =
    stopped || !active || !today ? null : recurringNextPosting(item, today);
  const outOfFleetCount = item.allocations.filter(
    (allocation) => allocation.active === false,
  ).length;
  // What posts now. `amount` is the saved total, which still counts vehicles not in the fleet today.
  const posting = item.activeAmount ?? item.amount;
  const posted = item.allocations.filter(
    (allocation) => allocation.active !== false,
  );
  const shares = posted.length ? posted : item.allocations;
  const share =
    shares.length &&
    shares.every((allocation) => allocation.amount === shares[0].amount)
      ? formatNumber(shares[0].amount)
      : "Varies";
  const action = canEdit ? "Edit" : "Open";
  const postingNote = [
    item.partial ? "Your vehicles' share." : "",
    posting !== item.amount
      ? `${kes(item.amount)} in total, with ${outOfFleetCount === 1 ? "1 share for a vehicle" : `${outOfFleetCount} shares for vehicles`} not in the fleet today.`
      : "",
    `About ${kes(recurringMonthlyEstimate(posting, item.frequency))} a month`,
  ]
    .filter(Boolean)
    .join(" ");
  return (
    <Tr>
      <Td label="Item" className="item nw" title={itemNote(item)}>
        {item.name}
      </Td>
      <Td label="Vehicles" className="nw">
        <RecurringVehicles
          item={item}
          fleet={fleet}
          outOfFleetCount={outOfFleetCount}
        />
      </Td>
      <Td label="Amount per vehicle" numeric>
        {share}
      </Td>
      <Td label="Each run" numeric className="tot" title={postingNote}>
        {formatNumber(posting)}
      </Td>
      <Td label="Runs" className="nw">
        {recurringFrequency(item)}
        <CellNote>
          {item.end
            ? `${formatDateOnly(item.start)} to ${formatDateOnly(item.end)}`
            : `From ${formatDateOnly(item.start)}, no end date`}
        </CellNote>
      </Td>
      <Td label="Next run" className="nw">
        {next ? formatDateOnly(next) : !today ? "—" : ""}
      </Td>
      <Td label="Status" className="nw">
        <RecurringStatus
          item={item}
          today={today}
          stopped={stopped}
          active={active}
          next={next}
        />
      </Td>
      <Td numeric>
        <RowActionGroup>
          <RowAction aria-label={`${action} ${item.name}`} onClick={onOpen}>
            {action}
          </RowAction>
        </RowActionGroup>
      </Td>
    </Tr>
  );
}

// One plate for one vehicle, "All vehicles" when it covers every active vehicle the viewer can see, else a count
// with the registrations on hover.
function RecurringVehicles({
  item,
  fleet,
  outOfFleetCount,
}: {
  item: RecurringItem;
  fleet: Set<string> | null;
  outOfFleetCount: number;
}) {
  const registrations = item.allocations
    .map((allocation) => allocation.registration)
    .filter((registration): registration is string => Boolean(registration));
  const covered = new Set(
    item.allocations
      .filter((allocation) => allocation.active !== false)
      .map((allocation) => allocation.vehicleId),
  );
  const everyVehicle =
    !item.partial &&
    fleet !== null &&
    fleet.size > 1 &&
    [...fleet].every((id) => covered.has(id));
  const title = [
    registrations.join(", "),
    outOfFleetCount ? `${outOfFleetCount} not in the fleet today` : "",
    item.partial ? "plus vehicles you can't see" : "",
  ]
    .filter(Boolean)
    .join("; ");
  if (item.allocations.length === 1 && !item.partial && registrations.length)
    return <RegPlate>{registrations[0]}</RegPlate>;
  return (
    <span title={title || undefined}>
      {everyVehicle
        ? "All vehicles"
        : plural(item.allocations.length, "vehicle", "vehicles")}
    </span>
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

// The note and, for a cost, the bucket it counts under (a cost saved without one counts as a recurring charge).
function itemNote(item: RecurringItem) {
  const bucket = costBucket(item);
  const text = [item.note, bucket ? expenseBucketNames[bucket] : null]
    .filter(Boolean)
    .join(". ");
  return text || undefined;
}
