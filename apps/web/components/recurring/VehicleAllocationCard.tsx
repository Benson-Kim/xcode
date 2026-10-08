import { useFormats } from "../../lib/formats";
import type { VehicleOption } from "../setup/shared";
import {
  BalancePanel,
  Card,
  CardHeader,
  Chip,
  ChipGroup,
  Choice,
  CurrencyInput,
  ErrorText,
  GroupLabel,
  Hint,
  ListSkeleton,
} from "../ui";
import { balanceLabel } from "./allocation";
import type { Allocations } from "./useAllocations";

type Props = {
  vehicles: VehicleOption[];
  vehiclesLoading: boolean;
  disabled: boolean;
  alloc: Allocations;
  error?: string;
};

function SelectionActions({
  companies,
  alloc,
}: {
  companies: [string, string][];
  alloc: Allocations;
}) {
  return (
    <ChipGroup aria-label="Vehicle selection actions">
      {companies
        .filter(([companyId]) => companyId)
        .map(([companyId, companyName]) => (
          <Chip key={companyId} onClick={() => alloc.selectCompany(companyId)}>
            All {companyName}
          </Chip>
        ))}
      <Chip onClick={alloc.clear}>Clear</Chip>
      <Chip
        disabled={!alloc.total || !alloc.postingIds.length}
        onClick={alloc.splitEqually}
      >
        Split equally
      </Chip>
    </ChipGroup>
  );
}

function AllocationHints({
  vehicles,
  disabled,
  alloc,
}: Pick<Props, "vehicles" | "disabled" | "alloc">) {
  const { outOfFleetIds } = alloc;
  const vehicleName = (vehicleId: string) =>
    vehicles.find((vehicle) => vehicle.id === vehicleId)?.registration ??
    "A vehicle";
  return (
    <>
      {alloc.splitNotice ? (
        <Hint role="status">{alloc.splitNotice}</Hint>
      ) : (!alloc.total || !alloc.selected.length) && !disabled ? (
        <Hint>
          Enter the amount and select vehicles to enable Split equally.
        </Hint>
      ) : null}
      {outOfFleetIds.length > 0 && (
        <Hint>
          {outOfFleetIds.length === 1
            ? `${vehicleName(outOfFleetIds[0])} is not in the fleet today, so its share stays in the total but does not post.`
            : `${outOfFleetIds.map(vehicleName).join(", ")} are not in the fleet today, so their shares stay in the total but do not post.`}
          {!disabled && " Untick a vehicle to take its share off the amount."}
        </Hint>
      )}
    </>
  );
}

function VehicleShareRow({
  vehicle,
  disabled,
  alloc,
}: {
  vehicle: VehicleOption;
  disabled: boolean;
  alloc: Allocations;
}) {
  const ticked = alloc.selected.includes(vehicle.id);
  return (
    <div className="grid min-h-13 grid-cols-[minmax(0,320px)_200px] items-center gap-4 border-t border-divider max-[720px]:grid-cols-[minmax(0,1fr)_140px] max-[720px]:gap-3">
      <Choice
        label={
          vehicle.active === false
            ? `${vehicle.registration} (not in the fleet today)`
            : vehicle.registration
        }
        checked={ticked}
        disabled={disabled || (vehicle.active === false && !ticked)}
        onChange={(event) =>
          alloc.toggleVehicle(vehicle.id, event.target.checked)
        }
      />
      {ticked ? (
        <CurrencyInput
          density="compact"
          aria-label={`Share for ${vehicle.registration}`}
          value={alloc.shares[vehicle.id] ?? "0"}
          disabled={disabled || vehicle.active === false}
          onChange={(event) => alloc.setShare(vehicle.id, event.target.value)}
        />
      ) : (
        <span />
      )}
    </div>
  );
}

export function VehicleAllocationCard({
  vehicles,
  vehiclesLoading,
  disabled,
  alloc,
  error,
}: Props) {
  const { kes } = useFormats();
  const companies = [
    ...new Map(
      vehicles.map((vehicle) => [vehicle.companyId, vehicle.companyName]),
    ).entries(),
  ];
  return (
    <Card density="form">
      <CardHeader
        title="Vehicles"
        description="Split the amount across one or more vehicles. It must add up exactly."
      />
      {!disabled && !vehiclesLoading && (
        <SelectionActions companies={companies} alloc={alloc} />
      )}
      <AllocationHints vehicles={vehicles} disabled={disabled} alloc={alloc} />
      {vehiclesLoading && (
        <div role="status" aria-busy="true">
          <span className="sr-only">Loading vehicles</span>
          <ListSkeleton rows={3} />
        </div>
      )}
      <div>
        {!vehiclesLoading &&
          companies.map(([companyId, companyName]) => (
            <div key={companyId || "vehicles"}>
              {companyName && <GroupLabel>{companyName}</GroupLabel>}
              {vehicles
                .filter((vehicle) => vehicle.companyId === companyId)
                .map((vehicle) => (
                  <VehicleShareRow
                    key={vehicle.id}
                    vehicle={vehicle}
                    disabled={disabled}
                    alloc={alloc}
                  />
                ))}
            </div>
          ))}
      </div>
      <BalancePanel ok={alloc.isBalanced}>
        <span>
          Allocated {kes(alloc.allocationTotal)} of {kes(alloc.total)}
        </span>
        <span>
          {balanceLabel(
            {
              selectedCount: alloc.selected.length,
              total: alloc.total,
              difference: alloc.difference,
              isBalanced: alloc.isBalanced,
            },
            kes,
          )}
        </span>
      </BalancePanel>
      {error && <ErrorText>{error}</ErrorText>}
    </Card>
  );
}
