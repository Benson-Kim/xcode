import { useState } from "react";

import { plural } from "@xcode/shared/format";

import { useFormats } from "../../lib/formats";
import type { RecurringItem, VehicleOption } from "../setup/shared";
import {
  companyVehicleIds,
  formatShare,
  splitAcrossFleet,
  summarizeAllocation,
  sumShares,
  withoutKey,
} from "./allocation";

type Params = {
  item?: RecurringItem;
  vehicles: VehicleOption[];
  preselectVehicle?: string;
  amount: string;
  setAmount: (value: string) => void;
};

export function useAllocations({
  item,
  vehicles,
  preselectVehicle,
  amount,
  setAmount,
}: Params) {
  const { kes } = useFormats();
  const [selected, setSelected] = useState<string[]>(
    () =>
      item?.allocations.map((allocation) => allocation.vehicleId) ||
      (preselectVehicle ? [preselectVehicle] : []),
  );
  const [shares, setShares] = useState<Record<string, string>>(() =>
    Object.fromEntries(
      item?.allocations.map((allocation) => [
        allocation.vehicleId,
        formatShare(allocation.amount),
      ]) || [],
    ),
  );
  const [manual, setManual] = useState(Boolean(item));
  const [splitNotice, setSplitNotice] = useState("");

  const total = Number(amount) || 0;
  const summary = summarizeAllocation(vehicles, selected, shares, total);
  const { postingIds } = summary;
  const splitFor = (amountTotal: number, ids: string[]) =>
    splitAcrossFleet(vehicles, shares, amountTotal, ids);

  function changeAmount(value: string) {
    setAmount(value);
    setSplitNotice("");
    if (!manual) setShares(splitFor(Number(value) || 0, selected));
  }

  function toggleVehicle(vehicleId: string, checked: boolean) {
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
      setShares((current) => withoutKey(current, vehicleId));
      setSplitNotice(
        `Took ${vehicle.registration}'s ${kes(share)} share off the amount.`,
      );
      return;
    }
    if (!manual) setShares(splitFor(total, next));
    else
      setShares((current) =>
        checked
          ? { ...current, [vehicleId]: "0" }
          : withoutKey(current, vehicleId),
      );
  }

  function selectCompany(companyId: string) {
    const next = [
      ...new Set([...selected, ...companyVehicleIds(vehicles, companyId)]),
    ];
    setSelected(next);
    setSplitNotice("");
    setManual(false);
    setShares(splitFor(total, next));
  }

  function clear() {
    setSelected([]);
    setShares({});
    setManual(false);
  }

  function splitEqually() {
    if (!total || !postingIds.length) return;
    const shared = splitFor(total, selected);
    setManual(false);
    setShares(shared);
    setSplitNotice(
      `Split ${kes(sumShares(postingIds, shared))} equally across ${plural(postingIds.length, "vehicle", "vehicles")}.`,
    );
  }

  function setShare(vehicleId: string, value: string) {
    setSplitNotice("");
    setManual(true);
    setShares({ ...shares, [vehicleId]: value });
  }

  return {
    selected,
    shares,
    splitNotice,
    total,
    ...summary,
    changeAmount,
    toggleVehicle,
    selectCompany,
    clear,
    splitEqually,
    setShare,
  };
}

export type Allocations = ReturnType<typeof useAllocations>;
