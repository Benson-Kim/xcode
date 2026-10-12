import { memo } from "react";

import { percentText } from "@xcode/shared/format";
import type { RevenueVehicle } from "@xcode/shared/revenue";

import { useFormats } from "../../lib/formats";
import { DayCell } from "./DayCell";
import { RegPlate } from "./RegPlate";
import type { OpenDay } from "./useCaptureFlow";

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
        <small className="block text-xs font-semibold text-slate">
          {vehicle.companyName}
        </small>
      </th>
      {vehicle.days.map((day) => (
        <td key={day.date} className="r">
          <DayCell
            vehicle={vehicle}
            cell={day}
            today={today}
            canCapture={canCapture}
            onOpen={onOpenDay}
          />
        </td>
      ))}
      <td className="r tot">{formats.formatNumber(vehicle.totalAmount)}</td>
      <td>
        {vehicle.percent !== null && (
          <div className="prog">
            <div className="t" aria-hidden="true">
              <i
                className={vehicle.percent >= 100 ? "full" : undefined}
                style={{ width: `${Math.min(vehicle.percent, 100)}%` }}
              />
            </div>
            <span>{percentText(vehicle.percent)}</span>
          </div>
        )}
      </td>
    </tr>
  );
});
