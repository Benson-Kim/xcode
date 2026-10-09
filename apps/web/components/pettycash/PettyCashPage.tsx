"use client";

import { useEffect, useState } from "react";

import { plural } from "@xcode/shared/format";
import type { Period } from "@xcode/shared/periods";
import {
  pettyCashEntriesPath,
  pettyCashOverviewPath,
  type PettyCashDayApproved,
  type PettyCashEntry,
  type PettyCashEntryPage,
  type PettyCashKind,
  type PettyCashOverview,
  type PettyCashPermissions,
  type PettyCashSaved,
  type PettyCashStatus,
} from "@xcode/shared/pettyCash";

import { useAppearance } from "../../lib/appearance";
import { useResource } from "../../lib/data";
import { useFormats } from "../../lib/formats";
import {
  Banner,
  Button,
  PageHeader,
  Pager,
  Tabs,
  usePaging,
  useToast,
} from "../ui";
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
  initialDate,
}: {
  initialStatus?: PettyCashStatus;
  initialDate?: string;
}) {
  const formats = useFormats();
  const toast = useToast();
  const appearanceDate = useAppearance().appearance?.businessDate;
  const [tab, setTab] = useState<Tab>("expenses");
  const [chosen, setChosen] = useState<Period | null>(
    initialDate ? { from: initialDate, to: initialDate, unit: "day" } : null,
  );
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

  // Without a period the server answers for the business date, which is how the page learns it. What the person may
  // do and who holds a float do not depend on the days or the filter, so the last answer keeps them while the next
  // loads.
  const overview = useResource<PettyCashOverview>(
    pettyCashOverviewPath({
      from: chosen?.from,
      to: chosen?.to,
      holderId: holderId || undefined,
    }),
  );
  const [known, setKnown] = useState<PettyCashOverview | undefined>(
    overview.data,
  );
  if (overview.data && overview.data !== known) setKnown(overview.data);

  const permissions = known?.permissions;
  const businessDate = known?.businessDate ?? appearanceDate ?? null;
  const range = chosen ?? (known ? { from: known.from, to: known.to } : null);
  const period: Period | null = range && {
    ...range,
    unit: chosen?.unit ?? "day",
  };
  const oneDay = range ? range.from === range.to : true;
  const date = range && oneDay ? range.from : null;
  // A new entry opens on today when what is shown contains it, otherwise on its last day.
  const formDate =
    businessDate &&
    range &&
    !(range.from <= businessDate && businessDate <= range.to)
      ? range.to
      : businessDate;

  const paging = usePaging(
    `${range?.from}|${range?.to}|${holderId}|${query}|${tab}|${status}`,
  );
  const list = useResource<PettyCashEntryPage>(
    range
      ? pettyCashEntriesPath({
          from: range.from,
          to: range.to,
          holderId: holderId || undefined,
          q: query || undefined,
          page: paging.page,
          pageSize: paging.pageSize,
          ...(tab === "cash"
            ? { kind: "cash" as const }
            : {
                kind: ["expense", "credit"] as const,
                ...(status === "all" ? {} : { status }),
              }),
        })
      : null,
  );
  if (list.data) paging.stepBack(list.data.total);
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
    <ToolbarActions
      permissions={permissions}
      canApproveDay={permissions.canApproveDay && oneDay}
      approving={busyId === "day"}
      onRecord={(kind) => setEntryDialog({ kind })}
      onApproveDay={() => void approveDay()}
    />
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

      <div className="mt-5">
        <FigureCards overview={overview.data} />
      </div>

      <Tabs
        id="petty"
        label="Petty cash"
        options={TABS}
        value={tab}
        onChange={setTab}
      >
        <FiltersBar
          period={period}
          businessDate={businessDate}
          firstDayOfWeek={formats.firstDayOfWeek()}
          onPeriodChange={setChosen}
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
            days={!oneDay}
            loading={loading}
            failed={Boolean(list.error)}
            actions={actions}
          />
        ) : (
          <>
            <CashTable
              entries={items}
              days={!oneDay}
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

        <Pager
          page={paging.page}
          pageSize={paging.pageSize}
          total={list.data?.total ?? 0}
          onPageChange={paging.setPage}
          onPageSizeChange={paging.setPageSize}
        />
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

// What this person may record, and approving the day shown.
function ToolbarActions({
  permissions,
  canApproveDay,
  approving,
  onRecord,
  onApproveDay,
}: {
  permissions: PettyCashPermissions;
  canApproveDay: boolean;
  approving: boolean;
  onRecord: (kind: PettyCashKind) => void;
  onApproveDay: () => void;
}) {
  return (
    <>
      {permissions.canSpend && (
        <Button onClick={() => onRecord("expense")}>Expense</Button>
      )}
      {permissions.canIssue && (
        <Button tone="outline" onClick={() => onRecord("cash")}>
          Cash
        </Button>
      )}
      {(permissions.canSpend || permissions.canIssue) && (
        <Button tone="warn" onClick={() => onRecord("credit")}>
          Credit note
        </Button>
      )}
      {canApproveDay && (
        <Button tone="ok" disabled={approving} onClick={onApproveDay}>
          Approve day
        </Button>
      )}
    </>
  );
}
