import { memo } from "react";

import type { WeekDay } from "@xcode/shared/dates";
import { percentText } from "@xcode/shared/format";
import type { RevenueVehicle } from "@xcode/shared/revenue";

import { useFormats } from "../../lib/formats";
import { ChevronIcon, cn } from "../ui";
import { DayCell } from "./DayCell";
import { CELL, DAY_COLUMN } from "./styles";
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
          <td
            key={day.date}
            className={cn(
              CELL,
              DAY_COLUMN,
              "text-right",
              day.date === today && "bg-blue-wash",
            )}
          >
            <DayCell
              vehicle={vehicle}
              cell={day}
              today={today}
              canCapture={canCapture}
              onOpen={onOpenDay}
            />
          </td>
        ))}
        <td className={cn(CELL, "text-right")}>
          <strong>{formats.formatNumber(vehicle.totalAmount)}</strong>
        </td>
        <td className={cn(CELL, "text-right")}>
          {vehicle.percent !== null && (
            <span
              className={cn("font-bold", vehicle.percent < 90 && "text-red")}
            >
              {percentText(vehicle.percent)}
            </span>
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
          <td
            colSpan={10}
            className="border-b border-divider bg-paper px-3 pt-1 pb-4"
          >
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
    <th
      scope="row"
      className={cn(
        CELL,
        "sticky left-0 z-1 min-w-35 bg-surface text-left font-normal",
      )}
    >
      <button
        type="button"
        aria-expanded={isOpen}
        aria-controls={isOpen ? `revenue-detail-${vehicle.id}` : undefined}
        onClick={() => onToggle(vehicle.id)}
        className="inline-flex min-h-8 items-center gap-1.5 text-left font-bold text-blue hover:underline"
      >
        <ChevronIcon
          className={cn(
            "shrink-0 transition-transform motion-reduce:transition-none",
            !isOpen && "-rotate-90",
          )}
        />
        {vehicle.registration}
      </button>
      <small className="block pl-5.5 text-xs text-grey">
        {vehicle.companyName}
      </small>
    </th>
  );
}
