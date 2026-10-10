import { memo } from "react";

import type { WeekDay } from "@xcode/shared/dates";
import { percentText } from "@xcode/shared/format";
import type { RevenueVehicle } from "@xcode/shared/revenue";

import { useFormats } from "../../lib/formats";
import { ChevronIcon, cn } from "../ui";
import { DayCell } from "./DayCell";
import { RegPlate } from "./RegPlate";
import { DAY_COLUMN } from "./styles";
import type { OpenDay } from "./useCaptureFlow";
import { VehicleWeek } from "./VehicleWeek";

export const VehicleRow = memo(function VehicleRow({
  vehicle,
  isOpen,
  days,
  today,
  canCapture,
  rowIndex,
  measure,
  onToggle,
  onOpenDay,
}: {
  vehicle: RevenueVehicle;
  isOpen: boolean;
  days: WeekDay[];
  today: string;
  canCapture: boolean;
  rowIndex?: number;
  measure: (element: HTMLElement | null) => void;
  onToggle: (id: string) => void;
  onOpenDay: OpenDay;
}) {
  const formats = useFormats();
  return (
    <>
      <tr ref={measure} data-measure={vehicle.id} aria-rowindex={rowIndex}>
        <VehicleLabel vehicle={vehicle} isOpen={isOpen} onToggle={onToggle} />
        {vehicle.days.map((day) => (
          <td key={day.date} className={cn("r", DAY_COLUMN)}>
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
      {isOpen && (
        <tr
          id={`revenue-detail-${vehicle.id}`}
          ref={measure}
          data-measure={`${vehicle.id}:detail`}
          aria-rowindex={rowIndex === undefined ? undefined : rowIndex + 1}
        >
          <td colSpan={10}>
            <VehicleWeek
              vehicle={vehicle}
              days={days}
              today={today}
              canCapture={canCapture}
              onOpen={(date, from) => onOpenDay(vehicle, date, from)}
            />
          </td>
        </tr>
      )}
    </>
  );
});

function VehicleLabel({
  vehicle,
  isOpen,
  onToggle,
}: {
  vehicle: RevenueVehicle;
  isOpen: boolean;
  onToggle: (id: string) => void;
}) {
  return (
    // A row header; the design's cell type and case, not a column heading's.
    <th scope="row" className="font-normal tracking-normal normal-case">
      <button
        type="button"
        aria-expanded={isOpen}
        aria-controls={isOpen ? `revenue-detail-${vehicle.id}` : undefined}
        onClick={() => onToggle(vehicle.id)}
        className="inline-flex items-center gap-1.5 text-left"
      >
        <ChevronIcon
          className={cn(
            "shrink-0 text-slate transition-transform motion-reduce:transition-none",
            !isOpen && "-rotate-90",
          )}
        />
        <RegPlate>{vehicle.registration}</RegPlate>
      </button>
      <small className="block pl-5.5 text-xs font-semibold text-slate">
        {vehicle.companyName}
      </small>
    </th>
  );
}
