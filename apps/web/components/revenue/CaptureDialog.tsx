import { vehicleLabel } from "@xcode/shared/revenue";

import { revenueApi } from "../../lib/endpoints/revenue";
import { FormDialog } from "../pettycash/DialogFooter";
import { Banner, ListSkeleton, LoadingRegion } from "../ui";
import { CaptureForm } from "./CaptureForm";
import type { useCaptureFlow } from "./useCaptureFlow";

export function CaptureDialog({
  flow,
  today,
  earliest,
  threshold,
}: {
  flow: ReturnType<typeof useCaptureFlow>;
  today: string;
  earliest: string | null;
  threshold: number;
}) {
  const { capture, vehicle, cell, elsewhere } = flow;
  return (
    <FormDialog
      open={capture !== null}
      size="sm"
      title={vehicle ? vehicleLabel(vehicle) : flow.title}
      onClose={flow.close}
    >
      {capture &&
        (vehicle && cell ? (
          <CaptureForm
            key={`${capture.vehicleId}:${capture.date}`}
            vehicle={vehicle}
            cell={cell}
            today={today}
            earliest={earliest}
            threshold={threshold}
            onShiftDay={flow.shiftDay}
            onCancel={flow.close}
            onDone={(wasNew) => flow.advance(capture, wasNew)}
            reload={async () =>
              (
                await revenueApi.vehicleWeek(capture.vehicleId, capture.date)
              ).vehicles[0]?.days.find((day) => day.date === capture.date)
            }
          />
        ) : elsewhere.error ? (
          <Banner>{elsewhere.error}</Banner>
        ) : elsewhere.data ? (
          <Banner>
            This day is outside the vehicle&apos;s time in the fleet.
          </Banner>
        ) : (
          <LoadingRegion label="Loading the day">
            <ListSkeleton rows={2} />
          </LoadingRegion>
        ))}
    </FormDialog>
  );
}
