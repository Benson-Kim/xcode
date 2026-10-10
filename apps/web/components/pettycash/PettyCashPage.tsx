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
import { PeriodPicker } from "../period/PeriodPicker";
import { BandSkeleton } from "../revenue/RegPlate";
import {
  Banner,
  Button,
  HeroBand,
  PageHeader,
  Pager,
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
import { ViewPills } from "./ViewPills";

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

  const holderName = holderId
    ? known?.holders.find((holder) => holder.id === holderId)?.name
    : undefined;

  return (
    <section className="flex flex-col gap-3.5">
      <PageHeader title="Petty cash" description="" srOnlyTitle />

      <HeroBand
        variant="eq"
        label="Cash balance equals opening balance plus cash issued minus expenses minus credit notes"
        period={
          period && businessDate ? (
            <PeriodPicker
              period={period}
              businessDate={businessDate}
              firstDayOfWeek={formats.firstDayOfWeek()}
              onChange={setChosen}
            />
          ) : (
            <BandSkeleton />
          )
        }
        trailing={
          <>
            {permissions && (
              <RecordButtons
                permissions={permissions}
                onRecord={(kind) => setEntryDialog({ kind })}
              />
            )}
          </>
        }
      >
        <FigureCards
          overview={overview.data}
          label={holderName ? `Cash balance, ${holderName}` : "Cash balance"}
        />
      </HeroBand>

      {notice && <Banner>{notice}</Banner>}

      {overview.error && !known && (
        <div className="flex flex-wrap items-center gap-3">
          <Banner>{overview.error}</Banner>
          <Button tone="outline" onClick={overview.reload}>
            Try again
          </Button>
        </div>
      )}

      <FiltersBar
        views={
          <ViewPills
            id="petty"
            label="Petty cash"
            options={TABS}
            value={tab}
            onChange={setTab}
            count={list.data?.total}
          />
        }
        holders={permissions?.canViewAll ? known?.holders : undefined}
        holderId={holderId}
        onHolderChange={setHolderId}
        status={tab === "expenses" ? status : undefined}
        onStatusChange={setStatus}
        search={search}
        onSearchChange={setSearch}
        actions={
          permissions?.canApproveDay && oneDay ? (
            <Button
              tone="ok"
              disabled={busyId === "day"}
              onClick={() => void approveDay()}
            >
              Approve day
            </Button>
          ) : undefined
        }
      />

      <div
        role="tabpanel"
        id="petty-panel"
        aria-labelledby={`petty-tab-${tab}`}
        className="flex flex-col gap-3.5"
      >
        {list.error && <Banner>{list.error}</Banner>}

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
      </div>

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

// What this person may record: the actions on the headline card.
function RecordButtons({
  permissions,
  onRecord,
}: {
  permissions: PettyCashPermissions;
  onRecord: (kind: PettyCashKind) => void;
}) {
  return (
    <>
      {(permissions.canSpend || permissions.canIssue) && (
        <Button tone="outline" onClick={() => onRecord("credit")}>
          Credit note
        </Button>
      )}
      {permissions.canIssue && (
        <Button tone="outline" onClick={() => onRecord("cash")}>
          Cash
        </Button>
      )}
      {permissions.canSpend && (
        <Button tone="primary" onClick={() => onRecord("expense")}>
          Expense
        </Button>
      )}
    </>
  );
}
