import { StyleSheet, View } from "react-native";

import { useFormats } from "../../lib/formats";
import { useOnline } from "../../lib/network";
import { queueCounts, type RevenueQueue } from "../../revenue/queue";
import type { QueuedCapture } from "../../revenue/types";
import { Button, Text, useTheme } from "../../ui";
import { keyOf, valueText } from "./model";
import { styles as shared } from "./styles";

type Entry = {
  entry: QueuedCapture;
  queue: RevenueQueue;
};

// What the person can do about a conflict: see both values and keep one.
function ConflictDetail({
  entry,
  queue,
  canReplace,
}: Entry & { canReplace: (entry: QueuedCapture) => boolean }) {
  const { colors } = useTheme();
  const formats = useFormats();
  // Replacing needs the person's own right to change that day, and the API's say on the saved record (canEdit).
  const mayReplace = canReplace(entry) && entry.current?.canEdit !== false;
  return (
    <>
      <Text style={{ fontSize: 14, color: colors.grey }}>
        {entry.current
          ? `Saved: ${valueText(formats, entry.current)}${entry.current.note ? ` (${entry.current.note})` : ""}`
          : "Connect to the internet to see what was saved."}
      </Text>
      <Text
        style={{ fontSize: 14, color: colors.grey }}
      >{`Yours: ${valueText(formats, entry)}${entry.note ? ` (${entry.note})` : ""}`}</Text>
      {entry.current && !mayReplace ? (
        <Text style={{ fontSize: 14, color: colors.grey }}>
          {canReplace(entry)
            ? "Your access does not include changing the saved record for this day."
            : "Changing a day after it has passed needs Correct revenue after the day."}
        </Text>
      ) : null}
      {/* Stacked: each choice keeps its whole label on one line on a narrow phone. */}
      <View style={styles.choices}>
        {entry.current ? (
          mayReplace && (
            <Button
              onPress={() => void queue.replace(entry)}
              style={styles.choice}
            >
              Replace with mine
            </Button>
          )
        ) : (
          <Button onPress={() => void queue.retry(entry)} style={styles.choice}>
            Check again
          </Button>
        )}
        <Button
          tone="outline"
          onPress={() => void queue.discard(entry)}
          style={styles.choice}
        >
          Keep saved value
        </Button>
      </View>
    </>
  );
}

function EntryActions({ entry, queue }: Entry) {
  return (
    <View style={styles.actions}>
      <Button
        tone="outline"
        onPress={() => void queue.retry(entry)}
        style={styles.flexButton}
      >
        Try again
      </Button>
      <Button
        tone="outline"
        onPress={() => void queue.discard(entry)}
        style={styles.flexButton}
      >
        Discard
      </Button>
    </View>
  );
}

function QueueEntry({
  entry,
  queue,
  canReplace,
}: Entry & {
  canReplace: (entry: QueuedCapture) => boolean;
}) {
  const { colors } = useTheme();
  const formats = useFormats();
  return (
    <View
      style={[
        styles.problem,
        { borderColor: colors.cardLine, backgroundColor: colors.surface },
      ]}
    >
      <Text weight="bold">{`${entry.registration}, ${formats.formatWeekdayDate(entry.date)}`}</Text>
      <Text style={{ fontSize: 14 }}>{entry.message}</Text>
      {entry.state === "conflict" ? (
        <ConflictDetail entry={entry} queue={queue} canReplace={canReplace} />
      ) : (
        <EntryActions entry={entry} queue={queue} />
      )}
    </View>
  );
}

// Captures that have not reached the API yet. Conflicts and refusals wait for the person; the rest go on their own.
export function QueuePanel({
  queue,
  canReplace,
}: {
  queue: RevenueQueue;
  canReplace: (entry: QueuedCapture) => boolean;
}) {
  const { colors } = useTheme();
  const offline = !useOnline();
  if (!queue.entries.length) return null;
  const counts = queueCounts(queue.entries);
  const summary = [
    counts.waiting ? `${counts.waiting} waiting to send` : "",
    counts.conflicts
      ? `${counts.conflicts} ${counts.conflicts === 1 ? "conflict" : "conflicts"}`
      : "",
    counts.failed ? `${counts.failed} not saved` : "",
  ].filter(Boolean);
  return (
    <View
      style={[
        styles.panel,
        { borderColor: colors.amberLine, backgroundColor: colors.amberBg },
      ]}
    >
      <View style={styles.panelHead}>
        <View style={{ flex: 1 }}>
          <Text
            weight="bold"
            accessibilityRole="header"
            style={{ color: colors.amberText }}
          >
            On this phone
          </Text>
          <Text style={{ fontSize: 14, color: colors.amberText }}>
            {summary.join(", ")}
          </Text>
          {offline && counts.waiting > 0 ? (
            <Text style={{ fontSize: 14, color: colors.amberText }}>
              No internet. They are sent when you are back online.
            </Text>
          ) : null}
        </View>
        {counts.waiting > 0 && (
          <Button
            tone="outline"
            busy={queue.syncing}
            busyText="Sending…"
            onPress={() => void queue.sync()}
            style={shared.smallButton}
          >
            Send now
          </Button>
        )}
      </View>
      {queue.entries
        .filter((entry) => entry.state !== "pending")
        .map((entry) => (
          <QueueEntry
            key={keyOf(entry.vehicleId, entry.date)}
            entry={entry}
            queue={queue}
            canReplace={canReplace}
          />
        ))}
    </View>
  );
}

const styles = StyleSheet.create({
  panel: { borderWidth: 1, borderRadius: 14, padding: 14, gap: 12 },
  panelHead: { flexDirection: "row", alignItems: "center", gap: 12 },
  problem: { borderWidth: 1, borderRadius: 12, padding: 12, gap: 6 },
  actions: { flexDirection: "row", gap: 8, marginTop: 4 },
  flexButton: { flex: 1, width: "auto", height: 48, paddingHorizontal: 8 },
  choices: { gap: 8, marginTop: 4 },
  choice: { height: 48 },
});
