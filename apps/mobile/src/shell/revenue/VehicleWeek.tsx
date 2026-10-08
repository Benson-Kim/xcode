import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { FlatList, View } from "react-native";

import { weekDays } from "@xcode/shared/dates";

import { OfflineError, SessionEndedError } from "../../lib/api";
import { useFormats } from "../../lib/formats";
import type { RevenueVehicle, RevenueWeek } from "../../revenue/types";
import { loadWeek } from "../../revenue/week";
import { ErrorText, Text, useTheme } from "../../ui";
import { DayBar, useColumns } from "./DayBar";
import { keyOf, targetFor, type Waiting } from "./model";
import { styles } from "./styles";

type Columns = ReturnType<typeof useColumns>;

// The vehicle's own load of the week, kept on the week list's copy until it arrives.
function useVehicleWeek(
  owner: string,
  week: RevenueWeek,
  fallback: RevenueVehicle,
  onSessionEnded: () => void,
) {
  const [vehicle, setVehicle] = useState<RevenueVehicle>(fallback);
  const [problem, setProblem] = useState("");
  useEffect(() => {
    let active = true;
    loadWeek(owner, week.weekStart, fallback.id).then(
      ({ week: loaded }) => {
        const found = loaded.vehicles.find((item) => item.id === fallback.id);
        if (active && found) setVehicle(found);
      },
      (reason: Error) => {
        if (!active) return;
        if (reason instanceof SessionEndedError) return onSessionEnded();
        // Offline, the week list's copy of this vehicle stays on screen.
        setProblem(reason instanceof OfflineError ? "" : reason.message);
      },
    );
    return () => {
      active = false;
    };
  }, [owner, week.weekStart, fallback.id, onSessionEnded]);
  return { vehicle, problem };
}

function DetailHead({ columns }: { columns: Columns }) {
  const { colors } = useTheme();
  return (
    <View
      style={[
        styles.detailRow,
        styles.detailHead,
        { borderBottomColor: colors.cardLine },
      ]}
    >
      <Text
        weight="semibold"
        style={[styles.detailDay, columns.day, { color: colors.grey }]}
      >
        Day
      </Text>
      <Text
        weight="semibold"
        style={[styles.detailNumber, columns.number, { color: colors.grey }]}
      >
        Expected
      </Text>
      <Text
        weight="semibold"
        style={[
          styles.detailActual,
          { fontSize: 14, color: colors.grey, textAlign: "right" },
        ]}
      >
        Actual and difference
      </Text>
    </View>
  );
}

function DetailFoot({
  vehicle,
  columns,
}: {
  vehicle: RevenueVehicle;
  columns: Columns;
}) {
  const { colors } = useTheme();
  const formats = useFormats();
  return (
    <View
      accessible
      accessibilityLabel={`To date: expected ${formats.kes(vehicle.totalExpected)}, actual ${formats.kes(vehicle.totalAmount)}, ${formats.formatDifference(vehicle.totalAmount, vehicle.totalExpected)}`}
      style={styles.detailRow}
    >
      <Text weight="bold" style={[styles.detailDay, columns.day]}>
        To date
      </Text>
      <Text weight="bold" style={[styles.detailNumber, columns.number]}>
        {formats.kes(vehicle.totalExpected)}
      </Text>
      <View style={styles.detailActual}>
        <Text weight="bold">{formats.kes(vehicle.totalAmount)}</Text>
        <Text
          style={{
            fontSize: 13,
            color:
              vehicle.totalAmount < vehicle.totalExpected
                ? colors.red
                : colors.green,
          }}
        >
          {formats.formatDifference(vehicle.totalAmount, vehicle.totalExpected)}
        </Text>
      </View>
    </View>
  );
}

// One vehicle's week: expected, actual and the difference for each day, with a bar against expected.
export function VehicleWeek({
  owner,
  fallback,
  week,
  waiting,
  canCapture,
  header,
  onOpen,
  onSessionEnded,
}: {
  owner: string;
  fallback: RevenueVehicle;
  week: RevenueWeek;
  waiting: Waiting;
  canCapture: boolean;
  header: ReactNode;
  onOpen: (vehicle: RevenueVehicle, date: string, week: RevenueWeek) => void;
  onSessionEnded: () => void;
}) {
  const columns = useColumns();
  const { vehicle, problem } = useVehicleWeek(
    owner,
    week,
    fallback,
    onSessionEnded,
  );
  const vehicleWeek = useMemo(
    () => ({ ...week, vehicles: [vehicle] }),
    [week, vehicle],
  );
  // "Tue 29" for each day of the week, worked out once per week.
  const dayNames = useMemo(
    () =>
      new Map(
        weekDays(week.weekStart).map((day) => [
          day.date,
          `${day.shortName} ${day.dayOfMonth}`,
        ]),
      ),
    [week.weekStart],
  );
  const open = useCallback(
    (date: string) => onOpen(vehicle, date, vehicleWeek),
    [onOpen, vehicle, vehicleWeek],
  );
  return (
    <FlatList
      style={styles.list}
      contentContainerStyle={styles.content}
      data={vehicle.days}
      keyExtractor={(cell) => cell.date}
      ListHeaderComponent={
        <View style={styles.header}>
          {header}
          {problem ? <ErrorText>{problem}</ErrorText> : null}
          <DetailHead columns={columns} />
        </View>
      }
      renderItem={({ item }) => (
        <DayBar
          cell={item}
          name={dayNames.get(item.date) ?? item.date}
          today={week.businessDate}
          queued={waiting.get(keyOf(vehicle.id, item.date))}
          tappable={Boolean(
            targetFor(vehicle, item.date, vehicleWeek, waiting, canCapture),
          )}
          onOpen={open}
        />
      )}
      ListFooterComponent={<DetailFoot vehicle={vehicle} columns={columns} />}
    />
  );
}
