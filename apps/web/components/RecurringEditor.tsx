"use client";

import { useState } from "react";
import { useAppearance } from "../lib/appearance";
import { apiRequest } from "../lib/data";
import {
  firstOfMonth,
  formatDateOnly,
  monthNames,
  ordinal,
  recurringFrequency,
  recurringMonthlyEstimate,
  recurringNextPostings,
} from "./recurringPresentation";
import {
  BalancePanel,
  Banner,
  Button,
  Card,
  CardHeader,
  Chip,
  ChipGroup,
  Choice,
  ChoiceField,
  CurrencyInput,
  ErrorSummary,
  ErrorText,
  Field,
  FormActions,
  FormLayout,
  Grid2,
  GroupLabel,
  Hint,
  ListSkeleton,
  Note,
  PageHeader,
  SelectInput,
  Spacer,
  TextInput,
  useToast,
} from "./ui";
import { kes, plural } from "../lib/format";
import type { ExpenseBucket, ExpenseItemOption } from "../lib/types";
import {
  costBucket,
  expenseBucketNames,
  legacyCostTypeNames,
  type RecurringItem,
  type VehicleOption,
} from "./setup/shared";

type Props = {
  item?: RecurringItem;
  vehicles: VehicleOption[];
  // The active expense items a cost can pick (GET expense-items/options). Undefined while they load, or when only viewing.
  expenseItems?: ExpenseItemOption[];
  onCancel: () => void;
  onSaved: () => Promise<void> | void;
  canEdit?: boolean;
  preselectVehicle?: string;
  // The vehicle picker's list is still loading; the rest of the form is usable meanwhile.
  vehiclesLoading?: boolean;
  // Why a picker's list could not be loaded.
  loadError?: string;
};

type Errors = Partial<
  Record<
    | "expenseItem"
    | "name"
    | "note"
    | "amount"
    | "frequency"
    | "start"
    | "end"
    | "allocations",
    string
  >
>;

// An expense item in the picker. `off` marks the item a saved cost uses once it is no longer active.
type ItemChoice = {
  id: string;
  name: string;
  categoryId: string;
  categoryName: string;
  bucket: ExpenseBucket | null;
  off: boolean;
};

const NOTE_LIMIT = 200;

// Every day (1) stays only on items saved before; savings post every week or every month.
const frequencies = [
  { value: 2, label: "Every week" },
  { value: 3, label: "Every month" },
  { value: 4, label: "Every year" },
];

const weekdays = [
  { value: 1, label: "Monday" },
  { value: 2, label: "Tuesday" },
  { value: 3, label: "Wednesday" },
  { value: 4, label: "Thursday" },
  { value: 5, label: "Friday" },
  { value: 6, label: "Saturday" },
  { value: 0, label: "Sunday" },
];

// Splits a total into whole cents, giving the first vehicles the remainder so it adds up exactly.
function splitAmountEvenly(total: number, vehicleIds: string[]) {
  if (!vehicleIds.length) return {};
  const totalCents = Math.round(total * 100);
  const baseCents = Math.floor(totalCents / vehicleIds.length);
  const remainder = totalCents - baseCents * vehicleIds.length;
  return Object.fromEntries(
    vehicleIds.map((vehicleId, index) => [
      vehicleId,
      formatShare((baseCents + (index < remainder ? 1 : 0)) / 100),
    ]),
  );
}

// Whole amounts without ".00", as the design shows them.
function formatShare(amount: number) {
  return Number.isInteger(amount) ? String(amount) : amount.toFixed(2);
}

export function RecurringEditor({
  item,
  vehicles,
  expenseItems,
  onCancel,
  onSaved,
  canEdit = true,
  preselectVehicle,
  vehiclesLoading = false,
  loadError,
}: Props) {
  const toast = useToast();
  const { appearance } = useAppearance();
  // "Today" is always the organization's business date, never the computer clock. It is undefined until the
  // appearance has loaded, and a new item's start date defaults to it as soon as it arrives.
  const today = appearance?.businessDate;
  const earliestStart = today ? firstOfMonth(today) : undefined;
  const isNew = !item;
  const [kind, setKind] = useState(item?.kind || 1);
  const [expenseItemId, setExpenseItemId] = useState(item?.expenseItemId ?? "");
  const [name, setName] = useState(item?.kind === 2 ? item.name : "");
  const [note, setNote] = useState(item?.note ?? "");
  // The saved total is the sum of every share, including those of vehicles not in the fleet today, so an existing
  // item always opens balanced.
  const [amount, setAmount] = useState(
    item ? formatShare(item.allocations.reduce((sum, allocation) => sum + allocation.amount, 0)) : "",
  );
  const [frequency, setFrequency] = useState(item?.frequency || 3);
  const [weekday, setWeekday] = useState(
    String(item?.frequency === 2 ? (item.day ?? 6) : 6),
  );
  const [monthDay, setMonthDay] = useState(
    item?.frequency === 3 || item?.frequency === 4
      ? item.lastDay
        ? "last"
        : String(item.day ?? 1)
      : "1",
  );
  const [month, setMonth] = useState(String(item?.month ?? 1));
  const [startInput, setStart] = useState<string | null>(item?.start ?? null);
  const start = startInput ?? today ?? "";
  const [end, setEnd] = useState(item?.end || "");
  const [noEnd, setNoEnd] = useState(!item?.end);
  // Only stopping asks for a typed reason; the server writes the reason for adding or changing an item.
  const [stopReason, setStopReason] = useState("");
  const initialSelection =
    item?.allocations.map((allocation) => allocation.vehicleId) ||
    (preselectVehicle ? [preselectVehicle] : []);
  const [selected, setSelected] = useState<string[]>(initialSelection);
  const [shares, setShares] = useState<Record<string, string>>(
    Object.fromEntries(
      item?.allocations.map((allocation) => [
        allocation.vehicleId,
        formatShare(allocation.amount),
      ]) || [],
    ),
  );
  const [manualAllocations, setManualAllocations] = useState(Boolean(item));
  const [errors, setErrors] = useState<Errors>({});
  const [saveError, setSaveError] = useState("");
  const [splitNotice, setSplitNotice] = useState("");
  const [confirmStop, setConfirmStop] = useState(false);
  // Shown beside the reason field, not at the top of the page, so it is next to what needs fixing.
  const [stopError, setStopError] = useState("");
  const [busy, setBusy] = useState(false);

  const total = Number(amount) || 0;
  const allocationTotal = selected.reduce(
    (sum, vehicleId) => sum + (Number(shares[vehicleId]) || 0),
    0,
  );
  const difference =
    Math.round(total * 100) - Math.round(allocationTotal * 100);
  const isBalanced = selected.length > 0 && total > 0 && difference === 0;
  const stopped = Boolean(item?.stoppedFrom && (!today || item.stoppedFrom <= today));
  const futureStop = item?.stoppedFrom && today && item.stoppedFrom > today ? item.stoppedFrom : null;
  const startLocked = Boolean(item && (!today || item.start < today));
  const disabled = !canEdit || stopped || busy;
  const companies = [
    ...new Map(
      vehicles.map((vehicle) => [vehicle.companyId, vehicle.companyName]),
    ).entries(),
  ];

  // Items saved before expense items keep their old cost type and daily schedule until someone changes them.
  const legacyCategory = Boolean(item?.kind === 1 && !item.expenseItemId);
  const legacyCategoryName = legacyCostTypeNames[item?.category || 4];
  // Until an expense item is chosen, an old row keeps counting in its old type's bucket.
  const legacyBucket = item && legacyCategory ? costBucket(item) : null;
  const legacyDaily = item?.frequency === 1;
  const itemChoices: ItemChoice[] = (expenseItems ?? []).map((option) => ({
    ...option,
    off: false,
  }));
  if (
    item?.expenseItemId &&
    !itemChoices.some((choice) => choice.id === item.expenseItemId)
  )
    itemChoices.unshift({
      id: item.expenseItemId,
      name: item.expenseItemName || item.name,
      categoryId: "",
      categoryName: "",
      bucket: item.bucket ?? null,
      off: expenseItems !== undefined,
    });
  const picked = itemChoices.find((choice) => choice.id === expenseItemId);
  const itemGroups = [
    ...itemChoices
      .reduce(
        (groups, choice) =>
          groups.set(choice.categoryId, [
            ...(groups.get(choice.categoryId) ?? []),
            choice,
          ]),
        new Map<string, ItemChoice[]>(),
      )
      .values(),
  ];
  const countedAs = picked?.bucket
    ? expenseBucketNames[picked.bucket]
    : legacyBucket && !expenseItemId
      ? expenseBucketNames[legacyBucket]
      : undefined;

  // A vehicle not in the fleet today (left, or not joined yet) keeps its share, read-only: it stays in the total but
  // does not post.
  const inFleet = (vehicleId: string) =>
    vehicles.find((vehicle) => vehicle.id === vehicleId)?.active !== false;
  const outOfFleetShares = (vehicleIds: string[]) =>
    Object.fromEntries(
      vehicleIds
        .filter((vehicleId) => !inFleet(vehicleId))
        .map((vehicleId) => [vehicleId, shares[vehicleId] ?? "0"]),
    );
  // Splits what is left after the shares of vehicles not in the fleet across the vehicles that are.
  function splitAcrossFleet(amountTotal: number, vehicleIds: string[]) {
    const kept = outOfFleetShares(vehicleIds);
    const keptTotal = Object.values(kept).reduce((sum, share) => sum + (Number(share) || 0), 0);
    return {
      ...kept,
      ...splitAmountEvenly(Math.max(0, amountTotal - keptTotal), vehicleIds.filter(inFleet)),
    };
  }

  function updateAmount(value: string) {
    setAmount(value);
    setSplitNotice("");
    if (!manualAllocations)
      setShares(splitAcrossFleet(Number(value) || 0, selected));
  }

  function updateKind(value: number) {
    setKind(value);
    // Savings are set aside every week or every month, never yearly.
    if (value === 2 && frequency === 4) setFrequency(3);
  }

  function updateSelection(vehicleId: string, checked: boolean) {
    const vehicle = vehicles.find((candidate) => candidate.id === vehicleId);
    if (checked && vehicle?.active === false) return;
    const next = checked
      ? [...new Set([...selected, vehicleId])]
      : selected.filter((id) => id !== vehicleId);
    setSelected(next);
    setSplitNotice("");
    if (!checked && vehicle?.active === false) {
      // Removing the share of a vehicle not in the fleet also takes it off the amount, so the form stays balanced.
      const share = Number(shares[vehicleId]) || 0;
      setAmount(formatShare(Math.max(0, total - share)));
      setShares((current) => {
        const nextShares = { ...current };
        delete nextShares[vehicleId];
        return nextShares;
      });
      setSplitNotice(`Took ${vehicle.registration}'s ${kes(share)} share off the amount.`);
      return;
    }
    if (!manualAllocations) setShares(splitAcrossFleet(total, next));
    else
      setShares((current) => {
        const nextShares = { ...current };
        if (checked) nextShares[vehicleId] = "0";
        else delete nextShares[vehicleId];
        return nextShares;
      });
  }

  function selectCompany(companyId: string) {
    const next = [
      ...new Set([
        ...selected,
        ...vehicles
          .filter((vehicle) => vehicle.companyId === companyId && vehicle.active !== false)
          .map((vehicle) => vehicle.id),
      ]),
    ];
    setSelected(next);
    setSplitNotice("");
    setManualAllocations(false);
    setShares(splitAcrossFleet(total, next));
  }

  const vehicleName = (vehicleId: string) =>
    vehicles.find((vehicle) => vehicle.id === vehicleId)?.registration ?? "A vehicle";
  const postingIds = selected.filter(inFleet);
  const outOfFleetIds = selected.filter((vehicleId) => !inFleet(vehicleId));
  // What posts on each due date: the shares of the vehicles still in the fleet.
  const postingTotal = postingIds.reduce(
    (sum, vehicleId) => sum + (Number(shares[vehicleId]) || 0),
    0,
  );

  function splitEqually() {
    if (!total || !postingIds.length) return;
    const shared = splitAcrossFleet(total, selected);
    setManualAllocations(false);
    setShares(shared);
    const split = postingIds.reduce((sum, vehicleId) => sum + (Number(shared[vehicleId]) || 0), 0);
    setSplitNotice(
      `Split ${kes(split)} equally across ${plural(postingIds.length, "vehicle", "vehicles")}.`,
    );
  }

  const periodIsValid = noEnd || Boolean(end && end >= start);
  const lastDay = (frequency === 3 || frequency === 4) && monthDay === "last";
  const schedule = {
    frequency,
    day:
      frequency === 2
        ? Number(weekday)
        : frequency === 1 || lastDay
          ? null
          : Number(monthDay),
    lastDay,
    month: frequency === 4 ? Number(month) : null,
    start,
    end: noEnd ? null : end || null,
  };
  const previewDates =
    today && postingTotal > 0 && postingIds.length && periodIsValid
      ? recurringNextPostings(schedule, today, 5)
      : [];
  const title = kind === 1 ? picked?.name || item?.name || "" : name.trim();

  async function save() {
    if (disabled) return;
    const next: Errors = {};
    if (kind === 1 && !picked) next.expenseItem = "Choose the expense item.";
    else if (kind === 1 && picked?.off)
      next.expenseItem = "This item is turned off. Choose another expense item.";
    if (kind === 2 && !name.trim()) next.name = "Enter a name.";
    if (note.trim().length > NOTE_LIMIT)
      next.note = `Keep the note to ${NOTE_LIMIT} characters.`;
    if (total <= 0) next.amount = "Enter the amount in KES.";
    if (frequency === 1)
      next.frequency = "Every day is no longer offered. Choose how often it posts.";
    if (!start) next.start = "Enter the start date.";
    else if (earliestStart && start < earliestStart && (isNew || start !== item.start))
      next.start = `Start on or after ${formatDateOnly(earliestStart)}. Anything earlier is a one-off expense, not a schedule.`;
    if (!noEnd && (!end || end < start))
      next.end = "The end date must be on or after the start date.";
    if (!selected.length) next.allocations = "Tick at least one vehicle.";
    else if (difference !== 0)
      next.allocations = `The split must add up to ${kes(total)}. It is ${kes(allocationTotal)}.`;
    setErrors(next);
    setSaveError("");
    if (Object.keys(next).length) return;
    const allocations = selected.map((vehicleId) => ({
      vehicleId,
      amount: Number(shares[vehicleId]) || 0,
    }));
    setBusy(true);
    try {
      await apiRequest(
        isNew ? "setup/recurring" : `setup/recurring/${item.id}`,
        {
          method: isNew ? "POST" : "PUT",
          body: JSON.stringify({
            // A cost takes its name and bucket from its expense item on the server.
            name: title,
            kind,
            category: null,
            amount: total,
            frequency,
            day: schedule.day,
            lastDay: schedule.lastDay,
            start,
            end: noEnd ? null : end,
            allocations,
            expenseItemId: kind === 1 ? expenseItemId : null,
            note: note.trim() || null,
            month: schedule.month,
          }),
        },
      );
      toast(
        isNew
          ? `${title} added. It now posts to ${plural(allocations.length, "vehicle", "vehicles")}.`
          : `Changes saved for ${title}.`,
      );
      await onSaved();
    } catch (value) {
      setSaveError((value as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function stop() {
    if (!item || disabled) return;
    if (!confirmStop) return setConfirmStop(true);
    if (!stopReason.trim()) {
      setStopError("Give a reason for stopping this item.");
      return;
    }
    setStopError("");
    setBusy(true);
    try {
      await apiRequest(`setup/recurring/${item.id}/stop`, {
        method: "POST",
        body: JSON.stringify({
          confirmed: true,
          reason: stopReason.trim(),
        }),
      });
      toast(`${item.name} stopped.`);
      await onSaved();
    } catch (value) {
      setSaveError((value as Error).message);
      setConfirmStop(false);
    } finally {
      setBusy(false);
    }
  }

  // A stop dated after the business date has not taken effect, so it can be cancelled and the item keeps posting
  // (D16). Cancelling is not one of the places that ask for a typed reason, so the server writes its own.
  async function cancelStop() {
    if (!item || !canEdit || busy) return;
    setBusy(true);
    try {
      await apiRequest(`setup/recurring/${item.id}/restore`, {
        method: "POST",
        body: JSON.stringify({}),
      });
      toast(`The stop of ${item.name} was cancelled.`);
      await onSaved();
    } catch (value) {
      setSaveError((value as Error).message);
    } finally {
      setBusy(false);
    }
  }

  // What an item saved before expense items still uses, shown as read-only labels.
  const legacyUses = [
    legacyCategory && `the old cost type ${legacyCategoryName}`,
    legacyDaily && "a daily schedule",
  ].filter(Boolean);
  const legacyNeeds = [
    legacyCategory && "an expense item",
    legacyDaily && "how often it posts",
  ].filter(Boolean);
  const dayOptions = Array.from({ length: 28 }, (_, index) => index + 1);

  return (
    <section>
      <PageHeader
        title={isNew ? "Add scheduled expense or saving" : item.name}
        description={
          isNew
            ? "It posts to the vehicles you choose on every due date."
            : `${recurringFrequency(item)}${item.note ? `. ${item.note}` : ""}`
        }
      />
      <FormLayout>
        <ErrorSummary count={Object.keys(errors).length} />
        {saveError && <Banner>{saveError}</Banner>}
        {loadError && <Banner>{loadError}</Banner>}
        {!canEdit &&
          (item?.partial ? (
            <Note>
              This item also posts to vehicles you can&apos;t see, so only someone who can see all of them can change it.
              The amounts here are your vehicles&apos; share.
            </Note>
          ) : (
            <Note>You can view this item but not change it.</Note>
          ))}
        {item && startLocked && !stopped && today && (
          <Note tone="info">
            Changes apply from {formatDateOnly(today)}. Postings before that
            stay as they were.
          </Note>
        )}
        {stopped && (
          <Note>
            Stopped. The last posting was on or before{" "}
            {formatDateOnly(item!.stoppedFrom!)}.
          </Note>
        )}
        {futureStop && (
          <Note tone="info">
            Scheduled to stop on {formatDateOnly(futureStop)}. You can still
            change the schedule, or cancel the stop, before then.
          </Note>
        )}
        {legacyUses.length > 0 && !stopped && (
          <Note tone="info">
            Set up with {legacyUses.join(" and ")}, which{" "}
            {legacyUses.length > 1 ? "are" : "is"} no longer offered. It keeps
            posting as it is.
            {canEdit ? ` To save a change, choose ${legacyNeeds.join(" and ")}.` : ""}
          </Note>
        )}

        <Card density="form">
          <CardHeader title="What and how often" />
          <Grid2>
            <ChoiceField
              label="Type"
              hint={
                kind === 2
                  ? "Set aside each week or month, not counted as money out."
                  : "Money out on the day it is paid."
              }
            >
              {[
                { value: 1, label: "Cost" },
                { value: 2, label: "Savings" },
              ].map((option) => (
                <Choice
                  key={option.value}
                  type="radio"
                  name="recurring-kind"
                  label={option.label}
                  checked={kind === option.value}
                  disabled={disabled}
                  onChange={() => updateKind(option.value)}
                />
              ))}
            </ChoiceField>
            {kind === 1 ? (
              <Field
                id="recurring-item"
                label="Expense item"
                error={errors.expenseItem}
                hint={
                  picked
                    ? `${picked.categoryName ? `${picked.categoryName}. ` : ""}${countedAs ? `Counts as ${countedAs}.` : ""}`
                    : legacyCategory && !expenseItemId
                      ? `Was the old cost type ${legacyCategoryName}.`
                      : "Items come from Expense categories."
                }
              >
                <SelectInput
                  value={expenseItemId}
                  disabled={disabled}
                  onChange={(event) => setExpenseItemId(event.target.value)}
                >
                  <option value="">
                    {canEdit && expenseItems === undefined && !picked
                      ? "Loading expense items"
                      : "Choose an item"}
                  </option>
                  {itemGroups.map((group) =>
                    group[0].categoryName ? (
                      <optgroup key={group[0].categoryId} label={group[0].categoryName}>
                        {group.map((choice) => (
                          <option key={choice.id} value={choice.id}>
                            {choice.name}
                          </option>
                        ))}
                      </optgroup>
                    ) : (
                      group.map((choice) => (
                        <option key={choice.id} value={choice.id}>
                          {choice.off ? `${choice.name} (turned off)` : choice.name}
                        </option>
                      ))
                    ),
                  )}
                </SelectInput>
              </Field>
            ) : (
              <Field id="recurring-name" label="Name" error={errors.name}>
                <TextInput
                  value={name}
                  placeholder="For example Owner savings"
                  disabled={disabled}
                  onChange={(event) => setName(event.target.value)}
                />
              </Field>
            )}
            <Field
              id="recurring-note"
              label="Note"
              error={errors.note}
              hint={`Optional. Up to ${NOTE_LIMIT} characters.`}
            >
              <TextInput
                value={note}
                maxLength={NOTE_LIMIT}
                placeholder="For example Zuri Genesis fleet"
                disabled={disabled}
                onChange={(event) => setNote(event.target.value)}
              />
            </Field>
            <Field
              id="recurring-amount"
              label="Amount each time"
              error={errors.amount}
              hint="The total. Split it across vehicles below."
            >
              <CurrencyInput
                min="1"
                value={amount}
                disabled={disabled}
                onChange={(event) => updateAmount(event.target.value)}
              />
            </Field>
            <ChoiceField
              label="How often"
              error={errors.frequency}
              hint={
                frequency === 1
                  ? "Now every day, which is no longer offered."
                  : kind === 2
                    ? "Savings are set aside every week or every month."
                    : undefined
              }
            >
              {frequencies
                .filter((option) => kind === 1 || option.value !== 4)
                .map((option) => (
                  <Choice
                    key={option.value}
                    type="radio"
                    name="recurring-frequency"
                    label={option.label}
                    checked={frequency === option.value}
                    disabled={disabled}
                    onChange={() => setFrequency(option.value)}
                  />
                ))}
            </ChoiceField>
            {frequency === 2 && (
              <Field id="recurring-weekday" label="On">
                <SelectInput
                  value={weekday}
                  disabled={disabled}
                  onChange={(event) => setWeekday(event.target.value)}
                >
                  {weekdays.map((day) => (
                    <option key={day.value} value={day.value}>
                      {day.label}
                    </option>
                  ))}
                </SelectInput>
              </Field>
            )}
            {frequency === 4 && (
              <Field id="recurring-month" label="Month">
                <SelectInput
                  value={month}
                  disabled={disabled}
                  onChange={(event) => setMonth(event.target.value)}
                >
                  {monthNames.map((label, index) => (
                    <option key={label} value={index + 1}>
                      {label}
                    </option>
                  ))}
                </SelectInput>
              </Field>
            )}
            {(frequency === 3 || frequency === 4) && (
              <Field
                id="recurring-monthday"
                label="On"
                hint={
                  frequency === 3
                    ? "For the 29th to the 31st, choose the last day so short months are covered."
                    : "The day it falls due each year."
                }
              >
                <SelectInput
                  value={monthDay}
                  disabled={disabled}
                  onChange={(event) => setMonthDay(event.target.value)}
                >
                  {dayOptions.map((value) => (
                    <option key={value} value={value}>
                      The {ordinal(value)}
                    </option>
                  ))}
                  <option value="last">The last day</option>
                </SelectInput>
              </Field>
            )}
          </Grid2>
          <Grid2 narrow>
            <Field
              id="recurring-start"
              label="Starts"
              error={errors.start}
              hint={
                startLocked
                  ? "Already running. Changes start today."
                  : earliestStart
                    ? `On or after ${formatDateOnly(earliestStart)}. A start before today also adds the earlier postings.`
                    : "A start before today also adds the earlier postings."
              }
            >
              <TextInput
                type="date"
                value={start}
                min={startLocked ? undefined : earliestStart}
                disabled={disabled || startLocked}
                onChange={(event) => setStart(event.target.value)}
              />
            </Field>
            <div className="flex min-w-0 flex-col gap-1.5">
              {!noEnd && (
                <Field
                  id="recurring-end"
                  label="Ends"
                  error={
                    errors.end ??
                    (!periodIsValid
                      ? "End date must be on or after the start date."
                      : undefined)
                  }
                >
                  <TextInput
                    type="date"
                    value={end}
                    min={start}
                    disabled={disabled}
                    onChange={(event) => setEnd(event.target.value)}
                  />
                </Field>
              )}
              <Choice
                label="No end date"
                checked={noEnd}
                disabled={disabled}
                onChange={(event) => setNoEnd(event.target.checked)}
              />
            </div>
          </Grid2>
        </Card>

        <Card density="form">
          <CardHeader
            title="Vehicles"
            description="Split the amount across one or more vehicles. It must add up exactly."
          />
          {!disabled && !vehiclesLoading && (
            <ChipGroup aria-label="Vehicle selection actions">
              {companies
                .filter(([companyId]) => companyId)
                .map(([companyId, companyName]) => (
                  <Chip
                    key={companyId}
                    onClick={() => selectCompany(companyId)}
                  >
                    All {companyName}
                  </Chip>
                ))}
              <Chip
                onClick={() => {
                  setSelected([]);
                  setShares({});
                  setManualAllocations(false);
                }}
              >
                Clear
              </Chip>
              <Chip
                disabled={!total || !postingIds.length}
                onClick={splitEqually}
              >
                Split equally
              </Chip>
            </ChipGroup>
          )}
          {splitNotice ? (
            <Hint role="status">{splitNotice}</Hint>
          ) : (!total || !selected.length) && !disabled ? (
            <Hint>
              Enter the amount and select vehicles to enable Split equally.
            </Hint>
          ) : null}
          {outOfFleetIds.length > 0 && (
            <Hint>
              {outOfFleetIds.length === 1
                ? `${vehicleName(outOfFleetIds[0])} is not in the fleet today, so its share stays in the total but does not post.`
                : `${outOfFleetIds.map(vehicleName).join(", ")} are not in the fleet today, so their shares stay in the total but do not post.`}
              {!disabled && " Untick a vehicle to take its share off the amount."}
            </Hint>
          )}
          {vehiclesLoading && (
            <div role="status" aria-busy="true">
              <span className="sr-only">Loading vehicles</span>
              <ListSkeleton rows={3} />
            </div>
          )}
          <div>
            {!vehiclesLoading &&
              companies.map(([companyId, companyName]) => (
                <div key={companyId || "vehicles"}>
                  {companyName && <GroupLabel>{companyName}</GroupLabel>}
                  {vehicles
                    .filter((vehicle) => vehicle.companyId === companyId)
                    .map((vehicle) => (
                      <div
                        key={vehicle.id}
                        className="grid min-h-13 grid-cols-[minmax(0,320px)_200px] items-center gap-4 border-t border-divider max-[720px]:grid-cols-[minmax(0,1fr)_140px] max-[720px]:gap-3"
                      >
                        <Choice
                          label={vehicle.active === false ? `${vehicle.registration} (not in the fleet today)` : vehicle.registration}
                          checked={selected.includes(vehicle.id)}
                          disabled={disabled || (vehicle.active === false && !selected.includes(vehicle.id))}
                          onChange={(event) =>
                            updateSelection(vehicle.id, event.target.checked)
                          }
                        />
                        {selected.includes(vehicle.id) ? (
                          <CurrencyInput
                            density="compact"
                            aria-label={`Share for ${vehicle.registration}`}
                            value={shares[vehicle.id] ?? "0"}
                            disabled={disabled || vehicle.active === false}
                            onChange={(event) => {
                              setSplitNotice("");
                              setManualAllocations(true);
                              setShares({
                                ...shares,
                                [vehicle.id]: event.target.value,
                              });
                            }}
                          />
                        ) : (
                          <span />
                        )}
                      </div>
                    ))}
                </div>
              ))}
          </div>
          <BalancePanel ok={isBalanced}>
            <span>
              Allocated {kes(allocationTotal)} of {kes(total)}
            </span>
            <span>
              {!selected.length
                ? "Tick at least one vehicle"
                : !total
                  ? "Enter the amount"
                  : isBalanced
                    ? "Balanced"
                    : difference > 0
                      ? `${kes(difference / 100)} still to allocate`
                      : `${kes(-difference / 100)} too much`}
            </span>
          </BalancePanel>
          {errors.allocations && <ErrorText>{errors.allocations}</ErrorText>}
        </Card>

        <Card density="form">
          <CardHeader title="What will post" description="Worked out for you" />
          {previewDates.length ? (
            <>
              <ol className="m-0 list-decimal pl-5">
                {previewDates.map((date) => (
                  <li key={date} className="py-0.5 tabular-nums">
                    {formatDateOnly(date)}: {kes(postingTotal)} across{" "}
                    {plural(postingIds.length, "vehicle", "vehicles")}
                  </li>
                ))}
              </ol>
              <Hint>
                About {kes(recurringMonthlyEstimate(postingTotal, frequency))} a month.{" "}
                {kind === 2
                  ? "Shown as savings in each vehicle report."
                  : countedAs
                    ? `Counted under ${countedAs} in each vehicle report.`
                    : "Counted as money out in each vehicle report."}
              </Hint>
            </>
          ) : (
            <Hint>
              {!total || !selected.length
                ? "Enter the amount and choose vehicles to see the postings."
                : !periodIsValid
                  ? "The end date is before the start date."
                  : !today
                    ? "The postings show once the business date has loaded."
                    : "No postings from today in this period."}
            </Hint>
          )}
        </Card>

        {item && canEdit && !stopped && confirmStop && (
          <Card density="form">
            <CardHeader
              title="Stop from today"
              description="A short reason is required and is kept in the change log."
            />
            <Field id="recurring-stop-reason" label="Reason for stopping">
              <TextInput
                autoFocus
                maxLength={500}
                placeholder="For example, the loan is paid off"
                value={stopReason}
                disabled={busy}
                aria-invalid={Boolean(stopError) || undefined}
                onChange={(event) => {
                  setStopReason(event.target.value);
                  setStopError("");
                }}
              />
            </Field>
            {stopError && <Banner>{stopError}</Banner>}
          </Card>
        )}

        <FormActions>
          {canEdit && !stopped && (
            <Button
              tone="ok"
              disabled={busy}
              aria-busy={busy || undefined}
              onClick={() => void save()}
            >
              {busy ? "Saving..." : isNew ? "Add" : "Save changes"}
            </Button>
          )}
          <Button tone="quiet" disabled={busy} onClick={onCancel}>
            {canEdit && !stopped ? "Cancel" : "Back"}
          </Button>
          <Spacer />
          {item && canEdit && !stopped && futureStop && (
            <Button tone="outline" disabled={busy} onClick={() => void cancelStop()}>
              Cancel stop
            </Button>
          )}
          {item && canEdit && !stopped && !futureStop && (
            <Button tone="warn" disabled={busy} onClick={() => void stop()}>
              {confirmStop ? "Tap again to stop from today" : "Stop from today"}
            </Button>
          )}
        </FormActions>
      </FormLayout>
    </section>
  );
}
