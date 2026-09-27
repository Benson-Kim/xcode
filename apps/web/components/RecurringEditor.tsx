"use client";

import { useState } from "react";
import { requestSetup } from "./requestSetup";
import {
  formatDateOnly,
  recurringFrequency,
  recurringMonthlyEstimate,
  recurringNextPostings,
  todayDateOnly,
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
  ChoiceGroup,
  CurrencyInput,
  ErrorSummary,
  ErrorText,
  Field,
  FormActions,
  FormLayout,
  Grid2,
  GroupLabel,
  Hint,
  Note,
  PageHeader,
  SelectInput,
  Spacer,
  TextInput,
  useToast,
} from "./ui";
import { kes, plural } from "../lib/format";
import { recurringCategoryNames, type RecurringItem, type VehicleOption } from "./setup/shared";

type Props = {
  item?: RecurringItem;
  vehicles: VehicleOption[];
  onCancel: () => void;
  onSaved: () => Promise<void> | void;
  canEdit?: boolean;
  preselectVehicle?: string;
};

type Errors = Partial<Record<"name" | "amount" | "start" | "end" | "allocations", string>>;

const presets = [
  { name: "Loan repayment", kind: 1, category: 4, frequency: 3 },
  { name: "Insurance", kind: 1, category: 4, frequency: 3 },
  { name: "SACCO fee", kind: 1, category: 4, frequency: 3 },
  { name: "Stage fees", kind: 1, category: 1, frequency: 1 },
  { name: "Savings", kind: 2, category: 4, frequency: 2 },
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
  return Object.fromEntries(vehicleIds.map((vehicleId, index) => [vehicleId, formatShare((baseCents + (index < remainder ? 1 : 0)) / 100)]));
}

// Whole amounts without ".00", as the design shows them.
function formatShare(amount: number) {
  return Number.isInteger(amount) ? String(amount) : amount.toFixed(2);
}

function ordinal(value: number) {
  const lastTwo = value % 100;
  const suffix = lastTwo >= 11 && lastTwo <= 13 ? "th" : ["th", "st", "nd", "rd"][value % 10] || "th";
  return `${value}${suffix}`;
}

export function RecurringEditor({ item, vehicles, onCancel, onSaved, canEdit = true, preselectVehicle }: Props) {
  const toast = useToast();
  const isNew = !item;
  const [name, setName] = useState(item?.name || "");
  const [kind, setKind] = useState(item?.kind || 1);
  const [category, setCategory] = useState(item?.category || 4);
  const [amount, setAmount] = useState(item?.amount ? String(item.amount) : "");
  const [frequency, setFrequency] = useState(item?.frequency || 3);
  const [weekday, setWeekday] = useState(String(item?.frequency === 2 ? (item.day ?? 6) : 6));
  const [monthDay, setMonthDay] = useState(item?.frequency === 3 ? (item.lastDay ? "last" : String(item.day ?? 1)) : "1");
  const [start, setStart] = useState(item?.start || todayDateOnly());
  const [end, setEnd] = useState(item?.end || "");
  const [noEnd, setNoEnd] = useState(!item?.end);
  const initialSelection = item?.allocations.map((allocation) => allocation.vehicleId) || (preselectVehicle ? [preselectVehicle] : []);
  const [selected, setSelected] = useState<string[]>(initialSelection);
  const [shares, setShares] = useState<Record<string, string>>(
    Object.fromEntries(item?.allocations.map((allocation) => [allocation.vehicleId, formatShare(allocation.amount)]) || []),
  );
  const [manualAllocations, setManualAllocations] = useState(Boolean(item));
  const [errors, setErrors] = useState<Errors>({});
  const [saveError, setSaveError] = useState("");
  const [splitNotice, setSplitNotice] = useState("");
  const [confirmStop, setConfirmStop] = useState(false);
  const [busy, setBusy] = useState(false);

  const total = Number(amount) || 0;
  const allocationTotal = selected.reduce((sum, vehicleId) => sum + (Number(shares[vehicleId]) || 0), 0);
  const difference = Math.round(total * 100) - Math.round(allocationTotal * 100);
  const isBalanced = selected.length > 0 && total > 0 && difference === 0;
  const today = todayDateOnly();
  const stopped = Boolean(item?.stoppedFrom);
  const startLocked = Boolean(item && item.start < today);
  const disabled = !canEdit || stopped || busy;
  const companies = [...new Map(vehicles.map((vehicle) => [vehicle.companyId, vehicle.companyName])).entries()];

  function updateAmount(value: string) {
    setAmount(value);
    setSplitNotice("");
    if (!manualAllocations) setShares(splitAmountEvenly(Number(value) || 0, selected));
  }

  function updateSelection(vehicleId: string, checked: boolean) {
    const next = checked ? [...new Set([...selected, vehicleId])] : selected.filter((id) => id !== vehicleId);
    setSelected(next);
    setSplitNotice("");
    if (!manualAllocations) setShares(splitAmountEvenly(total, next));
    else
      setShares((current) => {
        const nextShares = { ...current };
        if (checked) nextShares[vehicleId] = "0";
        else delete nextShares[vehicleId];
        return nextShares;
      });
  }

  function selectCompany(companyId: string) {
    const next = [...new Set([...selected, ...vehicles.filter((vehicle) => vehicle.companyId === companyId).map((vehicle) => vehicle.id)])];
    setSelected(next);
    setSplitNotice("");
    setManualAllocations(false);
    setShares(splitAmountEvenly(total, next));
  }

  function splitEqually() {
    if (!total || !selected.length) return;
    setManualAllocations(false);
    setShares(splitAmountEvenly(total, selected));
    setSplitNotice(`Split ${kes(total)} equally across ${plural(selected.length, "vehicle", "vehicles")}.`);
  }

  function applyPreset(preset: (typeof presets)[number]) {
    setName(preset.name);
    setKind(preset.kind);
    setCategory(preset.category);
    setFrequency(preset.frequency);
    if (preset.frequency === 2) setWeekday("6");
    if (preset.frequency === 3) setMonthDay("1");
  }

  const periodIsValid = noEnd || Boolean(end && end >= start);
  const schedule = {
    frequency,
    day: frequency === 1 ? null : frequency === 2 ? Number(weekday) : monthDay === "last" ? null : Number(monthDay),
    lastDay: frequency === 3 && monthDay === "last",
    start,
    end: noEnd ? null : end || null,
  };
  const previewDates = total > 0 && selected.length && periodIsValid ? recurringNextPostings(schedule, today, 5) : [];

  async function save() {
    if (disabled) return;
    const next: Errors = {};
    if (!name.trim()) next.name = "Enter a name.";
    if (total <= 0) next.amount = "Enter the amount in KES.";
    if (!start) next.start = "Enter the start date.";
    if (!noEnd && (!end || end < start)) next.end = "The end date must be on or after the start date.";
    if (!selected.length) next.allocations = "Tick at least one vehicle.";
    else if (difference !== 0) next.allocations = `The split must add up to ${kes(total)}. It is ${kes(allocationTotal)}.`;
    setErrors(next);
    setSaveError("");
    if (Object.keys(next).length) return;
    const allocations = selected.map((vehicleId) => ({ vehicleId, amount: Number(shares[vehicleId]) || 0 }));
    setBusy(true);
    try {
      await requestSetup(isNew ? "recurring" : `recurring/${item.id}`, {
        method: isNew ? "POST" : "PUT",
        body: JSON.stringify({
          name: name.trim(),
          kind,
          category: kind === 1 ? category : null,
          amount: total,
          frequency,
          day: schedule.day,
          lastDay: schedule.lastDay,
          start,
          end: noEnd ? null : end,
          allocations,
          reason: isNew ? `Added recurring item ${name.trim()}` : `Updated recurring item ${name.trim()}`,
        }),
      });
      toast(isNew ? `${name.trim()} added. It now posts to ${plural(allocations.length, "vehicle", "vehicles")}.` : `Changes saved for ${name.trim()}.`);
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
    setBusy(true);
    try {
      await requestSetup(`recurring/${item.id}/stop`, {
        method: "POST",
        body: JSON.stringify({ confirmed: true, reason: "Stopped recurring item" }),
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

  return (
    <section>
      <PageHeader
        title={isNew ? "Add recurring cost or saving" : item.name}
        description={isNew ? "It posts to the vehicles you choose on every due date in its period." : recurringFrequency(item)}
      />
      <FormLayout>
        <ErrorSummary count={Object.keys(errors).length} />
        {saveError && <Banner>{saveError}</Banner>}
        {!canEdit && <Note>You can view this item but not change it.</Note>}
        {item && startLocked && !stopped && <Note tone="info">Changes apply from {formatDateOnly(today)}. Postings before that stay as they were.</Note>}
        {stopped && <Note>Stopped. The last posting was on or before {formatDateOnly(item!.stoppedFrom!)}.</Note>}

        <Card density="form">
          <CardHeader title="What it is" />
          {isNew && canEdit && (
            <ChipGroup aria-label="Quick picks">
              {presets.map((preset) => (
                <Chip key={preset.name} onClick={() => applyPreset(preset)}>
                  {preset.name}
                </Chip>
              ))}
            </ChipGroup>
          )}
          <Grid2>
            <Field id="recurring-name" label="Name" error={errors.name}>
              <TextInput value={name} placeholder="For example Loan repayment" disabled={disabled} onChange={(event) => setName(event.target.value)} />
            </Field>
            <ChoiceField label="Type" hint={kind === 2 ? "Savings are set aside, not counted as a cost." : "Costs reduce net contribution."}>
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
                  onChange={() => setKind(option.value)}
                />
              ))}
            </ChoiceField>
            {kind === 1 && (
              <Field id="recurring-category" label="Cost type">
                <SelectInput value={category} disabled={disabled} onChange={(event) => setCategory(Number(event.target.value))}>
                  {Object.entries(recurringCategoryNames).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </SelectInput>
              </Field>
            )}
            <Field id="recurring-amount" label="Amount each time" error={errors.amount} hint="The total. Split it across vehicles below.">
              <CurrencyInput min="1" value={amount} disabled={disabled} onChange={(event) => updateAmount(event.target.value)} />
            </Field>
          </Grid2>
        </Card>

        <Card density="form">
          <CardHeader title="How often" />
          <ChoiceGroup role="radiogroup" label="How often">
            {[
              { value: 1, label: "Every day" },
              { value: 2, label: "Every week" },
              { value: 3, label: "Every month" },
            ].map((option) => (
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
          </ChoiceGroup>
          {frequency !== 1 && (
            <Grid2>
              {frequency === 2 ? (
                <Field id="recurring-weekday" label="On">
                  <SelectInput value={weekday} disabled={disabled} onChange={(event) => setWeekday(event.target.value)}>
                    {weekdays.map((day) => (
                      <option key={day.value} value={day.value}>
                        {day.label}
                      </option>
                    ))}
                  </SelectInput>
                </Field>
              ) : (
                <Field id="recurring-monthday" label="On" hint="For the 29th to the 31st, choose the last day so short months are covered.">
                  <SelectInput value={monthDay} disabled={disabled} onChange={(event) => setMonthDay(event.target.value)}>
                    {Array.from({ length: 28 }, (_, index) => index + 1).map((value) => (
                      <option key={value} value={value}>
                        The {ordinal(value)}
                      </option>
                    ))}
                    <option value="last">The last day</option>
                  </SelectInput>
                </Field>
              )}
            </Grid2>
          )}
          <Grid2>
            <Field
              id="recurring-start"
              label="Starts"
              error={errors.start}
              hint={startLocked ? "Already running. Changes start today." : "A start date before today also adds the earlier postings to past reports."}
            >
              <TextInput type="date" value={start} disabled={disabled || startLocked} onChange={(event) => setStart(event.target.value)} />
            </Field>
            <div className="flex min-w-0 flex-col gap-1.5">
              {!noEnd && (
                <Field id="recurring-end" label="Ends" error={errors.end ?? (!periodIsValid ? "End date must be on or after the start date." : undefined)}>
                  <TextInput type="date" value={end} min={start} disabled={disabled} onChange={(event) => setEnd(event.target.value)} />
                </Field>
              )}
              <Choice label="No end date" checked={noEnd} disabled={disabled} onChange={(event) => setNoEnd(event.target.checked)} />
            </div>
          </Grid2>
        </Card>

        <Card density="form">
          <CardHeader title="Vehicles" description="Split the amount across one or more vehicles. It must add up exactly." />
          {!disabled && (
            <ChipGroup aria-label="Vehicle selection actions">
              {companies.filter(([companyId]) => companyId).map(([companyId, companyName]) => (
                <Chip key={companyId} onClick={() => selectCompany(companyId)}>
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
              <Chip disabled={!total || !selected.length} onClick={splitEqually}>
                Split equally
              </Chip>
            </ChipGroup>
          )}
          {splitNotice ? (
            <Hint role="status">{splitNotice}</Hint>
          ) : (!total || !selected.length) && !disabled ? (
            <Hint>Enter the amount and select vehicles to enable Split equally.</Hint>
          ) : null}
          <div>
            {companies.map(([companyId, companyName]) => (
              <div key={companyId || "vehicles"}>
                {companyName && <GroupLabel>{companyName}</GroupLabel>}
                {vehicles
                  .filter((vehicle) => vehicle.companyId === companyId)
                  .map((vehicle) => (
                    <div key={vehicle.id} className="grid min-h-13 grid-cols-[minmax(0,1fr)_170px] items-center gap-3 border-t border-divider max-[720px]:grid-cols-[minmax(0,1fr)_140px]">
                      <Choice
                        label={vehicle.registration}
                        checked={selected.includes(vehicle.id)}
                        disabled={disabled}
                        onChange={(event) => updateSelection(vehicle.id, event.target.checked)}
                      />
                      {selected.includes(vehicle.id) ? (
                        <CurrencyInput
                          density="compact"
                          aria-label={`Share for ${vehicle.registration}`}
                          value={shares[vehicle.id] ?? "0"}
                          disabled={disabled}
                          onChange={(event) => {
                            setSplitNotice("");
                            setManualAllocations(true);
                            setShares({ ...shares, [vehicle.id]: event.target.value });
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
                    {formatDateOnly(date)}: {kes(total)} across {plural(selected.length, "vehicle", "vehicles")}
                  </li>
                ))}
              </ol>
              <Hint>
                About {kes(recurringMonthlyEstimate(total, frequency))} a month.{" "}
                {kind === 2 ? "Shown as savings in each vehicle report." : `Counted under ${recurringCategoryNames[category]} in each vehicle report.`}
              </Hint>
            </>
          ) : (
            <Hint>
              {!total || !selected.length
                ? "Enter the amount and choose vehicles to see the postings."
                : !periodIsValid
                  ? "The end date is before the start date."
                  : "No postings from today in this period."}
            </Hint>
          )}
        </Card>

        <FormActions>
          {canEdit && !stopped && (
            <Button disabled={busy} aria-busy={busy || undefined} onClick={() => void save()}>
              {busy ? "Saving..." : isNew ? "Add" : "Save changes"}
            </Button>
          )}
          <Button tone="outline" disabled={busy} onClick={onCancel}>
            {canEdit && !stopped ? "Cancel" : "Back"}
          </Button>
          <Spacer />
          {item && canEdit && !stopped && (
            <Button tone="danger" disabled={busy} onClick={() => void stop()}>
              {confirmStop ? "Tap again to stop from today" : "Stop from today"}
            </Button>
          )}
        </FormActions>
      </FormLayout>
    </section>
  );
}
