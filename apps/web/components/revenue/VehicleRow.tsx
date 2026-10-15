import { memo } from "react";

import { gapText, type RevenueVehicle } from "@xcode/shared/revenue";

import { useFormats } from "../../lib/formats";
import { DayCell } from "./DayCell";
import { RegPlate } from "./RegPlate";
import type { OpenDay } from "./useCaptureFlow";

// The gap to target as the design's chip: a signed figure, green at or above target, amber up to the band below
// it, red beyond (v2.31). Nothing while no target counts yet.
export function GapChip({
  gap,
  band,
}: {
  gap: number | null | undefined;
  band: "pos" | "amb" | "neg" | null | undefined;
}) {
  const formats = useFormats();
  if (gap === null || gap === undefined || !band) return null;
  return (
    <span className={`gap ${band}`}>{gapText(gap, formats.formatNumber)}</span>
  );
}

export const VehicleRow = memo(function VehicleRow({
  vehicle,
  today,
  canCapture,
  rowIndex,
  measure,
  onOpenDay,
}: {
  vehicle: RevenueVehicle;
  today: string;
  canCapture: boolean;
  rowIndex?: number;
  measure: (element: HTMLElement | null) => void;
  onOpenDay: OpenDay;
}) {
  const formats = useFormats();
  return (
    <tr ref={measure} data-measure={vehicle.id} aria-rowindex={rowIndex}>
      {/* A row header; the design's cell type and case, not a column heading's. */}
      <th scope="row" className="font-normal tracking-normal normal-case">
        <RegPlate>{vehicle.registration}</RegPlate>
      </th>
      {vehicle.days.map((day) => (
        <DayCell
          key={day.date}
          vehicle={vehicle}
          cell={day}
          today={today}
          canCapture={canCapture}
          onOpen={onOpenDay}
        />
      ))}
      <td className="r tot">{formats.formatNumber(vehicle.totalAmount)}</td>
      <td className="r">
        <GapChip gap={vehicle.gap} band={vehicle.gapBand} />
      </td>
    </tr>
  );
});
