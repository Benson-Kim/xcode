import type { VehicleOption } from "../setup/shared";

export function formatShare(amount: number) {
  return Number.isInteger(amount) ? String(amount) : amount.toFixed(2);
}

// Splits a total into whole cents, giving the first vehicles the remainder so it adds up exactly.
export function splitAmountEvenly(total: number, vehicleIds: string[]) {
  if (!vehicleIds.length) return {};
  const totalCents = Math.round(total * 100);
  const baseCents = Math.floor(totalCents / vehicleIds.length);
  const remainder = totalCents - baseCents * vehicleIds.length;
  return Object.fromEntries(
    vehicleIds.map((vehicleId, index) => [
      vehicleId,
      formatShare((baseCents + (index < remainder ? 1 : 0)) / 100),
    ]),
  );
}

export function sumShares(ids: string[], shares: Record<string, string>) {
  return ids.reduce((sum, id) => sum + (Number(shares[id]) || 0), 0);
}

export function isInFleet(vehicles: VehicleOption[], vehicleId: string) {
  return vehicles.find((vehicle) => vehicle.id === vehicleId)?.active !== false;
}

// Splits what is left after the shares of vehicles not in the fleet across the vehicles that are.
export function splitAcrossFleet(
  vehicles: VehicleOption[],
  shares: Record<string, string>,
  total: number,
  vehicleIds: string[],
) {
  const kept = Object.fromEntries(
    vehicleIds
      .filter((vehicleId) => !isInFleet(vehicles, vehicleId))
      .map((vehicleId) => [vehicleId, shares[vehicleId] ?? "0"]),
  );
  const keptTotal = Object.values(kept).reduce(
    (sum, share) => sum + (Number(share) || 0),
    0,
  );
  return {
    ...kept,
    ...splitAmountEvenly(
      Math.max(0, total - keptTotal),
      vehicleIds.filter((vehicleId) => isInFleet(vehicles, vehicleId)),
    ),
  };
}

export function balanceLabel(
  state: {
    selectedCount: number;
    total: number;
    difference: number;
    isBalanced: boolean;
  },
  kes: (amount: number) => string,
) {
  const { selectedCount, total, difference, isBalanced } = state;
  if (!selectedCount) return "Tick at least one vehicle";
  if (!total) return "Enter the amount";
  if (isBalanced) return "Balanced";
  return difference > 0
    ? `${kes(difference / 100)} still to allocate`
    : `${kes(-difference / 100)} too much`;
}

export function summarizeAllocation(
  vehicles: VehicleOption[],
  selected: string[],
  shares: Record<string, string>,
  total: number,
) {
  const allocationTotal = sumShares(selected, shares);
  const difference =
    Math.round(total * 100) - Math.round(allocationTotal * 100);
  const postingIds = selected.filter((id) => isInFleet(vehicles, id));
  return {
    allocationTotal,
    difference,
    isBalanced: selected.length > 0 && total > 0 && difference === 0,
    postingIds,
    outOfFleetIds: selected.filter((id) => !isInFleet(vehicles, id)),
    // What posts on each due date: the shares of the vehicles still in the fleet.
    postingTotal: sumShares(postingIds, shares),
  };
}

export function companyVehicleIds(
  vehicles: VehicleOption[],
  companyId: string,
) {
  return vehicles
    .filter(
      (vehicle) => vehicle.companyId === companyId && vehicle.active !== false,
    )
    .map((vehicle) => vehicle.id);
}

export function withoutKey(shares: Record<string, string>, key: string) {
  const next = { ...shares };
  delete next[key];
  return next;
}
