"use client";

import { useFormats } from "../../lib/formats";
import { AmountInput } from "../pettycash/AmountInput";
import {
  Field,
  LinkButton,
  SearchSelect,
  TextInput,
  type SearchOption,
} from "../ui";

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
          error={costProblem}
        >
          <AmountInput
            value={cost}
            onChange={(event) => onCost(event.target.value)}
          />
        </Field>
      </div>
      <div className="mtot">
        <span>Total amount</span>
        <b className="num">
          <output>{formats.kes(total ?? 0)}</output>
        </b>
      </div>
    </>
  );
}
