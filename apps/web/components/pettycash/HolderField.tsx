"use client";

import {
  pettyCashOverviewPath,
  type PettyCashFloat,
  type PettyCashHolder,
  type PettyCashOverview,
} from "@xcode/shared/pettyCash";

import { useResource } from "../../lib/data";
import { useFormats } from "../../lib/formats";
import { cn, Field, SelectInput } from "../ui";

// The manager the cash goes to or comes from, with the cash they hold at the right of the label (a figure, so it
// stays). A float the page already has gives it; any other is read from that manager's own overview. An expense that
// asks whose float it goes on leaves the figure out.
export function HolderField({
  holders,
  value,
  error,
  floats,
  showBalance = true,
  autoFocus,
  onChange,
}: {
  holders: PettyCashHolder[];
  value: string;
  error?: string;
  floats?: PettyCashFloat[];
  showBalance?: boolean;
  autoFocus: boolean;
  onChange: (holderId: string) => void;
}) {
  const formats = useFormats();
  const known = floats?.find((float) => float.holderId === value);
  const fetched = useResource<PettyCashOverview>(
    showBalance && value && !known
      ? pettyCashOverviewPath({ holderId: value })
      : null,
  );
  const balance = !showBalance
    ? undefined
    : known
      ? known.balance
      : fetched.data
        ? (fetched.data.floats.find((float) => float.holderId === value)
            ?.balance ?? 0)
        : undefined;
  return (
    <Field
      id="pc-holder"
      label="Manager"
      error={error}
      action={
        showBalance ? (
          <span
            className={cn(
              "hint",
              balance !== undefined && balance < 0 && "neg",
            )}
          >
            {balance === undefined
              ? ""
              : `Cash on hand ${formats.formatNumber(balance)}`}
          </span>
        ) : undefined
      }
    >
      <SelectInput
        autoFocus={autoFocus}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      >
        <option value="">Choose manager</option>
        {holders.map((holder) => (
          <option key={holder.id} value={holder.id}>
            {`${holder.name}${holder.active ? "" : " (not active)"}`}
          </option>
        ))}
      </SelectInput>
    </Field>
  );
}
