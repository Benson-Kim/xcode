"use client";

import { useState } from "react";

import { vehicleLabel } from "@xcode/shared/revenue";

import type { SearchOption } from "../ui";
import { CatalogQuickAdd } from "./CatalogQuickAdd";
import type { Vehicle } from "./shared";
import { useCatalogRights } from "./useCatalogEditor";
import { useVehicleAddRight, VehicleQuickAdd } from "./VehicleQuickAdd";

type NewVehicle = { typed: string; row: number | null };

// The options given, then those added here that the reloaded options do not hold yet.
const withAdded = (options: SearchOption[], added: SearchOption[]) => [
  ...options,
  ...added.filter(
    (option) => !options.some((offered) => offered.value === option.value),
  ),
];

// "+ Add new" for the item and vehicle pickers of an entry form. Each adder is undefined without the right to
// create; `dialogs` goes after the form's closing tag, since the create forms cannot nest inside it. What is added
// stays among the options (withItems, withVehicles) until the reload lists it, so the field shows it at once.
export function useQuickAdds({
  onItem,
  onVehicle,
  reload,
  date,
  labelVehicle = vehicleLabel,
}: {
  onItem: (id: string) => void;
  // row is the split row the vehicle was typed on, null for the single vehicle.
  onVehicle?: (id: string, row: number | null) => void;
  reload?: () => void;
  // The entry's date: a vehicle added for an earlier day joins the fleet on it.
  date?: string;
  // How the form's vehicle list names a vehicle, so an added one reads the same before and after the reload.
  labelVehicle?: (vehicle: Vehicle) => string;
}) {
  const catalog = useCatalogRights();
  const canAddVehicle = useVehicleAddRight() && onVehicle !== undefined;
  const [item, setItem] = useState<string | null>(null);
  const [vehicle, setVehicle] = useState<NewVehicle | null>(null);
  const [addedItems, setAddedItems] = useState<SearchOption[]>([]);
  const [addedVehicles, setAddedVehicles] = useState<SearchOption[]>([]);

  const dialogs = (
    <>
      {item !== null && (
        <CatalogQuickAdd
          name={item}
          onCreated={(created) => {
            setItem(null);
            setAddedItems((current) => [
              ...current,
              {
                value: created.id,
                label: created.name,
                group: created.categoryName,
              },
            ]);
            onItem(created.id);
            reload?.();
          }}
          onClose={() => setItem(null)}
        />
      )}
      {vehicle && (
        <VehicleQuickAdd
          registration={vehicle.typed}
          date={date}
          onCreated={(created) => {
            setVehicle(null);
            setAddedVehicles((current) => [
              ...current,
              { value: created.id, label: labelVehicle(created) },
            ]);
            onVehicle?.(created.id, vehicle.row);
            reload?.();
          }}
          onClose={() => setVehicle(null)}
        />
      )}
    </>
  );

  return {
    addItem: catalog.add ? (typed: string) => setItem(typed) : undefined,
    addVehicle: canAddVehicle
      ? (typed: string, row: number | null = null) => setVehicle({ typed, row })
      : undefined,
    withItems: (options: SearchOption[]) => withAdded(options, addedItems),
    withVehicles: (options: SearchOption[]) =>
      withAdded(options, addedVehicles),
    dialogs,
  };
}
