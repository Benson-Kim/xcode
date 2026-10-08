"use client";

import { useEffect, useState } from "react";

import { plural } from "@xcode/shared/format";
import {
  PETTY_CASH_PAGE_SIZE,
  pettyCashEntriesPath,
  pettyCashOverviewPath,
  type PettyCashDayApproved,
  type PettyCashEntry,
  type PettyCashEntryPage,
  type PettyCashOverview,
  type PettyCashPeriod,
  type PettyCashSaved,
  type PettyCashStatus,
} from "@xcode/shared/pettyCash";

import { useResource } from "../../lib/data";
import { useFormats } from "../../lib/formats";
import { Banner, Button, Hint, PageHeader, Tabs, useToast } from "../ui";
import { CashTable } from "./CashTable";
import { EntriesTable } from "./EntriesTable";
import { EntryDialog, type EntryDialogState } from "./EntryDialog";
import { FigureCards } from "./FigureCards";
import { FiltersBar, type StatusFilter } from "./FiltersBar";
import { FloatsTable } from "./FloatsTable";
import { entryLabel } from "./labels";
import { RemoveDialog, SendBackDialog } from "./ReasonDialogs";
import { entryPath, failureMessage, isConflict, sendJson } from "./request";
import type { EntryActions } from "./RowActions";

type Tab = "expenses" | "cash";

const TABS: { value: Tab; label: string }[] = [
  { value: "expenses", label: "Expenses" },
  { value: "cash", label: "Cash received" },
];

export function PettyCashPage({
  initialStatus,
}: {
  initialStatus?: PettyCashStatus;
}) {
  const formats = useFormats();
  const toast = useToast();
  const [tab, setTab] = useState<Tab>("expenses");
  const [chosenDate, setChosenDate] = useState<string | null>(null);
  const [period, setPeriod] = useState<PettyCashPeriod>("day");
  const [holderId, setHolderId] = useState("");
  const [status, setStatus] = useState<StatusFilter>(initialStatus ?? "all");
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [notice, setNotice] = useState("");
  const [busyId, setBusyId] = useState<string | null>(null);
  const [entryDialog, setEntryDialog] = useState<EntryDialogState | null>(null);
  const [sendingBack, setSendingBack] = useState<PettyCashEntry | null>(null);
  const [removing, setRemoving] = useState<PettyCashEntry | null>(null);

  useEffect(() => {
    const timer = setTimeout(() => setQuery(search.trim()), 300);
    return () => clearTimeout(timer);
  }, [search]);

  // Without a date the server answers for the business date, which is how the page learns it. What the person may do
  // and who holds a float do not depend on the day or the filter, so the last answer keeps them while the next loads.
  const overview = useResource<PettyCashOverview>(
    pettyCashOverviewPath({
      date: chosenDate ?? undefined,
      period: period === "week" ? period : undefined,
      holderId: holderId || undefined,
    }),
  );
  const [known, setKnown] = useState<PettyCashOverview | undefined>(
    overview.data,
  );
  if (overview.data && overview.data !== known) setKnown(overview.data);

  const permissions = known?.permissions;
  const date = chosenDate ?? known?.date ?? null;
  const businessDate = known?.businessDate ?? null;
  const week = period === "week";
  // The server cuts weeks on the organization's first day, so a week's lists wait for its overview to say where it
  // starts.
  const shown =
    overview.data &&
    overview.data.period === period &&
    overview.data.date === date
      ? overview.data
      : null;
  const range =
    date === null
      ? null
      : week
        ? shown && { from: shown.from, to: shown.to }
        : { from: date, to: date };
  // A new entry opens on today when what is shown contains it, otherwise on its last day.
  const formDate =
    businessDate &&
    range &&
    !(range.from <= businessDate && businessDate <= range.to)
      ? range.to
      : businessDate;

  const list = useResource<PettyCashEntryPage>(
    range
      ? pettyCashEntriesPath({
          from: range.from,
          to: range.to,
          holderId: holderId || undefined,
          q: query || undefined,
          pageSize: PETTY_CASH_PAGE_SIZE,
          ...(tab === "cash"
            ? { kind: "cash" as const }
            : {
                kind: ["expense", "credit"] as const,
                ...(status === "all" ? {} : { status }),
              }),
        })
      : null,
  );
  const items = list.data?.items ?? [];
  const loading = range === null ? !overview.error : list.loading;

  function refresh() {
    overview.reload();
    list.reload();
  }

  function conflict(message: string) {
    setNotice(message);
    setEntryDialog(null);
    setSendingBack(null);
    setRemoving(null);
    refresh();
  }

  function saved(message: string) {
    setNotice("");
    setEntryDialog(null);
    setSendingBack(null);
    setRemoving(null);
    toast(message);
    refresh();
  }

  async function approve(entry: PettyCashEntry) {
    setBusyId(entry.id);
    setNotice("");
    try {
      await sendJson<PettyCashSaved>("POST", entryPath(entry.id, "approve"), {
        version: entry.version,
      });
      toast(`Approved ${entryLabel(formats, entry)}.`);
      refresh();
    } catch (reason) {
      setNotice(failureMessage(reason));
      if (isConflict(reason)) refresh();
    } finally {
      setBusyId(null);
    }
  }

  async function approveDay() {
    if (!date) return;
    setBusyId("day");
    setNotice("");
    try {
      const result = await sendJson<PettyCashDayApproved>(
        "POST",
        "setup/pettycash/approve-day",
        {
          date,
          ...(holderId ? { holderId } : {}),
        },
      );
      const skipped = result.skipped
        ? ` ${plural(result.skipped, "entry was", "entries were")} left for someone else to approve.`
        : "";
      toast(
        result.approved
          ? `Approved ${plural(result.approved, "entry", "entries")}, ${formats.kes(result.total)}.${skipped}`
          : `Nothing to approve on this day.${skipped}`,
      );
      refresh();
    } catch (reason) {
      setNotice(failureMessage(reason));
    } finally {
      setBusyId(null);
    }
  }

  const actions: EntryActions = {
    busyId,
    onApprove: (entry) => void approve(entry),
    onSendBack: setSendingBack,
    onEdit: (entry) => setEntryDialog({ kind: entry.kind, entry }),
    onRemove: setRemoving,
  };

  const toolbarActions = permissions && (
    <>
      {permissions.canSpend && (
        <Button onClick={() => setEntryDialog({ kind: "expense" })}>
          Expense
        </Button>
      )}
      {permissions.canIssue && (
        <Button tone="outline" onClick={() => setEntryDialog({ kind: "cash" })}>
          Cash
        </Button>
      )}
      {(permissions.canSpend || permissions.canIssue) && (
        <Button tone="warn" onClick={() => setEntryDialog({ kind: "credit" })}>
          Credit note
        </Button>
      )}
      {permissions.canApproveDay && !week && (
        <Button
          tone="ok"
          disabled={busyId === "day" || !date}
          onClick={() => void approveDay()}
        >
          Approve day
        </Button>
      )}
    </>
  );

  return (
    <section>
      <PageHeader title="Petty cash" description="" />

      {notice && <Banner className="mt-5">{notice}</Banner>}

      {overview.error && !known && (
        <div className="mt-5 flex flex-wrap items-center gap-3">
          <Banner>{overview.error}</Banner>
          <Button tone="outline" onClick={overview.reload}>
            Try again
          </Button>
        </div>
      )}

      <Tabs
        id="petty"
        label="Petty cash"
        options={TABS}
        value={tab}
        onChange={setTab}
        aside={<FigureCards overview={overview.data} />}
      >
        <FiltersBar
          date={date}
          range={range}
          businessDate={businessDate}
          period={period}
          onPeriodChange={setPeriod}
          onDateChange={setChosenDate}
          holders={permissions?.canViewAll ? known?.holders : undefined}
          holderId={holderId}
          onHolderChange={setHolderId}
          status={tab === "expenses" ? status : undefined}
          onStatusChange={setStatus}
          search={search}
          onSearchChange={setSearch}
          actions={toolbarActions}
        />

        {list.error && <Banner className="mt-4">{list.error}</Banner>}

        {tab === "expenses" ? (
          <EntriesTable
            entries={items}
            week={week}
            loading={loading}
            failed={Boolean(list.error)}
            actions={actions}
          />
        ) : (
          <>
            <CashTable
              entries={items}
              week={week}
              loading={loading}
              failed={Boolean(list.error)}
              actions={actions}
            />
            <FloatsTable
              floats={overview.data?.floats}
              loading={!overview.data && !overview.error}
            />
          </>
        )}

        {list.data && list.data.total > list.data.items.length && (
          <Hint className="mt-2">
            Showing the first {list.data.items.length} of {list.data.total}.
            Search or pick a manager to narrow the list.
          </Hint>
        )}
      </Tabs>

      {permissions && formDate && businessDate && (
        <EntryDialog
          state={entryDialog}
          date={formDate}
          businessDate={businessDate}
          permissions={permissions}
          holderId={holderId}
          onSaved={saved}
          onConflict={conflict}
          onClose={() => setEntryDialog(null)}
        />
      )}

      <SendBackDialog
        entry={sendingBack}
        onDone={saved}
        onConflict={conflict}
        onClose={() => setSendingBack(null)}
      />

      <RemoveDialog
        entry={removing}
        onDone={saved}
        onConflict={conflict}
        onClose={() => setRemoving(null)}
      />
    </section>
  );
}
