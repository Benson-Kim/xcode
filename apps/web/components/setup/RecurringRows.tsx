"use client";

import { plural } from "@xcode/shared/format";

import { useFormats } from "../../lib/formats";
import {
  recurringFrequency,
  recurringMonthlyEstimate,
  recurringNextPosting,
} from "../recurringPresentation";
import { RowAction, RowActionGroup, StatusBadge, Td, Tr } from "../ui";
import {
  costBucket,
  expenseBucketNames,
  type RecurringItem,
  RegPlate,
} from "./shared";

function RecurringStatus({
  item,
  today,
  stopped,
  active,
  scheduled,
}: {
  item: RecurringItem;
  today?: string;
  stopped: boolean;
  active: boolean;
  scheduled: string | null;
}) {
  const { formatDateOnly } = useFormats();
  const futureStop =
    item.stoppedFrom && today && item.stoppedFrom > today
      ? item.stoppedFrom
      : null;
  if (stopped) return <StatusBadge tone="off">Stopped</StatusBadge>;
  if (!active) return <StatusBadge tone="off">No active vehicles</StatusBadge>;
  if (item.pausedFrom) return <StatusBadge tone="warn">Paused</StatusBadge>;
  if (futureStop)
    return (
      <StatusBadge tone="warn">Stops {formatDateOnly(futureStop)}</StatusBadge>
    );
  if (today && !scheduled)
    return <StatusBadge tone="neutral">Finished</StatusBadge>;
  return <StatusBadge tone="ok">Running</StatusBadge>;
}

export function RecurringRow({
  item,
  savings,
  today,
  stopped,
  active,
  fleet,
  canEdit,
  busy,
  onOpen,
  onRuns,
  onPause,
}: {
  item: RecurringItem;
  savings: boolean;
  today?: string;
  stopped: boolean;
  active: boolean;
  fleet: Set<string> | null;
  canEdit: boolean;
  busy: boolean;
  onOpen: () => void;
  onRuns: () => void;
  onPause: () => void;
}) {
  const { formatDateOnly, formatNumber, kes } = useFormats();
  const scheduled =
    stopped || !active || !today ? null : recurringNextPosting(item, today);
  const next = item.pausedFrom ? null : scheduled;
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
  const ended = Boolean(today && item.end && item.end < today);
  const canPause =
    canEdit && active && !stopped && !ended && !(today && !scheduled);
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
      {!savings && (
        <Td label="Each run" numeric className="tot" title={postingNote}>
          {formatNumber(posting)}
        </Td>
      )}
      <Td label="Runs" className={savings ? undefined : "nw"}>
        {recurringFrequency(item)}
        {item.end && (
          <span className="note">Until {formatDateOnly(item.end)}</span>
        )}
      </Td>
      {savings ? (
        <>
          <Td label="Last run" className="nw">
            {item.lastRun && (
              <>
                {formatDateOnly(item.lastRun)}
                <span className="note">{item.lastRunVehicles ?? 0} saved</span>
              </>
            )}
          </Td>
          <Td label="Balance" numeric className="tot">
            {item.balance != null && formatNumber(item.balance)}
          </Td>
        </>
      ) : (
        <Td label="Next run" className="nw">
          {next ? formatDateOnly(next) : !today ? "—" : ""}
        </Td>
      )}
      <Td label="Status" className="nw">
        <RecurringStatus
          item={item}
          today={today}
          stopped={stopped}
          active={active}
          scheduled={scheduled}
        />
      </Td>
      <Td numeric>
        <RowActionGroup>
          {savings && (
            <RowAction aria-label={`Runs ${item.name}`} onClick={onRuns}>
              Runs
            </RowAction>
          )}
          <RowAction aria-label={`${action} ${item.name}`} onClick={onOpen}>
            {action}
          </RowAction>
          {canPause && (
            <RowAction
              tone={item.pausedFrom ? "ok" : "warn"}
              aria-label={`${item.pausedFrom ? "Resume" : "Pause"} ${item.name}`}
              disabled={busy}
              onClick={onPause}
            >
              {item.pausedFrom ? "Resume" : "Pause"}
            </RowAction>
          )}
        </RowActionGroup>
      </Td>
    </Tr>
  );
}

export function SavingsFooter({ rows }: { rows: RecurringItem[] }) {
  const { formatNumber } = useFormats();
  const balance = rows.reduce((sum, row) => sum + (row.balance ?? 0), 0);
  return (
    <tr>
      <td colSpan={5}>{plural(rows.length, "saving", "savings")}</td>
      <td className="r">{formatNumber(balance)}</td>
      <td colSpan={2} />
    </tr>
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
  if (everyVehicle || !registrations.length)
    return (
      <span title={title || undefined}>
        {everyVehicle
          ? "All vehicles"
          : plural(item.allocations.length, "vehicle", "vehicles")}
      </span>
    );
  // As the design: the plates of the vehicles it covers.
  return (
    <div className="splitv" title={title || undefined}>
      {registrations.map((registration) => (
        <RegPlate key={registration}>{registration}</RegPlate>
      ))}
    </div>
  );
}

// The note and, for a cost, the bucket it counts under (a cost saved without one counts as a recurring charge).
function itemNote(item: RecurringItem) {
  const bucket = costBucket(item);
  const text = [item.note, bucket ? expenseBucketNames[bucket] : null]
    .filter(Boolean)
    .join(". ");
  return text || undefined;
}
