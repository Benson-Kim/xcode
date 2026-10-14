"use client";

import { useId, useState } from "react";

import { MONTH_NAMES, ordinal, WEEKDAYS } from "@xcode/shared/dates";
import { vehicleLabel } from "@xcode/shared/revenue";

import { useAppearance } from "../lib/appearance";
import { recurringApi } from "../lib/endpoints/recurring";
import { useFormats } from "../lib/formats";
import type { ExpenseItemOption } from "../lib/types";
import {
  buildRequest,
  chosenVehicles,
  DEFAULT_WINDOW,
  initialFields,
  openingAmounts,
  type RecurringFields,
  runSummary,
  validateFields,
} from "./recurring/fields";
import {
  RECURRING_FREQUENCY,
  RECURRING_FREQUENCY_OPTIONS,
} from "./recurringPresentation";
import type { RecurringItem, VehicleOption } from "./setup/shared";
import {
  Button,
  CurrencyInput,
  Dialog,
  Field,
  SearchSelect,
  useToast,
  type SearchOption,
} from "./ui";

type Props = {
  item?: RecurringItem;
  // What a new item is: 1 a scheduled expense, 2 a saving.
  kind?: number;
  vehicles: VehicleOption[];
  vehiclesLoading?: boolean;
  // The active expense items a scheduled expense can pick (GET expense-items/options).
  expenseItems?: ExpenseItemOption[];
  // Whether the editor sees every vehicle: only then can "All vehicles" be chosen.
  fullScope?: boolean;
  canEdit?: boolean;
  preselectVehicle?: string;
  loadError?: string;
  onCancel: () => void;
  onSaved: () => Promise<void> | void;
};

const weekdays = [...WEEKDAYS.slice(1), WEEKDAYS[0]];
const monthDays = Array.from({ length: 28 }, (_, index) => index + 1);

// Scheduled expense or saving (v2.30): what, how much per vehicle, when it runs, which vehicles, and for a saving
// the revenue rule and the opening balance. Labels, fields and figures only.
export function RecurringEditor({
  item,
  kind = 1,
  vehicles,
  vehiclesLoading = false,
  expenseItems,
  fullScope = false,
  canEdit = true,
  preselectVehicle,
  loadError,
  onCancel,
  onSaved,
}: Props) {
  const today = useAppearance().appearance?.businessDate ?? "";
  const formats = useFormats();
  const toast = useToast();
  const formId = useId();
  const fleet = vehicles
    .filter((vehicle) => vehicle.active !== false)
    .map((vehicle) => vehicle.id);
  const [fields, setFields] = useState<RecurringFields>(() => {
    const start = initialFields(item, kind, fullScope, fleet);
    return preselectVehicle && !item
      ? { ...start, allVehicles: false, vehicleIds: [preselectVehicle] }
      : start;
  });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const saving = fields.kind === 2;
  const disabled = !canEdit || busy;
  const set = <K extends keyof RecurringFields>(
    key: K,
    value: RecurringFields[K],
  ) => {
    setFields((current) => ({ ...current, [key]: value }));
    setError("");
  };
  const chosen = chosenVehicles(fields, fleet);
  const summary = runSummary(fields, item, chosen.length, today, formats);
  const itemOptions: SearchOption[] = (expenseItems ?? []).map((option) => ({
    value: option.id,
    label: option.name,
    group: option.categoryName,
  }));
  if (
    item?.expenseItemId &&
    !itemOptions.some((option) => option.value === item.expenseItemId)
  )
    itemOptions.unshift({
      value: item.expenseItemId,
      label: item.expenseItemName || item.name,
    });
  const opening = openingAmounts(fields, chosen);
  const openingTotal = opening.reduce((sum, share) => sum + share.amount, 0);

  async function save() {
    if (disabled) return;
    const problem = validateFields(fields, chosen, today);
    if (problem) return setError(problem);
    const itemName =
      itemOptions.find((option) => option.value === fields.expenseItemId)
        ?.label ??
      item?.name ??
      "";
    setBusy(true);
    try {
      await recurringApi.save(
        item,
        buildRequest(fields, item, chosen, today, itemName),
      );
      toast(
        item
          ? "Saved. Applies from the next run."
          : summary.text.startsWith("First run today")
            ? saving
              ? fields.conditionOn
                ? "Saved. Today’s run waits for today’s revenue."
                : "Saved. Today’s run is posted."
              : "Saved. Today’s run is in central expenses."
            : `Saved. ${summary.text.split(",")[0]}.`,
      );
      await onSaved();
    } catch (value) {
      setError((value as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const frequencies = [
    ...(saving
      ? [{ value: RECURRING_FREQUENCY.daily, label: "Every day" }]
      : []),
    ...RECURRING_FREQUENCY_OPTIONS,
  ];
  const dateSelect = (
    <div className="f">
      <label htmlFor="sDom">Date</label>
      <select
        className="inp"
        id="sDom"
        value={fields.monthDay}
        disabled={disabled}
        onChange={(event) => set("monthDay", event.target.value)}
      >
        {monthDays.map((day) => (
          <option key={day} value={String(day)}>
            {ordinal(day)}
          </option>
        ))}
        {fields.monthDay === "last" && <option value="last">Last day</option>}
      </select>
    </div>
  );

  return (
    <Dialog
      open
      size={saving ? "md" : undefined}
      title={`${item ? "Edit" : "New"} ${saving ? "saving" : "scheduled expense"}`}
      onClose={onCancel}
      footer={
        <>
          <Button tone="outline" disabled={busy} onClick={onCancel}>
            Cancel
          </Button>
          {canEdit && (
            <Button tone="ok" type="submit" form={formId} disabled={busy}>
              Save
            </Button>
          )}
        </>
      }
    >
      <form
        id={formId}
        noValidate
        className="contents"
        onSubmit={(event) => {
          event.preventDefault();
          void save();
        }}
      >
        {saving ? (
          <div className="f">
            <label htmlFor="sName">Name</label>
            <input
              className="inp"
              id="sName"
              value={fields.name}
              disabled={disabled}
              onChange={(event) => set("name", event.target.value)}
            />
          </div>
        ) : (
          <Field id="fItemQ" label="Item">
            <SearchSelect
              options={itemOptions}
              value={fields.expenseItemId}
              placeholder={
                expenseItems === undefined && canEdit && !item
                  ? "Loading items"
                  : "Search item"
              }
              disabled={disabled}
              onChange={(value) => set("expenseItemId", value)}
            />
          </Field>
        )}
        <div className="mrow2">
          <Field id="sAmt" label="Amount per vehicle, KES">
            <CurrencyInput
              value={fields.amount}
              disabled={disabled}
              onChange={(event) => set("amount", event.target.value)}
            />
          </Field>
          <div className="f">
            <label htmlFor="sFreq">Runs</label>
            <select
              className="inp"
              id="sFreq"
              value={fields.frequency}
              disabled={disabled}
              onChange={(event) => {
                const frequency = Number(event.target.value);
                setFields((current) => ({
                  ...current,
                  frequency,
                  conditionDays: String(DEFAULT_WINDOW[frequency] ?? 30),
                }));
              }}
            >
              {frequencies.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>
        </div>
        {fields.frequency === RECURRING_FREQUENCY.weekly && (
          <div className="f">
            <label htmlFor="sDay">Day</label>
            <select
              className="inp"
              id="sDay"
              value={fields.weekday}
              disabled={disabled}
              onChange={(event) => set("weekday", event.target.value)}
            >
              {weekdays.map((day) => (
                <option key={day.value} value={String(day.value)}>
                  {day.label}
                </option>
              ))}
            </select>
          </div>
        )}
        {fields.frequency === RECURRING_FREQUENCY.monthly && dateSelect}
        {fields.frequency === RECURRING_FREQUENCY.yearly && (
          <div className="mrow2">
            {dateSelect}
            <div className="f">
              <label htmlFor="sMon">Month</label>
              <select
                className="inp"
                id="sMon"
                value={fields.month}
                disabled={disabled}
                onChange={(event) => set("month", event.target.value)}
              >
                {MONTH_NAMES.map((name, index) => (
                  <option key={name} value={String(index + 1)}>
                    {name}
                  </option>
                ))}
              </select>
            </div>
          </div>
        )}
        {saving && (
          <>
            <div className="f">
              <label htmlFor="sCond">Save</label>
              <select
                className="inp"
                id="sCond"
                value={fields.conditionOn ? "1" : "0"}
                disabled={disabled}
                onChange={(event) =>
                  set("conditionOn", event.target.value === "1")
                }
              >
                <option value="0">Every run</option>
                <option value="1">Only when revenue reaches a target</option>
              </select>
            </div>
            {fields.conditionOn && (
              <div className="mrow2">
                <Field id="sMin" label="Revenue per vehicle, KES">
                  <CurrencyInput
                    value={fields.conditionMin}
                    disabled={disabled}
                    onChange={(event) =>
                      set("conditionMin", event.target.value)
                    }
                  />
                </Field>
                <div className="f">
                  <label htmlFor="sDays">Measured</label>
                  <select
                    className="inp"
                    id="sDays"
                    value={fields.conditionDays}
                    disabled={disabled}
                    onChange={(event) =>
                      set("conditionDays", event.target.value)
                    }
                  >
                    <option value="1">That day</option>
                    <option value="7">Over the 7 days to the run</option>
                    <option value="30">Over the 30 days to the run</option>
                  </select>
                </div>
              </div>
            )}
          </>
        )}
        <div className="f">
          <div className="flabrow">
            <span className="flab">Vehicles</span>
            {fullScope && (
              <label className="mck">
                <input
                  type="checkbox"
                  id="sAll"
                  checked={fields.allVehicles}
                  disabled={disabled}
                  onChange={(event) => set("allVehicles", event.target.checked)}
                />
                All vehicles
              </label>
            )}
          </div>
          {!fields.allVehicles && (
            <div
              className="checks"
              role="group"
              aria-label="Vehicles"
              aria-busy={vehiclesLoading || undefined}
            >
              {vehicles.map((vehicle) => (
                <label key={vehicle.id} className="ck">
                  <input
                    type="checkbox"
                    checked={fields.vehicleIds.includes(vehicle.id)}
                    disabled={disabled || vehicle.active === false}
                    onChange={(event) =>
                      set(
                        "vehicleIds",
                        event.target.checked
                          ? [...fields.vehicleIds, vehicle.id]
                          : fields.vehicleIds.filter((id) => id !== vehicle.id),
                      )
                    }
                  />
                  {vehicleLabel(vehicle)}
                </label>
              ))}
            </div>
          )}
        </div>
        {saving && (
          <div className="f">
            <div className="flabrow">
              <label className="mck">
                <input
                  type="checkbox"
                  id="sOpen"
                  checked={fields.openingOn}
                  disabled={disabled}
                  onChange={(event) => set("openingOn", event.target.checked)}
                />
                Opening balance
              </label>
            </div>
            {fields.openingOn && (
              <>
                <div className="orow">
                  <span className="hint">As at</span>
                  <input
                    className="inp"
                    type="date"
                    aria-label="Opening balance date"
                    max={today || undefined}
                    value={fields.openingDate}
                    disabled={disabled}
                    onChange={(event) => set("openingDate", event.target.value)}
                  />
                </div>
                <div className="ogrid">
                  {vehicles
                    .filter((vehicle) => chosen.includes(vehicle.id))
                    .map((vehicle) => (
                      <label key={vehicle.id} className="ocell">
                        <span className="reg">{vehicle.registration}</span>
                        <input
                          className="inp num"
                          inputMode="numeric"
                          placeholder="0"
                          aria-label={`Opening balance, ${vehicle.registration}`}
                          value={fields.openingAmounts[vehicle.id] ?? ""}
                          disabled={disabled}
                          onChange={(event) =>
                            set("openingAmounts", {
                              ...fields.openingAmounts,
                              [vehicle.id]: event.target.value,
                            })
                          }
                        />
                      </label>
                    ))}
                </div>
                <div className="hint" id="sOpenTot">
                  {opening.length
                    ? `Opening balance ${formats.money(openingTotal)} across ${formats.plural(opening.length, "vehicle", "vehicles")}`
                    : item?.opening
                      ? `Opening balance ${formats.money(item.opening.total)} as at ${formats.formatDateOnly(item.opening.date)}`
                      : ""}
                </div>
              </>
            )}
          </div>
        )}
        <div className="mtot">
          <span id="sNext">{summary.text}</span>
          <b className="num" id="sTot">
            {summary.total}
          </b>
        </div>
        {(error || loadError) && (
          <div className="ferr" role="alert">
            {error || loadError}
          </div>
        )}
      </form>
    </Dialog>
  );
}
