"use client";

import {
  EXPENSE_MAX_VEHICLES,
  splitEvenly,
  unallocated,
} from "@xcode/shared/expenses";
import { parsePettyCashAmount } from "@xcode/shared/pettyCash";

import { useFormats } from "../../lib/formats";
import { AmountInput } from "../pettycash/AmountInput";
import {
  BalancePanel,
  CloseIcon,
  LinkButton,
  SearchSelect,
  type SearchOption,
} from "../ui";

export type Split = { vehicleId: string; amount: string };

// What the rows add up to against the total: the amounts (0 where one cannot be read), what is left to allocate
// (negative when over), whether a vehicle is picked twice, and whether the rows can be saved.
export function splitState(splits: Split[], total: number | null) {
  const amounts = splits.map((split) => {
    const parsed = parsePettyCashAmount(split.amount);
    return parsed.ok ? parsed.amount : 0;
  });
  const left =
    total === null
      ? null
      : unallocated(
          total,
          amounts.map((amount) => ({ amount })),
        );
  const chosen = splits.map((split) => split.vehicleId).filter(Boolean);
  const duplicate = new Set(chosen).size < chosen.length;
  const valid =
    total !== null &&
    splits.every((split) => split.vehicleId) &&
    amounts.every((amount) => amount !== 0) &&
    !duplicate &&
    left === 0;
  return { amounts, left, duplicate, valid };
}

// One purchase over several vehicles: a vehicle and an amount on each row, and a line saying whether they balance.
export function SplitRows({
  splits,
  total,
  vehicleOptions,
  onChange,
  onSingle,
}: {
  splits: Split[];
  total: number | null;
  vehicleOptions: SearchOption[];
  onChange: (splits: Split[]) => void;
  // One row is left: back to a single vehicle.
  onSingle: (vehicleId: string) => void;
}) {
  const formats = useFormats();
  const { left, duplicate, valid } = splitState(splits, total);

  function change(index: number, part: Partial<Split>) {
    onChange(
      splits.map((split, at) => (at === index ? { ...split, ...part } : split)),
    );
  }

  function remove(index: number) {
    const rest = splits.filter((_, at) => at !== index);
    if (rest.length > 1) onChange(rest);
    else onSingle(rest[0]?.vehicleId ?? "");
  }

  function splitEqually() {
    if (total === null) return;
    const shares = splitEvenly(total, splits.length);
    onChange(
      splits.map((split, at) => ({ ...split, amount: String(shares[at]) })),
    );
  }

  return (
    <div className="f">
      <div className="flabrow">
        <span className="flab">Vehicles</span>
        <span className="mlinks">
          <LinkButton compact disabled={total === null} onClick={splitEqually}>
            Split equally
          </LinkButton>
          <LinkButton
            compact
            disabled={splits.length >= EXPENSE_MAX_VEHICLES}
            onClick={() => onChange([...splits, { vehicleId: "", amount: "" }])}
          >
            Add vehicle
          </LinkButton>
        </span>
      </div>
      <div className="msplit">
        {splits.map((split, index) => (
          <div key={index} className="arow">
            <SearchSelect
              aria-label={`Vehicle ${index + 1}`}
              options={vehicleOptions}
              value={split.vehicleId}
              placeholder="Choose vehicle"
              onChange={(id) => change(index, { vehicleId: id })}
            />
            <AmountInput
              aria-label={`Amount for vehicle ${index + 1}`}
              value={split.amount}
              onChange={(event) =>
                change(index, { amount: event.target.value })
              }
            />
            <button
              type="button"
              className="rmx"
              aria-label={`Remove vehicle ${index + 1}`}
              onClick={() => remove(index)}
            >
              <CloseIcon />
            </button>
          </div>
        ))}
      </div>
      {total !== null && left !== null && (
        <BalancePanel ok={valid}>
          {duplicate
            ? "The same vehicle is picked twice"
            : left > 0
              ? `${formats.kes(left)} left to allocate`
              : left < 0
                ? `${formats.kes(-left)} over the total`
                : valid
                  ? `Balanced, ${formats.kes(total)} across ${splits.length} vehicles`
                  : "Choose a vehicle and an amount for each row"}
        </BalancePanel>
      )}
    </div>
  );
}
