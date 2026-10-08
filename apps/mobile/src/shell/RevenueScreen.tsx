import { useState } from "react";
import { View } from "react-native";

import { permissionChecker } from "@xcode/shared/permissions";

import type { StoredPerson } from "../lib/storage";
import type { RevenueQueue } from "../revenue/queue";
import { Card, ScreenTitle } from "./parts";
import { CaptureSheet } from "./revenue/CaptureSheet";
import { RevenueHeader } from "./revenue/HeaderNav";
import { keyOf, type ViewMode } from "./revenue/model";
import { DayList, WeekList, emptyList } from "./revenue/rows";
import { styles } from "./revenue/styles";
import { useCaptureDay, useDayRows } from "./revenue/useCaptureDay";
import { useCaptureTarget } from "./revenue/useCaptureTarget";
import { useRevenueWeek } from "./revenue/useRevenueWeek";
import { useWaiting } from "./revenue/useWaiting";
import { VehicleWeek } from "./revenue/VehicleWeek";

function access(person: StoredPerson) {
  const can = permissionChecker(person.permissions);
  return {
    canView: can("revenue.view"),
    canCapture: can("revenue.capture"),
    canReason: can("revenue.no_earnings"),
    canCorrect: can("revenue.correct"),
  };
}

function NoAccess() {
  return (
    <View style={[styles.content, { gap: 16 }]}>
      <ScreenTitle>Revenue</ScreenTitle>
      <Card
        title="Revenue access"
        sub="Your admin has not granted revenue viewing access."
      />
    </View>
  );
}

export function RevenueScreen({
  person,
  queue,
  businessDate,
  onSessionEnded,
}: {
  person: StoredPerson;
  queue: RevenueQueue;
  // The business date the phone last saw, for when no week has loaded (offline).
  businessDate?: string;
  onSessionEnded: () => void;
}) {
  const owner = person.userId ?? person.phoneNumber;
  const { canView, canCapture, canReason, canCorrect } = access(person);

  const [mode, setMode] = useState<ViewMode>("day");
  const [detail, setDetail] = useState<string | null>(null);
  const { week, saved, loading, error, setWeekStart, retry, shown } =
    useRevenueWeek({ canView, owner, queue, onSessionEnded });

  const { waiting, canReplace } = useWaiting({
    entries: queue.entries,
    today: week?.businessDate ?? businessDate,
    canCapture,
    canCorrect,
  });
  const { day, inWeek, firstNeeded, goToDay } = useCaptureDay({
    week,
    waiting,
    canCapture,
    queueLoaded: queue.loaded,
    setWeekStart,
  });
  const rows = useDayRows({ week, inWeek, day, waiting, canCapture });
  const { target, openDay, openDetailDay, save, close } = useCaptureTarget({
    week,
    waiting,
    day,
    canCapture,
    add: queue.add,
  });

  if (!canView) return <NoAccess />;

  const detailVehicle = detail
    ? week?.vehicles.find((vehicle) => vehicle.id === detail)
    : undefined;
  const header = (
    <RevenueHeader
      mode={mode}
      onMode={setMode}
      week={week}
      detailVehicle={detailVehicle}
      onBack={() => setDetail(null)}
      notice={{ saved, error, loading }}
      onRetry={retry}
      queue={queue}
      canReplace={canReplace}
      day={day}
      inWeek={inWeek}
      rows={rows}
      firstNeeded={firstNeeded}
      onGoDay={goToDay}
      onWeek={setWeekStart}
    />
  );
  const empty = emptyList({ loading, week, mode, inWeek });

  return (
    <>
      {detailVehicle && week ? (
        <VehicleWeek
          key={`${detailVehicle.id}/${week.weekStart}/${shown}`}
          owner={owner}
          fallback={detailVehicle}
          week={week}
          waiting={waiting}
          canCapture={canCapture}
          header={header}
          onOpen={openDetailDay}
          onSessionEnded={onSessionEnded}
        />
      ) : mode === "day" ? (
        <DayList rows={rows} header={header} empty={empty} onOpen={openDay} />
      ) : (
        <WeekList
          week={week}
          header={header}
          empty={empty}
          onOpen={setDetail}
        />
      )}
      {target && (
        <CaptureSheet
          key={keyOf(target.vehicle.id, target.date)}
          target={target}
          canReason={canReason}
          onSave={(entry) => save(target, entry)}
          onClose={close}
        />
      )}
    </>
  );
}
