import { revenueApi } from "../../lib/endpoints/revenue";
import { Banner, Dialog, ListSkeleton, LoadingRegion } from "../ui";
import { CaptureForm } from "./CaptureForm";
import type { useCaptureFlow } from "./useCaptureFlow";

export function CaptureDialog({
  flow,
  canChooseReason,
}: {
  flow: ReturnType<typeof useCaptureFlow>;
  canChooseReason: boolean;
}) {
  const { capture, vehicle, cell, elsewhere } = flow;
  return (
    <Dialog open={capture !== null} title={flow.title} onClose={flow.close}>
      {capture &&
        (vehicle && cell ? (
          <CaptureForm
            key={`${capture.vehicleId}:${capture.date}`}
            vehicle={vehicle}
            cell={cell}
            info={capture.info}
            canChooseReason={canChooseReason}
            onCancel={flow.close}
            onDone={() => flow.advance(capture)}
            onOpenDay={flow.fillFirst}
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
    </Dialog>
  );
}
