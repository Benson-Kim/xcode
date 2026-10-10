"use client";

import type { ReactNode } from "react";

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

// Quantity and unit cost side by side, the quantity narrower; one above the other on a phone.
function QuantityRow({ children }: { children: ReactNode }) {
  return (
    <div className="grid grid-cols-[1fr_2fr] gap-x-3.5 gap-y-3.5 max-[420px]:grid-cols-1">
      {children}
    </div>
  );
}

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
          placeholder="Choose the item"
          onChange={onItem}
        />
      </Field>
      <QuantityRow>
        <Field id="ex-units" label="Qty" error={unitsProblem}>
          <TextInput
            inputMode="decimal"
            autoComplete="off"
            value={units}
            onChange={(event) => onUnits(event.target.value)}
          />
        </Field>
        <Field
          id="ex-cost"
          label="Unit cost"
          hint="Use a minus sign for a refund."
          error={costProblem}
        >
          <AmountInput
            value={cost}
            onChange={(event) => onCost(event.target.value)}
          />
        </Field>
      </QuantityRow>
      {group && (
        <Note tone="info">
          This expense was shared by {group.size} vehicles. Changing the item,
          quantity or unit cost takes it out of that purchase.
        </Note>
      )}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-linear-to-br from-card-a to-card-b px-4 py-[11px] text-white">
        <span className="text-xs font-bold tracking-[.06em] text-on-deep uppercase">
          Total amount
        </span>
        <output className="text-[22px] font-extrabold tabular-nums">
          {formats.kes(total ?? 0)}
        </output>
      </div>
    </>
  );
}
