import { useMemo, useState, type ReactNode } from "react";
import { View } from "react-native";

import { shiftDate, startOfWeek } from "@xcode/shared/dates";
import type { Formatter } from "@xcode/shared/format";
import type {
  PettyCashEntry,
  PettyCashEntryQuery,
  PettyCashOverview,
  PettyCashPeriod,
} from "@xcode/shared/pettyCash";

import { useFormats } from "../lib/formats";
import {
  Card,
  CardNote,
  CardValue,
  LineSkeleton,
  SectionTitle,
  Segmented,
} from "../shell/parts";
import { Button, ErrorText, Text, useTheme } from "../ui";
import { usePagedEntries } from "./client";
import { balanceText } from "./format";
import { CashForm } from "./forms";
import {
  DayStepper,
  EntryRow,
  SmallButton,
  Stat,
  type EntryActions,
} from "./parts";

type EntryList = ReturnType<typeof usePagedEntries>;

const PERIODS: { value: PettyCashPeriod; label: string }[] = [
  { value: "day", label: "Day" },
  { value: "week", label: "Week" },
];

function EntryListState({
  list,
  empty,
  children,
}: {
  list: EntryList;
  empty: string;
  children: ReactNode;
}) {
  if (list.loading) return <LineSkeleton lines={3} />;
  if (list.error && list.items.length === 0)
    return (
      <View style={{ gap: 8 }}>
        <ErrorText>{list.error}</ErrorText>
        <Button tone="outline" onPress={list.retry}>
          Try again
        </Button>
      </View>
    );
  if (list.items.length === 0) return <CardNote>{empty}</CardNote>;
  return (
    <View style={{ gap: 12 }}>
      {children}
      {list.error ? <ErrorText>{list.error}</ErrorText> : null}
      {list.hasMore ? (
        <Button
          tone="outline"
          busy={list.loadingMore}
          busyText="Loading…"
          onPress={list.loadMore}
        >
          Show more
        </Button>
      ) : null}
    </View>
  );
}

export function FloatSection({
  overview,
  holderId,
  loading,
  error,
  retry,
  day,
  period,
  businessDate,
  onDay,
  onPeriod,
  stamp,
  actions,
  busyId,
  onRecordExpense,
  onCreditNote,
  onSessionEnded,
}: {
  overview: PettyCashOverview | null;
  holderId: string | null;
  loading: boolean;
  error: string;
  retry: () => void;
  day: string;
  period: PettyCashPeriod;
  businessDate: string;
  onDay: (date: string) => void;
  onPeriod: (period: PettyCashPeriod) => void;
  stamp: number;
  actions: EntryActions;
  busyId: string | null;
  onRecordExpense: () => void;
  onCreditNote: () => void;
  onSessionEnded: () => void;
}) {
  const formats = useFormats();
  const { kes } = formats;
  const week = period === "week";
  const firstDay = formats.firstDayOfWeek();
  const query = useMemo<PettyCashEntryQuery>(() => {
    const from = week ? startOfWeek(day, firstDay) : day;
    const to = week ? shiftDate(from, 6) : day;
    return { from, to, ...(holderId ? { holderId } : {}) };
  }, [day, week, firstDay, holderId]);
  const list = usePagedEntries(query, stamp, onSessionEnded);
  const mine = overview?.floats.find((float) => float.holderId === holderId);
  return (
    <View style={{ gap: 16 }}>
      <Card title="My float" sub="Cash in hand now">
        {mine ? (
          <>
            <CardValue bad={mine.balance < 0}>
              {balanceText(formats, mine.balance)}
            </CardValue>
            <CardNote>
              {mine.waitingCount
                ? `${mine.waitingCount} ${mine.waitingCount === 1 ? "entry" : "entries"}, ${kes(mine.waiting)}, waiting for approval`
                : "Nothing is waiting for approval."}
            </CardNote>
            {mine.sentBack ? (
              <CardNote>{`${kes(mine.sentBack)} was sent back to you.`}</CardNote>
            ) : null}
          </>
        ) : overview ? (
          <CardNote>No cash has been given to you yet.</CardNote>
        ) : error ? (
          <ErrorText>{error}</ErrorText>
        ) : (
          <LineSkeleton lines={2} />
        )}
      </Card>
      <Segmented
        label="Show figures for"
        options={PERIODS}
        value={period}
        onChange={onPeriod}
      />
      <DayStepper
        label={week ? "Week" : "Day"}
        date={day}
        period={period}
        businessDate={businessDate}
        formats={formats}
        onChange={onDay}
      />
      {overview ? (
        <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 12 }}>
          <Stat
            label={
              week
                ? "Opening cash balance, start of week"
                : "Opening cash balance"
            }
            value={balanceText(formats, overview.figures.openingBalance)}
            bad={overview.figures.openingBalance < 0}
          />
          <Stat
            label={week ? "Money out in the week" : "Money out"}
            value={kes(overview.figures.moneyOut)}
          />
          <Stat
            label={week ? "Cash received in the week" : "Cash received"}
            value={
              overview.figures.cashReceived < 0
                ? `${kes(-overview.figures.cashReceived)} returned`
                : kes(overview.figures.cashReceived)
            }
          />
          <Stat
            label={
              week
                ? "Closing cash balance, end of week"
                : "Closing cash balance"
            }
            value={balanceText(formats, overview.figures.closingBalance)}
            bad={overview.figures.closingBalance < 0}
          />
        </View>
      ) : loading ? (
        <LineSkeleton lines={4} />
      ) : error ? (
        <View style={{ gap: 8 }}>
          <ErrorText>{error}</ErrorText>
          <Button tone="outline" onPress={retry}>
            Try again
          </Button>
        </View>
      ) : null}
      {overview?.permissions.canSpend ? (
        <View style={{ gap: 12 }}>
          <Button onPress={onRecordExpense}>Record expense</Button>
          <Button tone="outline" onPress={onCreditNote}>
            Credit note
          </Button>
        </View>
      ) : null}
      <SectionTitle>Entries</SectionTitle>
      <EntryListState
        list={list}
        empty={
          week
            ? "Nothing recorded in this week."
            : "Nothing recorded on this day."
        }
      >
        {list.items.map((entry) => (
          <EntryRow
            key={entry.id}
            entry={entry}
            formats={formats}
            showHolder={entry.holderId !== holderId}
            showDate={week}
            busy={busyId === entry.id}
            actions={actions}
          />
        ))}
      </EntryListState>
    </View>
  );
}

const WAITING: PettyCashEntryQuery = { status: "waiting" };

function groupByDate(items: PettyCashEntry[]) {
  const groups = new Map<string, PettyCashEntry[]>();
  for (const entry of items)
    groups.set(entry.date, [...(groups.get(entry.date) ?? []), entry]);
  return [...groups.entries()];
}

export function ApprovalsSection({
  overview,
  stamp,
  actions,
  busyId,
  onApproveDay,
  onSessionEnded,
}: {
  overview: PettyCashOverview | null;
  stamp: number;
  actions: EntryActions;
  busyId: string | null;
  onApproveDay: (date: string) => void;
  onSessionEnded: () => void;
}) {
  const formats = useFormats();
  const { colors } = useTheme();
  const list = usePagedEntries(WAITING, stamp, onSessionEnded);
  const limit = overview?.permissions.approvalLimit ?? null;
  return (
    <View style={{ gap: 16 }}>
      <Text style={{ fontSize: 14, color: colors.grey }}>
        {limit === null
          ? "Entries waiting for approval, oldest day first."
          : `Entries waiting for approval, oldest day first. You can approve entries up to ${formats.kes(limit)}.`}
      </Text>
      <EntryListState list={list} empty="Nothing is waiting for approval.">
        {groupByDate(list.items).map(([date, entries]) => (
          <View key={date} style={{ gap: 12 }}>
            <View
              style={{
                flexDirection: "row",
                alignItems: "center",
                justifyContent: "space-between",
                gap: 12,
              }}
            >
              <Text
                weight="bold"
                accessibilityRole="header"
                style={{ flex: 1 }}
              >
                {formats.formatDateOnly(date)}
              </Text>
              {overview?.permissions.canApproveDay ? (
                <SmallButton
                  tone="solid"
                  label={`Approve day ${formats.formatDateOnly(date)}`}
                  onPress={() => onApproveDay(date)}
                >
                  Approve day
                </SmallButton>
              ) : null}
            </View>
            {entries.map((entry) => (
              <EntryRow
                key={entry.id}
                entry={entry}
                formats={formats}
                showHolder
                busy={busyId === entry.id}
                actions={actions}
              />
            ))}
          </View>
        ))}
      </EntryListState>
    </View>
  );
}

export function GiveSection({
  day,
  businessDate,
  overview,
  stamp,
  onSaved,
  onStale,
  onCreditNote,
  onSessionEnded,
}: {
  day: string;
  businessDate: string;
  overview: PettyCashOverview;
  stamp: number;
  onSaved: (message: string) => void;
  onStale: (message: string) => void;
  onCreditNote: () => void;
  onSessionEnded: () => void;
}) {
  // A new key after each save gives the next entry its own id.
  const [round, setRound] = useState(0);
  return (
    <View style={{ gap: 24 }}>
      <CashForm
        key={round}
        date={day}
        businessDate={businessDate}
        permissions={overview.permissions}
        stamp={stamp}
        onSaved={(message) => {
          setRound((value) => value + 1);
          onSaved(message);
        }}
        onStale={onStale}
        onSessionEnded={onSessionEnded}
      />
      <Button tone="outline" onPress={onCreditNote}>
        Credit note
      </Button>
    </View>
  );
}

export function FloatsSection({
  overview,
  formats,
}: {
  overview: PettyCashOverview;
  formats: Formatter;
}) {
  const { kes } = formats;
  if (overview.floats.length === 0) return <CardNote>No floats yet.</CardNote>;
  return (
    <View style={{ gap: 12 }}>
      {overview.floats.map((float) => (
        <Card
          key={float.holderId}
          title={float.name}
          sub={float.active ? undefined : "No longer a float holder"}
        >
          <CardValue bad={float.balance < 0}>
            {balanceText(formats, float.balance)}
          </CardValue>
          <CardNote>
            {`Waiting ${kes(float.waiting)}, approved ${kes(float.approved)}, sent back ${kes(float.sentBack)}`}
          </CardNote>
          <CardNote>
            {float.lastCashOn
              ? `Last cash given ${formats.formatDateOnly(float.lastCashOn)}`
              : "No cash given yet"}
          </CardNote>
        </Card>
      ))}
    </View>
  );
}
