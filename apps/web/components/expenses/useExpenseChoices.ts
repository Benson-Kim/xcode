"use client";

import { useState } from "react";

import {
  expenseOptionsPath,
  type ExpenseLedgerRow,
  type ExpenseOptions,
} from "@xcode/shared/expenses";

import { useResource } from "../../lib/data";
import type { SearchOption } from "../ui";

export const isDateShape = (value: string) => /^\d{4}-\d{2}-\d{2}$/.test(value);

// The vehicles and items to pick from on a date. While the next ones load the last ones stay, and the vehicle and
// item of a row being changed are listed even if they are no longer offered.
export function useExpenseChoices(date: string, entry?: ExpenseLedgerRow) {
  const options = useResource<ExpenseOptions>(
    isDateShape(date) ? expenseOptionsPath(date) : null,
  );
  const [held, setHeld] = useState<ExpenseOptions | undefined>(options.data);
  if (options.data && options.data !== held) setHeld(options.data);
  const choices = options.data ?? held;

  const vehicles = choices?.vehicles ?? [];
  const vehicleChoices =
    entry && !vehicles.some((vehicle) => vehicle.id === entry.vehicleId)
      ? [
          ...vehicles,
          {
            id: entry.vehicleId,
            companyId: "",
            companyName: "",
            registration: entry.registration,
            active: false,
          },
        ]
      : vehicles;
  const items = choices?.items ?? [];
  const itemChoices =
    entry?.expenseItemId &&
    !items.some((item) => item.id === entry.expenseItemId)
      ? [
          ...items,
          {
            id: entry.expenseItemId,
            name: entry.itemName,
            categoryId: "",
            categoryName: entry.categoryName ?? "Other",
            bucket: entry.bucket,
          },
        ]
      : items;

  const vehicleOptions: SearchOption[] = vehicleChoices.map((vehicle) => ({
    value: vehicle.id,
    label: vehicle.companyName
      ? `${vehicle.registration}, ${vehicle.companyName}`
      : vehicle.registration,
  }));

  return {
    vehicleChoices,
    vehicleOptions,
    itemChoices,
    error: choices ? "" : options.error,
  };
}
