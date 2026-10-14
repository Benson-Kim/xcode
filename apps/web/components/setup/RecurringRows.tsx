"use client";

import { plural } from "@xcode/shared/format";

import { useFormats } from "../../lib/formats";
import {
  recurringFrequency,
  recurringNextPosting,
} from "../recurringPresentation";
import { RowAction, RowActionGroup, StatusBadge, Td, Tr } from "../ui";
import { type RecurringItem, RegPlate } from "./shared";

// The revenue rule of a saving in words: "Every run", or "Revenue KES 12,000 or more over the 7 days to the run".
export function ruleText(
  item: Pick<RecurringItem, "condition">,
  kes: (amount: number) => string,
) {
  const rule = item.condition;
  if (!rule) return "Every run";
  const window =
    rule.days === 1 ? "that day" : `over the ${rule.days} days to the run`;
  return `Revenue ${kes(rule.min)} or more ${window}`;
}

// What the last run did: "3 saved, 1 skipped, 2 waiting for revenue".
export function runTally(
  states: { saved: number; skipped: number; held: number } | null | undefined,
  fallback?: number,
) {
  if (!states) return fallback !== undefined ? `${fallback} saved` : "";
  return [
    states.saved ? `${states.saved} saved` : "",
    states.skipped ? `${states.skipped} skipped` : "",
    states.held ? `${states.held} waiting for revenue` : "",
  ]
    .filter(Boolean)
    .join(", ");
}

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
  canPause,
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
  canPause: boolean;
  busy: boolean;
  onOpen: () => void;
  onRuns: () => void;
  onPause: () => void;
}) {
  const { formatDateOnly, formatNumber, kes } = useFormats();
  const scheduled =
    stopped || !active || !today
      ? null
      : (item.nextRun ?? recurringNextPosting(item, today));
  const next = item.pausedFrom ? null : scheduled;
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
  const ended = Boolean(today && item.end && item.end < today);
  const pausable =
    canPause && active && !stopped && !ended && !(today && !scheduled);
  return (
    <Tr>
      <Td label={savings ? "Saving" : "Item"} className="item nw">
        {item.name}
      </Td>
      <Td label="Vehicles">
        <RecurringVehicles item={item} fleet={fleet} />
      </Td>
      <Td label={savings ? "Per vehicle" : "Amount per vehicle"} numeric>
        {share}
      </Td>
      {!savings && (
        <Td label="Each run" numeric className="tot">
          {formatNumber(posting)}
        </Td>
      )}
      <Td label="Runs" className={savings ? undefined : "nw"}>
        {recurringFrequency(item)}
        {savings && item.condition && (
          <span className="note">{ruleText(item, kes)}</span>
        )}
      </Td>
      {savings ? (
        <>
          <Td label="Last run" className="nw">
            {item.lastRun && (
              <>
                {formatDateOnly(item.lastRun)}
                <span className="note">
                  {runTally(item.lastRunStates, item.lastRunVehicles ?? 0)}
                </span>
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
          <RowAction
            aria-label={`${canEdit ? "Edit" : "Open"} ${item.name}`}
            onClick={onOpen}
          >
            {canEdit ? "Edit" : "Open"}
          </RowAction>
          {pausable && (
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

// "All vehicles" when it covers every active vehicle the viewer can see, else the plates of the vehicles it covers.
function RecurringVehicles({
  item,
  fleet,
}: {
  item: RecurringItem;
  fleet: Set<string> | null;
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
    item.partial ? "plus vehicles you can't see" : "",
  ]
    .filter(Boolean)
    .join("; ");
  if (everyVehicle || !registrations.length)
    return (
      <span title={title || undefined}>
        {everyVehicle
          ? "All vehicles"
          : plural(item.allocations.length, "vehicle", "vehicles")}
      </span>
    );
  if (registrations.length === 1 && !item.partial)
    return <RegPlate>{registrations[0]}</RegPlate>;
  return (
    <div className="splitv" title={title || undefined}>
      {registrations.map((registration) => (
        <RegPlate key={registration}>{registration}</RegPlate>
      ))}
    </div>
  );
}
