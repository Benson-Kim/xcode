"use client";

import type { ExpenseGroup } from "@xcode/shared/expenses";

import { useFormats } from "../../lib/formats";
import { AmountInput } from "../pettycash/AmountInput";
import {
  Field,
  LinkButton,
  Note,
  SearchSelect,
  TextInput,
  type SearchOption,
} from "../ui";

export function DateField({
  date,
  businessDate,
  problem,
  onChange,
}: {
  date: string;
  businessDate: string;
  problem: string;
  onChange: (value: string) => void;
}) {
  return (
    <Field id="ex-date" label="Date" error={problem}>
      <TextInput
        type="date"
        max={businessDate}
        value={date}
        onChange={(event) => onChange(event.target.value)}
      />
    </Field>
  );
}

export function VehicleField({
  vehicleId,
  options,
  onVehicle,
  onSplit,
}: {
  vehicleId: string;
  options: SearchOption[];
  onVehicle: (id: string) => void;
  // Left out where the expense cannot be split (a row being changed).
  onSplit?: () => void;
}) {
  return (
    <Field
      id="ex-vehicle"
      label="Vehicle"
      action={
        onSplit && (
          <LinkButton compact onClick={onSplit}>
            Split across vehicles
          </LinkButton>
        )
      }
    >
      <SearchSelect
        options={options}
        value={vehicleId}
        placeholder="Choose the vehicle"
        onChange={onVehicle}
      />
    </Field>
  );
}

// The date with the vehicle beside it (.mrow2); once the purchase is split, the date alone.
export function DateAndVehicle({
  date,
  businessDate,
  dateProblem,
  onDate,
  split,
  vehicleId,
  vehicleOptions,
  onVehicle,
  onSplit,
}: {
  date: string;
  businessDate: string;
  dateProblem: string;
  onDate: (value: string) => void;
  split: boolean;
  vehicleId: string;
  vehicleOptions: SearchOption[];
  onVehicle: (id: string) => void;
  onSplit?: () => void;
}) {
  const dateField = (
    <DateField
      date={date}
      businessDate={businessDate}
      problem={dateProblem}
      onChange={onDate}
    />
  );
  if (split) return dateField;
  return (
    <div className="mrow2">
      {dateField}
      <VehicleField
        vehicleId={vehicleId}
        options={vehicleOptions}
        onVehicle={onVehicle}
        onSplit={onSplit}
      />
    </div>
  );
}

// The item, quantity and unit cost of the purchase, with the total they make.
export function PurchaseFields({
  itemId,
  onItem,
  itemOptions,
  units,
  onUnits,
  unitsProblem,
  cost,
  onCost,
  costProblem,
  group,
  total,
}: {
  itemId: string;
  onItem: (value: string) => void;
  itemOptions: SearchOption[];
  units: string;
  onUnits: (value: string) => void;
  unitsProblem: string;
  cost: string;
  onCost: (value: string) => void;
  costProblem: string;
  group: ExpenseGroup | null;
  total: number | null;
}) {
  const formats = useFormats();
  return (
    <>
      <Field id="ex-item" label="Item">
        <SearchSelect
          options={itemOptions}
          value={itemId}
          placeholder="Search item"
          onChange={onItem}
        />
      </Field>
      <div className="mrow">
        <Field id="ex-units" label="Qty" error={unitsProblem}>
          <TextInput
            inputMode="decimal"
            autoComplete="off"
            className="num"
            value={units}
            onChange={(event) => onUnits(event.target.value)}
          />
        </Field>
        <Field
          id="ex-cost"
          label={`Unit cost, ${formats.currencyCode()}`}
          hint="Use a minus sign for a refund."
          error={costProblem}
        >
          <AmountInput
            value={cost}
            onChange={(event) => onCost(event.target.value)}
          />
        </Field>
      </div>
      {group && (
        <Note tone="info">
          This expense was shared by {group.size} vehicles. Changing the item,
          quantity or unit cost takes it out of that purchase.
        </Note>
      )}
      <div className="mtot">
        <span>Total amount</span>
        <b className="num">
          <output>{formats.kes(total ?? 0)}</output>
        </b>
      </div>
    </>
  );
}
