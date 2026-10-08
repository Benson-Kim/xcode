import { useCallback, useEffect, useState } from "react";
import { View } from "react-native";

import { shiftDate, startOfWeek } from "@xcode/shared/dates";
import { plural } from "@xcode/shared/format";
import {
  pettyCashOverviewPath,
  type PettyCashDayApproved,
  type PettyCashEntry,
  type PettyCashOverview,
  type PettyCashPeriod,
  type PettyCashSaved,
} from "@xcode/shared/pettyCash";

import { SessionEndedError } from "../lib/api";
import { useFormats } from "../lib/formats";
import { useConnected } from "../lib/network";
import { LineSkeleton, SectionTitle, Segmented } from "../shell/parts";
import { Banner, Button, ErrorText } from "../ui";
import { send, useLoaded, type Outcome } from "./client";
import { CashForm, CreditForm, ExpenseForm, ReasonForm } from "./forms";
import { Notice, type EntryActions } from "./parts";
import {
  ApprovalsSection,
  FloatSection,
  FloatsSection,
  GiveSection,
} from "./sections";

export type PettyCashSection = "float" | "approvals" | "give" | "floats";

type Form =
  | { kind: "expense" | "credit" | "cash"; entry?: PettyCashEntry }
  | { kind: "remove" | "sendBack"; entry: PettyCashEntry };

type NoticeState = { tone: "ok" | "error"; text: string } | null;

const OFFLINE_NOTE =
  "No internet. Petty cash loads and saves only while you are online.";
const UNREACHABLE_NOTE =
  "Can't reach the XCODE server. Petty cash loads and saves only while it answers.";

// Petty cash: the person's own float, approvals, cash given and every float, each only with its permission.
// Everything here is online-only; the server decides what each entry allows.
export function PettyCashScreen({
  offline,
  businessDate,
  start,
  onSessionEnded,
}: {
  offline: boolean;
  businessDate?: string;
  start?: PettyCashSection;
  onSessionEnded: () => void;
}) {
  const formats = useFormats();
  const connected = useConnected();
  const [stamp, setStamp] = useState(0);
  const [date, setDate] = useState<string | null>(null);
  const [period, setPeriod] = useState<PettyCashPeriod>("day");
  const [chosen, setChosen] = useState<PettyCashSection | undefined>(start);
  const [form, setForm] = useState<Form | null>(null);
  const [notice, setNotice] = useState<NoticeState>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  // Without a holder the figures add up every float the person can see: what All floats and the permissions use.
  const overview = useLoaded<PettyCashOverview>(
    offline ? null : "setup/pettycash/overview",
    stamp,
    onSessionEnded,
  );
  // The last answer stays for its permissions while the next one loads.
  const [kept, setKept] = useState<PettyCashOverview | null>(null);
  useEffect(() => {
    if (overview.data) setKept(overview.data);
  }, [overview.data]);
  const current = overview.data ?? kept;
  const day = date ?? current?.date ?? null;
  const today = current?.businessDate ?? businessDate ?? null;

  const permissions = current?.permissions;
  const sections: { value: PettyCashSection; label: string }[] = [
    ...(permissions?.canSpend
      ? [{ value: "float" as const, label: "My float" }]
      : []),
    ...(permissions?.canApproveItem
      ? [{ value: "approvals" as const, label: "Approvals" }]
      : []),
    ...(permissions?.canIssue
      ? [{ value: "give" as const, label: "Give cash" }]
      : []),
    ...(permissions?.canViewAll
      ? [{ value: "floats" as const, label: "All floats" }]
      : []),
  ];
  const section =
    sections.find((item) => item.value === chosen)?.value ?? sections[0]?.value;

  // My float is the person's own float, even when they can see every float.
  const ownId = permissions?.holderId ?? null;
  const own = useLoaded<PettyCashOverview>(
    !offline && section === "float" && day
      ? pettyCashOverviewPath({
          date: day,
          period,
          ...(ownId ? { holderId: ownId } : {}),
        })
      : null,
    stamp,
    onSessionEnded,
  );
  const [keptOwn, setKeptOwn] = useState<PettyCashOverview | null>(null);
  useEffect(() => {
    if (own.data) setKeptOwn(own.data);
  }, [own.data]);
  const ownCurrent = own.data ?? keptOwn;
  const fresh =
    ownCurrent && ownCurrent.date === day && ownCurrent.period === period
      ? ownCurrent
      : null;

  const reload = useCallback(() => setStamp((value) => value + 1), []);
  const finish = (tone: "ok" | "error", text: string) => {
    setForm(null);
    setNotice({ tone, text });
    reload();
  };

  async function run<T>(
    id: string | null,
    call: () => Promise<Outcome<T>>,
    done: (data: T) => string,
  ) {
    setBusyId(id);
    setNotice(null);
    try {
      const result = await call();
      if (result.ok) finish("ok", done(result.data));
      else if (result.reload) finish("error", result.message);
      else setNotice({ tone: "error", text: result.message });
    } catch (reason) {
      if (reason instanceof SessionEndedError) onSessionEnded();
      else
        setNotice({
          tone: "error",
          text: "The request could not be completed.",
        });
    } finally {
      setBusyId(null);
    }
  }

  const actions: EntryActions = {
    onEdit: (entry) => {
      setNotice(null);
      setForm({ kind: entry.kind, entry });
    },
    onRemove: (entry) => {
      setNotice(null);
      setForm({ kind: "remove", entry });
    },
    onApprove: (entry) =>
      void run<PettyCashSaved>(
        entry.id,
        () =>
          send("POST", `entries/${entry.id}/approve`, {
            version: entry.version,
          }),
        () => "Entry approved.",
      ),
    onSendBack: (entry) => {
      setNotice(null);
      setForm({ kind: "sendBack", entry });
    },
  };

  function approveDay(target: string) {
    void run<PettyCashDayApproved>(
      null,
      () => send("POST", "approve-day", { date: target }),
      (result) =>
        `Approved ${plural(result.approved, "entry", "entries")}, ${formats.kes(result.total)}.${
          result.skipped
            ? ` ${plural(result.skipped, "entry was", "entries were")} left for someone else.`
            : ""
        }`,
    );
  }

  const common = {
    businessDate: today ?? "",
    permissions: permissions!,
    stamp,
    onCancel: () => setForm(null),
    onSaved: (message: string) => finish("ok", message),
    onStale: (message: string) => finish("error", message),
    onSessionEnded,
  };

  function pick(next: PettyCashSection) {
    setNotice(null);
    setChosen(next);
  }

  function body() {
    if (offline)
      return (
        <Banner tone="offline">
          {connected ? UNREACHABLE_NOTE : OFFLINE_NOTE}
        </Banner>
      );
    if (!current || !permissions || !today) {
      if (overview.error)
        return (
          <View style={{ gap: 8 }}>
            <ErrorText>{overview.error}</ErrorText>
            <Button tone="outline" onPress={overview.retry}>
              Try again
            </Button>
          </View>
        );
      return <LineSkeleton lines={4} />;
    }
    const shown = day ?? today;
    const weekEnd = shiftDate(startOfWeek(shown, formats.firstDayOfWeek()), 6);
    const formDate =
      section === "float" && period === "week"
        ? weekEnd < today
          ? weekEnd
          : today
        : shown;
    if (form) {
      if (form.kind === "remove" || form.kind === "sendBack")
        return <ReasonForm {...common} entry={form.entry} mode={form.kind} />;
      if (form.kind === "expense")
        return <ExpenseForm {...common} entry={form.entry} date={formDate} />;
      if (form.kind === "credit")
        return <CreditForm {...common} entry={form.entry} date={formDate} />;
      return <CashForm {...common} entry={form.entry} date={formDate} />;
    }
    if (!section)
      return <ErrorText>Nothing to show with your access.</ErrorText>;
    return (
      <View style={{ gap: 16 }}>
        {sections.length > 1 ? (
          <Segmented
            label="Petty cash view"
            options={sections}
            value={section}
            onChange={pick}
          />
        ) : null}
        {notice ? <Notice tone={notice.tone}>{notice.text}</Notice> : null}
        {section === "float" ? (
          <FloatSection
            overview={fresh}
            holderId={ownId}
            loading={own.loading}
            error={own.error}
            retry={own.retry}
            day={shown}
            period={period}
            businessDate={today}
            onDay={(next) => {
              setNotice(null);
              setDate(next);
            }}
            onPeriod={(next) => {
              setNotice(null);
              setPeriod(next);
            }}
            stamp={stamp}
            actions={actions}
            busyId={busyId}
            onRecordExpense={() => setForm({ kind: "expense" })}
            onCreditNote={() => setForm({ kind: "credit" })}
            onSessionEnded={onSessionEnded}
          />
        ) : section === "approvals" ? (
          <ApprovalsSection
            overview={current}
            stamp={stamp}
            actions={actions}
            busyId={busyId}
            onApproveDay={approveDay}
            onSessionEnded={onSessionEnded}
          />
        ) : section === "give" ? (
          <GiveSection
            day={formDate}
            businessDate={today}
            overview={current}
            stamp={stamp}
            onSaved={(message) => {
              setNotice({ tone: "ok", text: message });
              reload();
            }}
            onStale={(message) => finish("error", message)}
            onCreditNote={() => setForm({ kind: "credit" })}
            onSessionEnded={onSessionEnded}
          />
        ) : (
          <FloatsSection overview={current} formats={formats} />
        )}
      </View>
    );
  }

  return (
    <View style={{ gap: 16 }}>
      <SectionTitle>Petty cash</SectionTitle>
      {body()}
    </View>
  );
}
